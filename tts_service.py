"""
TTS语音播报模块
调用TTS服务将文本转换为语音
"""
import logging
import httpx
import os
import base64
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class TTSService:
    """文本转语音服务"""

    def __init__(self):
        """初始化TTS服务"""
        # TTS服务地址(可以通过环境变量配置)
        self.tts_url = os.getenv(
            "TTS_SERVICE_URL",
            "http://localhost:13984/api/llm/v1/tts"  # 假设Sidecar提供TTS服务
        )
        self.api_key = os.getenv("LLM_API_KEY", "zbx:...")

    async def text_to_speech(self, text: str, voice: str = "default") -> Optional[str]:
        """
        将文本转换为语音

        Args:
            text: 要转换的文本
            voice: 音色(可选)

        Returns:
            音频数据的base64编码,如果失败则返回None
        """
        try:
            # 调用TTS服务
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.tts_url,
                    json={
                        "text": text,
                        "voice": voice
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()
                result = response.json()

                # 假设返回格式为 {"audio": "base64_encoded_audio_data"}
                audio_data = result.get("audio")
                if audio_data:
                    logger.info(f"TTS转换成功,文本长度: {len(text)}")
                    return audio_data
                else:
                    logger.warning("TTS响应中未包含音频数据")
                    return None

        except Exception as e:
            logger.error(f"TTS转换失败: {e}", exc_info=True)
            return None

    async def text_to_speech_file(self, text: str, output_path: str, voice: str = "default") -> bool:
        """
        将文本转换为语音并保存到文件

        Args:
            text: 要转换的文本
            output_path: 输出文件路径
            voice: 音色(可选)

        Returns:
            是否成功
        """
        try:
            audio_base64 = await self.text_to_speech(text, voice)
            if audio_base64:
                # 解码base64数据
                audio_data = base64.b64decode(audio_base64)

                # 保存到文件
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(audio_data)

                logger.info(f"音频文件保存成功: {output_path}")
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"保存音频文件失败: {e}", exc_info=True)
            return False


    async def generate_news_audio(self, news_report: str) -> Optional[Dict]:
        """
        为新闻播报稿生成语音

        Args:
            news_report: 新闻播报稿文本

        Returns:
            包含音频数据的字典,如果失败则返回None
        """
        try:
            # 调用TTS服务生成语音
            audio_base64 = await self.text_to_speech(news_report, voice="news_anchor")

            if audio_base64:
                return {
                    "audio": audio_base64,
                    "format": "mp3",  # 假设返回mp3格式
                    "text": news_report
                }
            else:
                return None

        except Exception as e:
            logger.error(f"生成新闻语音失败: {e}", exc_info=True)
            return None


# 降级方案:使用简单的占位符
class MockTTSService:
    """Mock TTS服务 - 用于测试或降级"""

    async def text_to_speech(self, text: str, voice: str = "default") -> Optional[str]:
        """
        模拟TTS转换,返回占位符

        实际生产中应该调用真实的TTS服务
        """
        logger.info(f"[Mock TTS] 模拟转换文本: {text[:50]}...")
        # 返回一个空的base64字符串作为占位符
        return ""

    async def text_to_speech_file(self, text: str, output_path: str, voice: str = "default") -> bool:
        """模拟保存音频文件"""
        logger.info(f"[Mock TTS] 模拟保存音频到: {output_path}")
        # 创建一个空的音频文件作为占位符
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(b"")  # 空文件
        return True

    async def generate_news_audio(self, news_report: str) -> Optional[Dict]:
        """模拟生成新闻音频"""
        logger.info(f"[Mock TTS] 模拟生成新闻音频,文本长度: {len(news_report)}")
        return {
            "audio": "",  # 空的base64
            "format": "mp3",
            "text": news_report,
            "mock": True  # 标记为mock数据
        }


# 测试代码
if __name__ == "__main__":
    import asyncio

    async def test():
        # 使用Mock服务测试
        tts = MockTTSService()
        result = await tts.text_to_speech("这是一条测试新闻播报")
        print(f"TTS结果: {result}")

        # 测试生成新闻音频
        audio = await tts.generate_news_audio("各位听众好,以下是今日热点新闻...")
        print(f"新闻音频: {audio}")

    asyncio.run(test())
