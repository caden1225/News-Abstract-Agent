"""
简单测试脚本 - 测试流式和非流式响应
直接发送"今天有哪些新闻"query
"""
import httpx
import json
import asyncio
import time


BASE_URL = "http://localhost:8080"
CHAT_URL = f"{BASE_URL}/api/v1/chat"
QUERY = "今天有哪些新闻"


def create_request(stream: bool) -> dict:
    """创建请求体"""
    return {
        "version": "2.1",
        "request_id": f"test_{int(time.time() * 1000)}",
        "timestamp": int(time.time() * 1000),
        "vin": "TEST",
        "channel_id": "test",
        "query": QUERY,
        "stream": stream
    }


async def test_stream_mode():
    """测试流式响应"""
    print("\n" + "="*60)
    print("🌊 测试流式响应 (stream=true)")
    print("="*60)

    request_data = create_request(stream=True)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                CHAT_URL,
                json=request_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status_code != 200:
                    print(f"❌ 请求失败: {response.status_code}")
                    print(response.text[:500])
                    return False

                print("✅ 开始接收流式响应...\n")

                frame_count = 0
                full_text = ""

                async for line in response.aiter_lines():
                    if not line.strip() or line.startswith("event:"):
                        continue

                    if line.startswith("data:"):
                        json_str = line[5:].strip()
                        try:
                            data = json.loads(json_str)
                            frame_count += 1

                            if "data" in data:
                                response_data = data["data"]
                                is_final = response_data.get("frame_is_final", False)

                                # 显示文本片段
                                if response_data.get("frame_text"):
                                    chunk = response_data["frame_text"]
                                    print(f"📝 片段#{frame_count}: {chunk}")
                                    full_text += chunk

                                # 最终帧
                                if is_final:
                                    print(f"\n✅ 流式响应完成，共 {frame_count} 帧")
                                    if response_data.get("complete_content"):
                                        print(f"📄 完整文本长度: {len(response_data['complete_content'])} 字符")

                                    # 检查音频
                                    parts = response_data.get("frame_parts", [])
                                    if parts:
                                        for part in parts:
                                            if part.get("type") == "audio":
                                                print("🎵 包含音频数据")

                        except json.JSONDecodeError:
                            pass

                print(f"\n{'='*60}")
                return True

    except Exception as e:
        print(f"❌ 流式测试失败: {e}")
        return False


async def test_non_stream_mode():
    """测试非流式响应"""
    print("\n" + "="*60)
    print("📄 测试非流式响应 (stream=false)")
    print("="*60)

    request_data = create_request(stream=False)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                CHAT_URL,
                json=request_data,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code != 200:
                print(f"❌ 请求失败: {response.status_code}")
                print(response.text[:500])
                return False

            print("✅ 接收到完整响应\n")

            # 解析SSE流（非流式也用SSE格式返回）
            frame_count = 0
            final_data = None

            async for line in response.aiter_lines():
                if not line.strip() or line.startswith("event:"):
                    continue

                if line.startswith("data:"):
                    json_str = line[5:].strip()
                    try:
                        data = json.loads(json_str)
                        frame_count += 1

                        if "data" in data:
                            response_data = data["data"]
                            is_final = response_data.get("frame_is_final", False)

                            if is_final:
                                final_data = response_data
                                print(f"📊 接收到最终响应帧")
                                print(f"   帧总数: {frame_count}")

                                if response_data.get("complete_content"):
                                    content = response_data["complete_content"]
                                    print(f"   文本长度: {len(content)} 字符")
                                    print(f"\n📋 完整响应:")
                                    print("-" * 60)
                                    print(content)
                                    print("-" * 60)

                                # 检查音频
                                parts = response_data.get("frame_parts", [])
                                if parts:
                                    for part in parts:
                                        if part.get("type") == "audio":
                                            print("🎵 包含音频数据")

                    except json.JSONDecodeError:
                        pass

            print(f"\n{'='*60}")
            return final_data is not None

    except Exception as e:
        print(f"❌ 非流式测试失败: {e}")
        return False


async def main():
    """主函数"""
    print("\n" + "="*60)
    print("🧪 News TTS Agent 简单测试")
    print(f"📍 服务地址: {BASE_URL}")
    print(f"❓ 测试查询: {QUERY}")
    print("="*60)

    # 先测试流式
    stream_ok = await test_stream_mode()
    await asyncio.sleep(2)

    # 再测试非流式
    non_stream_ok = await test_non_stream_mode()

    # 汇总结果
    print("\n" + "="*60)
    print("📊 测试结果汇总")
    print("="*60)
    print(f"流式响应:   {'✅ 通过' if stream_ok else '❌ 失败'}")
    print(f"非流式响应: {'✅ 通过' if non_stream_ok else '❌ 失败'}")
    print("="*60 + "\n")

    if stream_ok and non_stream_ok:
        print("🎉 所有测试通过!")
    else:
        print("⚠️  部分测试失败，请检查服务状态")


if __name__ == "__main__":
    asyncio.run(main())
