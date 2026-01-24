"""
DashScope TTS 服务
使用阿里云通义千问 TTS API 进行语音合成
支持流式返回
"""
import os
import logging
import asyncio
import base64
import numpy as np
from typing import Optional, List
from threading import Lock

try:
    import dashscope
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False
    dashscope = None

from llm_utils.config import config

logger = logging.getLogger(__name__)


def map_language_code_to_dashscope(language_code: str) -> str:
    """
    将语言代码映射到 DashScope 的 language_type
    
    Args:
        language_code: 语言代码 (zh, en, ko 等)
    
    Returns:
        DashScope language_type (Chinese, English, Korean 等)
    """
    language_map = {
        "zh": "Chinese",
        "en": "English",
        "ko": "Korean",
        "ja": "Japanese",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "pt": "Portuguese",
        "ru": "Russian",
        "ar": "Arabic",
    }
    return language_map.get(language_code.lower(), "Chinese")  # 默认中文


class DashScopeTTSService:
    """
    DashScope TTS 服务
    
    特点：
    1. 使用阿里云通义千问 TTS API
    2. 支持流式返回
    3. 无需本地模型，通过API调用
    """

    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化TTS服务"""
        # 防止重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return

        if not DASHSCOPE_AVAILABLE:
            raise RuntimeError("DashScope SDK 未安装，请运行: pip install dashscope")

        # TTS 参数
        tts_config = config.get("tts", {})
        dashscope_config = tts_config.get("dashscope", {})
        
        # API Key（优先从环境变量读取，其次从配置文件）
        self.api_key = os.getenv("DASHSCOPE_API_KEY") or dashscope_config.get("api_key", "")
        if not self.api_key:
            raise ValueError("DashScope API Key 未配置，请设置环境变量 DASHSCOPE_API_KEY 或在配置文件中配置")

        # 模型配置
        self.model = dashscope_config.get("model", "qwen3-tts-flash")
        self.voice = dashscope_config.get("voice", "Cherry")
        self.language_type = dashscope_config.get("language_type", "Chinese")
        
        # API URL（支持不同地域）
        api_url = dashscope_config.get("api_url", "https://dashscope.aliyuncs.com/api/v1")
        # 确保 URL 格式正确（必须以 http:// 或 https:// 开头）
        if api_url.startswith("//"):
            # 如果以 // 开头，添加 https: 前缀
            api_url = "https:" + api_url
            logger.warning(f"API URL 格式已自动修复: {api_url}")
        elif not api_url.startswith(("http://", "https://")):
            # 如果完全没有协议前缀，添加 https://
            api_url = "https://" + api_url
            logger.warning(f"API URL 格式已自动修复: {api_url}")
        dashscope.base_http_api_url = api_url
        logger.info(f"DashScope API URL: {api_url}")

        # 音频参数（确保 sample_rate 是整数类型）
        sample_rate = dashscope_config.get("sample_rate", 24000)
        self.sample_rate = int(sample_rate) if sample_rate else 24000
        self.enabled = True

        logger.info(f"DashScope TTS 初始化: model={self.model}, voice={self.voice}, "
                   f"language_type={self.language_type}, sample_rate={self.sample_rate}Hz")

        self._initialized = True

    def load_model(self):
        """DashScope 无需加载模型（API服务）"""
        logger.info("DashScope TTS 使用 API 服务，无需加载模型")
        pass

    def list_speakers(self) -> List[str]:
        """获取可用的说话人列表（预定义的音色）"""
        # DashScope 支持的音色列表（根据实际API文档调整）
        return ["Cherry", "Alice", "Bob", "Diana", "Echo", "Frank", "Grace", "Henry"]

    def set_speaker(self, voice: str):
        """设置音色"""
        available_voices = self.list_speakers()
        if voice not in available_voices:
            logger.warning(f"音色 '{voice}' 不在预定义列表中，但将继续使用")
        self.voice = voice
        logger.info(f"音色已切换为: {voice}")

    async def synthesize(
        self,
        text: str,
        spk_id: Optional[str] = None,
        request_id: Optional[str] = None,
        is_last_chunk: bool = False,
        language: Optional[str] = None
    ) -> bytes:
        """
        非流式语音合成（内部使用流式API，收集所有音频后返回）
        
        Args:
            text: 待合成文本
            spk_id: 说话人ID（可选，默认使用配置的voice）
            request_id: 请求ID（DashScope 暂不支持session管理）
            is_last_chunk: 是否为最后一个 chunk（DashScope 暂不支持）
            language: 语言代码（如 zh, en, ko），如果提供则覆盖配置的 language_type
        
        Returns:
            PCM音频数据 (16-bit, mono, 24000Hz)
        """
        if not text or not text.strip():
            logger.warning("文本为空，返回空音频")
            return b""

        # 使用指定的音色或默认音色
        voice = spk_id if spk_id else self.voice
        
        # 使用传入的语言参数，如果没有则使用配置的默认值
        if language:
            language_type = map_language_code_to_dashscope(language)
        else:
            language_type = self.language_type

        logger.info(f"开始合成: {len(text)} 字符, voice={voice}, model={self.model}, language_type={language_type}")

        # 在事件循环中运行同步API调用
        loop = asyncio.get_event_loop()

        def run_synthesis():
            """在单独的线程中运行TTS API调用"""
            try:
                audio_chunks = []
                
                # 调用 DashScope API（流式模式）
                response = dashscope.MultiModalConversation.call(
                    api_key=self.api_key,
                    model=self.model,
                    text=text,
                    voice=voice,
                    language_type=language_type,
                    stream=True
                )

                # 收集所有音频chunks
                for chunk in response:
                    if chunk.output is not None:
                        audio = chunk.output.audio
                        if audio.data is not None:
                            # 解码 base64 音频数据
                            wav_bytes = base64.b64decode(audio.data)
                            # 转换为 numpy 数组（int16格式）
                            audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
                            audio_chunks.append(audio_np.tobytes())
                        
                        # 检查是否完成
                        if chunk.output.finish_reason == "stop":
                            logger.debug(f"TTS 合成完成: expires_at={chunk.output.audio.expires_at if hasattr(chunk.output.audio, 'expires_at') else 'N/A'}")
                            break

                if not audio_chunks:
                    logger.warning("未收到任何音频数据")
                    return b""

                # 合并所有音频chunks
                audio_data = b"".join(audio_chunks)
                logger.info(f"合成完成: {len(audio_data)} 字节, {len(audio_data)/2/self.sample_rate:.2f}秒")
                return audio_data

            except Exception as e:
                logger.error(f"DashScope TTS 合成失败: {e}", exc_info=True)
                raise

        # 使用线程池执行同步API调用
        audio_data = await loop.run_in_executor(None, run_synthesis)
        return audio_data

    async def synthesize_streaming(
        self,
        text_stream,
        spk_id: Optional[str] = None
    ):
        """
        流式语音合成（生成器）
        
        Args:
            text_stream: 文本流生成器
            spk_id: 说话人ID（可选）
        
        Yields:
            PCM音频数据 (16-bit, mono, 24000Hz)
        """
        # 收集所有文本
        all_text = ""
        async for text in text_stream:
            all_text += text

        if not all_text or not all_text.strip():
            return

        voice = spk_id if spk_id else self.voice
        logger.info(f"开始流式合成: {len(all_text)} 字符, voice={voice}")

        loop = asyncio.get_event_loop()

        def run_streaming_synthesis():
            """在单独的线程中运行流式TTS，返回音频chunks列表"""
            try:
                audio_chunks = []
                response = dashscope.MultiModalConversation.call(
                    api_key=self.api_key,
                    model=self.model,
                    text=all_text,
                    voice=voice,
                    language_type=self.language_type,
                    stream=True
                )

                for chunk in response:
                    if chunk.output is not None:
                        audio = chunk.output.audio
                        if audio.data is not None:
                            wav_bytes = base64.b64decode(audio.data)
                            audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
                            audio_chunks.append(audio_np.tobytes())
                        
                        if chunk.output.finish_reason == "stop":
                            break

                return audio_chunks

            except Exception as e:
                logger.error(f"DashScope 流式TTS 合成失败: {e}", exc_info=True)
                raise

        # 使用线程池执行并yield结果
        audio_chunks = await loop.run_in_executor(None, run_streaming_synthesis)
        for audio_chunk in audio_chunks:
            yield audio_chunk


# 全局TTS服务实例
_dashscope_service: Optional[DashScopeTTSService] = None


def get_tts_service() -> DashScopeTTSService:
    """获取DashScope TTS服务单例"""
    global _dashscope_service
    if _dashscope_service is None:
        _dashscope_service = DashScopeTTSService()
    return _dashscope_service


async def initialize_tts():
    """初始化TTS服务（在应用启动时调用）"""
    global _dashscope_service
    if _dashscope_service is None:
        _dashscope_service = DashScopeTTSService()

    try:
        _dashscope_service.load_model()
        logger.info("✅ DashScope TTS 服务初始化成功")
        return True
    except Exception as e:
        logger.error(f"❌ DashScope TTS 服务初始化失败: {e}")
        return False
