#!/usr/bin/env python3
"""
快速性能测试脚本
测试文本和音频生成的实际性能（需要服务运行）
"""
import sys
import asyncio
import time
import requests
import json
from pathlib import Path
from typing import Dict, List

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_streaming_performance(base_url: str = "http://localhost:8080"):
    """测试流式生成性能"""
    print("\n" + "=" * 70)
    print("  流式生成性能测试")
    print("=" * 70)
    
    url = f"{base_url}/api/v1/chat"
    payload = {
        "query": "今天有什么新闻",
        "stream": True,
        "request_id": f"perf_test_{int(time.time())}"
    }
    
    print(f"\n测试查询: {payload['query']}")
    print(f"开始测试...\n")
    
    timestamps = {
        "request_start": time.time(),
        "first_text": None,
        "first_audio": None,
        "request_end": None
    }
    
    frame_stats = {
        "thinking": 0,
        "text": 0,
        "audio": 0,
        "total": 0
    }
    
    try:
        response = requests.post(url, json=payload, stream=True, timeout=60)
        
        if response.status_code != 200:
            print(f"❌ 请求失败: HTTP {response.status_code}")
            return
        
        for line in response.iter_lines():
            if not line:
                continue
            
            line_str = line.decode('utf-8')
            current_time = time.time()
            
            if line_str.startswith("data:"):
                try:
                    data_str = line_str[5:].strip()
                    data = json.loads(data_str)
                    
                    response_data = data.get("data", {})
                    response_type = response_data.get("response_type", "")
                    
                    frame_stats["total"] += 1
                    
                    if response_type == "thinking":
                        frame_stats["thinking"] += 1
                    elif response_type == "text":
                        frame_stats["text"] += 1
                        if timestamps["first_text"] is None:
                            timestamps["first_text"] = current_time
                            latency = (current_time - timestamps["request_start"]) * 1000
                            print(f"  ✅ 首文本token: {latency:.2f}ms")
                    elif response_type == "audio":
                        frame_stats["audio"] += 1
                        if timestamps["first_audio"] is None:
                            timestamps["first_audio"] = current_time
                            latency = (current_time - timestamps["request_start"]) * 1000
                            print(f"  ✅ 首音频块: {latency:.2f}ms")
                    
                    # 检查是否完成
                    if response_data.get("frame_is_final"):
                        timestamps["request_end"] = current_time
                        break
                
                except json.JSONDecodeError:
                    continue
        
        # 计算性能指标
        total_time = timestamps["request_end"] - timestamps["request_start"] if timestamps["request_end"] else 0
        
        print(f"\n📊 性能统计：")
        print(f"  总时间: {total_time:.3f}s")
        print(f"  总帧数: {frame_stats['total']}")
        print(f"  - Thinking帧: {frame_stats['thinking']}")
        print(f"  - 文本帧: {frame_stats['text']}")
        print(f"  - 音频帧: {frame_stats['audio']}")
        
        if timestamps["first_text"]:
            text_latency = (timestamps["first_text"] - timestamps["request_start"]) * 1000
            print(f"  首文本延迟: {text_latency:.2f}ms")
        
        if timestamps["first_audio"]:
            audio_latency = (timestamps["first_audio"] - timestamps["request_start"]) * 1000
            print(f"  首音频延迟: {audio_latency:.2f}ms")
            
            if timestamps["first_text"]:
                text_to_audio = (timestamps["first_audio"] - timestamps["first_text"]) * 1000
                print(f"  文本到音频延迟: {text_to_audio:.2f}ms")
        
        # 性能评估
        print(f"\n📈 性能评估：")
        if timestamps["first_text"]:
            text_latency = (timestamps["first_text"] - timestamps["request_start"]) * 1000
            if text_latency < 1000:
                print(f"  ✅ 首文本延迟良好（{text_latency:.0f}ms < 1000ms）")
            else:
                print(f"  ⚠️  首文本延迟较高（{text_latency:.0f}ms >= 1000ms）")
        
        if timestamps["first_audio"]:
            audio_latency = (timestamps["first_audio"] - timestamps["request_start"]) * 1000
            if audio_latency < 2500:
                print(f"  ✅ 首音频延迟良好（{audio_latency:.0f}ms < 2500ms）")
            else:
                print(f"  ⚠️  首音频延迟较高（{audio_latency:.0f}ms >= 2500ms）")
    
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务，请确保服务正在运行")
        print(f"   服务地址: {base_url}")
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="快速性能测试")
    parser.add_argument(
        "--url",
        default="http://localhost:8080",
        help="服务URL（默认: http://localhost:8080）"
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 70)
    print("  快速性能测试")
    print("=" * 70)
    print(f"\n服务地址: {args.url}")
    print("提示: 确保服务正在运行")
    
    test_streaming_performance(args.url)
    
    print("\n" + "=" * 70)
    print("  测试完成")
    print("=" * 70)
    print("\n💡 更多测试选项：")
    print("  - 详细分析: python3 scripts/analyze_generation_pipeline.py")
    print("  - 完整测试: python3 scripts/test_text_audio_generation.py")


if __name__ == "__main__":
    main()
