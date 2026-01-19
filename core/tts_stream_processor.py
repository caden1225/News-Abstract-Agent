"""
TTS流式处理器模块
负责处理TTS流式合成和音频队列管理
"""
import asyncio
import base64
import logging
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)


class TTSStreamProcessor:
    """TTS流式处理器类"""
    
    def __init__(self, tts_service, language: str, request_id: str):
        """
        初始化TTS流式处理器
        
        Args:
            tts_service: TTS服务实例
            language: TTS语言
            request_id: 请求ID
        """
        self.tts_service = tts_service
        self.language = language
        self.request_id = request_id
        self.audio_chunk_count = 0
    
    async def process_tts_stream(
        self,
        text_stream: AsyncGenerator[str, None],
        audio_queue: asyncio.Queue
    ):
        """
        处理流式TTS合成
        
        优化：
        - 添加背压控制
        - 添加错误恢复机制
        
        Args:
            text_stream: 文本流生成器
            audio_queue: 音频队列
        """
        from tts_utils.tts_optimization_utils import BackpressureController
        from core.retry import retry_async, RetryConfig
        
        # 优化：创建背压控制器
        audio_backpressure = BackpressureController(audio_queue, threshold=0.8)
        
        try:
            logger.info(
                f"开始处理流式TTS: request_id={self.request_id}, language={self.language}"
            )
            
            # 优化：添加重试机制
            @retry_async(RetryConfig(max_attempts=2, initial_delay=0.1))
            async def synthesize_with_retry():
                """带重试的TTS合成"""
                async for audio_chunk in self.tts_service.synthesize_stream(
                    text_stream=text_stream,
                    language=self.language,
                    request_id=self.request_id
                ):
                    # 优化：使用背压控制
                    audio_base64 = base64.b64encode(audio_chunk.audio_data).decode("utf-8")
                    await audio_backpressure.put(audio_base64)
                    self.audio_chunk_count += 1
                    
                    logger.debug(
                        f"✅ TTS音频块生成 #{self.audio_chunk_count}: "
                        f"chunk_id={audio_chunk.chunk_id}, "
                        f"text_len={len(audio_chunk.text)}, "
                        f"audio_len={len(audio_chunk.audio_data)} bytes, "
                        f"is_final={audio_chunk.is_final}"
                    )
            
            await synthesize_with_retry()
            
            logger.info(
                f"流式TTS处理完成: request_id={self.request_id}, "
                f"共生成 {self.audio_chunk_count} 个音频块, "
                f"背压触发次数: {audio_backpressure.get_backpressure_count()}"
            )
        except Exception as e:
            logger.error(
                f"❌ 流式TTS处理失败: request_id={self.request_id}, error={e}",
                exc_info=True
            )
            # 优化：错误恢复 - 如果失败，尝试降级处理
            if self.audio_chunk_count == 0:  # 还没有生成任何chunk
                logger.warning(f"TTS流式处理失败，尝试降级处理: request_id={self.request_id}")
                try:
                    # 收集所有文本，使用批量模式作为降级
                    text_buffer = ""
                    async for token in text_stream:
                        text_buffer += token
                    
                    if text_buffer:
                        logger.info(f"使用批量模式作为降级: request_id={self.request_id}, text_len={len(text_buffer)}")
                        audio_data = await self.tts_service.synthesize_batch(
                            text=text_buffer,
                            language=self.language,
                            request_id=self.request_id
                        )
                        if audio_data:
                            audio_base64 = base64.b64encode(audio_data).decode("utf-8")
                            await audio_backpressure.put(audio_base64)
                            self.audio_chunk_count += 1
                            logger.info(f"降级模式成功: request_id={self.request_id}")
                            return
                except Exception as fallback_error:
                    logger.error(f"降级处理也失败: {fallback_error}", exc_info=True)
            
            # 如果降级也失败，抛出异常
            raise
    
    async def generate_tts_chunk(
        self,
        text: str,
        audio_queue: asyncio.Queue
    ):
        """
        异步生成 TTS 音频块（批量模式，兼容旧代码）
        
        Args:
            text: 要合成的文本
            audio_queue: 音频队列
        """
        try:
            # 使用批量模式合成
            audio_data = await self.tts_service.synthesize_batch(
                text=text,
                language=self.language,
                request_id=f"chunk_{id(text)}"
            )
            
            # 转换为base64
            audio_base64 = base64.b64encode(audio_data).decode("utf-8")
            
            await audio_queue.put(audio_base64)
            logger.debug(
                f"TTS 块生成完成: text_len={len(text)}, language={self.language}"
            )
            
        except Exception as e:
            logger.error(f"TTS 生成失败: {e}", exc_info=True)
            raise
