"""
TTS 模块包

包含各种 TTS 引擎的实现：
- cosyvoice2: CosyVoice2/CosyVoice3 本地模型
"""

# 使用懒加载避免模块代理冲突
def __getattr__(name):
    if name in ("TTSService", "AsyncTTSService"):
        from .cosyvoice2 import TTSService, AsyncTTSService
        globals()["TTSService"] = TTSService
        globals()["AsyncTTSService"] = AsyncTTSService
        return TTSService if name == "TTSService" else AsyncTTSService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["TTSService", "AsyncTTSService"]
