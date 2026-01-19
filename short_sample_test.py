#!/usr/bin/env python3
"""
生成短语音测试样本
"""
import asyncio
import requests
import json
import base64
import wave
from pathlib import Path

async def generate_short_sample():
    """生成短语音样本"""
    print("生成短语音测试样本...")

    # 使用更短的测试文本
    test_queries = [
        "你好",
        "测试",
        "今天"
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n{i}. 测试: '{query}'")

        url = "http://localhost:8080/api/v1/chat"
        headers = {"Content-Type": "application/json"}
        data = {
            "query": query,
            "stream": True
        }

        try:
            response = requests.post(url, json=data, headers=headers, stream=True, timeout=30)
            response.raise_for_status()

            audio_chunks = []
            text_content = ""

            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data:'):
                        json_str = line[5:].strip()
                        try:
                            data_obj = json.loads(json_str)
                            if 'data' in data_obj:
                                response_data = data_obj['data']

                                # 收集文本
                                if response_data.get('frame_text'):
                                    text_content += response_data['frame_text']

                                # 收集音频
                                if response_data.get('frame_parts'):
                                    for part in response_data['frame_parts']:
                                        if part.get('type') == 'audio':
                                            audio_data = part.get('audio', {}).get('data', '')
                                            if audio_data.startswith('data:;base64,'):
                                                audio_data = audio_data.split(',', 1)[1]
                                            audio_chunks.append(audio_data)

                                # 检查完成
                                if response_data.get('frame_is_final') and response_data.get('response_type') == 'final':
                                    break

                        except json.JSONDecodeError:
                            pass

            if audio_chunks:
                # 合并音频
                all_audio = b''.join(base64.b64decode(a) for a in audio_chunks)
                duration = len(all_audio) / 2 / 24000

                print(f"  音频时长: {duration:.2f} 秒")
                print(f"  文本内容: {text_content[:50]}...")

                # 保存
                output_path = Path(f"test_output/sample_{i}_{query}.wav")
                with wave.open(str(output_path), "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(24000)
                    wav_file.writeframes(all_audio)

                print(f"  ✅ 保存: {output_path}")

        except Exception as e:
            print(f"  ❌ 失败: {e}")

    print(f"\n✅ 测试样本已生成")
    print(f"\n播放测试:")
    print(f"  ffplay test_output/sample_1_你好.wav")
    print(f"  ffplay test_output/sample_2_测试.wav")
    print(f"  ffplay test_output/sample_3_今天.wav")

if __name__ == "__main__":
    asyncio.run(generate_short_sample())
