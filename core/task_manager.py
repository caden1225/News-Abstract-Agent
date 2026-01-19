"""
全局任务管理器

管理异步任务的生命周期，替代全局字典，避免内存泄漏
"""
import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
from core.exceptions import NewsAgentError

logger = logging.getLogger(__name__)


class TaskExpiredError(NewsAgentError):
    """任务已过期异常"""

    def __init__(self, task_id: str):
        super().__init__(
            message=f"Task {task_id} has expired",
            code=408,
            details={"task_id": task_id}
        )


class LanguageTaskManager:
    """
    LLM语言判断任务管理器

    特性：
    1. 自动清理过期任务，防止内存泄漏
    2. 线程安全的任务存储
    3. 任务超时检测
    """

    def __init__(self, task_ttl: int = 300):
        """
        初始化任务管理器

        Args:
            task_ttl: 任务生存时间（秒），默认5分钟
        """
        self._tasks: Dict[str, Dict[str, any]] = {}
        self._lock = asyncio.Lock()
        self._task_ttl = task_ttl
        self._cleanup_task: Optional[asyncio.Task] = None

        logger.info(f"LanguageTaskManager 初始化完成: task_ttl={task_ttl}s")

    async def start_cleanup_task(self, interval: int = 60):
        """
        启动后台清理任务

        Args:
            interval: 清理间隔（秒），默认60秒
        """
        if self._cleanup_task is not None:
            logger.warning("清理任务已在运行")
            return

        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(interval)
                    await self.cleanup_expired_tasks()
                except asyncio.CancelledError:
                    logger.info("清理任务已取消")
                    break
                except Exception as e:
                    logger.error(f"清理任务出错: {e}", exc_info=True)

        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info(f"后台清理任务已启动: interval={interval}s")

    async def stop_cleanup_task(self):
        """停止后台清理任务"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("后台清理任务已停止")

    async def store_task(
        self,
        request_id: str,
        task: asyncio.Task,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        存储任务

        Args:
            request_id: 请求ID
            task: 异步任务对象
            metadata: 可选的元数据

        Returns:
            是否成功存储
        """
        async with self._lock:
            self._tasks[request_id] = {
                "task": task,
                "created_at": datetime.now(),
                "metadata": metadata or {}
            }
            logger.debug(f"存储任务: request_id={request_id}, total_tasks={len(self._tasks)}")
            return True

    async def get_task(self, request_id: str) -> Optional[asyncio.Task]:
        """
        获取任务

        Args:
            request_id: 请求ID

        Returns:
            任务对象，如果不存在或已过期返回None
        """
        async with self._lock:
            task_info = self._tasks.get(request_id)

            if task_info is None:
                logger.debug(f"任务不存在: request_id={request_id}")
                return None

            # 检查是否过期
            created_at = task_info["created_at"]
            if datetime.now() - created_at > timedelta(seconds=self._task_ttl):
                logger.warning(f"任务已过期: request_id={request_id}")
                # 移除过期任务
                del self._tasks[request_id]
                return None

            return task_info["task"]

    async def remove_task(self, request_id: str) -> bool:
        """
        移除任务

        Args:
            request_id: 请求ID

        Returns:
            是否成功移除
        """
        async with self._lock:
            if request_id in self._tasks:
                task = self._tasks[request_id]["task"]
                # 取消任务（如果还在运行）
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                del self._tasks[request_id]
                logger.debug(f"移除任务: request_id={request_id}, remaining={len(self._tasks)}")
                return True
            return False

    async def cleanup_expired_tasks(self) -> int:
        """
        清理过期任务

        Returns:
            清理的任务数量
        """
        async with self._lock:
            now = datetime.now()
            expired_keys = []

            for request_id, task_info in self._tasks.items():
                created_at = task_info["created_at"]
                if now - created_at > timedelta(seconds=self._task_ttl):
                    expired_keys.append(request_id)

            for request_id in expired_keys:
                task_info = self._tasks[request_id]
                task = task_info["task"]

                # 取消任务
                if not task.done():
                    task.cancel()

                del self._tasks[request_id]

            if expired_keys:
                logger.info(f"清理过期任务: count={len(expired_keys)}, remaining={len(self._tasks)}")

            return len(expired_keys)

    async def wait_for_task(
        self,
        request_id: str,
        timeout: Optional[float] = None
    ) -> any:
        """
        等待任务完成

        Args:
            request_id: 请求ID
            timeout: 超时时间（秒），None表示使用默认TTL

        Returns:
            任务结果

        Raises:
            TaskExpiredError: 任务不存在或已过期
            asyncio.TimeoutError: 任务超时
        """
        task = await self.get_task(request_id)

        if task is None:
            raise TaskExpiredError(request_id)

        timeout = timeout or self._task_ttl

        try:
            result = await asyncio.wait_for(task, timeout=timeout)
            # 任务完成后，自动移除
            await self.remove_task(request_id)
            return result
        except asyncio.TimeoutError:
            logger.error(f"任务超时: request_id={request_id}, timeout={timeout}s")
            await self.remove_task(request_id)
            raise

    @property
    def task_count(self) -> int:
        """当前任务数量"""
        return len(self._tasks)

    def get_task_info(self, request_id: str) -> Optional[Dict]:
        """
        获取任务信息（非线程安全，仅用于调试）

        Args:
            request_id: 请求ID

        Returns:
            任务信息字典，如果不存在返回None
        """
        if request_id in self._tasks:
            task_info = self._tasks[request_id]
            return {
                "created_at": task_info["created_at"].isoformat(),
                "done": task_info["task"].done(),
                "metadata": task_info["metadata"]
            }
        return None


# 全局单例
_language_task_manager: Optional[LanguageTaskManager] = None


def get_language_task_manager() -> LanguageTaskManager:
    """
    获取全局语言任务管理器实例

    Returns:
        LanguageTaskManager 实例
    """
    global _language_task_manager

    if _language_task_manager is None:
        _language_task_manager = LanguageTaskManager()

    return _language_task_manager
