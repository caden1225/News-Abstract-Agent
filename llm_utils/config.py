"""
配置管理模块
支持从 YAML 配置文件读取配置，并支持环境变量替换
"""
from pathlib import Path
import yaml
import os
import logging

logger = logging.getLogger(__name__)

# 获取当前文件所在目录
parent_path = Path(__file__).parent


class Config(object):
    """配置管理类"""

    def __init__(self):
        """初始化配置"""
        config_path = parent_path / 'resources/config.yaml'
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
                env_var = value[2:-1]
                env_value = os.getenv(env_var)
                if env_value is None:
                    logger.warning(f"Environment variable {env_var} not found, using original value")
                    return value
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

    def reload(self):
        """重新加载配置文件"""
        logger.info("Reloading config...")
        config_path = parent_path / 'resources/config.yaml'
        with open(config_path, 'r', encoding="UTF-8") as f:
            self.config_data = yaml.safe_load(f)
        self._replace_env_vars()
        logger.info("Config reloaded successfully")


# 全局配置实例
config = Config()
