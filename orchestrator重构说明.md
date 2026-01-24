# Orchestrator 重构说明

## 重构目标

按照以下要求精简 orchestrator 的逻辑：
1. think文本不合成语音，content文本合成
2. 先启动文本生成，再启动语音合成，这两个任务最后没有任务阻塞关系
3. 生成的文本还是累积一定长度后再提交给音频合成
4. 音频合成一个文本输入对应一个音频输出块

## 重构后的架构

### 两阶段模型

```
阶段1：文本生成 (text_generator)
  └─ LLM流式输出
      ├─ thinking tokens → 立即输出（不提交TTS）
      └─ content tokens → 累积后输出 + 提交TTS

阶段2：语音合成 (tts_synthesizer)
  └─ 独立运行，一个文本chunk对应一个音频chunk

调度器：dispatcher
  └─ 优先排空thinking帧，然后交替输出text和audio帧
```

## 关键改进

### 1. 文本生成阶段 (`text_generator`)

- **thinking处理**：
  - `flush_thinking()`: thinking文本立即输出到 `text_frame_queue`，**不提交TTS**
  - 添加 `<think>` 标签包装

- **content处理**：
  - `flush_content()`: content文本累积到一定长度后：
    - 输出到 `text_frame_queue`（用于客户端显示）
    - 提交到 `tts_queue`（用于TTS合成）
  - 使用 `_should_flush_text()` 判断是否刷新（基于长度、标点、时间）

### 2. 语音合成阶段 (`tts_synthesizer`)

- **独立运行**：与文本生成阶段无阻塞关系
- **一对一映射**：一个文本chunk对应一个音频chunk
- **结束判断**：通过预取下一个chunk判断是否是最后一个

### 3. 调度器 (`dispatcher`)

- **优先策略**：
  1. 完全排空thinking帧（确保thinking不被延迟）
  2. 处理text帧
  3. 处理audio帧

- **无阻塞等待**：两个阶段独立完成，不互相等待

## 代码结构

```python
async def _stream_llm_and_tts(...):
    # 配置和队列初始化
    
    async def text_generator():
        """阶段1：文本生成"""
        # thinking立即输出，不提交TTS
        # content累积后输出并提交TTS
    
    async def tts_synthesizer():
        """阶段2：语音合成"""
        # 独立运行，一个文本chunk对应一个音频chunk
    
    async def dispatcher():
        """统一调度"""
        # 优先排空thinking帧，然后交替输出text和audio帧
    
    # 启动两个独立任务（无阻塞关系）
    text_task = asyncio.create_task(text_generator())
    tts_task = asyncio.create_task(tts_synthesizer())
    
    # 调度输出
    async for frame in dispatcher():
        yield frame
```

## 解决的问题

1. ✅ **thinking帧延迟问题**：通过优先排空thinking帧，确保thinking不被音频延迟
2. ✅ **任务阻塞问题**：文本生成和语音合成独立运行，无阻塞关系
3. ✅ **逻辑简化**：从三协程模型简化为两阶段模型，逻辑更清晰
4. ✅ **一对一映射**：一个文本chunk对应一个音频chunk，关系明确

## 注意事项

1. **TTS队列管理**：使用预取机制判断最后一个chunk，需要正确处理队列为空的情况
2. **错误处理**：两个阶段都有独立的错误处理，不会互相影响
3. **资源清理**：使用 `finally` 确保任务正确结束和资源清理
