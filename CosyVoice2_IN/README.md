# CosyVoice2 模块化版本

CosyVoice2的模块化封装,支持作为Python包导入使用,并新增**流式文本分块推理功能**。

## 📦 项目特性

### 核心功能

- ✅ **模块化封装**: 可作为Python包 `import cosyvoice` 使用
- ✅ **Zero-shot语音克隆**: 使用参考音频合成目标说话人声音
- ✅ **预置音色合成**: 使用预训练的多种音色
- ✅ **跨语言合成**: 支持中英文等多语言
- ✅ **流式推理**: 支持流式和非流式两种输出模式
- ✅ **流式分块推理**: 新增功能,支持文本分块输入并保持语义连贯性

### 新增功能: 流式文本分块推理

支持将长文本分块处理,同时保持跨chunk的语义、韵律和音色连贯性。

**核心优势**:
- 🔄 **语义连贯**: 跨chunk保持完整上下文
- 🎵 **韵律自然**: 平滑的语调和节奏过渡
- 🎤 **音色一致**: 全程保持稳定音色
- ⚡ **延迟优化**: 支持可调的chunk大小,实现低延迟输出

## 🚀 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 基础使用

#### 1. 预置音色合成

```python
from cosyvoice.cli.cosyvoice import CosyVoice2

# 初始化模型
model = CosyVoice2('/path/to/CosyVoice2-0.5B')

# 合成语音
for result in model.inference_sft(
    tts_text="今天天气很好",
    spk_id="girl_zh",
    stream=False
):
    audio = result['tts_speech']
    # 保存或播放音频...
```

#### 2. Zero-shot语音克隆

```python
from cosyvoice.utils.file_utils import load_wav

# 加载参考音频
prompt_speech = load_wav('reference.wav', 16000)

# 克隆声音合成
for result in model.inference_zero_shot(
    tts_text="这是要合成的文本",
    prompt_text="参考音频的文本",
    prompt_speech_16k=prompt_speech,
    stream=False
):
    audio = result['tts_speech']
```

#### 3. 流式文本分块推理 (新功能)

```python
# 准备文本chunks
text_chunks = ["今天天气很好", "适合出去散步", "呼吸新鲜空气"]

# 分块推理,保持连贯性
for result in model.inference_sft_chunked(
    text_chunks=text_chunks,
    spk_id="girl_zh",
    stream=True,
    token_hop_len=15,  # 控制输出chunk大小
    mel_cache_len=6    # 控制边界平滑度
):
    audio = result['tts_speech']
    # 实时处理音频...
```

## 📖 API文档

### CosyVoice2 类

#### 初始化

```python
CosyVoice2(
    model_dir: str,              # 模型路径
    load_jit: bool = False,      # 是否加载JIT优化模型
    load_trt: bool = False,      # 是否加载TensorRT优化
    load_vllm: bool = False,     # 是否加载vLLM加速
    fp16: bool = False           # 是否使用FP16精度
)
```

#### 方法列表

##### `inference_sft()`
使用预置音色合成语音

```python
inference_sft(
    tts_text: str,               # 要合成的文本
    spk_id: str,                 # 说话人ID (如 "girl_zh", "man_zh")
    stream: bool = False,        # 是否流式输出
    speed: float = 1.0,          # 语速倍数
    text_frontend: bool = True   # 是否进行文本归一化
) -> Generator[dict, None, None]
```

**可用说话人ID**: 使用 `model.list_available_spks()` 查看

##### `inference_zero_shot()`
Zero-shot语音克隆

```python
inference_zero_shot(
    tts_text: str,                    # 要合成的文本
    prompt_text: str,                 # 参考音频的文本
    prompt_speech_16k: torch.Tensor,  # 参考音频 (16kHz)
    zero_shot_spk_id: str = '',       # 可选的零样本ID
    stream: bool = False,
    speed: float = 1.0
) -> Generator[dict, None, None]
```

##### `inference_cross_lingual()`
跨语言合成

```python
inference_cross_lingual(
    tts_text: str,                    # 要合成的文本
    prompt_speech_16k: torch.Tensor,  # 参考音频
    stream: bool = False
) -> Generator[dict, None, None]
```

##### `inference_sft_chunked()` (新增)
流式文本分块推理

```python
inference_sft_chunked(
    text_chunks: List[str] | Generator[str],  # 文本块列表或生成器
    spk_id: str,                              # 说话人ID
    stream: bool = False,                     # 是否流式输出音频
    speed: float = 1.0,                       # 语速倍数
    text_frontend: bool = True,               # 文本归一化
    token_hop_len: int = None,                # 输出chunk大小 (可选)
    mel_cache_len: int = None                 # 边界平滑缓存 (可选)
) -> Generator[dict, None, None]
```

**参数说明**:
- `text_chunks`: 文本块列表,每个块会被独立归一化但作为连续流处理
- `token_hop_len`: 控制流式输出时每次yield的音频大小
  - 越小 → 延迟越低,但yield次数越多
  - 越大 → 单次输出更长,延迟略高但更流畅
  - 默认: 25 (约1秒音频)
- `mel_cache_len`: 控制chunk边界的平滑过渡
  - 越大 → 过渡越平滑
  - 默认: 8

**返回值**:
生成器,每次yield一个字典 `{'tts_speech': torch.Tensor}`

## 🎛️ 性能优化

### Chunk参数配置说明

#### 参数位置

流式分块推理的chunk大小由以下两个参数控制:

1. **输入层面 - 文本chunk大小** (用户控制)
   - **位置**: `inference_sft_chunked()` 的 `text_chunks` 参数
   - **作用**: 控制输入文本的分块方式
   - **配置方式**:
   ```python
   # 方式1: 手动分块
   text_chunks = ["第一段文本", "第二段文本", "第三段文本"]

   # 方式2: 按字符长度自动分块
   long_text = "很长的文本内容..."
   chunk_size = 20  # 每块20个字符
   text_chunks = [long_text[i:i+chunk_size] for i in range(0, len(long_text), chunk_size)]

   # 方式3: 使用生成器 (实时流)
   def text_stream():
       for sentence in sentences:
           yield sentence
   text_chunks = text_stream()
   ```

2. **输出层面 - 音频chunk大小** (模型控制)
   - **参数名**: `token_hop_len` 和 `mel_cache_len`
   - **位置**: `inference_sft_chunked()` 方法的可选参数
   - **配置方式**:
   ```python
   # 直接在调用时指定
   for result in model.inference_sft_chunked(
       text_chunks=text_chunks,
       spk_id="girl_zh",
       stream=True,
       token_hop_len=15,   # ← 输出chunk大小
       mel_cache_len=6     # ← 边界平滑缓存
   ):
       audio = result['tts_speech']
   ```

#### 参数作用机制

```
输入文本 → [文本分块] → 文本chunks → [Token生成] → Token流 → [音频生成] → 音频chunks
           ↑用户控制                                    ↑token_hop_len控制
                                                        ↑mel_cache_len平滑
```

**双层chunk架构**:
- **第1层 (输入)**: 文本语义chunk - 由用户根据语义边界划分
- **第2层 (输出)**: 音频时序chunk - 由`token_hop_len`控制流式yield频率

#### 完整配置示例

```python
from cosyvoice.cli.cosyvoice import CosyVoice2

# 1. 初始化模型
model = CosyVoice2('/path/to/CosyVoice2-0.5B')

# 2. 配置输入chunk (用户层面)
text = "人工智能技术正在快速发展，深刻改变着我们的生活方式和工作模式。"
text_chunks = ["人工智能技术", "正在快速发展", "深刻改变着", "我们的生活方式", "和工作模式"]

# 3. 配置输出chunk参数 (模型层面)
for result in model.inference_sft_chunked(
    text_chunks=text_chunks,      # 输入chunk配置
    spk_id="girl_zh",
    stream=True,                  # 启用流式输出
    token_hop_len=15,            # 输出chunk大小: 每15个token yield一次
    mel_cache_len=6              # 边界缓存: 6帧mel用于平滑过渡
):
    audio_chunk = result['tts_speech']
    # 实时处理每个音频chunk
    play_or_stream(audio_chunk)
```

### 流式分块推理参数调优

根据实际测试,不同的`token_hop_len`和`mel_cache_len`组合适用于不同场景:

#### 推荐配置

| 场景 | token_hop_len | mel_cache_len | 首次响应 | 特点 |
|------|--------------|---------------|---------|------|
| **实时对话** | 8 | 4 | ~1.3s | 最快响应,适合语音助手 |
| **通用应用** | 15 | 6 | ~1.5s | **推荐默认配置** |
| **高质量播报** | 25 | 8 | ~1.9s | 最佳效率,适合朗读 |

#### 使用示例

```python
# 实时对话场景 (追求最低延迟)
for result in model.inference_sft_chunked(
    text_chunks=["你好", "有什么", "可以帮您"],
    spk_id="girl_zh",
    stream=True,
    token_hop_len=8,   # 超低延迟
    mel_cache_len=4
):
    play_immediately(result['tts_speech'])

# 通用场景 (推荐配置)
for result in model.inference_sft_chunked(
    text_chunks=["人工智能", "正在发展", "改变世界"],
    spk_id="girl_zh",
    stream=True,
    token_hop_len=15,  # 平衡配置
    mel_cache_len=6
):
    process_audio(result['tts_speech'])

# 新闻播报场景 (追求高质量)
for result in model.inference_sft_chunked(
    text_chunks=news_paragraphs,
    spk_id="woman_zh",
    stream=True,
    token_hop_len=25,  # 高效率
    mel_cache_len=8
):
    buffer_and_play(result['tts_speech'])
```

### 性能说明

基于系统化测试的结果:

- **token_hop_len < 8**: ❌ 不推荐,反而导致更高延迟
- **token_hop_len = 8-10**: ⚡ 最低延迟,适合实时场景
- **token_hop_len = 15**: ✅ **最佳平衡点**,推荐大多数场景使用
- **token_hop_len = 20-25**: 📈 最佳效率,适合批处理

## 💻 使用示例

### 示例1: 简单的TTS

```python
from cosyvoice.cli.cosyvoice import CosyVoice2
import soundfile as sf

# 初始化
model = CosyVoice2('/path/to/model')

# 合成
for result in model.inference_sft("今天天气真好", spk_id="girl_zh"):
    audio = result['tts_speech'].squeeze().cpu().numpy()
    sf.write('output.wav', audio, model.sample_rate)
```

### 示例2: 流式分块处理

```python
# 长文本分块
long_text = "这是一段很长的文本..."
chunks = [long_text[i:i+20] for i in range(0, len(long_text), 20)]

# 流式合成
audio_segments = []
for result in model.inference_sft_chunked(
    text_chunks=chunks,
    spk_id="girl_zh",
    stream=True,
    token_hop_len=15
):
    audio_segments.append(result['tts_speech'])

# 合并音频
import torch
full_audio = torch.cat(audio_segments, dim=1)
```

### 示例3: 实时文本流处理

```python
def text_stream():
    """模拟实时文本流"""
    texts = ["实时", "语音", "合成", "演示"]
    for text in texts:
        yield text
        time.sleep(0.1)  # 模拟延迟

# 使用Generator输入
for result in model.inference_sft_chunked(
    text_chunks=text_stream(),
    spk_id="girl_zh",
    stream=True,
    token_hop_len=8  # 低延迟配置
):
    audio = result['tts_speech']
    # 立即播放或发送
```

### 示例4: Zero-shot克隆

```python
from cosyvoice.utils.file_utils import load_wav

# 加载参考音频
prompt_wav = load_wav('reference.wav', 16000)

# 克隆声音
for result in model.inference_zero_shot(
    tts_text="使用克隆的声音说这句话",
    prompt_text="参考音频的文本内容",
    prompt_speech_16k=prompt_wav
):
    audio = result['tts_speech'].squeeze().cpu().numpy()
    sf.write('cloned.wav', audio, model.sample_rate)
```

## 🔬 技术实现细节

### Chunk模式的实现原理

#### 利用的现有模型结构

`inference_sft_chunked` 方法**零修改**核心模型代码，完全基于CosyVoice2已有的功能实现：

1. **核心机制: LLM的`inference_bistream`方法**
   - **位置**: `cosyvoice/llm/llm.py:505-602`
   - **原有功能**: 接受**Generator类型**的text输入，用于流式推理
   - **利用方式**: 将多个文本chunk的token作为连续的Generator流输入
   ```python
   # llm.py中的关键方法
   def inference_bistream(self, text: Generator, ...):
       # 接受Generator输入,逐步消费token
       for text_token in text:
           # 维护KV-cache,保持上下文连续
   ```

2. **状态管理: UUID会话机制**
   - **位置**: `cosyvoice/cli/model.py`
   - **原有功能**: 使用UUID标识一次推理会话，跨多次yield维护缓存
   - **利用方式**: 单次`inference_sft_chunked`调用生成一个UUID，所有chunk共享
   ```python
   # model.py中的UUID机制
   uuid = str(uuid4())  # 一次调用生成一个会话ID
   self.llm_cache[uuid] = {}      # LLM的KV-cache
   self.flow_cache[uuid] = {}     # Flow的mel缓存
   self.hift_cache[uuid] = {}     # HiFiGAN的音频缓存
   ```

3. **流式输出: Flow和HiFiGAN的streaming支持**
   - **Flow位置**: `cosyvoice/flow/flow.py:161` (`pre_lookahead_len=3`)
   - **HiFiGAN缓存**: `cosyvoice/cli/model.py:272-277` (mel_cache_len, speech_window)
   - **原有功能**: 支持`stream=True`参数进行增量音频生成
   - **利用方式**: 通过`token_hop_len`控制每次yield的音频长度

#### 实现流程

```
用户调用 inference_sft_chunked(text_chunks=[chunk1, chunk2, chunk3])
    ↓
生成UUID (如: "a1b2c3d4-...")  ← 会话标识
    ↓
创建 text_token_generator():
    for chunk in text_chunks:
        normalized = frontend.text_normalize(chunk)  ← 逐个归一化
        text_token = frontend._extract_text_token(normalized)
        yield token逐个                               ← Generator输出
    ↓
调用 model.tts(text=generator, uuid=uuid, ...)
    ↓
LLM.inference_bistream(text=generator):          ← 核心！接受Generator
    for token in text:                            ← 消费所有chunk的token
        维护 llm_cache[uuid]                       ← KV-cache保持连贯
        yield speech_token
    ↓
Flow.forward(speech_token, streaming=True):
    使用 flow_cache[uuid]                          ← mel缓存保持平滑
    每 token_hop_len 个token yield一次mel
    ↓
HiFiGAN.inference(mel):
    使用 hift_cache[uuid]                          ← 音频缓存淡入淡出
    使用 speech_window (hamming) 平滑边界
    yield audio_chunk
    ↓
返回给用户
```

#### 与原有`inference_sft`的区别

| 方面 | inference_sft (传统) | inference_sft_chunked (新) |
|------|---------------------|---------------------------|
| **文本输入** | 单个字符串 | 多个chunk的Generator |
| **UUID生命周期** | 每次调用新建 | 整个chunk序列共享 |
| **LLM输入类型** | `text: torch.Tensor` | `text: Generator` → 触发`inference_bistream` |
| **上下文连续性** | 单次独立 | 跨chunk保持KV-cache |
| **适用场景** | 短文本/独立句子 | 长文本/连续对话 |

### 请求区分机制

#### 如何区分同一请求的不同chunk

**答案: 不需要区分** - 这是设计的巧妙之处！

- **用户视角**: 传入`text_chunks`列表或生成器
- **模型视角**: 看到的是**连续的token流**，完全不知道chunk边界
- **实现方式**:
  ```python
  def text_token_generator():
      for chunk in text_chunks:  # 遍历所有chunk
          text_token = process(chunk)
          for i in range(text_token.shape[1]):
              yield text_token[:, i:i+1]  # 逐token yield，无边界标记
  ```

- **连贯性保证**: LLM的`inference_bistream`将所有token视为一个连续序列，自然维护上下文

#### 如何区分不同的请求

**关键机制: UUID会话管理**

1. **每次调用生成新UUID**
   ```python
   # cosyvoice.py: inference_sft_chunked
   def inference_sft_chunked(self, text_chunks, ...):
       # 每次调用这个方法时，内部会生成新UUID
       model_input = {...}
       for output in self.model.tts(**model_input):  # ← 这里生成新UUID
           yield output
   ```

2. **UUID在model.tts()中生成**
   ```python
   # model.py: tts方法
   def tts(self, text, ...):
       uuid = str(uuid4())  # ← 新请求 = 新UUID

       # 所有缓存以UUID为key
       self.llm_cache[uuid] = {}
       self.flow_cache[uuid] = {}
       self.hift_cache[uuid] = {}

       # 推理完成后清理
       del self.llm_cache[uuid]
       del self.flow_cache[uuid]
       del self.hift_cache[uuid]
   ```

3. **请求隔离示例**
   ```python
   # 请求1
   for audio in model.inference_sft_chunked(
       text_chunks=["你好", "世界"],  # UUID-1234
       spk_id="girl_zh"
   ):
       play(audio)  # 使用cache[UUID-1234]

   # 请求2 (完全独立)
   for audio in model.inference_sft_chunked(
       text_chunks=["再见", "朋友"],  # UUID-5678 (新的!)
       spk_id="girl_zh"
   ):
       play(audio)  # 使用cache[UUID-5678]，与请求1完全隔离
   ```

#### 缓存生命周期

```
调用开始                      调用结束
   ↓                            ↓
[生成UUID] → [创建缓存] → [逐chunk处理] → [清理缓存]
   uuid-A      cache[A]={}    使用cache[A]   del cache[A]

下次调用开始
   ↓
[生成UUID] → [创建缓存] → ...
   uuid-B      cache[B]={}    ← 全新的缓存，不受A影响
```

#### 并发请求支持

由于UUID机制，**天然支持并发**:

```python
import asyncio

async def process_request(text_chunks, request_id):
    # 每个请求有独立的UUID和缓存
    for audio in model.inference_sft_chunked(text_chunks, spk_id="girl_zh"):
        await send_audio(audio, request_id)

# 并发处理多个请求，互不干扰
await asyncio.gather(
    process_request(["你好", "世界"], request_id=1),  # UUID-AAA
    process_request(["早上", "好啊"], request_id=2),  # UUID-BBB
    process_request(["晚安", "朋友"], request_id=3)   # UUID-CCC
)
```

## 📁 项目结构

```
CosyVoice2_MODULE/
├── cosyvoice/              # 核心包
│   ├── cli/                # 命令行接口
│   │   ├── cosyvoice.py    # CosyVoice2主类 (新增inference_sft_chunked)
│   │   ├── model.py        # 模型封装 (UUID会话管理)
│   │   └── frontend.py     # 前端处理
│   ├── llm/                # 语言模型
│   │   └── llm.py          # Qwen2LM实现 (inference_bistream核心)
│   ├── flow/               # Flow模型
│   │   └── flow.py         # Flow matching (streaming支持)
│   ├── hifigan/            # 声码器
│   ├── transformer/        # Transformer组件
│   └── utils/              # 工具函数
├── matcha/                 # Matcha-TTS依赖
├── run.py                  # 示例脚本
├── run_chunked.py          # 分块推理示例 (新旧方法对比)
├── __init__.py             # 包初始化
└── README.md               # 本文件
```

## 🔧 高级用法

### 添加自定义零样本说话人

```python
from cosyvoice.utils.file_utils import load_wav

# 添加新的零样本说话人
model.add_zero_shot_spk(
    prompt_text="参考文本",
    prompt_speech_16k=load_wav('reference.wav', 16000),
    zero_shot_spk_id="custom_speaker"
)

# 保存说话人信息
model.save_spkinfo()

# 使用自定义说话人
for result in model.inference_zero_shot(
    tts_text="测试文本",
    prompt_text="",
    prompt_speech_16k=None,
    zero_shot_spk_id="custom_speaker"
):
    audio = result['tts_speech']
```

### 查看可用说话人

```python
spks = model.list_available_spks()
print("可用说话人:", spks)
```

## ⚠️ 注意事项

### 文本分块建议

1. **最小chunk大小**: 建议每个chunk至少包含2-3个字
   - ❌ 不推荐: `["人", "工", "智", "能"]` (单字会出错)
   - ✅ 推荐: `["人工", "智能", "技术"]` (2字以上)

2. **语义完整性**: 尽量在语义完整的位置切分
   - ✅ 好: `["今天天气很好", "适合出去散步"]`
   - ⚠️ 差: `["今天天", "气很好适", "合出去"]`

3. **总长度限制**: 建议单次推理总文本不超过200个token

### 参数选择建议

- **默认使用**: `token_hop_len=15, mel_cache_len=6`
  - 延迟和效率的最佳平衡

- **追求速度**: `token_hop_len=8, mel_cache_len=4`
  - 首次响应约1.3秒,适合实时对话

- **追求效率**: `token_hop_len=25, mel_cache_len=8`
  - RTF最优,适合批处理和播报

### 硬件要求

- **CPU**: 支持,但推理速度较慢
- **GPU**: CUDA设备,显著提升速度
- **Apple Silicon**: 支持MPS加速 (M1/M2/M3/M4)

### 模型文件

确保模型目录包含以下文件:
```
CosyVoice2-0.5B/
├── cosyvoice2.yaml          # 配置文件
├── llm.pt                   # LLM权重
├── flow.pt                  # Flow模型权重
├── hift.pt                  # 声码器权重
├── campplus.onnx            # 说话人编码器
├── speech_tokenizer_v2.onnx # 语音tokenizer
├── spk2info.pt              # 说话人信息
└── CosyVoice-BlankEN/       # Qwen预训练模型
```

## 🐛 常见问题

### Q: 分块推理时音频不连贯?
A:
1. 确保使用`inference_sft_chunked`而不是多次调用`inference_sft`
2. 检查chunk是否在语义完整的位置切分
3. 适当增大`mel_cache_len`参数(如8或10)

### Q: 首次响应延迟高?
A:
1. 降低`token_hop_len`到8-10
2. 使用`stream=True`启用流式模式
3. 减小每个chunk的大小

### Q: 生成的音频质量不好?
A:
1. 检查参考音频质量(zero-shot模式)
2. 确保文本归一化正确
3. 尝试不同的说话人ID

### Q: 内存占用过高?
A:
1. 减小`token_hop_len`
2. 使用更短的文本chunk
3. 避免在单次调用中处理过长的文本

## 📊 性能基准

基于CosyVoice2-0.5B模型,Apple M4设备测试:

| 配置 | 首次响应 | RTF | Yield次数 | 适用场景 |
|------|---------|-----|----------|---------|
| token_hop_len=8 | 1.26s | 2.24 | 8 | 实时对话 |
| token_hop_len=15 | 1.47s | 1.53 | 6 | **通用推荐** |
| token_hop_len=25 | 1.94s | 1.39 | 4 | 批处理 |

测试文本: 6个短chunk,总计约3.5秒音频

## 🔄 更新日志

### v1.1.0 (2025-11)
- ✨ 新增 `inference_sft_chunked` 方法,支持流式文本分块推理
- ✨ 添加 `token_hop_len` 和 `mel_cache_len` 可调参数
- 📝 完善文档和使用示例
- 🔧 优化默认参数配置

### v1.0.0
- 🎉 初始版本,模块化封装CosyVoice2
- ✅ 支持多种推理模式
- ✅ 支持流式和非流式输出

## 📄 许可证

本项目基于CosyVoice2官方实现,遵循Apache 2.0许可证。

## 🙏 致谢

- CosyVoice2官方团队
- Qwen2模型团队
- 社区贡献者

## 📮 联系方式

如有问题或建议,请提交Issue或Pull Request。

---

**快速配置参考**:
```python
# 实时对话: token_hop_len=8, mel_cache_len=4
# 通用推荐: token_hop_len=15, mel_cache_len=6  ⭐
# 高质量: token_hop_len=25, mel_cache_len=8
```
