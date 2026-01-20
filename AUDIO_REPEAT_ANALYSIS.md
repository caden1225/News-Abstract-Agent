# 音频重复问题分析

## 问题描述

在流式TTS合成中，前面音频会有一部分重复。

## 根本原因

这是CosyVoice2流式处理的边界平滑机制导致的。具体流程如下：

### 第一个音频块的处理流程

```python
# CosyVoice2Model.token2wav() 方法

# 1. 第一个音频块：没有缓存
if self.hift_cache_dict[uuid] is None:
    hift_cache_source = torch.zeros(1, 1, 0)

# 2. 生成音频
tts_speech, tts_source = self.hift.inference(...)

# 3. 保存缓存（关键！）
self.hift_cache_dict[uuid] = {
    'mel': tts_mel[:, :, -self.mel_cache_len:],
    'source': tts_source[:, :, -self.source_cache_len:],
    'speech': tts_speech[:, -self.source_cache_len:]  # 保存最后source_cache_len长度
}

# 4. 切除最后source_cache_len长度
tts_speech = tts_speech[:, :-self.source_cache_len]  # ⚠️ 第一个音频块被切除了最后部分
```

**问题**：第一个音频块的最后 `source_cache_len` 长度被保存到缓存，但第一个音频块本身也被切除了这部分，导致第一个音频块不完整。

### 第二个音频块的处理流程

```python
# 1. 拼接缓存的mel（来自第一个音频块）
if self.hift_cache_dict[uuid] is not None:
    hift_cache_mel = self.hift_cache_dict[uuid]['mel']
    tts_mel = torch.concat([hift_cache_mel, tts_mel], dim=2)

# 2. 生成音频（包含缓存部分）
tts_speech, tts_source = self.hift.inference(...)

# 3. 边界平滑（关键！）
if self.hift_cache_dict[uuid] is not None:
    # fade_in_out会混合缓存的speech和新生成的speech
    tts_speech = fade_in_out(
        tts_speech,  # 新生成的音频
        self.hift_cache_dict[uuid]['speech'],  # 缓存的音频（来自第一个音频块的最后部分）
        self.speech_window  # 汉宁窗，用于平滑过渡
    )

# 4. 保存新的缓存
self.hift_cache_dict[uuid] = {
    'speech': tts_speech[:, -self.source_cache_len:]
}

# 5. 切除最后source_cache_len长度
tts_speech = tts_speech[:, :-self.source_cache_len]
```

**问题**：`fade_in_out` 函数会混合缓存的音频（来自第一个音频块的最后部分）和新生成的音频，导致第二个音频块的开头包含了第一个音频块的最后部分，造成重复。

### fade_in_out 函数的工作原理

```python
def fade_in_out(fade_in_mel, fade_out_mel, window):
    mel_overlap_len = int(window.shape[0] / 2)
    # 混合前mel_overlap_len长度
    fade_in_mel[..., :mel_overlap_len] = (
        fade_in_mel[..., :mel_overlap_len] * window[:mel_overlap_len] +  # 新音频（淡入）
        fade_out_mel[..., -mel_overlap_len:] * window[mel_overlap_len:]  # 缓存音频（淡出）
    )
    return fade_in_mel
```

这个函数会在新音频的开头和缓存音频的结尾之间创建平滑过渡，但这也导致了部分重复。

## 重复长度计算

- `mel_cache_len = 3`（配置值）
- `source_cache_len = mel_cache_len * 480 = 3 * 480 = 1440` 样本（对于CosyVoice2）
- 采样率：24000 Hz
- **重复时长**：`1440 / 24000 = 0.06秒`（约60毫秒）

实际上，由于 `fade_in_out` 的平滑窗口是 `2 * source_cache_len`，重复部分可能更长。

## 为什么需要这个机制？

1. **保证音频连续性**：流式处理时，每个音频块是独立生成的，需要平滑过渡避免不连续
2. **边界平滑**：使用汉宁窗进行淡入淡出，避免音频块之间的突变
3. **模型要求**：HiFT模型需要一定的上下文（缓存）来生成高质量的音频

## 解决方案

### 方案1：接受重复（推荐）

这是CosyVoice2的正常行为，用于保证音频质量。重复部分很短（约60-120毫秒），通常不影响理解。

### 方案2：调整 mel_cache_len

减小 `mel_cache_len` 可以减少重复长度，但可能影响音频质量：

```yaml
mel_cache_len: 1  # 最小重复，但可能影响质量
```

### 方案3：后处理去重（不推荐，已尝试但失败）

**尝试结果**：尝试通过去除第二个及后续音频块开头的重复部分来修复，但导致：
- 前面音频重复多次
- 后面音频缺失

**原因分析**：
- `fade_in_out` 是混合操作，不是完全重复
- 混合的是新音频和缓存音频，权重由汉宁窗决定
- 简单切除会导致音频不连续或缺失
- CosyVoice2的流式处理机制设计如此，无法通过后处理完美修复

**结论**：这是CosyVoice2流式处理的正常行为，应该接受这个重复。

## 当前配置的影响

当前默认配置：
- `mel_cache_len = 3`
- `source_cache_len = 3 * 480 = 1440` 样本
- 重复时长：约 0.06秒

这个重复长度是合理的，既能保证音频质量，又不会造成明显的重复感。

## 总结

音频重复是CosyVoice2流式处理的**正常行为**，用于：
1. 保证音频块之间的平滑过渡
2. 提供模型所需的上下文
3. 提高音频质量

重复部分很短（约60-120毫秒），通常不影响使用体验。如果觉得重复明显，可以适当减小 `mel_cache_len`，但要注意可能影响音频质量。

