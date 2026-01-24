#!/usr/bin/env python3
"""
TTS文本片段测试脚本
使用提供的文本片段测试TTS服务的流式合成功能
"""
import asyncio
import os
import sys
import logging
import wave
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# 用户提供的文本片段
TEXT_CHUNKS = [
    # "好的，我现在需要处理用户的请求，",非流式合成统计
    # "生成适合驾驶场景的新闻播报稿。",
    # "首先，我要仔细阅读用户提供的任务说明和新闻素材，",
    # "确保理解所有要求。",
    # "用户强调必须使用中文，信息",
    # "要完整，每条新闻1-2句话，总字数",
    # "控制在100字内。同时，要",
    # "口语化，自然开场，不用固定开场白，结尾要有关心的句子"
  "外交部今天通报，芬兰总理奥尔波",
  "将于1月25日至28日对中国进行正式访问，这是中芬两国重要的外交互动。",
  "这个访问安排正值冬季，不知道两国会不会讨论能源合作这些大家关心的话题。\n\n另外也有个挺特别",
  "的新闻，朝鲜副总理杨胜虎在参观机械厂时被最高领导人金正恩当场罢免",
  "，原因是现场提出\"山羊能拉牛车吗\"的质疑。",
  "这个处理方式确实比较直接，看来朝鲜高层管理还是挺强调务实的。\n\n最后要说的是国内消息",
  "，32岁程序员高广辉在家突发猝死，当时还有4项工作任务待完成。",
  "人社局工作人员表示是否属于工伤还在调查。",
  "这个情况确实让人揪心，也提醒大家要注意工作强度和身体健康。\n\n好了，今天的新闻就为您",
  "播报到这里，祝您驾驶平安，注意休息。"
]


async def text_chunk_generator():
    """生成文本流（模拟流式输入）"""
    logger.info("开始生成文本流...")
    for i, text in enumerate(TEXT_CHUNKS, 1):
        logger.info(f"[文本片段 {i}/{len(TEXT_CHUNKS)}] {text}")
        yield text
        # 模拟文本流式到达的延迟
        await asyncio.sleep(0.2)
    logger.info("文本流生成完成")


async def test_tts_streaming():
    """测试TTS流式合成"""
    logger.info("=" * 80)
    logger.info("TTS文本片段流式合成测试")
    logger.info("=" * 80)
    
    try:
        # 导入TTS服务
        from tts_utils import get_tts_service, initialize_tts
        
        # 初始化TTS服务
        logger.info("\n📦 初始化TTS服务...")
        if not await initialize_tts():
            logger.error("❌ TTS服务初始化失败")
            return False
        
        tts_service = get_tts_service()
        if not tts_service:
            logger.error("❌ 无法获取TTS服务实例")
            return False
        
        logger.info("✅ TTS服务初始化成功")
        logger.info(f"   服务类型: {type(tts_service).__name__}")
        logger.info(f"   采样率: {tts_service.sample_rate} Hz")
        logger.info(f"   说话人: {tts_service.spk_id}")
        
        # 列出可用说话人
        try:
            speakers = tts_service.list_speakers()
            logger.info(f"   可用说话人: {len(speakers)} 个")
            if speakers:
                logger.info(f"   示例: {speakers[:3]}")
        except Exception as e:
            logger.warning(f"   ⚠️  获取说话人列表失败: {e}")
        
        # 测试流式合成
        logger.info("\n🎤 开始流式语音合成...")
        logger.info(f"   文本片段数: {len(TEXT_CHUNKS)}")
        logger.info(f"   总文本长度: {sum(len(chunk) for chunk in TEXT_CHUNKS)} 字符")
        
        # 收集所有音频块
        audio_chunks = []
        chunk_count = 0
        total_bytes = 0
        chunk_sizes = []  # 记录每个chunk的大小
        chunk_timestamps = []  # 记录每个chunk的接收时间
        start_time = time.time()
        
        try:
            async for audio_chunk in tts_service.synthesize_streaming(
                text_chunk_generator(),
                spk_id=None  # 使用默认说话人
            ):
                chunk_count += 1
                chunk_size = len(audio_chunk)
                total_bytes += chunk_size
                chunk_sizes.append(chunk_size)
                chunk_timestamps.append(time.time())
                audio_chunks.append(audio_chunk)
                
                # 计算音频时长（假设16-bit PCM，单声道）
                duration = chunk_size / 2 / tts_service.sample_rate
                # 计算从开始到当前chunk的累计时间
                elapsed = chunk_timestamps[-1] - start_time
                logger.info(f"   [音频块 {chunk_count}] {chunk_size:>8} bytes (~{duration:.2f}s) [累计: {elapsed:.2f}s]")
        
        except Exception as e:
            logger.error(f"❌ 流式合成过程中出错: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        synthesis_time = time.time() - start_time
        
        # 详细的统计信息
        logger.info(f"\n{'='*80}")
        logger.info("📊 音频Chunk统计信息")
        logger.info(f"{'='*80}")
        logger.info(f"✅ 流式合成完成!")
        logger.info(f"")
        logger.info(f"📈 总体统计:")
        logger.info(f"   接收的音频chunk总数: {chunk_count} 个")
        logger.info(f"   总字节数: {total_bytes:,} bytes ({total_bytes/1024:.2f} KB)")
        logger.info(f"   合成总耗时: {synthesis_time:.2f} 秒")
        
        if chunk_sizes:
            avg_chunk_size = sum(chunk_sizes) / len(chunk_sizes)
            min_chunk_size = min(chunk_sizes)
            max_chunk_size = max(chunk_sizes)
            
            logger.info(f"")
            logger.info(f"📏 Chunk大小统计:")
            logger.info(f"   平均大小: {avg_chunk_size:.0f} bytes ({avg_chunk_size/1024:.2f} KB)")
            logger.info(f"   最小大小: {min_chunk_size:,} bytes ({min_chunk_size/1024:.2f} KB)")
            logger.info(f"   最大大小: {max_chunk_size:,} bytes ({max_chunk_size/1024:.2f} KB)")
            
            # 计算每个chunk的音频时长
            chunk_durations = [size / 2 / tts_service.sample_rate for size in chunk_sizes]
            total_duration = sum(chunk_durations)
            avg_duration = total_duration / len(chunk_durations)
            
            logger.info(f"")
            logger.info(f"⏱️  音频时长统计:")
            logger.info(f"   总音频时长: {total_duration:.2f} 秒")
            logger.info(f"   平均chunk时长: {avg_duration:.2f} 秒")
            logger.info(f"   最小chunk时长: {min(chunk_durations):.2f} 秒")
            logger.info(f"   最大chunk时长: {max(chunk_durations):.2f} 秒")
            
            # 计算接收速率
            if synthesis_time > 0:
                chunks_per_second = chunk_count / synthesis_time
                bytes_per_second = total_bytes / synthesis_time
                logger.info(f"")
                logger.info(f"⚡ 接收速率:")
                logger.info(f"   Chunk接收速率: {chunks_per_second:.2f} chunks/秒")
                logger.info(f"   数据接收速率: {bytes_per_second/1024:.2f} KB/秒")
            
            # 显示前几个和后几个chunk的详细信息
            logger.info(f"")
            logger.info(f"📋 Chunk详情 (前5个):")
            for i in range(min(5, len(chunk_sizes))):
                duration = chunk_sizes[i] / 2 / tts_service.sample_rate
                logger.info(f"   Chunk {i+1}: {chunk_sizes[i]:>8} bytes (~{duration:.2f}s)")
            
            if len(chunk_sizes) > 5:
                logger.info(f"   ... (省略 {len(chunk_sizes)-5} 个chunk)")
                logger.info(f"📋 Chunk详情 (后5个):")
                for i in range(max(0, len(chunk_sizes)-5), len(chunk_sizes)):
                    duration = chunk_sizes[i] / 2 / tts_service.sample_rate
                    logger.info(f"   Chunk {i+1}: {chunk_sizes[i]:>8} bytes (~{duration:.2f}s)")
        
        logger.info(f"{'='*80}")
        
        if not audio_chunks:
            logger.warning("⚠️  没有生成任何音频数据")
            return False
        
        # 保存音频文件
        logger.info("\n💾 保存音频文件...")
        
        # 创建输出目录
        output_dir = Path(project_root) / "test_output"
        output_dir.mkdir(exist_ok=True)
        
        # 生成输出文件名（带时间戳）
        timestamp = int(time.time())
        output_filename = f"tts_test_{timestamp}.wav"
        output_path = output_dir / output_filename
        
        try:
            # 合并所有音频块并保存为WAV文件
            with wave.open(str(output_path), "wb") as wav_file:
                wav_file.setnchannels(1)  # 单声道
                wav_file.setsampwidth(2)  # 16-bit = 2字节
                wav_file.setframerate(tts_service.sample_rate)  # 采样率
                
                for chunk in audio_chunks:
                    wav_file.writeframes(chunk)
            
            # 计算音频时长
            total_samples = total_bytes // 2
            duration_seconds = total_samples / tts_service.sample_rate
            
            logger.info(f"✅ 音频保存成功!")
            logger.info(f"   输出文件: {output_path}")
            logger.info(f"   音频时长: {duration_seconds:.2f} 秒")
            logger.info(f"   采样率: {tts_service.sample_rate} Hz")
            logger.info(f"   声道数: 1 (单声道)")
            logger.info(f"   位深: 16 bit")
            logger.info(f"   文件大小: {output_path.stat().st_size} bytes")
            
        except Exception as e:
            logger.error(f"❌ 保存音频文件失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ 测试完成!")
        logger.info("=" * 80)
        return True
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_tts_non_streaming():
    """测试TTS非流式合成（对比测试）"""
    logger.info("\n" + "=" * 80)
    logger.info("TTS非流式合成测试（对比）")
    logger.info("=" * 80)
    
    try:
        from tts_utils import get_tts_service
        
        tts_service = get_tts_service()
        if not tts_service:
            logger.error("❌ 无法获取TTS服务实例")
            return False
        
        # 合并所有文本片段
        full_text = "".join(TEXT_CHUNKS)
        logger.info(f"\n📝 完整文本: {full_text}")
        logger.info(f"   文本长度: {len(full_text)} 字符")
        
        logger.info("\n🎤 开始非流式语音合成...")
        start_time = time.time()
        
        audio_data = await tts_service.synthesize(
            text=full_text,
            spk_id=None
        )
        
        synthesis_time = time.time() - start_time
        
        # 计算音频时长
        total_samples = len(audio_data) // 2
        duration_seconds = total_samples / tts_service.sample_rate
        
        logger.info(f"✅ 非流式合成完成!")
        logger.info(f"")
        logger.info(f"📊 非流式合成统计:")
        logger.info(f"   音频字节数: {len(audio_data):,} bytes ({len(audio_data)/1024:.2f} KB)")
        logger.info(f"   音频时长: {duration_seconds:.2f} 秒")
        logger.info(f"   合成耗时: {synthesis_time:.2f} 秒")
        if synthesis_time > 0:
            logger.info(f"   合成速率: {len(audio_data)/1024/synthesis_time:.2f} KB/秒")
        
        # 保存音频文件
        output_dir = Path(project_root) / "test_output"
        output_dir.mkdir(exist_ok=True)
        
        timestamp = int(time.time())
        output_filename = f"tts_test_non_streaming_{timestamp}.wav"
        output_path = output_dir / output_filename
        
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(tts_service.sample_rate)
            wav_file.writeframes(audio_data)
        
        total_samples = len(audio_data) // 2
        duration_seconds = total_samples / tts_service.sample_rate
        
        logger.info(f"✅ 音频保存成功!")
        logger.info(f"   输出文件: {output_path}")
        logger.info(f"   音频时长: {duration_seconds:.2f} 秒")
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ 非流式测试完成!")
        logger.info("=" * 80)
        return True
        
    except Exception as e:
        logger.error(f"❌ 非流式测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主函数"""
    logger.info("\n" + "=" * 80)
    logger.info("TTS文本片段测试脚本")
    logger.info("=" * 80)
    logger.info(f"\n📋 测试文本片段 ({len(TEXT_CHUNKS)} 个):")
    for i, chunk in enumerate(TEXT_CHUNKS, 1):
        logger.info(f"   {i}. {chunk}")
    logger.info("")
    
    # 测试1: 流式合成
    streaming_result = await test_tts_streaming()
    
    # 测试2: 非流式合成（对比）
    non_streaming_result = await test_tts_non_streaming()
    
    # 总结
    logger.info("\n" + "=" * 80)
    logger.info("测试总结")
    logger.info("=" * 80)
    logger.info(f"流式合成: {'✅ 通过' if streaming_result else '❌ 失败'}")
    logger.info(f"非流式合成: {'✅ 通过' if non_streaming_result else '❌ 失败'}")
    
    if streaming_result:
        logger.info("\n🎉 流式合成测试通过！")
        return 0
    else:
        logger.error("\n❌ 流式合成测试失败，请检查错误信息")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

