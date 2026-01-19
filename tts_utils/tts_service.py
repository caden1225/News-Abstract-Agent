"""
TTS 服务模块
使用本地 CosyVoice2/CosyVoice3 模型进行流式文本转语音合成

核心功能：
1. 流式文本输入（token级别）
2. 智能分句（保证语音连贯性）
3. 音频流式输出
4. ID标记机制（保证可追踪性）
"""
import asyncio
import logging
import uuid
from typing import AsyncGenerator, Optional

from llm_utils.config import config
from models.tts import AudioChunk, SentenceBuffer

logger = logging.getLogger(__name__)


class TTSService:
    """TTS 服务类 - 使用本地 CosyVoice2/CosyVoice3 模型"""

    def __init__(
        self,
        enabled: Optional[bool] = None,
        model_dir: Optional[str] = None,
        model_type: Optional[str] = None,
        spk_id: Optional[str] = None
    ):
        """
        初始化TTS服务

        Args:
            enabled: 是否启用TTS（None 时从配置读取）
            model_dir: 模型目录路径（None 时从配置读取）
            model_type: 模型类型 ("auto", "cosyvoice2", "cosyvoice3")（None 时从配置读取）
            spk_id: 默认说话人ID（None 时从配置读取）
        """
        from .local_tts_service import LocalTTSService

        if model_dir is None:
            model_dir = config.get("tts.local_model_dir")

        if model_type is None:
            model_type = config.get("tts.local_model_type", "auto")

        if spk_id is None:
            spk_id = config.get("tts.default_spk_id", "girl_zh")

        if enabled is None:
            enabled = config.get("tts.enabled", True)

        self.enabled = enabled
        self.local_service = LocalTTSService(
            model_dir=model_dir,
            model_type=model_type,
            spk_id=spk_id,
            enabled=enabled
        )

        logger.info(
            f"TTS服务已初始化: model_dir={model_dir}, "
            f"model_type={model_type}, spk_id={spk_id}, enabled={enabled}"
        )

    async def synthesize_stream(
        self,
        text_stream: AsyncGenerator[str, None],
        language: str = "zh",
        request_id: Optional[str] = None,
        format: str = "pcm",
        sample_rate: int = 24000,
        voice: Optional[str] = None
    ) -> AsyncGenerator[AudioChunk, None]:
        """
        流式TTS合成（核心方法）

        工作流程：
        1. 接收文本流（token级别）
        2. 智能分句（检测句子边界）
        3. 对每个完整句子调用TTS服务
        4. 流式返回音频块

        Args:
            text_stream: 文本流（AsyncGenerator）
            language: 语言代码（zh, en, ko等）
            request_id: 请求ID（用于追踪）
            format: 音频格式（pcm, wav, mp3）
            sample_rate: 采样率（默认24000Hz）
            voice: 语音ID（可选）

        Yields:
            AudioChunk: 音频块对象
        """
        if not self.enabled:
            logger.warning("TTS服务未启用，跳过合成")
            return

        async for audio_chunk in self.local_service.synthesize_stream(
            text_stream=text_stream,
            language=language,
            request_id=request_id,
            format=format,
            sample_rate=sample_rate,
            voice=voice
        ):
            yield audio_chunk

    async def synthesize_batch(
        self,
        text: str,
        language: str = "zh",
        request_id: Optional[str] = None,
        format: str = "pcm",
        sample_rate: int = 24000,
        voice: Optional[str] = None
    ) -> bytes:
        """
        批量TTS合成（非流式模式）

        Args:
            text: 完整文本
            language: 语言代码
            request_id: 请求ID
            format: 音频格式
            sample_rate: 采样率
            voice: 语音ID

        Returns:
            完整的音频数据（bytes）
        """
        if not self.enabled:
            logger.warning("TTS服务未启用，跳过合成")
            return b""

        if request_id is None:
            request_id = f"tts_{uuid.uuid4().hex[:8]}"

        logger.info(f"批量TTS合成: request_id={request_id}, text_length={len(text)}")

        # 将文本转换为流式输入
        async def text_stream():
            yield text

        # 收集所有音频块
        audio_chunks = []
        async for audio_chunk in self.synthesize_stream(
            text_stream=text_stream(),
            language=language,
            request_id=request_id,
            format=format,
            sample_rate=sample_rate,
            voice=voice
        ):
            audio_chunks.append(audio_chunk.audio_data)

        # 合并所有音频块
        if audio_chunks:
            return b"".join(audio_chunks)
        else:
            return b""

    def list_speakers(self):
        """列出所有可用的说话人ID"""
        return self.local_service.list_speakers()


# 全局TTS服务实例（单例模式）
_tts_service: Optional[TTSService] = None


def get_tts_service() -> TTSService:
    """获取TTS服务实例（单例）"""
    global _tts_service

    if _tts_service is None:
        _tts_service = TTSService()

    return _tts_service
