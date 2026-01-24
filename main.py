"""
News TTS Agent - FastAPI 主应用
提供新闻查询和播报服务
"""
import os
import logging
import uuid
import json
import time
from typing import Optional, Union
from pathlib import Path
from contextlib import asynccontextmanager

# ==================== 环境变量配置（必须在其他导入之前）====================
# 加载环境变量（必须在设置之前加载，避免被覆盖）
from dotenv import load_dotenv
load_dotenv()

# 定义项目根目录（必须在设置环境变量之前）
_project_root = Path(__file__).parent

# ==================== 禁用自动下载（使用本地模型）====================
# 禁用 Transformers 和 HuggingFace Hub 自动下载
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
_wetext_local_path = _project_root / 'tts_modules' / 'cosyvoice2' / 'Wetext'
if _wetext_local_path.exists():
    os.environ['WETEXT_HOME'] = str(_wetext_local_path.resolve())

# 设置 ModelScope 缓存目录到项目目录，避免使用系统默认缓存
# 这样即使需要下载，也会下载到项目目录中，便于管理和复用
# 添加异常处理，避免目录创建失败导致卡死
_modelscope_cache_dir = None
try:
    _modelscope_cache_dir = _project_root / 'data' / 'modelscope_cache'

    # 检查目录是否已存在但权限不正确
    if _modelscope_cache_dir.exists():
        # 尝试创建测试文件来检查写权限
        _test_file = _modelscope_cache_dir / '.write_test'
        try:
            _test_file.touch()
            _test_file.unlink()
        except (OSError, PermissionError):
            print(f"⚠️  ModelScope 缓存目录存在但无写权限: {_modelscope_cache_dir}")
            print("   将使用系统默认缓存目录")
            _modelscope_cache_dir = None
    else:
        # 目录不存在，尝试创建
        try:
            _modelscope_cache_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            print(f"⚠️  无法创建 ModelScope 缓存目录: {_modelscope_cache_dir}")
            print(f"   错误: {e}")
            print("   将使用系统默认缓存目录")
            _modelscope_cache_dir = None

    # 只有在目录可用时才设置环境变量
    if _modelscope_cache_dir is not None:
        cache_path = str(_modelscope_cache_dir.resolve())
        # 设置 ModelScope 相关的所有缓存环境变量
        os.environ['MODELSCOPE_CACHE'] = cache_path
        os.environ['MODELSCOPE_HUB_CACHE'] = cache_path
        # ModelScope 可能使用 hub 目录结构，确保设置正确的路径
        os.environ['MODELSCOPE_HUB'] = cache_path
        # 确保 hub 子目录存在
        hub_dir = _modelscope_cache_dir / 'hub'
        if not hub_dir.exists():
            try:
                hub_dir.mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError):
                pass  # 如果无法创建，继续使用主目录
except Exception as e:
    print(f"⚠️  设置 ModelScope 缓存目录时出错: {e}")
    print("   将使用系统默认缓存目录")
    _modelscope_cache_dir = None

from fastapi import FastAPI, HTTPException
from starlette.requests import Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from core.orchestrator import NewsAgentOrchestrator
from models.api import ChatRequest, AgentRequest, HealthResponse
from scheduler.tasks import NewsScheduler
from core.rate_limit import limiter, rate_limit_exceeded_handler, rate_limit_default
from slowapi.errors import RateLimitExceeded

# ==================== 日志配置 ====================

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== 应用生命周期 ====================

orchestrator: Optional[NewsAgentOrchestrator] = None
news_scheduler: Optional[NewsScheduler] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global orchestrator, news_scheduler

    # 启动时初始化
    logger.info("=" * 70)
    logger.info("News TTS Agent 正在启动...")
    logger.info("=" * 70)
    
    # 输出环境变量配置信息
    if 'WETEXT_HOME' in os.environ:
        logger.info(f"📁 WETEXT_HOME: {os.environ['WETEXT_HOME']}")
    if 'MODELSCOPE_CACHE' in os.environ:
        logger.info(f"📁 ModelScope 缓存目录: {os.environ['MODELSCOPE_CACHE']}")

    try:
        orchestrator = NewsAgentOrchestrator()
        logger.info("✅ NewsAgentOrchestrator 初始化成功")
    except Exception as e:
        logger.error(f"❌ NewsAgentOrchestrator 初始化失败: {e}")
        raise

    # 初始化 TTS 服务
    from llm_utils.config import config as app_config
    tts_config = app_config.get("tts", {})
    tts_enabled = tts_config.get("enabled", True)
    tts_mock = tts_config.get("mock", False)
    tts_service = None

    if tts_enabled:
        try:
            from tts_utils import get_tts_service, initialize_tts

            # 检查当前选择的 TTS 服务类型
            service_type = os.getenv("TTS_SERVICE_TYPE", "").lower() or tts_config.get("service_type", "cosyvoice2").lower()
            is_dashscope = service_type == "dashscope"

            # 如果是mock模式，使用Mock服务
            if tts_mock:
                logger.info("使用 Mock TTS 服务（配置模式）")
                from tts_utils.mock_service import MockTTSService
                tts_service = MockTTSService()
                logger.info("✅ Mock TTS 服务初始化成功")
                # 将TTS服务注入到orchestrator
                if orchestrator:
                    orchestrator.tts_service = tts_service
                    logger.info("  - TTS 服务已注入到 Orchestrator")
            else:
                logger.info(f"正在初始化 TTS 服务 (类型: {service_type})...")
                tts_service = get_tts_service()

                # 初始化TTS模型（加载模型到内存）
                init_result = await initialize_tts()
                if init_result:
                    logger.info("✅ TTS 服务初始化成功")
                    # 将TTS服务注入到orchestrator
                    if orchestrator:
                        orchestrator.tts_service = tts_service
                        logger.info("  - TTS 服务已注入到 Orchestrator")
                else:
                    # DashScope 服务不允许回退
                    if is_dashscope:
                        raise RuntimeError("DashScope TTS 服务初始化失败，不允许回退")
                    logger.warning("⚠️  TTS 服务初始化失败，回退到 Mock 服务")
                    from tts_utils.mock_service import MockTTSService
                    tts_service = MockTTSService()
                    if orchestrator:
                        orchestrator.tts_service = tts_service
                        logger.info("  - Mock TTS 服务已注入到 Orchestrator")
        except Exception as e:
            # 检查是否是 DashScope 服务
            service_type = os.getenv("TTS_SERVICE_TYPE", "").lower() or tts_config.get("service_type", "cosyvoice2").lower()
            is_dashscope = service_type == "dashscope"
            
            if is_dashscope:
                # DashScope 服务不允许回退，直接抛出异常
                logger.error(f"❌ DashScope TTS 服务初始化失败: {e}", exc_info=True)
                raise RuntimeError(f"DashScope TTS 服务初始化失败: {e}")
            
            # 其他服务允许回退
            logger.error(f"❌ TTS 服务初始化失败: {e}", exc_info=True)
            logger.warning("回退到 Mock TTS 服务")
            try:
                from tts_utils.mock_service import MockTTSService
                tts_service = MockTTSService()
                if orchestrator:
                    orchestrator.tts_service = tts_service
                    logger.info("  - Mock TTS 服务已注入到 Orchestrator")
            except Exception as mock_e:
                logger.error(f"❌ Mock TTS 服务也初始化失败: {mock_e}", exc_info=True)
                raise
    else:
        logger.info("ℹ️ TTS 服务已禁用（配置中 tts.enabled=false）")

    # 初始化定时任务调度器
    from llm_utils.config import config as app_config
    
    scheduler_config = app_config.get("scheduler", {})
    enable_scheduler = scheduler_config.get("enabled", False) or os.getenv("ENABLE_SCHEDULER", "false").lower() == "true"
    
    if enable_scheduler:
        try:
            # 从配置读取参数
            timezone = scheduler_config.get("timezone", "Asia/Shanghai")
            persist_jobs = scheduler_config.get("persist_jobs", True)
            # 从配置文件读取定时任务数据库路径
            jobs_db_path = scheduler_config.get("jobs_db_path", "data/scheduler_jobs.db")
            # 如果是相对路径，转换为绝对路径
            if not os.path.isabs(jobs_db_path):
                project_root = Path(__file__).parent
                jobs_db_path = str((project_root / jobs_db_path).resolve())
            
            news_scheduler = NewsScheduler(
                use_async=True,
                timezone=timezone,
                persist_jobs=persist_jobs,
                jobs_db_path=jobs_db_path
            )
            
            # 每日定时爬取任务（推荐：每天8点）
            daily_crawl_config = scheduler_config.get("daily_crawl", {})
            if daily_crawl_config.get("enabled", True):
                daily_hour = int(daily_crawl_config.get("hour", 8))
                daily_minute = int(daily_crawl_config.get("minute", 0))
                days_to_keep = int(daily_crawl_config.get("days_to_keep", 7))
                clear_before = daily_crawl_config.get("clear_before_crawl", False)
                
                news_scheduler.add_daily_crawl_job(
                    hour=daily_hour,
                    minute=daily_minute,
                    days_to_keep=days_to_keep,
                    clear_before_crawl=clear_before
                )
                logger.info(f"✅ 已添加每日爬取任务: 每天 {daily_hour:02d}:{daily_minute:02d}，保留 {days_to_keep} 天")
            
            # 定时清理任务（可选：每天凌晨3点）
            cleanup_config = scheduler_config.get("cleanup", {})
            if cleanup_config.get("enabled", True):
                cleanup_hour = int(cleanup_config.get("hour", 3))
                cleanup_minute = int(cleanup_config.get("minute", 0))
                cleanup_days = int(cleanup_config.get("days_to_keep", 30))
                
                news_scheduler.add_cleanup_job(
                    hour=cleanup_hour,
                    minute=cleanup_minute,
                    days_to_keep=cleanup_days
                )
                logger.info(f"✅ 已添加清理任务: 每天 {cleanup_hour:02d}:{cleanup_minute:02d}，保留 {cleanup_days} 天")
            
            # 健康检查任务（可选：每小时）
            health_config = scheduler_config.get("health_check", {})
            if health_config.get("enabled", True):
                from scheduler.jobs import health_check_job
                health_interval = int(health_config.get("interval_minutes", 60))
                
                news_scheduler.add_interval_job(
                    job_func=health_check_job,
                    job_id="health_check",
                    minutes=health_interval
                )
                logger.info(f"✅ 已添加健康检查任务: 每 {health_interval} 分钟")
            
            # 间隔爬取任务（每10分钟执行一次）
            crawler_config = app_config.get("crawler", {})
            crawl_interval_minutes = int(crawler_config.get("crawl_interval_minutes", 10))
            if crawl_interval_minutes > 0:
                from scheduler.jobs import crawl_news_job
                
                news_scheduler.add_interval_job(
                    job_func=crawl_news_job,
                    job_id="interval_crawl_news",
                    minutes=crawl_interval_minutes,
                    start_now=False
                )
                logger.info(f"✅ 已添加间隔爬取任务: 每 {crawl_interval_minutes} 分钟")
            
            # 每周清除所有数据任务（可选：每周日晚上9点）
            weekly_clear_config = scheduler_config.get("weekly_clear", {})
            if weekly_clear_config.get("enabled", False):
                weekly_day = weekly_clear_config.get("day_of_week", "sun")
                weekly_hour = int(weekly_clear_config.get("hour", 21))
                weekly_minute = int(weekly_clear_config.get("minute", 0))
                
                news_scheduler.add_weekly_clear_job(
                    day_of_week=weekly_day,
                    hour=weekly_hour,
                    minute=weekly_minute
                )
                logger.info(f"✅ 已添加每周清除任务: 每{weekly_day} {weekly_hour:02d}:{weekly_minute:02d}")
            
            # 启动调度器
            news_scheduler.start()
            logger.info("✅ NewsScheduler 初始化成功")
            logger.info(f"  - 时区: {timezone}")
            logger.info(f"  - 任务持久化: {'启用' if persist_jobs else '禁用'}")
        except Exception as e:
            logger.warning(f"⚠️ NewsScheduler 初始化失败（非致命）: {e}", exc_info=True)
    else:
        logger.info("ℹ️ 定时任务调度器已禁用")

    # 打印配置信息
    logger.info(f"📊 当前配置:")
    logger.info(f"  - 使用爬虫数据库: {os.getenv('CRAWLER_DB_PATH', '默认路径')}")
    logger.info(f"  - LLM模式: {os.getenv('LLM_MODE', 'openrouter')}")
    tts_model_dir = app_config.get("tts.local_model_dir", "未配置")
    tts_status = "已启用" if tts_enabled else "已禁用"
    logger.info(f"  - TTS服务: {tts_status} (模型目录: {tts_model_dir})")
    logger.info(f"  - 定时任务: {'已启用' if enable_scheduler else '已禁用'}")

    # 检查数据库是否为空，如果为空则执行首次爬虫
    try:
        from core.crawler_service import get_crawler_service
        crawler_service = get_crawler_service()
        stats = crawler_service.get_statistics()
        total_news = stats.get("total_news", 0)
        
        if total_news == 0:
            logger.info("=" * 70)
            logger.info("📰 检测到数据库为空，执行首次爬虫...")
            logger.info("=" * 70)
            try:
                results = crawler_service.crawl_all()
                total_crawled = sum(results.values())
                logger.info(f"✅ 首次爬虫完成，共抓取 {total_crawled} 条新闻")
                for site, count in results.items():
                    logger.info(f"  - {site}: {count} 条")
            except Exception as e:
                logger.warning(f"⚠️ 首次爬虫失败（非致命）: {e}", exc_info=True)
                logger.warning("服务将继续启动，您可以稍后手动触发爬虫")
        else:
            logger.info(f"📰 数据库已有 {total_news} 条新闻，跳过首次爬虫")
    except Exception as e:
        logger.warning(f"⚠️ 检查数据库状态失败（非致命）: {e}")
        logger.warning("服务将继续启动，您可以稍后手动触发爬虫")
    
    logger.info("=" * 70)
    logger.info("✅ 服务启动完成，准备接受请求")
    logger.info("=" * 70)

    yield

    # 关闭时清理
    logger.info("服务正在关闭...")
    
    # 关闭定时任务调度器
    if news_scheduler and news_scheduler.running:
        news_scheduler.shutdown(wait=True)
        logger.info("✅ NewsScheduler 已关闭")
    
    logger.info("✅ 服务已关闭")


# ==================== FastAPI 应用 ====================

app = FastAPI(
    title="News TTS Agent",
    description="基于 LangGraph 的智能新闻播报系统",
    version="2.0.0",
    lifespan=lifespan
)

# 注册速率限制器
app.state.limiter = limiter

# 注册速率限制异常处理器
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """速率限制异常处理器"""
    return rate_limit_exceeded_handler(request, exc)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境请设置具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 请求/响应模型 ====================
# ChatRequest 和 HealthResponse 已移动到 models.api


# ==================== 工具函数 ====================

def generate_request_id() -> str:
    """生成请求ID"""
    return f"req_{uuid.uuid4().hex[:16]}"


# ==================== 路由 ====================

@app.get("/", tags=["基础"])
async def root():
    """根路径"""
    return {
        "service": "News TTS Agent",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse, tags=["基础"])
async def health_check():
    """健康检查"""
    import time
    return {
        "status": "healthy" if orchestrator else "unhealthy",
        "version": "2.0.0",
        "uptime": f"{time.time() % 86400:.0f}s"
    }


@app.post("/api/v1/chat", tags=["新闻"])
@rate_limit_default(limit="10/minute")  # 速率限制：每分钟10次请求
async def chat(request: Request):
    """
    新闻查询接口

    支持的查询类型：
    - "今天有什么新闻" - 今日热点新闻
    - "今天科技新闻" - 今日分类新闻
    - "昨天的新闻" - 所有新闻

    返回格式：
    - SSE 流式响应（默认）
    - JSON 响应（stream=false）
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="服务未就绪")

    # 尝试解析请求体，支持两种格式
    body = await request.json()

    # 判断请求格式：AgentRequest 有 version 和 vin 字段，ChatRequest 没有
    if "version" in body and "vin" in body:
        # 使用 AgentRequest（完整格式）
        try:
            agent_request = AgentRequest(**body)
            request_id = agent_request.request_id
            query = agent_request.query
            stream = agent_request.stream
            version = agent_request.version
            debug = agent_request.debug or False
            context = agent_request.context
            history = agent_request.history
            user_id = agent_request.user_id
            conversation_id = agent_request.conversation_id
            vin = agent_request.vin
            channel_id = agent_request.channel_id
            voice_zone = agent_request.voice_zone
            timestamp = agent_request.timestamp
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"AgentRequest 格式错误: {str(e)}")
    else:
        # 使用 ChatRequest（简化格式，向后兼容）
        try:
            chat_request = ChatRequest(**body)
            request_id = chat_request.request_id or generate_request_id()
            query = chat_request.query
            stream = chat_request.stream
            version = "2.1"  # 默认版本
            debug = chat_request.debug
            context = None
            history = None
            user_id = None
            conversation_id = None
            vin = None
            channel_id = None
            voice_zone = None
            timestamp = int(time.time() * 1000)  # 使用当前时间戳
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"ChatRequest 格式错误: {str(e)}")

    logger.info(f"收到请求: request_id={request_id}, query={query}, stream={stream}, version={version}")

    try:
        if stream:
            # 流式响应（SSE）
            return StreamingResponse(
                stream_chat(
                    query=query,
                    request_id=request_id,
                    version=version,
                    debug=debug,
                    context=context,
                    history=history,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    vin=vin,
                    channel_id=channel_id,
                    voice_zone=voice_zone,
                    timestamp=timestamp
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # 非流式响应（等待完整结果）
            result = await get_chat_result(
                query=query,
                request_id=request_id,
                version=version,
                debug=debug,
                context=context,
                history=history,
                user_id=user_id,
                conversation_id=conversation_id,
                vin=vin,
                channel_id=channel_id,
                voice_zone=voice_zone,
                timestamp=timestamp
            )
            return result

    except Exception as e:
        logger.error(f"处理请求失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def stream_chat(
    query: str,
    request_id: str,
    version: str = "2.1",
    debug: bool = False,
    context=None,
    history=None,
    user_id: str = None,
    conversation_id: str = None,
    vin: str = None,
    channel_id: str = None,
    voice_zone: int = None,
    timestamp: int = None
):
    """
    流式聊天响应生成器

    Args:
        query: 用户查询
        request_id: 请求ID
        version: LLM Protocol 版本号
        debug: 是否显示调试信息
        context: 上下文信息
        history: 历史对话记录
        user_id: 用户ID
        conversation_id: 会话ID
        vin: 车辆VIN
        channel_id: 渠道ID
        voice_zone: 语音区域
        timestamp: 请求时间戳

    Yields:
        SSE 格式的响应数据
    """
    try:
        async for response in orchestrator.process_query(
            query=query,
            request_id=request_id,
            stream=True,
            version=version,
            debug=debug,
            context=context,
            history=history,
            user_id=user_id,
            conversation_id=conversation_id,
            vin=vin,
            channel_id=channel_id,
            voice_zone=voice_zone,
            timestamp=timestamp
        ):
            yield response

    except Exception as e:
        logger.error(f"流式响应失败: {e}", exc_info=True)
        # 返回错误响应
        error_response = {
            "version": version,
            "request_id": request_id,
            "code": 500,
            "message": str(e),
            "data": None
        }
        yield f"event:error\ndata:{json.dumps(error_response, ensure_ascii=False)}\n\n"


async def get_chat_result(
    query: str,
    request_id: str,
    version: str = "2.1",
    debug: bool = False,
    context=None,
    history=None,
    user_id: str = None,
    conversation_id: str = None,
    vin: str = None,
    channel_id: str = None,
    voice_zone: int = None,
    timestamp: int = None
):
    """
    获取聊天结果（非流式）

    Args:
        query: 用户查询
        request_id: 请求ID
        version: LLM Protocol 版本号
        debug: 是否显示调试信息
        context: 上下文信息
        history: 历史对话记录
        user_id: 用户ID
        conversation_id: 会话ID
        vin: 车辆VIN
        channel_id: 渠道ID
        voice_zone: 语音区域
        timestamp: 请求时间戳

    Returns:
        完整响应数据
    """
    responses = []
    try:
        async for response in orchestrator.process_query(
            query=query,
            request_id=request_id,
            stream=True,
            version=version,
            debug=debug,
            context=context,
            history=history,
            user_id=user_id,
            conversation_id=conversation_id,
            vin=vin,
            channel_id=channel_id,
            voice_zone=voice_zone,
            timestamp=timestamp
        ):
            responses.append(response)
    except Exception as e:
        logger.error(f"获取聊天结果失败: {e}", exc_info=True)
        return {
            "version": version,
            "request_id": request_id,
            "code": 500,
            "message": str(e),
            "data": None
        }

    # 返回最后一个响应
    if responses:
        # 解析 SSE 响应
        last_response = responses[-1]
        if "data:" in last_response:
            try:
                data_str = last_response.split("data:", 1)[1].strip()
                return json.loads(data_str)
            except (json.JSONDecodeError, IndexError) as e:
                logger.error(f"解析响应失败: {e}")

    # 默认响应
    return {
        "version": version,
        "request_id": request_id,
        "code": 0,
        "message": "success",
        "data": None
    }


@app.post("/api/v1/news/summary", tags=["新闻"])
@rate_limit_default(limit="20/minute")  # 速率限制：每分钟20次请求（摘要接口更宽松）
async def news_summary(request: Request, chat_request: ChatRequest):
    """
    新闻摘要接口（简化版，只返回文本）

    快速获取新闻摘要，不包含音频等多模态数据
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="服务未就绪")

    request_id = chat_request.request_id or generate_request_id()

    try:
        # 获取完整结果
        result = await get_chat_result(chat_request.query, request_id)

        # 空值检查
        if result is None:
            logger.warning("获取摘要结果为空")
            return {
                "request_id": request_id,
                "query": chat_request.query,
                "summary": "",
                "news_count": 0
            }

        # 提取摘要文本
        data = result.get("data") or {}
        summary_text = data.get("complete_content", "")
        extension = data.get("extension") or {}
        news_count = extension.get("news_count", 0)

        return {
            "request_id": request_id,
            "query": chat_request.query,
            "summary": summary_text,
            "news_count": news_count
        }

    except Exception as e:
        logger.error(f"获取摘要失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stats", tags=["系统"])
async def get_stats():
    """获取系统统计信息"""
    from core.crawler_service import get_crawler_service

    try:
        crawler = get_crawler_service()
        stats = crawler.get_stats()

        return {
            "database": {
                "total_news": stats.get("total_news", 0),
                "categories": stats.get("by_category", []),
                "today_count": stats.get("today_count", 0)
            },
            "service": {
                "status": "healthy",
                "orchestrator": "ready"
            }
        }

    except Exception as e:
        logger.error(f"获取统计信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 定时任务管理 API ====================

@app.get("/api/v1/scheduler/status", tags=["定时任务"])
async def scheduler_status():
    """获取定时任务调度器状态"""
    if not news_scheduler:
        return {
            "enabled": False,
            "running": False,
            "message": "定时任务调度器未启用"
        }
    
    return {
        "enabled": True,
        "running": news_scheduler.running,
        "jobs": news_scheduler.get_jobs()
    }


@app.get("/api/v1/scheduler/jobs", tags=["定时任务"])
async def list_scheduler_jobs():
    """列出所有定时任务"""
    if not news_scheduler:
        raise HTTPException(status_code=503, detail="定时任务调度器未启用")
    
    return {
        "jobs": news_scheduler.get_jobs()
    }


@app.post("/api/v1/scheduler/jobs/{job_id}/pause", tags=["定时任务"])
async def pause_scheduler_job(job_id: str):
    """暂停指定任务"""
    if not news_scheduler:
        raise HTTPException(status_code=503, detail="定时任务调度器未启用")
    
    success = news_scheduler.pause_job(job_id)
    if success:
        return {"message": f"任务 {job_id} 已暂停"}
    raise HTTPException(status_code=404, detail=f"任务 {job_id} 不存在")


@app.post("/api/v1/scheduler/jobs/{job_id}/resume", tags=["定时任务"])
async def resume_scheduler_job(job_id: str):
    """恢复指定任务"""
    if not news_scheduler:
        raise HTTPException(status_code=503, detail="定时任务调度器未启用")
    
    success = news_scheduler.resume_job(job_id)
    if success:
        return {"message": f"任务 {job_id} 已恢复"}
    raise HTTPException(status_code=404, detail=f"任务 {job_id} 不存在")


@app.post("/api/v1/scheduler/sync", tags=["定时任务"])
async def trigger_sync_now():
    """立即触发一次同步任务"""
    from scheduler.jobs import sync_news_job
    
    logger.info("手动触发同步任务")
    
    try:
        result = sync_news_job()
        return {
            "message": "同步任务已执行",
            "result": result
        }
    except Exception as e:
        logger.error(f"手动同步失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/scheduler/reset-crawl", tags=["定时任务"])
async def reset_crawl_status():
    """
    重置爬取状态
    
    清理所有 crawled_urls 记录，强制下次爬取时重新抓取所有新闻
    用于解决"所有新闻都被跳过"的问题
    """
    from core.crawler_service import get_crawler_service
    
    logger.info("手动重置爬取状态")
    
    try:
        crawler_service = get_crawler_service()
        result = crawler_service.reset_crawl_status()
        return {
            "message": "爬取状态已重置",
            "result": result
        }
    except Exception as e:
        logger.error(f"重置爬取状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/scheduler/crawl", tags=["定时任务"])
async def trigger_crawl_now(force_reload: bool = False):
    """
    立即触发一次爬取任务
    
    Args:
        force_reload: 是否强制重新抓取（清理 crawled_urls，默认 False）
    """
    from scheduler.jobs import crawl_news_job
    
    logger.info(f"手动触发爬取任务 (force_reload={force_reload})")
    
    try:
        result = crawl_news_job(config={"force_reload": force_reload})
        return {
            "message": "爬取任务已执行",
            "result": result
        }
    except Exception as e:
        logger.error(f"手动爬取失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn

    # 从环境变量读取配置
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", 8080))
    debug = os.getenv("API_DEBUG", "false").lower() == "true"

    logger.info(f"启动服务器: http://{host}:{port}")
    logger.info(f"API文档: http://{host}:{port}/docs")

    # 配置 uvicorn
    config = uvicorn.Config(
        "main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )
    server = uvicorn.Server(config)

    # 启动服务器
    server.run()
