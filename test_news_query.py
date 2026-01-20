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
                NO_DATA_TIMEOUT = 10.0  # 如果10秒没有收到数据，认为流已结束
                has_received_audio = False  # 标记是否收到过音频
                last_text_frame_time = None  # 记录最后一个文本帧的时间
                
                try:
                    # 使用 iter_chunked 而不是 iter_any，可以更好地控制
                    async for chunk in resp.content.iter_chunked(8192):
                        current_time = time.time()
                        
                        # 检查是否超时（长时间没有收到数据）
                        # 如果收到过音频，给更长的超时时间（音频传输可能需要更长时间）
                        timeout_threshold = NO_DATA_TIMEOUT * 2 if has_received_audio else NO_DATA_TIMEOUT
                        if current_time - last_data_time > timeout_threshold:
                            print(f"\n⚠️  超过 {timeout_threshold} 秒未收到数据，认为流已结束")
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
                                
                                data = event.get("data", {})
                                if not data:
                                    continue
                                
                                frame_id = data.get("frame_id", 0)
                                response_type = data.get("response_type", "")
                                frame_is_final = data.get("frame_is_final", False)
                                frame_parts = data.get("frame_parts", [])
                                extension = data.get("extension", {})
                                
                                # 获取增量内容
                                delta_content = data.get("delta_content", "")
                                frame_text = data.get("frame_text", "")
                                token_type = extension.get("token_type", "")
                                
                                # 判断响应类型
                                is_audio_frame = response_type == "audio" or token_type == "audio"
                                is_thinking_frame = response_type == "thinking" or token_type == "thinking"
                                is_text_frame = (
                                    response_type == "text" or 
                                    token_type == "content" or 
                                    (frame_text and response_type == "text")
                                )
                                is_image_frame = response_type == "image"
                                
                                # 打印每个类型的第一个完整响应
                                # 注意：final是特殊标记，独立判断，不与其他类型互斥
                                
                                # 1. 处理 FINAL 类型（优先，因为final是特殊标记）
                                if frame_is_final and not first_responses_printed["final"]:
                                    first_responses_printed["final"] = True
                                    print("\n" + "=" * 80)
                                    print("📋 第一个 FINAL 类型响应（完整JSON）")
                                    print("=" * 80)
                                    print(json.dumps(event, indent=2, ensure_ascii=False))
                                    print("=" * 80 + "\n")
                                
                                # 2. 处理 THINKING 类型
                                if is_thinking_frame and not first_responses_printed["thinking"]:
                                    first_responses_printed["thinking"] = True
                                    print("\n" + "=" * 80)
                                    print("📋 第一个 THINKING 类型响应（完整JSON）")
                                    print("=" * 80)
                                    print(json.dumps(event, indent=2, ensure_ascii=False))
                                    print("=" * 80 + "\n")
                                
                                # 3. 处理 TEXT 类型（排除thinking和audio）
                                if is_text_frame and not is_thinking_frame and not is_audio_frame and not first_responses_printed["text"]:
                                    first_responses_printed["text"] = True
                                    print("\n" + "=" * 80)
                                    print("📋 第一个 TEXT 类型响应（完整JSON）")
                                    print("=" * 80)
                                    print(json.dumps(event, indent=2, ensure_ascii=False))
                                    print("=" * 80 + "\n")
                                
                                # 4. 处理 AUDIO 类型
                                if is_audio_frame and not first_responses_printed["audio"]:
                                    first_responses_printed["audio"] = True
                                    print("\n" + "=" * 80)
                                    print("📋 第一个 AUDIO 类型响应（完整JSON）")
                                    print("=" * 80)
                                    # 为了可读性，音频数据可能很长，我们截断显示base64数据
                                    event_copy = json.loads(json.dumps(event))  # 深拷贝
                                    if event_copy.get("data", {}).get("frame_parts"):
                                        for part in event_copy["data"]["frame_parts"]:
                                            if part.get("audio", {}).get("data"):
                                                audio_data = part["audio"]["data"]
                                                if len(audio_data) > 100:
                                                    part["audio"]["data"] = audio_data[:100] + f"... (已截断，总长度: {len(audio_data)} 字符)"
                                    print(json.dumps(event_copy, indent=2, ensure_ascii=False))
                                    print("=" * 80 + "\n")
                                
                                # 5. 处理 IMAGE 类型
                                if is_image_frame and not first_responses_printed["image"]:
                                    first_responses_printed["image"] = True
                                    print("\n" + "=" * 80)
                                    print("📋 第一个 IMAGE 类型响应（完整JSON）")
                                    print("=" * 80)
                                    print(json.dumps(event, indent=2, ensure_ascii=False))
                                    print("=" * 80 + "\n")
                                
                                # 调试输出：显示每个帧的类型（每10帧、音频帧或最终帧）
                                if stats["total_frames"] % 10 == 0 or frame_is_final or is_audio_frame:
                                    print(f"[调试] Frame #{frame_id}: type={response_type}, token_type={token_type}, final={frame_is_final}, parts={len(frame_parts) if frame_parts else 0}", flush=True)
                                
                                # 处理音频帧（优先处理，因为音频帧可能没有其他内容）
                                if is_audio_frame:
                                    # 音频帧的 response_type="audio" 或 token_type="audio"
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
                                                            # 记录第一个音频的时间戳
                                                            if first_audio_time is None:
                                                                first_audio_time = time.time()
                                                            
                                                            # 解析 base64 数据
                                                            if audio_data_str.startswith("data:;base64,"):
                                                                base64_data = audio_data_str[13:]
                                                            elif audio_data_str.startswith("data:audio/pcm;base64,"):
                                                                base64_data = audio_data_str[22:]
                                                            else:
                                                                base64_data = audio_data_str
                                                            
                                                            audio_bytes = base64.b64decode(base64_data)
                                                            if audio_bytes:
                                                                all_audio_chunks.append(audio_bytes)
                                                                has_received_audio = True  # 标记已收到音频
                                                                print(f"🔊 收到音频块 (Frame #{frame_id}): {len(audio_bytes)} 字节", flush=True)
                                                        except Exception as e:
                                                            print(f"⚠️  解码音频数据失败: {e}", flush=True)
                                    else:
                                        # 如果没有 frame_parts，打印警告
                                        print(f"⚠️  音频帧 Frame #{frame_id} 没有 frame_parts", flush=True)
                                
                                # 处理 thinking 类型（使用上面已判断的变量）
                                if is_thinking_frame and not is_audio_frame:
                                    stats["thinking_frames"] += 1
                                    if delta_content:
                                        accumulated_thinking += delta_content
                                        all_texts.append(("thinking", delta_content))
                                
                                # 处理 content/text 类型（使用上面已判断的变量）
                                if is_text_frame and not is_thinking_frame and not is_audio_frame:
                                    stats["text_frames"] += 1
                                    text_to_display = delta_content if delta_content else frame_text
                                    if text_to_display:
                                        # 记录第一个文本的时间戳
                                        if first_text_time is None:
                                            first_text_time = time.time()
                                        last_text_frame_time = time.time()  # 更新最后一个文本帧的时间
                                        accumulated_text += text_to_display
                                        all_texts.append(("text", text_to_display))
                                
                                # 处理其他 frame_text
                                if frame_text and not is_thinking_frame and not is_text_frame and not is_audio_frame:
                                    all_texts.append(("frame_text", frame_text))
                                
                                # 处理 frame_parts（图片和其他类型，音频已在上面处理）
                                if frame_parts and isinstance(frame_parts, list):
                                    for part in frame_parts:
                                        if not isinstance(part, dict):
                                            continue
                                        
                                        part_type = part.get("type", "")
                                        
                                        # 处理图片
                                        if part_type == "image":
                                            stats["image_frames"] += 1
                                            image_info = part.get("image", {})
                                            if isinstance(image_info, dict):
                                                image_data = image_info.get("data", "")
                                                if image_data:
                                                    all_image_links.append(image_data)
                                                    print(f"🖼️  收到图片链接 (Frame #{frame_id}): {image_data}", flush=True)
                                
                                # 处理最终帧
                                if frame_is_final:
                                    stats["final_frame"] = True
                                    complete_content = data.get("complete_content", "")
                                    if complete_content:
                                        accumulated_text = complete_content
                                        all_texts.append(("complete", complete_content))
                                    
                                    print()
                                    print("=" * 80)
                                    print("✅ 收到最终帧")
                                    print("=" * 80)
                                    
                                    # 收到最终帧后，标记完成并退出循环
                                    stream_complete = True
                                    break  # 退出内层 while 循环
                                    
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
                                stream_complete = True
                                break
                            
                            # 检查是否超时（在处理完数据后也检查）
                            timeout_threshold = NO_DATA_TIMEOUT * 2 if has_received_audio else NO_DATA_TIMEOUT
                            
                            # 如果文本帧处理完超过15秒还没收到音频，也考虑退出
                            if last_text_frame_time and not has_received_audio:
                                text_to_audio_timeout = 15.0
                                if current_check_time - last_text_frame_time > text_to_audio_timeout:
                                    print(f"\n⚠️  文本帧处理完超过 {text_to_audio_timeout} 秒未收到音频，认为流已结束")
                                    stream_complete = True
                                    break
                            
                            if current_check_time - last_data_time > timeout_threshold:
                                print(f"\n⚠️  超过 {timeout_threshold} 秒未收到新数据，认为流已结束")
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
                    
                    # 生成输出文件名
                    timestamp = int(time.time())
                    safe_query = "".join(c for c in QUERY[:20] if c.isalnum() or c in (' ', '-', '_')).strip()
                    safe_query = safe_query.replace(' ', '_') if safe_query else "news"
                    output_filename = f"{safe_query}_{timestamp}_merged.wav"
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
        print(f"❌ 无法连接到服务: {e}")
        print(f"\n💡 请先启动服务:")
        print(f"   python3 main.py")
        print(f"\n或在另一个终端运行:")
        print(f"   uvicorn main:app --host 0.0.0.0 --port 8080")
        return
    
    print()
    
    # 运行测试
    await test_news_query()


if __name__ == "__main__":
    asyncio.run(main())

