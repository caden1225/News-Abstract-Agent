"""
爬虫日志配置模块
控制台输出精简日志，详细日志写入文件
"""
import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime


def setup_crawler_logging(log_dir: str = "logs", log_file_prefix: str = "crawler"):
    """
    配置爬虫日志系统
    
    Args:
        log_dir: 日志文件目录，默认为 logs
        log_file_prefix: 日志文件前缀，默认为 crawler
    """
    # 确保日志目录存在
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # 创建日志文件名（带时间戳）
    timestamp = datetime.now().strftime("%Y%m%d")
    log_file = log_path / f"{log_file_prefix}_{timestamp}.log"
    
    # 获取爬虫相关的 logger
    crawler_logger = logging.getLogger('news_crawler')
    crawler_logger.setLevel(logging.DEBUG)
    
    # 清除已有的处理器（避免重复添加）
    crawler_logger.handlers.clear()
    
    # 控制台处理器 - 精简输出（只显示 INFO 及以上级别）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    
    # 文件处理器 - 详细输出（DEBUG 级别，完整格式）
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # 添加处理器
    crawler_logger.addHandler(console_handler)
    crawler_logger.addHandler(file_handler)
    
    # 设置子模块的日志级别
    logging.getLogger('news_crawler.crawlers').setLevel(logging.DEBUG)
    logging.getLogger('news_crawler.database').setLevel(logging.DEBUG)
    logging.getLogger('news_crawler.client').setLevel(logging.DEBUG)
    logging.getLogger('news_crawler.post_processor').setLevel(logging.DEBUG)
    
    return crawler_logger


def get_crawler_logger(name: str = None):
    """
    获取爬虫日志记录器
    
    Args:
        name: logger 名称，如果为 None 则使用调用模块的名称
        
    Returns:
        Logger 实例
    """
    if name is None:
        import inspect
        try:
            frame = inspect.currentframe().f_back
            name = frame.f_globals.get('__name__', 'news_crawler')
        except (AttributeError, KeyError):
            name = 'news_crawler'
    
    # 确保 logger 名称以 news_crawler 开头
    if not name.startswith('news_crawler'):
        # 如果已经是完整路径，直接使用；否则添加前缀
        if '.' in name:
            name = f'news_crawler.{name}'
        else:
            name = f'news_crawler.{name}' if name != 'news_crawler' else 'news_crawler'
    
    return logging.getLogger(name)

