"""
TTS 工具模块
提供流式文本转语音服务
"""
from tts_utils.tts_service import TTSService, get_tts_service
from tts_utils.local_tts_service import LocalTTSService
from tts_utils.tts_manager import TTSServiceManager, get_tts_manager

__all__ = [
    "TTSService",
    "get_tts_service",
    "LocalTTSService",
    "TTSServiceManager",
    "get_tts_manager"
]
