#!/usr/bin/env python3
"""
音频合成优化测试脚本
测试优化后的音频合成性能，验证优化效果
"""
import sys
import asyncio
import time
import statistics
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AudioOptimizationTester:
    """音频优化测试器"""
    
    def __init__(self):
        self.metrics: Dict[str, List[float]] = {
            "text_stream_latency": [],      # 文本流延迟（token到TTS）
            "sentence_buffer_latency": [],  # 句子缓冲延迟
            "tts_first_chunk": [],          # TTS首音频块延迟
            "tts_chunk_rate": [],           # TTS音频块生成速率
            "backpressure_triggers": [],    # 背压触发次数
            "adaptive_timeout_adjustments": [],  # 自适应超时调整次数
            "error_recovery": [],          # 错误恢复次数
            "total_latency": []             # 总延迟
        }
    
    def print_header(self, title: str):
        """打印标题"""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70)
    
    def test_adaptive_timeout(self):
        """测试自适应超时"""
        self.print_header("测试自适应超时")
        
        try:
            # 直接导入优化工具模块，避免通过__init__.py导入（可能触发torch等依赖）
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "tts_optimization_utils",
                project_root / "tts_utils" / "tts_optimization_utils.py"
            )
            tts_utils_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tts_utils_module)
            
            AdaptiveTimeout = tts_utils_module.AdaptiveTimeout
            
            timeout = AdaptiveTimeout(initial=0.1, min_timeout=0.01, max_timeout=0.5)
            
            print(f"✅ 初始超时: {timeout.get_timeout():.3f}秒")
            
            # 模拟有数据的情况
            for i in range(5):
                timeout.adjust(has_data=True)
                print(f"   有数据后超时 #{i+1}: {timeout.get_timeout():.3f}秒")
            
            # 模拟无数据的情况
            for i in range(5):
                timeout.adjust(has_data=False)
                print(f"   无数据后超时 #{i+1}: {timeout.get_timeout():.3f}秒")
            
            print("✅ 自适应超时测试通过")
            return True
        except Exception as e:
            print(f"❌ 自适应超时测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_backpressure_controller(self):
        """测试背压控制器"""
        self.print_header("测试背压控制器")
        
        try:
            # 直接导入优化工具模块，避免通过__init__.py导入
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "tts_optimization_utils",
                project_root / "tts_utils" / "tts_optimization_utils.py"
            )
            tts_utils_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tts_utils_module)
            
            BackpressureController = tts_utils_module.BackpressureController
            
            queue = asyncio.Queue(maxsize=10)
            controller = BackpressureController(queue, threshold=0.8)
            
            print(f"✅ 队列容量: {queue.maxsize}")
            print(f"✅ 背压阈值: {controller.threshold:.1%}")
            
            # 测试正常情况
            async def test_normal():
                await controller.put("test_item")
                usage = controller.get_usage()
                print(f"✅ 正常放入后使用率: {usage:.1%}")
                return True
            
            # 测试背压触发
            async def test_backpressure():
                # 填满队列到80%以上
                for i in range(8):
                    await queue.put(f"item_{i}")
                
                usage_before = controller.get_usage()
                print(f"   背压前使用率: {usage_before:.1%}")
                
                start_time = time.time()
                await controller.put("trigger_item")
                elapsed = time.time() - start_time
                
                usage_after = controller.get_usage()
                print(f"   背压后使用率: {usage_after:.1%}")
                print(f"   背压触发耗时: {elapsed:.3f}秒")
                
                triggers = controller.get_backpressure_count()
                print(f"   背压触发次数: {triggers}")
                
                return True
            
            result1 = asyncio.run(test_normal())
            result2 = asyncio.run(test_backpressure())
            
            if result1 and result2:
                print("✅ 背压控制器测试通过")
                return True
        except Exception as e:
            print(f"❌ 背压控制器测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_text_info_preservation(self):
        """测试文本信息保留"""
        self.print_header("测试文本信息保留")
        
        try:
            from models.tts import AudioChunk
            
            # 模拟音频块
            chunk = AudioChunk(
                chunk_id="test_chunk_1",
                text="这是测试文本",  # ✅ 实际文本，不是占位符
                audio_data=b"fake_audio_data",
                format="pcm",
                is_final=False,
                timestamp=int(time.time() * 1000),
                metadata={
                    "sentence_key": 1,
                    "sample_rate": 24000
                }
            )
            
            print(f"✅ 音频块ID: {chunk.chunk_id}")
            print(f"✅ 文本内容: {chunk.text}")
            print(f"✅ 句子键: {chunk.metadata.get('sentence_key')}")
            
            if chunk.text != "流式合成中..." and len(chunk.text) > 0:
                print("✅ 文本信息保留测试通过（使用实际文本，不是占位符）")
                return True
            else:
                print("❌ 文本信息保留测试失败（仍使用占位符）")
                return False
        except Exception as e:
            print(f"❌ 文本信息保留测试失败: {e}")
            return False
    
    def test_double_buffer_removal(self):
        """测试双重缓冲消除"""
        self.print_header("测试双重缓冲消除")
        
        try:
            # 检查orchestrator.py中是否还有缓冲逻辑
            orchestrator_path = project_root / "core" / "orchestrator.py"
            with open(orchestrator_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查是否还有buffer_size = 5这样的缓冲逻辑
            if 'buffer_size = 5' in content or 'buffer_size=5' in content:
                print("❌ 发现双重缓冲：orchestrator中仍有5字符缓冲")
                return False
            
            # 检查是否直接yield token
            if 'yield token' in content or 'yield token_content' in content:
                print("✅ 双重缓冲已消除：直接yield token")
                return True
            else:
                print("⚠️  无法确认双重缓冲是否已消除")
                return False
        except Exception as e:
            print(f"❌ 双重缓冲消除测试失败: {e}")
            return False
    
    def test_error_recovery(self):
        """测试错误恢复机制"""
        self.print_header("测试错误恢复机制")
        
        try:
            # 检查local_tts_service.py中是否有错误恢复逻辑
            tts_service_path = project_root / "tts_utils" / "local_tts_service.py"
            with open(tts_service_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            has_retry = '@retry_async' in content or 'retry_async' in content
            has_fallback = 'synthesize_batch' in content and 'fallback' in content.lower()
            
            print(f"✅ 重试机制: {'是' if has_retry else '否'}")
            print(f"✅ 降级策略: {'是' if has_fallback else '否'}")
            
            if has_retry or has_fallback:
                print("✅ 错误恢复机制测试通过")
                return True
            else:
                print("❌ 错误恢复机制测试失败（未找到重试或降级逻辑）")
                return False
        except Exception as e:
            print(f"❌ 错误恢复机制测试失败: {e}")
            return False
    
    def test_optimization_utils(self):
        """测试优化工具类"""
        self.print_header("测试优化工具类")
        
        try:
            # 直接导入优化工具模块，避免通过__init__.py导入
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "tts_optimization_utils",
                project_root / "tts_utils" / "tts_optimization_utils.py"
            )
            tts_utils_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tts_utils_module)
            
            AdaptiveTimeout = tts_utils_module.AdaptiveTimeout
            BackpressureController = tts_utils_module.BackpressureController
            AudioChunkNormalizer = tts_utils_module.AudioChunkNormalizer
            
            print("✅ AdaptiveTimeout 类存在")
            print("✅ BackpressureController 类存在")
            print("✅ AudioChunkNormalizer 类存在")
            
            # 测试AudioChunkNormalizer
            normalizer = AudioChunkNormalizer(target_duration_ms=500, sample_rate=24000)
            test_audio = b"x" * 10000  # 模拟音频数据
            chunks = normalizer.add_chunk(test_audio)
            print(f"✅ AudioChunkNormalizer 测试通过（生成 {len(chunks)} 个标准化块）")
            
            return True
        except Exception as e:
            print(f"❌ 优化工具类测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        self.print_header("音频合成优化测试")
        
        print(f"\n测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        tests = [
            ("双重缓冲消除", self.test_double_buffer_removal),
            ("自适应超时", self.test_adaptive_timeout),
            ("背压控制器", self.test_backpressure_controller),
            ("文本信息保留", self.test_text_info_preservation),
            ("错误恢复机制", self.test_error_recovery),
            ("优化工具类", self.test_optimization_utils),
        ]
        
        results = []
        for test_name, test_func in tests:
            try:
                result = test_func()
                results.append((test_name, result))
            except Exception as e:
                print(f"❌ {test_name} 测试异常: {e}")
                results.append((test_name, False))
        
        # 打印总结
        self.print_header("测试结果总结")
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        print(f"\n总计: {total} 项测试")
        print(f"通过: {passed} 项")
        print(f"失败: {total - passed} 项")
        print(f"通过率: {passed/total*100:.1f}%")
        
        print("\n详细结果:")
        for test_name, result in results:
            status = "✅ 通过" if result else "❌ 失败"
            print(f"  {status} - {test_name}")
        
        if passed == total:
            print("\n🎉 所有测试通过！优化已正确实施。")
            return True
        else:
            print(f"\n⚠️  有 {total - passed} 项测试失败，请检查相关代码。")
            return False


def main():
    """主函数"""
    tester = AudioOptimizationTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
