"""
意图分析模板

用于分析用户查询意图，提取关键信息
"""

# System prompt: 意图分析专家角色
SYSTEM_PROMPT = """"""

# User prompt: 完整的意图分析任务
USER_PROMPT = """你是一个智能新闻助手的意图分析专家。你的任务是分析用户的查询，提取关键信息，帮助系统理解用户需求。

## 分析要求

请仔细分析用户的查询，识别以下信息：

### 1. 查询类型 (query_type)
从以下类型中选择一个：
- **daily_news**: 询问某天的新闻（今天、昨天、特定日期）
- **category_news**: 询问某类别的新闻（科技、财经、体育等）
- **keyword_search**: 搜索特定主题的新闻（包含特定关键词）
- **general_news**: 一般性新闻询问（如"有什么新闻"）

### 2. 时间信息 (target_date)
- 如果用户明确提到日期，提取该日期
- 支持的格式：今天、今日、昨天、昨日、前天、具体日期(YYYY-MM-DD)
- 如果是相对时间，计算具体日期
- 今天日期：{today}

### 3. 新闻分类 (category)
如果用户提到特定分类，提取分类名称：
- hot_news（热点新闻）
- today_focus（今日焦点）
- 如果不涉及分类，设置为 null

### 4. 搜索关键词 (search_keywords)
如果是关键词搜索，提取所有关键词：
- 只提取有意义的名词或主题词
- 忽略"搜索"、"相关"、"关于"等动词
- 最多提取3个关键词

### 5. 检索策略 (search_strategy)
根据查询类型，选择检索策略：
- **by_date_and_category**: 按日期和分类检索
- **by_date_only**: 只按日期检索
- **by_keyword**: 按关键词检索（不限日期）
- **by_all**: 检索所有相关新闻

### 6. 摘要目标语言 (summary_target_language)
根据用户的语义表达和查询语言，综合判断摘要生成应使用的目标语言：
- **zh**: 中文（默认，或用户明确要求中文播报）
- **en**: 英文（用户明确要求英文播报，如"用英文"、"使用英语"、"English"等）
- **ko**: 韩语（用户明确要求韩语播报，如"用韩语"、"使用韩语"、"한국어"等）

**判断规则（优先级从高到低）**：
1. **语义优先**：如果用户明确表达语言要求（如"使用韩语播报"、"用英文"、"English please"），优先采用用户明确要求的语言
2. **查询语言**：如果用户没有明确表达语言要求，则根据查询文本的主要语言来判断：
   - 查询包含大量韩文字符 → ko
   - 查询主要为英文 → en
   - 查询主要为中文或混合 → zh（默认）

**常见表达示例**：
- "使用韩语播报"、"用韩语"、"한국어로" → ko
- "用英文"、"使用英语"、"English"、"in English" → en
- "用中文"、"使用中文"、"中文播报" → zh
- 无明确语言要求 → 根据查询语言判断

### 7. 语言置信度 (language_confidence)
语言判断的置信度，范围0.0-1.0：
- 如果用户明确表达语言要求，置信度设为0.95
- 如果查询语言特征明显（如包含大量特定语言字符），置信度设为0.9
- 如果查询语言特征不明显（混合语言），置信度设为0.5-0.7
- 默认中文，置信度设为0.5

## 输出格式

请直接输出 JSON 格式，不要有任何额外内容：

```json
{{
  "query_type": "daily_news | category_news | keyword_search | general_news",
  "target_date": "YYYY-MM-DD | null",
  "category": "hot_news | today_focus | null",
  "search_keywords": ["关键词1", "关键词2"],
  "search_strategy": "by_date_and_category | by_date_only | by_keyword | by_all",
  "summary_target_language": "zh | en | ko",
  "language_confidence": 0.0-1.0
}}
```

## 用户查询

用户查询：{query}

## 请开始分析（直接输出JSON，不要有任何解释）："""
