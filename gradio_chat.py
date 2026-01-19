"""
Gradio 聊天界面 - 用于测试 News TTS Agent 服务
提供全面的信息展示，包括流式响应、Token统计、调试信息等
支持以列表形式展示每个帧的响应（思考、文本、图片、音频）
"""
import os
import json
import time
import base64
import tempfile
import httpx
import gradio as gr
from typing import Optional, Tuple, List, Dict, Union
from datetime import datetime
from pathlib import Path


# ==================== 配置 ====================

DEFAULT_API_URL = os.getenv("API_URL", "http://localhost:8080")
CHAT_ENDPOINT = f"{DEFAULT_API_URL}/api/v1/chat"
STATS_ENDPOINT = f"{DEFAULT_API_URL}/api/v1/stats"
HEALTH_ENDPOINT = f"{DEFAULT_API_URL}/health"

# 临时文件目录
TEMP_DIR = Path(tempfile.gettempdir()) / "news_tts_agent"
TEMP_DIR.mkdir(exist_ok=True)


# ==================== 工具函数 ====================

def parse_sse_line(line: str) -> Optional[dict]:
    """解析SSE格式的数据行"""
    if not line.strip():
        return None
    
    # SSE格式: event:data\ndata:{json}
    # 跳过event行
    if line.startswith("event:"):
        return None
    
    if line.startswith("data:"):
        json_str = line[5:].strip()  # 移除 "data:" 前缀
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            # 调试：打印解析失败的JSON
            print(f"JSON解析失败: {e}, 内容: {json_str[:200]}")
            return None
    
    return None


def format_timestamp(ts: Optional[int]) -> str:
    """格式化时间戳"""
    if ts is None:
        return "N/A"
    try:
        dt = datetime.fromtimestamp(ts / 1000)
        return dt.strftime("%H:%M:%S.%f")[:-3]
    except:
        return str(ts)


def extract_audio_data(audio_data: str, frame_id: int, return_bytes: bool = False) -> Optional[Union[str, bytes]]:
    """
    从base64音频数据中提取并保存为临时文件或返回原始PCM数据
    
    Args:
        audio_data: base64编码的音频数据（可能包含data URI前缀）
        frame_id: 帧ID，用于生成唯一文件名
        return_bytes: 如果为True，返回PCM字节数据；否则返回WAV文件路径
    
    Returns:
        临时文件路径或PCM字节数据，如果提取失败则返回None
    """
    if not audio_data:
        return None
    
    try:
        # 提取base64数据
        base64_data = None
        if audio_data.startswith("data:;base64,"):
            base64_data = audio_data[len("data:;base64,"):]
        elif audio_data.startswith("data:audio/"):
            base64_data = audio_data.split(",", 1)[1] if "," in audio_data else ""
        elif audio_data.startswith("data:"):
            base64_data = audio_data.split(",", 1)[1] if "," in audio_data else ""
        else:
            # 假设已经是base64数据
            base64_data = audio_data
        
        if not base64_data:
            return None
        
        # 解码base64数据
        audio_bytes = base64.b64decode(base64_data)
        
        # 如果只需要返回字节数据
        if return_bytes:
            return audio_bytes
        
        # 创建临时文件（PCM格式，单声道24000Hz）
        audio_file = TEMP_DIR / f"audio_frame_{frame_id}_{int(time.time() * 1000)}.wav"
        
        # 简单的WAV文件头（PCM，单声道，24000Hz，16bit）
        # 注意：这里假设是PCM格式，实际可能需要根据format字段调整
        wav_header = b'RIFF'
        wav_header += (36 + len(audio_bytes)).to_bytes(4, 'little')
        wav_header += b'WAVE'
        wav_header += b'fmt '
        wav_header += (16).to_bytes(4, 'little')  # fmt chunk size
        wav_header += (1).to_bytes(2, 'little')    # audio format (PCM)
        wav_header += (1).to_bytes(2, 'little')    # num channels (mono)
        wav_header += (24000).to_bytes(4, 'little')  # sample rate
        wav_header += (48000).to_bytes(4, 'little')  # byte rate
        wav_header += (2).to_bytes(2, 'little')    # block align
        wav_header += (16).to_bytes(2, 'little')   # bits per sample
        wav_header += b'data'
        wav_header += len(audio_bytes).to_bytes(4, 'little')
        
        with open(audio_file, 'wb') as f:
            f.write(wav_header + audio_bytes)
        
        return str(audio_file)
    except Exception as e:
        print(f"音频解码失败: {e}")
        return None


def merge_audio_chunks(audio_chunks: List[bytes], output_file: str, sample_rate: int = 24000) -> Optional[str]:
    """
    合并多个PCM音频块为一个WAV文件
    
    Args:
        audio_chunks: PCM音频块列表
        output_file: 输出文件路径
        sample_rate: 采样率（默认24000Hz）
    
    Returns:
        合并后的文件路径，如果失败则返回None
    """
    if not audio_chunks:
        return None
    
    try:
        # 合并所有音频块
        merged_audio = b''.join(audio_chunks)
        
        # 创建WAV文件头
        wav_header = b'RIFF'
        wav_header += (36 + len(merged_audio)).to_bytes(4, 'little')
        wav_header += b'WAVE'
        wav_header += b'fmt '
        wav_header += (16).to_bytes(4, 'little')  # fmt chunk size
        wav_header += (1).to_bytes(2, 'little')    # audio format (PCM)
        wav_header += (1).to_bytes(2, 'little')    # num channels (mono)
        wav_header += (sample_rate).to_bytes(4, 'little')  # sample rate
        wav_header += (sample_rate * 2).to_bytes(4, 'little')  # byte rate (sample_rate * channels * bits_per_sample / 8)
        wav_header += (2).to_bytes(2, 'little')    # block align
        wav_header += (16).to_bytes(2, 'little')   # bits per sample
        wav_header += b'data'
        wav_header += len(merged_audio).to_bytes(4, 'little')
        
        # 写入文件
        with open(output_file, 'wb') as f:
            f.write(wav_header + merged_audio)
        
        print(f"✅ 合并音频成功: {output_file} (共 {len(audio_chunks)} 个块, {len(merged_audio)} 字节)")
        return output_file
    except Exception as e:
        print(f"⚠️ 合并音频失败: {e}")
        return None


def extract_image_data(image_data: str, frame_id: int, image_index: int) -> Optional[str]:
    """
    从图片URL或base64数据中提取并保存为临时文件
    
    Args:
        image_data: 图片URL或base64数据
        frame_id: 帧ID
        image_index: 图片索引
    
    Returns:
        临时文件路径或URL，如果提取失败则返回None
    """
    if not image_data:
        return None
    
    try:
        # 如果是URL，直接返回
        if image_data.startswith("http://") or image_data.startswith("https://"):
            return image_data
        
        # 如果是base64数据
        if image_data.startswith("data:image/"):
            # 提取格式和base64数据
            header, base64_data = image_data.split(",", 1)
            format_match = header.split("/")[1].split(";")[0]  # 提取格式如 jpeg, png
            
            # 解码base64数据
            image_bytes = base64.b64decode(base64_data)
            
            # 创建临时文件
            image_file = TEMP_DIR / f"image_frame_{frame_id}_{image_index}_{int(time.time() * 1000)}.{format_match}"
            
            with open(image_file, 'wb') as f:
                f.write(image_bytes)
            
            return str(image_file)
        else:
            # 假设是纯base64数据
            image_bytes = base64.b64decode(image_data)
            image_file = TEMP_DIR / f"image_frame_{frame_id}_{image_index}_{int(time.time() * 1000)}.jpg"
            
            with open(image_file, 'wb') as f:
                f.write(image_bytes)
            
            return str(image_file)
    except Exception as e:
        print(f"图片提取失败: {e}")
        return None


def format_frame_for_display(frame_data: dict, full_response_data: dict = None) -> str:
    """
    格式化帧数据用于显示
    
    Args:
        frame_data: 帧数据字典
        full_response_data: 完整的响应数据（用于显示JSON）
    
    Returns:
        格式化的HTML字符串
    """
    import html
    
    frame_id = frame_data.get("frame_id", "N/A")
    timestamp = format_timestamp(frame_data.get("frame_timestamp"))
    response_type = frame_data.get("response_type", "unknown")
    is_final = frame_data.get("frame_is_final", False)
    
    # 获取显示文本：最终帧优先使用complete_content，否则使用frame_text
    complete_content = frame_data.get("complete_content")
    frame_text = complete_content if complete_content else frame_data.get("frame_text", "")
    
    frame_parts = frame_data.get("frame_parts", [])
    extension = frame_data.get("extension", {})
    
    # 构建HTML - 改进的排版
    html_parts = []
    # 外层容器 - 改进的样式
    html_parts.append(f"<div class='frame-item' style='border: 1px solid #e0e0e0; padding: 15px; margin: 8px 0; border-radius: 8px; background-color: #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); transition: all 0.2s;'>")
    
    # 头部：Frame ID、时间戳和类型标签
    html_parts.append(f"<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #f0f0f0;'>")
    html_parts.append(f"<div style='display: flex; align-items: center; gap: 10px;'>")
    html_parts.append(f"<strong style='font-size: 1.1em; color: #333;'>Frame #{frame_id}</strong>")
    
    # 类型标签 - 改进的样式
    type_colors = {
        "thinking": "#FF9800",
        "text": "#4CAF50",
        "audio": "#2196F3",
        "image": "#9C27B0",
        "final": "#F44336",
        "unknown": "#757575"
    }
    type_color = type_colors.get(response_type, "#757575")
    html_parts.append(f"<span style='background-color: {type_color}; color: white; padding: 4px 10px; border-radius: 4px; font-size: 0.85em; font-weight: 500;'>{response_type.upper()}</span>")
    if is_final:
        html_parts.append(f"<span style='background-color: #F44336; color: white; padding: 4px 10px; border-radius: 4px; font-size: 0.85em; font-weight: 500;'>FINAL</span>")
    html_parts.append(f"</div>")
    html_parts.append(f"<span style='color: #888; font-size: 0.9em; font-family: monospace;'>{timestamp}</span>")
    html_parts.append(f"</div>")
    
    # 内容区域 - 显示frame_text（流式帧的增量内容或最终帧的完整内容）
    content = frame_text or ""
    if content and not (is_final and complete_content):  # 最终帧的完整内容单独显示，这里不重复
        html_parts.append(f"<div style='margin-bottom: 12px; padding: 12px; background: linear-gradient(to bottom, #f8f9fa, #ffffff); border-left: 3px solid {type_color}; border-radius: 4px;'>")
        html_parts.append(f"<div style='font-weight: 600; color: #555; margin-bottom: 6px; font-size: 0.9em;'>📝 {'完整内容' if is_final else '增量内容'}</div>")
        html_parts.append(f"<div style='white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word; color: #333; line-height: 1.6; font-size: 0.95em;'>{html.escape(content[:500])}{'...' if len(content) > 500 else ''}</div>")
        html_parts.append(f"</div>")
    
    # 扩展信息 - 思考内容（优先从extension获取，最终帧包含完整内容）
    if extension:
        thinking_content = extension.get("thinking_content")
        if thinking_content:
            html_parts.append(f"<div style='margin-bottom: 12px; padding: 12px; background-color: #FFF8E1; border-left: 3px solid #FFC107; border-radius: 4px;'>")
            html_parts.append(f"<div style='font-weight: 600; color: #555; margin-bottom: 6px; font-size: 0.9em;'>🧠 思考过程</div>")
            # 最终帧显示完整内容，流式帧显示预览
            preview_length = 500 if is_final else 300
            html_parts.append(f"<div style='white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word; color: #666; line-height: 1.6; font-size: 0.9em;'>{html.escape(thinking_content[:preview_length])}{'...' if len(thinking_content) > preview_length else ''}</div>")
            html_parts.append(f"</div>")
    
    # 最终帧特殊标记
    if is_final and complete_content:
        html_parts.append(f"<div style='margin-bottom: 12px; padding: 12px; background-color: #E8F5E9; border-left: 3px solid #4CAF50; border-radius: 4px;'>")
        html_parts.append(f"<div style='font-weight: 600; color: #2E7D32; margin-bottom: 6px; font-size: 0.9em;'>✅ 完整响应内容</div>")
        html_parts.append(f"<div style='white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word; color: #333; line-height: 1.6; font-size: 0.95em;'>{html.escape(complete_content[:500])}{'...' if len(complete_content) > 500 else ''}</div>")
        html_parts.append(f"</div>")
    
    # 多模态内容 - 改进的样式
    if frame_parts:
        for i, part in enumerate(frame_parts):
            if not part or not isinstance(part, dict):
                continue
            part_type = part.get("type", "unknown")
            if part_type == "audio":
                audio_info = part.get("audio", {})
                html_parts.append(f"<div style='margin-bottom: 10px; padding: 10px; background-color: #E3F2FD; border-left: 3px solid #2196F3; border-radius: 4px;'>")
                html_parts.append(f"<div style='font-weight: 600; color: #1976D2; margin-bottom: 4px; font-size: 0.9em;'>🎵 音频 #{i+1}</div>")
                html_parts.append(f"<div style='color: #555; font-size: 0.9em;'>格式: {audio_info.get('format', 'unknown')}")
                if audio_info.get("is_final"):
                    html_parts.append(" <span style='color: #4CAF50; font-weight: 600;'>(最终)</span>")
                html_parts.append(f"</div>")
                html_parts.append(f"</div>")
            elif part_type == "image":
                image_info = part.get("image", {})
                html_parts.append(f"<div style='margin-bottom: 10px; padding: 10px; background-color: #F3E5F5; border-left: 3px solid #9C27B0; border-radius: 4px;'>")
                html_parts.append(f"<div style='font-weight: 600; color: #7B1FA2; margin-bottom: 6px; font-size: 0.9em;'>🖼️ 图片 #{i+1}</div>")
                html_parts.append(f"<div style='color: #555; font-size: 0.9em; margin-bottom: 6px;'>格式: {image_info.get('format', 'unknown')}</div>")
                image_url = image_info.get("data", "")
                if image_url:
                    if os.path.exists(image_url) and not image_url.startswith(("http://", "https://")):
                        html_parts.append(f"<div style='padding: 8px; background-color: #fff; border: 1px solid #ddd; border-radius: 4px; font-size: 0.85em; color: #666;'>")
                        html_parts.append(f"📁 本地文件: {html.escape(image_url)}")
                        html_parts.append(f"</div>")
                    else:
                        if image_url.startswith("data:image/"):
                            html_parts.append(f"<img src='{html.escape(image_url)}' style='max-width: 100%; max-height: 200px; margin-top: 6px; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);' />")
                        else:
                            html_parts.append(f"<img src='{html.escape(image_url)}' style='max-width: 100%; max-height: 200px; margin-top: 6px; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);' onerror='this.style.display=\"none\"; this.nextElementSibling.style.display=\"block\";' />")
                            html_parts.append(f"<div style='display: none; padding: 8px; background-color: #ffebee; border: 1px solid #ef5350; border-radius: 4px; font-size: 0.85em; color: #c62828;'>❌ 无法加载图片: {html.escape(image_url)}</div>")
                html_parts.append(f"</div>")
    
    # 完整响应JSON按钮 - 改进的样式和位置
    if full_response_data:
        json_str = json.dumps(full_response_data, ensure_ascii=False, indent=2)
        json_id = f"frame_json_{frame_id}"
        toggle_id = f"toggle_{json_id}"
        html_parts.append(f"<div style='margin-top: 12px; padding-top: 12px; border-top: 1px solid #f0f0f0;'>")
        html_parts.append(f"<button type='button' id='{toggle_id}' onclick=\"var x = document.getElementById('{json_id}'); var btn = document.getElementById('{toggle_id}'); if (x.style.display === 'none' || !x.style.display) {{ x.style.display = 'block'; btn.innerHTML = '📋 隐藏完整响应'; btn.style.backgroundColor = '#495057'; }} else {{ x.style.display = 'none'; btn.innerHTML = '📋 显示完整响应'; btn.style.backgroundColor = '#6c757d'; }}\" style='background-color: #6c757d; color: white; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer; font-size: 0.9em; font-weight: 500; transition: background-color 0.2s; width: 100%;'>")
        html_parts.append(f"📋 显示完整响应")
        html_parts.append(f"</button>")
        html_parts.append(f"<div id='{json_id}' style='display: none; margin-top: 12px; padding: 12px; background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; max-height: 500px; overflow-y: auto; box-shadow: inset 0 2px 4px rgba(0,0,0,0.06);'>")
        html_parts.append(f"<div style='font-weight: 600; color: #495057; margin-bottom: 8px; font-size: 0.9em;'>📄 Frame #{frame_id} 完整响应数据</div>")
        html_parts.append(f"<pre style='white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word; margin: 0; font-size: 0.85em; line-height: 1.5; color: #212529; font-family: 'Consolas', 'Monaco', 'Courier New', monospace;'>{html.escape(json_str)}</pre>")
        html_parts.append(f"</div>")
        html_parts.append(f"</div>")
    
    html_parts.append("</div>")
    
    return "".join(html_parts)


# ==================== 核心功能 ====================

async def submit_query_stream(
    query: str,
    stream_enabled: bool,
    debug: bool,
    history: List[Dict[str, str]]
):
    """
    提交查询并返回流式响应（生成器函数，用于实时更新）
    
    Yields:
        (history, complete_text, frames_html, merged_audio_file, audio_files, image_files, raw_json)
        其中 merged_audio_file 是合并后的完整音频文件路径（用于播放）
        audio_files 包含所有音频文件列表（包括合并后的文件）
    """
    if not query.strip():
        yield history, "", "<div style='text-align: center; color: #999; padding: 20px;'>等待响应...</div>", [], [], ""
        return
    
    # 生成请求ID
    request_id = f"gradio_{int(time.time() * 1000)}"
    
    # 构建请求
    request_data = {
        "query": query,
        "request_id": request_id,
        "stream": stream_enabled,
        "debug": debug
    }
    
    # 初始化响应变量
    complete_text = ""  # 最终完整文本（从final帧的complete_content获取）
    audio_files = []  # 存储音频文件路径
    audio_chunks = []  # 存储所有音频块（PCM数据），用于合并
    image_files = []  # 存储图片文件路径或URL
    raw_json = ""  # 最终帧的原始JSON
    streaming_text = ""  # 流式累积的文本内容
    thinking_content = ""  # 累积的思考内容
    merged_audio_file = None  # 合并后的最终音频文件
    
    # 更新历史记录
    new_history = history.copy() if history else []
    new_history.append({"role": "user", "content": query})
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                CHAT_ENDPOINT,
                json=request_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status_code != 200:
                    error_msg = f"请求失败: HTTP {response.status_code}\n{await response.aread()}"
                    new_history.append({"role": "assistant", "content": error_msg})
                    yield new_history, "", "<div style='text-align: center; color: #f00; padding: 20px;'>" + error_msg + "</div>", None, [], [], error_msg
                    return
                
                # 解析SSE流并实时更新（使用缓冲区方式，与test_api.py一致）
                final_response = None
                buffer = ""
                
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue
                    
                    buffer += chunk.decode("utf-8", errors="ignore")
                    
                    # 按行处理缓冲区
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        
                        if not line or not line.startswith("data:"):
                            continue
                        
                        data_str = line[5:].strip()  # 移除 "data:" 前缀
                        if data_str in ("", "[DONE]"):
                            continue
                        
                        try:
                            data = json.loads(data_str)
                            final_response = data
                            
                            # 检查错误响应
                            code = data.get("code", 0)
                            if code != 0:
                                error_msg = data.get("message", "未知错误")
                                new_history.append({"role": "assistant", "content": f"❌ 错误: {error_msg}"})
                                yield new_history, "", "<div style='text-align: center; color: #f00; padding: 20px;'>" + error_msg + "</div>", None, [], [], json.dumps(data, ensure_ascii=False, indent=2)
                                return
                            
                            if "data" not in data:
                                continue
                            
                            response_data = data.get("data", {})
                            if not response_data:
                                continue
                            
                            frame_id = response_data.get("frame_id", 0)
                            response_type = response_data.get("response_type", "")
                            extension = response_data.get("extension") or {}
                            token_type = extension.get("token_type", "") if extension else ""
                            
                            # 检查是否为最终帧
                            is_final = response_data.get("frame_is_final", False)
                            
                            # 获取内容：最终帧使用complete_content，流式帧使用frame_text
                            if is_final:
                                # 最终帧：complete_content包含完整内容，frame_text为空
                                complete_content = response_data.get("complete_content", "")
                                frame_text = complete_content  # 用于显示
                                # 更新完整文本
                                if complete_content:
                                    complete_text = complete_content
                                    streaming_text = complete_content  # 同步更新流式文本
                            else:
                                # 流式帧：frame_text包含增量内容
                                frame_text = response_data.get("frame_text", "")
                            
                            # 确定实际的响应类型（优先使用token_type）
                            if token_type == "thinking" or response_type == "thinking":
                                actual_type = "thinking"
                            elif token_type == "content" or response_type == "text" or (frame_text and not response_type):
                                actual_type = "text"
                            elif response_type == "audio" or token_type == "audio":
                                actual_type = "audio"
                            else:
                                actual_type = response_type or "unknown"
                            
                            # 累积thinking内容 - 流式帧使用frame_text，最终帧使用extension.thinking_content
                            if is_final:
                                # 最终帧：从extension中获取完整的thinking内容
                                if extension.get("thinking_content"):
                                    thinking_content = extension["thinking_content"]
                            else:
                                # 流式帧：累积frame_text中的thinking内容
                                if actual_type == "thinking" and frame_text:
                                    thinking_content += frame_text
                            
                            # 累积文本内容 - 仅流式帧需要累积
                            if not is_final and actual_type == "text" and frame_text:
                                streaming_text += frame_text
                            
                            # 构建聊天框显示内容：包含thinking和普通文本
                            # thinking内容用Markdown格式显示（引用格式和斜体）
                            display_parts = []
                            if thinking_content:
                                # 使用Markdown格式显示thinking内容（引用块 + 斜体）
                                display_parts.append(f"> *💭 思考过程：{thinking_content}*")
                            if streaming_text:
                                display_parts.append(streaming_text)
                            
                            # 组合显示文本
                            combined_display_text = "\n\n".join(display_parts) if display_parts else ""
                            
                            # 构建帧数据
                            frame_parts_for_data = response_data.get("frame_parts") or []
                            frame_data = {
                                "frame_id": frame_id,
                                "frame_timestamp": response_data.get("frame_timestamp"),
                                "response_type": actual_type,
                                "frame_text": frame_text,  # 增量文本或完整内容
                                "frame_parts": frame_parts_for_data,
                                "extension": extension or {},
                                "frame_is_final": is_final,
                                "complete_content": response_data.get("complete_content") if is_final else None
                            }
                            
                            # 处理音频和图片（使用上面已经获取的frame_parts_for_data）
                            # 注意：音频帧的 response_type 是 "audio"，音频数据在 frame_parts 中
                            for part in frame_parts_for_data:
                                if not part or not isinstance(part, dict):
                                    continue
                                if part.get("type") == "audio":
                                    audio_info = part.get("audio", {})
                                    audio_data = audio_info.get("data", "")
                                    if audio_data:
                                        try:
                                            # 只提取PCM字节数据用于合并，不保存单个文件
                                            audio_bytes = extract_audio_data(audio_data, frame_id, return_bytes=True)
                                            if audio_bytes:
                                                audio_chunks.append(audio_bytes)
                                                print(f"✅ 提取音频块成功: Frame #{frame_id}, 大小={len(audio_bytes)} 字节")
                                        except Exception as e:
                                            print(f"⚠️ 提取音频块失败 (Frame #{frame_id}): {e}", flush=True)
                                elif part.get("type") == "image":
                                    image_info = part.get("image", {})
                                    image_data = image_info.get("data", "")
                                    if image_data:
                                        image_file = extract_image_data(image_data, frame_id, len(image_files))
                                        if image_file and image_file not in image_files:
                                            image_files.append(image_file)
                            
                            # 调试：打印音频帧信息
                            if actual_type == "audio":
                                print(f"🔊 收到音频帧: Frame #{frame_id}, frame_parts数量={len(frame_parts_for_data)}", flush=True)
                            
                            # 不再保存帧列表，只在最终帧时生成简单的HTML显示
                            frames_html = "<div style='text-align: center; color: #999; padding: 20px;'>流式响应中，帧列表已禁用以提升性能...</div>"
                            
                            # 实时更新聊天记录（流式文本或完整内容，包含thinking）
                            temp_history = new_history.copy()
                            
                            # 确定显示文本：最终帧优先使用complete_content，否则使用组合的显示文本
                            if is_final and complete_text:
                                # 最终帧：如果有thinking内容，也一起显示
                                final_display_parts = []
                                if thinking_content:
                                    final_display_parts.append(f"> *💭 思考过程：{thinking_content}*")
                                final_display_parts.append(complete_text)
                                display_text = "\n\n".join(final_display_parts)
                            else:
                                # 流式帧：使用组合的显示文本
                                display_text = combined_display_text
                            
                            if display_text:
                                temp_history.append({"role": "assistant", "content": display_text})
                            
                            # 如果是最终帧，保存原始JSON并合并音频
                            if is_final:
                                raw_json = json.dumps(data, ensure_ascii=False, indent=2)
                                
                                # 合并所有音频块为最终文件
                                if audio_chunks:
                                    merged_file_name = f"merged_audio_{request_id}_{int(time.time() * 1000)}.wav"
                                    merged_file_path = TEMP_DIR / merged_file_name
                                    merged_audio_file = merge_audio_chunks(audio_chunks, str(merged_file_path))
                                    if merged_audio_file:
                                        # 将合并后的文件添加到文件列表的最前面
                                        audio_files.insert(0, merged_audio_file)
                            
                            # 实时yield更新（返回合并后的音频文件）
                            merged_audio_for_display = merged_audio_file if merged_audio_file else (audio_files[0] if audio_files else None)
                            yield temp_history, display_text, frames_html, merged_audio_for_display, audio_files, image_files, raw_json if is_final else ""
                            
                        except json.JSONDecodeError as e:
                            # 忽略JSON解析错误，继续处理下一行
                            continue
                        except Exception as e:
                            # 其他错误也忽略，继续处理
                            print(f"处理帧数据时出错: {e}")
                            continue
                
                # 最终合并音频（如果还没有合并）
                if audio_chunks and not merged_audio_file:
                    merged_file_name = f"merged_audio_{request_id}_{int(time.time() * 1000)}.wav"
                    merged_file_path = TEMP_DIR / merged_file_name
                    merged_audio_file = merge_audio_chunks(audio_chunks, str(merged_file_path))
                    if merged_audio_file:
                        # 只保存合并后的文件
                        audio_files = [merged_audio_file]
                
                # 生成最终帧信息显示
                if not frames_html or frames_html == "<div style='text-align: center; color: #999; padding: 20px;'>流式响应中，帧列表已禁用以提升性能...</div>":
                    frames_html = "<div style='padding: 15px; background-color: #f8f9fa; border-radius: 8px;'>"
                    frames_html += "<div style='font-weight: 600; color: #333; margin-bottom: 10px;'>✅ 响应完成</div>"
                    if thinking_content:
                        frames_html += f"<div style='color: #666; font-size: 0.9em; margin-top: 8px;'>思考内容长度: {len(thinking_content)} 字符</div>"
                    if complete_text:
                        frames_html += f"<div style='color: #666; font-size: 0.9em; margin-top: 8px;'>响应文本长度: {len(complete_text)} 字符</div>"
                    elif streaming_text:
                        frames_html += f"<div style='color: #666; font-size: 0.9em; margin-top: 8px;'>响应文本长度: {len(streaming_text)} 字符</div>"
                    frames_html += "</div>"
                
                # 最终更新历史记录（包含thinking内容）
                final_history = new_history.copy()
                final_display_parts = []
                
                # 添加thinking内容（如果有）
                if thinking_content:
                    final_display_parts.append(f"> *💭 思考过程：{thinking_content}*")
                
                # 添加最终文本内容
                if complete_text:
                    final_display_parts.append(complete_text)
                elif streaming_text:
                    final_display_parts.append(streaming_text)
                else:
                    final_display_parts.append("⚠️ 未收到有效响应文本")
                
                # 组合最终显示文本
                final_display_text = "\n\n".join(final_display_parts)
                final_history.append({"role": "assistant", "content": final_display_text})
                
                # 最终yield（包含合并后的音频文件）
                merged_audio_for_display = merged_audio_file if merged_audio_file else None
                yield final_history, complete_text, frames_html, merged_audio_for_display, audio_files, image_files, raw_json
    
    except httpx.ConnectError as e:
        error_msg = f"❌ 连接失败: 无法连接到 {CHAT_ENDPOINT}\n请确认服务是否已启动: python main.py"
        new_history.append({"role": "assistant", "content": error_msg})
        yield new_history, "", "<div style='text-align: center; color: #f00; padding: 20px;'>" + error_msg + "</div>", None, [], [], json.dumps({"error": str(e), "type": "ConnectError"}, ensure_ascii=False, indent=2)
    except httpx.TimeoutException:
        error_msg = f"❌ 请求超时: 服务器响应时间过长（超过120秒）"
        new_history.append({"role": "assistant", "content": error_msg})
        yield new_history, "", "<div style='text-align: center; color: #f00; padding: 20px;'>" + error_msg + "</div>", None, [], [], json.dumps({"error": "Request timeout"}, ensure_ascii=False, indent=2)
    except Exception as e:
        error_msg = f"❌ 请求失败: {str(e)}"
        new_history.append({"role": "assistant", "content": error_msg})
        import traceback
        error_trace = traceback.format_exc()
        error_json = {
            "error": str(e),
            "type": type(e).__name__,
            "traceback": error_trace
        }
        raw_json = json.dumps(error_json, ensure_ascii=False, indent=2)
        yield new_history, "", "<div style='text-align: center; color: #f00; padding: 20px;'>" + error_msg + "</div>", None, [], [], raw_json


def get_system_stats() -> str:
    """获取系统统计信息"""
    try:
        response = httpx.get(STATS_ENDPOINT, timeout=10.0)
        if response.status_code == 200:
            stats = response.json()
            
            lines = []
            lines.append("### 系统统计信息")
            lines.append("")
            
            # 数据库统计
            if "database" in stats:
                db_stats = stats["database"]
                lines.append("#### 数据库")
                lines.append(f"- **总新闻数**: {db_stats.get('total_news', 0):,}")
                lines.append(f"- **今日新闻**: {db_stats.get('today_count', 0):,}")
                
                if "categories" in db_stats:
                    lines.append("- **分类统计**:")
                    for cat in db_stats["categories"]:
                        lines.append(f"  - {cat.get('category', '未知')}: {cat.get('count', 0)}")
            
            # 服务状态
            if "service" in stats:
                service_stats = stats["service"]
                lines.append("")
                lines.append("#### 服务状态")
                lines.append(f"- **状态**: {service_stats.get('status', 'unknown')}")
                lines.append(f"- **编排器**: {service_stats.get('orchestrator', 'unknown')}")
            
            return "\n".join(lines)
        else:
            return f"❌ 获取统计信息失败: HTTP {response.status_code}"
    except Exception as e:
        return f"❌ 获取统计信息失败: {str(e)}"


def check_health() -> str:
    """检查服务健康状态"""
    try:
        response = httpx.get(HEALTH_ENDPOINT, timeout=5.0)
        if response.status_code == 200:
            health = response.json()
            return f"✅ 服务健康\n- 状态: {health.get('status', 'unknown')}\n- 版本: {health.get('version', 'unknown')}\n- 运行时间: {health.get('uptime', 'unknown')}"
        else:
            return f"❌ 健康检查失败: HTTP {response.status_code}"
    except Exception as e:
        return f"❌ 健康检查失败: {str(e)}"


# ==================== Gradio界面 ====================

# 自定义CSS（在函数外部定义，以便在launch时使用）
CUSTOM_CSS = """
.gradio-container {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
.frame-item {
    transition: all 0.2s ease;
}
.frame-item:hover {
    box-shadow: 0 2px 8px rgba(0,0,0,0.15) !important;
    transform: translateY(-1px);
}
/* 聊天窗口自动换行 */
.message {
    white-space: pre-wrap !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
}
.message-text {
    white-space: pre-wrap !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
}
/* 确保聊天内容可以换行 */
#chatbot .message-wrap,
#chatbot .message-content,
#chatbot .message-body,
.chatbot .message,
.chatbot .message-text {
    white-space: pre-wrap !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
    max-width: 100% !important;
}
/* 确保聊天消息容器可以换行 */
.chatbot-container .message,
.chatbot-container .message-wrap {
    white-space: pre-wrap !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
}
"""

def create_interface():
    """创建Gradio界面"""
    
    with gr.Blocks(title="News TTS Agent 测试界面", css=CUSTOM_CSS) as demo:
        gr.Markdown("""
        # 🎙️ News TTS Agent 测试界面
        
        这是一个全面的测试界面，用于测试 News TTS Agent 服务的各项功能。
        
        **功能特性**:
        - 💬 实时流式聊天
        - 🧠 思考过程展示
        - 📝 文本内容展示
        - 🖼️ 图片展示
        - 🎵 音频播放支持
        - 📋 帧列表展示（每个响应帧的详细信息）
        """)
        
        with gr.Row():
            with gr.Column(scale=2):
                # 聊天界面
                chatbot = gr.Chatbot(
                    label="聊天记录",
                    height=400,
                    show_label=True,
                    container=True,
                    type="messages"  # 使用新的消息格式
                )
                
                with gr.Row():
                    query_input = gr.Textbox(
                        label="输入查询",
                        placeholder="例如: 今天有什么新闻",
                        lines=2,
                        scale=4
                    )
                    submit_btn = gr.Button("发送", variant="primary", scale=1)
                
                with gr.Row():
                    stream_checkbox = gr.Checkbox(
                        label="流式响应",
                        value=True,
                        info="启用流式响应以实时显示文本"
                    )
                    debug_checkbox = gr.Checkbox(
                        label="调试模式",
                        value=False,
                        info="显示详细的调试信息"
                    )
                    clear_btn = gr.Button("清空历史", variant="secondary")
            
            with gr.Column(scale=1):
                # 系统信息
                with gr.Accordion("系统信息", open=True):
                    health_status = gr.Textbox(
                        label="服务状态",
                        value="点击刷新按钮检查",
                        interactive=False,
                        lines=3
                    )
                    refresh_health_btn = gr.Button("刷新状态", size="sm")
                    
                    system_stats = gr.Markdown(
                        label="系统统计",
                        value="点击刷新按钮获取统计信息"
                    )
                    refresh_stats_btn = gr.Button("刷新统计", size="sm")
        
        # 详细信息面板（移到帧列表上面）
        with gr.Accordion("详细信息", open=False):
            with gr.Tabs():
                with gr.Tab("完整响应"):
                    complete_text_output = gr.Textbox(
                        label="完整响应内容",
                        lines=10,
                        max_lines=20,
                        interactive=False
                    )
                
                with gr.Tab("音频文件"):
                    # 使用Audio组件支持流式播放，File组件用于下载
                    audio_player = gr.Audio(
                        label="音频播放（合并后的完整音频）",
                        type="filepath",
                        autoplay=False
                    )
                    audio_outputs = gr.File(
                        label="音频文件列表（可下载）",
                        file_count="multiple",
                        type="filepath"
                    )
                
                with gr.Tab("图片文件"):
                    image_outputs = gr.Gallery(
                        label="图片列表",
                        show_label=True,
                        elem_id="gallery",
                        columns=3,
                        rows=2,
                        height="auto"
                    )
                
                with gr.Tab("原始JSON"):
                    raw_json_output = gr.Code(
                        label="原始响应JSON",
                        language="json",
                        value="等待响应...",
                        interactive=False
                    )
        
        # 帧列表展示（在详细信息下面）
        with gr.Accordion("📋 响应帧列表（每个帧的详细信息）", open=True):
            frames_display = gr.HTML(
                label="帧列表",
                value="<div style='text-align: center; color: #999; padding: 20px;'>等待响应...</div>"
            )
        
        # 事件绑定
        def clear_history():
            """清空历史"""
            return (
                [],  # chatbot
                "",  # complete_text
                "<div style='text-align: center; color: #999; padding: 20px;'>等待响应...</div>",  # frames_display
                None,  # audio_player (merged audio)
                [],  # audio_files
                [],  # image_files
                ""   # raw_json
            )
        
        def refresh_health():
            """刷新健康状态"""
            return check_health()
        
        def refresh_stats():
            """刷新统计信息"""
            return get_system_stats()
        
        # 绑定事件（使用流式生成器）
        submit_btn.click(
            fn=submit_query_stream,
            inputs=[query_input, stream_checkbox, debug_checkbox, chatbot],
            outputs=[
                chatbot,
                complete_text_output,
                frames_display,
                audio_player,  # 合并后的完整音频
                audio_outputs,  # 所有音频文件列表
                image_outputs,
                raw_json_output
            ]
        )
        
        query_input.submit(
            fn=submit_query_stream,
            inputs=[query_input, stream_checkbox, debug_checkbox, chatbot],
            outputs=[
                chatbot,
                complete_text_output,
                frames_display,
                audio_player,  # 合并后的完整音频
                audio_outputs,  # 所有音频文件列表
                image_outputs,
                raw_json_output
            ]
        )
        
        clear_btn.click(
            fn=clear_history,
            outputs=[
                chatbot,
                complete_text_output,
                frames_display,
                audio_player,  # 合并后的完整音频
                audio_outputs,  # 所有音频文件列表
                image_outputs,
                raw_json_output
            ]
        )
        
        refresh_health_btn.click(
            fn=refresh_health,
            outputs=[health_status]
        )
        
        refresh_stats_btn.click(
            fn=refresh_stats,
            outputs=[system_stats]
        )
        
        # 页面加载时自动刷新
        demo.load(
            fn=refresh_health,
            outputs=[health_status]
        )
        
        demo.load(
            fn=refresh_stats,
            outputs=[system_stats]
        )
    
    return demo


# ==================== 主函数 ====================

if __name__ == "__main__":
    # 检查gradio是否安装
    try:
        import gradio
    except ImportError:
        print("❌ 未安装gradio，请运行: pip install gradio")
        exit(1)
    
    # 创建并启动界面
    demo = create_interface()
    
    # 获取配置
    server_port = int(os.getenv("GRADIO_PORT", 7860))
    server_host = os.getenv("GRADIO_HOST", "0.0.0.0")
    share = os.getenv("GRADIO_SHARE", "false").lower() == "true"
    
    print(f"\n{'='*60}")
    print("🚀 启动 Gradio 测试界面")
    print(f"{'='*60}")
    print(f"📡 API地址: {DEFAULT_API_URL}")
    print(f"🌐 界面地址: http://{server_host}:{server_port}")
    print(f"{'='*60}\n")
    
    demo.launch(
        server_name=server_host,
        server_port=server_port,
        share=share,
        show_error=True
    )
