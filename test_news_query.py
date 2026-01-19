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
                
                async for chunk in resp.content.iter_any():
                    if not chunk:
                        continue
                    
                    buffer += chunk.decode("utf-8", errors="ignore")
                    
                    # 按行处理缓冲区
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        
                        if not line or not line.startswith("data:"):
                            continue
                        
                        data_str = line[5:].strip()
                        if data_str in ("", "[DONE]"):
                            continue
                        
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
                            
                            # 处理 thinking 类型
                            is_thinking = response_type == "thinking" or token_type == "thinking"
                            if is_thinking:
                                stats["thinking_frames"] += 1
                                if delta_content:
                                    accumulated_thinking += delta_content
                                    all_texts.append(("thinking", delta_content))
                            
                            # 处理 content/text 类型
                            is_content = (
                                response_type == "text" or 
                                token_type == "content" or 
                                (frame_text and response_type == "text")
                            )
                            if is_content and not is_thinking:
                                stats["text_frames"] += 1
                                text_to_display = delta_content if delta_content else frame_text
                                if text_to_display:
                                    accumulated_text += text_to_display
                                    all_texts.append(("text", text_to_display))
                            
                            # 处理其他 frame_text
                            if frame_text and not is_thinking and not is_content:
                                all_texts.append(("frame_text", frame_text))
                            
                            # 处理 frame_parts（音频和图片）
                            if frame_parts and isinstance(frame_parts, list):
                                for part in frame_parts:
                                    if not isinstance(part, dict):
                                        continue
                                    
                                    part_type = part.get("type", "")
                                    
                                    # 处理音频
                                    if part_type == "audio":
                                        stats["audio_frames"] += 1
                                        audio_info = part.get("audio", {})
                                        if isinstance(audio_info, dict):
                                            audio_data_str = audio_info.get("data", "")
                                            if audio_data_str:
                                                try:
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
                                                        print(f"🔊 收到音频块 (Frame #{frame_id}): {len(audio_bytes)} 字节")
                                                except Exception as e:
                                                    print(f"⚠️  解码音频数据失败: {e}")
                                    
                                    # 处理图片
                                    elif part_type == "image":
                                        stats["image_frames"] += 1
                                        image_info = part.get("image", {})
                                        if isinstance(image_info, dict):
                                            image_data = image_info.get("data", "")
                                            if image_data:
                                                all_image_links.append(image_data)
                                                print(f"🖼️  收到图片链接 (Frame #{frame_id}): {image_data}")
                            
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
                                
                        except json.JSONDecodeError:
                            # 忽略 JSON 解析错误
                            pass
                
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
                
                # 打印所有文本
                print("=" * 80)
                print("📝 所有文本内容")
                print("=" * 80)
                if all_texts:
                    for text_type, text_content in all_texts:
                        type_label = {
                            "thinking": "💭 思考",
                            "text": "📄 文本",
                            "frame_text": "📋 帧文本",
                            "complete": "✅ 完整内容"
                        }.get(text_type, "❓ 未知")
                        print(f"\n[{type_label}]")
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

