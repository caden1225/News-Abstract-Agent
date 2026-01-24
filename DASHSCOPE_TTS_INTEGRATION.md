# DashScope TTS 集成说明

## 概述

已成功将阿里云 DashScope TTS（通义千问 TTS API）集成到项目中，支持通过环境变量或配置文件切换使用。

## 配置方式

### 方式1：环境变量（推荐）

在 `.env` 文件中添加以下配置：

```bash
# 选择 TTS 服务类型
TTS_SERVICE_TYPE=dashscope

# DashScope API Key（必需）
DASHSCOPE_API_KEY=sk-your-api-key-here

# 可选配置
DASHSCOPE_MODEL=qwen3-tts-flash
DASHSCOPE_VOICE=Cherry
DASHSCOPE_LANGUAGE_TYPE=Chinese
DASHSCOPE_API_URL=https://dashscope.aliyuncs.com/api/v1
DASHSCOPE_SAMPLE_RATE=24000
```

### 方式2：配置文件

在 `config/config.yaml` 中配置：

```yaml
tts:
  service_type: dashscope  # 或 cosyvoice2, mock
  dashscope:
    api_key: ${DASHSCOPE_API_KEY:}
    model: qwen3-tts-flash
    voice: Cherry
    language_type: Chinese
    api_url: https://dashscope.aliyuncs.com/api/v1
    sample_rate: 24000
```

## 切换服务

通过设置 `TTS_SERVICE_TYPE` 环境变量或配置文件中的 `tts.service_type` 来切换：

- `dashscope`: 使用 DashScope TTS API
- `cosyvoice2`: 使用本地 CosyVoice2 模型（默认）
- `mock`: 使用 Mock TTS 服务（测试用）

## 安装依赖

确保已安装 DashScope SDK：

```bash
pip install dashscope
```

SDK 版本要求：>= 1.24.6

## 支持的音色

预定义的音色列表（可通过 `list_speakers()` 查看）：
- Cherry
- Alice
- Bob
- Diana
- Echo
- Frank
- Grace
- Henry

## 特性

1. **流式支持**: DashScope API 支持流式返回，已集成到服务中
2. **语言参数透传**: 支持从 orchestrator 传递语言参数（zh, en, ko 等），自动映射到 DashScope 的 language_type
3. **配置灵活**: 支持环境变量和配置文件两种方式
4. **单例模式**: 服务使用单例模式，避免重复初始化
5. **无回退机制**: 如果 DashScope 初始化失败，会直接抛出异常，不会回退到其他服务

## 使用示例

服务会自动根据配置选择，无需修改代码。在 `main.py` 中：

```python
from tts_utils import get_tts_service, initialize_tts

# 获取服务（根据配置自动选择）
tts_service = get_tts_service()

# 初始化
await initialize_tts()

# 使用（语言参数会自动从 orchestrator 传递）
audio_data = await tts_service.synthesize(
    text="你好，世界", 
    spk_id=None,
    language="zh"  # 可选，如果不提供则使用配置的默认值
)
```

## 语言参数映射

DashScope 服务会自动将语言代码映射到 DashScope 的 `language_type`：

- `zh` → `Chinese`
- `en` → `English`
- `ko` → `Korean`
- `ja` → `Japanese`
- 其他语言代码默认映射为 `Chinese`

语言参数会从 orchestrator 的 `tts_language` 自动传递到 TTS 服务。

## 注意事项

1. **API Key**: 必须配置 `DASHSCOPE_API_KEY`，否则服务无法启动
2. **地域**: 如果使用新加坡地域，需要修改 `api_url` 为 `https://dashscope-intl.aliyuncs.com/api/v1`
3. **采样率**: DashScope 默认采样率为 24000Hz，与 CosyVoice2 的 22050Hz 不同
4. **成本**: DashScope 是付费 API 服务，请注意使用成本

## 故障排查

如果遇到问题：

1. 检查 API Key 是否正确配置
2. 确认已安装 `dashscope` 包
3. 查看日志中的错误信息
4. 确认网络连接正常（需要访问阿里云 API）
