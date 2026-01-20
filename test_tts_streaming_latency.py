#!/usr/bin/env python3
"""
TTS流式生成延时测试脚本
直接测试TTS服务的流式生成性能，测量关键延时指标
"""
import asyncio
import logging
import sys
import time
import statistics
import wave
from pathlib import Path
from typing import AsyncGenerator, List, Dict, Optional
from datetime import datetime
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

# 音频参数
AUDIO_SAMPLE_RATE = 24000  # 采样率（Hz）
AUDIO_SAMPLE_WIDTH = 2  # 16位 = 2字节
AUDIO_CHANNELS = 1  # 单声道

# 文本样例数据
TEXT_SAMPLES = {
    "news1": "近日伊朗局势持续紧张，革命卫队高官宣布该国已进入最高战备状态，导弹储备量自2025年以来持续增加。",
    "news2": "据最新消息，国际油价在今日早盘出现大幅波动，布伦特原油期货价格一度上涨超过3%，市场分析师认为这与中东地区紧张局势有关。",
    "news3": "科技巨头发布最新财报，显示人工智能业务收入同比增长150%，超出市场预期。公司股价在盘后交易中上涨超过8%。",
    "short": "你好，这是一个简短的测试文本。",
    "medium": "人工智能技术正在快速发展，深度学习、大语言模型等前沿技术不断突破，为各行各业带来新的机遇和挑战。",
    "long": "随着全球气候变化的加剧，各国政府和企业都在积极寻求可持续发展的解决方案。可再生能源、电动汽车、碳捕获技术等领域正在快速发展，为构建绿色未来贡献力量。同时，数字化转型也在加速推进，云计算、物联网、区块链等新技术正在重塑传统产业格局。",
    "tech": "量子计算技术取得重大突破，研究人员成功实现了1000量子比特的稳定运行，这标志着量子计算从实验室走向实用化的重要里程碑。",
    "finance": "央行宣布降准0.5个百分点，释放长期资金约1万亿元，旨在支持实体经济发展，稳定市场流动性。市场普遍认为这一政策将有助于提振经济信心。",
    "sports": "在刚刚结束的比赛中，主队以3比1的比分战胜对手，取得了本赛季的第三场胜利。球队核心球员表现出色，贡献了两粒进球和一次助攻。"
}


class TTSLatencyTester:
    """TTS流式生成延时测试器"""
    
    def __init__(self):
        self.metrics: Dict[str, List[float]] = {
            "first_audio_latency": [],      # 首音频块延迟（从文本流开始到首音频块）
            "text_to_audio_delay": [],     # 文本到音频延迟（从首文本到首音频）
            "audio_chunk_intervals": [],    # 音频块间隔时间
            "total_processing_time": [],    # 总处理时间
            "audio_chunk_count": [],        # 音频块数量
            "total_audio_duration": [],     # 总音频时长（秒）
            "realtime_factor": [],         # 实时因子（RTF）
            "audio_generation_rate": []     # 音频生成速率（字节/秒）
        }
        self._warmed_up = False  # 预热状态标记
    
    async def create_text_stream(
        self,
        text: str,
        mode: str = "token",
        chunk_size: int = 1,
        delay: float = 0.05
    ) -> AsyncGenerator[str, None]:
        """
        创建模拟的文本流生成器
        
        Args:
            text: 完整文本
            mode: 输入模式 ("token", "word", "sentence")
            chunk_size: 每次yield的字符数（token模式）
            delay: 每次yield之间的延迟（秒）
        
        Yields:
            str: 文本块
        """
        if mode == "token":
            # 按字符输入（模拟token级别）
            for i in range(0, len(text), chunk_size):
                yield text[i:i + chunk_size]
                if delay > 0:
                    await asyncio.sleep(delay)
        
        elif mode == "word":
            # 按词输入（简单按空格分割）
            words = text.split()
            for word in words:
                yield word + " "
                if delay > 0:
                    await asyncio.sleep(delay)
        
        elif mode == "sentence":
            # 按句子输入
            sentences = []
            current_sentence = ""
            
            for char in text:
                current_sentence += char
                if char in ['。', '.', '！', '!', '？', '?', '；', ';', '\n']:
                    if current_sentence.strip():
                        sentences.append(current_sentence.strip())
                    current_sentence = ""
            
            if current_sentence.strip():
                sentences.append(current_sentence.strip())
            
            if not sentences:
                sentences = [text]
            
            for sentence in sentences:
                yield sentence
                if delay > 0:
                    await asyncio.sleep(delay)
    
    async def warmup_tts(self, tts_service, timeout: float = 15.0) -> bool:
        """
        预热TTS模型，避免首次推理延迟影响测试结果
        
        Args:
            tts_service: TTS服务实例
            timeout: 预热超时时间（秒）
        
        Returns:
            bool: 预热是否成功
        """
        if self._warmed_up:
            logger.debug("TTS模型已预热，跳过")
            return True
        
        logger.info(f"\n{'='*80}")
        logger.info("开始预热TTS模型（避免首次推理延迟影响测试）")
        logger.info(f"{'='*80}\n")
        
        try:
            start_time = time.time()
            
            async def warmup_text_stream():
                """预热用的简单文本流"""
                yield "你好，这是预热文本。"
            
            # 执行预热：获取至少一个音频块
            chunk_count = 0
            async def do_warmup():
                nonlocal chunk_count
                async for chunk in tts_service.synthesize_stream(
                    text_stream=warmup_text_stream(),
                    language="zh",
                    request_id="warmup",
                    format="pcm",
                    sample_rate=AUDIO_SAMPLE_RATE
                ):
                    chunk_count += 1
                    # 获取第一个chunk就足够预热了
                    if chunk_count >= 1:
                        break
            
            await asyncio.wait_for(do_warmup(), timeout=timeout)
            elapsed = time.time() - start_time
            
            logger.info(f"✅ TTS模型预热完成，耗时: {elapsed:.2f}秒")
            logger.info(f"   预热生成了 {chunk_count} 个音频块")
            logger.info(f"{'='*80}\n")
            
            self._warmed_up = True
            return True
        
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ TTS模型预热超时（>{timeout}秒），但将继续测试")
            self._warmed_up = True  # 标记为已尝试，避免重复
            return False
        except Exception as e:
            logger.warning(f"⚠️ TTS模型预热失败: {e}，但将继续测试")
            logger.warning("   注意：首次测试可能包含模型初始化延迟")
            self._warmed_up = True  # 标记为已尝试，避免重复
            return False
    
    async def test_single_run(
        self,
        text: str,
        text_stream_mode: str = "token",
        text_stream_delay: float = 0.05,
        request_id: Optional[str] = None,
        warmup: bool = True
    ) -> Dict:
        """
        执行单次TTS流式生成测试
        
        Args:
            text: 测试文本
            text_stream_mode: 文本流模式
            text_stream_delay: 文本流延迟
            request_id: 请求ID
            warmup: 是否在测试前预热模型（默认True）
        
        Returns:
            包含测试结果的字典
        """
        if request_id is None:
            request_id = f"test_{uuid.uuid4().hex[:8]}"
        
        logger.info(f"\n{'='*80}")
        logger.info(f"开始测试: request_id={request_id}")
        logger.info(f"测试文本: {text[:50]}...")
        logger.info(f"文本长度: {len(text)} 字符")
        logger.info(f"文本流模式: {text_stream_mode}, 延迟: {text_stream_delay}s")
        logger.info(f"{'='*80}\n")
        
        # 初始化TTS服务
        try:
            from tts_utils import get_tts_service
            tts_service = get_tts_service()
            
            if not tts_service or not tts_service.enabled:
                logger.error("❌ TTS服务未启用")
                return {"success": False, "error": "TTS服务未启用"}
        
        except Exception as e:
            logger.error(f"❌ TTS服务初始化失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        
        # 预热TTS模型（如果需要）
        if warmup:
            await self.warmup_tts(tts_service)
        
        # 记录关键时间点
        timestamps = {
            "text_stream_start": None,      # 文本流开始时间
            "first_text_token": None,        # 首文本token时间
            "first_audio_chunk": None,       # 首音频块时间
            "last_audio_chunk": None,        # 最后一个音频块时间
            "text_stream_end": None          # 文本流结束时间
        }
        
        # 统计数据
        stats = {
            "audio_chunk_count": 0,
            "total_audio_bytes": 0,
            "audio_chunk_times": [],         # 每个音频块的到达时间（相对于开始）
            "audio_chunk_sizes": [],         # 每个音频块的大小
            "text_tokens": 0
        }
        
        # 收集所有音频块（用于保存文件）
        audio_chunks: List[bytes] = []
        
        try:
            # 创建文本流
            text_stream = self.create_text_stream(
                text=text,
                mode=text_stream_mode,
                delay=text_stream_delay
            )
            
            # 开始测试
            timestamps["text_stream_start"] = time.time()
            timestamps["first_text_token"] = time.time()  # 第一个token立即开始
            
            logger.info("开始TTS流式合成...")
            
            # 调用TTS流式合成
            async for audio_chunk in tts_service.synthesize_stream(
                text_stream=text_stream,
                language="zh",
                request_id=request_id,
                format="pcm",
                sample_rate=AUDIO_SAMPLE_RATE
            ):
                current_time = time.time()
                elapsed = current_time - timestamps["text_stream_start"]
                
                # 记录首音频块
                if timestamps["first_audio_chunk"] is None:
                    timestamps["first_audio_chunk"] = current_time
                    first_audio_latency = elapsed * 1000
                    logger.info(f"✅ 首音频块到达: {first_audio_latency:.2f}ms")
                
                # 更新最后音频块时间
                timestamps["last_audio_chunk"] = current_time
                
                # 统计信息
                stats["audio_chunk_count"] += 1
                audio_size = len(audio_chunk.audio_data)
                stats["total_audio_bytes"] += audio_size
                stats["audio_chunk_times"].append(elapsed)
                stats["audio_chunk_sizes"].append(audio_size)
                
                # 收集音频块
                audio_chunks.append(audio_chunk.audio_data)
                
                logger.debug(
                    f"音频块 #{stats['audio_chunk_count']}: "
                    f"chunk_id={audio_chunk.chunk_id}, "
                    f"大小={audio_size} 字节, "
                    f"文本='{audio_chunk.text[:30]}...', "
                    f"延迟={elapsed*1000:.2f}ms"
                )
            
            timestamps["text_stream_end"] = time.time()
            
            # 保存音频文件
            audio_file_path = None
            if audio_chunks:
                audio_file_path = self.save_audio_file(
                    audio_chunks=audio_chunks,
                    text=text,
                    request_id=request_id,
                    mode=text_stream_mode
                )
            
            # 计算指标
            total_time = timestamps["text_stream_end"] - timestamps["text_stream_start"]
            first_audio_latency = (
                (timestamps["first_audio_chunk"] - timestamps["text_stream_start"]) * 1000
                if timestamps["first_audio_chunk"] else None
            )
            
            # 计算音频时长
            total_samples = stats["total_audio_bytes"] // AUDIO_SAMPLE_WIDTH
            audio_duration = total_samples / AUDIO_SAMPLE_RATE
            
            # 计算实时因子（RTF）
            realtime_factor = audio_duration / total_time if total_time > 0 else 0
            
            # 计算音频生成速率
            audio_generation_rate = stats["total_audio_bytes"] / total_time if total_time > 0 else 0
            
            # 计算音频块间隔
            chunk_intervals = []
            if len(stats["audio_chunk_times"]) > 1:
                for i in range(1, len(stats["audio_chunk_times"])):
                    interval = stats["audio_chunk_times"][i] - stats["audio_chunk_times"][i-1]
                    chunk_intervals.append(interval * 1000)  # 转换为毫秒
            
            result = {
                "success": True,
                "request_id": request_id,
                "timestamps": timestamps,
                "stats": stats,
                "audio_file_path": audio_file_path,
                "metrics": {
                    "first_audio_latency_ms": first_audio_latency,
                    "total_processing_time_s": total_time,
                    "audio_chunk_count": stats["audio_chunk_count"],
                    "total_audio_bytes": stats["total_audio_bytes"],
                    "audio_duration_s": audio_duration,
                    "realtime_factor": realtime_factor,
                    "audio_generation_rate_bytes_per_s": audio_generation_rate,
                    "avg_chunk_interval_ms": statistics.mean(chunk_intervals) if chunk_intervals else 0,
                    "min_chunk_interval_ms": min(chunk_intervals) if chunk_intervals else 0,
                    "max_chunk_interval_ms": max(chunk_intervals) if chunk_intervals else 0
                }
            }
            
            # 打印结果
            self.print_test_result(result)
            
            return result
        
        except Exception as e:
            logger.error(f"❌ 测试失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def save_audio_file(
        self,
        audio_chunks: List[bytes],
        text: str,
        request_id: str,
        mode: str
    ) -> Optional[Path]:
        """
        保存音频文件
        
        Args:
            audio_chunks: 音频块列表
            text: 测试文本
            request_id: 请求ID
            mode: 文本流模式
        
        Returns:
            保存的文件路径，如果失败则返回None
        """
        if not audio_chunks:
            return None
        
        try:
            # 创建输出目录
            output_dir = Path("test_output")
            output_dir.mkdir(exist_ok=True)
            
            # 生成输出文件名
            timestamp = int(time.time())
            safe_text = "".join(c for c in text[:20] if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_text = safe_text.replace(' ', '_') if safe_text else "tts_test"
            output_filename = f"{safe_text}_{mode}_{request_id}_{timestamp}_merged.wav"
            output_path = output_dir / output_filename
            
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
            
            logger.info(f"\n✅ 音频文件已保存:")
            logger.info(f"   文件路径: {output_path}")
            logger.info(f"   文件大小: {total_bytes} 字节 ({total_bytes / 1024:.2f} KB)")
            logger.info(f"   音频时长: {duration_seconds:.2f} 秒")
            logger.info(f"   采样率: {AUDIO_SAMPLE_RATE} Hz")
            logger.info(f"   声道数: {AUDIO_CHANNELS}")
            logger.info(f"   位深: {AUDIO_SAMPLE_WIDTH * 8} bit")
            
            return output_path
        
        except Exception as e:
            logger.error(f"❌ 保存音频文件失败: {e}", exc_info=True)
            return None
    
    def print_test_result(self, result: Dict):
        """打印单次测试结果"""
        if not result.get("success"):
            logger.error(f"测试失败: {result.get('error')}")
            return
        
        metrics = result["metrics"]
        audio_file_path = result.get("audio_file_path")
        
        logger.info(f"\n{'='*80}")
        logger.info("测试结果")
        logger.info(f"{'='*80}")
        logger.info(f"首音频块延迟: {metrics['first_audio_latency_ms']:.2f}ms")
        logger.info(f"总处理时间: {metrics['total_processing_time_s']:.3f}s")
        logger.info(f"音频块数量: {metrics['audio_chunk_count']}")
        logger.info(f"总音频大小: {metrics['total_audio_bytes']} 字节 ({metrics['total_audio_bytes']/1024:.2f} KB)")
        logger.info(f"音频时长: {metrics['audio_duration_s']:.2f}s")
        logger.info(f"实时因子 (RTF): {metrics['realtime_factor']:.3f}x")
        logger.info(f"音频生成速率: {metrics['audio_generation_rate_bytes_per_s']:.0f} 字节/秒")
        
        if metrics['avg_chunk_interval_ms'] > 0:
            logger.info(f"音频块间隔:")
            logger.info(f"  - 平均: {metrics['avg_chunk_interval_ms']:.2f}ms")
            logger.info(f"  - 最小: {metrics['min_chunk_interval_ms']:.2f}ms")
            logger.info(f"  - 最大: {metrics['max_chunk_interval_ms']:.2f}ms")
        
        if audio_file_path:
            logger.info(f"\n💡 音频文件: {audio_file_path}")
            logger.info(f"   可以使用以下命令播放:")
            logger.info(f"   ffplay {audio_file_path}")
            logger.info(f"   或")
            logger.info(f"   aplay {audio_file_path}")
        
        logger.info(f"{'='*80}\n")
    
    async def test_multiple_runs(
        self,
        text: str,
        iterations: int = 5,
        text_stream_mode: str = "token",
        text_stream_delay: float = 0.05,
        warmup: bool = True
    ):
        """
        执行多次测试并统计
        
        Args:
            text: 测试文本
            iterations: 测试次数
            text_stream_mode: 文本流模式
            text_stream_delay: 文本流延迟
            warmup: 是否在第一次测试前预热模型（默认True）
        """
        logger.info(f"\n{'='*80}")
        logger.info("TTS流式生成延时测试 - 多次测试")
        logger.info(f"{'='*80}")
        logger.info(f"测试文本: {text[:50]}...")
        logger.info(f"测试次数: {iterations}")
        logger.info(f"文本流模式: {text_stream_mode}, 延迟: {text_stream_delay}s")
        logger.info(f"预热模型: {'是' if warmup else '否'}")
        logger.info(f"{'='*80}\n")
        
        results = []
        
        for i in range(iterations):
            logger.info(f"\n--- 第 {i+1}/{iterations} 次测试 ---")
            
            # 只在第一次测试时预热（如果启用）
            should_warmup = warmup and (i == 0)
            
            result = await self.test_single_run(
                text=text,
                text_stream_mode=text_stream_mode,
                text_stream_delay=text_stream_delay,
                request_id=f"test_{i+1}_{int(time.time())}",
                warmup=should_warmup
            )
            
            if result.get("success"):
                results.append(result)
                metrics = result["metrics"]
                
                # 收集指标
                self.metrics["first_audio_latency"].append(metrics["first_audio_latency_ms"])
                self.metrics["total_processing_time"].append(metrics["total_processing_time_s"])
                self.metrics["audio_chunk_count"].append(metrics["audio_chunk_count"])
                self.metrics["total_audio_duration"].append(metrics["audio_duration_s"])
                self.metrics["realtime_factor"].append(metrics["realtime_factor"])
                self.metrics["audio_generation_rate"].append(metrics["audio_generation_rate_bytes_per_s"])
            
            # 等待一段时间再开始下一次测试
            if i < iterations - 1:
                await asyncio.sleep(2)
        
        # 打印统计结果
        self.print_statistics(results)
    
    def print_statistics(self, results: List[Dict]):
        """打印统计结果"""
        if not results:
            logger.warning("没有成功的测试结果")
            return
        
        logger.info(f"\n{'='*80}")
        logger.info("统计结果（多次测试）")
        logger.info(f"{'='*80}")
        logger.info(f"成功测试次数: {len(results)}/{len(results) + (len(self.metrics['first_audio_latency']) - len(results))}")
        
        if self.metrics["first_audio_latency"]:
            latencies = self.metrics["first_audio_latency"]
            logger.info(f"\n首音频块延迟:")
            logger.info(f"  - 平均: {statistics.mean(latencies):.2f}ms")
            logger.info(f"  - 中位数: {statistics.median(latencies):.2f}ms")
            logger.info(f"  - 最小: {min(latencies):.2f}ms")
            logger.info(f"  - 最大: {max(latencies):.2f}ms")
            if len(latencies) > 1:
                logger.info(f"  - 标准差: {statistics.stdev(latencies):.2f}ms")
        
        if self.metrics["total_processing_time"]:
            times = self.metrics["total_processing_time"]
            logger.info(f"\n总处理时间:")
            logger.info(f"  - 平均: {statistics.mean(times):.3f}s")
            logger.info(f"  - 最小: {min(times):.3f}s")
            logger.info(f"  - 最大: {max(times):.3f}s")
        
        if self.metrics["realtime_factor"]:
            rtfs = self.metrics["realtime_factor"]
            logger.info(f"\n实时因子 (RTF):")
            logger.info(f"  - 平均: {statistics.mean(rtfs):.3f}x")
            logger.info(f"  - 最小: {min(rtfs):.3f}x")
            logger.info(f"  - 最大: {max(rtfs):.3f}x")
            logger.info(f"  - {'✅ RTF < 1.0 (实时生成)' if statistics.mean(rtfs) < 1.0 else '⚠️ RTF >= 1.0 (慢于实时)'}")
        
        if self.metrics["audio_generation_rate"]:
            rates = self.metrics["audio_generation_rate"]
            logger.info(f"\n音频生成速率:")
            logger.info(f"  - 平均: {statistics.mean(rates):.0f} 字节/秒")
            logger.info(f"  - 最小: {min(rates):.0f} 字节/秒")
            logger.info(f"  - 最大: {max(rates):.0f} 字节/秒")
        
        logger.info(f"\n{'='*80}\n")


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="TTS流式生成延时测试")
    parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="测试文本（如果未指定，使用--sample参数）"
    )
    parser.add_argument(
        "--sample",
        type=str,
        choices=list(TEXT_SAMPLES.keys()),
        default="news1",
        help=f"使用预设文本样例（默认：news1）。可选: {', '.join(TEXT_SAMPLES.keys())}"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="测试次数（默认：3）"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["token", "word", "sentence"],
        default="token",
        help="文本流模式: token(按字符), word(按词), sentence(按句子)（默认：token）"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="文本流延迟（秒/字符），模拟LLM生成速度（默认：0.05）。"
             "更小的值（如0.01）表示更快的生成速度，更大的值（如0.1）表示更慢的生成速度"
    )
    parser.add_argument(
        "--single",
        action="store_true",
        help="只执行单次测试（不进行统计）"
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="禁用模型预热（用于测试冷启动延迟）"
    )
    
    args = parser.parse_args()
    
    # 确定使用的文本
    if args.text:
        test_text = args.text
    else:
        test_text = TEXT_SAMPLES.get(args.sample, TEXT_SAMPLES["news1"])
    
    tester = TTSLatencyTester()
    
    print("\n" + "=" * 80)
    print("TTS流式生成延时测试工具")
    print("=" * 80)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"模型预热: {'禁用' if args.no_warmup else '启用（默认）'}")
    print(f"文本流延迟: {args.delay}秒/字符 (模拟LLM生成速度)")
    print(f"文本流模式: {args.mode}")
    if args.text:
        print(f"测试文本: {test_text[:50]}...")
    else:
        print(f"文本样例: {args.sample}")
        print(f"测试文本: {test_text[:50]}...")
    print("=" * 80)
    
    warmup_enabled = not args.no_warmup
    
    if args.single:
        # 单次测试
        result = await tester.test_single_run(
            text=test_text,
            text_stream_mode=args.mode,
            text_stream_delay=args.delay,
            warmup=warmup_enabled
        )
    else:
        # 多次测试
        await tester.test_multiple_runs(
            text=test_text,
            iterations=args.iterations,
            text_stream_mode=args.mode,
            text_stream_delay=args.delay,
            warmup=warmup_enabled
        )
    
    print(f"\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

