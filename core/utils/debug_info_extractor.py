"""
从systemAgent响应消息中提取debug_info的工具函数
"""
from typing import Dict, Any, Optional


def extract_debug_info_from_system_agent(system_agent_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    从systemAgent响应消息中提取并整理debug_info信息
    
    Args:
        system_agent_response: systemAgent响应消息体，包含request和response信息
        
    Returns:
        整理后的debug_info字典
    """
    debug_info = {}
    
    # 提取请求信息
    request = system_agent_response.get("request", {})
    response = system_agent_response.get("response", {})
    response_debug_info = response.get("debug_info", {})
    
    # 1. 搜索相关信息
    search_result = response_debug_info.get("searchResult", {})
    if search_result:
        debug_info["search"] = {
            "rawCount": search_result.get("rawCount"),  # 原始结果数量
            "refCount": search_result.get("refCount"),  # 引用结果数量
            "textLength": search_result.get("textLength"),  # 文本长度
            "resultLength": search_result.get("resultLength"),  # 结果长度
            "searchCost": search_result.get("searchCost"),  # 搜索耗时(ms)
            "param": {
                "realTime": search_result.get("param", {}).get("realTime"),  # 实时性要求
                "sQuery": search_result.get("param", {}).get("sQuery"),  # 搜索查询
                "requestId": search_result.get("param", {}).get("requestId")
            }
        }
    
    # 2. 路由信息
    route = response_debug_info.get("route")
    if route:
        debug_info["route"] = route
    
    # 3. 搜索判断信息
    judge_search = response_debug_info.get("judgeSearch", {})
    if judge_search:
        debug_info["judgeSearch"] = {
            "needSearch": judge_search.get("needSearch"),  # 是否需要搜索
            "realTime": judge_search.get("realTime"),  # 是否实时
            "bertCost": judge_search.get("bertCost"),  # BERT模型耗时(ms)
            "llmCost": judge_search.get("llmCost")  # LLM判断耗时(ms)
        }
    
    # 4. 天气检查信息
    weather_check = response_debug_info.get("weatherLlmCheck", {})
    if weather_check:
        debug_info["weatherCheck"] = {
            "isWeatherQuery": weather_check.get("w", False),  # 是否为天气查询
            "timeCost": weather_check.get("timeCost")  # 检查耗时(ms)
        }
    
    # 5. 链式成本信息
    chain_cost = response_debug_info.get("chainCost", {})
    if chain_cost:
        debug_info["chainCost"] = {
            "requestTs": chain_cost.get("requestTs"),  # 请求时间戳
            "requestTsGap": chain_cost.get("requestTsGap")  # 请求时间间隔(ms)
        }
    
    # 6. 答案生成信息
    ans_info = response_debug_info.get("ans", {})
    if ans_info:
        debug_info["answer"] = {
            "ansLength": ans_info.get("ansLength"),  # 答案长度
            "contentFirstFrameCost": ans_info.get("contentFirstFrameCost"),  # 首帧内容生成耗时(ms)
            "completeFrameTs": ans_info.get("completeFrameTs"),  # 完整帧时间戳
            "firstFrameTs": ans_info.get("firstFrameTs"),  # 首帧时间戳
            "eeFirstFrameCost": ans_info.get("eeFirstFrameCost")  # EE首帧耗时(ms)
        }
    
    # 7. 语义缓存信息
    semantic_cache = response_debug_info.get("semanticCache", {})
    if semantic_cache:
        debug_info["semanticCache"] = {
            "hit": semantic_cache.get("hit", False),  # 是否命中缓存
            "timeCost": semantic_cache.get("timeCost")  # 缓存检查耗时(ms)
        }
    
    # 8. 查询重写信息
    rewrite = response_debug_info.get("rewrite", {})
    if rewrite:
        debug_info["rewrite"] = {
            "method": rewrite.get("method"),  # 重写方法
            "timeCost": rewrite.get("timeCost")  # 重写耗时(ms)
        }
    
    # 9. 性能指标汇总
    total_cost_ms = system_agent_response.get("totalCostMs")
    first_frame_ms = system_agent_response.get("firstFrameMs")
    if total_cost_ms is not None or first_frame_ms is not None:
        debug_info["performance"] = {
            "totalCostMs": total_cost_ms,  # 总耗时(ms)
            "firstFrameMs": first_frame_ms  # 首帧耗时(ms)
        }
    
    # 10. 数据源信息（从extension中提取）
    extension = response.get("extension", {})
    if extension:
        # extension可能直接包含data字段，也可能这些字段直接在extension中
        extension_data = extension.get("data", extension)
        
        source_info = {}
        if "source" in extension_data:
            source_info["source"] = extension_data.get("source")  # 数据源标识
        if "sourceName" in extension_data:
            source_info["sourceName"] = extension_data.get("sourceName")  # 数据源名称
        if "sourceLogo" in extension_data:
            source_info["sourceLogo"] = extension_data.get("sourceLogo")  # 数据源Logo
        if source_info:
            debug_info["dataSource"] = source_info
        
        # 参考来源数量
        references = extension_data.get("references", [])
        if references:
            debug_info["references"] = {
                "count": len(references),  # 参考来源数量
                "sources": [
                    {
                        "index": ref.get("index"),
                        "title": ref.get("title"),
                        "hostname": ref.get("hostname"),
                        "datetimeStr": ref.get("datetimeStr"),
                        "url": ref.get("url")
                    }
                    for ref in references[:5]  # 只保留前5个
                ]
            }
        
        # 推荐查询
        recommend_querys = extension_data.get("recommendQuerys", [])
        if recommend_querys:
            debug_info["recommendQuerys"] = recommend_querys
    
    # 11. 请求基本信息
    if request:
        debug_info["request"] = {
            "query": request.get("query"),  # 用户查询
            "requestId": request.get("request_id"),  # 请求ID
            "conversationId": request.get("conversation_id"),  # 会话ID
            "userId": request.get("user_id"),  # 用户ID
            "vin": request.get("vin"),  # 车辆VIN
            "timestamp": request.get("timestamp")  # 请求时间戳
        }
    
    # 12. 响应基本信息
    if response:
        debug_info["response"] = {
            "agentId": response.get("agent_id"),  # Agent ID
            "frameId": response.get("frame_id"),  # 帧ID
            "frameIsFinal": response.get("frame_is_final"),  # 是否最终帧
            "frameTimestamp": response.get("frame_timestamp"),  # 帧时间戳
            "completeContentLength": len(response.get("complete_content", ""))  # 完整内容长度
        }
    
    return debug_info


def merge_debug_info(existing_debug_info: Optional[Dict[str, Any]], 
                     new_debug_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    合并现有的debug_info和新提取的debug_info
    
    Args:
        existing_debug_info: 现有的debug_info
        new_debug_info: 新提取的debug_info
        
    Returns:
        合并后的debug_info
    """
    if not existing_debug_info:
        return new_debug_info
    
    # 合并策略：新信息覆盖旧信息，但保留旧信息中不冲突的部分
    merged = existing_debug_info.copy()
    
    # 对于嵌套字典，进行深度合并
    for key, value in new_debug_info.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    
    return merged

