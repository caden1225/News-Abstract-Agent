# News TTS Agent 架构设计方案

## 一、需求概述

### 核心功能需求

1. **定时新闻抓取**: 每天早上8点自动抓取配置的新闻源（包括图片），缓存到数据库
2. **智能意图识别**: 判断查询是否为"今天的新闻"或"指定日期的新闻"
3. **新闻摘要生成**: 使用LLM生成摘要，支持think模式
4. **多模态响应**: 返回摘要文本 + 新闻图片链接 + TTS音频
5. **流式输出**: 使用流式方式边生成边返回，优化用户体验

### 技术选型

- **Web框架**: FastAPI
- **LLM编排**: LangGraph
- **数据库**: SQLite (开发) / PostgreSQL (生产)
- **ORM**: SQLAlchemy
- **定时任务**: APScheduler
- **异步并发**: asyncio + aiohttp

---

## 二、现有代码与需求差距分析

### ✅ 已有功能

| 模块 | 功能 | 状态 |
|------|------|------|
| `news_scraper.py` | RSS新闻抓取 | ✅ 已实现 |
| `news_summarizer.py` | LLM摘要生成 | ✅ 已实现 |
| `tts_service.py` | TTS音频生成 | ✅ 已实现 |
| `main.py` | FastAPI接口 | ✅ 已实现 |
| `models.py` | 数据模型定义 | ✅ 已实现 |
| API响应格式 | LLM Protocol 2.1 | ✅ 已兼容 |
| 流式响应 | SSE格式 | ✅ 已实现 |

### ❌ 缺失功能

| 功能 | 重要性 | 现状 |
|------|--------|------|
| **数据库持久化** | 🔴 P0 | 无，只有内存临时数据 |
| **定时任务调度** | 🔴 P0 | 无，需要手动触发 |
| **新闻图片抓取** | 🔴 P0 | 无，RSS只有文本 |
| **日期意图识别** | 🟡 P1 | 无，默认只返回今天 |
| **LangGraph集成** | 🟡 P1 | 无，使用简单的函数调用 |
| **Think模式支持** | 🟢 P2 | 无，标准LLM调用 |
| **混合流式策略** | 🟡 P1 | 简单的逐字流式，无图片/音频混合 |

### 📊 差距总结

**核心差距**:
1. **缺少数据库层**: 无法缓存和持久化新闻
2. **缺少图片处理**: 无法抓取和存储新闻配图
3. **缺少编排框架**: 简单的函数调用难以管理复杂流程
4. **缺少定时任务**: 无法自动化每日抓取

---

## 三、整体架构设计

### 3.1 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Web Layer                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Chat API    │  │  Admin API   │  │ Health Check │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                   Core Orchestrator Layer                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         News Agent Orchestrator (LangGraph)           │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │   │
│  │  │ Intent  │ │ Fetch   │ │Summary  │ │  TTS    │   │   │
│  │  │ Analyzer│ │ News    │ │  News   │ │Generator│   │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                      Service Layer                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  News Service│  │ Summary Svc  │  │  TTS Service │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Scraper Tool │  │   LLM Tool   │  │Image Downloader│     │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    Data Access Layer                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              SQLAlchemy ORM + Repository              │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                      Storage Layer                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Database   │  │ File Storage │  │   Cache      │      │
│  │ (SQLite/PG)  │  │   (Images)   │  │  (Optional)  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 核心组件职责

#### Layer 1: Web Layer (FastAPI)

**职责**: HTTP请求处理、路由分发、响应格式化

**主要模块**:
- `api/routes/chat.py`: 聊天接口
- `api/routes/admin.py`: 管理接口（手动触发任务、查询状态）
- `api/middleware.py`: 中间件（日志、异常处理）

#### Layer 2: Orchestrator Layer (LangGraph)

**职责**: 工作流编排、状态管理、流式控制

**核心类**:
- `NewsAgentOrchestrator`: 主编排器
- `StreamManager`: 流式响应管理
- `ResponseBuilder`: 响应构建器

#### Layer 3: Service Layer

**职责**: 业务逻辑实现、工具调用、数据处理

**主要服务**:
- `NewsService`: 新闻业务逻辑（查询、缓存）
- `SummaryService`: 摘要生成服务
- `TTSService`: TTS音频生成
- `ScraperTool`: 新闻抓取工具（LangGraph Tool）
- `LLMTool`: LLM调用工具（LangGraph Tool）
- `ImageDownloader`: 图片下载工具

#### Layer 4: Data Access Layer

**职责**: 数据持久化、缓存管理

**主要模块**:
- `database/models.py`: SQLAlchemy模型定义
- `database/repositories.py`: Repository模式实现
- `database/session.py`: 数据库会话管理

#### Layer 5: Storage Layer

**职责**: 数据存储

**存储组件**:
- **SQLite/PostgreSQL**: 存储新闻元数据
- **FileSystem**: 存储下载的图片文件
- **Redis (可选)**: 缓存今天的新闻数据

---

## 四、数据库设计

### 4.1 数据模型

#### News (新闻表)

```sql
CREATE TABLE news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(500) NOT NULL,              -- 新闻标题
    link VARCHAR(1000) UNIQUE NOT NULL,       -- 新闻链接（唯一索引）
    summary TEXT,                             -- 原始摘要
    ai_summary TEXT,                          -- AI生成的摘要
    source VARCHAR(100),                      -- 新闻源名称
    published_date DATE NOT NULL,             -- 发布日期
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_published_date (published_date),
    INDEX idx_source (source)
);
```

#### NewsImage (新闻图片表)

```sql
CREATE TABLE news_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id INTEGER NOT NULL,                 -- 关联news.id
    image_url VARCHAR(1000) NOT NULL,         -- 原始图片URL
    local_path VARCHAR(500),                  -- 本地存储路径
    file_size INTEGER,                        -- 文件大小（字节）
    width INTEGER,                            -- 图片宽度
    height INTEGER,                           -- 图片高度
    download_status VARCHAR(20) DEFAULT 'pending', -- pending/downloading/failed/success
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (news_id) REFERENCES news(id) ON DELETE CASCADE,
    INDEX idx_news_id (news_id),
    INDEX idx_download_status (download_status)
);
```

#### NewsReport (新闻播报记录表)

```sql
CREATE TABLE news_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date DATE NOT NULL UNIQUE,         -- 播报日期
    report_text TEXT NOT NULL,                -- 播报文本
    news_count INTEGER NOT NULL,              -- 新闻条数
    news_ids TEXT NOT NULL,                   -- JSON格式存储新闻ID列表
    audio_path VARCHAR(500),                  -- TTS音频文件路径
    audio_duration FLOAT,                     -- 音频时长（秒）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_report_date (report_date)
);
```

#### ScraperJob (抓取任务记录表)

```sql
CREATE TABLE scraper_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_date DATE NOT NULL,                   -- 任务日期
    status VARCHAR(20) NOT NULL,              -- pending/running/completed/failed
    total_news INTEGER DEFAULT 0,             -- 抓取新闻总数
    success_news INTEGER DEFAULT 0,           -- 成功抓取数
    failed_news INTEGER DEFAULT 0,            -- 失败抓取数
    error_message TEXT,                       -- 错误信息
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    INDEX idx_job_date (job_date),
    INDEX idx_status (status)
);
```

### 4.2 ORM模型定义

```python
# database/models.py
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Float, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class News(Base):
    __tablename__ = 'news'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    link = Column(String(1000), unique=True, nullable=False, index=True)
    summary = Column(Text)
    ai_summary = Column(Text)
    source = Column(String(100))
    published_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联关系
    images = relationship("NewsImage", back_populates="news", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_published_date', 'published_date'),
        Index('idx_source', 'source'),
    )

class NewsImage(Base):
    __tablename__ = 'news_images'

    id = Column(Integer, primary_key=True, autoincrement=True)
    news_id = Column(Integer, ForeignKey('news.id', ondelete='CASCADE'), nullable=False)
    image_url = Column(String(1000), nullable=False)
    local_path = Column(String(500))
    file_size = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)
    download_status = Column(String(20), default='pending')
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关联关系
    news = relationship("News", back_populates="images")

    __table_args__ = (
        Index('idx_news_id', 'news_id'),
        Index('idx_download_status', 'download_status'),
    )

class NewsReport(Base):
    __tablename__ = 'news_reports'

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_date = Column(Date, unique=True, nullable=False, index=True)
    report_text = Column(Text, nullable=False)
    news_count = Column(Integer, nullable=False)
    news_ids = Column(Text, nullable=False)  # JSON格式
    audio_path = Column(String(500))
    audio_duration = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

class ScraperJob(Base):
    __tablename__ = 'scraper_jobs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False)  # pending/running/completed/failed
    total_news = Column(Integer, default=0)
    success_news = Column(Integer, default=0)
    failed_news = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    __table_args__ = (
        Index('idx_job_date', 'job_date'),
        Index('idx_status', 'status'),
    )
```

### 4.3 Repository模式

```python
# database/repositories.py
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from database.models import News, NewsImage, NewsReport, ScraperJob

class NewsRepository:
    """新闻数据仓库"""

    def __init__(self, db: Session):
        self.db = db

    def get_by_date(self, date: date) -> List[News]:
        """获取指定日期的新闻"""
        return self.db.query(News).filter(
            News.published_date == date
        ).order_by(News.created_at.desc()).all()

    def get_today_news(self) -> List[News]:
        """获取今天的新闻"""
        return self.get_by_date(date.today())

    def get_by_link(self, link: str) -> Optional[News]:
        """根据链接获取新闻（用于去重）"""
        return self.db.query(News).filter(News.link == link).first()

    def create(self, news_data: dict) -> News:
        """创建新闻记录"""
        news = News(**news_data)
        self.db.add(news)
        self.db.commit()
        self.db.refresh(news)
        return news

    def bulk_create(self, news_list: List[dict]) -> List[News]:
        """批量创建新闻记录"""
        news_objects = [News(**data) for data in news_list]
        self.db.add_all(news_objects)
        self.db.commit()
        return news_objects

class NewsImageRepository:
    """新闻图片数据仓库"""

    def __init__(self, db: Session):
        self.db = db

    def create(self, image_data: dict) -> NewsImage:
        """创建图片记录"""
        image = NewsImage(**image_data)
        self.db.add(image)
        self.db.commit()
        self.db.refresh(image)
        return image

    def bulk_create(self, images: List[dict]) -> List[NewsImage]:
        """批量创建图片记录"""
        image_objects = [NewsImage(**data) for data in images]
        self.db.add_all(image_objects)
        self.db.commit()
        return image_objects

    def get_by_news_id(self, news_id: int) -> List[NewsImage]:
        """获取新闻的所有图片"""
        return self.db.query(NewsImage).filter(
            NewsImage.news_id == news_id,
            NewsImage.download_status == 'success'
        ).all()
```

---

## 五、LangGraph工作流设计

### 5.1 工作流状态定义

```python
# core/workflow/state.py
from typing import TypedDict, List, Optional
from datetime import date

class NewsAgentState(TypedDict):
    """新闻Agent工作流状态"""
    # 输入
    query: str                          # 用户查询
    request_id: str                     # 请求ID
    stream: bool                        # 是否流式

    # 意图分析结果
    intent: str                         # today | specific_date | general
    target_date: Optional[date]         # 目标日期

    # 新闻数据
    news_list: List[dict]               # 新闻列表
    news_count: int                     # 新闻数量

    # 摘要和播报
    summary_with_think: Optional[dict]  # 包含think的摘要
    report_text: str                    # 播报文本

    # 多模态数据
    image_links: List[str]              # 图片链接列表
    audio_data: Optional[str]           # TTS音频数据

    # 流式控制
    frame_data: Optional[dict]          # 当前帧数据（用于流式输出）

    # 错误处理
    error: Optional[str]                # 错误信息
```

### 5.2 LangGraph工作流图

```
                    ┌─────────────────┐
                    │   Start Node    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Intent Analyzer │
                    │  (意图分析)      │
                    └────────┬────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
           today?                   specific_date?
                │                         │
                ▼                         ▼
    ┌───────────────────┐      ┌───────────────────┐
    │  Check Cache      │      │  Fetch News       │
    │  (检查缓存)        │      │  (抓取指定日期)     │
    └────────┬──────────┘      └────────┬──────────┘
             │                           │
        hit? │                   ┌───────┴────────┐
             │                   │                │
     ┌───────▼───────┐   ┌──────▼─────┐  ┌──────▼─────┐
     │ Use Cached    │   │Fetch Online │  │Return Empty │
     │ News (使用缓存)│   │News (在线抓取)│ │(返回空数据)  │
     └───────┬───────┘   └──────┬─────┘  └────────────┘
             │                   │
             └─────────┬─────────┘
                       │
                       ▼
            ┌──────────────────┐
            │ Download Images  │
            │  (下载新闻图片)   │
            └────────┬─────────┘
                     │
                     ▼
            ┌──────────────────┐
            │  Summarize News  │
            │  (生成摘要+think) │
            └────────┬─────────┘
                     │
                     ▼
            ┌──────────────────┐
            │ Generate Report  │
            │ (生成播报稿)      │
            └────────┬─────────┘
                     │
                     ▼
            ┌──────────────────┐
            │ Generate TTS     │
            │  (生成音频)       │
            └────────┬─────────┘
                     │
                     ▼
            ┌──────────────────┐
            │ Build Response   │
            │  (构建响应)       │
            └────────┬─────────┘
                     │
                     ▼
            ┌──────────────────┐
            │   End Node       │
            └──────────────────┘
```

### 5.3 LangGraph实现代码

```python
# core/workflow/graph.py
from langgraph.graph import StateGraph, END
from core.workflow.state import NewsAgentState

async def intent_analyzer(state: NewsAgentState) -> NewsAgentState:
    """意图分析节点"""
    query = state["query"]
    request_id = state["request_id"]

    # 使用LLM分析意图
    from llm_utils.llm_service import LLMService
    intent_result = await LLMService.analyze_intent(query)

    return {
        **state,
        "intent": intent_result["intent"],
        "target_date": intent_result.get("target_date")
    }

async def check_cache(state: NewsAgentState) -> NewsAgentState:
    """检查缓存节点（今天的新闻）"""
    from database.repositories import NewsRepository
    from database.session import get_db

    db = next(get_db())
    repo = NewsRepository(db)

    # 查询今天的新闻
    today_news = repo.get_today_news()

    if today_news:
        # 缓存命中
        return {
            **state,
            "news_list": [n.to_dict() for n in today_news],
            "news_count": len(today_news)
        }
    else:
        # 缓存未命中，需要抓取
        return state

async def fetch_news_online(state: NewsAgentState) -> NewsAgentState:
    """在线抓取新闻节点"""
    from news_scraper import EnhancedNewsScraper

    scraper = EnhancedNewsScraper()

    # 如果是今天的新闻，使用常规抓取
    if state["intent"] == "today":
        news_list = await scraper.fetch_today_news_with_images()
    else:
        # 指定日期的新闻
        target_date = state["target_date"]
        news_list = await scraper.fetch_news_by_date(target_date)

    # 保存到数据库
    from database.repositories import NewsRepository
    from database.session import get_db

    db = next(get_db())
    repo = NewsRepository(db)

    saved_news = []
    for news in news_list:
        # 检查是否已存在（根据link去重）
        existing = repo.get_by_link(news["link"])
        if not existing:
            saved = repo.create(news)
            saved_news.append(saved.to_dict())
        else:
            saved_news.append(existing.to_dict())

    return {
        **state,
        "news_list": saved_news,
        "news_count": len(saved_news)
    }

async def download_images(state: NewsAgentState) -> NewsAgentState:
    """下载新闻图片节点"""
    from services.image_service import ImageDownloader

    downloader = ImageDownloader()
    image_links = []

    for news in state["news_list"]:
        # 下载新闻图片
        images = await downloader.download_news_images(news["link"])
        image_links.extend(images)

    return {
        **state,
        "image_links": image_links
    }

async def summarize_news(state: NewsAgentState) -> NewsAgentState:
    """生成新闻摘要节点（支持think模式）"""
    from services.summary_service import SummaryService

    summary_service = SummaryService(enable_think=True)

    # 批量生成摘要
    news_with_summary = await summary_service.summarize_batch(
        state["news_list"]
    )

    return {
        **state,
        "news_list": news_with_summary
    }

async def generate_report(state: NewsAgentState) -> NewsAgentState:
    """生成播报稿节点"""
    from services.summary_service import SummaryService

    summary_service = SummaryService()

    # 生成播报稿
    report_text = await summary_service.generate_report(
        state["news_list"]
    )

    return {
        **state,
        "report_text": report_text
    }

async def generate_tts(state: NewsAgentState) -> NewsAgentState:
    """生成TTS音频节点"""
    from tts_service import TTSService

    tts_service = TTSService()

    # 生成音频
    audio_result = await tts_service.generate_audio(
        state["report_text"]
    )

    return {
        **state,
        "audio_data": audio_result["audio"]
    }

async def build_response(state: NewsAgentState) -> NewsAgentState:
    """构建响应节点"""
    from core.stream_manager import StreamManager

    stream_manager = StreamManager()

    # 构建最终响应
    frame_data = {
        "report_text": state["report_text"],
        "image_links": state["image_links"],
        "audio_data": state["audio_data"],
        "news_count": state["news_count"]
    }

    return {
        **state,
        "frame_data": frame_data
    }

# 条件边函数
def should_fetch_online(state: NewsAgentState) -> str:
    """判断是否需要在线抓取"""
    if state.get("news_count", 0) > 0:
        return "use_cached"
    else:
        return "fetch_online"

def is_today_intent(state: NewsAgentState) -> str:
    """判断是否是今天意图"""
    if state["intent"] == "today":
        return "today"
    elif state["intent"] == "specific_date":
        return "specific_date"
    else:
        return "general"

# 构建工作流图
def build_news_workflow() -> StateGraph:
    """构建新闻Agent工作流"""
    workflow = StateGraph(NewsAgentState)

    # 添加节点
    workflow.add_node("intent_analyzer", intent_analyzer)
    workflow.add_node("check_cache", check_cache)
    workflow.add_node("fetch_news_online", fetch_news_online)
    workflow.add_node("download_images", download_images)
    workflow.add_node("summarize_news", summarize_news)
    workflow.add_node("generate_report", generate_report)
    workflow.add_node("generate_tts", generate_tts)
    workflow.add_node("build_response", build_response)

    # 设置入口
    workflow.set_entry_point("intent_analyzer")

    # 添加边（连接节点）
    workflow.add_conditional_edges(
        "intent_analyzer",
        is_today_intent,
        {
            "today": "check_cache",
            "specific_date": "fetch_news_online",
            "general": "fetch_news_online"
        }
    )

    workflow.add_conditional_edges(
        "check_cache",
        should_fetch_online,
        {
            "use_cached": "download_images",
            "fetch_online": "fetch_news_online"
        }
    )

    workflow.add_edge("fetch_news_online", "download_images")
    workflow.add_edge("download_images", "summarize_news")
    workflow.add_edge("summarize_news", "generate_report")
    workflow.add_edge("generate_report", "generate_tts")
    workflow.add_edge("generate_tts", "build_response")
    workflow.add_edge("build_response", END)

    return workflow.compile()
```

---

## 六、流式响应策略设计

### 6.1 混合流式响应格式

```
┌─────────────────────────────────────────────────────────────┐
│                    流式响应时间线                             │
├─────────────────────────────────────────────────────────────┤
│ Frame 1-N:     逐字返回文本播报稿                             │
│                 frame_text: "各" → "各位" → "各位听众"...    │
│                 frame_is_final: false                        │
├─────────────────────────────────────────────────────────────┤
│ Frame N+1:     返回第一条新闻图片                             │
│                 frame_parts: [{type: "image", ...}]          │
│                 frame_is_final: false                        │
├─────────────────────────────────────────────────────────────┤
│ Frame N+2:     返回第二条新闻图片                             │
│                 frame_parts: [{type: "image", ...}]          │
│                 frame_is_final: false                        │
├─────────────────────────────────────────────────────────────┤
│ ...                                                        │
├─────────────────────────────────────────────────────────────┤
│ Final Frame:   返回完整文本 + 音频数据                         │
│                 complete_content: "完整播报稿..."             │
│                 frame_parts: [{type: "audio", ...}]          │
│                 frame_is_final: true                         │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 流式响应管理器

```python
# core/stream_manager.py
class StreamManager:
    """流式响应管理器"""

    def __init__(self):
        self.frame_id = 0

    async def stream_text(
        self,
        text: str,
        request: AgentRequest
    ) -> AsyncGenerator[str, None]:
        """流式返回文本（逐字）"""

        content = ""
        for char in text:
            content += char

            frame = ResponseData(
                frame_id=self.frame_id,
                frame_timestamp=int(time.time() * 1000),
                frame_text=content,
                frame_is_final=False
            )

            response = BaseResponse(
                version=request.version,
                request_id=request.request_id,
                code=0,
                message="success",
                data=frame
            )

            yield f"event:data\ndata:{response.json()}\n\n"
            self.frame_id += 1
            await asyncio.sleep(0.02)  # 控制发送频率

    async def stream_images(
        self,
        image_links: List[str],
        request: AgentRequest
    ) -> AsyncGenerator[str, None]:
        """流式返回图片链接"""

        for img_url in image_links:
            frame_part = FramePart(
                type="image",
                image=FramePartImage(
                    format="url",
                    data=img_url
                )
            )

            frame = ResponseData(
                frame_id=self.frame_id,
                frame_timestamp=int(time.time() * 1000),
                frame_text="",
                frame_is_final=False,
                frame_parts=[frame_part]
            )

            response = BaseResponse(
                version=request.version,
                request_id=request.request_id,
                code=0,
                message="success",
                data=frame
            )

            yield f"event:data\ndata:{response.json()}\n\n"
            self.frame_id += 1

    async def stream_final(
        self,
        complete_text: str,
        audio_data: str,
        request: AgentRequest
    ) -> str:
        """返回最终帧（包含完整文本和音频）"""

        # 构建音频frame_part
        audio_part = FramePart(
            type="audio",
            audio=FramePartAudio(
                format="wav",
                data=f"data:;base64,{audio_data}",
                is_final=True
            )
        )

        frame = ResponseData(
            frame_id=self.frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text="",
            frame_is_final=True,
            complete_content=complete_text,
            frame_parts=[audio_part]
        )

        response = BaseResponse(
            version=request.version,
            request_id=request.request_id,
            code=0,
            message="success",
            data=frame
        )

        return f"event:data\ndata:{response.json()}\n\n"
```

### 6.3 混合流式编排

```python
# core/orchestrator.py
class NewsAgentOrchestrator:
    """新闻Agent核心编排器"""

    def __init__(self):
        self.workflow = build_news_workflow()
        self.stream_manager = StreamManager()

    async def process_query(
        self,
        query: str,
        request: AgentRequest
    ) -> AsyncGenerator[str, None]:
        """处理查询并返回流式响应"""

        # 1. 执行工作流获取数据
        initial_state = {
            "query": query,
            "request_id": request.request_id,
            "stream": request.stream,
            "news_list": [],
            "news_count": 0,
            "image_links": [],
            "audio_data": None,
            "report_text": ""
        }

        # 执行工作流
        final_state = await self.workflow.ainvoke(initial_state)

        # 2. 流式返回文本
        async for frame in self.stream_manager.stream_text(
            final_state["report_text"],
            request
        ):
            yield frame

        # 3. 流式返回图片
        async for frame in self.stream_manager.stream_images(
            final_state["image_links"],
            request
        ):
            yield frame

        # 4. 返回最终帧（音频）
        final_frame = await self.stream_manager.stream_final(
            final_state["report_text"],
            final_state["audio_data"],
            request
        )
        yield final_frame
```

---

## 七、定时任务设计

### 7.1 定时任务调度器

```python
# scheduler/news_scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class NewsScheduler:
    """新闻定时任务调度器"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    async def daily_news_fetch_job(self):
        """每天8点执行新闻抓取任务"""
        logger.info(f"开始执行每日新闻抓取任务: {datetime.now()}")

        try:
            from services.news_service import NewsService
            from database.repositories import NewsRepository
            from database.session import get_db

            db = next(get_db())
            news_service = NewsService(db)

            # 执行抓取
            result = await news_service.fetch_and_store_news()

            logger.info(
                f"每日新闻抓取完成: "
                f"总数={result['total']}, "
                f"成功={result['success']}, "
                f"失败={result['failed']}"
            )

        except Exception as e:
            logger.error(f"每日新闻抓取任务失败: {e}", exc_info=True)

    def start(self):
        """启动调度器"""
        # 每天早上8点执行
        self.scheduler.add_job(
            self.daily_news_fetch_job,
            trigger=CronTrigger(hour=8, minute=0),
            id='daily_news_fetch',
            name='每日新闻抓取',
            replace_existing=True
        )

        self.scheduler.start()
        logger.info("新闻定时任务调度器已启动")

    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()
        logger.info("新闻定时任务调度器已关闭")
```

### 7.2 启动定时任务

```python
# main.py
from scheduler.news_scheduler import NewsScheduler

# 全局调度器实例
scheduler = None

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    global scheduler

    # 初始化数据库
    init_db()

    # 启动定时任务调度器
    scheduler = NewsScheduler()
    scheduler.start()
    logger.info("应用启动完成")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理"""
    global scheduler

    if scheduler:
        scheduler.shutdown()
    logger.info("应用关闭完成")
```

---

## 八、增强的新闻抓取器

### 8.1 图片提取实现

```python
# news_scraper_enhanced.py
import feedparser
import requests
from bs4 import BeautifulSoup
from typing import List, Dict
import re

class EnhancedNewsScraper:
    """增强的新闻抓取器 - 支持图片提取"""

    async def extract_news_images(self, news_url: str) -> List[str]:
        """从新闻页面提取图片URL"""

        try:
            response = requests.get(news_url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')

            images = []

            # 查找所有img标签
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src')

                if src:
                    # 过滤无效图片
                    if self._is_valid_image(src):
                        # 转换为绝对URL
                        absolute_url = self._to_absolute_url(src, news_url)
                        images.append(absolute_url)

            return images[:3]  # 最多返回3张图片

        except Exception as e:
            logger.error(f"提取图片失败: {e}")
            return []

    def _is_valid_image(self, url: str) -> bool:
        """判断是否是有效的图片URL"""
        # 排除小图标、头像等
        invalid_patterns = [
            r'icon', r'logo', r'avatar', r'sprite',
            r'\.gif$', r'\.svg$', r'1x1', r'pixel'
        ]

        for pattern in invalid_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False

        return True

    def _to_absolute_url(self, url: str, base_url: str) -> str:
        """转换为绝对URL"""
        from urllib.parse import urljoin

        if url.startswith('http'):
            return url
        else:
            return urljoin(base_url, url)
```

### 8.2 图片下载服务

```python
# services/image_service.py
import aiohttp
import asyncio
from pathlib import Path
from typing import List
import hashlib

class ImageDownloader:
    """图片下载器"""

    def __init__(self, storage_dir: str = "data/images"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def download_news_images(
        self,
        news_id: int,
        image_urls: List[str]
    ) -> List[str]:
        """批量下载新闻图片"""

        downloaded_paths = []

        async with aiohttp.ClientSession() as session:
            tasks = [
                self.download_single_image(session, news_id, url)
                for url in image_urls
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, str):  # 成功下载
                    downloaded_paths.append(result)
                elif isinstance(result, Exception):
                    logger.warning(f"图片下载失败: {result}")

        return downloaded_paths

    async def download_single_image(
        self,
        session: aiohttp.ClientSession,
        news_id: int,
        url: str
    ) -> str:
        """下载单张图片"""

        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    content = await response.read()

                    # 生成文件名
                    file_hash = hashlib.md5(content).hexdigest()
                    ext = self._get_extension(url)
                    filename = f"{news_id}_{file_hash}{ext}"
                    filepath = self.storage_dir / filename

                    # 保存文件
                    with open(filepath, 'wb') as f:
                        f.write(content)

                    logger.info(f"图片下载成功: {filename}")
                    return str(filepath)

        except Exception as e:
            logger.error(f"下载图片失败 {url}: {e}")
            raise

    def _get_extension(self, url: str) -> str:
        """从URL获取文件扩展名"""
        if '.jpg' in url or '.jpeg' in url:
            return '.jpg'
        elif '.png' in url:
            return '.png'
        elif '.webp' in url:
            return '.webp'
        else:
            return '.jpg'  # 默认
```

---

## 九、详细开发计划

### Phase 1: 数据库设计与实现 (2天)

**任务清单**:
1. ✅ 设计数据库表结构
2. ✅ 实现SQLAlchemy ORM模型
3. ✅ 实现Repository模式
4. ✅ 编写数据库迁移脚本
5. ✅ 编写单元测试

**产出**:
- `database/models.py`
- `database/repositories.py`
- `database/migrations/`
- `tests/test_database.py`

**验收标准**:
- [ ] 所有表创建成功
- [ ] CRUD操作正常
- [ ] 关联查询正常
- [ ] 单元测试通过

---

### Phase 2: 增强新闻抓取 (2天)

**任务清单**:
1. ✅ 实现图片提取（BeautifulSoup）
2. ✅ 实现图片下载（aiohttp并发）
3. ✅ 实现图片存储（本地/云存储）
4. ✅ 集成到数据库保存流程
5. ✅ 编写测试用例

**产出**:
- `news_scraper_enhanced.py`
- `services/image_service.py`
- `tests/test_scraper.py`

**验收标准**:
- [ ] 能成功提取新闻图片
- [ ] 图片下载成功率>80%
- [ ] 图片正确保存到数据库
- [ ] 测试用例通过

---

### Phase 3: LangGraph基础搭建 (3天)

**任务清单**:
1. ✅ 安装和配置LangGraph
2. ✅ 定义State和Tools
3. ✅ 实现意图分析节点
4. ✅ 实现新闻获取节点（缓存/在线）
5. ✅ 实现基础工作流
6. ✅ 编写测试用例

**产出**:
- `core/workflow/state.py`
- `core/workflow/nodes/`
- `core/workflow/graph.py`
- `tests/test_workflow.py`

**代码示例**:

```python
# core/workflow/nodes/intent_node.py
from typing import Dict, Any
from core.workflow.state import NewsAgentState

async def intent_analyzer_node(
    state: NewsAgentState
) -> Dict[str, Any]:
    """意图分析节点"""

    query = state["query"]

    # 使用LLM分析意图
    prompt = f"""分析用户查询意图，判断是：
1. today - 查询今天的新闻
2. specific_date - 查询指定日期的新闻（需提取日期）
3. general - 一般性新闻查询

查询：{query}

返回JSON格式：{{"intent": "today/specific_date/general", "date": "YYYY-MM-DD"（如果适用）}}
"""

    messages = [
        {"role": "system", "content": "你是意图分析专家"},
        {"role": "user", "content": prompt}
    ]

    result = await llm_tool.invoke(messages)
    intent_data = json.loads(result)

    return {
        "intent": intent_data["intent"],
        "target_date": intent_data.get("date")
    }
```

---

### Phase 4: 定时任务系统 (1-2天)

**任务清单**:
1. ✅ 集成APScheduler
2. ✅ 实现每天8点的定时抓取任务
3. ✅ 实现任务日志记录
4. ✅ 实现任务管理API（手动触发、状态查询）
5. ✅ 编写测试用例

**产出**:
- `scheduler/news_scheduler.py`
- `api/routes/admin.py`

---

### Phase 5: 核心编排器实现 (2天)

**任务清单**:
1. ✅ 实现`NewsAgentOrchestrator`
2. ✅ 集成LangGraph工作流
3. ✅ 实现流式响应管理
4. ✅ 实现错误处理和降级逻辑
5. ✅ 编写测试用例

**产出**:
- `core/orchestrator.py`
- `core/stream_manager.py`

**技术细节**:
```python
class NewsAgentOrchestrator:
    """新闻Agent核心编排器"""

    def __init__(self):
        self.workflow = build_news_workflow()
        self.stream_manager = StreamManager()

    async def process_query(
        self,
        query: str,
        request: AgentRequest
    ) -> AsyncGenerator[str, None]:
        """处理查询并返回流式响应"""

        try:
            # 1. 初始化工作流状态
            initial_state = {
                "query": query,
                "request_id": request.request_id,
                "stream": request.stream
            }

            # 2. 执行工作流
            async for state_update in self.workflow.astream(initial_state):
                # 3. 实时流式返回
                if state_update.get("frame_data"):
                    frame = self.stream_manager.build_frame(
                        state_update["frame_data"]
                    )
                    yield frame

            # 4. 返回最终帧
            final_state = await self.workflow.ainvoke(initial_state)
            final_frame = self.stream_manager.build_final_frame(final_state)
            yield final_frame

        except Exception as e:
            logger.error(f"处理查询失败: {e}")
            error_frame = self.stream_manager.build_error_frame(
                request_id=request.request_id,
                error=str(e)
            )
            yield error_frame
```

---

### Phase 6: API层实现 (1-2天)

**任务清单**:
1. ✅ 实现聊天接口（流式SSE）
2. ✅ 实现健康检查接口
3. ✅ 实现管理接口（手动触发任务、查询状态）
4. ✅ 编写API测试用例

**产出**:
- `api/routes/chat.py`
- `api/routes/admin.py`

---

### Phase 7: 流式响应优化 (1-2天)

**任务清单**:
1. ✅ 实现文本逐字流式返回
2. ✅ 实现图片链接中间返回
3. ✅ 实现音频数据最终返回
4. ✅ 优化帧发送频率和时机
5. ✅ 编写测试用例

**产出**:
- `core/stream_manager.py`
- `core/response_builder.py`

---

### Phase 8: 测试与优化 (2-3天)

**任务清单**:
1. ✅ 单元测试（所有工具和节点）
2. ✅ 集成测试（完整工作流）
3. ✅ 性能测试（并发、响应时间）
4. ✅ 端到端测试（从请求到响应）
5. ✅ 错误场景测试
6. ✅ 文档完善

**产出**:
- `tests/`目录
- 测试报告
- API文档

---

### Phase 9: 部署与监控 (1-2天)

**任务清单**:
1. ✅ Docker镜像构建
2. ✅ 配置生产环境数据库
3. ✅ 配置日志收集
4. ✅ 配置监控告警
5. ✅ 编写部署文档

---

## 十、关键技术点

### 10.1 LangGraph异步流式支持

```python
# 使用astream实现流式输出
async for state in workflow.astream(initial_state):
    # 每个节点执行完都会返回状态
    if "summary" in state:
        # 可以在这里进行中间流式返回
        pass
```

### 10.2 并发图片下载

```python
import asyncio
import aiohttp

async def download_images_concurrent(urls: List[str]) -> List[str]:
    """并发下载图片"""
    async with aiohttp.ClientSession() as session:
        tasks = [download_single_image(session, url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, str)]
```

### 10.3 Think模式支持

```python
class LLMTool:
    async def invoke_with_think(self, messages: List[Dict]):
        """支持think模式的LLM调用"""

        # 使用支持thinking的模型
        response = await self.llm_client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            # 某些模型支持的think参数
            extra_body={
                "enable_thinking": True,
                "thinking_tokens": 2000
            }
        )

        # 解析结果
        content = response.choices[0].message.content
        think_content = response.choices[0].message.thinking_content

        return {
            "content": content,
            "think": think_content
        }
```

### 10.4 混合流式响应实现

```python
class StreamManager:
    """流式响应管理器"""

    async def mixed_stream(
        self,
        text: str,
        images: List[str],
        audio: str
    ):
        """混合流式返回：文本 → 图片 → 音频"""

        # 1. 文本逐字流式
        for i, char in enumerate(text):
            yield self.build_text_frame(char, i)
            await asyncio.sleep(0.02)

        # 2. 图片批量返回
        for idx, img_url in enumerate(images):
            yield self.build_image_frame(img_url, i + idx)

        # 3. 音频最终返回
        yield self.build_final_audio_frame(audio, i + idx + 1)
```

---

## 十一、风险与挑战

### 11.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LangGraph学习曲线 | 开发周期延长 | 提前学习参考案例 |
| TTS生成时间过长 | 用户体验差 | 优化为异步并行生成 |
| 图片下载失败率 | 图片缺失 | 添加降级和重试机制 |
| 数据库性能瓶颈 | 响应慢 | 添加索引和缓存 |
| 定时任务执行失败 | 数据缺失 | 添加监控和告警 |

### 11.2 性能优化建议

1. **并发处理**：新闻抓取和图片下载使用异步并发
2. **缓存策略**：今天的新闻缓存到数据库和内存
3. **流式优化**：边生成边返回，不等待全部完成
4. **数据库优化**：合理设计索引，避免N+1查询
5. **CDN加速**：图片上传到CDN，加速访问

---

## 十二、总结

### 12.1 开发优先级

**P0 (核心功能)**:
- 数据库设计和实现
- 增强新闻抓取（含图片）
- LangGraph工作流基础实现
- 混合流式响应

**P1 (重要功能)**:
- 定时任务系统
- 意图分析（今天/指定日期）
- Think模式支持

**P2 (增强功能)**:
- 任务管理API
- 监控和日志
- 性能优化

### 12.2 预计工期

- **Phase 1-3**: 基础设施 + 工作流 = 7-9天
- **Phase 4-6**: 定时任务 + 编排器 + API = 5-6天
- **Phase 7-8**: 流式优化 + 测试 = 3-5天
- **Phase 9**: 部署上线 = 1-2天

**总计**: 16-22天（约3-4周）

### 12.3 后续扩展

- 支持更多新闻源（微博热搜、抖音热点等）
- 支持个性化推荐（基于历史查询）
- 支持多语言TTS
- 支持语音交互（ASR + TTS完整闭环）
- 添加新闻分类和标签

---

**文档版本**: v1.0
**创建日期**: 2025-01-09
**最后更新**: 2025-01-09
