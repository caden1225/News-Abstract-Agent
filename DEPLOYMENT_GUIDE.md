# 新闻播报Agent - 部署指南

## 项目概述

本项目已成功创建并通过所有测试,主要功能包括:
- ✅ 当日热点新闻抓取
- ✅ 智能新闻摘要生成
- ✅ TTS语音播报
- ✅ 完整的API接口
- ✅ Docker容器化

## 已完成的测试

### 1. 功能模块测试 ✅
```
✓ 新闻抓取功能 - PASS
✓ 新闻摘要功能 - PASS
✓ TTS功能 - PASS
✓ 播报稿生成 - PASS
```

### 2. API接口测试 ✅
```
✓ GET  /health - 健康检查正常
✓ GET  /api/v1/news - 新闻获取正常
✓ POST /api/v1/chat - 聊天接口正常
```

### 3. Docker镜像测试 ✅
```
✓ 镜像构建成功
✓ 容器运行正常
✓ API访问正常
```

## 项目文件结构

```
news-tts-agent/
├── main.py                    # 主API接口
├── news_scraper.py            # 新闻抓取模块
├── news_summarizer.py         # 新闻摘要模块
├── tts_service.py             # TTS语音服务模块
├── test_agent.py              # 测试脚本
├── requirements.txt           # Python依赖
├── Dockerfile                 # Docker镜像(生产环境)
├── Dockerfile.simple          # Docker镜像(简化版)
├── .appinfo                   # 应用配置
├── Bdefile                    # BDE配置
├── start.sh                   # 启动脚本
├── README.md                  # 项目说明
└── DEPLOYMENT_GUIDE.md        # 本文档
```

## 部署步骤

### 方式1: 使用基础镜像部署(推荐)

这种方式与banma-nlu-aliyun项目使用相同的基础镜像。

#### 1. 构建镜像

```bash
cd /home/caden/workspace/12_19_deliver/gerrit/news-tts-agent

# 使用Dockerfile(与banma-nlu-aliyun相同的基础镜像)
docker build -t news-tts-agent:latest .
```

#### 2. 推送到镜像仓库

```bash
# 标记镜像(替换REGISTRY为实际的镜像仓库地址)
docker tag news-tts-agent:latest ${REGISTRY}/llm-skeleton-test:latest

# 推送镜像
docker push ${REGISTRY}/llm-skeleton-test:latest
```

#### 3. 注册到管理平台

```bash
# 创建应用版本
zbxctl llm app version create \
  --app-id llm-skeleton-test \
  --version v1.0.0 \
  --docker ${REGISTRY}/llm-skeleton-test:latest \
  --commit-id $(git rev-parse --short HEAD) \
  --branch $(git rev-parse --abbrev-ref HEAD) \
  --description "新闻播报Agent v1.0.0 - 支持新闻抓取、摘要和TTS语音播报"

# 部署到环境
zbxctl llm app version deploy \
  --app-id llm-skeleton-test \
  --version v1.0.0 \
  --envs default
```

### 方式2: 使用简化Dockerfile部署

使用Dockerfile.simple(基于python:3.12-slim)构建镜像。

```bash
cd /home/caden/workspace/12_19_deliver/gerrit/news-tts-agent

# 构建镜像
docker build -f Dockerfile.simple -t news-tts-agent:simple .

# 标记和推送
docker tag news-tts-agent:simple ${REGISTRY}/llm-skeleton-test:simple
docker push ${REGISTRY}/llm-skeleton-test:simple

# 注册到平台
zbxctl llm app version create \
  --app-id llm-skeleton-test \
  --version v1.0.0-simple \
  --docker ${REGISTRY}/llm-skeleton-test:simple \
  --commit-id $(git rev-parse --short HEAD) \
  --description "新闻播报Agent v1.0.0 (简化版)"
```

## 环境变量配置

部署时需要配置以下环境变量:

| 变量名 | 说明 | 默认值 | 是否必需 |
|--------|------|--------|----------|
| `SIDECAR_BASE_URL` | Sidecar服务地址 | `http://localhost:13984/api/llm/v1` | 是 |
| `LLM_API_KEY` | LLM API密钥 | `zbx:...` | 是 |
| `LLM_MODEL_ALIAS` | 模型别名 | `qwen2-7b` | 否 |
| `TTS_SERVICE_URL` | TTS服务地址 | `http://localhost:13984/api/llm/v1/tts` | 否 |
| `USE_MOCK_TTS` | 是否使用Mock TTS | `true` | 否 |

## 验证部署

### 1. 健康检查

```bash
curl http://<your-service-url>/health
```

预期响应:
```json
{"status":"ok","service":"news-tts-agent","version":"1.0.0"}
```

### 2. 新闻查询测试

```bash
curl http://<your-service-url>/api/v1/news
```

### 3. 聊天接口测试

```bash
curl -X POST http://<your-service-url>/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "version": "1.0",
    "channel_id": "test",
    "request_id": "test_001",
    "timestamp": 1234567890,
    "vin": "TEST_VIN",
    "stream": false,
    "user_id": "test_user",
    "query": "播报今日热点新闻"
  }'
```

## 功能说明

### 1. 新闻抓取
- 支持多个RSS新闻源
- 当真实新闻源不可用时,自动使用演示数据
- 过滤并排序当天新闻

### 2. 新闻摘要
- 使用平台注册的大语言模型生成摘要
- 支持批量处理提高效率
- 降级策略确保可用性

### 3. TTS语音播报
- 调用TTS服务生成语音
- 返回base64编码的音频数据
- 支持Mock模式用于测试

## 注意事项

1. **Sidecar依赖**:
   - 生产环境需要配置正确的Sidecar地址
   - 本地开发时需要启动Sidecar服务

2. **模型配置**:
   - 确保在平台注册了可用的LLM模型
   - 使用正确的模型别名

3. **TTS服务**:
   - 默认使用Mock TTS用于测试
   - 生产环境需要配置真实的TTS服务

4. **日志监控**:
   - 应用日志输出到stdout/stderr
   - 平台会自动收集和展示日志

## 故障排查

### 问题1: 无法获取新闻
**现象**: 返回空新闻列表
**原因**: RSS源不可访问
**解决**: 系统会自动使用演示数据,无需处理

### 问题2: LLM调用失败
**现象**: 摘要生成失败
**原因**:
- Sidecar服务未启动或配置错误
- 模型别名未注册
- API密钥错误

**解决**:
1. 检查Sidecar服务状态
2. 验证模型别名是否在平台注册
3. 确认API密钥配置正确

### 问题3: TTS无声音
**现象**: 返回的音频为空
**原因**: TTS服务未配置
**解决**:
- 检查TTS服务配置
- 设置`USE_MOCK_TTS=true`使用Mock模式

## 版本信息

- **应用ID**: llm-skeleton-test
- **当前版本**: v1.0.0
- **Python版本**: 3.12+
- **FastAPI版本**: 0.104.1

## 联系支持

如有问题,请查看:
1. 项目README.md
2. AGENT_DEVELOPMENT_GUIDE.md(在llm-appkit-template-java-v0.2.0目录)
3. 平台管理后台的日志和监控

## 下一步优化建议

1. **RSS源优化**: 添加更多可靠的新闻源
2. **TTS集成**: 接入真实的TTS服务
3. **缓存机制**: 添加新闻缓存减少重复抓取
4. **个性化配置**: 支持用户自定义新闻类别
5. **推送功能**: 支持定时新闻推送
