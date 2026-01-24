"""
TTS 相关数据模型
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any, List
import asyncio


class TTSFormat(str, Enum):
    """音频格式枚举"""
    PCM = "pcm"  # PCM格式（单声道 24000Hz）
    WAV = "wav"
    MP3 = "mp3"


@dataclass
class AudioChunk:
    """音频块数据类"""
    chunk_id: str  # 音频块唯一ID
    text: str  # 对应的文本内容
    audio_data: bytes  # 音频二进制数据
    format: str  # 音频格式
    is_final: bool  # 是否为最后一个音频块
    timestamp: int  # 生成时间戳（毫秒）
    metadata: Optional[Dict[str, Any]] = None  # 额外元数据


class SentenceBuffer:
    """智能句子缓冲区
    
    功能：
    1. 检测句子边界（句号、问号、感叹号等）
    2. 处理中英文混合文本
    3. 支持最小/最大长度限制
    """
    
    # 句子结束标点（中英文）
    SENTENCE_ENDINGS = {
        '。', '.', '！', '!', '？', '?', 
        '；', ';', '\n', '\r\n'
    }
    
    # 中文标点
    CHINESE_PUNCTUATION = {
        '。', '，', '！', '？', '；', '：', 
        '、', '…', '—', '——', '（', '）', 
        '【', '】', '《', '》', '"', '"', 
        ''', ''', '「', '」'
    }
    
    def __init__(
        self,
        min_length: int = 15,  # 最小句子长度（字符数）
        max_length: int = 200,  # 最大句子长度（超过则强制分割）
        max_wait_time: float = 1.0  # 最大等待时间（秒），超时则输出当前缓冲区
    ):
        self.min_length = min_length
        self.max_length = max_length
        self.max_wait_time = max_wait_time
        self.buffer = ""
        self.last_update_time = None
    
    def add_text(self, text: str) -> List[str]:
        """
        添加文本到缓冲区，检测句子边界
        
        Returns:
            完整句子的列表（可能为空）
        """
        self.buffer += text
        self.last_update_time = asyncio.get_event_loop().time()
        
        sentences = []
        
        # 如果超过最大长度，强制分割
        if len(self.buffer) >= self.max_length:
            # 尝试在标点处分割
            split_pos = self._find_safe_split_position(self.buffer, self.max_length)
            if split_pos > 0:
                sentence = self.buffer[:split_pos + 1].strip()
                if sentence:
                    sentences.append(sentence)
                self.buffer = self.buffer[split_pos + 1:].strip()
            else:
                # 无法找到安全分割点，直接按最大长度分割
                sentence = self.buffer[:self.max_length].strip()
                if sentence:
                    sentences.append(sentence)
                self.buffer = self.buffer[self.max_length:].strip()
        
        # 检测句子结束标点
        while True:
            found_end = False
            earliest_end_pos = len(self.buffer)
            
            for ending in self.SENTENCE_ENDINGS:
                pos = self.buffer.find(ending)
                if pos != -1 and pos < earliest_end_pos:
                    earliest_end_pos = pos
                    found_end = True
            
            if not found_end:
                break
            
            # 提取完整句子（包含结束标点）
            sentence = self.buffer[:earliest_end_pos + 1].strip()
            
            # 检查最小长度要求
            if len(sentence) >= self.min_length:
                sentences.append(sentence)
                self.buffer = self.buffer[earliest_end_pos + 1:].strip()
            else:
                # 句子太短，继续累积
                break
        
        return sentences
    
    def _find_safe_split_position(self, text: str, max_len: int) -> int:
        """在最大长度附近找到安全的分割位置（标点处）"""
        if len(text) <= max_len:
            return -1
        
        # 在最大长度的前后50个字符内查找标点
        search_start = max(0, max_len - 50)
        search_end = min(len(text), max_len + 50)
        
        # 优先查找句子结束标点
        for ending in self.SENTENCE_ENDINGS:
            pos = text.rfind(ending, search_start, search_end)
            if pos != -1:
                return pos
        
        # 如果没有找到句子结束标点，查找其他标点
        for punct in self.CHINESE_PUNCTUATION:
            pos = text.rfind(punct, search_start, search_end)
            if pos != -1:
                return pos
        
        # 如果没有找到中文标点，查找其他标点
        for punct in [',', '，', '、']:
            pos = text.rfind(punct, search_start, search_end)
            if pos != -1:
                return pos
        
        return -1
    
    def flush(self) -> Optional[str]:
        """
        清空缓冲区，返回剩余内容
        
        Returns:
            剩余缓冲区内容，如果为空则返回 None
        """
        if self.buffer.strip():
            result = self.buffer.strip()
            self.buffer = ""
            return result
        return None
    
    def get_pending_text(self) -> str:
        """获取当前缓冲区内容（不清空）"""
        return self.buffer
    
    def should_flush(self) -> bool:
        """检查是否应该清空缓冲区（超时）"""
        if self.last_update_time is None:
            return False
        
        elapsed = asyncio.get_event_loop().time() - self.last_update_time
        return elapsed >= self.max_wait_time and len(self.buffer) > 0

