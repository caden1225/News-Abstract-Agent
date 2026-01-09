# News TTS Agent 轻量级架构设计方案 v2.0

> 基于用户反馈优化后的轻量级、高性能架构

---

## 一、核心设计原则

### 1.1 轻量级原则
- ✅ **零ORM依赖**：使用SQLite + 原生SQL
- ✅ **最小依赖**：只使用必要的Python库
- ✅ **简单直观**：代码易读、易维护

### 1.2 缓存优先原则
- ✅ **快速响应**：今天新闻直接返回缓存（<100ms）
- ✅ **智能降级**：缓存未命中时才调用LLM和爬虫
- ✅ **成本优化**：减少不必要的LLM调用

### 1.3 渐进式响应原则
- ✅ **首帧优化**：第一帧包含所有图片链接
- ✅ **流式文本**：逐字返回文本播报
- ✅ **最终音频**：最后一帧返回完整音频

---

## 二、轻量级数据存储设计

### 2.1 数据库选型

**选择：SQLite + 原生SQL**

```python
# 数据库操作示例（无ORM）
import sqlite3
from typing import List, Dict, Optional
from datetime import date, datetime
import json

class NewsDatabase:
    """轻量级新闻数据库（零ORM依赖）"""

    def __init__(self, db_path: str = "data/news.db"):
        """初始化数据库连接"""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # 支持字典访问
        self._init_tables()

    def _init_tables(self):
        """初始化数据表"""
        # 新闻表
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                link TEXT UNIQUE NOT NULL,
                summary TEXT,
                ai_summary TEXT,
                source TEXT,
                category TEXT,
                published_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                images TEXT  -- JSON格式存储图片URL列表
            )
        """)

        # 创建索引
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_published_date
            ON news(published_date)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_category
            ON news(category)
        """)

        # 播报记录表
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date DATE UNIQUE NOT NULL,
                report_text TEXT NOT NULL,
                news_ids TEXT NOT NULL,  -- JSON数组
                audio_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.commit()

    def get_today_news(
        self,
        category: Optional[str] = None
    ) -> List[Dict]:
        """获取今天的新闻

        Args:
            category: 可选的分类过滤

        Returns:
            新闻字典列表
        """
        today = date.today().isoformat()

        if category:
            cursor = self.conn.execute(
                """SELECT * FROM news
                   WHERE published_date = ? AND category = ?
                   ORDER BY created_at DESC""",
                (today, category)
            )
        else:
            cursor = self.conn.execute(
                """SELECT * FROM news
                   WHERE published_date = ?
                   ORDER BY created_at DESC""",
                (today,)
            )

        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_news_by_keywords(
        self,
        keywords: List[str],
        limit: int = 10
    ) -> List[Dict]:
        """根据关键词搜索新闻

        Args:
            keywords: 关键词列表
            limit: 返回数量限制

        Returns:
            匹配的新闻列表
        """
        # 构建SQL查询
        where_clauses = []
        params = []

        for keyword in keywords:
            where_clauses.append(
                "(title LIKE ? OR summary LIKE ? OR ai_summary LIKE ?)"
            )
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

        sql = f"""
            SELECT * FROM news
            WHERE {' OR '.join(where_clauses)}
            ORDER BY published_date DESC
            LIMIT ?
        """
        params.append(limit)

        cursor = self.conn.execute(sql, params)
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def insert_news(
        self,
        news_data: List[Dict]
    ) -> int:
        """批量插入新闻（去重）"""
        inserted_count = 0

        for news in news_data:
            try:
                self.conn.execute(
                    """INSERT OR IGNORE INTO news
                       (title, link, summary, source, published_date, images)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        news['title'],
                        news['link'],
                        news.get('summary', ''),
                        news.get('source', ''),
                        news.get('published_date', date.today().isoformat()),
                        json.dumps(news.get('images', []), ensure_ascii=False)
                    )
                )
                if self.conn.total_changes > 0:
                    inserted_count += 1
            except sqlite3.IntegrityError:
                # 跳过重复的新闻
                continue

        self.conn.commit()
        return inserted_count

    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        """将数据库行转换为字典"""
        data = dict(row)
        # 解析JSON字段
        if data.get('images'):
            data['images'] = json.loads(data['images'])
        else:
            data['images'] = []
        return data

    def close(self):
        """关闭数据库连接"""
        self.conn.close()
```

### 2.2 内存缓存层

```python
from datetime import date
from typing import List, Dict, Optional
import asyncio

class NewsCache:
    """内存缓存层（进一步优化性能）"""

    def __init__(self):
        self._cache: Dict[str, List[Dict]] = {}
        self._cache_date: Optional[date] = None

    def get_today_news(
        self,
        category: Optional[str] = None
    ) -> Optional[List[Dict]]:
        """获取内存中的今天新闻缓存

        Returns:
            如果缓存存在且有效，返回新闻列表；否则返回None
        """
        today = date.today()

        # 检查缓存是否过期
        if self._cache_date != today:
            return None

        # 返回缓存
        cache_key = f"today_{category or 'all'}"
        return self._cache.get(cache_key)

    def set_today_news(
        self,
        news_list: List[Dict],
        category: Optional[str] = None
    ):
        """设置今天的新闻缓存"""
        today = date.today()

        # 更新缓存日期
        self._cache_date = today

        # 存储缓存
        cache_key = f"today_{category or 'all'}"
        self._cache[cache_key] = news_list

    def clear(self):
        """清空缓存"""
        self._cache = {}
        self._cache_date = None
```

### 2.3 数据访问层总览

```
┌─────────────────────────────────────────────────────────┐
│                   业务逻辑层                             │
│  (NewsAgentOrchestrator)                                 │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│               轻量级数据访问层                            │
│  ┌─────────────────────────────────────────────────┐    │
│  │         NewsDataService                         │    │
│  │  - get_today_news(category)                     │    │
│  │  - search_news(keywords)                        │    │
│  │  - save_news(news_list)                         │    │
│  └────────────┬────────────────────────────────────┘    │
└────────────────┼─────────────────────────────────────────┘
                 │
    ┌────────────┴────────────┐
    │                         │
    ▼                         ▼
┌─────────────────┐   ┌─────────────────┐
│  NewsCache      │   │  NewsDatabase   │
│  (内存缓存)      │   │  (SQLite)       │
│  ~1ms 响应       │   │  ~10ms 响应     │
└─────────────────┘   └─────────────────┘
```

---

## 三、优化后的意图识别与缓存策略

### 3.1 意图识别分类

```python
from enum import Enum
from typing import List, Optional
from datetime import date, timedelta

class QueryIntent(Enum):
    """查询意图枚举"""
    TODAY_GENERAL = "today_general"       # 今天的通用新闻
    TODAY_CATEGORIZED = "today_categorized" # 今天的分类新闻
    SPECIFIC_DATE = "specific_date"        # 指定日期新闻
    KEYWORD_SEARCH = "keyword_search"      # 关键词搜索
    UNKNOWN = "unknown"                    # 未知意图

class IntentAnalysisResult:
    """意图分析结果"""
    intent: QueryIntent
    target_date: Optional[date]
    category: Optional[str]
    keywords: List[str]
    use_cache: bool

    def __init__(
        self,
        intent: QueryIntent,
        target_date: Optional[date] = None,
        category: Optional[str] = None,
        keywords: List[str] = None,
        use_cache: bool = False
    ):
        self.intent = intent
        self.target_date = target_date
        self.category = category
        self.keywords = keywords or []
        self.use_cache = use_cache
```

### 3.2 两阶段意图识别

**阶段1：快速规则匹配（零成本）**

```python
class FastIntentClassifier:
    """快速意图分类器（基于规则）"""

    # 时间关键词
    TIME_KEYWORDS = {
        'today': ['今天', '今日', '最新', '当前'],
        'yesterday': ['昨天', '昨日'],
        'this_week': ['本周', '这周'],
    }

    # 分类关键词
    CATEGORY_KEYWORDS = {
        '科技': ['科技', 'AI', '人工智能', '芯片', '互联网', '5G'],
        '财经': ['财经', '股市', '经济', '金融', '股票'],
        '体育': ['体育', '足球', '篮球', 'NBA', '奥运'],
        '娱乐': ['娱乐', '电影', '明星', '音乐'],
    }

    def classify(self, query: str) -> IntentAnalysisResult:
        """快速分类用户查询"""
        query_lower = query.lower()

        # 1. 判断时间
        target_date = None
        time_intent = None

        for time_type, keywords in self.TIME_KEYWORDS.items():
            if any(kw in query for kw in keywords):
                if time_type == 'today':
                    target_date = date.today()
                    time_intent = 'today'
                elif time_type == 'yesterday':
                    target_date = date.today() - timedelta(days=1)
                    time_intent = 'specific_date'
                break

        # 2. 判断分类
        category = None
        for cat, keywords in self.CATEGORY_KEYWORDS.items():
            if any(kw in query for kw in keywords):
                category = cat
                break

        # 3. 判断是否可以使用缓存
        use_cache = (
            time_intent == 'today' and  # 今天的新闻
            target_date is not None     # 有明确日期
        )

        # 4. 确定意图类型
        if use_cache and category:
            intent = QueryIntent.TODAY_CATEGORIZED
        elif use_cache:
            intent = QueryIntent.TODAY_GENERAL
        elif target_date:
            intent = QueryIntent.SPECIFIC_DATE
        else:
            intent = QueryIntent.KEYWORD_SEARCH

        return IntentAnalysisResult(
            intent=intent,
            target_date=target_date,
            category=category,
            keywords=[],
            use_cache=use_cache
        )
```

**阶段2：LLM深度分析（仅在需要时）**

```python
class LLMIntentAnalyzer:
    """LLM意图分析器（深度分析）"""

    async def analyze(
        self,
        query: str,
        fast_result: IntentAnalysisResult
    ) -> IntentAnalysisResult:
        """使用LLM进行深度意图分析

        仅在快速分类无法确定时调用
        """
        # 如果快速分类已经确定，直接返回
        if fast_result.use_cache:
            return fast_result

        # 构建LLM提示词
        prompt = f"""分析用户查询意图，返回JSON格式：

查询：{query}

请返回以下JSON：
{{
    "intent": "today_general | today_categorized | specific_date | keyword_search",
    "target_date": "YYYY-MM-DD（如果提到具体日期）",
    "category": "新闻分类（科技/财经/体育/娱乐等，如果有）",
    "keywords": ["搜索关键词列表（如果是搜索类查询）"]
}}

注意：
- 如果用户查询"今天的XX新闻"，intent为today_categorized
- 如果用户查询"昨天/特定日期的新闻"，intent为specific_date
- 如果用户查询某个主题的新闻，提取关键词
"""

        messages = [
            {"role": "system", "content": "你是意图分析专家"},
            {"role": "user", "content": prompt}
        ]

        # 调用LLM
        result = await llm_service.call_llm(
            messages=messages,
            temperature=0.1,  # 低温度保证稳定性
            response_format="json"
        )

        # 解析结果
        analysis = json.loads(result)

        return IntentAnalysisResult(
            intent=QueryIntent(analysis['intent']),
            target_date=self._parse_date(analysis.get('target_date')),
            category=analysis.get('category'),
            keywords=analysis.get('keywords', []),
            use_cache=False
        )
```

### 3.3 智能路由策略

```python
class NewsServiceRouter:
    """新闻服务路由器"""

    def __init__(
        self,
        cache: NewsCache,
        database: NewsDatabase
    ):
        self.cache = cache
        self.database = database
        self.fast_classifier = FastIntentClassifier()
        self.llm_analyzer = LLMIntentAnalyzer()

    async def route_query(
        self,
        query: str
    ) -> tuple[List[Dict], bool]:
        """路由查询到适当的数据源

        Returns:
            (新闻列表, 是否来自缓存)
        """
        # 阶段1: 快速分类
        fast_result = self.fast_classifier.classify(query)

        # 如果可以使用缓存，直接返回
        if fast_result.use_cache:
            # 先查内存缓存
            cached = self.cache.get_today_news(
                category=fast_result.category
            )

            if cached:
                logger.info("✅ 命中内存缓存")
                return cached, True

            # 再查数据库缓存
            db_news = self.database.get_today_news(
                category=fast_result.category
            )

            if db_news:
                logger.info("✅ 命中数据库缓存")
                # 更新内存缓存
                self.cache.set_today_news(
                    db_news,
                    category=fast_result.category
                )
                return db_news, True

        # 阶段2: LLM深度分析
        deep_result = await self.llm_analyzer.analyze(
            query,
            fast_result
        )

        # 根据深度分析结果处理
        if deep_result.intent == QueryIntent.SPECIFIC_DATE:
            # 指定日期的新闻（需要在线抓取）
            news = await self._fetch_news_by_date(
                deep_result.target_date
            )
            return news, False

        elif deep_result.intent == QueryIntent.KEYWORD_SEARCH:
            # 关键词搜索
            news = self.database.get_news_by_keywords(
                deep_result.keywords
            )

            if not news:
                # 数据库无结果，在线搜索
                news = await self._search_news_online(
                    deep_result.keywords
                )
            return news, False

        else:
            # 其他情况返回空列表
            return [], False
```

---

## 四、优化后的流式响应格式

### 4.1 响应帧设计

```python
@dataclass
class StreamFrame:
    """流式响应帧"""
    frame_id: int
    timestamp: int
    frame_text: str              # 当前累积的文本
    is_final: bool               # 是否最终帧

    # 多模态数据（仅在特定帧出现）
    images: Optional[List[str]] = None      # 仅第1帧
    audio: Optional[str] = None             # 仅最终帧
    complete_content: Optional[str] = None  # 仅最终帧
```

### 4.2 响应时间线

```
┌────────────────────────────────────────────────────────────┐
│ Frame 0: 初始帧（图片 + 初始文本）                          │
│ ├─ frame_id: 0                                            │
│ ├─ frame_text: "各"                                        │
│ ├─ is_final: false                                        │
│ ├─ images: ["http://img1.jpg", "http://img2.jpg", ...]   │
│ └─ audio: None                                            │
├────────────────────────────────────────────────────────────┤
│ Frame 1-N: 文本流式帧                                       │
│ ├─ frame_id: 1, 2, 3, ...                                │
│ ├─ frame_text: "各位" → "各位听众" → "各位听众好" ...    │
│ ├─ is_final: false                                        │
│ ├─ images: None  ⭐ (不再重复)                             │
│ └─ audio: None                                            │
├────────────────────────────────────────────────────────────┤
│ Frame Final: 最终帧（音频）                                 │
│ ├─ frame_id: N+1                                          │
│ ├─ frame_text: ""                                         │
│ ├─ is_final: true                                         │
│ ├─ complete_content: "完整文本..."                         │
│ ├─ images: None                                           │
│ └─ audio: "data:;base64,UklGRiQAAAB..."                  │
└────────────────────────────────────────────────────────────┘
```

### 4.3 流式响应生成器

```python
class OptimizedStreamGenerator:
    """优化的流式响应生成器"""

    async def generate_response(
        self,
        query: str,
        request: AgentRequest
    ) -> AsyncGenerator[str, None]:
        """生成优化的流式响应"""

        # 1. 获取新闻（智能路由）
        news_list, from_cache = await self.router.route_query(query)

        if not news_list:
            yield self._build_error_frame("未找到相关新闻")
            return

        # 2. 提取所有图片URL
        image_urls = []
        for news in news_list:
            if news.get('images'):
                image_urls.extend(news['images'])

        # 3. 生成播报稿
        report_text = await self.summary_service.generate_report(news_list)

        # 4. 生成TTS音频
        audio_data = await self.tts_service.generate_audio(report_text)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 阶段1: 返回第1帧（图片 + 初始文本）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        first_frame = self._build_frame(
            frame_id=0,
            frame_text=report_text[0] if report_text else "",
            images=image_urls,  # ⭐ 所有图片
            is_final=False
        )
        yield first_frame

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 阶段2: 流式返回文本（逐字）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        content = ""
        for i, char in enumerate(report_text[1:], start=1):
            content += char

            text_frame = self._build_frame(
                frame_id=i,
                frame_text=content,
                images=None,  # ⭐ 不再包含图片
                is_final=False
            )
            yield text_frame
            await asyncio.sleep(0.02)  # 控制发送频率

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 阶段3: 返回最终帧（音频）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        final_frame = self._build_frame(
            frame_id=len(report_text),
            frame_text="",
            images=None,
            audio=audio_data,  # ⭐ 完整音频
            complete_content=report_text,
            is_final=True
        )
        yield final_frame

    def _build_frame(
        self,
        frame_id: int,
        frame_text: str,
        images: Optional[List[str]] = None,
        audio: Optional[str] = None,
        complete_content: Optional[str] = None,
        is_final: bool = False
    ) -> str:
        """构建单帧响应（SSE格式）"""

        frame_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text=frame_text,
            frame_is_final=is_final,
            complete_content=complete_content
        )

        # 添加图片（仅第1帧）
        if images:
            frame_parts = [
                FramePart(
                    type="image",
                    image=FramePartImage(
                        format="url",
                        data=url
                    )
                )
                for url in images
            ]
            frame_data.frame_parts = frame_parts

        # 添加音频（仅最终帧）
        elif audio:
            frame_parts = [
                FramePart(
                    type="audio",
                    audio=FramePartAudio(
                        format="wav",
                        data=f"data:;base64,{audio}",
                        is_final=True
                    )
                )
            ]
            frame_data.frame_parts = frame_parts

        # 构建完整响应
        response = BaseResponse(
            version=request.version,
            request_id=request.request_id,
            code=0,
            message="success",
            data=frame_data
        )

        return f"event:data\ndata:{response.json()}\n\n"
```

---

## 五、完整流程图

```
┌─────────────────────────────────────────────────────────────┐
│                    用户查询："今天科技新闻"                   │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              阶段1: 快速意图分类（规则匹配）                  │
│  - 检测关键词："今天" → target_date=2025-01-09             │
│  - 检测分类："科技" → category="科技"                       │
│  - 判断：use_cache=true                                     │
│  - 耗时：<1ms                                               │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              阶段2: 智能缓存查询                              │
│  ① 查内存缓存：NewsCache.get_today_news("科技")             │
│     └─ 未命中                                                │
│  ② 查数据库：NewsDatabase.get_today_news("科技")            │
│     └─ 命中！返回15条新闻                                    │
│  ③ 更新内存缓存：NewsCache.set_today_news(...)              │
│  - 耗时：~10ms                                              │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              阶段3: 数据准备                                  │
│  ① 提取图片：从15条新闻中提取32张图片URL                     │
│  ② 生成摘要：直接使用缓存的ai_summary                        │
│  ③ 生成播报稿：直接使用缓存的report_text                     │
│  - 耗时：~50ms（因为已缓存）                                 │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              阶段4: TTS音频生成                               │
│  - 调用TTS服务生成音频                                        │
│  - 耗时：~1-2s（异步处理）                                   │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              阶段5: 流式响应返回                              │
│  Frame 0: [图片32张] + "各"                                  │
│  Frame 1-N: 逐字文本流...                                    │
│  Frame Final: [完整音频]                                     │
│  - 总耗时：~1-2s（主要是TTS时间）                            │
└─────────────────────────────────────────────────────────────┘

对比传统方案：
┌─────────────────────────────────────────────────────────────┐
│ 传统方案（无缓存优化）                                        │
│  ① LLM意图分析：~500ms                                      │
│  ② 在线抓取新闻：~2-5s                                      │
│  ③ LLM生成摘要：~1-2s                                       │
│  ④ LLM生成播报稿：~1-2s                                     │
│  ⑤ TTS音频生成：~1-2s                                       │
│  总耗时：~5-11s                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 六、LangGraph工作流简化设计

基于轻量级原则，LangGraph可以更简化：

### 6.1 简化的State定义

```python
from typing import TypedDict, List, Optional

class SimpleNewsState(TypedDict):
    """简化的工作流状态"""
    # 输入
    query: str

    # 意图分析结果
    intent: QueryIntent
    category: Optional[str]

    # 新闻数据
    news_list: List[Dict]

    # 响应数据
    report_text: str
    image_urls: List[str]
    audio_data: str
```

### 6.2 简化的工作流图

```
     ┌──────────────┐
     │   Start      │
     └──────┬───────┘
            │
            ▼
     ┌──────────────┐
     │ Intent Check │  (快速规则匹配)
     └──────┬───────┘
            │
       ┌────┴────┐
       │         │
    Cache?     Need Fetch?
       │         │
       ▼         ▼
  ┌─────────┐  ┌────────────┐
  │Return   │  │Fetch News  │
  │Cached   │  │Online      │
  └─────────┘  └─────┬──────┘
                     │
                     ▼
              ┌────────────┐
              │Summary &   │
              │TTS Generate│
              └─────┬──────┘
                    │
                    ▼
              ┌────────────┐
              │  End       │
              └────────────┘
```

### 6.3 是否需要LangGraph？

**分析**：

| 方案 | 适用场景 | 复杂度 | 推荐度 |
|------|----------|--------|--------|
| **简单函数链** | 流程线性、分支少 | ⭐ | ⭐⭐⭐⭐⭐ |
| **LangGraph** | 复杂状态管理、多分支 | ⭐⭐⭐ | ⭐⭐⭐ |

**结论**：对于这个项目，**先用简单函数链，未来需要时再引入LangGraph**

```python
# 简化的实现（无LangGraph）
class NewsAgentPipeline:
    """新闻Agent处理流水线（简单版本）"""

    async def process_query(self, query: str) -> Dict:
        """处理查询"""

        # 1. 意图分析
        intent_result = self.fast_classifier.classify(query)

        # 2. 获取新闻（智能路由）
        news_list, from_cache = await self.router.route_query(
            query,
            intent_result
        )

        # 3. 生成播报稿
        report_text = await self.summary_service.generate_report(
            news_list
        )

        # 4. 生成音频
        audio_data = await self.tts_service.generate_audio(
            report_text
        )

        # 5. 返回结果
        return {
            "news_list": news_list,
            "report_text": report_text,
            "audio_data": audio_data,
            "from_cache": from_cache
        }
```

---

## 七、依赖优化

### 7.1 最小化依赖

```txt
# 核心依赖
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic>=2.0.0

# HTTP客户端（异步）
httpx>=0.25.0

# HTML解析（新闻抓取）
beautifulsoup4>=4.12.0
lxml>=4.9.0
feedparser>=6.0.10

# 工具库
python-dateutil>=2.8.2
python-multipart==0.0.6

# 配置管理
pyyaml>=6.0

# 可选：定时任务
apscheduler>=3.10.0

# 可选：LangGraph（按需引入）
# langgraph>=0.0.20
# langchain>=0.1.0
```

**对比原方案**：
- ❌ 移除：SQLAlchemy（ORM）
- ❌ 移除：OpenAI SDK（直接用httpx）
- ✅ 保留：FastAPI核心
- ✅ 新增：BeautifulSoup（图片提取）

---

## 八、性能对比

### 8.1 响应时间对比

| 场景 | 原方案（全流程） | 优化方案（缓存） | 提升 |
|------|-----------------|-----------------|------|
| **今天通用新闻** | ~5-11s | ~100-200ms | **50x** |
| **今天分类新闻** | ~5-11s | ~200-300ms | **30x** |
| **指定日期新闻** | ~5-11s | ~3-5s | **2x** |
| **关键词搜索** | ~5-11s | ~1-3s | **3x** |

### 8.2 成本对比

| 场景 | 原方案 | 优化方案 | 节省 |
|------|--------|---------|------|
| **今天新闻** | LLM×3 | 0 | **100%** |
| **分类新闻** | LLM×3 | 0 | **100%** |
| **指定日期** | LLM×3 | LLM×1 | **66%** |
| **关键词搜索** | LLM×3 | LLM×1 | **66%** |

---

## 九、总结

### 9.1 核心优化点

1. **✅ 零ORM依赖**：SQLite + 原生SQL，轻量快速
2. **✅ 智能缓存**：今天新闻秒级响应
3. **✅ 两阶段意图识别**：快速规则 + LLM深度分析
4. **✅ 优化流式响应**：首帧包含所有图片
5. **✅ 按需使用LangGraph**：简单场景无需复杂框架

### 9.2 架构优势

- **轻量**：最小依赖，易于部署
- **快速**：缓存优先，响应时间降低50x
- **灵活**：支持今天/指定日期/关键词搜索
- **可扩展**：按需引入LangGraph等高级特性

### 9.3 开发优先级

**P0（必须）**：
1. 轻量级数据库层
2. 快速意图分类器
3. 智能路由服务
4. 优化的流式响应

**P1（重要）**：
5. 新闻图片提取
6. 定时任务（每天8点抓取）
7. LLM深度分析（复杂查询）

**P2（可选）**：
8. LangGraph集成（如需要）
9. Redis缓存（分布式部署）
10. 监控和日志

---

**文档版本**: v2.0
**更新日期**: 2025-01-09
**主要变化**: 轻量化设计 + 智能缓存优化 + 流式响应优化
