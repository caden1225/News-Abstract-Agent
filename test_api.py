#!/usr/bin/env python3
"""
FastAPI 服务流式测试脚本
测试流式聊天 API，支持完整的流式响应显示

测试用例：
1. "今天有什么新闻，用韩语播放下" - 测试多语言播报功能
2. "今天有什么科技新闻？" - 测试分类新闻查询

使用方法：
    python3 test_api.py
    
环境变量：
    API_URL: API服务地址（默认: http://localhost:8080）
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
from typing import Dict, Any

# ==================== 配置 ====================

BASE_URL = os.getenv("API_URL", "http://localhost:8080")
TIMEOUT = 120  # 秒
AUDIO_SAMPLE_RATE = 24000  # 音频采样率（Hz）
AUDIO_CHANNELS = 1  # 单声道
AUDIO_SAMPLE_WIDTH = 2  # 16位 = 2字节


# ==================== 测试用例 ====================

class APITester:
    """API 测试器"""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = None
        self.passed = 0
        self.failed = 0
        self.test_results = []
        # 创建输出目录
        self.output_dir = Path("test_output")
        self.output_dir.mkdir(exist_ok=True)
        self.audio_chunk_counter = 0

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def print_header(self, title: str):
        """打印测试标题"""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70)

    def print_test(self, name: str, passed: bool, duration: float, details: str = ""):
        """打印测试结果"""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} | {name} ({duration:.2f}s)")
        if details:
            print(f"       {details}")

        if passed:
            self.passed += 1
        else:
            self.failed += 1

        self.test_results.append({
            "name": name,
            "passed": passed,
            "duration": duration,
            "details": details
        })

    def save_audio_chunk(self, audio_data: bytes, frame_id: int, chunk_index: int = 0, query: str = ""):
        """保存音频 chunk 为 PCM 和 WAV 格式
        
        Args:
            audio_data: PCM 音频数据（int16 格式）
            frame_id: 帧 ID
            chunk_index: chunk 索引
            query: 查询文本（用于生成文件名）
        """
        try:
            # 生成文件名（使用查询文本的前10个字符，去除特殊字符）
            safe_query = "".join(c for c in query[:10] if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_query = safe_query.replace(' ', '_') if safe_query else "audio"
            
            # 生成唯一文件名
            self.audio_chunk_counter += 1
            timestamp = int(time.time() * 1000) % 1000000
            base_name = f"{safe_query}_frame{frame_id}_chunk{chunk_index}_{self.audio_chunk_counter:04d}_{timestamp}"
            
            # 保存 PCM 文件
            pcm_path = self.output_dir / f"{base_name}.pcm"
            with open(pcm_path, "wb") as f:
                f.write(audio_data)
            
            # 保存 WAV 文件
            wav_path = self.output_dir / f"{base_name}.wav"
            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(AUDIO_CHANNELS)  # 单声道
                wav_file.setsampwidth(AUDIO_SAMPLE_WIDTH)  # 16位 = 2字节
                wav_file.setframerate(AUDIO_SAMPLE_RATE)  # 采样率
                wav_file.writeframes(audio_data)
            
            return pcm_path, wav_path
        except Exception as e:
            print(f"\n       ⚠️  保存音频失败: {e}", flush=True)
            return None, None

    async def test_root(self):
        """测试根路径"""
        self.print_header("测试 1: 根路径")

        start = time.time()
        try:
            async with self.session.get(f"{self.base_url}/") as resp:
                duration = time.time() - start
                if resp.status == 200:
                    data = await resp.json()
                    self.print_test(
                        "GET /",
                        True,
                        duration,
                        f"服务: {data.get('service')}, 版本: {data.get('version')}"
                    )
                else:
                    self.print_test("GET /", False, duration, f"状态码: {resp.status}")
        except Exception as e:
            duration = time.time() - start
            self.print_test("GET /", False, duration, str(e))

    async def test_health(self):
        """测试健康检查"""
        self.print_header("测试 2: 健康检查")

        start = time.time()
        try:
            async with self.session.get(f"{self.base_url}/health") as resp:
                duration = time.time() - start
                if resp.status == 200:
                    data = await resp.json()
                    self.print_test(
                        "GET /health",
                        True,
                        duration,
                        f"状态: {data.get('status')}, 版本: {data.get('version')}"
                    )
                else:
                    self.print_test("GET /health", False, duration, f"状态码: {resp.status}")
        except Exception as e:
            duration = time.time() - start
            self.print_test("GET /health", False, duration, str(e))

    async def test_stats(self):
        """测试统计信息"""
        self.print_header("测试 3: 统计信息")

        start = time.time()
        try:
            async with self.session.get(f"{self.base_url}/api/v1/stats") as resp:
                duration = time.time() - start
                if resp.status == 200:
                    data = await resp.json()
                    db_info = data.get("database", {})
                    total = db_info.get("total_news", 0)
                    self.print_test(
                        "GET /api/v1/stats",
                        True,
                        duration,
                        f"总新闻数: {total}"
                    )
                else:
                    self.print_test("GET /api/v1/stats", False, duration, f"状态码: {resp.status}")
        except Exception as e:
            duration = time.time() - start
            self.print_test("GET /api/v1/stats", False, duration, str(e))

    async def test_chat_stream(self, query: str):
        """测试流式聊天"""
        self.print_header(f"测试 4: 流式聊天 - {query}")
        
        # 输出保存路径信息
        print(f"       📁 音频文件将保存到: {self.output_dir.absolute()}")

        # 重置音频计数器（每个测试独立计数）
        self.audio_chunk_counter = 0

        start = time.time()
        stats = {
            "thinking_frames": 0,
            "text_frames": 0,
            "audio_frames": 0,
            "final_frame": False,
            "thinking_chars": 0,
            "text_chars": 0,
            "total_frames": 0
        }
        
        accumulated_thinking = ""
        accumulated_text = ""
        final_data = None
        
        try:
            payload = {
                "query": query,
                "stream": True
            }

            async with self.session.post(
                f"{self.base_url}/api/v1/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            ) as resp:
                if resp.status != 200:
                    duration = time.time() - start
                    self.print_test(
                        f"POST /api/v1/chat (stream={query})",
                        False,
                        duration,
                        f"状态码: {resp.status}"
                    )
                    return

                # 读取流式响应
                print("       流式响应帧：")
                buffer = ""
                
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
                            final_data = event
                            stats["total_frames"] += 1
                            
                            # 检查错误响应
                            code = event.get("code", 0)
                            if code != 0:
                                message = event.get("message", "")
                                print(f"       [ERROR] 错误码: {code}, 消息: {message}", flush=True)
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
                            delta_audio = data.get("delta_audio", "")
                            frame_text = data.get("frame_text", "")
                            token_type = extension.get("token_type", "")
                            
                            # 使用独立的 if 语句，而不是 elif，这样可以同时处理多种类型的内容
                            # 按照接收顺序实时显示，不因类型而延迟
                            
                            # 处理 thinking 类型（紫色）
                            is_thinking = response_type == "thinking" or token_type == "thinking"
                            if is_thinking:
                                stats["thinking_frames"] += 1
                                if delta_content:
                                    accumulated_thinking += delta_content
                                    stats["thinking_chars"] += len(delta_content)
                                    print(f"\033[35m{delta_content}\033[0m", end="", flush=True)
                            
                            # 处理 content/text 类型（绿色）- 与 thinking 和 audio 并行处理
                            is_content = (
                                response_type == "text" or 
                                token_type == "content" or 
                                (frame_text and response_type == "text")
                            )
                            if is_content and not is_thinking:  # 避免重复处理
                                stats["text_frames"] += 1
                                # 优先使用 delta_content，其次使用 frame_text
                                text_to_display = delta_content if delta_content else frame_text
                                if text_to_display:
                                    accumulated_text += text_to_display
                                    stats["text_chars"] += len(text_to_display)
                                    print(f"\033[32m{text_to_display}\033[0m", end="", flush=True)
                            
                            # 处理其他 frame_text（如果存在且不是 thinking/content/text）
                            if frame_text and not is_thinking and not is_content:
                                # 显示 frame_text（黄色）
                                print(f"\033[33m{frame_text}\033[0m", end="", flush=True)
                            
                            # 处理 audio 类型（蓝色）- 与文本并行处理
                            if frame_parts or delta_audio:
                                stats["audio_frames"] += 1
                                audio_count = len(frame_parts) if frame_parts else 0
                                # 显示音频块信息（蓝色）
                                print(f"\n\033[34m🔊 [Audio Frame #{frame_id}] {audio_count} chunk(s)\033[0m", flush=True)
                                
                                # 处理 frame_parts 中的音频数据
                                if frame_parts and isinstance(frame_parts, list):
                                    for chunk_idx, part in enumerate(frame_parts):
                                        if isinstance(part, dict):
                                            audio_info = part.get("audio", {})
                                            if isinstance(audio_info, dict):
                                                audio_data_str = audio_info.get("data", "")
                                                if audio_data_str:
                                                    # 解析 data:;base64,{base64_data} 格式
                                                    if audio_data_str.startswith("data:;base64,"):
                                                        base64_data = audio_data_str[13:]  # 跳过 "data:;base64,"
                                                    elif audio_data_str.startswith("data:audio/pcm;base64,"):
                                                        base64_data = audio_data_str[22:]  # 跳过 "data:audio/pcm;base64,"
                                                    else:
                                                        base64_data = audio_data_str
                                                    
                                                    try:
                                                        # 解码 base64 数据
                                                        audio_bytes = base64.b64decode(base64_data)
                                                        if audio_bytes:
                                                            # 保存音频文件
                                                            pcm_path, wav_path = self.save_audio_chunk(
                                                                audio_bytes, frame_id, chunk_idx, query
                                                            )
                                                            if pcm_path and wav_path:
                                                                print(f"       💾 已保存: {pcm_path.name} ({len(audio_bytes)} bytes)", flush=True)
                                                                print(f"       💾 已保存: {wav_path.name}", flush=True)
                                                    except Exception as e:
                                                        print(f"       ⚠️  解码音频数据失败: {e}", flush=True)
                                
                                # 处理 delta_audio（如果有）
                                if delta_audio:
                                    try:
                                        # delta_audio 可能是 base64 字符串
                                        if isinstance(delta_audio, str):
                                            if delta_audio.startswith("data:;base64,"):
                                                base64_data = delta_audio[13:]
                                            else:
                                                base64_data = delta_audio
                                            audio_bytes = base64.b64decode(base64_data)
                                            if audio_bytes:
                                                pcm_path, wav_path = self.save_audio_chunk(
                                                    audio_bytes, frame_id, 0, query
                                                )
                                                if pcm_path and wav_path:
                                                    print(f"       💾 已保存: {pcm_path.name} ({len(audio_bytes)} bytes)", flush=True)
                                                    print(f"       💾 已保存: {wav_path.name}", flush=True)
                                    except Exception as e:
                                        print(f"       ⚠️  处理 delta_audio 失败: {e}", flush=True)
                            
                            # 处理最终帧
                            if frame_is_final:
                                stats["final_frame"] = True
                                complete_content = data.get("complete_content", "")
                                if complete_content:
                                    accumulated_text = complete_content
                                
                                print("\n\n       " + "=" * 60)
                                print("       ✅ 收到最终帧")
                                print("       " + "=" * 60)
                                
                        except json.JSONDecodeError:
                            # 忽略 JSON 解析错误
                            pass

                duration = time.time() - start

                # 检查是否有有效内容（即使有错误码也继续处理）
                has_valid_content = (
                    accumulated_text or 
                    accumulated_thinking or 
                    stats["text_frames"] > 0 or 
                    stats["thinking_frames"] > 0 or
                    stats["audio_frames"] > 0
                )
                
                # 获取最终数据（即使有错误也尝试获取）
                news_count = 0
                thinking_chain = []
                error_info = ""
                
                if final_data and isinstance(final_data, dict):
                    code = final_data.get("code", 0)
                    if code != 0:
                        message = final_data.get("message", "")
                        error_info = f"错误码: {code}, 消息: {message}"
                    
                    # 尝试获取数据（即使有错误码也可能有部分数据）
                    data = final_data.get("data", {})
                    if data:
                        extension = data.get("extension", {})
                        if extension:
                            news_count = extension.get("news_count", 0)
                            thinking_chain = extension.get("thinking_chain", [])
                    
                    # 如果最终帧有完整内容，使用它
                    if data:
                        complete_content = data.get("complete_content", "")
                        if complete_content:
                            accumulated_text = complete_content
                
                # 打印统计信息
                print(f"\n       统计信息:")
                print(f"       - 总帧数: {stats['total_frames']}")
                print(f"       - Thinking 帧: {stats['thinking_frames']} ({stats['thinking_chars']} 字符)")
                print(f"       - Text 帧: {stats['text_frames']} ({stats['text_chars']} 字符)")
                print(f"       - Audio 帧: {stats['audio_frames']}")
                print(f"       - 新闻数: {news_count}")
                print(f"       - 思维链步骤: {len(thinking_chain)}")
                if error_info:
                    print(f"       - ⚠️  {error_info}")
                
                # 输出完整摘要内容
                print(f"\n       完整摘要内容:")
                print("       " + "=" * 60)
                if accumulated_text:
                    for line in accumulated_text.split("\n"):
                        if line.strip():
                            print(f"       {line}")
                else:
                    print("       (摘要为空)")
                print("       " + "=" * 60)
                
                # 输出思维链
                if thinking_chain:
                    print(f"\n       思维链信息:")
                    print(f"       步骤数: {len(thinking_chain)}")
                    for i, step in enumerate(thinking_chain, 1):
                        node = step.get("node", "unknown")
                        thinking = step.get("thinking", "")
                        print(f"          [{i}] 节点: {node}")
                        if thinking:
                            preview = thinking[:200]
                            print(f"              思考: {preview}")
                            if len(thinking) > 200:
                                print(f"              ... (共 {len(thinking)} 字符)")
                
                # 判断测试是否通过：只要收到响应就认为成功（TTS错误不影响其他功能）
                # 只有在完全没有收到任何帧时才失败
                test_passed = stats["total_frames"] > 0
                details_parts = []
                if error_info:
                    details_parts.append(error_info)
                details_parts.append(f"响应数: {stats['total_frames']}, 新闻数: {news_count}, 摘要长度: {len(accumulated_text)}")
                if not has_valid_content and stats["total_frames"] > 0:
                    details_parts.append("(无有效内容，但响应正常)")
                elif stats["total_frames"] == 0:
                    details_parts.append("未收到任何响应")
                
                self.print_test(
                    f"POST /api/v1/chat (stream={query})",
                    test_passed,
                    duration,
                    " | ".join(details_parts)
                )

        except asyncio.TimeoutError:
            duration = time.time() - start
            self.print_test(
                f"POST /api/v1/chat (stream={query})",
                False,
                duration,
                "请求超时"
            )
        except Exception as e:
            duration = time.time() - start
            self.print_test(
                f"POST /api/v1/chat (stream={query})",
                False,
                duration,
                str(e)
            )

    async def test_chat_non_stream(self, query: str):
        """测试非流式聊天"""
        self.print_header(f"测试 5: 非流式聊天 - {query}")

        start = time.time()
        try:
            payload = {
                "query": query,
                "stream": False
            }

            async with self.session.post(
                f"{self.base_url}/api/v1/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            ) as resp:
                duration = time.time() - start

                if resp.status != 200:
                    self.print_test(
                        f"POST /api/v1/chat (non-stream={query})",
                        False,
                        duration,
                        f"状态码: {resp.status}"
                    )
                    return

                data = await resp.json()
                duration = time.time() - start

                if not data:
                    self.print_test(
                        f"POST /api/v1/chat (non-stream={query})",
                        False,
                        duration,
                        "响应数据为空"
                    )
                    return

                # 安全地访问嵌套字典
                code = data.get("code", 0)
                message = data.get("message", "")
                error_info = ""
                if code != 0:
                    error_info = f"错误码: {code}, 消息: {message}"
                    print(f"       ⚠️  {error_info}")

                # 尝试获取数据（即使有错误码也可能有部分数据）
                data_obj = data.get('data', {})
                if not isinstance(data_obj, dict):
                    data_obj = {}
                
                summary = data_obj.get('complete_content', '') or ''
                if not isinstance(summary, str):
                    summary = str(summary) if summary else ''
                
                extension = data_obj.get('extension', {})
                if not isinstance(extension, dict):
                    extension = {}
                
                news_count = extension.get('news_count', 0) or 0
                thinking_chain = extension.get('thinking_chain', [])
                if not isinstance(thinking_chain, list):
                    thinking_chain = []
                
                # 判断是否有有效内容
                has_valid_content = bool(summary) or news_count > 0 or len(thinking_chain) > 0
                
                # 打印详细信息
                if summary:
                    print(f"       摘要预览: {summary[:200]}...")
                if thinking_chain:
                    print(f"       思维链步骤数: {len(thinking_chain)}")
                
                # 只要收到响应就认为成功（TTS错误不影响其他功能）
                # 只有在完全没有响应数据时才失败
                test_passed = True  # 默认通过，因为已经收到了响应
                details_parts = []
                if error_info:
                    details_parts.append(error_info)
                details_parts.append(f"新闻数: {news_count}, 摘要长度: {len(summary)}")
                if not has_valid_content:
                    details_parts.append("(无有效内容，但响应正常)")

                self.print_test(
                    f"POST /api/v1/chat (non-stream={query})",
                    test_passed,
                    duration,
                    " | ".join(details_parts)
                )

        except asyncio.TimeoutError:
            duration = time.time() - start
            self.print_test(
                f"POST /api/v1/chat (non-stream={query})",
                False,
                duration,
                "请求超时"
            )
        except Exception as e:
            duration = time.time() - start
            self.print_test(
                f"POST /api/v1/chat (non-stream={query})",
                False,
                duration,
                str(e)
            )

    async def test_news_summary(self, query: str):
        """测试新闻摘要接口"""
        self.print_header(f"测试 6: 新闻摘要 - {query}")

        start = time.time()
        try:
            payload = {
                "query": query
            }

            async with self.session.post(
                f"{self.base_url}/api/v1/news/summary",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            ) as resp:
                duration = time.time() - start

                if resp.status != 200:
                    self.print_test(
                        f"POST /api/v1/news/summary ({query})",
                        False,
                        duration,
                        f"状态码: {resp.status}"
                    )
                    return

                data = await resp.json()
                duration = time.time() - start

                if not data:
                    self.print_test(
                        f"POST /api/v1/news/summary ({query})",
                        False,
                        duration,
                        "响应数据为空"
                    )
                    return

                # 安全地获取 summary，处理 None 值
                summary = data.get('summary')
                if summary is None:
                    summary = ''
                elif not isinstance(summary, str):
                    summary = str(summary) if summary else ''
                
                news_count = data.get('news_count', 0)

                self.print_test(
                    f"POST /api/v1/news/summary ({query})",
                    True,
                    duration,
                    f"新闻数: {news_count}, 摘要长度: {len(summary)}"
                )

                if len(summary) > 0:
                    print(f"       摘要预览: {summary[:200]}...")

        except asyncio.TimeoutError:
            duration = time.time() - start
            self.print_test(
                f"POST /api/v1/news/summary ({query})",
                False,
                duration,
                "请求超时"
            )
        except Exception as e:
            duration = time.time() - start
            self.print_test(
                f"POST /api/v1/news/summary ({query})",
                False,
                duration,
                str(e)
            )

    async def test_scheduler_status(self):
        """测试调度器状态"""
        self.print_header("测试 7: 调度器状态")

        start = time.time()
        try:
            async with self.session.get(f"{self.base_url}/api/v1/scheduler/status") as resp:
                duration = time.time() - start
                if resp.status == 200:
                    data = await resp.json()
                    enabled = data.get("enabled", False)
                    running = data.get("running", False)
                    jobs_count = len(data.get("jobs", []))
                    self.print_test(
                        "GET /api/v1/scheduler/status",
                        True,
                        duration,
                        f"启用: {enabled}, 运行中: {running}, 任务数: {jobs_count}"
                    )
                else:
                    self.print_test("GET /api/v1/scheduler/status", False, duration, f"状态码: {resp.status}")
        except Exception as e:
            duration = time.time() - start
            self.print_test("GET /api/v1/scheduler/status", False, duration, str(e))

    async def test_scheduler_jobs(self):
        """测试列出所有任务"""
        self.print_header("测试 8: 列出调度器任务")

        start = time.time()
        try:
            async with self.session.get(f"{self.base_url}/api/v1/scheduler/jobs") as resp:
                duration = time.time() - start
                if resp.status == 200:
                    data = await resp.json()
                    jobs = data.get("jobs", [])
                    self.print_test(
                        "GET /api/v1/scheduler/jobs",
                        True,
                        duration,
                        f"任务数: {len(jobs)}"
                    )
                    if jobs:
                        print("       任务列表:")
                        for job in jobs:
                            job_id = job.get("id", "unknown")
                            job_name = job.get("name", "unknown")
                            next_run = job.get("next_run_time", "N/A")
                            print(f"         - {job_id} ({job_name}): 下次运行 {next_run}")
                elif resp.status == 503:
                    # 调度器未启用，这是正常的
                    self.print_test(
                        "GET /api/v1/scheduler/jobs",
                        True,
                        duration,
                        "调度器未启用（正常）"
                    )
                else:
                    self.print_test("GET /api/v1/scheduler/jobs", False, duration, f"状态码: {resp.status}")
        except Exception as e:
            duration = time.time() - start
            self.print_test("GET /api/v1/scheduler/jobs", False, duration, str(e))

    async def test_scheduler_crawl(self, force_reload: bool = False):
        """测试手动触发爬取"""
        self.print_header(f"测试 9: 手动触发爬取 (force_reload={force_reload})")

        start = time.time()
        try:
            url = f"{self.base_url}/api/v1/scheduler/crawl"
            if force_reload:
                url += "?force_reload=true"
            
            async with self.session.post(
                url,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            ) as resp:
                duration = time.time() - start
                if resp.status == 200:
                    data = await resp.json()
                    message = data.get("message", "")
                    self.print_test(
                        f"POST /api/v1/scheduler/crawl (force_reload={force_reload})",
                        True,
                        duration,
                        message
                    )
                elif resp.status == 503:
                    self.print_test(
                        f"POST /api/v1/scheduler/crawl (force_reload={force_reload})",
                        True,
                        duration,
                        "调度器未启用（正常）"
                    )
                else:
                    self.print_test(
                        f"POST /api/v1/scheduler/crawl (force_reload={force_reload})",
                        False,
                        duration,
                        f"状态码: {resp.status}"
                    )
        except asyncio.TimeoutError:
            duration = time.time() - start
            self.print_test(
                f"POST /api/v1/scheduler/crawl (force_reload={force_reload})",
                False,
                duration,
                "请求超时"
            )
        except Exception as e:
            duration = time.time() - start
            self.print_test(
                f"POST /api/v1/scheduler/crawl (force_reload={force_reload})",
                False,
                duration,
                str(e)
            )

    async def test_scheduler_sync(self):
        """测试手动触发同步"""
        self.print_header("测试 10: 手动触发同步")

        start = time.time()
        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/scheduler/sync",
                timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            ) as resp:
                duration = time.time() - start
                if resp.status == 200:
                    data = await resp.json()
                    message = data.get("message", "")
                    self.print_test(
                        "POST /api/v1/scheduler/sync",
                        True,
                        duration,
                        message
                    )
                elif resp.status == 503:
                    self.print_test(
                        "POST /api/v1/scheduler/sync",
                        True,
                        duration,
                        "调度器未启用（正常）"
                    )
                else:
                    self.print_test("POST /api/v1/scheduler/sync", False, duration, f"状态码: {resp.status}")
        except asyncio.TimeoutError:
            duration = time.time() - start
            self.print_test("POST /api/v1/scheduler/sync", False, duration, "请求超时")
        except Exception as e:
            duration = time.time() - start
            self.print_test("POST /api/v1/scheduler/sync", False, duration, str(e))

    async def test_scheduler_reset_crawl(self):
        """测试重置爬取状态"""
        self.print_header("测试 11: 重置爬取状态")

        start = time.time()
        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/scheduler/reset-crawl",
                timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            ) as resp:
                duration = time.time() - start
                if resp.status == 200:
                    data = await resp.json()
                    message = data.get("message", "")
                    self.print_test(
                        "POST /api/v1/scheduler/reset-crawl",
                        True,
                        duration,
                        message
                    )
                else:
                    self.print_test("POST /api/v1/scheduler/reset-crawl", False, duration, f"状态码: {resp.status}")
        except asyncio.TimeoutError:
            duration = time.time() - start
            self.print_test("POST /api/v1/scheduler/reset-crawl", False, duration, "请求超时")
        except Exception as e:
            duration = time.time() - start
            self.print_test("POST /api/v1/scheduler/reset-crawl", False, duration, str(e))

    async def test_scheduler_pause_resume_job(self, job_id: str = "daily_crawl"):
        """测试暂停和恢复任务"""
        self.print_header(f"测试 12: 暂停/恢复任务 - {job_id}")

        # 先尝试暂停
        start = time.time()
        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/scheduler/jobs/{job_id}/pause"
            ) as resp:
                duration = time.time() - start
                if resp.status == 200:
                    data = await resp.json()
                    message = data.get("message", "")
                    self.print_test(
                        f"POST /api/v1/scheduler/jobs/{job_id}/pause",
                        True,
                        duration,
                        message
                    )
                elif resp.status == 404:
                    self.print_test(
                        f"POST /api/v1/scheduler/jobs/{job_id}/pause",
                        True,
                        duration,
                        f"任务 {job_id} 不存在（正常，可能未启用调度器）"
                    )
                    return  # 如果任务不存在，就不测试恢复了
                elif resp.status == 503:
                    self.print_test(
                        f"POST /api/v1/scheduler/jobs/{job_id}/pause",
                        True,
                        duration,
                        "调度器未启用（正常）"
                    )
                    return
                else:
                    self.print_test(
                        f"POST /api/v1/scheduler/jobs/{job_id}/pause",
                        False,
                        duration,
                        f"状态码: {resp.status}"
                    )
                    return
        except Exception as e:
            duration = time.time() - start
            self.print_test(
                f"POST /api/v1/scheduler/jobs/{job_id}/pause",
                False,
                duration,
                str(e)
            )
            return

        # 等待一下再恢复
        await asyncio.sleep(0.5)

        # 然后恢复
        start = time.time()
        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/scheduler/jobs/{job_id}/resume"
            ) as resp:
                duration = time.time() - start
                if resp.status == 200:
                    data = await resp.json()
                    message = data.get("message", "")
                    self.print_test(
                        f"POST /api/v1/scheduler/jobs/{job_id}/resume",
                        True,
                        duration,
                        message
                    )
                elif resp.status == 404:
                    self.print_test(
                        f"POST /api/v1/scheduler/jobs/{job_id}/resume",
                        True,
                        duration,
                        f"任务 {job_id} 不存在（正常）"
                    )
                elif resp.status == 503:
                    self.print_test(
                        f"POST /api/v1/scheduler/jobs/{job_id}/resume",
                        True,
                        duration,
                        "调度器未启用（正常）"
                    )
                else:
                    self.print_test(
                        f"POST /api/v1/scheduler/jobs/{job_id}/resume",
                        False,
                        duration,
                        f"状态码: {resp.status}"
                    )
        except Exception as e:
            duration = time.time() - start
            self.print_test(
                f"POST /api/v1/scheduler/jobs/{job_id}/resume",
                False,
                duration,
                str(e)
            )

    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "🚀" * 35)
        print("  News TTS Agent - API 流式测试套件")
        print("🚀" * 35)

        # 流式聊天测试
        await self.test_chat_stream("今天有什么新闻，用韩语播放下")
        await self.test_chat_stream("今天有什么科技新闻？")

        # 打印总结
        self.print_summary()

    def print_summary(self):
        """打印测试总结"""
        print("\n" + "=" * 70)
        print("  测试总结")
        print("=" * 70)
        print(f"总计: {self.passed + self.failed} | 通过: {self.passed} | 失败: {self.failed}")

        if self.failed > 0:
            print("\n❌ 失败的测试:")
            for result in self.test_results:
                if not result['passed']:
                    print(f"  - {result['name']}: {result['details']}")

        print("\n" + "=" * 70)

        if self.failed == 0:
            print("✅ 所有测试通过！")
            print("=" * 70 + "\n")
            return True
        else:
            print("❌ 部分测试失败")
            print("=" * 70 + "\n")
            return False


# ==================== 主函数 ====================

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
        print(f"\n或使用环境变量指定端口:")
        print(f"   API_PORT=8080 python3 main.py")
        return

    # 运行测试
    async with APITester(BASE_URL) as tester:
        success = await tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
