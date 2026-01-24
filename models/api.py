"""
API 相关数据模型
包含 LLM Protocol 2.1 接口模型和 FastAPI 请求/响应模型
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


# ==================== LLM Protocol 2.1 请求模型 ====================

class QueryPartAudio(BaseModel):
    """查询部分的音频内容"""
    format: str  # 音频的编码格式，如 wav, mp3
    data: str  # 音频的 url 或 base64 数据，如 https://{url} 或 data:;base64,{base64}


class QueryPartImage(BaseModel):
    """查询部分的图片内容"""
    format: str  # 图片的编码格式，如 jpeg
    data: str  # 图片的 url 或 base64 数据


class QueryPart(BaseModel):
    """用户的多模态请求部分"""
    type: str  # 类型，如 text, audio, image 等
    text: Optional[str] = None  # text 类型的内容
    audio: Optional[QueryPartAudio] = None  # audio 类型的内容
    image: Optional[QueryPartImage] = None  # image 类型的内容


class HistoryContentImage(BaseModel):
    """历史记录中的图片内容"""
    url: str  # 图片的 URL 或 base64 数据


class HistoryContentNLU(BaseModel):
    """历史记录内容中的NLU信息"""
    domain: str  # 领域，如 llm
    intent: str  # 意图，如 llm-car-control, llm-car-knowledge


class HistoryContent(BaseModel):
    """历史记录中的内容"""
    type: str  # 内容类型，如 text, image
    text: Optional[str] = None  # 文本内容
    image: Optional[HistoryContentImage] = None  # 图片内容
    metadata: Optional[Dict[str, Any]] = None  # 图片元数据
    nlu: Optional[HistoryContentNLU] = None  # DIS of content（文档中在 content 内部）


class HistoryItem(BaseModel):
    """历史对话记录"""
    role: str  # 角色，如 user, assistant
    request_id: Optional[str] = None  # Request ID
    timestamp: Optional[int] = None  # Unix timestamp (milliseconds)
    content: List[HistoryContent]  # 内容


class ContextLLMNLU(BaseModel):
    """上下文中的LLM NLU分类结果"""
    domain: str  # 分类结果，如 llm
    intent: str  # 分类结果，如 llm-car-control


class ContextLocation(BaseModel):
    """车辆位置对象"""
    latitude: float  # 车辆纬度
    longitude: float  # 车辆经度


class ContextASRResult(BaseModel):
    """语音ASR识别结果对象"""
    language: str  # 语言类型：en, zh, zh-yue


class Context(BaseModel):
    """上下文数据"""
    llm_nlu: Optional[ContextLLMNLU] = None  # 系统代理的分类结果
    location: Optional[ContextLocation] = None  # 车辆位置对象
    asr_result: Optional[ContextASRResult] = None  # 语音ASR识别结果对象


class AgentRequest(BaseModel):
    """请求模型 - LLM Protocol 2.1"""
    version: str  # LLM Protocol version, 2.1
    request_id: str  # Request id, a unique ID for each request
    conversation_id: Optional[str] = None  # Conversation ID
    timestamp: int  # Unix timestamp (milliseconds)
    vin: str  # Vehicle VIN (anonymized)
    voice_zone: Optional[int] = None  # Voice zone (0=Invalid, 1=FrontLeft, 2=FrontRight, etc.)
    account_id: Optional[str] = None  # Login account ID (anonymized)
    user_id: Optional[str] = None  # User ID (anonymized)
    channel_id: Optional[str] = None  # Channel ID
    vehicle_model: Optional[str] = None  # Vehicle model/series
    query: str  # ASR result, user's original speech query
    query_parts: Optional[List[QueryPart]] = None  # 用户的多模态请求
    query_type: Optional[str] = Field(None, alias="_query_type")  # e.g. text, omni
    history: Optional[List[HistoryItem]] = None  # 历史对话记录
    context: Optional[Context] = None  # Context Data
    stream: bool  # Whether to use stream response
    debug: Optional[bool] = False  # Whether to display debug info

    class Config:
        # 允许额外字段，保持兼容性
        extra = "allow"
        # 允许通过别名填充
        populate_by_name = True


# ==================== LLM Protocol 2.1 响应模型 ====================

class FramePartAudio(BaseModel):
    """帧部分的音频内容"""
    format: str  # 音频的编码格式，模型输出格式是 pcm (单声道 24000Hz)
    data: str  # 音频的 base64 数据，如 data:;base64,{base64_audio}
    is_final: bool  # 音频是否结束


class FramePartImage(BaseModel):
    """帧部分的图片内容"""
    format: str  # 图片格式，如 png, jpg
    data: str  # 图片临时地址，如 https://xxx.aliyuncs.com/xxx/png


class FramePart(BaseModel):
    """agent 的多模态响应部分"""
    type: str  # 类型，如 text, audio, image 等
    text: Optional[str] = None  # text 类型的内容（有 frame_text 暂时不填）
    audio: Optional[FramePartAudio] = None  # audio 类型的内容
    image: Optional[FramePartImage] = None  # image 类型的内容


class Usage(BaseModel):
    """Token统计信息"""
    input_tokens: int  # Number of input tokens
    output_tokens: int  # Number of output tokens
    total_tokens: int  # Total tokens = input tokens + output tokens


class ResponseData(BaseModel):
    """
    响应数据内容 - LLM Protocol 2.1
    
    注意：文档中标记为必填的字段，在实际返回时应确保有值。
    这里使用 Optional 是为了构建响应时的灵活性。
    """
    agent_id: Optional[str] = None  # Agent ID, llm-car-knowledge
    frame_timestamp: Optional[int] = None  # Frame unix timestamp (milliseconds)
    frame_id: Optional[int] = None  # Frame ID, zero-based indexing
    frame_text: Optional[str] = None  # Unstructured frame data content
    content: Optional[str] = None  # 统一文本内容出口（thinking/content）
    frame_parts: Optional[List[FramePart]] = None  # agent 的多模态响应，final 帧为 null
    frame_is_final: Optional[bool] = None  # Whether this is the final frame
    response_type: Optional[str] = None  # e.g. omni, thinking
    complete_content: Optional[str] = None  # Complete text response content
    extension: Optional[Dict[str, Any]] = None  # Structured data generated by the LLM
    usage: Optional[Usage] = None  # Token statistics, output in the final frame
    debug_info: Optional[Dict[str, Any]] = None  # Debug information

    class Config:
        # 允许额外字段，保持兼容性
        extra = "allow"


class BaseResponse(BaseModel):
    """基础响应模型 - LLM Protocol 2.1"""
    version: str  # LLM protocol version
    request_id: str  # Agent request id
    code: int  # Response code, non-zero indicates an error
    message: str  # Error message, 'success' for successful responses
    event: Optional[str] = None  # Events: submitted, thinking, acting, completed, incompleted, user_stopped
    data: Optional[ResponseData] = None  # Response data


# ==================== FastAPI 请求/响应模型 ====================

class ChatRequest(BaseModel):
    """聊天请求模型"""
    query: str = Field(..., description="用户查询", example="今天有什么新闻")
    request_id: Optional[str] = Field(None, description="请求ID（可选，自动生成）")
    stream: bool = Field(True, description="是否使用流式响应")
    debug: bool = Field(False, description="是否显示调试信息")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    version: str
    uptime: str


# ==================== 兼容性别名 ====================

# 为了向后兼容，保留以下别名
AgentResponse = ResponseData
HistoryNLU = HistoryContentNLU  # 旧代码可能引用这个名称

