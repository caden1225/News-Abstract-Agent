"""
TTS 服务管理模块

提供 TTS 服务的统一管理接口，包括：
- 服务初始化和生命周期管理
- 说话人列表查询
"""
import logging
from typing import Optional, List
from llm_utils.config import config

logger = logging.getLogger(__name__)


class TTSServiceManager:
    """TTS 服务管理器"""

    def __init__(self):
        """初始化 TTS 服务管理器"""
        self._tts_service = None
        self._local_service = None

    def get_tts_service(self):
        """
        获取 TTS 服务实例（单例模式）

        Returns:
            TTSService 实例
        """
        if self._tts_service is None:
            from .tts_service import TTSService
            self._tts_service = TTSService()
        return self._tts_service

    def get_local_service(self):
        """
        获取本地 TTS 服务实例

        Returns:
            LocalTTSService 实例，如果未初始化则返回 None
        """
        if self._local_service is None:
            from .local_tts_service import LocalTTSService
            import threading
            import signal

            model_dir = config.get("tts.local_model_dir")
            if model_dir:
                try:
                    # 使用线程初始化，避免阻塞主线程
                    init_result = {"service": None, "error": None}
                    
                    def init_in_thread():
                        """在线程中初始化TTS服务"""
                        try:
                            init_result["service"] = LocalTTSService(
                                model_dir=model_dir,
                                model_type=config.get("tts.local_model_type", "auto"),
                                spk_id=config.get("tts.default_spk_id", "girl_zh"),
                                enabled=config.get("tts.enabled", True)
                            )
                        except Exception as e:
                            init_result["error"] = e
                            logger.error(f"初始化本地 TTS 服务失败: {e}", exc_info=True)
                    
                    # 启动初始化线程
                    init_thread = threading.Thread(target=init_in_thread, daemon=True)
                    init_thread.start()
                    
                    # 等待初始化完成，设置超时避免无限等待
                    init_thread.join(timeout=60.0)  # 60秒超时
                    
                    if init_thread.is_alive():
                        logger.warning("TTS服务初始化超时（60秒），可能仍在后台初始化中")
                        # 不设置self._local_service，下次调用时会重试
                        return None
                    
                    if init_result["error"]:
                        logger.error(f"TTS服务初始化失败: {init_result['error']}")
                        return None
                    
                    self._local_service = init_result["service"]
                except Exception as e:
                    logger.error(f"初始化本地 TTS 服务失败: {e}", exc_info=True)
        return self._local_service

    def list_speakers(self) -> Optional[List[str]]:
        """
        列出所有可用的说话人ID

        Returns:
            说话人ID列表，如果服务不可用则返回 None
        """
        local_service = self.get_local_service()
        if local_service:
            return local_service.list_speakers()
        else:
            logger.warning("本地 TTS 服务未初始化")
            return None

    def is_local_available(self) -> bool:
        """
        检查本地 TTS 服务是否可用

        Returns:
            本地服务是否可用
        """
        local_service = self.get_local_service()
        return local_service is not None and local_service.enabled

    def get_service_info(self) -> dict:
        """
        获取当前服务信息

        Returns:
            包含服务信息的字典
        """
        info = {
            "mode": "local",
            "enabled": config.get("tts.enabled", True),
            "model_dir": config.get("tts.local_model_dir"),
            "model_type": config.get("tts.local_model_type", "auto"),
            "default_spk_id": config.get("tts.default_spk_id", "girl_zh"),
            "local_available": self.is_local_available()
        }

        # 获取说话人列表
        speakers = self.list_speakers()
        if speakers:
            info["available_speakers"] = speakers

        return info


# 全局服务管理器实例
_tts_manager: Optional[TTSServiceManager] = None


def get_tts_manager() -> TTSServiceManager:
    """获取 TTS 服务管理器实例（单例）"""
    global _tts_manager
    if _tts_manager is None:
        _tts_manager = TTSServiceManager()
    return _tts_manager
