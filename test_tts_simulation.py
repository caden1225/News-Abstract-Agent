#!/usr/bin/env python3
"""
TTS服务执行流程模拟测试脚本

功能：
1. 使用与orchestrator相同的文本分割逻辑
2. 模拟TTS调用流程
3. 保存每段生成的音频
4. 合并并保存最终音频
"""
import os
import sys
import asyncio
import logging
import time
from pathlib import Path
from typing import List, Tuple
import wave
import numpy as np

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from llm_utils.config import config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 测试文本（可以修改为实际使用的文本）
TEST_TEXT = """
今天是一个阳光明媚的日子。我们来看看最新的新闻动态。
首先，科技领域传来好消息。人工智能技术取得了重大突破。
这项技术将改变我们的生活方式。让我们期待更多创新。
"""


class TextSplitter:
    """文本分割器 - 模拟orchestrator中的文本分割逻辑"""
    
    def __init__(self):
        # 从配置读取参数
        self.tts_min_length = int(config.get("tts.buffer.min_length", 15))
        self.tts_max_length = int(config.get("tts.buffer.max_length", 200))
        self.max_latency = float(config.get("tts.buffer.max_wait_time", 1.0))
        
        # 句子结束标点集合（与orchestrator保持一致）
        self.SENTENCE_ENDINGS = {'。', '.', '！', '!', '？', '?', '；', ';', '\n', '\r\n'}
        # 用于安全位置分割的标点集合
        self.SAFE_SPLIT_PUNCTUATION = {'。', '，', '！', '？', '；', '：', '、', '…', '—', '——', ',', ';', ':'}
        
        logger.info(f"文本分割器初始化:")
        logger.info(f"  最小长度: {self.tts_min_length}")
        logger.info(f"  最大长度: {self.tts_max_length}")
        logger.info(f"  最大延迟: {self.max_latency}秒")
    
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
        
        # 其次查找其他安全标点
        for punct in self.SAFE_SPLIT_PUNCTUATION:
            pos = text.rfind(punct, search_start, search_end)
            if pos != -1:
                return pos
        
        return -1
    
    def _find_sentence_boundary(self, text: str) -> int:
        """向后查找最早的句子结束标点位置"""
        earliest_pos = len(text)
        found = False
        
        for ending in self.SENTENCE_ENDINGS:
            pos = text.find(ending)
            if pos != -1 and pos < earliest_pos:
                earliest_pos = pos
                found = True
        
        return earliest_pos if found else -1
    
    def _extract_text_chunk(self, buffer: str, force: bool = False) -> Tuple[str, str]:
        """
        从缓冲区提取文本chunk（智能分割）
        
        Args:
            buffer: 待分割的文本缓冲区
            force: 是否强制分割（即使未达到最小长度）
        
        Returns:
            (chunk, remaining_buffer) - 提取的chunk和剩余缓冲区
        """
        if not buffer:
            return "", ""
        
        # 超过最大长度，尝试在安全位置分割
        if len(buffer) >= self.tts_max_length:
            split_pos = self._find_safe_split_position(buffer, self.tts_max_length)
            if split_pos > 0:
                chunk = buffer[:split_pos + 1].strip()
                remaining = buffer[split_pos + 1:].strip()
                return chunk, remaining
            # 无法找到安全位置，强制分割
            chunk = buffer[:self.tts_max_length].strip()
            remaining = buffer[self.tts_max_length:].strip()
            return chunk, remaining
        
        # 查找句子边界
        if len(buffer) >= self.tts_min_length or force:
            boundary_pos = self._find_sentence_boundary(buffer)
            if boundary_pos != -1:
                sentence = buffer[:boundary_pos + 1].strip()
                if len(sentence) >= self.tts_min_length or force:
                    remaining = buffer[boundary_pos + 1:].strip()
                    return sentence, remaining
            
            # 强制模式：返回整个buffer（即使没有找到句子边界）
            if force:
                return buffer.strip(), ""
        
        # 未达到分割条件
        return "", buffer
    
    def _should_flush_text(self, buffer: str, last_ts: float, now: float) -> bool:
        """判断content文本是否应该刷新到TTS"""
        if not buffer:
            return False
        
        # 超过最大长度
        if len(buffer) >= self.tts_max_length:
            return True
        
        # 达到最小长度且找到句子边界
        if len(buffer) >= self.tts_min_length:
            boundary_pos = self._find_sentence_boundary(buffer)
            if boundary_pos != -1:
                return True
        
        # 超时且达到最小长度
        if (now - last_ts) >= self.max_latency and len(buffer) >= self.tts_min_length:
            return True
        
        return False
    
    def split_text(self, text: str) -> List[str]:
        """
        将文本分割成多个chunks（模拟orchestrator的文本生成流程）
        
        Args:
            text: 完整文本
        
        Returns:
            文本chunk列表
        """
        chunks = []
        buffer = text.strip()
        last_ts = time.time()
        
        logger.info(f"开始分割文本，总长度: {len(buffer)} 字符")
        
        while buffer:
            now = time.time()
            
            # 判断是否应该刷新
            if not self._should_flush_text(buffer, last_ts, now):
                # 如果还有剩余文本但未达到刷新条件，强制刷新
                if buffer:
                    chunk, remaining = self._extract_text_chunk(buffer, force=True)
                    if chunk:
                        chunks.append(chunk)
                        logger.info(f"  [强制分割] chunk {len(chunks)}: {len(chunk)} 字符 - {chunk[:50]}...")
                        buffer = remaining
                        last_ts = now
                break
            
            # 提取chunk
            chunk, remaining = self._extract_text_chunk(buffer, force=False)
            if chunk:
                chunks.append(chunk)
                logger.info(f"  [智能分割] chunk {len(chunks)}: {len(chunk)} 字符 - {chunk[:50]}...")
                buffer = remaining
                last_ts = now
            else:
                # 无法提取，强制提取
                chunk, remaining = self._extract_text_chunk(buffer, force=True)
                if chunk:
                    chunks.append(chunk)
                    logger.info(f"  [强制分割] chunk {len(chunks)}: {len(chunk)} 字符 - {chunk[:50]}...")
                    buffer = remaining
                    last_ts = now
                else:
                    break
        
        logger.info(f"文本分割完成，共 {len(chunks)} 个chunks")
        return chunks


def save_audio_bytes(audio_bytes: bytes, output_path: Path, sample_rate: int = 22050):
    """
    保存PCM音频字节为WAV文件
    
    Args:
        audio_bytes: PCM格式的音频字节（16-bit, mono）
        output_path: 输出文件路径
        sample_rate: 采样率（默认22050Hz）
    """
    # 将字节转换为numpy数组
    audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
    
    # 保存为WAV文件
    with wave.open(str(output_path), 'wb') as wav_file:
        wav_file.setnchannels(1)  # 单声道
        wav_file.setsampwidth(2)  # 16-bit = 2 bytes
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_array.tobytes())
    
    duration = len(audio_array) / sample_rate
    logger.info(f"  保存音频: {output_path.name} ({len(audio_bytes)} 字节, {duration:.2f}秒)")


def merge_audio_chunks(audio_chunks: List[bytes]) -> bytes:
    """
    合并多个音频chunk
    
    Args:
        audio_chunks: 音频字节列表
    
    Returns:
        合并后的音频字节
    """
    return b"".join(audio_chunks)


async def simulate_tts_process(text: str, output_dir: Path, request_id: str = None):
    """
    模拟TTS执行流程
    
    Args:
        text: 待合成的文本
        output_dir: 输出目录
        request_id: 请求ID，用于session管理（如果为None则自动生成）
    """
    logger.info("=" * 80)
    logger.info("开始模拟TTS执行流程")
    logger.info("=" * 80)
    
    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"输出目录: {output_dir}")
    
    # 生成或使用提供的 request_id
    if request_id is None:
        import uuid
        request_id = f"test_{uuid.uuid4().hex[:8]}"
    logger.info(f"Request ID: {request_id} (用于session管理，保证音色一致性)")
    
    # 1. 初始化文本分割器
    logger.info("\n[步骤1] 初始化文本分割器")
    splitter = TextSplitter()
    
    # 2. 分割文本
    logger.info("\n[步骤2] 分割文本")
    text_chunks = splitter.split_text(text)
    
    if not text_chunks:
        logger.error("文本分割失败，没有生成任何chunk")
        return
    
    # 3. 初始化TTS服务
    logger.info("\n[步骤3] 初始化TTS服务")
    try:
        from tts_utils import get_tts_service, initialize_tts
        
        if not await initialize_tts():
            logger.error("❌ TTS服务初始化失败")
            return
        
        tts_service = get_tts_service()
        if not tts_service:
            logger.error("❌ 无法获取TTS服务实例")
            return
        
        logger.info(f"✅ TTS服务初始化成功")
        logger.info(f"   服务类型: {type(tts_service).__name__}")
        logger.info(f"   采样率: {tts_service.sample_rate} Hz")
        logger.info(f"   说话人: {tts_service.spk_id}")
        
    except Exception as e:
        logger.error(f"❌ TTS服务初始化异常: {e}", exc_info=True)
        return
    
    # 4. 对每个chunk进行TTS合成
    logger.info("\n[步骤4] 开始TTS合成")
    logger.info(f"使用 session 管理 (request_id={request_id})，确保音色一致性")
    audio_chunks = []
    total_start_time = time.time()
    
    for idx, chunk in enumerate(text_chunks, 1):
        logger.info(f"\n处理 chunk {idx}/{len(text_chunks)}:")
        logger.info(f"  文本: {chunk}")
        logger.info(f"  长度: {len(chunk)} 字符")
        
        # 判断是否为最后一个chunk
        is_last_chunk = (idx == len(text_chunks))
        
        try:
            chunk_start_time = time.time()
            
            # 调用TTS合成（与orchestrator中的调用方式完全一致）
            # 传递 request_id 和 is_last_chunk，用于 session 管理，保证音色一致性
            audio_bytes = await tts_service.synthesize(
                text=chunk,
                spk_id=None,
                request_id=request_id,
                is_last_chunk=is_last_chunk
            )
            
            chunk_duration = time.time() - chunk_start_time
            audio_duration = len(audio_bytes) / 2 / tts_service.sample_rate
            
            logger.info(f"  ✅ 合成完成:")
            logger.info(f"     音频大小: {len(audio_bytes)} 字节")
            logger.info(f"     音频时长: {audio_duration:.2f} 秒")
            logger.info(f"     合成耗时: {chunk_duration:.2f} 秒")
            logger.info(f"     RTF: {chunk_duration / audio_duration:.2f}")
            logger.info(f"     是否最后chunk: {is_last_chunk}")
            
            # 保存单个chunk的音频
            chunk_output_path = output_dir / f"chunk_{idx:03d}.wav"
            save_audio_bytes(audio_bytes, chunk_output_path, tts_service.sample_rate)
            
            audio_chunks.append(audio_bytes)
            
        except Exception as e:
            logger.error(f"  ❌ chunk {idx} 合成失败: {e}", exc_info=True)
            continue
    
    total_duration = time.time() - total_start_time
    logger.info(f"\n所有chunk合成完成，总耗时: {total_duration:.2f} 秒")
    
    # 5. 合并所有音频
    logger.info("\n[步骤5] 合并音频")
    if audio_chunks:
        merged_audio = merge_audio_chunks(audio_chunks)
        merged_duration = len(merged_audio) / 2 / tts_service.sample_rate
        
        logger.info(f"合并完成:")
        logger.info(f"  总音频大小: {len(merged_audio)} 字节")
        logger.info(f"  总音频时长: {merged_duration:.2f} 秒")
        logger.info(f"  chunk数量: {len(audio_chunks)}")
        
        # 保存合并后的音频
        merged_output_path = output_dir / "merged_audio.wav"
        save_audio_bytes(merged_audio, merged_output_path, tts_service.sample_rate)
        logger.info(f"✅ 合并音频已保存: {merged_output_path}")
    else:
        logger.error("没有可合并的音频chunk")
    
    # 6. 生成摘要报告
    logger.info("\n[步骤6] 生成摘要报告")
    report_path = output_dir / "report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("TTS执行流程模拟测试报告\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Request ID: {request_id}\n")
        f.write(f"原始文本长度: {len(text)} 字符\n")
        f.write(f"分割chunk数量: {len(text_chunks)}\n")
        f.write(f"成功合成chunk数量: {len(audio_chunks)}\n")
        f.write(f"总合成耗时: {total_duration:.2f} 秒\n")
        if audio_chunks:
            total_audio_duration = sum(len(chunk) / 2 / tts_service.sample_rate for chunk in audio_chunks)
            f.write(f"总音频时长: {total_audio_duration:.2f} 秒\n")
            f.write(f"平均RTF: {total_duration / total_audio_duration:.2f}\n")
        f.write(f"\nSession管理: 已启用 (request_id={request_id})\n")
        f.write("  所有chunk使用相同的UUID和缓存，确保音色一致性\n")
        f.write("\n文本Chunks:\n")
        for idx, chunk in enumerate(text_chunks, 1):
            f.write(f"  {idx}. [{len(chunk)} 字符] {chunk}\n")
        f.write("\n输出文件:\n")
        for idx in range(1, len(audio_chunks) + 1):
            f.write(f"  - chunk_{idx:03d}.wav\n")
        f.write(f"  - merged_audio.wav\n")
    
    logger.info(f"✅ 摘要报告已保存: {report_path}")
    logger.info("\n" + "=" * 80)
    logger.info("TTS执行流程模拟完成")
    logger.info("=" * 80)


async def main():
    """主函数"""
    # 解析命令行参数
    import argparse
    parser = argparse.ArgumentParser(description="TTS执行流程模拟测试")
    parser.add_argument(
        "--text",
        type=str,
        default=TEST_TEXT,
        help="待合成的文本（默认使用内置测试文本）"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="tts_test_output",
        help="输出目录（默认: tts_test_output）"
    )
    parser.add_argument(
        "--request-id",
        type=str,
        default=None,
        help="请求ID，用于session管理（默认自动生成）"
    )
    
    args = parser.parse_args()
    
    # 创建输出目录
    output_dir = Path(args.output_dir)
    
    # 运行模拟
    await simulate_tts_process(args.text, output_dir, request_id=args.request_id)


if __name__ == "__main__":
    asyncio.run(main())

