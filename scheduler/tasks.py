"""
新闻定时任务调度器
基于 APScheduler 实现
"""
import os
import logging
from datetime import datetime
from typing import Optional, Callable, List, Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor

logger = logging.getLogger(__name__)


class NewsScheduler:
    """
    新闻爬取定时调度器
    
    支持功能：
    - 定时爬取新闻
    - 定时同步数据
    - 定时清理旧数据
    - 任务持久化（可选）
    
    使用示例：
    ```python
    scheduler = NewsScheduler()
    
    # 添加定时爬取任务（每小时执行）
    scheduler.add_crawl_job(interval_hours=1)
    
    # 添加 cron 任务（每天早上 8 点）
    scheduler.add_cron_job(
        job_func=my_func,
        job_id="daily_sync",
        hour=8, minute=0
    )
    
    # 启动调度器
    scheduler.start()
    ```
    """
    
    def __init__(
        self,
        use_async: bool = True,
        max_workers: int = 4,
        timezone: str = "Asia/Shanghai",
        persist_jobs: bool = True,
        jobs_db_path: str = "data/scheduler_jobs.db"
    ):
        """
        初始化调度器
        
        Args:
            use_async: 是否使用异步调度器（推荐 True）
            max_workers: 最大工作线程数
            timezone: 时区设置
            persist_jobs: 是否持久化任务（重启后不丢失）
            jobs_db_path: 任务持久化数据库路径
        """
        self.use_async = use_async
        self.timezone = timezone
        self.persist_jobs = persist_jobs
        self._scheduler: Optional[AsyncIOScheduler | BackgroundScheduler] = None
        self._jobs: Dict[str, Dict[str, Any]] = {}
        
        # 配置 job stores
        if persist_jobs:
            try:
                from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
                from pathlib import Path
                
                # 确保目录存在
                db_path = Path(jobs_db_path)
                db_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 使用 SQLite 持久化任务
                jobstores = {
                    'default': SQLAlchemyJobStore(url=f'sqlite:///{jobs_db_path}')
                }
                logger.info(f"使用任务持久化: {jobs_db_path}")
            except ImportError:
                logger.warning("SQLAlchemy 未安装，使用内存存储（任务不会持久化）")
                jobstores = {
                    'default': MemoryJobStore()
                }
        else:
            jobstores = {
                'default': MemoryJobStore()
            }
        
        executors = {
            'default': ThreadPoolExecutor(max_workers),
            'processpool': ProcessPoolExecutor(max_workers // 2 or 1)
        }
        
        job_defaults = {
            'coalesce': True,  # 合并错过的任务
            'max_instances': 1,  # 同一任务最大并发数
            'misfire_grace_time': 60 * 5  # 5分钟容错
        }
        
        # 创建调度器
        if use_async:
            self._scheduler = AsyncIOScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
                timezone=timezone
            )
        else:
            self._scheduler = BackgroundScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
                timezone=timezone
            )
        
        logger.info(f"NewsScheduler 初始化完成 (async={use_async}, timezone={timezone}, persist={persist_jobs})")
    
    def add_interval_job(
        self,
        job_func: Callable,
        job_id: str,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        start_now: bool = False,
        **kwargs
    ) -> str:
        """
        添加间隔执行的任务
        
        Args:
            job_func: 要执行的函数
            job_id: 任务唯一ID
            hours: 间隔小时数
            minutes: 间隔分钟数
            seconds: 间隔秒数
            start_now: 是否立即执行一次
            **kwargs: 传递给 job_func 的参数
            
        Returns:
            任务ID
        """
        if not any([hours, minutes, seconds]):
            raise ValueError("至少指定一个时间间隔参数")
        
        trigger = IntervalTrigger(
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            timezone=self.timezone
        )
        
        job = self._scheduler.add_job(
            job_func,
            trigger=trigger,
            id=job_id,
            name=f"interval_{job_id}",
            kwargs=kwargs,
            replace_existing=True
        )
        
        self._jobs[job_id] = {
            "type": "interval",
            "hours": hours,
            "minutes": minutes,
            "seconds": seconds,
            "func": job_func.__name__,
            "added_at": datetime.now().isoformat()
        }
        
        logger.info(f"添加间隔任务: {job_id} (every {hours}h {minutes}m {seconds}s)")
        
        # 立即执行一次
        if start_now:
            self._scheduler.add_job(
                job_func,
                id=f"{job_id}_immediate",
                kwargs=kwargs,
                replace_existing=True
            )
            logger.info(f"任务 {job_id} 立即执行一次")
        
        return job_id
    
    def add_cron_job(
        self,
        job_func: Callable,
        job_id: str,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
        day_of_week: str = "*",
        **kwargs
    ) -> str:
        """
        添加 Cron 定时任务
        
        Args:
            job_func: 要执行的函数
            job_id: 任务唯一ID
            hour: 小时 (0-23)
            minute: 分钟 (0-59)
            second: 秒 (0-59)
            day_of_week: 星期几 (0-6 或 mon-sun)
            **kwargs: 传递给 job_func 的参数
            
        Returns:
            任务ID
        """
        trigger = CronTrigger(
            hour=hour,
            minute=minute,
            second=second,
            day_of_week=day_of_week,
            timezone=self.timezone
        )
        
        job = self._scheduler.add_job(
            job_func,
            trigger=trigger,
            id=job_id,
            name=f"cron_{job_id}",
            kwargs=kwargs,
            replace_existing=True
        )
        
        self._jobs[job_id] = {
            "type": "cron",
            "hour": hour,
            "minute": minute,
            "second": second,
            "day_of_week": day_of_week,
            "func": job_func.__name__,
            "added_at": datetime.now().isoformat()
        }
        
        logger.info(f"添加 Cron 任务: {job_id} (at {hour}:{minute}:{second}, days={day_of_week})")
        
        return job_id
    
    def remove_job(self, job_id: str) -> bool:
        """
        移除任务
        
        Args:
            job_id: 任务ID
            
        Returns:
            是否成功移除
        """
        try:
            self._scheduler.remove_job(job_id)
            self._jobs.pop(job_id, None)
            logger.info(f"移除任务: {job_id}")
            return True
        except Exception as e:
            logger.warning(f"移除任务失败: {job_id}, error={e}")
            return False
    
    def pause_job(self, job_id: str) -> bool:
        """暂停任务"""
        try:
            self._scheduler.pause_job(job_id)
            logger.info(f"暂停任务: {job_id}")
            return True
        except Exception as e:
            logger.warning(f"暂停任务失败: {job_id}, error={e}")
            return False
    
    def resume_job(self, job_id: str) -> bool:
        """恢复任务"""
        try:
            self._scheduler.resume_job(job_id)
            logger.info(f"恢复任务: {job_id}")
            return True
        except Exception as e:
            logger.warning(f"恢复任务失败: {job_id}, error={e}")
            return False
    
    def get_jobs(self) -> List[Dict[str, Any]]:
        """获取所有任务信息"""
        jobs = []
        for job in self._scheduler.get_jobs():
            next_run = None
            try:
                if hasattr(job, 'next_run_time') and job.next_run_time:
                    next_run = job.next_run_time.isoformat() if hasattr(job.next_run_time, 'isoformat') else str(job.next_run_time)
            except:
                pass
            
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": next_run,
                "pending": getattr(job, 'pending', False)
            })
        return jobs
    
    def get_job_info(self, job_id: str) -> Optional[Dict[str, Any]]:
        """获取指定任务信息"""
        job = self._scheduler.get_job(job_id)
        if job:
            next_run = None
            try:
                if hasattr(job, 'next_run_time') and job.next_run_time:
                    next_run = job.next_run_time.isoformat() if hasattr(job.next_run_time, 'isoformat') else str(job.next_run_time)
            except:
                pass
            
            return {
                "id": job.id,
                "name": job.name,
                "next_run_time": next_run,
                "config": self._jobs.get(job_id, {})
            }
        return None
    
    def start(self):
        """启动调度器"""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("✅ NewsScheduler 已启动")
    
    def shutdown(self, wait: bool = True):
        """
        关闭调度器
        
        Args:
            wait: 是否等待任务完成
        """
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("✅ NewsScheduler 已关闭")
    
    @property
    def running(self) -> bool:
        """调度器是否正在运行"""
        return self._scheduler.running if self._scheduler else False
    
    # ==================== 便捷方法 ====================
    
    def add_crawl_job(
        self,
        interval_hours: int = 1,
        start_now: bool = False,
        crawler_config: Optional[Dict] = None
    ) -> str:
        """
        添加定时爬取新闻任务（便捷方法）
        
        Args:
            interval_hours: 爬取间隔（小时）
            start_now: 是否立即执行一次
            crawler_config: 爬虫配置
            
        Returns:
            任务ID
        """
        from scheduler.jobs import crawl_news_job
        
        return self.add_interval_job(
            job_func=crawl_news_job,
            job_id="crawl_news",
            hours=interval_hours,
            start_now=start_now,
            config=crawler_config or {}
        )
    
    def add_sync_job(
        self,
        interval_minutes: int = 30,
        start_now: bool = False
    ) -> str:
        """
        添加定时同步任务（便捷方法）
        
        Args:
            interval_minutes: 同步间隔（分钟）
            start_now: 是否立即执行一次
            
        Returns:
            任务ID
        """
        from scheduler.jobs import sync_news_job
        
        return self.add_interval_job(
            job_func=sync_news_job,
            job_id="sync_news",
            minutes=interval_minutes,
            start_now=start_now
        )
    
    def add_cleanup_job(
        self,
        hour: int = 3,
        minute: int = 0,
        days_to_keep: int = 30
    ) -> str:
        """
        添加定时清理任务（每天凌晨执行）
        
        Args:
            hour: 执行小时
            minute: 执行分钟
            days_to_keep: 保留天数
            
        Returns:
            任务ID
        """
        from scheduler.jobs import cleanup_old_news_job
        
        return self.add_cron_job(
            job_func=cleanup_old_news_job,
            job_id="cleanup_news",
            hour=hour,
            minute=minute,
            days_to_keep=days_to_keep
        )
    
    def add_daily_crawl_job(
        self,
        hour: int = 8,
        minute: int = 0,
        days_to_keep: int = 7,
        clear_before_crawl: bool = False
    ) -> str:
        """
        添加每日定时爬取任务（推荐使用）
        
        每天指定时间执行，爬取新新闻并清理旧数据
        
        Args:
            hour: 执行小时 (0-23)，默认8点
            minute: 执行分钟 (0-59)，默认0分
            days_to_keep: 保留天数，默认7天
            clear_before_crawl: 是否在爬取前清理，默认False（爬取后清理）
            
        Returns:
            任务ID
        """
        from scheduler.jobs import crawl_and_refresh_job
        
        # 通过 config 参数传递配置
        config = {
            "days_to_keep": days_to_keep,
            "clear_before_crawl": clear_before_crawl
        }
        
        return self.add_cron_job(
            job_func=crawl_and_refresh_job,
            job_id="daily_crawl_and_refresh",
            hour=hour,
            minute=minute,
            config=config
        )
    
    def add_weekly_clear_job(
        self,
        day_of_week: str = "sun",  # 0-6 或 mon-sun
        hour: int = 21,
        minute: int = 0
    ) -> str:
        """
        添加每周清除所有数据任务
        
        每周指定时间执行，清除数据库中的所有新闻数据
        
        Args:
            day_of_week: 星期几 (0-6 或 mon-sun)，默认 "sun"（周日）
            hour: 执行小时 (0-23)，默认21点（晚上9点）
            minute: 执行分钟 (0-59)，默认0分
            
        Returns:
            任务ID
        """
        from scheduler.jobs import clear_all_news_job
        
        return self.add_cron_job(
            job_func=clear_all_news_job,
            job_id="weekly_clear_all_news",
            hour=hour,
            minute=minute,
            day_of_week=day_of_week
        )

