# API 响应格式详解

## 概述

`/api/v1/chat` 接口**同时支持流式和非流式**两种响应模式，通过请求参数 `stream` 控制。

无论哪种模式，都使用 **Server-Sent Events (SSE)** 格式返回。

## 响应格式

### SSE 数据格式

每个响应帧的格式：

```
event:data
data:{"version":"2.1","request_id":"xxx","code":0,"message":"success","data":{...}}

event:data
data:{"version":"2.1","request_id":"xxx","code":0,"message":"success","data":{...}}
```

## 模式一：流式响应 (stream=true)

### 请求示例

```json
{
  "version": "2.1",
  "request_id": "test_123",
  "stream": true,
  "query": "今天有什么新闻"
}
```

### 响应流程

```
帧1: frame_text="收"                    → frame_is_final=false
帧2: frame_text="收到"                  → frame_is_final=false
帧3: frame_text="收到您"                → frame_is_final=false
...
帧N: frame_text="收到您的查询：今天有什么新闻..."  → frame_is_final=false
帧N+1: frame_text="", complete_content="完整文本", frame_is_final=true
```

### 数据字段说明

#### 中间帧（逐字发送）

```json
{
  "version": "2.1",
  "request_id": "test_123",
  "code": 0,
  "message": "success",
  "data": {
    "frame_id": 0,
    "frame_timestamp": 1736380800000,
    "frame_text": "收",              // ← 累积的文本内容
    "frame_is_final": false          // ← 不是最后一帧
  }
}
```

#### 最终帧（包含完整数据）

```json
{
  "version": "2.1",
  "request_id": "test_123",
  "code": 0,
  "message": "success",
  "data": {
    "frame_id": 153,
    "frame_timestamp": 1736380803060,
    "frame_text": "",                              // ← 最终帧此字段为空
    "frame_is_final": true,                        // ← 标记为最终帧
    "complete_content": "收到您的查询：今天有...", // ← 完整文本 ⭐
    "frame_parts": [                               // ← 多模态数据 ⭐
      {
        "type": "audio",
        "audio": {
          "format": "wav",
          "data": "data:;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAA...",
          "is_final": true
        }
      }
    ],
    "debug_info": {                                 // ← 调试信息（如果开启）
      "request": {...},
      "totalTime": 1260
    }
  }
}
```

### 关键点

- ✅ **frame_text**: 流式过程中的累积文本
- ✅ **complete_content**: **仅在最终帧中**，包含完整文本
- ✅ **frame_parts**: **仅在最终帧中**，包含音频等多模态数据
- ✅ **frame_is_final**: 标记是否为最后一帧

## 模式二：非流式响应 (stream=false)

### 请求示例

```json
{
  "version": "2.1",
  "request_id": "test_123",
  "stream": false,
  "query": "今天有什么新闻"
}
```

### 响应流程

```
帧1: frame_text="完整文本内容..."  → frame_is_final=false
帧2: frame_text="", complete_content="完整文本内容", frame_is_final=true
```

### 数据字段说明

#### 第一帧（内容帧）

```json
{
  "data": {
    "frame_id": 0,
    "frame_timestamp": 1736380800000,
    "frame_text": "收到您的查询：今天有什么新闻...",  // ← 全部文本
    "frame_is_final": false
  }
}
```

#### 第二帧（完成帧）

```json
{
  "data": {
    "frame_id": 1,
    "frame_timestamp": 1736380803060,
    "frame_text": "",                              // ← 为空
    "frame_is_final": true,                        // ← 最终帧标记
    "complete_content": "收到您的查询：今天有...", // ← 完整文本 ⭐
    "frame_parts": [...]                           // ← 音频数据 ⭐
  }
}
```

## 数据字段汇总

### ResponseData 数据结构

| 字段 | 类型 | 说明 | 出现位置 |
|------|------|------|----------|
| `frame_id` | int | 帧序号（从0开始） | 所有帧 |
| `frame_timestamp` | int | 帧时间戳（毫秒） | 所有帧 |
| `frame_text` | string | 文本内容 | 中间帧有内容 |
| `frame_is_final` | bool | 是否为最终帧 | 所有帧 |
| `complete_content` | string | **完整文本** | **仅最终帧** ⭐ |
| `frame_parts` | array | **多模态数据** | **仅最终帧** ⭐ |
| `debug_info` | object | 调试信息 | 仅最终帧（开启debug时） |

### FramePart 数据结构（多模态）

```json
{
  "type": "audio",              // 类型：audio, image, text 等
  "audio": {
    "format": "wav",            // 音频格式
    "data": "data:;base64,...", // Base64 编码的音频数据
    "is_final": true
  }
}
```

## 如何获取完整数据

### 方式一：使用 frame_is_final 判断

```python
async for line in response:
    if line.startswith("data:"):
        json_str = line[5:].strip()
        data = json.loads(json_str)
        response_data = data["data"]

        if response_data.get("frame_is_final"):
            # 这是最终帧，包含完整数据
            complete_text = response_data.get("complete_content")
            frame_parts = response_data.get("frame_parts")

            print(f"完整文本: {complete_text}")
            if frame_parts:
                for part in frame_parts:
                    if part["type"] == "audio":
                        audio_data = part["audio"]["data"]
                        print(f"音频数据: {audio_data[:50]}...")
```

### 方式二：累积 frame_text

```python
complete_text = ""
async for line in response:
    if line.startswith("data:"):
        json_str = line[5:].strip()
        data = json.loads(json_str)
        response_data = data["data"]

        # 累积 frame_text
        if response_data.get("frame_text"):
            complete_text += response_data["frame_text"]

        # 检查是否完成
        if response_data.get("frame_is_final"):
            # 可以使用累积的文本，或使用 complete_content 字段
            final_text = response_data.get("complete_content", complete_text)
            print(f"完整文本: {final_text}")
```

## 实际示例

### 流式响应完整示例

```bash
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "version": "2.1",
    "request_id": "test_001",
    "timestamp": 1736380800000,
    "vin": "TEST",
    "channel_id": "test",
    "query": "今天有什么新闻",
    "stream": true
  }'
```

**响应**：
```
event:data
data:{"version":"2.1","request_id":"test_001","code":0,"message":"success","data":{"frame_id":0,"frame_timestamp":1736380800000,"frame_text":"收","frame_is_final":false}}

event:data
data:{"version":"2.1","request_id":"test_001","code":0,"message":"success","data":{"frame_id":1,"frame_timestamp":1736380800020,"frame_text":"收到","frame_is_final":false}}

...

event:data
data:{"version":"2.1","request_id":"test_001","code":0,"message":"success","data":{"frame_id":153,"frame_timestamp":1736380803060,"frame_text":"","frame_is_final":true,"complete_content":"收到您的查询：今天有什么新闻\n\n为您播报今日新闻摘要：...","frame_parts":[{"type":"audio","audio":{"format":"wav","data":"data:;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAA...","is_final":true}}]}}
```

## 总结

### 1. 响应模式

✅ **同时支持流式和非流式**，通过 `stream` 参数控制

### 2. 返回格式

✅ **统一使用 SSE (Server-Sent Events)** 格式

### 3. 数据获取

✅ **最终帧中包含完整数据**：
- `complete_content` - 完整文本
- `frame_parts` - 多模态数据（音频等）

### 4. 判断方法

✅ 使用 `frame_is_final == true` 判断是否为最终帧

---

**最后更新**: 2025-01-09
