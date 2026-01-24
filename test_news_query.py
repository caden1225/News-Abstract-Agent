#!/usr/bin/env python3
"""
测试脚本：测试API请求
"""
import asyncio
import aiohttp
import json
import os
import time
import base64
import wave
from pathlib import Path

# ==================== 配置 ====================

BASE_URL = os.getenv("API_URL", "http://localhost:8080")
QUERY = "今天有什么新闻？用韩语播一下"
AUDIO_SAMPLE_RATE = 24000  # 音频采样率（Hz）
AUDIO_CHANNELS = 1  # 单声道
AUDIO_SAMPLE_WIDTH = 2  # 16位 = 2字节

# ==================== 主函数 ====================

async def test_news_query():
    """测试新闻查询"""
    print(f"测试查询: {QUERY}")
    print(f"API地址: {BASE_URL}\n")
    
    # 创建输出目录
    output_dir = Path("test_output")
    output_dir.mkdir(exist_ok=True)
    start_time = time.time()
    timestamp = int(start_time)
    safe_query = "".join(c for c in QUERY[:20] if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_query = safe_query.replace(' ', '_') if safe_query else "news"
    output_basename = f"{safe_query}_{timestamp}"
    
    # 存储数据
    all_audio_chunks = []  # 所有音频块（PCM字节数据）
    audio_chunk_sizes = []  # 每个音频块的大小（字节）
    all_frames = []  # 所有帧（用于保存，移除base64音频数据）
    
    # 统计信息
    stats = {
        "thinking_frames": 0,
        "text_frames": 0,
        "audio_frames": 0,
        "image_frames": 0,
        "total_frames": 0,
        "final_frame": False
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "query": QUERY,
                "stream": True
            }
            
            async with session.post(
                f"{BASE_URL}/api/v1/chat",
                json=payload,
            ) as resp:
                if resp.status != 200:
                    print(f"❌ 请求失败，状态码: {resp.status}")
                    return
                
                print("📥 开始接收流式响应...\n")
                buffer = ""
                stream_complete = False
                
                async for chunk in resp.content.iter_chunked(8192):
                    if not chunk:
                        if resp.closed:
                            stream_complete = True
                            break
                        continue
                    
                    buffer += chunk.decode("utf-8", errors="ignore")
                    
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        
                        if not line or not line.startswith("data:"):
                            continue
                        
                        data_str = line[5:].strip()
                        
                        if data_str in ("", "[DONE]"):
                            print("\n✅ 收到 [DONE] 信号")
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
                            
                            stats["total_frames"] += 1
                            
                            # 处理响应数据
                            data = event.get("data", {})
                            if not data:
                                continue
                            
                            response_type = data.get("response_type", "")
                            frame_text = data.get("frame_text", "")
                            delta_content = data.get("delta_content", "")
                            content = data.get("content", "")
                            frame_is_final = data.get("frame_is_final", False)
                            frame_parts = data.get("frame_parts", [])
                            extension = data.get("extension", {})
                            token_type = extension.get("token_type", "")
                            
                            # 判断帧类型
                            is_audio_frame = response_type == "audio" or token_type == "audio"
                            is_thinking_frame = response_type == "thinking" or token_type == "thinking"
                            is_text_frame = (
                                response_type == "text" or
                                token_type == "content" or
                                (frame_text and response_type == "text")
                            )
                            is_image_frame = response_type == "image"
                            
                            # 处理音频帧
                            if is_audio_frame:
                                stats["audio_frames"] += 1
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
                                                    except Exception as e:
                                                        print(f"⚠️  解码音频数据失败: {e}", flush=True)
                            
                            # 统计其他帧类型
                            if is_thinking_frame and not is_audio_frame:
                                stats["thinking_frames"] += 1
                            
                            if is_text_frame and not is_thinking_frame and not is_audio_frame:
                                stats["text_frames"] += 1
                            
                            if is_image_frame:
                                stats["image_frames"] += 1
                            
                            # 保存帧（移除base64音频数据）
                            frame_to_save = json.loads(json.dumps(event))  # 深拷贝
                            if is_audio_frame and frame_parts:
                                # 移除音频数据中的base64内容
                                for part in frame_to_save.get("data", {}).get("frame_parts", []):
                                    if isinstance(part, dict) and part.get("type") == "audio":
                                        audio_info = part.get("audio", {})
                                        if isinstance(audio_info, dict) and "data" in audio_info:
                                            audio_info["data"] = "[音频数据已移除]"
                            all_frames.append(frame_to_save)
                            
                            # 打印文本内容
                            if not is_audio_frame:
                                text = delta_content or content or frame_text
                                if text:
                                    print(text, end="", flush=True)
                            
                            # 处理最终帧
                            if frame_is_final:
                                stats["final_frame"] = True
                                print("\n\n✅ 收到最终帧")
                                stream_complete = True
                                break
                                
                        except json.JSONDecodeError:
                            continue
                
                if not stream_complete:
                    print("\n⚠️  流已结束")
                
                # 保存所有帧内容
                frames_json_path = output_dir / f"{output_basename}_frames.json"
                try:
                    with open(frames_json_path, "w", encoding="utf-8") as f:
                        json.dump(all_frames, f, indent=2, ensure_ascii=False)
                    print(f"\n✅ 已保存所有帧内容: {frames_json_path}")
                except Exception as e:
                    print(f"\n⚠️  保存帧内容失败: {e}")
                
                # 合并音频
                if all_audio_chunks:
                    print("\n" + "=" * 80)
                    print("🔊 合并音频")
                    print("=" * 80)
                    print(f"收到 {len(all_audio_chunks)} 个音频块")
                    total_bytes = sum(len(chunk) for chunk in all_audio_chunks)
                    print(f"总大小: {total_bytes} 字节 ({total_bytes / 1024 / 1024:.2f} MB)")
                    
                    output_filename = f"{output_basename}_merged.wav"
                    output_path = output_dir / output_filename
                    
                    try:
                        with wave.open(str(output_path), "wb") as wav_file:
                            wav_file.setnchannels(AUDIO_CHANNELS)
                            wav_file.setsampwidth(AUDIO_SAMPLE_WIDTH)
                            wav_file.setframerate(AUDIO_SAMPLE_RATE)
                            
                            for chunk in all_audio_chunks:
                                wav_file.writeframes(chunk)
                        
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
                    print("\n⚠️  未收到音频数据")
                
                # 打印统计信息
                duration = time.time() - start_time
                print("\n" + "=" * 80)
                print("📊 统计信息")
                print("=" * 80)
                print(f"总耗时: {duration:.2f} 秒")
                print(f"总帧数: {stats['total_frames']}")
                print(f"Thinking 帧: {stats['thinking_frames']}")
                print(f"Text 帧: {stats['text_frames']}")
                print(f"Audio 帧: {stats['audio_frames']}")
                print(f"Image 帧: {stats['image_frames']}")
                print(f"最终帧: {'是' if stats['final_frame'] else '否'}")
                if audio_chunk_sizes:
                    print(f"\n音频块统计:")
                    print(f"  总块数: {len(audio_chunk_sizes)}")
                    print(f"  最小块大小: {min(audio_chunk_sizes):,} 字节")
                    print(f"  最大块大小: {max(audio_chunk_sizes):,} 字节")
                    print(f"  平均块大小: {sum(audio_chunk_sizes) / len(audio_chunk_sizes):,.0f} 字节")
                print("=" * 80)
                
                print("\n✅ 测试完成")
                
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
