"""
配置验证模块

使用Pydantic进行配置验证，确保配置的正确性
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
import os
import yaml
from pathlib import Path


class LLMConfigModel(BaseModel):
    """LLM配置模型"""
    base_url: str
    api_key: str = ""
    summarizer_model: str = "Qwen2.5-7B-Instruct"
    timeout: int = Field(default=30, gt=0, le=300)
    enable_thinking: bool = True
    thinking_budget: int = Field(default=1024, gt=0, le=8192)

    @validator('api_key', pre=True)
    def validate_api_key(cls, v):
        """验证API key，支持环境变量替换"""
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            # 提取环境变量名
            env_var = v[2:-1].split(":")[0]
            default_value = v[2:-1].split(":")[1] if ":" in v[2:-1] else ""
            return os.getenv(env_var, default_value)
        return v


class TTSConfigModel(BaseModel):
    """TTS配置模型"""
    local_model_dir: Optional[str] = None
    local_model_type: str = "auto"
    default_spk_id: str = "girl_zh"
    enabled: bool = True


class NewsSourceModel(BaseModel):
    """新闻源配置模型"""
    name: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)


class NewsConfigModel(BaseModel):
    """新闻配置模型"""
    sources: List[NewsSourceModel] = Field(default_factory=list)
    max_news_per_source: int = Field(default=10, gt=0, le=100)
    cache_ttl: int = Field(default=3600, gt=0, le=86400)


class APIConfigModel(BaseModel):
    """API配置模型"""
    host: str = "0.0.0.0"
    port: int = Field(default=8080, gt=0, le=65535)
    debug: bool = False


class NewsSelectionConfigModel(BaseModel):
    """新闻选择配置模型"""
    max_selected_news: int = Field(default=5, gt=0, le=20)
    max_images: int = Field(default=10, gt=0, le=50)


class CrawlerConfigModel(BaseModel):
    """爬虫配置模型"""
    config_path: str = "config/sites.yaml"
    db_path: str = "data/news.db"
    verbose: bool = False
    crawl_interval_hours: int = Field(default=1, gt=0, le=24)


class SchedulerConfigModel(BaseModel):
    """定时任务配置模型"""
    enabled: bool = False
    timezone: str = "Asia/Shanghai"
    persist_jobs: bool = True
    jobs_db_path: str = "data/scheduler_jobs.db"
    daily_crawl: Optional[Dict[str, Any]] = None
    cleanup: Optional[Dict[str, Any]] = None
    health_check: Optional[Dict[str, Any]] = None
    weekly_clear: Optional[Dict[str, Any]] = None


class LoggingConfigModel(BaseModel):
    """日志配置模型"""
    level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class AppConfigModel(BaseModel):
    """应用配置模型"""
    llm: LLMConfigModel
    tts: TTSConfigModel
    news: NewsConfigModel
    api: APIConfigModel
    news_selection: NewsSelectionConfigModel
    crawler: CrawlerConfigModel
    scheduler: SchedulerConfigModel
    logging: LoggingConfigModel

    class Config:
        """Pydantic配置"""
        extra = "ignore"  # 忽略额外字段


def load_config(config_path: str = "config/config.yaml") -> AppConfigModel:
    """
    加载并验证配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        验证后的配置对象

    Raises:
        ValueError: 配置文件不存在或验证失败
        yaml.YAMLError: YAML解析失败
    """
    config_file = Path(config_path)

    if not config_file.exists():
        raise ValueError(f"配置文件不存在: {config_path}")

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)

        # 验证配置
        validated_config = AppConfigModel(**config_data)

        return validated_config

    except yaml.YAMLError as e:
        raise ValueError(f"YAML解析失败: {e}")
    except Exception as e:
        raise ValueError(f"配置验证失败: {e}")


def validate_config(config_dict: Dict[str, Any]) -> AppConfigModel:
    """
    验证配置字典

    Args:
        config_dict: 配置字典

    Returns:
        验证后的配置对象
    """
    return AppConfigModel(**config_dict)
