"""
统一异常处理模块

定义所有自定义异常类，提供统一的错误处理机制
"""
from typing import Optional, Any, Dict


class NewsAgentError(Exception):
    """新闻Agent基础异常类"""

    def __init__(
        self,
        message: str,
        code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "code": self.code,
            "details": self.details
        }


class DataNotFoundError(NewsAgentError):
    """数据未找到异常"""

    def __init__(self, message: str = "未找到相关数据", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=404, details=details)


class LLMError(NewsAgentError):
    """LLM服务异常"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=501, details=details)


class TTSError(NewsAgentError):
    """TTS服务异常"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=502, details=details)


class CrawlerError(NewsAgentError):
    """爬虫服务异常"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=503, details=details)


class ValidationError(NewsAgentError):
    """数据验证异常"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=400, details=details)


class WorkflowError(NewsAgentError):
    """工作流执行异常"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=500, details=details)
