"""
工作流状态模型
LangGraph 工作流状态定义
"""
from typing import TypedDict, List, Dict, Optional, Annotated, Any
import operator


class NewsAgentState(TypedDict):
    """新闻Agent工作流状态"""

    # ==================== 输入 ====================
    query: str                              # 用户查询
    request_id: str                         # 请求ID
    stream: bool                            # 是否流式

    # ==================== 意图分析结果 (LLM提取) ====================
    query_type: str                         # 查询类型: daily_news / category_news / keyword_search / general_news
    target_date: Optional[str]              # 目标日期 (YYYY-MM-DD)
    category: Optional[str]                 # 新闻分类: hot_news / today_focus / null
    search_keywords: List[str]              # 搜索关键词列表 (最多3个)
    search_strategy: str                     # 检索策略: by_date_and_category / by_date_only / by_keyword / by_all

    # ==================== 兼容字段 (保留以兼容旧代码) ====================
    intent_type: str                        # 兼容字段，映射到 query_type
    keywords: List[str]                     # 兼容字段，映射到 search_keywords

    # ==================== 数据源决策 ====================
    data_source: str                        # cache / fetch / hybrid
    cache_hit: bool                         # 是否命中缓存

    # ==================== 新闻数据 ====================
    news_list: List[Dict]                   # 获取的新闻列表
    news_count: int                         # 新闻数量
    selected_news: List[Dict]               # 选中的新闻（用于摘要）

    # ==================== 处理结果 ====================
    summary: str                            # 新闻播报稿
    audio_data: Optional[str]               # TTS音频数据
    
    # ==================== 并行生成状态 ====================
    text_ready: bool                        # 文本生成是否完成
    audio_ready: bool                       # 音频生成是否完成
    streaming_text: str                     # 流式文本内容（逐步累积）
    streaming_audio_chunks: List[str]       # 流式音频块（base64编码）

    # ==================== 处理过程（流式返回） ====================
    processing_steps: Annotated[List[str], operator.add]  # 处理步骤列表（累加）
    current_step: str                       # 当前处理步骤描述
    progress_percentage: int                # 进度百分比 (0-100)

    # ==================== 多模态数据 ====================
    image_links: List[str]                  # 图片链接列表

    # ==================== 思维链 ====================
    thinking_chain: Annotated[List[Dict[str, Any]], operator.add]  # 思维链步骤列表（累加）

    # ==================== TTS语言配置 ====================
    tts_language: str                       # TTS语言: "zh" (中文) / "en" (英文) / "ko" (韩语)
    language_confidence: float              # 语言判断置信度 (0.0-1.0)
    
    # ==================== LLM语言判断任务状态 ====================
    llm_language_pending: bool              # LLM语言判断是否还在执行中
    llm_language_ready: bool                 # LLM语言判断是否已完成

    # ==================== 控制字段 ====================
    error: Optional[str]                    # 错误信息
    completed: bool                        # 是否完成

