"""
常量配置模块

集中管理所有硬编码的魔法数字和配置常量
"""
import os
from dataclasses import dataclass
from typing import Dict

# 加载 .env 文件（必须在读取环境变量之前）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # 如果 dotenv 未安装，跳过（环境变量可能已通过其他方式设置）
    pass


@dataclass
class LanguageConfig:
    """语言检测配置"""
    # 韩文字符检测阈值
    KOREAN_RATIO_THRESHOLD: float = 0.3
    KOREAN_CONFIDENCE: float = 0.9

    # 中文字符检测阈值
    CHINESE_RATIO_THRESHOLD: float = 0.3
    CHINESE_RATIO_LOW_THRESHOLD: float = 0.1
    CHINESE_CONFIDENCE_HIGH: float = 0.9
    CHINESE_CONFIDENCE_MEDIUM: float = 0.7
    CHINESE_CONFIDENCE_DEFAULT: float = 0.5

    # 英文字符检测阈值
    ENGLISH_RATIO_THRESHOLD: float = 0.5
    ENGLISH_CONFIDENCE: float = 0.8

    # 默认配置
    DEFAULT_LANGUAGE: str = "zh"
    DEFAULT_CONFIDENCE: float = 0.5


@dataclass
class TTSConfig:
    """TTS配置"""
    # 流式生成分块配置
    MIN_CHUNK_SIZE: int = 20
    CHUNK_DIVISOR: int = 10
    DEFAULT_CHUNK_COUNT: int = 10

    # 音频格式
    AUDIO_FORMAT: str = "pcm"
    AUDIO_SAMPLE_RATE: int = 24000
    AUDIO_CHANNELS: int = 1

    # 超时配置
    TTS_TIMEOUT: float = 30.0

    # 语言配置
    SUPPORTED_LANGUAGES: Dict[str, str] = None

    def __post_init__(self):
        if self.SUPPORTED_LANGUAGES is None:
            self.SUPPORTED_LANGUAGES = {
                "zh": "中文",
                "en": "英文",
                "ko": "韩语"
            }


@dataclass
class LLMConfig:
    """LLM配置"""
    # 意图分析配置
    INTENT_TEMPERATURE: float = 0.1
    INTENT_MAX_TOKENS: int = 500

    # 摘要生成配置
    SUMMARY_TEMPERATURE: float = 0.7
    SUMMARY_MAX_TOKENS: int = 2000

    # 重试配置
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0

    # 超时配置
    LLM_TIMEOUT: float = 30.0

    def __post_init__(self):
        """从配置文件读取 max_tokens 配置（如果存在）"""
        try:
            from llm_utils.config import config
            
            # 从配置文件读取 max_tokens 配置
            intent_max_tokens = config.get("llm.max_tokens.intent")
            if intent_max_tokens is not None:
                self.INTENT_MAX_TOKENS = int(intent_max_tokens)
            
            summary_max_tokens = config.get("llm.max_tokens.summary")
            if summary_max_tokens is not None:
                self.SUMMARY_MAX_TOKENS = int(summary_max_tokens)
        except Exception:
            # 如果配置文件读取失败，使用默认值
            pass


@dataclass
class DatabaseConfig:
    """数据库配置"""
    # 查询限制
    MAX_NEWS_PER_SOURCE: int = 10
    MAX_SELECTED_NEWS: int = 5
    MAX_IMAGES: int = 10
    KEYWORD_SEARCH_LIMIT: int = 50
    CACHE_NEWS_LIMIT: int = 50

    # 缓存配置
    DEFAULT_CACHE_TTL: int = 3600  # 1小时


@dataclass
class WorkflowConfig:
    """工作流配置"""
    # 规则分析置信度阈值
    RULE_CONFIDENCE_THRESHOLD: float = 0.8

    # LLM语言判断超时
    LLM_LANGUAGE_TIMEOUT: float = 5.0

    # 进度百分比配置
    PROGRESS_INTENT_ANALYSIS: int = 10
    PROGRESS_CACHE_QUERY: int = 20
    PROGRESS_DATA_FETCH: int = 30
    PROGRESS_NEWS_SELECTION: int = 50
    PROGRESS_SUMMARY_GENERATION: int = 70
    PROGRESS_TTS_GENERATION: int = 90
    PROGRESS_COMPLETE: int = 100


@dataclass
class StreamConfig:
    """流式输出配置"""
    # 文本chunk合并配置（从环境变量读取，支持.env文件）
    TEXT_CHUNK_MIN_SIZE: int = 15  # 最小累积字符数
    TEXT_CHUNK_MAX_SIZE: int = 80  # 最大累积字符数（超过则强制yield）
    TEXT_CHUNK_TIMEOUT: float = 0.3  # 最大等待时间（秒）
    TEXT_CHUNK_SENTENCE_ENDINGS: str = "。！？.!?；;"  # 句子结束标点

    def __post_init__(self):
        """从环境变量读取配置（支持.env文件）"""
        import logging
        logger = logging.getLogger(__name__)
        
        # 从环境变量读取配置，如果没有或为空则使用默认值
        min_size_env = os.getenv("TEXT_CHUNK_MIN_SIZE")
        if min_size_env and min_size_env.strip():
            try:
                self.TEXT_CHUNK_MIN_SIZE = int(min_size_env.strip())
                logger.debug(f"从环境变量读取 TEXT_CHUNK_MIN_SIZE={self.TEXT_CHUNK_MIN_SIZE}")
            except ValueError:
                logger.warning(f"环境变量 TEXT_CHUNK_MIN_SIZE 值无效: {min_size_env}，使用默认值 {self.TEXT_CHUNK_MIN_SIZE}")
        
        max_size_env = os.getenv("TEXT_CHUNK_MAX_SIZE")
        if max_size_env and max_size_env.strip():
            try:
                self.TEXT_CHUNK_MAX_SIZE = int(max_size_env.strip())
                logger.debug(f"从环境变量读取 TEXT_CHUNK_MAX_SIZE={self.TEXT_CHUNK_MAX_SIZE}")
            except ValueError:
                logger.warning(f"环境变量 TEXT_CHUNK_MAX_SIZE 值无效: {max_size_env}，使用默认值 {self.TEXT_CHUNK_MAX_SIZE}")
        
        timeout_env = os.getenv("TEXT_CHUNK_TIMEOUT")
        if timeout_env and timeout_env.strip():
            try:
                self.TEXT_CHUNK_TIMEOUT = float(timeout_env.strip())
                logger.debug(f"从环境变量读取 TEXT_CHUNK_TIMEOUT={self.TEXT_CHUNK_TIMEOUT}")
            except ValueError:
                logger.warning(f"环境变量 TEXT_CHUNK_TIMEOUT 值无效: {timeout_env}，使用默认值 {self.TEXT_CHUNK_TIMEOUT}")
        
        sentence_endings = os.getenv("TEXT_CHUNK_SENTENCE_ENDINGS")
        if sentence_endings and sentence_endings.strip():
            self.TEXT_CHUNK_SENTENCE_ENDINGS = sentence_endings.strip()
            logger.debug(f"从环境变量读取 TEXT_CHUNK_SENTENCE_ENDINGS={self.TEXT_CHUNK_SENTENCE_ENDINGS}")
        
        # 输出最终配置（用于调试）
        logger.info(
            f"流式输出配置已加载: "
            f"TEXT_CHUNK_MIN_SIZE={self.TEXT_CHUNK_MIN_SIZE}, "
            f"TEXT_CHUNK_MAX_SIZE={self.TEXT_CHUNK_MAX_SIZE}, "
            f"TEXT_CHUNK_TIMEOUT={self.TEXT_CHUNK_TIMEOUT}"
        )


# 导出实例
LANGUAGE_CONFIG = LanguageConfig()
TTS_CONFIG = TTSConfig()
LLM_CONFIG = LLMConfig()
DATABASE_CONFIG = DatabaseConfig()
WORKFLOW_CONFIG = WorkflowConfig()
STREAM_CONFIG = StreamConfig()
