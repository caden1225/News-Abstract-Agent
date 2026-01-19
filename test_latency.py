"""
测试脚本：通过调用本地服务API测试各阶段的延时
通过解析SSE流式响应来判断当前处于哪个阶段
"""
import asyncio
import aiohttp
import json
import time
import logging
import os
from typing import Dict, Optional, List
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置
BASE_URL = os.getenv("API_URL", "http://localhost:8080")
TIMEOUT = 300  # 5分钟超时


class StageDetector:
    """阶段检测器 - 根据响应判断当前阶段"""
    
    def __init__(self):
        self.stages = {
            "preprocessing": "前置处理（意图分析+数据获取+新闻选择）",
            "image_delivery": "图片交付",
            "thinking": "思考阶段（LLM思考）",
            "text_generation": "文本生成（LLM摘要）",
            "tts_generation": "TTS音频生成",
            "final": "最终响应"
        }
        
        # 阶段状态
        self.stage_times: Dict[str, Dict] = {}
        self.current_stage: Optional[str] = None
        self.stage_start_time: Optional[float] = None
        
        # 标志位
        self.has_seen_image = False
        self.has_seen_thinking = False
        self.has_seen_text = False
        self.has_seen_audio = False
        self.has_seen_final = False
        
    def detect_stage(self, event: Dict) -> Optional[str]:
        """
        根据响应事件检测当前阶段
        
        逻辑：分析每个帧中是否有文本和音频
        - 当第一次出现文本帧时，标记为文本生成阶段开始
        - 当第一次出现音频帧时，标记为TTS音频生成阶段开始
        """
        data = event.get("data", {})
        if not data:
            return None
        
        response_type = data.get("response_type", "")
        frame_is_final = data.get("frame_is_final", False)
        frame_parts = data.get("frame_parts", [])
        extension = data.get("extension", {})
        token_type = extension.get("token_type", "")
        
        # 最终帧（优先级最高）
        if frame_is_final:
            if not self.has_seen_final:
                self.has_seen_final = True
                return "final"
        
        # 图片阶段（通常在第一个响应中）
        if frame_parts:
            for part in frame_parts:
                if isinstance(part, dict) and part.get("type") == "image":
                    if not self.has_seen_image:
                        self.has_seen_image = True
                        return "image_delivery"
        
        # 检查是否有图片链接
        if extension.get("image_count", 0) > 0 and not self.has_seen_image:
            self.has_seen_image = True
            return "image_delivery"
        
        # 检测文本帧（优先检测，因为文本生成应该在音频之前或同时开始）
        # 文本帧的判断：response_type="text" 或 token_type="content"
        has_text = (response_type == "text" or token_type == "content")
        
        # 检测音频帧
        # 音频帧的判断：response_type="audio" 或 token_type="audio" 或 frame_parts中包含audio
        has_audio = False
        if response_type == "audio" or token_type == "audio":
            has_audio = True
        elif frame_parts:
            for part in frame_parts:
                if isinstance(part, dict) and part.get("type") == "audio":
                    has_audio = True
                    break
        
        # Thinking阶段（只在没有文本和音频时检测，避免干扰）
        if not has_text and not has_audio:
            if response_type == "thinking" or token_type == "thinking":
                if not self.has_seen_thinking:
                    self.has_seen_thinking = True
                    return "thinking"
        
        # 文本生成阶段：第一次出现文本帧时开始
        if has_text:
            if not self.has_seen_text:
                self.has_seen_text = True
                return "text_generation"
        
        # TTS音频生成阶段：第一次出现音频帧时开始
        if has_audio:
            if not self.has_seen_audio:
                self.has_seen_audio = True
                return "tts_generation"
        
        return None
    
    def start_stage(self, stage: str, timestamp: float):
        """开始一个阶段"""
        if self.current_stage and self.current_stage != stage:
            # 结束上一个阶段
            self.end_stage(timestamp)
        
        if stage not in self.stage_times:
            self.stage_times[stage] = {
                "start": timestamp,
                "end": None,
                "duration": 0.0,
                "first_frame_time": timestamp
            }
        else:
            # 如果阶段已存在，更新开始时间（取最早的）
            if self.stage_times[stage]["start"] is None or timestamp < self.stage_times[stage]["start"]:
                self.stage_times[stage]["start"] = timestamp
                self.stage_times[stage]["first_frame_time"] = timestamp
        
        self.current_stage = stage
        self.stage_start_time = timestamp
    
    def end_stage(self, timestamp: float):
        """结束当前阶段"""
        if self.current_stage and self.stage_start_time:
            duration = timestamp - self.stage_start_time
            if self.current_stage in self.stage_times:
                self.stage_times[self.current_stage]["end"] = timestamp
                self.stage_times[self.current_stage]["duration"] += duration
            
            logger.info(f"✅ 阶段完成: {self.stages.get(self.current_stage, self.current_stage)}, 耗时: {duration:.3f}秒")
        
        self.current_stage = None
        self.stage_start_time = None
    
    def get_report(self, total_time: float) -> str:
        """生成延时报告"""
        if not self.stage_times:
            return "无阶段数据"
        
        report = []
        report.append("\n" + "=" * 80)
        report.append("阶段延时报告（基于API响应）")
        report.append("=" * 80)
        report.append(f"总耗时: {total_time:.3f}秒")
        report.append("-" * 80)
        report.append(f"{'阶段':<40} {'开始时间(秒)':<15} {'持续时间(秒)':<15} {'占比':<10}")
        report.append("-" * 80)
        
        # 按开始时间排序
        sorted_stages = sorted(
            self.stage_times.items(),
            key=lambda x: x[1]["start"] if x[1]["start"] else 0
        )
        
        for stage_name, timing in sorted_stages:
            stage_display = self.stages.get(stage_name, stage_name)
            start_time = timing["start"] if timing["start"] else 0
            duration = timing["duration"] if timing["duration"] > 0 else 0
            percentage = (duration / total_time * 100) if total_time > 0 else 0
            
            report.append(
                f"{stage_display:<40} "
                f"{start_time:<15.3f} "
                f"{duration:<15.3f} "
                f"{percentage:<10.1f}%"
            )
        
        report.append("=" * 80)
        
        return "\n".join(report)


class LatencyTester:
    """延时测试器"""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def test_query(
        self,
        query: str,
        request_id: Optional[str] = None
    ) -> Dict:
        """测试单个查询的延时"""
        if not request_id:
            request_id = f"test_{int(time.time())}"
        
        logger.info(f"\n{'='*80}")
        logger.info(f"开始测试查询")
        logger.info(f"查询: {query}")
        logger.info(f"请求ID: {request_id}")
        logger.info(f"{'='*80}\n")
        
        detector = StageDetector()
        overall_start = time.time()
        request_start = time.time()
        
        # 记录请求开始时间（前置处理阶段）
        detector.start_stage("preprocessing", request_start)
        
        stats = {
            "total_frames": 0,
            "thinking_frames": 0,
            "text_frames": 0,
            "audio_frames": 0,
            "image_frames": 0,
            "final_frame": False
        }
        
        try:
            payload = {
                "query": query,
                "stream": True
            }
            
            async with self.session.post(
                f"{self.base_url}/api/v1/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            ) as resp:
                if resp.status != 200:
                    error_msg = f"HTTP错误: {resp.status}"
                    logger.error(error_msg)
                    return {
                        "success": False,
                        "error": error_msg,
                        "total_time": time.time() - overall_start
                    }
                
                # 读取流式响应
                buffer = ""
                first_response_time = None
                preprocessing_duration = 0.0
                
                async for chunk in resp.content.iter_any():
                    if not chunk:
                        continue
                    
                    buffer += chunk.decode("utf-8", errors="ignore")
                    
                    # 按行处理缓冲区
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        
                        if not line or not line.startswith("data:"):
                            continue
                        
                        data_str = line[5:].strip()
                        if data_str in ("", "[DONE]"):
                            continue
                        
                        try:
                            event = json.loads(data_str)
                            current_time = time.time()
                            
                            # 记录第一个响应的时间（前置处理结束）
                            if first_response_time is None:
                                first_response_time = current_time
                                preprocessing_duration = first_response_time - request_start
                                detector.end_stage(current_time)
                                logger.info(f"✅ 前置处理完成，耗时: {preprocessing_duration:.3f}秒")
                            
                            stats["total_frames"] += 1
                            
                            # 检查错误
                            code = event.get("code", 0)
                            if code != 0:
                                message = event.get("message", "")
                                logger.warning(f"收到错误响应: code={code}, message={message}")
                                continue
                            
                            # 检测阶段
                            detected_stage = detector.detect_stage(event)
                            if detected_stage:
                                detector.start_stage(detected_stage, current_time)
                            
                            # 统计帧类型
                            data = event.get("data", {})
                            if data:
                                response_type = data.get("response_type", "")
                                frame_parts = data.get("frame_parts", [])
                                extension = data.get("extension", {})
                                token_type = extension.get("token_type", "")
                                
                                if response_type == "thinking" or token_type == "thinking":
                                    stats["thinking_frames"] += 1
                                elif response_type == "text" or token_type == "content":
                                    stats["text_frames"] += 1
                                elif response_type == "audio" or token_type == "audio":
                                    stats["audio_frames"] += 1
                                elif response_type == "image":
                                    stats["image_frames"] += 1
                                
                                # 检查frame_parts
                                if frame_parts:
                                    for part in frame_parts:
                                        if isinstance(part, dict):
                                            part_type = part.get("type", "")
                                            if part_type == "image":
                                                stats["image_frames"] += 1
                                            elif part_type == "audio":
                                                stats["audio_frames"] += 1
                                
                                if data.get("frame_is_final", False):
                                    stats["final_frame"] = True
                                    detector.end_stage(current_time)
                            
                        except json.JSONDecodeError as e:
                            logger.debug(f"JSON解析失败: {e}")
                            continue
                
                # 确保所有阶段都已结束
                final_time = time.time()
                detector.end_stage(final_time)
                
                total_time = final_time - overall_start
                
                # 生成报告
                report = detector.get_report(total_time)
                
                logger.info(f"\n统计信息:")
                logger.info(f"  - 总帧数: {stats['total_frames']}")
                logger.info(f"  - Thinking帧: {stats['thinking_frames']}")
                logger.info(f"  - Text帧: {stats['text_frames']}")
                logger.info(f"  - Audio帧: {stats['audio_frames']}")
                logger.info(f"  - Image帧: {stats['image_frames']}")
                logger.info(f"  - 最终帧: {stats['final_frame']}")
                
                print(report)
                
                return {
                    "success": True,
                    "total_time": total_time,
                    "preprocessing_time": preprocessing_duration,
                    "stats": stats,
                    "stage_times": detector.stage_times,
                    "report": report
                }
        
        except asyncio.TimeoutError:
            total_time = time.time() - overall_start
            logger.error(f"请求超时: {total_time:.2f}秒")
            return {
                "success": False,
                "error": "请求超时",
                "total_time": total_time
            }
        except Exception as e:
            total_time = time.time() - overall_start
            logger.error(f"测试失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "total_time": total_time
            }


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="通过API测试各阶段延时")
    parser.add_argument(
        "--query",
        type=str,
        default="今天有什么新闻",
        help="测试查询（默认：今天有什么新闻）"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="测试次数（默认：1）"
    )
    parser.add_argument(
        "--url",
        type=str,
        default=BASE_URL,
        help=f"API服务地址（默认：{BASE_URL}）"
    )
    
    args = parser.parse_args()
    
    # 检查服务是否可用
    print("\n🔍 检查服务状态...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{args.url}/health",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    print("✅ 服务运行正常")
                else:
                    print(f"⚠️  服务状态异常: {resp.status}")
                    return
    except Exception as e:
        print(f"❌ 无法连接到服务: {e}")
        print(f"\n💡 请先启动服务:")
        print(f"   python3 main.py")
        return
    
    print("\n" + "=" * 80)
    print("新闻TTS Agent - API延时测试工具")
    print("=" * 80)
    print(f"API地址: {args.url}")
    print(f"测试查询: {args.query}")
    print(f"测试次数: {args.count}")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80 + "\n")
    
    results = []
    
    async with LatencyTester(args.url) as tester:
        for i in range(args.count):
            if i > 0:
                logger.info(f"\n等待 2 秒后开始下一次测试...")
                await asyncio.sleep(2)
            
            result = await tester.test_query(
                query=args.query,
                request_id=f"test_{i+1}_{int(time.time())}"
            )
            results.append(result)
    
    # 汇总报告
    if args.count > 1:
        print("\n" + "=" * 80)
        print("汇总报告")
        print("=" * 80)
        
        successful_tests = [r for r in results if r.get("success")]
        if successful_tests:
            total_times = [r["total_time"] for r in successful_tests]
            avg_time = sum(total_times) / len(total_times)
            min_time = min(total_times)
            max_time = max(total_times)
            
            print(f"成功测试: {len(successful_tests)}/{args.count}")
            print(f"平均总耗时: {avg_time:.3f}秒")
            print(f"最小耗时: {min_time:.3f}秒")
            print(f"最大耗时: {max_time:.3f}秒")
        
        print("=" * 80)
    
    print(f"\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
