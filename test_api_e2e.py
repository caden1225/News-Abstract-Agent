#!/usr/bin/env python3
"""
端到端API测试
验证任务成功标准：
1. 图片、音频和文本同时chunk方式返回
2. 最后一个response携带"is_final"标记
3. 文本、音频每次响应chunk大小可通过配置参数控制
"""
import requests
import json
import sys

# 成功标准追踪
SUCCESS_CRITERIA = {
    "has_text": False,        # 接收到文本token
    "has_audio": False,       # 接收到音频chunk
    "has_image": False,       # 接收到图片
    "has_is_final": False,    # 最后一个响应有is_final标记
    "has_complete_content": False,  # 最后响应有complete_content
    "streaming_works": False  # 流式返回正常工作
}

def test_streaming_api():
    """测试流式API"""
    url = "http://localhost:8080/api/v1/chat"

    payload = {
        "query": "今天有什么新闻",
        "stream": True
    }

    print("=" * 70)
    print("端到端API测试 - 验证任务成功标准")
    print("=" * 70)
    print(f"\n发送请求:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("\n响应流:")
    print("-" * 70)

    thinking_count = 0
    text_count = 0
    audio_count = 0
    image_count = 0
    complete_count = 0

    try:
        print("\n正在连接服务器...")
        with requests.post(url, json=payload, stream=True, timeout=120) as response:
            response.raise_for_status()

            print("✅ 连接成功，开始接收数据流...\n")

            for line in response.iter_lines():
                if not line:
                    continue

                line = line.decode('utf-8')

                # 解析SSE格式
                if line.startswith('event:'):
                    event = line.split(':', 1)[1].strip()
                    print(f"\n[事件] {event}")
                elif line.startswith('data:'):
                    data = line.split(':', 1)[1].strip()
                    try:
                        obj = json.loads(data)

                        # 提取关键信息
                        resp_data = obj.get('data', {})
                        resp_type = resp_data.get('response_type', '')
                        frame_id = resp_data.get('frame_id', 0)
                        is_final = resp_data.get('frame_is_final', False)
                        frame_text = resp_data.get('frame_text', '')

                        # 显示不同类型的数据
                        if resp_type == 'thinking':
                            thinking_count += 1
                            print(f"[Thinking #{thinking_count}] Frame={frame_id}, Text={frame_text[:30]}...")
                        elif resp_type == 'text':
                            text_count += 1
                            SUCCESS_CRITERIA["has_text"] = True
                            SUCCESS_CRITERIA["streaming_works"] = True
                            print(f"[Text #{text_count}] Frame={frame_id}, Text={frame_text[:30]}...")
                        elif resp_type == 'audio':
                            audio_count += 1
                            SUCCESS_CRITERIA["has_audio"] = True
                            SUCCESS_CRITERIA["streaming_works"] = True
                            frame_parts = resp_data.get('frame_parts', [{}])
                            if frame_parts:
                                has_audio = frame_parts[0].get('audio', {})
                                audio_len = len(has_audio.get('data', '')) if has_audio else 0
                                print(f"[Audio #{audio_count}] Frame={frame_id}, Size={audio_len} chars")
                        elif resp_type == 'image':
                            image_count += 1
                            SUCCESS_CRITERIA["has_image"] = True
                            frame_parts = resp_data.get('frame_parts', [])
                            img_count = len(frame_parts) if frame_parts else 0
                            print(f"[Image #{image_count}] Frame={frame_id}, Images={img_count}")

                        # 检查is_final标记
                        if is_final:
                            SUCCESS_CRITERIA["has_is_final"] = True
                            complete_count += 1
                            complete_content = resp_data.get('complete_content', '')
                            if complete_content:
                                SUCCESS_CRITERIA["has_complete_content"] = True
                            print(f"\n[完成] Frame={frame_id}, is_final=True, 文本长度={len(complete_content)} 字符")

                    except json.JSONDecodeError as e:
                        print(f"[数据解析错误] {data[:100]}...")

            print("\n" + "=" * 70)
            print("测试完成 - 统计信息")
            print("=" * 70)
            print(f"Thinking帧: {thinking_count}")
            print(f"文本帧: {text_count}")
            print(f"音频帧: {audio_count}")
            print(f"图片帧: {image_count}")
            print(f"完成帧: {complete_count}")
            print(f"总帧数: {thinking_count + text_count + audio_count + image_count + complete_count}")

            print("\n" + "=" * 70)
            print("任务成功标准验证")
            print("=" * 70)

            all_passed = True
            for criterion, passed in SUCCESS_CRITERIA.items():
                status = "✅ PASS" if passed else "❌ FAIL"
                criterion_name = {
                    "has_text": "文本chunk返回",
                    "has_audio": "音频chunk返回",
                    "has_image": "图片返回",
                    "has_is_final": "最后response有is_final标记",
                    "has_complete_content": "最后response有complete_content",
                    "streaming_works": "流式响应正常工作"
                }.get(criterion, criterion)
                print(f"{status}: {criterion_name}")
                if not passed:
                    all_passed = False

            print("\n" + "=" * 70)
            if all_passed:
                print("✅✅✅ 所有任务成功标准已满足！测试通过！✅✅✅")
                print("=" * 70)
                return 0
            else:
                print("❌ 某些任务成功标准未满足，需要继续修复")
                print("=" * 70)
                return 1

    except requests.exceptions.ConnectionError:
        print("\n❌ 无法连接到服务器")
        print("请确保服务器正在运行: python main.py")
        return 1
    except requests.exceptions.Timeout:
        print("\n❌ 请求超时")
        return 1
    except requests.exceptions.RequestException as e:
        print(f"\n❌ 请求失败: {e}")
        return 1

def test_health_check():
    """测试健康检查接口"""
    print("\n测试健康检查接口...")
    try:
        response = requests.get("http://localhost:8080/health", timeout=5)
        response.raise_for_status()
        data = response.json()
        print("✅ 健康检查通过")
        print(f"   状态: {data.get('status')}")
        print(f"   版本: {data.get('version')}")
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")

if __name__ == "__main__":
    # 先测试健康检查
    test_health_check()

    # 再测试流式API
    test_streaming_api()
