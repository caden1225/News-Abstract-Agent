"""
TTS优化工具类
实现文档中提出的优化方案
"""
import asyncio
import logging
from typing import Optional, List
from collections import deque

logger = logging.getLogger(__name__)


class AdaptiveTimeout:
    """自适应超时控制器
    
    根据数据流动态调整超时时间：
    - 有数据时：减小超时（加快响应）
    - 无数据时：增大超时（减少CPU占用）
    """
    
    def __init__(
        self,
        initial: float = 0.1,
        min_timeout: float = 0.01,
        max_timeout: float = 0.5,
        decay_factor: float = 0.9,
        growth_factor: float = 1.1
    ):
        """
        初始化自适应超时
        
        Args:
            initial: 初始超时时间（秒）
            min_timeout: 最小超时时间（秒）
            max_timeout: 最大超时时间（秒）
            decay_factor: 有数据时的衰减因子
            growth_factor: 无数据时的增长因子
        """
        self.timeout = initial
        self.min_timeout = min_timeout
        self.max_timeout = max_timeout
        self.decay_factor = decay_factor
        self.growth_factor = growth_factor
    
    def adjust(self, has_data: bool) -> float:
        """
        根据是否有数据调整超时
        
        Args:
            has_data: 是否有数据
        
        Returns:
            调整后的超时时间
        """
        if has_data:
            # 有数据，减小超时（加快响应）
            self.timeout = max(self.min_timeout, self.timeout * self.decay_factor)
        else:
            # 无数据，增大超时（减少CPU占用）
            self.timeout = min(self.max_timeout, self.timeout * self.growth_factor)
        
        return self.timeout
    
    def get_timeout(self) -> float:
        """获取当前超时时间"""
        return self.timeout
    
    def reset(self):
        """重置超时时间到初始值"""
        self.timeout = self.min_timeout


class BackpressureController:
    """背压控制器
    
    监控队列使用率，当超过阈值时触发背压控制：
    - 暂停数据生产（暂停LLM生成）
    - 给队列时间处理积压数据
    """
    
    def __init__(self, queue: asyncio.Queue, threshold: float = 0.8):
        """
        初始化背压控制器
        
        Args:
            queue: 要监控的队列
            threshold: 触发背压的阈值（0-1）
        """
        self.queue = queue
        self.threshold = threshold
        self.maxsize = queue.maxsize if queue.maxsize > 0 else float('inf')
        self._backpressure_count = 0
    
    async def put(self, item: any) -> bool:
        """
        带背压控制的put操作
        
        Args:
            item: 要放入队列的项
        
        Returns:
            是否成功放入（False表示触发背压）
        """
        if self.maxsize == float('inf'):
            await self.queue.put(item)
            return True
        
        usage = self.queue.qsize() / self.maxsize
        
        if usage > self.threshold:
            self._backpressure_count += 1
            logger.warning(
                f"⚠️ 队列使用率 {usage:.1%} > {self.threshold:.1%}，"
                f"触发背压控制 #{self._backpressure_count}（暂停100ms）"
            )
            await asyncio.sleep(0.1)  # 短暂暂停，给队列时间处理
        
        await self.queue.put(item)
        return True
    
    def get_usage(self) -> float:
        """获取当前队列使用率"""
        if self.maxsize == float('inf'):
            return 0.0
        return self.queue.qsize() / self.maxsize
    
    def get_backpressure_count(self) -> int:
        """获取背压触发次数"""
        return self._backpressure_count


class AudioChunkNormalizer:
    """音频块标准化器
    
    将不同大小的音频块标准化为统一大小，提高播放流畅度
    """
    
    def __init__(self, target_duration_ms: int = 500, sample_rate: int = 24000):
        """
        初始化音频块标准化器
        
        Args:
            target_duration_ms: 目标音频块时长（毫秒）
            sample_rate: 采样率（Hz）
        """
        self.target_duration_ms = target_duration_ms
        self.sample_rate = sample_rate
        self.target_samples = int(target_duration_ms * sample_rate / 1000)
        self.buffer = b""
    
    def add_chunk(self, audio_data: bytes) -> List[bytes]:
        """
        添加音频块，返回标准化的块列表
        
        Args:
            audio_data: 音频数据（PCM int16格式）
        
        Returns:
            标准化后的音频块列表
        """
        self.buffer += audio_data
        chunks = []
        
        # 16bit = 2 bytes per sample
        target_bytes = self.target_samples * 2
        
        while len(self.buffer) >= target_bytes:
            chunk = self.buffer[:target_bytes]
            chunks.append(chunk)
            self.buffer = self.buffer[target_bytes:]
        
        return chunks
    
    def flush(self) -> Optional[bytes]:
        """
        返回剩余的音频数据
        
        Returns:
            剩余的音频数据，如果没有则返回None
        """
        if self.buffer:
            result = self.buffer
            self.buffer = b""
            return result
        return None
    
    def reset(self):
        """重置缓冲区"""
        self.buffer = b""
