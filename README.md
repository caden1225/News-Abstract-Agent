# 新闻播报Agent (News TTS Agent)

## 功能概述

这是一个基于Python的新闻播报Agent应用,主要功能包括:

1. **新闻抓取**: 自动抓取当日热点新闻
2. **智能摘要**: 使用大语言模型生成新闻摘要
3. **语音播报**: 调用TTS服务生成语音播报

## 项目结构

```
news-tts-agent/
├── main.py                 # 主API接口
├── news_scraper.py         # 新闻抓取模块
├── news_summarizer.py      # 新闻摘要模块
├── tts_service.py          # TTS语音服务模块
├── requirements.txt        # Python依赖
├── Dockerfile             # Docker镜像构建文件
├── .appinfo               # 应用配置
├── Bdefile                # BDE配置
└── README.md              # 本文档
```

## 技术栈

- **框架**: FastAPI + Uvicorn
- **LLM调用**: OpenAI兼容API (通过Sidecar)
- **新闻源**: RSS feeds
- **容器化**: Docker

## 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `SIDECAR_BASE_URL` | Sidecar服务地址 | `http://localhost:13984/api/llm/v1` |
| `LLM_API_KEY` | LLM API密钥 | `zbx:...` |
| `LLM_MODEL_ALIAS` | 模型别名 | `qwen2-7b` |
| `TTS_SERVICE_URL` | TTS服务地址 | `http://localhost:13984/api/llm/v1/tts` |
| `USE_MOCK_TTS` | 是否使用Mock TTS | `true` |

## 本地开发

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件:

```bash
SIDECAR_BASE_URL=http://localhost:13984/api/llm/v1
LLM_API_KEY=your-api-key
LLM_MODEL_ALIAS=qwen2-7b
USE_MOCK_TTS=true
```

### 3. 启动应用

```bash
python main.py
```

应用将在 `http://localhost:8080` 启动

### 4. 测试API

#### 健康检查
```bash
curl http://localhost:8080/health
```

#### 获取新闻
```bash
curl http://localhost:8080/api/v1/news
```

#### 聊天接口(流式)
```bash
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "version": "1.0",
    "channel_id": "local_test",
    "request_id": "test_001",
    "timestamp": 1234567890,
    "vin": "VIN4LOCALTEST",
    "stream": true,
    "user_id": "test_user",
    "query": "播报今日热点新闻"
  }'
```

## Docker构建

### 构建镜像

```bash
docker build -t news-tts-agent:latest .
```

### 运行容器

```bash
docker run -d \
  -p 8080:8080 \
  -e SIDECAR_BASE_URL=http://host.docker.internal:13984/api/llm/v1 \
  -e USE_MOCK_TTS=true \
  news-tts-agent:latest
```

## 部署到管理平台

### 1. 推送镜像

```bash
# 标记镜像
docker tag news-tts-agent:latest ${REGISTRY}/llm-skeleton-test:latest

# 推送镜像
docker push ${REGISTRY}/llm-skeleton-test:latest
```

### 2. 注册应用

```bash
# 创建版本
zbxctl llm app version create \
  --app-id llm-skeleton-test \
  --version v1.0.0 \
  --docker ${REGISTRY}/llm-skeleton-test:latest \
  --commit-id $(git rev-parse --short HEAD) \
  --branch $(git rev-parse --abbrev-ref HEAD) \
  --description "新闻播报Agent v1.0.0"

# 部署到开发环境
zbxctl llm app version deploy \
  --app-id llm-skeleton-test \
  --version v1.0.0 \
  --envs default
```

## API规范

### POST /api/v1/chat

聊天接口,与Java脚手架API完全兼容

**请求格式**:
```json
{
  "version": "1.0",
  "channel_id": "string",
  "request_id": "string",
  "timestamp": 1234567890,
  "vin": "string",
  "stream": true,
  "user_id": "string",
  "query": "播报今日热点新闻",
  "conversation_id": "string (可选)",
  "context": {} (可选)
}
```

**响应格式** (Server-Sent Events):
```json
{
  "code": 0,
  "message": "Success",
  "data": {
    "request_id": "string",
    "user_id": "string",
    "vin": "string",
    "frame_id": 0,
    "frame_text": "文本内容",
    "frame_timestamp": 1234567890,
    "frame_is_final": false,
    "frame_voice": {
      "audio": "base64编码的音频数据",
      "format": "mp3"
    }
  }
}
```

## 功能说明

### 1. 新闻抓取
- 支持多个RSS新闻源
- 自动过滤当天新闻
- 去重和排序

### 2. 智能摘要
- 使用大语言模型生成简洁摘要
- 批量处理提高效率
- 降级策略保证可用性

### 3. 语音播报
- 调用TTS服务生成语音
- 支持多种音色
- 返回base64编码的音频数据

## 注意事项

1. **Sidecar依赖**: 本地开发时需要启动Sidecar服务
2. **Mock模式**: 默认使用Mock TTS用于测试
3. **日志级别**: 可通过环境变量调整
4. **性能优化**: 批量处理新闻摘要

## 故障排查

### 问题1: 无法获取新闻
- 检查网络连接
- 确认RSS源地址可访问

### 问题2: LLM调用失败
- 检查Sidecar服务状态
- 确认API密钥正确
- 查看模型别名是否注册

### 问题3: TTS无声音
- 检查TTS服务配置
- 确认音频数据格式
- 尝试关闭Mock模式

## 更新日志

### v1.0.0 (2025-01-06)
- 初始版本发布
- 实现新闻抓取功能
- 实现智能摘要功能
- 实现TTS语音播报功能
- 完成API接口开发
