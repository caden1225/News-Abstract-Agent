"""
TTS 工具模块
提供统一的TTS服务接口
"""
import logging
from typing import Optional

from llm_utils.config import config

logger = logging.getLogger(__name__)


def get_tts_service():
    """
    获取TTS服务实例

    根据配置自动选择TTS后端：
    - dashscope: DashScope TTS（阿里云通义千问API）
    - cosyvoice2: CosyVoice2（本地模型）
    - mock: Mock TTS（测试用）

    配置方式：
    1. 环境变量: TTS_SERVICE_TYPE=dashscope|cosyvoice2|mock
    2. 配置文件: tts.service_type

    Returns:
        TTS服务实例
    """
    import os
    tts_config = config.get("tts", {})
    enabled = tts_config.get("enabled", True)
    mock_mode = tts_config.get("mock", False)

    if not enabled:
        logger.info("TTS 服务已禁用")
        return None

    if mock_mode:
        logger.info("使用 Mock TTS 服务")
        from .mock_service import MockTTSService
        return MockTTSService()

    # 获取服务类型（优先环境变量，其次配置文件）
    service_type = os.getenv("TTS_SERVICE_TYPE", "").lower() or tts_config.get("service_type", "cosyvoice2").lower()

    # DashScope 服务
    if service_type == "dashscope":
        try:
            from .dashscope_service import get_tts_service as get_dashscope_service
            service = get_dashscope_service()
            logger.info("使用 DashScope TTS 服务")
            return service
        except ImportError as e:
            logger.error(f"DashScope 导入失败: {e}")
            raise RuntimeError(f"DashScope TTS 服务不可用: {e}")
        except Exception as e:
            logger.error(f"初始化 DashScope 失败: {e}")
            raise RuntimeError(f"DashScope TTS 服务初始化失败: {e}")

    # CosyVoice2 服务（默认）
    if service_type == "cosyvoice2" or not service_type:
        try:
            from .cosyvoice2_service import get_tts_service as get_cv2_service
            service = get_cv2_service()
            logger.info("使用 CosyVoice2 TTS 服务")
            return service
        except ImportError as e:
            logger.warning(f"CosyVoice2 导入失败: {e}")
            logger.warning("回退到 Mock TTS 服务")
            from .mock_service import MockTTSService
            return MockTTSService()
        except Exception as e:
            logger.error(f"初始化 CosyVoice2 失败: {e}")
            raise

    # 未知服务类型，回退到 CosyVoice2
    logger.warning(f"未知的 TTS 服务类型: {service_type}，使用 CosyVoice2")
    try:
        from .cosyvoice2_service import get_tts_service as get_cv2_service
        service = get_cv2_service()
        logger.info("使用 CosyVoice2 TTS 服务")
        return service
    except Exception as e:
        logger.error(f"初始化 CosyVoice2 失败: {e}")
        raise


async def initialize_tts():
    """初始化TTS服务（在应用启动时调用）"""
    import os
    tts_config = config.get("tts", {})
    enabled = tts_config.get("enabled", True)
    mock_mode = tts_config.get("mock", False)

    if not enabled:
        logger.info("TTS 服务已禁用")
        return True

    if mock_mode:
        logger.info("使用 Mock TTS 服务")
        return True

    # 获取服务类型（优先环境变量，其次配置文件）
    service_type = os.getenv("TTS_SERVICE_TYPE", "").lower() or tts_config.get("service_type", "cosyvoice2").lower()

    # DashScope 服务
    if service_type == "dashscope":
        try:
            from .dashscope_service import initialize_tts as init_dashscope
            return await init_dashscope()
        except Exception as e:
            logger.error(f"DashScope TTS 初始化失败: {e}")
            raise RuntimeError(f"DashScope TTS 服务初始化失败: {e}")

    # CosyVoice2 服务（默认）
    if service_type == "cosyvoice2" or not service_type:
        try:
            from .cosyvoice2_service import initialize_tts as init_cv2
            return await init_cv2()
        except Exception as e:
            logger.error(f"TTS 初始化失败: {e}")
            return False

    # 未知服务类型，回退到 CosyVoice2
    logger.warning(f"未知的 TTS 服务类型: {service_type}，使用 CosyVoice2")
    try:
        from .cosyvoice2_service import initialize_tts as init_cv2
        return await init_cv2()
    except Exception as e:
        logger.error(f"TTS 初始化失败: {e}")
        return False


__all__ = [
    "get_tts_service",
    "initialize_tts",
]
