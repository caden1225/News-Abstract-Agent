"""
模拟管理平台测试Agent的chat接口
用于本地测试验证/api/v1/chat接口的正确性
"""
import httpx
import json
import asyncio
import time
from typing import Optional, List


class PlatformTester:
    """模拟管理平台的测试器"""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.chat_url = f"{base_url}/api/v1/chat"

    def create_test_request(
        self,
        query: str,
        stream: bool = True,
        debug: bool = False,
        request_id: Optional[str] = None
    ) -> dict:
        """
        创建符合LLM Protocol 2.1的测试请求

        Args:
            query: 用户查询文本
            stream: 是否使用流式响应
            debug: 是否开启调试模式
            request_id: 自定义请求ID

        Returns:
            符合协议的请求字典
        """
        if request_id is None:
            request_id = f"test_{int(time.time() * 1000)}"

        return {
            "version": "2.1",
            "request_id": request_id,
            "conversation_id": f"conv_{int(time.time())}",
            "timestamp": int(time.time() * 1000),
            "vin": "TEST_VIN_12345678",
            "voice_zone": 0,
            "account_id": "test_account_001",
            "user_id": "test_user_001",
            "channel_id": "test_channel",
            "vehicle_model": "测试车型",
            "query": query,
            "query_parts": [
                {
                    "type": "text",
                    "text": query
                }
            ],
            "history": [],
            "context": {
                "llm_nlu": {
                    "domain": "news",
                    "intent": "news-tts"
                },
                "location": {
                    "latitude": 39.9042,
                    "longitude": 116.4074
                },
                "asr_result": {
                    "language": "zh"
                }
            },
            "stream": stream,
            "debug": debug
        }

    async def test_chat(self, query: str, stream: bool = True, debug: bool = False) -> bool:
        """
        测试chat接口

        Args:
            query: 测试查询
            stream: 是否使用流式响应
            debug: 是否开启调试模式

        Returns:
            测试是否成功
        """
        request_id = f"test_{int(time.time() * 1000)}"
        request_data = self.create_test_request(query, stream, debug, request_id)

        print(f"\n{'='*60}")
        print(f"发送请求: request_id={request_id}")
        print(f"查询内容: {query}")
        print(f"流式模式: {stream}")
        print(f"调试模式: {debug}")
        print(f"{'='*60}\n")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    self.chat_url,
                    json=request_data,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status_code != 200:
                        print(f"❌ 请求失败: status_code={response.status_code}")
                        print(f"响应内容: {response.text[:500]}")
                        return False

                    print("✅ 连接成功，开始接收响应...\n")

                    # 解析SSE流
                    frame_count = 0
                    final_response = None
                    complete_text = ""
                    has_audio = False

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue

                        # SSE格式: event:data\ndata:{json}
                        if line.startswith("event:data"):
                            continue

                        if line.startswith("data:"):
                            json_str = line[5:].strip()  # 移除 "data:" 前缀
                            try:
                                data = json.loads(json_str)
                                frame_count += 1

                                # 检查响应结构
                                if "data" not in data:
                                    print(f"❌ 帧#{frame_count}: 缺少data字段")
                                    print(f"   响应: {json.dumps(data, ensure_ascii=False)[:200]}")
                                    continue

                                response_data = data["data"]
                                is_final = response_data.get("frame_is_final", False)

                                # 显示文本内容
                                if response_data.get("frame_text"):
                                    text_chunk = response_data["frame_text"]
                                    print(f"📝 帧#{frame_count}: {text_chunk}")

                                # 检查是否是最终帧
                                if is_final:
                                    final_response = data
                                    complete_text = response_data.get("complete_content", "")

                                    # 检查音频
                                    frame_parts = response_data.get("frame_parts", [])
                                    if frame_parts:
                                        for part in frame_parts:
                                            if part.get("type") == "audio":
                                                has_audio = True
                                                audio_data = part.get("audio", {})
                                                audio_format = audio_data.get("format", "unknown")
                                                print(f"\n🎵 收到音频: format={audio_format}")
                                                if audio_data.get("data"):
                                                    data_preview = audio_data["data"][:50]
                                                    print(f"   数据预览: {data_preview}...")

                                    # 显示调试信息
                                    if response_data.get("debug_info"):
                                        debug_info = response_data["debug_info"]
                                        total_time = debug_info.get("totalTime", 0)
                                        print(f"\n⏱️  总耗时: {total_time}ms")

                                    # 显示token统计
                                    if response_data.get("usage"):
                                        usage = response_data["usage"]
                                        print(f"📊 Token统计:")
                                        print(f"   输入: {usage.get('input_tokens', 0)}")
                                        print(f"   输出: {usage.get('output_tokens', 0)}")
                                        print(f"   总计: {usage.get('total_tokens', 0)}")

                            except json.JSONDecodeError as e:
                                print(f"❌ JSON解析失败: {e}")
                                print(f"   原始数据: {json_str[:200]}")

                    # 测试结果汇总
                    print(f"\n{'='*60}")
                    print(f"📊 测试结果汇总:")
                    print(f"   总帧数: {frame_count}")
                    print(f"   响应状态: {'✅ 成功' if final_response and final_response.get('code') == 0 else '❌ 失败'}")
                    print(f"   完整文本长度: {len(complete_text)} 字符")
                    print(f"   包含音频: {'✅ 是' if has_audio else '❌ 否'}")
                    print(f"{'='*60}\n")

                    if complete_text:
                        print("📋 完整响应内容:")
                        print("-" * 60)
                        print(complete_text)
                        print("-" * 60)

                    return final_response and final_response.get('code') == 0

        except httpx.ConnectError:
            print(f"❌ 连接失败: 无法连接到 {self.chat_url}")
            print(f"   请确认服务是否已启动: python main.py")
            return False
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False


async def run_test_suite():
    """运行完整测试套件"""
    tester = PlatformTester()

    print("\n" + "="*60)
    print("🧪 News TTS Agent 平台测试套件")
    print("="*60)

    # 测试用例列表
    test_cases = [
        {
            "name": "基础新闻播报测试",
            "query": "今天有什么新闻",
            "stream": True,
            "debug": False
        },
        {
            "name": "热点新闻测试",
            "query": "帮我播报今日热点新闻",
            "stream": True,
            "debug": False
        },
        {
            "name": "调试模式测试",
            "query": "今天的头条新闻是什么",
            "stream": False,
            "debug": True
        }
    ]

    # 运行测试
    results = []
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'🔵'*30}")
        print(f"测试 {i}/{len(test_cases)}: {test_case['name']}")
        print(f"{'🔵'*30}")

        success = await tester.test_chat(
            query=test_case["query"],
            stream=test_case["stream"],
            debug=test_case["debug"]
        )

        results.append({
            "name": test_case["name"],
            "success": success
        })

        # 测试之间稍作等待
        if i < len(test_cases):
            await asyncio.sleep(1)

    # 测试汇总
    print(f"\n{'='*60}")
    print("📈 测试套件汇总")
    print(f"{'='*60}")

    passed = sum(1 for r in results if r["success"])
    total = len(results)

    for result in results:
        status = "✅ 通过" if result["success"] else "❌ 失败"
        print(f"{status} - {result['name']}")

    print(f"\n通过率: {passed}/{total} ({passed*100//total if total > 0 else 0}%)")
    print(f"{'='*60}\n")

    return passed == total


if __name__ == "__main__":
    # 检查命令行参数
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "single":
            # 单个测试: python test_platform_chat.py single "查询内容"
            query = sys.argv[2] if len(sys.argv) > 2 else "今天有什么新闻"
            tester = PlatformTester()
            asyncio.run(tester.test_chat(query, stream=True, debug=True))
        else:
            print("用法:")
            print("  python test_platform_chat.py          # 运行完整测试套件")
            print("  python test_platform_chat.py single '查询内容'  # 单个测试")
    else:
        # 运行完整测试套件
        success = asyncio.run(run_test_suite())
        sys.exit(0 if success else 1)
