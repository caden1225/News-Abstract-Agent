"""
新闻播报Agent - 主API接口
实现当日热点新闻抓取、摘要生成和TTS语音播报
与Java脚手架API完全兼容
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import time
import asyncio
import logging
import os

# 导入业务模块
from news_scraper import NewsScraper
from news_summarizer import NewsSummarizer
from tts_service import TTSService, MockTTSService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="News TTS Agent", version="1.0.0")

# ==================== 配置 ====================
SIDECAR_BASE_URL = os.getenv("SIDECAR_BASE_URL", "http://localhost:13984/api/llm/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "zbx:...")
USE_MOCK_TTS = os.getenv("USE_MOCK_TTS", "true").lower() == "true"

# ==================== 初始化服务 ====================
news_scraper = NewsScraper()
news_summarizer = NewsSummarizer(sidecar_base_url=SIDECAR_BASE_URL, api_key=LLM_API_KEY)

# 根据配置选择TTS服务
if USE_MOCK_TTS:
    logger.warning("使用Mock TTS服务(仅用于测试)")
    tts_service = MockTTSService()
else:
    tts_service = TTSService()

# ==================== 数据模型定义 ====================

class AgentRequest(BaseModel):
    """请求模型 - 与Java脚手架保持一致"""
    version: str
    channel_id: str
    request_id: str
    timestamp: int
    vin: str
    stream: bool
    user_id: str
    query: str
    conversation_id: Optional[str] = None
    history: Optional[List] = None
    context: Optional[Dict[str, Any]] = None
    agent_id: Optional[str] = None
    rewritten_query: Optional[str] = None
    debug: Optional[bool] = False
    system_metadata: Optional[Dict[str, Any]] = None


class AgentResponse(BaseModel):
    """响应数据模型 - 与Java脚手架保持一致"""
    request_id: str
    user_id: str
    vin: str
    frame_id: int
    frame_text: str
    frame_timestamp: int
    frame_is_final: bool
    complete_content: Optional[str] = None
    agent_id: Optional[str] = None
    nlu: Optional[Dict[str, Any]] = None
    function_call: Optional[Dict[str, Any]] = None
    extension: Optional[Dict[str, Any]] = None
    frame_parts: Optional[List] = None
    frame_voice: Optional[Dict[str, Any]] = None
    frame_image: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, Any]] = None
    scene_id: Optional[str] = None
    debug_info: Optional[Dict[str, Any]] = None


class BaseResponse(BaseModel):
    """基础响应模型 - 与Java脚手架保持一致"""
    code: int
    message: str
    data: AgentResponse
    event: Optional[str] = None
    request_id: Optional[str] = None
    version: Optional[str] = None


# ==================== Agent业务逻辑 ====================

async def process_news_query(query: str, context: Optional[Dict] = None) -> Dict[str, Any]:
    """
    处理新闻查询请求

    Args:
        query: 用户查询
        context: 上下文信息

    Returns:
        处理结果字典,包含新闻列表、播报稿和音频
    """
    logger.info(f"开始处理新闻查询: {query}")

    # 步骤1: 抓取当日热点新闻
    logger.info("步骤1: 抓取当日热点新闻...")
    news_list = news_scraper.fetch_today_news(limit_per_source=5)

    if not news_list:
        logger.warning("未获取到新闻,返回默认响应")
        return {
            "text": "抱歉,暂时无法获取今日热点新闻,请稍后再试。",
            "news_count": 0,
            "audio": None
        }

    # 转换为字典格式
    news_dicts = [news.to_dict() for news in news_list]
    logger.info(f"成功获取 {len(news_dicts)} 条新闻")

    # 步骤2: 生成新闻摘要
    logger.info("步骤2: 生成新闻摘要...")
    try:
        news_with_summaries = await news_summarizer.summarize_news_batch(news_dicts)
    except Exception as e:
        logger.error(f"生成摘要失败: {e},使用原始摘要")
        news_with_summaries = news_dicts

    # 步骤3: 生成新闻播报稿
    logger.info("步骤3: 生成新闻播报稿...")
    try:
        news_report = await news_summarizer.generate_news_report(news_with_summaries)
    except Exception as e:
        logger.error(f"生成播报稿失败: {e},使用简化版本")
        # 降级处理:使用简单的新闻列表
        report_parts = ["各位听众好,以下是今日热点新闻:"]
        for i, news in enumerate(news_with_summaries[:5], 1):
            title = news.get('title', '')
            summary = news.get('ai_summary', news.get('summary', ''))[:50]
            report_parts.append(f"{i}. {title}: {summary}")
        report_parts.append("以上就是今日热点新闻,感谢收听")
        news_report = "\n".join(report_parts)

    logger.info(f"播报稿生成成功,长度: {len(news_report)} 字符")

    # 步骤4: 生成TTS语音
    logger.info("步骤4: 生成TTS语音...")
    try:
        audio_result = await tts_service.generate_news_audio(news_report)
        audio_base64 = audio_result.get("audio") if audio_result else None
        if audio_base64:
            logger.info("语音生成成功")
        else:
            logger.warning("语音生成失败,仅返回文本")
    except Exception as e:
        logger.error(f"TTS转换失败: {e}")
        audio_base64 = None

    # 构建响应
    result = {
        "text": news_report,
        "news_count": len(news_with_summaries),
        "audio": audio_base64,
        "news_list": news_with_summaries[:5]  # 只返回前5条
    }

    logger.info(f"处理完成,共 {len(news_with_summaries)} 条新闻")
    return result


# ==================== API端点 ====================

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "ok",
        "service": "news-tts-agent",
        "version": "1.0.0"
    }


@app.get("/api/v1/news")
async def get_news():
    """
    获取当日热点新闻(调试接口)
    """
    try:
        news_list = news_scraper.fetch_today_news(limit_per_source=5)
        return {
            "code": 0,
            "message": "Success",
            "data": {
                "news_count": len(news_list),
                "news": [news.to_dict() for news in news_list]
            }
        }
    except Exception as e:
        logger.error(f"获取新闻失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/chat")
async def chat(request: AgentRequest):
    """
    聊天接口 - 与Java脚手架API完全兼容
    实现流式响应(Server-Sent Events)
    """
    logger.info(f"收到请求: request_id={request.request_id}, query={request.query}")

    async def generate_response():
        """生成流式响应"""
        try:
            frame_index = 0
            current_timestamp = int(time.time() * 1000)

            # 处理查询
            result = await process_news_query(request.query, request.context)
            response_text = result["text"]
            audio_base64 = result.get("audio")

            if request.stream:
                # 流式发送响应(模拟打字效果)
                complete_content = ""
                words = list(response_text)
                for word in words:
                    complete_content += word
                    response = AgentResponse(
                        request_id=request.request_id,
                        user_id=request.user_id,
                        vin=request.vin,
                        frame_id=frame_index,
                        frame_text=complete_content,
                        frame_timestamp=current_timestamp,
                        frame_is_final=False,
                        agent_id=request.agent_id
                    )

                    base_response = BaseResponse(
                        code=0,
                        message="Success",
                        data=response,
                        request_id=request.request_id
                    )

                    yield f"event:data\ndata:{json.dumps(base_response.dict(exclude_none=True), ensure_ascii=False)}\n\n"
                    frame_index += 1
                    await asyncio.sleep(0.02)  # 控制发送频率

                # 发送完成帧(包含音频数据)
                final_response = AgentResponse(
                    request_id=request.request_id,
                    user_id=request.user_id,
                    vin=request.vin,
                    frame_id=frame_index,
                    frame_text="",
                    frame_timestamp=int(time.time() * 1000),
                    frame_is_final=True,
                    complete_content=complete_content,
                    agent_id=request.agent_id
                )

                # 如果有音频数据,添加到响应中
                if audio_base64:
                    final_response.frame_voice = {
                        "audio": audio_base64,
                        "format": "mp3"
                    }
            else:
                # 非流式响应
                # 发送内容帧
                response = AgentResponse(
                    request_id=request.request_id,
                    user_id=request.user_id,
                    vin=request.vin,
                    frame_id=frame_index,
                    frame_text=response_text,
                    frame_timestamp=current_timestamp,
                    frame_is_final=False,
                    agent_id=request.agent_id
                )

                base_response = BaseResponse(
                    code=0,
                    message="Success",
                    data=response,
                    request_id=request.request_id
                )

                yield f"event:data\ndata:{json.dumps(base_response.dict(exclude_none=True), ensure_ascii=False)}\n\n"
                frame_index += 1

                # 发送完成帧
                final_response = AgentResponse(
                    request_id=request.request_id,
                    user_id=request.user_id,
                    vin=request.vin,
                    frame_id=frame_index,
                    frame_text="",
                    frame_timestamp=int(time.time() * 1000),
                    frame_is_final=True,
                    complete_content=response_text,
                    agent_id=request.agent_id
                )

                # 如果有音频数据,添加到响应中
                if audio_base64:
                    final_response.frame_voice = {
                        "audio": audio_base64,
                        "format": "mp3"
                    }

            # 发送最终响应
            final_base_response = BaseResponse(
                code=0,
                message="Success",
                data=final_response,
                request_id=request.request_id
            )

            yield f"event:data\ndata:{json.dumps(final_base_response.dict(exclude_none=True), ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"处理请求失败: {e}", exc_info=True)
            # 发送错误响应
            error_response = AgentResponse(
                request_id=request.request_id,
                user_id=request.user_id,
                vin=request.vin,
                frame_id=0,
                frame_text="",
                frame_timestamp=int(time.time() * 1000),
                frame_is_final=True,
                complete_content=None
            )

            error_base_response = BaseResponse(
                code=500,
                message=f"Internal Error: {str(e)}",
                data=error_response,
                request_id=request.request_id
            )

            yield f"event:data\ndata:{json.dumps(error_base_response.dict(exclude_none=True), ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ==================== 启动应用 ====================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info"
    )
