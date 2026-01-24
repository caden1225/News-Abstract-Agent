"""
音频分块器模块
负责将TTS生成的PCM音频按固定大小切分
"""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class AudioChunker:
    """
    PCM音频分块器
    
    功能：
    1. 缓存TTS生成的PCM音频数据
    2. 按8192字节切分（保证2字节对齐）
    3. 流式输出音频块
    
    使用场景：
    - TTS流式生成音频，边生成边分块
    - 保证下发到端侧的每个音频包不超过8KB
    """
    
    def __init__(self, chunk_size: int = 8192):
        """
        初始化音频分块器
        
        Args:
            chunk_size: 每个chunk的大小（字节），必须是2的倍数（2字节对齐）
        """
        if chunk_size % 2 != 0:
            raise ValueError(f"chunk_size必须是2的倍数（2字节对齐），当前值: {chunk_size}")
        
        self.chunk_size = chunk_size
        self.buffer = bytearray()
        self.total_input_bytes = 0
        self.total_output_chunks = 0
        
        logger.debug(f"AudioChunker初始化: chunk_size={chunk_size}")
    
    def add_audio(self, audio_data: bytes) -> List[bytes]:
        """
        添加音频数据，返回完整的chunk列表
        
        Args:
            audio_data: PCM音频数据（16-bit）
        
        Returns:
            完整的chunk列表（每个chunk大小为chunk_size）
        """
        if not audio_data:
            return []
        
        self.total_input_bytes += len(audio_data)
        self.buffer.extend(audio_data)
        
        chunks = []
        while len(self.buffer) >= self.chunk_size:
            # 提取一个完整的chunk
            chunk = bytes(self.buffer[:self.chunk_size])
            chunks.append(chunk)
            self.buffer = self.buffer[self.chunk_size:]
            self.total_output_chunks += 1
        
        if chunks:
            logger.debug(
                f"AudioChunker输出: {len(chunks)}个chunk, "
                f"缓存剩余: {len(self.buffer)}字节"
            )
        
        return chunks
    
    def flush(self) -> Optional[bytes]:
        """
        刷新剩余数据，返回最后一个chunk（可能小于chunk_size）
        
        Returns:
            剩余的音频数据，如果没有则返回None
        """
        if not self.buffer:
            return None
        
        # 确保2字节对齐
        if len(self.buffer) % 2 != 0:
            logger.warning(
                f"缓存数据不是2字节对齐: {len(self.buffer)}字节, "
                f"将截断最后1字节"
            )
            self.buffer = self.buffer[:-1]
        
        if not self.buffer:
            return None
        
        chunk = bytes(self.buffer)
        self.buffer.clear()
        self.total_output_chunks += 1
        
        logger.debug(
            f"AudioChunker flush: 输出最后一个chunk, "
            f"大小: {len(chunk)}字节"
        )
        
        return chunk
    
    def get_stats(self) -> dict:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "total_input_bytes": self.total_input_bytes,
            "total_output_chunks": self.total_output_chunks,
            "buffer_remaining": len(self.buffer),
            "chunk_size": self.chunk_size
        }
