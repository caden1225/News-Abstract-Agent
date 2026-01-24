"""
从处理状态中构建debug_info的工具函数
"""
import time
from typing import Dict, Any, Optional, List
from models.state import NewsAgentState


def build_debug_info_from_state(
    state: NewsAgentState,
    request_start_time: Optional[float] = None,
    debug: bool = False,
    version: str = "2.1",
    query: str = "",
    history: Optional[List] = None,
    user_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    vin: Optional[str] = None,
    channel_id: Optional[str] = None,
    voice_zone: Optional[int] = None,
    timestamp: Optional[int] = None,
    stream: bool = True
) -> Dict[str, Any]:
    """
    从处理状态中提取并构建debug_info
    
    Args:
        state: 处理状态
        request_start_time: 请求开始时间（可选，用于计算总耗时）
        debug: 是否显示调试信息
        version: LLM Protocol 版本号
        query: 用户查询
        history: 历史对话记录
        user_id: 用户ID
        conversation_id: 会话ID
        vin: 车辆VIN
        channel_id: 渠道ID
        voice_zone: 语音区域
        timestamp: 请求时间戳
        stream: 是否流式响应
        
    Returns:
        整理后的debug_info字典
    """
    debug_info = {}
    
    # 1. 请求基本信息（tiny_stone 风格 + 当前项目的详细信息）
    request_info = {
        "query": query or state.get("query", ""),
        "request_id": state.get("request_id", ""),
        "stream": stream or state.get("stream", False)
    }
    
    # 添加 tiny_stone 风格的请求字段（如果提供）
    if debug:
        request_info["debug"] = debug
        request_info["version"] = version
        request_info["stream"] = stream
        
        if history is not None:
            # 转换 history 为字典格式（如果包含 Pydantic 模型）
            try:
                if hasattr(history, '__iter__') and len(history) > 0:
                    history_list = []
                    for h in history:
                        if hasattr(h, 'dict'):
                            history_list.append(h.dict())
                        elif hasattr(h, 'model_dump'):
                            history_list.append(h.model_dump())
                        elif isinstance(h, dict):
                            history_list.append(h)
                        else:
                            history_list.append(str(h))
                    request_info["history"] = history_list
            except Exception as e:
                request_info["history"] = []
        
        if user_id is not None:
            request_info["user_id"] = user_id
        if conversation_id is not None:
            request_info["conversation_id"] = conversation_id
        if vin is not None:
            request_info["vin"] = vin
        if channel_id is not None:
            request_info["channel_id"] = channel_id
        if voice_zone is not None:
            request_info["voice_zone"] = voice_zone
        if timestamp is not None:
            request_info["timestamp"] = timestamp
    
    debug_info["request"] = request_info
    
    # 计算总耗时（tiny_stone 风格）
    if request_start_time:
        total_time = int((time.time() - request_start_time) * 1000)
        debug_info["totalTime"] = total_time
    
    # 2. 意图分析信息
    query_type = state.get("query_type", "")
    if query_type:
        debug_info["intentAnalysis"] = {
            "queryType": query_type,
            "searchStrategy": state.get("search_strategy", ""),
            "targetDate": state.get("target_date"),
            "category": state.get("category"),
            "searchKeywords": state.get("search_keywords", [])
        }
    
    # 3. 数据获取信息
    cache_hit = state.get("cache_hit", False)
    news_count = state.get("news_count", 0)
    data_source = state.get("data_source", "")
    
    debug_info["dataFetch"] = {
        "cacheHit": cache_hit,
        "dataSource": data_source,
        "newsCount": news_count,
        "selectedNewsCount": len(state.get("selected_news", []))
    }
    
    # 4. 处理步骤信息
    processing_steps = state.get("processing_steps", [])
    if processing_steps:
        debug_info["processing"] = {
            "steps": processing_steps,
            "stepCount": len(processing_steps),
            "currentStep": state.get("current_step", ""),
            "progressPercentage": state.get("progress_percentage", 0)
        }
    
    # 5. 内容生成信息
    summary = state.get("summary", "")
    thinking_chain = state.get("thinking_chain", [])
    
    if summary or thinking_chain:
        debug_info["contentGeneration"] = {
            "summaryLength": len(summary),
            "thinkingSteps": len(thinking_chain),
            "hasSummary": bool(summary),
            "hasThinking": len(thinking_chain) > 0
        }
    
    # 6. TTS信息
    tts_language = state.get("tts_language", "")
    language_confidence = state.get("language_confidence", 0.0)
    audio_data = state.get("audio_data")
    streaming_audio_chunks = state.get("streaming_audio_chunks", [])
    
    if tts_language or audio_data or streaming_audio_chunks:
        debug_info["tts"] = {
            "language": tts_language,
            "languageConfidence": language_confidence,
            "hasAudio": bool(audio_data),
            "audioChunkCount": len(streaming_audio_chunks),
            "llmLanguageReady": state.get("llm_language_ready", False)
        }
    
    # 7. 多模态信息
    image_links = state.get("image_links", [])
    if image_links:
        debug_info["multimodal"] = {
            "imageCount": len(image_links),
            "hasImages": len(image_links) > 0
        }
    
    # 8. 性能指标（如果提供了开始时间）
    if request_start_time:
        total_cost_ms = (time.time() - request_start_time) * 1000
        debug_info["performance"] = {
            "totalCostMs": round(total_cost_ms, 2),
            "requestStartTime": request_start_time
        }
    
    # 9. 并行生成状态
    text_ready = state.get("text_ready", False)
    audio_ready = state.get("audio_ready", False)
    
    if text_ready or audio_ready:
        debug_info["parallelGeneration"] = {
            "textReady": text_ready,
            "audioReady": audio_ready,
            "bothReady": text_ready and audio_ready
        }
    
    # 10. 错误信息（如果有）
    error = state.get("error")
    if error:
        debug_info["error"] = {
            "message": error,
            "hasError": True
        }
    
    # 11. 完成状态
    debug_info["status"] = {
        "completed": state.get("completed", False),
        "hasError": bool(error)
    }
    
    return debug_info

