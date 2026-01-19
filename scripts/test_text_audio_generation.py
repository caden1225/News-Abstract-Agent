#!/usr/bin/env python3
"""
文本和音频生成性能测试脚本
测试并评估文本生成（LLM）和音频生成（TTS）的实现方式和速度
"""
import sys
import asyncio
import time
import statistics
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TextAudioPerformanceTester:
    """文本和音频生成性能测试器"""
    
    def __init__(self):
        self.metrics: Dict[str, List[float]] = {
            "llm_first_token": [],      # LLM首token延迟
            "llm_token_rate": [],        # LLM token生成速率（tokens/秒）
            "text_to_tts_delay": [],     # 文本到TTS的延迟
            "tts_first_chunk": [],       # TTS首音频块延迟
            "tts_chunk_rate": [],        # TTS音频块生成速率（chunks/秒）
            "total_latency": [],         # 总延迟（从请求到首音频）
            "text_length": [],           # 文本长度
            "audio_chunks": []           # 音频块数量
        }
    
    def print_header(self, title: str):
        """打印标题"""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70)
    
    def analyze_implementation(self):
        """分析实现方式"""
        self.print_header("实现方式分析")
        
        print("\n📝 文本生成（LLM）流程：")
        print("  1. LLM流式调用 (call_llm_stream)")
        print("  2. 每个token立即yield给客户端")
        print("  3. Content token同时放入text_stream_queue给TTS")
        print("  4. 支持thinking和content两种token类型")
        
        print("\n🔊 音频生成（TTS）流程：")
        print("  1. 从text_stream_queue接收文本token")
        print("  2. 智能分句（SentenceBuffer，检测句子边界）")
        print("  3. 对完整句子调用TTS模型（CosyVoice2/3）")
        print("  4. 流式返回音频块（PCM格式，24000Hz）")
        print("  5. 音频块放入audio_queue，由监控任务处理")
        
        print("\n⚡ 关键延迟点：")
        print("  - LLM首token延迟（TTFB）：LLM模型响应时间")
        print("  - 文本缓冲延迟：text_stream_queue缓冲机制（buffer_size=5, timeout=0.01s）")
        print("  - TTS首音频延迟：从首句到首音频块的时间")
        print("  - 音频生成速度：TTS模型处理速度")
        
        print("\n🔄 并行处理：")
        print("  - LLM生成和TTS合成并行进行")
        print("  - 文本token流式传递，不等待完整文本")
        print("  - 音频块异步生成和yield")
    
    async def test_llm_stream_performance(self, test_text: str = None):
        """测试LLM流式生成性能"""
        self.print_header("LLM流式生成性能测试")
        
        try:
            from llm_utils.llm_service import LLMService, llm_config
            from prompts import build_news_summary_messages
            
            # 使用测试文本或默认文本
            if test_text is None:
                test_text = "今天有什么新闻？"
            
            # 构建消息
            messages = [
                {"role": "user", "content": f"请用一句话回答：{test_text}"}
            ]
            
            model_name = llm_config['model']
            
            print(f"测试模型: {model_name}")
            print(f"测试文本: {test_text}")
            print(f"开始流式生成...\n")
            
            # 测试多次取平均值
            iterations = 3
            for i in range(iterations):
                print(f"  测试 {i+1}/{iterations}...")
                
                token_times = []
                first_token_time = None
                token_count = 0
                total_text = ""
                
                start_time = time.time()
                
                async for token_type, token_content in LLMService.call_llm_stream(
                    model_name=model_name,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=200,
                    enable_thinking=False
                ):
                    current_time = time.time()
                    elapsed = current_time - start_time
                    
                    if first_token_time is None:
                        first_token_time = elapsed
                        print(f"    首token延迟: {first_token_time*1000:.2f}ms")
                    
                    if token_type == "content":
                        token_count += 1
                        total_text += token_content
                        token_times.append(elapsed)
                
                total_time = time.time() - start_time
                
                if token_count > 0:
                    # 计算token速率
                    token_rate = token_count / total_time if total_time > 0 else 0
                    
                    print(f"    总时间: {total_time:.3f}s")
                    print(f"    Token数: {token_count}")
                    print(f"    文本长度: {len(total_text)} 字符")
                    print(f"    Token速率: {token_rate:.2f} tokens/s")
                    print(f"    字符速率: {len(total_text)/total_time:.2f} chars/s")
                    
                    self.metrics["llm_first_token"].append(first_token_time * 1000)
                    self.metrics["llm_token_rate"].append(token_rate)
                    self.metrics["text_length"].append(len(total_text))
                
                await asyncio.sleep(1)  # 间隔1秒
            
            # 统计结果
            if self.metrics["llm_first_token"]:
                avg_first_token = statistics.mean(self.metrics["llm_first_token"])
                avg_token_rate = statistics.mean(self.metrics["llm_token_rate"])
                
                print(f"\n📊 LLM性能统计（{iterations}次测试）：")
                print(f"  平均首token延迟: {avg_first_token:.2f}ms")
                print(f"  平均token速率: {avg_token_rate:.2f} tokens/s")
                print(f"  平均文本长度: {statistics.mean(self.metrics['text_length']):.1f} 字符")
                
        except Exception as e:
            print(f"❌ LLM性能测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_text_to_tts_pipeline(self, test_text: str = "这是一段测试文本，用于评估文本到音频的转换性能。"):
        """测试文本到TTS的完整流程"""
        self.print_header("文本到TTS完整流程测试")
        
        try:
            from tts_utils import get_tts_service
            import asyncio
            
            tts_service = get_tts_service()
            
            if not tts_service or not tts_service.enabled:
                print("⚠️  TTS服务未启用，跳过测试")
                return
            
            print(f"测试文本: {test_text}")
            print(f"文本长度: {len(test_text)} 字符\n")
            
            # 模拟文本流
            async def text_stream():
                # 模拟token级别的文本流
                tokens = list(test_text)
                for token in tokens:
                    yield token
                    await asyncio.sleep(0.01)  # 模拟LLM生成速度
            
            # 测试多次
            iterations = 3
            for i in range(iterations):
                print(f"  测试 {i+1}/{iterations}...")
                
                chunk_times = []
                first_chunk_time = None
                chunk_count = 0
                total_audio_size = 0
                
                text_start_time = time.time()
                
                async for audio_chunk in tts_service.synthesize_stream(
                    text_stream=text_stream(),
                    language="zh",
                    request_id=f"test_{i}"
                ):
                    current_time = time.time()
                    elapsed = current_time - text_start_time
                    
                    if first_chunk_time is None:
                        first_chunk_time = elapsed
                        print(f"    首音频块延迟: {first_chunk_time*1000:.2f}ms")
                    
                    chunk_count += 1
                    total_audio_size += len(audio_chunk.audio_data)
                    chunk_times.append(elapsed)
                
                total_time = time.time() - text_start_time
                
                if chunk_count > 0:
                    chunk_rate = chunk_count / total_time if total_time > 0 else 0
                    audio_duration = total_audio_size / (24000 * 2)  # PCM, 24000Hz, 16bit
                    realtime_factor = audio_duration / total_time if total_time > 0 else 0
                    
                    print(f"    总时间: {total_time:.3f}s")
                    print(f"    音频块数: {chunk_count}")
                    print(f"    音频大小: {total_audio_size} bytes")
                    print(f"    音频时长: {audio_duration:.2f}s")
                    print(f"    实时因子: {realtime_factor:.2f}x")
                    print(f"    块生成速率: {chunk_rate:.2f} chunks/s")
                    
                    self.metrics["tts_first_chunk"].append(first_chunk_time * 1000)
                    self.metrics["tts_chunk_rate"].append(chunk_rate)
                    self.metrics["audio_chunks"].append(chunk_count)
                
                await asyncio.sleep(2)  # 间隔2秒
            
            # 统计结果
            if self.metrics["tts_first_chunk"]:
                avg_first_chunk = statistics.mean(self.metrics["tts_first_chunk"])
                avg_chunk_rate = statistics.mean(self.metrics["tts_chunk_rate"])
                
                print(f"\n📊 TTS性能统计（{iterations}次测试）：")
                print(f"  平均首音频块延迟: {avg_first_chunk:.2f}ms")
                print(f"  平均块生成速率: {avg_chunk_rate:.2f} chunks/s")
                print(f"  平均音频块数: {statistics.mean(self.metrics['audio_chunks']):.1f}")
                
        except Exception as e:
            print(f"❌ TTS性能测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_end_to_end_latency(self):
        """测试端到端延迟（从请求到首音频块）"""
        self.print_header("端到端延迟测试")
        
        try:
            from core.orchestrator import NewsAgentOrchestrator
            
            orchestrator = NewsAgentOrchestrator()
            
            test_query = "今天有什么新闻"
            request_id = f"latency_test_{int(time.time())}"
            
            print(f"测试查询: {test_query}")
            print(f"开始端到端测试...\n")
            
            # 记录关键时间点
            timestamps = {
                "request_start": None,
                "first_text_token": None,
                "first_audio_chunk": None,
                "request_end": None
            }
            
            frame_count = 0
            text_token_count = 0
            audio_chunk_count = 0
            
            timestamps["request_start"] = time.time()
            
            async for response in orchestrator.process_query(
                query=test_query,
                request_id=request_id,
                stream=True
            ):
                current_time = time.time()
                frame_count += 1
                
                # 解析响应
                if "data:" in response:
                    try:
                        import json
                        data_str = response.split("data:", 1)[1].strip()
                        data = json.loads(data_str)
                        
                        response_data = data.get("data", {})
                        response_type = response_data.get("response_type", "")
                        
                        # 检测首文本token
                        if response_type == "text" and timestamps["first_text_token"] is None:
                            timestamps["first_text_token"] = current_time
                            text_token_count += 1
                            print(f"  ✅ 首文本token: {(current_time - timestamps['request_start'])*1000:.2f}ms")
                        
                        # 检测首音频块
                        if response_type == "audio" and timestamps["first_audio_chunk"] is None:
                            timestamps["first_audio_chunk"] = current_time
                            audio_chunk_count += 1
                            print(f"  ✅ 首音频块: {(current_time - timestamps['request_start'])*1000:.2f}ms")
                        
                        if response_type == "text":
                            text_token_count += 1
                        elif response_type == "audio":
                            audio_chunk_count += 1
                    
                    except:
                        pass
            
            timestamps["request_end"] = time.time()
            
            total_time = timestamps["request_end"] - timestamps["request_start"]
            
            print(f"\n📊 端到端性能统计：")
            print(f"  总时间: {total_time:.3f}s")
            print(f"  总帧数: {frame_count}")
            print(f"  文本token数: {text_token_count}")
            print(f"  音频块数: {audio_chunk_count}")
            
            if timestamps["first_text_token"]:
                text_latency = (timestamps["first_text_token"] - timestamps["request_start"]) * 1000
                print(f"  首文本token延迟: {text_latency:.2f}ms")
                self.metrics["llm_first_token"].append(text_latency)
            
            if timestamps["first_audio_chunk"]:
                audio_latency = (timestamps["first_audio_chunk"] - timestamps["request_start"]) * 1000
                print(f"  首音频块延迟: {audio_latency:.2f}ms")
                self.metrics["total_latency"].append(audio_latency)
                
                if timestamps["first_text_token"]:
                    text_to_audio = (timestamps["first_audio_chunk"] - timestamps["first_text_token"]) * 1000
                    print(f"  文本到音频延迟: {text_to_audio:.2f}ms")
                    self.metrics["text_to_tts_delay"].append(text_to_audio)
            
        except Exception as e:
            print(f"❌ 端到端测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def analyze_bottlenecks(self):
        """分析性能瓶颈"""
        self.print_header("性能瓶颈分析")
        
        if not any(self.metrics.values()):
            print("⚠️  没有测试数据，无法分析瓶颈")
            return
        
        print("\n🔍 延迟分析：")
        
        if self.metrics["llm_first_token"]:
            avg_llm = statistics.mean(self.metrics["llm_first_token"])
            print(f"  LLM首token延迟: {avg_llm:.2f}ms")
        
        if self.metrics["text_to_tts_delay"]:
            avg_text_tts = statistics.mean(self.metrics["text_to_tts_delay"])
            print(f"  文本到TTS延迟: {avg_text_tts:.2f}ms")
        
        if self.metrics["tts_first_chunk"]:
            avg_tts = statistics.mean(self.metrics["tts_first_chunk"])
            print(f"  TTS首音频块延迟: {avg_tts:.2f}ms")
        
        if self.metrics["total_latency"]:
            avg_total = statistics.mean(self.metrics["total_latency"])
            print(f"  端到端延迟: {avg_total:.2f}ms")
        
        print("\n⚡ 性能建议：")
        
        if self.metrics["llm_first_token"]:
            avg_llm = statistics.mean(self.metrics["llm_first_token"])
            if avg_llm > 1000:
                print("  ⚠️  LLM首token延迟较高（>1s），建议：")
                print("     - 检查LLM服务响应时间")
                print("     - 考虑使用更快的模型或优化prompt")
        
        if self.metrics["text_to_tts_delay"]:
            avg_text_tts = statistics.mean(self.metrics["text_to_tts_delay"])
            if avg_text_tts > 500:
                print("  ⚠️  文本到TTS延迟较高（>500ms），建议：")
                print("     - 减小text_stream_queue的buffer_size")
                print("     - 优化SentenceBuffer的分句逻辑")
        
        if self.metrics["tts_first_chunk"]:
            avg_tts = statistics.mean(self.metrics["tts_first_chunk"])
            if avg_tts > 1000:
                print("  ⚠️  TTS首音频块延迟较高（>1s），建议：")
                print("     - 检查TTS模型加载时间")
                print("     - 考虑模型预热")
                print("     - 优化TTS推理速度")
    
    def print_summary(self):
        """打印测试总结"""
        self.print_header("测试总结")
        
        print("\n📊 性能指标汇总：")
        
        if self.metrics["llm_first_token"]:
            print(f"  LLM首token延迟: {statistics.mean(self.metrics['llm_first_token']):.2f}ms")
        
        if self.metrics["llm_token_rate"]:
            print(f"  LLM token速率: {statistics.mean(self.metrics['llm_token_rate']):.2f} tokens/s")
        
        if self.metrics["tts_first_chunk"]:
            print(f"  TTS首音频块延迟: {statistics.mean(self.metrics['tts_first_chunk']):.2f}ms")
        
        if self.metrics["tts_chunk_rate"]:
            print(f"  TTS块生成速率: {statistics.mean(self.metrics['tts_chunk_rate']):.2f} chunks/s")
        
        if self.metrics["total_latency"]:
            print(f"  端到端延迟: {statistics.mean(self.metrics['total_latency']):.2f}ms")
        
        print("\n" + "=" * 70)


async def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("  文本和音频生成性能测试")
    print("=" * 70)
    
    tester = TextAudioPerformanceTester()
    
    # 1. 分析实现方式
    tester.analyze_implementation()
    
    # 2. 测试LLM性能
    await tester.test_llm_stream_performance()
    
    # 3. 测试TTS性能
    await tester.test_text_to_tts_pipeline()
    
    # 4. 测试端到端延迟
    await tester.test_end_to_end_latency()
    
    # 5. 分析瓶颈
    tester.analyze_bottlenecks()
    
    # 6. 打印总结
    tester.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
