"""
配置管理模块
支持从 YAML 配置文件读取配置，并支持环境变量替换
支持可选的Pydantic配置验证
"""
from pathlib import Path
import yaml
import os
import logging
from typing import Optional

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# 获取项目根目录（向上两级：llm_utils -> 项目根）
project_root = Path(__file__).parent.parent


class Config(object):
    """配置管理类"""

    def __init__(self):
        """初始化配置"""
        config_path = project_root / 'config' / 'config.yaml'
        logger.info(f"Loading config from: {config_path}")

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, 'r', encoding="UTF-8") as f:
            self.config_data = yaml.safe_load(f)

        # 支持环境变量替换
        self._replace_env_vars()

        logger.info("Config loaded successfully")

    def _replace_env_vars(self):
        """递归替换配置中的环境变量"""

        def replace_value(value):
            if isinstance(value, dict):
                return {k: replace_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [replace_value(item) for item in value]
            elif isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                # 替换 ${VAR_NAME} 格式的环境变量
                # 支持默认值：${VAR_NAME:default_value}
                if ':' in value and value.endswith('}'):
                    # 有默认值的情况
                    env_var = value[2:].split(':', 1)[0]
                    default_val = value.rsplit(':', 1)[1][:-1]
                else:
                    # 无默认值的情况
                    env_var = value[2:-1]
                    default_val = value

                env_value = os.getenv(env_var)
                if env_value is None:
                    # 只在真正使用 sidecar 模式时才警告
                    # 检查是否在 sidecar 模式
                    current_mode = os.getenv("LLM_MODE", "sidecar").lower()
                    if current_mode == "sidecar" and env_var == "LLM_API_KEY":
                        logger.warning(f"环境变量 {env_var} 未设置（仅在使用 sidecar 模式时需要）")
                    return default_val
                return env_value
            return value

        self.config_data = replace_value(self.config_data)

    def get_value(self, key):
        """
        获取配置值，支持点分隔的路径

        Args:
            key: 配置键，支持 "llm.base_url" 格式

        Returns:
            配置值
        """
        keys = key.split('.')
        value = self.config_data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return None
            else:
                return None
        return value

    def get(self, key, default_value=None):
        """
        安全获取配置值

        Args:
            key: 配置键
            default_value: 默认值

        Returns:
            配置值，如果不存在则返回默认值
        """
        try:
            value = self.get_value(key)
            return value if value is not None else default_value
        except (KeyError, TypeError):
            return default_value

    def get_llm_config(self):
        """
        获取LLM配置（支持OpenRouter、Sidecar和Qianfan）

        优先级：环境变量 > config.yaml

        Returns:
            dict: {
                "base_url": str,
                "api_key": str,
                "model": str,
                "mode": str
            }
        """
        import os

        # 检查LLM_MODE环境变量
        llm_mode = os.getenv("LLM_MODE", "sidecar").lower()

        if llm_mode == "qianfan":
            # 百度千帆模式：从环境变量读取
            base_url = os.getenv("QIANFAN_BASE_URL", "https://qianfan.baidubce.com/v2")
            api_key = os.getenv("QIANFAN_API_KEY", "")
            model = os.getenv("QIANFAN_MODEL", "qwen3-32b")

            if not api_key:
                logger.warning("QIANFAN_API_KEY not configured, please set it in .env file")

            return {
                "base_url": base_url,
                "api_key": api_key,
                "model": model,
                "mode": "qianfan"
            }

        elif llm_mode == "openrouter":
            # OpenRouter模式：从环境变量读取
            base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
            api_key = os.getenv("OPENROUTER_API_KEY", "")
            model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4:latest")

            if not api_key or api_key == "your_openrouter_api_key_here":
                logger.warning("OPENROUTER_API_KEY not configured, please set it in .env file")

            return {
                "base_url": base_url,
                "api_key": api_key,
                "model": model,
                "mode": "openrouter"
            }

        else:
            # Sidecar模式：从config.yaml读取
            base_url = self.get("llm.base_url", "")
            api_key = self.get("llm.api_key", "")
            model = self.get("llm.summarizer_model", "")

            return {
                "base_url": base_url,
                "api_key": api_key,
                "model": model,
                "mode": "sidecar"
            }

    def get_thinking_config(self):
        """
        获取LLM thinking功能配置
        
        优先级：环境变量 > config.yaml
        
        Returns:
            dict: {
                "enable_thinking": bool,  # 是否启用thinking
                "thinking_budget": int    # thinking token预算
            }
        """
        import os
        
        # 从环境变量或配置文件获取
        enable_thinking_str = os.getenv("ENABLE_LLM_THINKING")
        if enable_thinking_str is None:
            # 从config.yaml读取
            enable_thinking_str = str(self.get("llm.enable_thinking", "true"))
        
        # 解析布尔值
        enable_thinking = enable_thinking_str.lower() in ("true", "1", "yes", "on")
        
        # 获取thinking预算
        thinking_budget = int(self.get("llm.thinking_budget", 1024))
        
        return {
            "enable_thinking": enable_thinking,
            "thinking_budget": thinking_budget
        }

    def reload(self):
        """重新加载配置文件"""
        logger.info("Reloading config...")
        config_path = project_root / 'config' / 'config.yaml'
        with open(config_path, 'r', encoding="UTF-8") as f:
            self.config_data = yaml.safe_load(f)
        self._replace_env_vars()
        logger.info("Config reloaded successfully")

    def validate(self) -> Optional[dict]:
        """
        使用Pydantic验证当前配置

        Returns:
            验证后的配置字典，如果验证失败则返回None

        Note:
            此方法是可选的，用于在需要时验证配置
            不会影响现有的get()方法
        """
        try:
            from core.config_schema import validate_config
            validated = validate_config(self.config_data)
            logger.info("配置验证成功")
            return validated.dict()
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            return None


# 全局配置实例
config = Config()
