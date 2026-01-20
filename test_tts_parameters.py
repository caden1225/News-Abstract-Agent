#!/usr/bin/env python3
"""
TTS参数测试脚本
测试不同参数组合对TTS生成质量和速度的影响
- 只合成一个短句，快速测试
- 以参数作为文件名的一部分
- 记录RTF、延迟等指标
"""
import asyncio
import logging
import sys
import time
import wave
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional
from datetime import datetime
import uuid

# 加载环境变量（必须在其他导入之前）
from dotenv import load_dotenv
load_dotenv()

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 配置日志（减少输出）
logging.basicConfig(
    level=logging.WARNING,  # 只显示警告和错误
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 音频参数
AUDIO_SAMPLE_RATE = 24000  # 采样率（Hz）
AUDIO_SAMPLE_WIDTH = 2  # 16位 = 2字节
AUDIO_CHANNELS = 1  # 单声道

# 测试文本（短句）
TEST_TEXT = "人工智能技术正在快速发展，深度学习和大语言模型等前沿技术不断突破。"


class TTSParameterTester:
    """TTS参数测试器"""
    
    def __init__(self):
        self.results: List[Dict] = []
    
    async def test_parameter_combination(
        self,
        token_hop_len: int,
        mel_cache_len: int,
        min_length: int,
        max_wait_time: float,
        test_text: str = TEST_TEXT
    ) -> Dict:
        """
        测试一组参数组合
        
        Args:
            token_hop_len: 音频块大小（token数）
            mel_cache_len: 边界平滑缓存长度
            min_length: 最小句子长度
            max_wait_time: 最大等待时间
            test_text: 测试文本
        
        Returns:
            测试结果字典
        """
        print(f"\n{'='*80}")
        print(f"测试参数组合:")
        print(f"  token_hop_len={token_hop_len}")
        print(f"  mel_cache_len={mel_cache_len}")
        print(f"  min_length={min_length}")
        print(f"  max_wait_time={max_wait_time}")
        print(f"  测试文本: {test_text[:50]}...")
        print(f"{'='*80}")
        
        try:
            # 初始化TTS服务
            from tts_utils import get_tts_service
            tts_service = get_tts_service()
            
            if not tts_service or not tts_service.enabled:
                return {
                    "success": False,
                    "error": "TTS服务未启用",
                    "params": {
                        "token_hop_len": token_hop_len,
                        "mel_cache_len": mel_cache_len,
                        "min_length": min_length,
                        "max_wait_time": max_wait_time
                    }
                }
            
            # 创建文本流（立即输入所有文本，无延迟）
            async def text_stream():
                yield test_text
            
            # 记录时间
            start_time = time.time()
            first_audio_time = None
            audio_chunks: List[bytes] = []
            
            # 执行TTS合成（传递参数覆盖）
            async for audio_chunk in tts_service.local_service.synthesize_stream(
                text_stream=text_stream(),
                language="zh",
                request_id=f"param_test_{uuid.uuid4().hex[:8]}",
                format="pcm",
                sample_rate=AUDIO_SAMPLE_RATE,
                token_hop_len=token_hop_len,
                mel_cache_len=mel_cache_len,
                min_length=min_length,
                max_wait_time=max_wait_time
            ):
                if first_audio_time is None:
                    first_audio_time = time.time()
                
                audio_chunks.append(audio_chunk.audio_data)
            
            end_time = time.time()
            
            # 计算指标
            total_time = end_time - start_time
            first_audio_latency = (first_audio_time - start_time) * 1000 if first_audio_time else None
            
            total_audio_bytes = sum(len(chunk) for chunk in audio_chunks)
            total_samples = total_audio_bytes // AUDIO_SAMPLE_WIDTH
            audio_duration = total_samples / AUDIO_SAMPLE_RATE
            
            rtf = audio_duration / total_time if total_time > 0 else 0
            
            # 保存音频文件
            audio_file_path = self.save_audio_file(
                audio_chunks=audio_chunks,
                token_hop_len=token_hop_len,
                mel_cache_len=mel_cache_len,
                min_length=min_length,
                max_wait_time=max_wait_time
            )
            
            result = {
                "success": True,
                "params": {
                    "token_hop_len": token_hop_len,
                    "mel_cache_len": mel_cache_len,
                    "min_length": min_length,
                    "max_wait_time": max_wait_time
                },
                "metrics": {
                    "first_audio_latency_ms": first_audio_latency,
                    "total_time_s": total_time,
                    "audio_duration_s": audio_duration,
                    "rtf": rtf,
                    "audio_chunks": len(audio_chunks),
                    "total_audio_bytes": total_audio_bytes
                },
                "audio_file": audio_file_path
            }
            
            print(f"✅ 测试完成:")
            print(f"  首音频延迟: {first_audio_latency:.2f}ms")
            print(f"  总处理时间: {total_time:.3f}s")
            print(f"  音频时长: {audio_duration:.2f}s")
            print(f"  RTF: {rtf:.3f}")
            print(f"  音频文件: {audio_file_path}")
            
            return result
        
        except Exception as e:
            logger.error(f"测试失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "params": {
                    "token_hop_len": token_hop_len,
                    "mel_cache_len": mel_cache_len,
                    "min_length": min_length,
                    "max_wait_time": max_wait_time
                }
            }
    
    def save_audio_file(
        self,
        audio_chunks: List[bytes],
        token_hop_len: int,
        mel_cache_len: int,
        min_length: int,
        max_wait_time: float
    ) -> Optional[Path]:
        """保存音频文件，文件名包含参数信息"""
        if not audio_chunks:
            return None
        
        try:
            # 创建输出目录
            output_dir = Path("test_output")
            output_dir.mkdir(exist_ok=True)
            
            # 生成文件名：包含所有参数
            # 将max_wait_time的小数点替换为下划线，避免文件名问题
            mw_str = str(max_wait_time).replace('.', '_')
            timestamp = int(time.time())
            filename = f"test_th{token_hop_len}_mc{mel_cache_len}_ml{min_length}_mw{mw_str}_{timestamp}.wav"
            output_path = output_dir / filename
            
            # 合并所有音频块
            total_bytes = sum(len(chunk) for chunk in audio_chunks)
            
            with wave.open(str(output_path), "wb") as wav_file:
                wav_file.setnchannels(AUDIO_CHANNELS)
                wav_file.setsampwidth(AUDIO_SAMPLE_WIDTH)
                wav_file.setframerate(AUDIO_SAMPLE_RATE)
                
                for chunk in audio_chunks:
                    wav_file.writeframes(chunk)
            
            return output_path
        
        except Exception as e:
            logger.error(f"保存音频文件失败: {e}", exc_info=True)
            return None
    
    def print_summary(self):
        """打印测试总结"""
        if not self.results:
            print("没有测试结果")
            return
        
        successful_results = [r for r in self.results if r.get("success")]
        
        if not successful_results:
            print("没有成功的测试结果")
            return
        
        print(f"\n{'='*80}")
        print("测试总结")
        print(f"{'='*80}")
        print(f"成功测试: {len(successful_results)}/{len(self.results)}")
        print(f"\n{'参数组合':<50} {'RTF':<10} {'延迟(ms)':<12} {'音频时长(s)':<15} {'文件'}")
        print("-" * 80)
        
        for result in successful_results:
            params = result["params"]
            metrics = result["metrics"]
            file_path = result.get("audio_file", "N/A")
            
            param_str = f"th{params['token_hop_len']}_mc{params['mel_cache_len']}_ml{params['min_length']}_mw{params['max_wait_time']}"
            rtf = metrics["rtf"]
            latency = metrics["first_audio_latency_ms"]
            duration = metrics["audio_duration_s"]
            filename = file_path.name if isinstance(file_path, Path) else file_path
            
            print(f"{param_str:<50} {rtf:<10.3f} {latency:<12.2f} {duration:<15.2f} {filename}")
        
        print(f"{'='*80}\n")
        
        # 找出最佳RTF
        best_rtf = min(successful_results, key=lambda x: x["metrics"]["rtf"])
        print(f"最佳RTF: {best_rtf['metrics']['rtf']:.3f}")
        print(f"  参数: token_hop_len={best_rtf['params']['token_hop_len']}, "
              f"mel_cache_len={best_rtf['params']['mel_cache_len']}, "
              f"min_length={best_rtf['params']['min_length']}, "
              f"max_wait_time={best_rtf['params']['max_wait_time']}")
        print(f"  文件: {best_rtf.get('audio_file', 'N/A')}")


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="TTS参数测试脚本")
    parser.add_argument(
        "--text",
        type=str,
        default=TEST_TEXT,
        help=f"测试文本（默认：{TEST_TEXT[:30]}...）"
    )
    parser.add_argument(
        "--token-hop-len",
        type=int,
        nargs="+",
        default=[30, 50, 80, 100],
        help="token_hop_len参数值列表（默认：30 50 80 100）"
    )
    parser.add_argument(
        "--mel-cache-len",
        type=int,
        nargs="+",
        default=[3, 4, 6, 8],
        help="mel_cache_len参数值列表（默认：3 4 6 8）"
    )
    parser.add_argument(
        "--min-length",
        type=int,
        nargs="+",
        default=[10, 15, 25],
        help="min_length参数值列表（默认：10 15 25）"
    )
    parser.add_argument(
        "--max-wait-time",
        type=float,
        nargs="+",
        default=[0.5, 1.0, 2.0],
        help="max_wait_time参数值列表（默认：0.5 1.0 2.0）"
    )
    parser.add_argument(
        "--single",
        action="store_true",
        help="只测试一组参数（使用第一个值）"
    )
    
    args = parser.parse_args()
    
    tester = TTSParameterTester()
    
    print("\n" + "=" * 80)
    print("TTS参数测试工具")
    print("=" * 80)
    print(f"测试文本: {args.text}")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # 生成参数组合
    if args.single:
        # 只测试一组参数
        param_combinations = [{
            "token_hop_len": args.token_hop_len[0],
            "mel_cache_len": args.mel_cache_len[0],
            "min_length": args.min_length[0],
            "max_wait_time": args.max_wait_time[0]
        }]
    else:
        # 测试所有参数组合（笛卡尔积）
        import itertools
        param_combinations = [
            {
                "token_hop_len": th,
                "mel_cache_len": mc,
                "min_length": ml,
                "max_wait_time": mw
            }
            for th, mc, ml, mw in itertools.product(
                args.token_hop_len,
                args.mel_cache_len,
                args.min_length,
                args.max_wait_time
            )
        ]
    
    print(f"\n将测试 {len(param_combinations)} 组参数组合")
    print("=" * 80)
    
    # 预热TTS服务（只做一次）
    print("\n预热TTS服务...")
    try:
        from tts_utils import get_tts_service
        tts_service = get_tts_service()
        if tts_service and tts_service.enabled:
            async def warmup_stream():
                yield "预热文本。"
            async for _ in tts_service.synthesize_stream(
                text_stream=warmup_stream(),
                language="zh",
                request_id="warmup"
            ):
                break
            print("✅ TTS服务预热完成\n")
    except Exception as e:
        print(f"⚠️ 预热失败: {e}，继续测试\n")
    
    # 执行测试
    for i, params in enumerate(param_combinations, 1):
        print(f"\n[{i}/{len(param_combinations)}] 测试中...")
        
        result = await tester.test_parameter_combination(
            token_hop_len=params["token_hop_len"],
            mel_cache_len=params["mel_cache_len"],
            min_length=params["min_length"],
            max_wait_time=params["max_wait_time"],
            test_text=args.text
        )
        
        tester.results.append(result)
        
        # 短暂休息，避免GPU过热
        if i < len(param_combinations):
            await asyncio.sleep(1)
    
    # 打印总结
    tester.print_summary()
    
    print(f"\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print("\n💡 提示：")
    print("  - 音频文件保存在 test_output/ 目录")
    print("  - 文件名格式: test_th{token_hop_len}_mc{mel_cache_len}_ml{min_length}_mw{max_wait_time}_{timestamp}.wav")
    print("  - 可以对比不同参数组合的音频质量和RTF指标")


if __name__ == "__main__":
    asyncio.run(main())

