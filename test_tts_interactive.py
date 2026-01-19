#!/usr/bin/env python3
"""
模拟实际服务交互的TTS测试脚本
- 手动初始化TTS服务
- 模拟文本块输入（流式）
- 接收TTS返回的音频块
- 合并所有音频块为完整音频文件
"""
import asyncio
import logging
import sys
import time
import wave
from pathlib import Path
from typing import AsyncGenerator, List
import uuid

# 加载环境变量（必须在其他导入之前）
from dotenv import load_dotenv
load_dotenv()

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== 配置 ====================

# 测试文本（可以分段输入模拟流式）
TEST_TEXT = "近日伊朗局势持续紧张，革命卫队高官宣布该国已进入最高战备状态，导弹储备量自2025年以来持续增加。"

# 音频参数
AUDIO_SAMPLE_RATE = 24000  # 采样率（Hz）
AUDIO_CHANNELS = 1  # 单声道
AUDIO_SAMPLE_WIDTH = 2  # 16位 = 2字节

# ==================== 文本流生成器 ====================

async def create_text_stream(text: str, chunk_size: int = 1, delay: float = 0.1) -> AsyncGenerator[str, None]:
    """
    创建模拟的文本流生成器
    
    Args:
        text: 完整文本
        chunk_size: 每次yield的字符数（模拟token级别输入）
        delay: 每次yield之间的延迟（秒），模拟实际服务中的流式输入
    
    Yields:
        str: 文本块
    """
    logger.info(f"开始生成文本流: 总长度={len(text)}, chunk_size={chunk_size}, delay={delay}s")
    
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        yield chunk
        
        # 模拟实际服务中的延迟
        if delay > 0:
            await asyncio.sleep(delay)
    
    logger.info("文本流生成完成")


async def create_text_stream_by_sentences(text: str, delay: float = 0.2) -> AsyncGenerator[str, None]:
    """
    按句子创建文本流（更真实的模拟）
    
    Args:
        text: 完整文本
        delay: 每个句子之间的延迟（秒）
    
    Yields:
        str: 句子文本块
    """
    logger.info(f"开始按句子生成文本流: 总长度={len(text)}")
    
    # 简单的句子分割（按标点符号）
    sentences = []
    current_sentence = ""
    
    for char in text:
        current_sentence += char
        if char in ['。', '.', '！', '!', '？', '?', '；', ';', '\n']:
            if current_sentence.strip():
                sentences.append(current_sentence.strip())
            current_sentence = ""
    
    # 添加最后一个句子（如果有）
    if current_sentence.strip():
        sentences.append(current_sentence.strip())
    
    # 如果没有句子，使用整个文本
    if not sentences:
        sentences = [text]
    
    logger.info(f"分割为 {len(sentences)} 个句子")
    
    for idx, sentence in enumerate(sentences):
        logger.info(f"发送句子 {idx + 1}/{len(sentences)}: {sentence[:50]}...")
        yield sentence
        
        # 模拟实际服务中的延迟
        if delay > 0 and idx < len(sentences) - 1:
            await asyncio.sleep(delay)
    
    logger.info("文本流生成完成")


# ==================== TTS服务初始化 ====================

def init_tts_service():
    """手动初始化TTS服务"""
    logger.info("=" * 80)
    logger.info("初始化TTS服务")
    logger.info("=" * 80)
    
    try:
        from tts_utils import get_tts_service
        from llm_utils.config import config
        
        # 获取配置
        model_dir = config.get("tts.local_model_dir")
        model_type = config.get("tts.local_model_type", "auto")
        spk_id = config.get("tts.default_spk_id", "girl_zh")
        enabled = config.get("tts.enabled", True)
        
        logger.info(f"配置信息:")
        logger.info(f"  - model_dir: {model_dir}")
        logger.info(f"  - model_type: {model_type}")
        logger.info(f"  - spk_id: {spk_id}")
        logger.info(f"  - enabled: {enabled}")
        logger.info("")
        
        # 初始化TTS服务
        tts_service = get_tts_service()
        
        # 检查服务状态
        if not tts_service.enabled:
            logger.warning("⚠️  TTS服务未启用")
            return None
        
        # 尝试获取说话人列表（验证服务可用性）
        try:
            speakers = tts_service.list_speakers()
            logger.info(f"✅ TTS服务初始化成功")
            logger.info(f"   可用说话人: {len(speakers)} 个")
            if speakers:
                logger.info(f"   说话人列表: {', '.join(speakers[:5])}{'...' if len(speakers) > 5 else ''}")
        except Exception as e:
            logger.warning(f"⚠️  无法获取说话人列表: {e}")
            logger.info("   但服务可能仍然可用")
        
        return tts_service
        
    except Exception as e:
        logger.error(f"❌ TTS服务初始化失败: {e}", exc_info=True)
        return None


# ==================== 主测试函数 ====================

async def test_tts_interactive(mode: str = "token"):
    """
    测试TTS交互
    
    Args:
        mode: 输入模式
            - "token": 按字符/词输入（模拟token级别）
            - "sentence": 按句子输入（更真实的模拟）
    """
    logger.info("=" * 80)
    logger.info("TTS交互测试")
    logger.info("=" * 80)
    logger.info(f"测试文本: {TEST_TEXT}")
    logger.info(f"输入模式: {mode}")
    logger.info("")
    
    # 初始化TTS服务
    tts_service = init_tts_service()
    if tts_service is None:
        logger.error("无法初始化TTS服务，测试终止")
        return
    
    logger.info("")
    
    # 创建输出目录
    output_dir = Path("test_output")
    output_dir.mkdir(exist_ok=True)
    
    # 生成请求ID
    request_id = f"test_{uuid.uuid4().hex[:8]}"
    logger.info(f"请求ID: {request_id}")
    logger.info("")
    
    # 创建文本流
    if mode == "token":
        # 按字符输入（模拟token级别）
        text_stream = create_text_stream(TEST_TEXT, chunk_size=1, delay=0.05)
    else:
        # 按句子输入
        text_stream = create_text_stream_by_sentences(TEST_TEXT, delay=0.2)
    
    # 收集所有音频块
    audio_chunks: List[bytes] = []
    chunk_info = []
    
    start_time = time.time()
    
    logger.info("=" * 80)
    logger.info("开始TTS合成")
    logger.info("=" * 80)
    
    try:
        # 调用TTS服务的流式合成
        chunk_count = 0
        async for audio_chunk in tts_service.synthesize_stream(
            text_stream=text_stream,
            language="zh",
            request_id=request_id,
            format="pcm",
            sample_rate=AUDIO_SAMPLE_RATE,
            voice=None
        ):
            chunk_count += 1
            audio_data = audio_chunk.audio_data
            is_final = audio_chunk.is_final
            
            # 保存音频块信息
            audio_chunks.append(audio_data)
            chunk_info.append({
                "chunk_id": audio_chunk.chunk_id,
                "text": audio_chunk.text,
                "size": len(audio_data),
                "is_final": is_final,
                "timestamp": audio_chunk.timestamp
            })
            
            logger.info(
                f"收到音频块 #{chunk_count}: "
                f"ID={audio_chunk.chunk_id}, "
                f"大小={len(audio_data)} 字节, "
                f"文本='{audio_chunk.text[:30]}...', "
                f"is_final={is_final}"
            )
        
        duration = time.time() - start_time
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("TTS合成完成")
        logger.info("=" * 80)
        logger.info(f"总耗时: {duration:.2f} 秒")
        logger.info(f"音频块数量: {len(audio_chunks)}")
        logger.info(f"总音频大小: {sum(len(chunk) for chunk in audio_chunks)} 字节")
        logger.info("")
        
        # 合并音频
        if audio_chunks:
            logger.info("=" * 80)
            logger.info("合并音频文件")
            logger.info("=" * 80)
            
            # 生成输出文件名
            timestamp = int(time.time())
            safe_text = "".join(c for c in TEST_TEXT[:20] if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_text = safe_text.replace(' ', '_') if safe_text else "tts_interactive"
            output_filename = f"{safe_text}_{mode}_{timestamp}_merged.wav"
            output_path = output_dir / output_filename
            
            try:
                # 合并所有音频块
                total_bytes = sum(len(chunk) for chunk in audio_chunks)
                
                with wave.open(str(output_path), "wb") as wav_file:
                    wav_file.setnchannels(AUDIO_CHANNELS)  # 单声道
                    wav_file.setsampwidth(AUDIO_SAMPLE_WIDTH)  # 16位 = 2字节
                    wav_file.setframerate(AUDIO_SAMPLE_RATE)  # 采样率
                    
                    for chunk in audio_chunks:
                        wav_file.writeframes(chunk)
                
                # 计算音频时长
                total_samples = total_bytes // AUDIO_SAMPLE_WIDTH
                duration_seconds = total_samples / AUDIO_SAMPLE_RATE
                
                logger.info(f"✅ 音频合并成功!")
                logger.info(f"   输出文件: {output_path}")
                logger.info(f"   文件大小: {total_bytes} 字节 ({total_bytes / 1024:.2f} KB)")
                logger.info(f"   音频时长: {duration_seconds:.2f} 秒")
                logger.info(f"   采样率: {AUDIO_SAMPLE_RATE} Hz")
                logger.info(f"   声道数: {AUDIO_CHANNELS}")
                logger.info(f"   位深: {AUDIO_SAMPLE_WIDTH * 8} bit")
                logger.info("")
                logger.info(f"💡 可以使用以下命令播放:")
                logger.info(f"   ffplay {output_path}")
                logger.info(f"   或")
                logger.info(f"   aplay {output_path}")
                logger.info("")
                
            except Exception as e:
                logger.error(f"❌ 合并音频失败: {e}", exc_info=True)
        else:
            logger.warning("⚠️  未收到任何音频块")
        
        # 打印详细信息
        logger.info("")
        logger.info("=" * 80)
        logger.info("音频块详细信息")
        logger.info("=" * 80)
        for idx, info in enumerate(chunk_info, 1):
            logger.info(
                f"块 #{idx}: ID={info['chunk_id']}, "
                f"大小={info['size']} 字节, "
                f"文本='{info['text'][:50]}...', "
                f"is_final={info['is_final']}"
            )
        
    except Exception as e:
        logger.error(f"❌ TTS合成失败: {e}", exc_info=True)


# ==================== 主函数 ====================

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="TTS交互测试脚本")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["token", "sentence"],
        default="token",
        help="输入模式: token(按字符) 或 sentence(按句子)"
    )
    
    args = parser.parse_args()
    
    await test_tts_interactive(mode=args.mode)


if __name__ == "__main__":
    asyncio.run(main())

