#!/usr/bin/env python3
"""
简单测试脚本：发送单次请求并打印每种类型的首尾帧（图片、thinking、content、音频）
"""
import asyncio
import aiohttp
import json
import os
import time
from copy import deepcopy
from typing import Dict, Any, Optional

# 配置
BASE_URL = os.getenv("API_URL", "http://localhost:8080")
QUERY = os.getenv("TEST_QUERY", "今天有什么新闻？")
TIMEOUT = float(os.getenv("TEST_TIMEOUT", "300"))


def detect_frame_type(data: Dict[str, Any]) -> str:
    """根据 response_type / token_type 推断帧类型"""
    response_type = data.get("response_type")
    token_type = data.get("extension", {}).get("token_type")
    frame_text = data.get("frame_text") or ""

    if token_type == "thinking" or response_type == "thinking":
        return "thinking"
    if token_type == "content" or response_type == "text" or (frame_text and not response_type):
        return "content"
    if token_type == "audio" or response_type == "audio":
        return "audio"
    if response_type == "image":
        return "image"
    return response_type or token_type or "unknown"


def summarize_event(event: Dict[str, Any], truncate_audio: bool = True) -> Dict[str, Any]:
    """复制并对音频字段做截断，便于打印"""
    event_copy = deepcopy(event)
    parts = event_copy.get("data", {}).get("frame_parts") or []
    if truncate_audio:
        for part in parts:
            audio = part.get("audio") or {}
            audio_data = audio.get("data") if isinstance(audio, dict) else None
            if audio_data and len(audio_data) > 120:
                part["audio"]["data"] = audio_data[:120] + f"...(len={len(audio_data)})"
    return event_copy


async def main():
    print("=" * 80)
    print("首尾帧测试")
    print(f"API: {BASE_URL}")
    print(f"Query: {QUERY}")
    print("=" * 80)

    first_frames: Dict[str, Optional[Dict[str, Any]]] = {
        "thinking": None,
        "content": None,
        "image": None,
        "audio": None,
    }
    last_frames: Dict[str, Optional[Dict[str, Any]]] = {
        "thinking": None,
        "content": None,
        "image": None,
        "audio": None,
    }

    async with aiohttp.ClientSession() as session:
        payload = {"query": QUERY, "stream": True}
        async with session.post(
            f"{BASE_URL}/api/v1/chat",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT),
        ) as resp:
            if resp.status != 200:
                print(f"请求失败，状态码: {resp.status}")
                return

            buffer = ""
            start_time = time.time()
            stream_done = False
            async for chunk in resp.content.iter_chunked(4096):
                buffer += chunk.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("event:"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue

                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    data = event.get("data") or {}
                    frame_type = detect_frame_type(data)
                    frame_id = data.get("frame_id", "N/A")

                    # 只跟踪目标类型
                    if frame_type in first_frames:
                        if first_frames[frame_type] is None:
                            first_frames[frame_type] = summarize_event(event)
                            elapsed = time.time() - start_time
                            print(f"[首帧][{frame_type}] frame_id={frame_id} t+{elapsed:.2f}s")
                        last_frames[frame_type] = summarize_event(event)
                        # 简单提示每个音频块
                        if frame_type == "audio":
                            print(f"[音频块] frame_id={frame_id}")

                    # 收到最终帧即退出
                    if data.get("frame_is_final"):
                        print("收到最终帧，结束读取。")
                        stream_done = True
                        break
                if stream_done:
                    break
            # 如果 chunk 循环提前结束，再退出外层
            if stream_done:
                pass

    print("\n结果：")
    for t in ["thinking", "content", "image", "audio"]:
        print("-" * 80)
        print(f"{t.upper()} 首帧:")
        if first_frames[t]:
            print(json.dumps(first_frames[t], indent=2, ensure_ascii=False))
        else:
            print("未收到")
        print(f"{t.upper()} 尾帧:")
        if last_frames[t]:
            print(json.dumps(last_frames[t], indent=2, ensure_ascii=False))
        else:
            print("未收到")


if __name__ == "__main__":
    asyncio.run(main())

