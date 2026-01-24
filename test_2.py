#!/usr/bin/env python3
"""
测试脚本：测试"今天有什么新闻？"查询
- 打印所有文本内容
- 打印所有图片链接
- 合并所有音频块为一个音频文件
"""
import asyncio
import aiohttp
import json
import os
import sys
import time
import base64
import wave
from pathlib import Path
from typing import List, Dict, Any

# ==================== 配置 ====================

BASE_URL = os.getenv("API_URL", "http://localhost:8080")
TIMEOUT = 300  # 秒
AUDIO_SAMPLE_RATE = 24000  # 音频采样率（Hz）
AUDIO_CHANNELS = 1  # 单声道
AUDIO_SAMPLE_WIDTH = 2  # 16位 = 2字节
# QUERY = "今天有什么新闻？用韩语播一下"
QUERY = "今天有什么新闻？"

# ==================== 主函数 ====================

async def test_news_query():
    """测试新闻查询"""
    print("=" * 80)
    print(f"测试查询: {QUERY}")
    print("=" * 80)
    print(f"API地址: {BASE_URL}")
    print(f"超时设置: {TIMEOUT}秒")
    print()
    
    # 创建输出目录
    output_dir = Path("test_output")
    output_dir.mkdir(exist_ok=True)
    print(f"📁 输出目录: {output_dir.absolute()}")
    print()
    
    # 存储所有收集的数据
    all_texts = []  # 所有文本内容
    all_image_links = []  # 所有图片链接
    all_audio_chunks = []  # 所有音频块（PCM字节数据）
    audio_chunk_sizes = []  # 每个音频块的大小（字节）
    
    # 统计信息
    stats = {
        "thinking_frames": 0,
        "text_frames": 0,
        "audio_frames": 0,
        "image_frames": 0,
        "total_frames": 0,
        "final_frame": False
    }
    
    # 响应时间记录
    first_text_time = None  # 第一个播报文本的时间戳
    first_audio_time = None  # 第一个音频的时间戳
    
    # 跟踪每种类型的第一个响应是否已打印
    first_responses_printed = {
        "thinking": False,
        "text": False,
        "audio": False,
        "image": False,
        "final": False
    }
    
    start_time = time.time()
    timestamp = int(start_time)
    safe_query = "".join(c for c in QUERY[:20] if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_query = safe_query.replace(' ', '_') if safe_query else "news"
    output_basename = f"{safe_query}_{timestamp}"
    
    final_frame_event = None  # 保存最终帧的完整内容
    last_text_frame_event = None   # 保存最后一个文本帧
    last_audio_frame_event = None  # 保存最后一个音频帧
    
    # 处理按 frame_id 有序输出
    pending_events = {}
    next_frame_id = 0

    def process_event(event):
        nonlocal first_text_time, first_audio_time, stream_complete, last_data_time, has_received_audio, last_text_frame_time
        nonlocal last_audio_frame_event, last_text_frame_event, final_frame_event
        nonlocal accumulated_thinking, accumulated_text
        nonlocal stats, all_audio_chunks, audio_chunk_sizes
        nonlocal all_audio_chunks, audio_chunk_sizes

        data = event.get("data", {})
        if not data:
            return

        frame_id = data.get("frame_id", 0)
        response_type = data.get("response_type", "")
        frame_is_final = data.get("frame_is_final", False)
        frame_parts = data.get("frame_parts", [])
        extension = data.get("extension", {})

        delta_content = data.get("delta_content", "")
        frame_text = data.get("frame_text", "")
        content_field = data.get("content", "")
        token_type = extension.get("token_type", "")

        is_audio_frame = response_type == "audio" or token_type == "audio"
        is_thinking_frame = response_type == "thinking" or token_type == "thinking"
        is_text_frame = (
            response_type == "text" or
            token_type == "content" or
            (frame_text and response_type == "text")
        )
        is_image_frame = response_type == "image"

        # 处理 FINAL 类型
        if frame_is_final and not first_responses_printed["final"]:
            first_responses_printed["final"] = True
            print("\n" + "=" * 80)
            print("📋 第一个 FINAL 类型响应（完整JSON）")
            print("=" * 80)
            print(json.dumps(event, indent=2, ensure_ascii=False))
            print("=" * 80 + "\n")

        if is_thinking_frame and not first_responses_printed["thinking"]:
            first_responses_printed["thinking"] = True
            print("\n" + "=" * 80)
            print("📋 第一个 THINKING 类型响应（完整JSON）")
            print("=" * 80)
            print(json.dumps(event, indent=2, ensure_ascii=False))
            print("=" * 80 + "\n")

        if is_image_frame and not first_responses_printed["image"]:
            first_responses_printed["image"] = True
            print("\n" + "=" * 80)
            print("📋 第一个 IMAGE 类型响应（完整JSON）")
            print("=" * 80)
            print(json.dumps(event, indent=2, ensure_ascii=False))
            print("=" * 80 + "\n")

        if stats["total_frames"] % 10 == 0 or frame_is_final or is_audio_frame:
            print(f"[调试] Frame #{frame_id}: type={response_type}, token_type={token_type}, final={frame_is_final}, parts={len(frame_parts) if frame_parts else 0}", flush=True)

        if is_audio_frame:
            last_audio_frame_event = json.loads(json.dumps(event))
            if frame_parts and isinstance(frame_parts, list):
                for part in frame_parts:
                    if not isinstance(part, dict):
                        continue
                    part_type = part.get("type", "")
                    if part_type == "audio":
                        stats["audio_frames"] += 1
                        audio_info = part.get("audio", {})
                        if isinstance(audio_info, dict):
                            audio_data_str = audio_info.get("data", "")
                            if audio_data_str:
                                try:
                                    if first_audio_time is None:
                                        first_audio_time = time.time()
                                    if audio_data_str.startswith("data:;base64,"):
                                        base64_data = audio_data_str[13:]
                                    elif audio_data_str.startswith("data:audio/pcm;base64,"):
                                        base64_data = audio_data_str[22:]
                                    else:
                                        base64_data = audio_data_str
                                    audio_bytes = base64.b64decode(base64_data)
                                    if audio_bytes:
                                        chunk_size = len(audio_bytes)
                                        all_audio_chunks.append(audio_bytes)
                                        audio_chunk_sizes.append(chunk_size)
                                        has_received_audio = True
                                        print(f"🔊 收到音频块 (Frame #{frame_id}): {chunk_size} 字节", flush=True)
                                except Exception as e:
                                    print(f"⚠️  解码音频数据失败: {e}", flush=True)
            else:
                print(f"⚠️  音频帧 Frame #{frame_id} 没有 frame_parts", flush=True)

        if is_thinking_frame and not is_audio_frame:
            stats["thinking_frames"] += 1
            thinking_text = (
                delta_content
                if delta_content
                else (content_field or frame_text)
            )
            if thinking_text:
                accumulated_thinking += thinking_text
                all_texts.append(("thinking", thinking_text))
                print(f"[思考帧 #{frame_id}] {thinking_text}", flush=True)

        if is_text_frame and not is_thinking_frame and not is_audio_frame:
            last_text_frame_event = json.loads(json.dumps(event))
            stats["text_frames"] += 1
            text_to_display = (
                delta_content
                if delta_content
                else (content_field or frame_text)
            )
            if text_to_display:
                if first_text_time is None:
                    first_text_time = time.time()
                last_text_frame_time = time.time()
                accumulated_text += text_to_display
                all_texts.append(("text", text_to_display))
                print(f"[文本帧 #{frame_id}] {text_to_display}", flush=True)

        if content_field and not is_thinking_frame and not is_text_frame and not is_audio_frame:
            all_texts.append(("frame_text", content_field))
        elif frame_text and not is_thinking_frame and not is_text_frame and not is_audio_frame:
            all_texts.append(("frame_text", frame_text))
            print(f"[其他文本帧 #{frame_id}] {frame_text}", flush=True)

        if frame_parts and isinstance(frame_parts, list):
            for part in frame_parts:
                if not isinstance(part, dict):
                    continue
                part_type = part.get("type", "")
                if part_type == "image":
                    stats["image_frames"] += 1
                    image_info = part.get("image", {})
                    if isinstance(image_info, dict):
                        image_data = image_info.get("data", "")
                        if image_data:
                            all_image_links.append(image_data)
                            print(f"🖼️  收到图片链接 (Frame #{frame_id}): {image_data}", flush=True)

        if frame_is_final:
            stats["final_frame"] = True
            final_frame_event = event
            complete_content = data.get("complete_content", "")
            if complete_content:
                accumulated_text = complete_content
                all_texts.append(("complete", complete_content))

            print()
            print("=" * 80)
            print("✅ 收到最终帧")
            print("=" * 80)
            stream_complete = True

    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "query": QUERY,
                "stream": True
            }
            
            print("📤 发送请求...")
            print(f"   查询: {QUERY}")
            print()
            
            async with session.post(
                f"{BASE_URL}/api/v1/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            ) as resp:
                if resp.status != 200:
                    print(f"❌ 请求失败，状态码: {resp.status}")
                    return
                
                print("📥 开始接收流式响应...")
                print()
                
                buffer = ""
                accumulated_thinking = ""
                accumulated_text = ""
                stream_complete = False  # 标记流是否完成
                last_data_time = time.time()  # 记录最后一次收到数据的时间
                NO_DATA_TIMEOUT = 3600.0  # 如果10秒没有收到数据，认为流已结束
                has_received_audio = False  # 标记是否收到过音频
                last_text_frame_time = None  # 记录最后一个文本帧的时间
                text_to_audio_timeout_env = os.getenv("TEXT_TO_AUDIO_TIMEOUT")
                # 如果需要等待批量TTS较长时间，可通过环境变量调整，设置为0或负数可关闭检查
                if text_to_audio_timeout_env is not None:
                    try:
                        TEXT_TO_AUDIO_TIMEOUT = float(text_to_audio_timeout_env)
                    except ValueError:
                        TEXT_TO_AUDIO_TIMEOUT = 120.0
                else:
                    TEXT_TO_AUDIO_TIMEOUT = 120.0  # 默认等120秒，兼容非chunk批量TTS
                last_chunk_receive_time = time.time()  # 记录最后一次收到chunk的时间（用于诊断）
                chunk_count = 0  # 记录收到的chunk数量
                
                try:
                    # 使用 iter_chunked 而不是 iter_any，可以更好地控制
                    async for chunk in resp.content.iter_chunked(8192):
                        current_time = time.time()
                        chunk_count += 1
                        chunk_size = len(chunk) if chunk else 0
                        last_chunk_receive_time = current_time
                        
                        # 调试：每10个chunk或收到空chunk时打印状态
                        if chunk_count % 10 == 0 or not chunk:
                            time_since_last_data = current_time - last_data_time
                            print(f"[调试] Chunk #{chunk_count}: size={chunk_size}, 距离上次数据={time_since_last_data:.2f}秒, "
                                  f"连接状态={'closed' if resp.closed else 'open'}, "
                                  f"缓冲区大小={len(buffer)}", flush=True)
                        
                        # 检查是否超时（长时间没有收到数据）
                        # 如果收到过音频，给更长的超时时间（音频传输可能需要更长时间）
                        timeout_threshold = NO_DATA_TIMEOUT * 2 if has_received_audio else NO_DATA_TIMEOUT
                        if current_time - last_data_time > timeout_threshold:
                            print(f"\n⚠️  超过 {timeout_threshold} 秒未收到数据，认为流已结束")
                            print(f"   最后收到数据时间: {last_data_time:.2f}")
                            print(f"   当前时间: {current_time:.2f}")
                            print(f"   最后收到chunk时间: {last_chunk_receive_time:.2f}")
                            print(f"   总chunk数: {chunk_count}")
                            stream_complete = True
                            break
                        
                        if not chunk:
                            # 空块可能表示连接关闭
                            if resp.closed:
                                print("\n⚠️  连接已关闭（收到空块）")
                                stream_complete = True
                                break
                            # 如果已经收到最终帧，且没有更多数据，退出循环
                            if stream_complete:
                                break
                            continue
                        
                        last_data_time = current_time
                        buffer += chunk.decode("utf-8", errors="ignore")
                        
                        # 按行处理缓冲区
                        processed_any = False
                        while "\n" in buffer:
                            processed_any = True
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            
                            if not line:
                                continue
                            
                            # 处理 SSE 格式：data: {...} 或 event:xxx\ndata: {...}
                            data_str = None
                            if line.startswith("data:"):
                                data_str = line[5:].strip()
                            elif line.startswith("event:"):
                                # 跳过 event 行，等待 data 行
                                continue
                            else:
                                # 可能是其他格式，跳过
                                continue
                            
                            # 确保 data_str 已定义
                            if data_str is None:
                                continue
                            
                            if data_str in ("", "[DONE]"):
                                # 收到 [DONE] 信号，退出循环
                                print("\n✅ 收到 [DONE] 信号")
                                stream_complete = True
                                break
                            
                            try:
                                event = json.loads(data_str)
                                stats["total_frames"] += 1
                                
                                # 检查错误响应
                                code = event.get("code", 0)
                                if code != 0:
                                    message = event.get("message", "")
                                    print(f"⚠️  错误码: {code}, 消息: {message}")
                                    continue
                                
                                stats["total_frames"] += 1

                                frame_id = event.get("data", {}).get("frame_id", 0)
                                pending_events[frame_id] = event

                                def drain_pending():
                                    nonlocal next_frame_id
                                    while next_frame_id in pending_events:
                                        evt = pending_events.pop(next_frame_id)
                                        process_event(evt)
                                        next_frame_id += 1

                                drain_pending()
                                    
                            except json.JSONDecodeError as e:
                                # 忽略 JSON 解析错误，但打印调试信息
                                if processed_any:
                                    # 只在处理了数据时才打印，避免过多输出
                                    pass
                        
                        # 如果收到最终帧或 [DONE]，退出外层循环
                        if stream_complete:
                            break
                        
                        # 处理缓冲区中剩余的数据（在 while 循环结束后）
                        if buffer.strip() and not stream_complete:
                            # 如果缓冲区还有数据但没有换行符，等待更多数据
                            # 不做任何处理，继续下一次迭代
                            pass
                        
                        # 定期检查连接状态和超时（每次迭代都检查）
                        current_check_time = time.time()
                        if not stream_complete:
                            # 检查是否连接已关闭
                            if resp.closed:
                                print("\n⚠️  连接已关闭，但未收到最终帧")
                                print(f"   最后收到数据时间: {last_data_time:.2f}")
                                print(f"   当前时间: {current_check_time:.2f}")
                                print(f"   总chunk数: {chunk_count}")
                                stream_complete = True
                                break
                            
                            # 检查是否超时（在处理完数据后也检查）
                            timeout_threshold = NO_DATA_TIMEOUT * 2 if has_received_audio else NO_DATA_TIMEOUT
                            
                            # 如果文本帧处理完较久还没收到音频，也考虑退出（可配置）
                            if last_text_frame_time and not has_received_audio and TEXT_TO_AUDIO_TIMEOUT is not None and TEXT_TO_AUDIO_TIMEOUT > 0:
                                if current_check_time - last_text_frame_time > TEXT_TO_AUDIO_TIMEOUT:
                                    print(f"\n⚠️  文本帧处理完超过 {TEXT_TO_AUDIO_TIMEOUT} 秒未收到音频，认为流已结束（可通过 TEXT_TO_AUDIO_TIMEOUT 调整或设为0禁用）")
                                    print(f"   最后文本帧时间: {last_text_frame_time:.2f}")
                                    print(f"   当前时间: {current_check_time:.2f}")
                                    stream_complete = True
                                    break
                            
                            if current_check_time - last_data_time > timeout_threshold:
                                print(f"\n⚠️  超过 {timeout_threshold} 秒未收到新数据，认为流已结束")
                                print(f"   最后收到数据时间: {last_data_time:.2f}")
                                print(f"   当前时间: {current_check_time:.2f}")
                                print(f"   最后收到chunk时间: {last_chunk_receive_time:.2f}")
                                print(f"   总chunk数: {chunk_count}")
                                print(f"   缓冲区剩余: {len(buffer)} 字符")
                                stream_complete = True
                                break
                
                except asyncio.TimeoutError:
                    print(f"\n⚠️  读取流数据超时")
                    stream_complete = True
                except Exception as e:
                    print(f"\n⚠️  读取流数据时出错: {e}")
                    import traceback
                    traceback.print_exc()
                    stream_complete = True
                
                # 如果流结束但没有收到最终帧，打印提示
                if not stats["final_frame"] and stream_complete:
                    print("\n⚠️  流已结束，但未收到最终帧标记")
                
                # 保存最终帧完整内容
                if final_frame_event is not None:
                    final_json_path = output_dir / f"{output_basename}_final.json"
                    try:
                        with open(final_json_path, "w", encoding="utf-8") as f:
                            json.dump(final_frame_event, f, indent=2, ensure_ascii=False)
                        print(f"\n✅ 已保存最终帧完整内容: {final_json_path}")
                    except Exception as e:
                        print(f"\n⚠️  保存最终帧内容失败: {e}")
                else:
                    print("\n⚠️  未捕获到最终帧，未生成最终帧JSON文件")

                # 打印最终的文本帧和音频帧（而非第一帧）
                if last_text_frame_event is not None:
                    print("\n" + "=" * 80)
                    print("📋 最终 TEXT 类型响应（完整JSON）")
                    print("=" * 80)
                    print(json.dumps(last_text_frame_event, indent=2, ensure_ascii=False))
                    print("=" * 80 + "\n")
                else:
                    print("\n⚠️  未捕获到文本帧，无法打印最终文本帧")

                if last_audio_frame_event is not None:
                    print("\n" + "=" * 80)
                    print("📋 最终 AUDIO 类型响应（完整JSON）")
                    print("=" * 80)
                    # 为了可读性，音频数据可能很长，我们截断显示base64数据
                    event_copy = json.loads(json.dumps(last_audio_frame_event))
                    if event_copy.get("data", {}).get("frame_parts"):
                        for part in event_copy["data"]["frame_parts"]:
                            if part.get("audio", {}).get("data"):
                                audio_data = part["audio"]["data"]
                                if len(audio_data) > 100:
                                    part["audio"]["data"] = audio_data[:100] + f"... (已截断，总长度: {len(audio_data)} 字符)"
                    print(json.dumps(event_copy, indent=2, ensure_ascii=False))
                    print("=" * 80 + "\n")
                else:
                    print("\n⚠️  未捕获到音频帧，无法打印最终音频帧")
                
                duration = time.time() - start_time
                
                print()
                print("=" * 80)
                print("📊 统计信息")
                print("=" * 80)
                print(f"总耗时: {duration:.2f} 秒")
                print(f"总帧数: {stats['total_frames']}")
                print(f"Thinking 帧: {stats['thinking_frames']}")
                print(f"Text 帧: {stats['text_frames']}")
                print(f"Audio 帧: {stats['audio_frames']}")
                print(f"Image 帧: {stats['image_frames']}")
                print(f"最终帧: {'是' if stats['final_frame'] else '否'}")
                print(f"总chunk数: {chunk_count}")
                print(f"缓冲区剩余: {len(buffer)} 字符")
                print()
                
                # 响应时间统计
                print("=" * 80)
                print("⏱️  响应时间")
                print("=" * 80)
                if first_text_time is not None:
                    text_response_time = first_text_time - start_time
                    print(f"第一个文本响应时间: {text_response_time:.3f} 秒")
                else:
                    print("第一个文本响应时间: (未收到)")
                
                if first_audio_time is not None:
                    audio_response_time = first_audio_time - start_time
                    print(f"第一个音频响应时间: {audio_response_time:.3f} 秒")
                else:
                    print("第一个音频响应时间: (未收到)")
                print()
                
                # 打印所有文本
                print("=" * 80)
                print("📝 所有文本内容")
                print("=" * 80)
                if all_texts:
                    # 按类型分组打印
                    thinking_texts = []
                    content_texts = []
                    other_texts = []
                    
                    for text_type, text_content in all_texts:
                        if text_type == "thinking":
                            thinking_texts.append(text_content)
                        elif text_type in ("text", "complete"):
                            content_texts.append(text_content)
                        else:
                            other_texts.append((text_type, text_content))
                    
                    # 打印思考内容
                    if thinking_texts:
                        print("\n[💭 思考内容]")
                        print("-" * 80)
                        full_thinking = "".join(thinking_texts)
                        print(full_thinking)
                    
                    # 打印播报文本内容（完整合并）
                    if content_texts:
                        print("\n[📄 播报文本内容（完整）]")
                        print("-" * 80)
                        full_content = "".join(content_texts)
                        print(full_content)
                    
                    # 打印其他文本
                    if other_texts:
                        for text_type, text_content in other_texts:
                            type_label = {
                                "frame_text": "📋 帧文本"
                            }.get(text_type, "❓ 未知")
                            print(f"\n[{type_label}]")
                            print("-" * 80)
                            print(text_content)
                else:
                    print("(无文本内容)")
                print()
                
                # 打印所有图片链接
                print("=" * 80)
                print("🖼️  所有图片链接")
                print("=" * 80)
                if all_image_links:
                    for idx, img_link in enumerate(all_image_links, 1):
                        print(f"{idx}. {img_link}")
                else:
                    print("(无图片链接)")
                print()
                
                # 合并音频
                print("=" * 80)
                print("🔊 合并音频")
                print("=" * 80)
                if all_audio_chunks:
                    print(f"收到 {len(all_audio_chunks)} 个音频块")
                    total_bytes = sum(len(chunk) for chunk in all_audio_chunks)
                    print(f"总大小: {total_bytes} 字节")
                    
                    # 打印每个音频块的大小统计
                    print()
                    print("-" * 80)
                    print("📊 音频块大小统计")
                    print("-" * 80)
                    if audio_chunk_sizes:
                        # 打印每个 chunk 的大小
                        print("每个音频块的大小:")
                        for idx, size in enumerate(audio_chunk_sizes, 1):
                            print(f"  Chunk #{idx}: {size:,} 字节 ({size / 1024:.2f} KB)")
                        
                        # 统计信息
                        print()
                        print("统计信息:")
                        print(f"  最小块大小: {min(audio_chunk_sizes):,} 字节 ({min(audio_chunk_sizes) / 1024:.2f} KB)")
                        print(f"  最大块大小: {max(audio_chunk_sizes):,} 字节 ({max(audio_chunk_sizes) / 1024:.2f} KB)")
                        print(f"  平均块大小: {sum(audio_chunk_sizes) / len(audio_chunk_sizes):,.0f} 字节 ({sum(audio_chunk_sizes) / len(audio_chunk_sizes) / 1024:.2f} KB)")
                        print(f"  总块数: {len(audio_chunk_sizes)}")
                        print(f"  总大小: {sum(audio_chunk_sizes):,} 字节 ({sum(audio_chunk_sizes) / 1024 / 1024:.2f} MB)")
                    else:
                        print("(无音频块大小记录)")
                    print("-" * 80)
                    print()
                    
                    # 生成输出文件名
                    output_filename = f"{output_basename}_merged.wav"
                    output_path = output_dir / output_filename
                    
                    # 合并所有音频块
                    try:
                        with wave.open(str(output_path), "wb") as wav_file:
                            wav_file.setnchannels(AUDIO_CHANNELS)  # 单声道
                            wav_file.setsampwidth(AUDIO_SAMPLE_WIDTH)  # 16位 = 2字节
                            wav_file.setframerate(AUDIO_SAMPLE_RATE)  # 采样率
                            
                            for chunk in all_audio_chunks:
                                wav_file.writeframes(chunk)
                        
                        # 计算音频时长
                        total_samples = total_bytes // AUDIO_SAMPLE_WIDTH
                        duration_seconds = total_samples / AUDIO_SAMPLE_RATE
                        
                        print(f"✅ 音频合并成功!")
                        print(f"   输出文件: {output_path}")
                        print(f"   音频时长: {duration_seconds:.2f} 秒")
                        print(f"   采样率: {AUDIO_SAMPLE_RATE} Hz")
                        print(f"   声道数: {AUDIO_CHANNELS}")
                        print(f"   位深: {AUDIO_SAMPLE_WIDTH * 8} bit")
                    except Exception as e:
                        print(f"❌ 合并音频失败: {e}")
                else:
                    print("(无音频数据)")
                print()
                
                print("=" * 80)
                print("✅ 测试完成")
                print("=" * 80)
                
    except asyncio.TimeoutError:
        print(f"❌ 请求超时（超过 {TIMEOUT} 秒）")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """主函数"""
    # 检查服务是否运行
    print("\n🔍 检查服务状态...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    print("✅ 服务运行正常")
                else:
                    print(f"⚠️  服务状态异常: {resp.status}")
    except Exception as e:
        return
    
    print()
    
    # 运行测试
    await test_news_query()


if __name__ == "__main__":
    asyncio.run(main())

