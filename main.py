"""
新闻播报Agent - 主API接口
实现当日热点新闻抓取、摘要生成和TTS语音播报
与Java脚手架API完全兼容
"""
import sys
from pathlib import Path

# 添加当前目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional, Dict, Any
import json
import time
import asyncio
import logging
import os

# 导入业务模块
from news_scraper import NewsScraper
from news_summarizer import NewsSummarizer
from tts_service import TTSService, MockTTSService
from models import (
    AgentRequest, ResponseData, BaseResponse,
    FramePart, FramePartAudio
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="News TTS Agent", version="1.0.0")

# ==================== 配置 ====================
USE_MOCK_TTS = os.getenv("USE_MOCK_TTS", "true").lower() == "true"
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

# ==================== 初始化服务 ====================
news_scraper = NewsScraper()
news_summarizer = NewsSummarizer()  # 使用新的初始化方式，从配置文件读取

# 根据配置选择TTS服务
if USE_MOCK_TTS:
    logger.warning("使用Mock TTS服务(仅用于测试)")
    tts_service = MockTTSService()
else:
    tts_service = TTSService()

# ==================== Agent业务逻辑 ====================

def generate_mock_response(query: str) -> Dict[str, Any]:
    """
    生成测试用的假数据响应

    Args:
        query: 用户查询

    Returns:
        包含假新闻和音频的响应字典
    """
    import base64

    # 假新闻数据
    mock_news_list = [
        {
            "title": "人工智能技术取得重大突破",
            "summary": "近日，国际顶级AI研究团队发布新一代大语言模型，在多项基准测试中刷新纪录",
            "ai_summary": "新一代AI模型性能提升显著，推理速度提高300%，能耗降低40%",
            "source": "科技日报",
            "publish_time": "2025-01-09 10:30",
            "url": "https://example.com/news/ai-breakthrough"
        },
        {
            "title": "全球新能源汽车销量创新高",
            "summary": "2024年全球新能源汽车销量突破1500万辆，同比增长35%",
            "ai_summary": "中国市场继续领跑，欧洲市场增速迅猛，技术创新推动产业发展",
            "source": "经济观察报",
            "publish_time": "2025-01-09 09:15",
            "url": "https://example.com/news/ev-sales"
        },
        {
            "title": "量子计算实现商用里程碑",
            "summary": "首台商用量子计算机正式交付，将用于金融建模和药物研发",
            "ai_summary": "量子计算正式进入应用阶段，算力优势将在多个领域发挥作用",
            "source": "科技周刊",
            "publish_time": "2025-01-09 08:45",
            "url": "https://example.com/news/quantum-computing"
        }
    ]

    # 根据查询生成不同的播报稿
    if "头条" in query or "热点" in query:
        mock_report = """各位听众好，以下是今日热点新闻：

第一，人工智能技术取得重大突破。国际顶级AI研究团队发布新一代大语言模型，推理速度提高300%，能耗降低40%。

第二，全球新能源汽车销量创新高。2024年全球销量突破1500万辆，同比增长35%，中国市场继续领跑。

第三，量子计算实现商用里程碑。首台商用量子计算机正式交付，将用于金融建模和药物研发。

以上就是今日热点新闻，感谢收听。"""
    else:
        mock_report = f"""收到您的查询：{query}

为您播报今日新闻摘要：

科技方面，人工智能技术取得重大突破，新一代大语言模型性能显著提升。

经济方面，全球新能源汽车销量创新高，2024年销量突破1500万辆。

前沿科技方面，量子计算实现商用里程碑，正式进入应用阶段。

感谢您的收听，如需了解更多详情，请随时提问。"""

    # 生成假音频数据（一个简短的WAV文件头）
    # 这里只生成一个小的base64字符串作为演示
    mock_audio_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xAC\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    mock_audio_base64 = base64.b64encode(mock_audio_wav).decode('utf-8')

    return {
        "text": mock_report,
        "news_count": len(mock_news_list),
        "audio": mock_audio_base64,
        "news_list": mock_news_list
    }


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

    # ==================== 测试模式：返回假数据 ====================
    if TEST_MODE:
        logger.info("🧪 测试模式：返回假数据")
        return generate_mock_response(query)

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


@app.get("/health/sidecar")
async def check_sidecar():
    """检查 Sidecar 健康状态"""
    import httpx
    from llm_utils.config import config

    sidecar_url = config.get_value("llm.base_url", "http://localhost:13984/api/llm/v1")
    health_url = sidecar_url.replace("/api/llm/v1", "/status.zebra")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(health_url)
            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "sidecar_url": sidecar_url,
                    "health_url": health_url,
                    "message": "Sidecar is running"
                }
            else:
                return {
                    "status": "unhealthy",
                    "sidecar_url": sidecar_url,
                    "health_url": health_url,
                    "message": f"Sidecar returned {response.status_code}"
                }
    except Exception as e:
        return {
            "status": "error",
            "sidecar_url": sidecar_url,
            "health_url": health_url,
            "message": str(e)
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
        start_time = time.time()
        try:
            frame_index = 0
            current_timestamp = int(time.time() * 1000)

            # 处理查询
            result = await process_news_query(request.query, request.context)
            response_text = result["text"]
            audio_base64 = result.get("audio")
            
            # 计算处理时间
            total_time = int((time.time() - start_time) * 1000)

            if request.stream:
                # 流式发送响应(模拟打字效果)
                complete_content = ""
                words = list(response_text)
                for word in words:
                    complete_content += word
                    response_data = ResponseData(
                        frame_id=frame_index,
                        frame_timestamp=current_timestamp,
                        frame_text=complete_content,
                        frame_is_final=False
                    )

                    base_response = BaseResponse(
                        version=request.version,
                        request_id=request.request_id,
                        code=0,
                        message="success",
                        data=response_data
                    )

                    yield f"event:data\ndata:{json.dumps(base_response.dict(exclude_none=True), ensure_ascii=False)}\n\n"
                    frame_index += 1
                    await asyncio.sleep(0.02)  # 控制发送频率

                # 发送完成帧(包含音频数据)
                # 构建调试信息
                debug_info = None
                if request.debug:
                    debug_info = {
                        "request": {
                            "debug": request.debug,
                            "query": request.query,
                            "history": [h.dict() if hasattr(h, 'dict') else h for h in (request.history or [])],
                            "version": request.version,
                            "voice_zone": request.voice_zone,
                            "stream": request.stream,
                            "user_id": request.user_id,
                            "conversation_id": request.conversation_id,
                            "vin": request.vin,
                            "channel_id": request.channel_id,
                            "request_id": request.request_id,
                            "timestamp": request.timestamp
                        },
                        "totalTime": total_time
                    }
                
                # 构建 frame_parts（如果有音频）
                frame_parts = None
                if audio_base64:
                    frame_parts = [
                        FramePart(
                            type="audio",
                            audio=FramePartAudio(
                                format="wav",
                                data=f"data:;base64,{audio_base64}",
                                is_final=True
                            )
                        )
                    ]
                
                final_response_data = ResponseData(
                    frame_id=frame_index,
                    frame_timestamp=int(time.time() * 1000),
                    frame_text="",
                    frame_is_final=True,
                    complete_content=complete_content,
                    frame_parts=frame_parts,
                    debug_info=debug_info
                )
            else:
                # 非流式响应
                # 发送内容帧
                response_data = ResponseData(
                    frame_id=frame_index,
                    frame_timestamp=current_timestamp,
                    frame_text=response_text,
                    frame_is_final=False
                )

                base_response = BaseResponse(
                    version=request.version,
                    request_id=request.request_id,
                    code=0,
                    message="success",
                    data=response_data
                )

                yield f"event:data\ndata:{json.dumps(base_response.dict(exclude_none=True), ensure_ascii=False)}\n\n"
                frame_index += 1

                # 发送完成帧
                # 构建调试信息
                debug_info = None
                if request.debug:
                    debug_info = {
                        "request": {
                            "debug": request.debug,
                            "query": request.query,
                            "history": [h.dict() if hasattr(h, 'dict') else h for h in (request.history or [])],
                            "version": request.version,
                            "voice_zone": request.voice_zone,
                            "stream": request.stream,
                            "user_id": request.user_id,
                            "conversation_id": request.conversation_id,
                            "vin": request.vin,
                            "channel_id": request.channel_id,
                            "request_id": request.request_id,
                            "timestamp": request.timestamp
                        },
                        "totalTime": total_time
                    }
                
                # 构建 frame_parts（如果有音频）
                frame_parts = None
                if audio_base64:
                    frame_parts = [
                        FramePart(
                            type="audio",
                            audio=FramePartAudio(
                                format="wav",
                                data=f"data:;base64,{audio_base64}",
                                is_final=True
                            )
                        )
                    ]
                
                final_response_data = ResponseData(
                    frame_id=frame_index,
                    frame_timestamp=int(time.time() * 1000),
                    frame_text="",
                    frame_is_final=True,
                    complete_content=response_text,
                    frame_parts=frame_parts,
                    debug_info=debug_info
                )

            # 发送最终响应
            final_base_response = BaseResponse(
                version=request.version,
                request_id=request.request_id,
                code=0,
                message="success",
                data=final_response_data
            )

            yield f"event:data\ndata:{json.dumps(final_base_response.dict(exclude_none=True), ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"处理请求失败: {e}", exc_info=True)
            # 发送错误响应
            error_response_data = ResponseData(
                frame_id=0,
                frame_timestamp=int(time.time() * 1000),
                frame_text="",
                frame_is_final=True
            )

            error_base_response = BaseResponse(
                version=request.version,
                request_id=request.request_id,
                code=500,
                message=f"Internal Error: {str(e)}",
                data=error_response_data
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
