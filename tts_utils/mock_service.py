"""
Mock TTS 服务
用于测试和开发，不依赖实际TTS模型
"""
import asyncio
import logging
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)


class MockTTSService:
    """
    Mock TTS服务

    生成静音音频数据，用于测试流程
    """

    def __init__(self, sample_rate: int = 22050):
        self.sample_rate = sample_rate
        self.spk_id = "mock_speaker"
        logger.info("Mock TTS 服务已初始化")

    def load_model(self):
        """模拟模型加载"""
        logger.info("Mock TTS 模型已加载")
        pass

    def list_speakers(self):
        """返回模拟的说话人列表"""
        return ["mock_speaker", "zh_girl", "zh_man"]

    def set_speaker(self, spk_id: str):
        """设置说话人"""
        self.spk_id = spk_id
        logger.debug(f"Mock TTS 说话人设置为: {spk_id}")

    async def synthesize_streaming(
        self,
        text_stream: AsyncGenerator[str, None],
        spk_id: Optional[str] = None
    ) -> AsyncGenerator[bytes, None]:
        """
        模拟流式语音合成

        生成静音音频数据 (16-bit PCM, mono)
        """
        spk_id = spk_id or self.spk_id
        all_text = ""

        # 收集所有文本
        async for text in text_stream:
            all_text += text

        if not all_text:
            return

        logger.info(f"Mock TTS 开始合成: {len(all_text)} 字符")

        # 按字符数估算音频时长 (平均 3 字符/秒)
        estimated_duration = len(all_text) / 3.0
        chunk_duration = 0.5  # 每个chunk 0.5秒
        samples_per_chunk = int(self.sample_rate * chunk_duration)

        # 生成多个音频chunks
        num_chunks = int(estimated_duration / chunk_duration) + 1

        for i in range(num_chunks):
            # 生成静音音频数据 (16-bit PCM)
            audio_chunk = bytes(samples_per_chunk * 2)  # 2 bytes per sample

            # 模拟处理延迟
            await asyncio.sleep(0.05)

            yield audio_chunk

        logger.info(f"Mock TTS 合成完成: {num_chunks} chunks, {estimated_duration:.2f}秒")

    async def synthesize(
        self,
        text: str,
        spk_id: Optional[str] = None,
        request_id: Optional[str] = None,
        is_last_chunk: bool = False,
        language: Optional[str] = None
    ) -> bytes:
        """
        模拟非流式语音合成
        
        Args:
            text: 待合成文本
            spk_id: 说话人ID（可选）
            request_id: 请求ID（可选，Mock 服务不使用）
            is_last_chunk: 是否为最后一个 chunk（可选，Mock 服务不使用）
            language: 语言代码（可选，Mock 服务不使用）
        """
        spk_id = spk_id or self.spk_id

        logger.info(f"Mock TTS 开始合成: {len(text)} 字符")

        # 估算音频时长
        estimated_duration = len(text) / 3.0
        total_samples = int(self.sample_rate * estimated_duration)

        # 生成静音音频
        audio_data = bytes(total_samples * 2)

        logger.info(f"Mock TTS 合成完成: {len(audio_data)} 字节, {estimated_duration:.2f}秒")

        return audio_data
