#!/usr/bin/env python3
"""
精简测试脚本：按顺序打印收到的每一帧，并保存到文件
- 所有帧按顺序保存到JSON文件（audio数据舍弃）
- 每个音频chunk保存为单独文件
- 合并所有音频chunk为一个文件
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

# ==================== 配置 ====================
BASE_URL = os.getenv("API_URL", "http://localhost:8080")
TIMEOUT = 300  # 秒
QUERY = "今天有什么新闻？"
AUDIO_SAMPLE_RATE = 24000  # 音频采样率（Hz）
AUDIO_CHANNELS = 1  # 单声道
AUDIO_SAMPLE_WIDTH = 2  # 16位 = 2字节

# ==================== 主函数 ====================

async def test_news_query():
    """测试新闻查询，按顺序打印每一帧，并保存到文件"""
    print("=" * 80)
    print(f"测试查询: {QUERY}")
    print(f"API地址: {BASE_URL}")
    print("=" * 80)
    print()
    
    # 创建输出目录
    output_dir = Path("test_output")
    output_dir.mkdir(exist_ok=True)
    print(f"📁 输出目录: {output_dir.absolute()}")
    print()
    
    # 生成输出文件名
    start_time = time.time()
    timestamp = int(start_time)
    safe_query = "".join(c for c in QUERY[:20] if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_query = safe_query.replace(' ', '_') if safe_query else "news"
    output_basename = f"{safe_query}_{timestamp}"
    
    # 存储所有帧（去掉audio数据）和音频chunk
    all_frames = []  # 所有帧（已去除audio数据）
    all_audio_chunks = []  # 所有音频块（PCM字节数据）
    audio_chunk_index = 0  # 音频chunk计数器
    
    # 处理按 frame_id 有序输出
    pending_events = {}
    next_frame_id = 0
    
    def remove_audio_data(obj):
        """递归移除对象中的audio数据"""
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                if key == "audio" and isinstance(value, dict):
                    # 保留audio结构但移除data字段
                    audio_info = {k: v for k, v in value.items() if k != "data"}
                    if audio_info:
                        result[key] = {**audio_info, "data": "[已移除: 数据过长]"}
                    else:
                        result[key] = {"data": "[已移除: 数据过长]"}
                else:
                    result[key] = remove_audio_data(value)
            return result
        elif isinstance(obj, list):
            return [remove_audio_data(item) for item in obj]
        else:
            return obj
    
    def process_frame(event):
        """处理单帧：打印、保存到列表、提取音频"""
        nonlocal next_frame_id, audio_chunk_index
        
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
        
        # 确定帧类型
        frame_type = "unknown"
        if response_type == "thinking" or token_type == "thinking":
            frame_type = "thinking"
        elif response_type == "text" or token_type == "content":
            frame_type = "text"
        elif response_type == "audio" or token_type == "audio":
            frame_type = "audio"
        elif response_type == "image":
            frame_type = "image"
        elif frame_is_final:
            frame_type = "final"
        
        # 获取内容
        content = delta_content or content_field or frame_text or ""
        
        # 打印帧信息
        print(f"[帧 #{frame_id}] 类型: {frame_type}, 最终: {frame_is_final}")
        if content:
            print(f"  内容: {content}")
        if frame_parts:
            print(f"  部件数: {len(frame_parts)}")
            for i, part in enumerate(frame_parts):
                part_type = part.get("type", "")
                print(f"    部件[{i}]: {part_type}")
        print()
        
        # 保存帧（去除audio数据）
        frame_copy = remove_audio_data(event)
        all_frames.append(frame_copy)
        
        # 提取音频数据
        if frame_parts and isinstance(frame_parts, list):
            for part in frame_parts:
                if not isinstance(part, dict):
                    continue
                part_type = part.get("type", "")
                if part_type == "audio":
                    audio_info = part.get("audio", {})
                    if isinstance(audio_info, dict):
                        audio_data_str = audio_info.get("data", "")
                        if audio_data_str:
                            try:
                                # 解析base64音频数据
                                if audio_data_str.startswith("data:;base64,"):
                                    base64_data = audio_data_str[13:]
                                elif audio_data_str.startswith("data:audio/pcm;base64,"):
                                    base64_data = audio_data_str[22:]
                                else:
                                    base64_data = audio_data_str
                                audio_bytes = base64.b64decode(base64_data)
                                if audio_bytes:
                                    all_audio_chunks.append(audio_bytes)
                                    # 保存单个音频chunk
                                    chunk_filename = f"{output_basename}_chunk_{audio_chunk_index:04d}.wav"
                                    chunk_path = output_dir / chunk_filename
                                    try:
                                        with wave.open(str(chunk_path), "wb") as wav_file:
                                            wav_file.setnchannels(AUDIO_CHANNELS)
                                            wav_file.setsampwidth(AUDIO_SAMPLE_WIDTH)
                                            wav_file.setframerate(AUDIO_SAMPLE_RATE)
                                            wav_file.writeframes(audio_bytes)
                                        print(f"  💾 已保存音频chunk: {chunk_filename}")
                                    except Exception as e:
                                        print(f"  ⚠️  保存音频chunk失败: {e}")
                                    audio_chunk_index += 1
                            except Exception as e:
                                print(f"  ⚠️  解码音频数据失败: {e}")
    
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "query": QUERY,
                "stream": True
            }
            
            print("📤 发送请求...")
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
                stream_complete = False
                
                try:
                    async for chunk in resp.content.iter_chunked(8192):
                        if not chunk:
                            if resp.closed or stream_complete:
                                break
                            continue
                        
                        buffer += chunk.decode("utf-8", errors="ignore")
                        
                        # 按行处理缓冲区
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            
                            if not line:
                                continue
                            
                            # 处理 SSE 格式：data: {...}
                            data_str = None
                            if line.startswith("data:"):
                                data_str = line[5:].strip()
                            elif line.startswith("event:"):
                                continue
                            else:
                                continue
                            
                            if data_str is None:
                                continue
                            
                            if data_str in ("", "[DONE]"):
                                print("✅ 收到 [DONE] 信号")
                                stream_complete = True
                                break
                            
                            try:
                                event = json.loads(data_str)
                                
                                # 检查错误响应
                                code = event.get("code", 0)
                                if code != 0:
                                    message = event.get("message", "")
                                    print(f"⚠️  错误码: {code}, 消息: {message}")
                                    continue
                                
                                # 按 frame_id 有序处理
                                frame_id = event.get("data", {}).get("frame_id", 0)
                                pending_events[frame_id] = event
                                
                                # 按顺序处理
                                while next_frame_id in pending_events:
                                    evt = pending_events.pop(next_frame_id)
                                    process_frame(evt)
                                    next_frame_id += 1
                                    
                                    # 如果是最终帧，标记完成
                                    if evt.get("data", {}).get("frame_is_final", False):
                                        stream_complete = True
                                    
                            except json.JSONDecodeError:
                                pass
                        
                        if stream_complete:
                            break
                
                except Exception as e:
                    print(f"⚠️  读取流数据时出错: {e}")
                
                # 处理剩余未处理的帧
                if pending_events:
                    print(f"\n⚠️  还有 {len(pending_events)} 个未处理的帧（frame_id 不连续）")
                    for frame_id in sorted(pending_events.keys()):
                        process_frame(pending_events[frame_id])
                
                # 保存所有帧到JSON文件
                print()
                print("=" * 80)
                print("💾 保存数据...")
                print("=" * 80)
                
                json_filename = f"{output_basename}_frames.json"
                json_path = output_dir / json_filename
                try:
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(all_frames, f, indent=2, ensure_ascii=False)
                    print(f"✅ 已保存所有帧到: {json_filename} (共 {len(all_frames)} 帧)")
                except Exception as e:
                    print(f"❌ 保存JSON文件失败: {e}")
                
                # 合并所有音频chunk
                if all_audio_chunks:
                    print(f"\n收到 {len(all_audio_chunks)} 个音频chunk")
                    total_bytes = sum(len(chunk) for chunk in all_audio_chunks)
                    print(f"总大小: {total_bytes} 字节")
                    
                    merged_filename = f"{output_basename}_merged.wav"
                    merged_path = output_dir / merged_filename
                    
                    try:
                        with wave.open(str(merged_path), "wb") as wav_file:
                            wav_file.setnchannels(AUDIO_CHANNELS)
                            wav_file.setsampwidth(AUDIO_SAMPLE_WIDTH)
                            wav_file.setframerate(AUDIO_SAMPLE_RATE)
                            
                            for chunk in all_audio_chunks:
                                wav_file.writeframes(chunk)
                        
                        # 计算音频时长
                        total_samples = total_bytes // AUDIO_SAMPLE_WIDTH
                        duration_seconds = total_samples / AUDIO_SAMPLE_RATE
                        
                        print(f"✅ 音频合并成功!")
                        print(f"   输出文件: {merged_filename}")
                        print(f"   音频时长: {duration_seconds:.2f} 秒")
                        print(f"   采样率: {AUDIO_SAMPLE_RATE} Hz")
                        print(f"   声道数: {AUDIO_CHANNELS}")
                        print(f"   位深: {AUDIO_SAMPLE_WIDTH * 8} bit")
                    except Exception as e:
                        print(f"❌ 合并音频失败: {e}")
                else:
                    print("\n(无音频数据)")
                
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
        print(f"⚠️  无法连接服务: {e}")
        return
    
    print()
    
    # 运行测试
    await test_news_query()


if __name__ == "__main__":
    asyncio.run(main())
