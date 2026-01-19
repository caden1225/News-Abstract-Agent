#!/usr/bin/env python3
"""
快速测试 - 验证服务配置
"""
import asyncio
import requests
import json
from pathlib import Path

async def test_service():
    """测试服务配置"""
    print("=" * 60)
    print("测试TTS服务配置")
    print("=" * 60)

    # 短文本测试
    test_query = "简单测试"

    print(f"\n测试查询: {test_query}")

    url = "http://localhost:8080/api/v1/chat"
    headers = {"Content-Type": "application/json"}
    data = {
        "query": test_query,
        "stream": True
    }

    print("\n发送请求...")

    try:
        response = requests.post(url, json=data, headers=headers, stream=True, timeout=60)
        response.raise_for_status()

        audio_chunks = []
        text_chunks = []
        total_frames = 0

        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data:'):
                    json_str = line[5:].strip()
                    try:
                        data_obj = json.loads(json_str)

                        if 'data' in data_obj:
                            response_data = data_obj['data']
                            total_frames += 1

                            # 收集文本
                            if response_data.get('frame_text'):
                                text_chunks.append(response_data['frame_text'])

                            # 收集音频
                            if response_data.get('frame_parts'):
                                for part in response_data['frame_parts']:
                                    if part.get('type') == 'audio':
                                        audio_data = part.get('audio', {}).get('data', '')
                                        if audio_data.startswith('data:;base64,'):
                                            audio_data = audio_data.split(',', 1)[1]
                                        audio_chunks.append(audio_data)

                            # 检查是否完成
                            if response_data.get('frame_is_final') and response_data.get('response_type') == 'final':
                                break

                    except json.JSONDecodeError:
                        pass

        print(f"\n✅ 收到响应:")
        print(f"  总帧数: {total_frames}")
        print(f"  文本块数: {len(text_chunks)}")
        print(f"  音频块数: {len(audio_chunks)}")

        if audio_chunks:
            import base64
            total_bytes = sum(len(base64.b64decode(a)) for a in audio_chunks)
            duration = total_bytes / 2 / 24000
            print(f"  音频总时长: {duration:.2f} 秒")
            print(f"  音频总大小: {total_bytes} 字节")

            # 评估
            expected_duration = len(''.join(text_chunks)) * 0.3
            ratio = duration / expected_duration if expected_duration > 0 else 0

            print(f"\n评估:")
            print(f"  预估时长: {expected_duration:.2f} 秒")
            print(f"  实际时长: {duration:.2f} 秒")
            print(f"  比值: {ratio:.2f}x")

            if ratio < 1.2:
                print(f"  ✅ 配置正确 (token_hop_len=50 已生效)")
            elif ratio < 1.5:
                print(f"  ⚠️  比值略高 (token_hop_len可能还是30)")
            else:
                print(f"  ❌ 配置未生效 (token_hop_len可能还是15)")

            print(f"\n💡 测试样本已保存")

            # 保存测试样本
            import wave
            output_path = Path("test_output/service_test_sample.wav")
            output_path.parent.mkdir(exist_ok=True)

            with wave.open(str(output_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(24000)
                for audio_base64 in audio_chunks:
                    audio_bytes = base64.b64decode(audio_base64)
                    wav_file.writeframes(audio_bytes)

            print(f"   文件: {output_path}")
            print(f"   播放: ffplay {output_path}")
        else:
            print(f"  ❌ 未收到音频块")

    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_service())
