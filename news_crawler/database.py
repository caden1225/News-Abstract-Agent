"""
爬虫数据库操作类
支持SQLite作为本地数据库
"""
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional
import json
from .post_processor import PostProcessor
from models.news import NewsItem

logger = logging.getLogger(__name__)


class Database:
    """数据库操作类（优化版：改进的连接池和健康检查）"""

    def __init__(self, db_path: str = "data/news.db", post_processor: Optional[PostProcessor] = None):
        self.db_path = db_path
        self.post_processor = post_processor
        # 优化：使用连接池（SQLite连接复用）
        self._connection_pool = None
        self._pool_lock = None
        self._connection_created_at = None
        self._max_connection_age = 3600  # 连接最大存活时间（秒），1小时后重新创建
        self.init_database()

    def get_connection(self):
        """
        获取数据库连接（优化版：带健康检查和连接老化管理）
        
        注意：SQLite是文件数据库，连接池主要是复用连接对象，减少创建开销
        """
        import threading
        import os
        from pathlib import Path
        from datetime import datetime, timedelta
        
        # 初始化连接池（延迟初始化）
        if self._connection_pool is None or self._pool_lock is None:
            try:
                # 确保数据库目录存在
                db_dir = Path(self.db_path).parent
                db_dir.mkdir(parents=True, exist_ok=True)
                
                self._connection_pool = self._create_connection()
                self._connection_created_at = datetime.now()
                self._pool_lock = threading.Lock()
            except sqlite3.OperationalError as e:
                self._handle_connection_error(e)
                raise
        
        # 优化：获取数据库连接（连接池模式 + 健康检查）
        with self._pool_lock:
            # 检查连接是否需要重新创建（连接老化）
            if self._connection_created_at:
                age = (datetime.now() - self._connection_created_at).total_seconds()
                if age > self._max_connection_age:
                    logger.info(f"连接已老化（{age:.0f}秒），重新创建连接")
                    try:
                        self._connection_pool.close()
                    except:
                        pass
                    self._connection_pool = None
                    self._connection_created_at = None
            
            # 如果连接池未初始化或已关闭，创建新连接
            if self._connection_pool is None:
                try:
                    self._connection_pool = self._create_connection()
                    self._connection_created_at = datetime.now()
                except sqlite3.OperationalError as e:
                    self._handle_connection_error(e)
                    raise
            
            # 健康检查：快速检查连接是否有效
            try:
                self._connection_pool.execute("SELECT 1").fetchone()
            except (sqlite3.OperationalError, sqlite3.ProgrammingError):
                # 连接已失效，重新创建
                logger.warning("检测到连接失效，重新创建连接")
                try:
                    self._connection_pool.close()
                except:
                    pass
                self._connection_pool = self._create_connection()
                self._connection_created_at = datetime.now()
            
            return self._connection_pool
    
    def _create_connection(self):
        """创建新的数据库连接"""
        from pathlib import Path
        
        # 确保数据库目录存在
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,  # 允许多线程使用
            timeout=10.0  # 设置超时
        )
        conn.row_factory = sqlite3.Row
        
        # 优化：启用WAL模式提高并发性能（如果失败则回退到DELETE模式）
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if journal_mode.upper() != 'WAL':
                logger.warning(f"WAL模式启用失败，当前模式: {journal_mode}，回退到DELETE模式")
                conn.execute("PRAGMA journal_mode=DELETE")
        except sqlite3.OperationalError as e:
            logger.warning(f"设置WAL模式失败: {e}，使用DELETE模式")
            try:
                conn.execute("PRAGMA journal_mode=DELETE")
            except:
                pass
        
        # 性能优化配置
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        conn.execute("PRAGMA temp_store=MEMORY")  # 临时表存储在内存中
        conn.execute("PRAGMA mmap_size=268435456")  # 256MB内存映射
        
        return conn
    
    def _handle_connection_error(self, e: sqlite3.OperationalError):
        """处理连接错误，提供详细的错误信息"""
        from pathlib import Path
        
        error_msg = str(e)
        if "disk I/O error" in error_msg.lower() or "database is locked" in error_msg.lower():
            # 检查数据库文件状态
            db_path_obj = Path(self.db_path)
            if db_path_obj.exists():
                file_size = db_path_obj.stat().st_size
                logger.error(f"数据库I/O错误: {error_msg}")
                logger.error(f"数据库文件: {self.db_path}")
                logger.error(f"文件大小: {file_size} 字节")
                logger.error("可能的原因:")
                logger.error("  1. 数据库文件被其他进程锁定")
                logger.error("  2. WAL文件损坏（尝试删除 .db-wal 和 .db-shm 文件）")
                logger.error("  3. 磁盘空间不足或权限问题")
            else:
                logger.error(f"数据库文件不存在: {self.db_path}")

    def init_database(self):
        """初始化数据库表"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # 创建新闻表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                source TEXT,
                source_site TEXT NOT NULL,
                category TEXT NOT NULL,
                tags TEXT,
                publish_time TIMESTAMP,
                image_urls TEXT,
                content TEXT,
                author TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 检查并添加新列（用于现有数据库升级）
        try:
            cursor.execute("ALTER TABLE news ADD COLUMN image_urls TEXT")
        except Exception:
            pass  # 列已存在
        try:
            cursor.execute("ALTER TABLE news ADD COLUMN tags TEXT")
        except Exception:
            pass  # 列已存在

        # 创建索引（优化：添加复合索引）
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_url ON news(url)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_category ON news(category)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tags ON news(tags)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_publish_time ON news(publish_time)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_source_site ON news(source_site)
        """)
        # 优化：添加复合索引以提高常用查询性能
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_news_publish_category 
            ON news(publish_time DESC, category, source_site)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_news_category_time 
            ON news(category, publish_time DESC)
        """)

        # 创建URL去重表（用于记录已抓取的URL）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crawled_urls (
                url TEXT PRIMARY KEY NOT NULL,
                crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source_site TEXT,
                category TEXT
            )
        """)
        
        # 创建索引以提高查询性能
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_crawled_urls_at ON crawled_urls(crawled_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_crawled_urls_site ON crawled_urls(source_site)
        """)

        # 创建播报记录表（存储已处理的新闻摘要和播报记录）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date DATE NOT NULL,
                summary TEXT NOT NULL,
                selected_news_ids TEXT NOT NULL,
                news_count INTEGER DEFAULT 0,
                language TEXT DEFAULT 'zh',
                processing_time_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_news_reports_date ON news_reports(report_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_news_reports_created_at ON news_reports(created_at)
        """)

        conn.commit()
        # 注意：不关闭连接，因为这是共享的连接池连接

    def insert_news(self, news: NewsItem) -> int:
        """插入单条新闻，返回插入的ID"""
        # 检查URL是否已抓取
        if self.is_url_crawled(news.url):
            return -1  # 已存在，不重复插入

        # 内容长度过滤：少于20个字的新闻不保存
        content_length = len(news.content) if news.content else 0
        if content_length < 20:
            logger.debug(f"内容长度不足20字，跳过保存: [{news.title}] ({content_length}字)")
            return -1

        # 应用后处理
        if self.post_processor:
            news = self.post_processor.process(news)
        
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # 将image_urls列表转换为JSON字符串
            image_urls_json = json.dumps(news.image_urls) if news.image_urls else None
            # 将tags列表转换为JSON字符串
            tags_json = json.dumps(news.tags) if news.tags else None
            
            # 使用本地时间（CST）而不是UTC时间
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 检查是否已存在（用于判断是INSERT还是REPLACE）
            cursor.execute("SELECT id, created_at FROM news WHERE url = ?", (news.url,))
            existing = cursor.fetchone()
            
            if existing:
                # 更新已存在的记录，保持原created_at，更新updated_at
                cursor.execute("""
                    UPDATE news SET
                        title = ?, source = ?, source_site = ?, category = ?, tags = ?,
                        publish_time = ?, image_urls = ?, content = ?, author = ?,
                        updated_at = ?
                    WHERE url = ?
                """, (
                    news.title,
                    news.source,
                    news.source_site,
                    news.category,
                    tags_json,
                    news.publish_time.isoformat() if news.publish_time else None,
                    image_urls_json,
                    news.content,
                    news.author,
                    now,
                    news.url
                ))
                news_id = existing[0]
            else:
                # 插入新记录，设置created_at和updated_at
                cursor.execute("""
                    INSERT INTO news
                    (title, url, source, source_site, category, tags, publish_time, image_urls, content, author, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    news.title,
                    news.url,
                    news.source,
                    news.source_site,
                    news.category,
                    tags_json,
                    news.publish_time.isoformat() if news.publish_time else None,
                    image_urls_json,
                    news.content,
                    news.author,
                    now,
                    now
                ))
                news_id = cursor.lastrowid

            conn.commit()
            news_id = cursor.lastrowid
            
            # 标记URL为已抓取
            self.mark_url_crawled(news.url, news.source_site, news.category)
            
            return news_id
        except sqlite3.Error as e:
            print(f"插入数据失败: {e}")
            return -1
        # 注意：不关闭连接，因为这是共享的连接池连接

    def insert_news_batch(self, news_list: List[NewsItem]) -> int:
        """批量插入新闻，返回成功插入的数量"""
        if not news_list:
            return 0

        # 内容长度过滤：少于20个字的新闻不保存
        filtered_list = []
        filtered_count = 0
        for news in news_list:
            content_length = len(news.content) if news.content else 0
            if content_length >= 20:
                filtered_list.append(news)
            else:
                filtered_count += 1
                logger.debug(f"内容长度不足20字，跳过保存: [{news.title}] ({content_length}字)")

        if filtered_count > 0:
            logger.info(f"内容长度过滤：跳过了 {filtered_count} 条短内容新闻")

        if not filtered_list:
            return 0

        # 过滤掉已抓取的URL
        urls = [news.url for news in filtered_list]
        new_urls = self.filter_crawled_urls(urls)
        
        if not new_urls:
            return 0  # 所有URL都已抓取过

        # 只处理未抓取的新闻
        news_to_insert = [news for news in filtered_list if news.url in new_urls]
        
        if not news_to_insert:
            return 0
        
        # 应用后处理
        if self.post_processor:
            news_to_insert = self.post_processor.process_batch(news_to_insert)

        conn = self.get_connection()
        cursor = conn.cursor()
        success_count = 0
        inserted_urls = []

        try:
            # 使用本地时间（CST）而不是UTC时间
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            for news in news_to_insert:
                try:
                    # 将image_urls列表转换为JSON字符串
                    image_urls_json = json.dumps(news.image_urls) if news.image_urls else None
                    # 将tags列表转换为JSON字符串
                    tags_json = json.dumps(news.tags) if news.tags else None
                    
                    # 检查是否已存在
                    cursor.execute("SELECT id, created_at FROM news WHERE url = ?", (news.url,))
                    existing = cursor.fetchone()
                    
                    if existing:
                        # 更新已存在的记录
                        cursor.execute("""
                            UPDATE news SET
                                title = ?, source = ?, source_site = ?, category = ?, tags = ?,
                                publish_time = ?, image_urls = ?, content = ?, author = ?,
                                updated_at = ?
                            WHERE url = ?
                        """, (
                            news.title,
                            news.source,
                            news.source_site,
                            news.category,
                            tags_json,
                            news.publish_time.isoformat() if news.publish_time else None,
                            image_urls_json,
                            news.content,
                            news.author,
                            now,
                            news.url
                        ))
                    else:
                        # 插入新记录
                        cursor.execute("""
                            INSERT INTO news
                            (title, url, source, source_site, category, tags, publish_time, image_urls, content, author, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            news.title,
                            news.url,
                            news.source,
                            news.source_site,
                            news.category,
                            tags_json,
                            news.publish_time.isoformat() if news.publish_time else None,
                            image_urls_json,
                            news.content,
                            news.author,
                            now,
                            now
                        ))
                    success_count += 1
                    inserted_urls.append((news.url, news.source_site, news.category))
                except sqlite3.Error as e:
                    print(f"插入新闻失败 [{news.title}]: {e}")

            conn.commit()
            
            # 批量标记URL为已抓取
            if inserted_urls:
                self.mark_urls_crawled([url for url, _, _ in inserted_urls])
        except sqlite3.Error as e:
            print(f"批量插入失败: {e}")
        # 注意：不关闭连接，因为这是共享的连接池连接

        return success_count

    def get_news_by_category(self, category: str, limit: int = 15) -> List[NewsItem]:
        """根据分类获取新闻"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM news
            WHERE category = ?
            ORDER BY publish_time DESC, created_at DESC
            LIMIT ?
        """, (category, limit))

        rows = cursor.fetchall()
        # 注意：不关闭连接，因为这是共享的连接池连接

        return [self._row_to_news(row) for row in rows]

    def get_latest_news(self, limit: int = 30) -> List[NewsItem]:
        """获取最新新闻"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM news
            ORDER BY publish_time DESC, created_at DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        # 注意：不关闭连接，因为这是共享的连接池连接

        return [self._row_to_news(row) for row in rows]

    def get_hot_news(self, limit: int = 15) -> List[NewsItem]:
        """获取实时热榜新闻"""
        return self.get_news_by_category("hot_news", limit)

    def get_today_focus(self, limit: int = 15) -> List[NewsItem]:
        """获取今日关注新闻"""
        return self.get_news_by_category("today_focus", limit)

    def search_news(self, keyword: str, limit: int = 50) -> List[NewsItem]:
        """
        搜索新闻（优化：使用索引优化查询）
        
        注意：对于大量数据，考虑使用全文索引（FTS5）以获得更好性能
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # 优化：使用索引优化的查询
        # 先搜索标题（通常更快），再搜索内容
        cursor.execute("""
            SELECT * FROM news
            WHERE title LIKE ? OR content LIKE ?
            ORDER BY publish_time DESC
            LIMIT ?
        """, (f"%{keyword}%", f"%{keyword}%", limit))

        rows = cursor.fetchall()
        # 注意：不关闭连接，因为这是共享的连接池连接

        return [self._row_to_news(row) for row in rows]

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        conn = self.get_connection()
        cursor = conn.cursor()

        stats = {}

        # 总新闻数
        cursor.execute("SELECT COUNT(*) as total FROM news")
        stats['total'] = cursor.fetchone()['total']

        # 按分类统计
        cursor.execute("""
            SELECT category, COUNT(*) as count
            FROM news
            GROUP BY category
        """)
        stats['by_category'] = {row['category']: row['count'] for row in cursor.fetchall()}

        # 按来源站点统计
        cursor.execute("""
            SELECT source_site, COUNT(*) as count
            FROM news
            GROUP BY source_site
        """)
        stats['by_source'] = {row['source_site']: row['count'] for row in cursor.fetchall()}

        # 最新更新时间
        cursor.execute("SELECT MAX(created_at) as latest FROM news")
        stats['latest_update'] = cursor.fetchone()['latest']

        # 注意：不关闭连接，因为这是共享的连接池连接
        return stats

    def _row_to_news(self, row: sqlite3.Row) -> NewsItem:
        """将数据库行转换为NewsItem对象"""
        # 解析image_urls JSON字符串为列表
        image_urls = None
        image_urls_json = row['image_urls'] if 'image_urls' in row.keys() else None
        if image_urls_json:
            try:
                image_urls = json.loads(image_urls_json)
            except Exception:
                image_urls = None

        # 解析tags JSON字符串为列表
        tags = None
        tags_json = row['tags'] if 'tags' in row.keys() else None
        if tags_json:
            try:
                tags = json.loads(tags_json)
            except Exception:
                tags = None

        return NewsItem(
            id=row['id'],
            title=row['title'],
            url=row['url'],
            source=row['source'],
            source_site=row['source_site'],
            category=row['category'],
            tags=tags,
            publish_time=datetime.fromisoformat(row['publish_time']) if row['publish_time'] else None,
            image_urls=image_urls,
            content=row['content'],
            author=row['author'],
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
        )

    def clear_old_news(self, days: int = 7):
        """
        清理旧新闻
        
        同时清理对应的 crawled_urls 记录，确保一致性
        
        Args:
            days: 清理多少天前的新闻
            
        Returns:
            删除的新闻数量
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # 先获取要删除的新闻的 URL 列表
        cursor.execute("""
            SELECT url FROM news
            WHERE datetime(publish_time) < datetime('now', '-' || ? || ' days')
        """, (days,))
        urls_to_delete = [row[0] for row in cursor.fetchall()]
        
        # 删除旧新闻
        cursor.execute("""
            DELETE FROM news
            WHERE datetime(publish_time) < datetime('now', '-' || ? || ' days')
        """, (days,))
        
        deleted_count = cursor.rowcount
        
        # 同时清理对应的 crawled_urls 记录
        if urls_to_delete:
            placeholders = ','.join('?' * len(urls_to_delete))
            cursor.execute(f"""
                DELETE FROM crawled_urls
                WHERE url IN ({placeholders})
            """, urls_to_delete)
            logger.info("清理了 %d 条对应的 crawled_urls 记录", cursor.rowcount)
        
        conn.commit()
        # 注意：不关闭连接，因为这是共享的连接池连接
        return deleted_count
    
    def clear_all_news(self) -> int:
        """
        清除所有新闻数据
        
        Returns:
            删除的新闻数量
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 获取删除前的数量
        cursor.execute("SELECT COUNT(*) FROM news")
        count_before = cursor.fetchone()[0]
        
        # 删除所有新闻
        cursor.execute("DELETE FROM news")
        
        # 同时清理URL记录（可选，但建议清理以保持一致性）
        cursor.execute("DELETE FROM crawled_urls")
        
        deleted_count = cursor.rowcount if cursor.rowcount > 0 else count_before
        conn.commit()
        
        # 注意：不关闭连接，因为这是共享的连接池连接
        return deleted_count

    def is_url_crawled(self, url: str) -> bool:
        """检查URL是否已被抓取过"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM crawled_urls WHERE url = ?", (url,))
        result = cursor.fetchone()
        # 注意：不关闭连接，因为这是共享的连接池连接
        return result is not None
    
    def mark_url_crawled(self, url: str, source_site: str = None, category: str = None):
        """标记URL为已抓取"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 使用本地时间（CST）而不是UTC时间
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
                INSERT OR REPLACE INTO crawled_urls (url, source_site, category, crawled_at)
                VALUES (?, ?, ?, ?)
            """, (url, source_site, category, now))
            conn.commit()
        except sqlite3.Error as e:
            print(f"标记URL失败 [{url}]: {e}")
        # 注意：不关闭连接，因为这是共享的连接池连接
    
    def mark_urls_crawled(self, urls: List[str], source_site: str = None, category: str = None):
        """批量标记URL为已抓取"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 使用本地时间（CST）而不是UTC时间
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for url in urls:
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO crawled_urls (url, source_site, category, crawled_at)
                    VALUES (?, ?, ?, ?)
                """, (url, source_site, category, now))
            except sqlite3.Error as e:
                print(f"标记URL失败 [{url}]: {e}")
        
        conn.commit()
        # 注意：不关闭连接，因为这是共享的连接池连接
    
    def filter_crawled_urls(self, urls: List[str]) -> List[str]:
        """过滤掉已抓取的URL，返回未抓取的URL列表"""
        if not urls:
            return []
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 使用IN查询批量检查
        placeholders = ','.join('?' * len(urls))
        cursor.execute(f"""
            SELECT url FROM crawled_urls 
            WHERE url IN ({placeholders})
        """, urls)
        
        crawled_urls = {row[0] for row in cursor.fetchall()}
        # 注意：不关闭连接，因为这是共享的连接池连接
        return [url for url in urls if url not in crawled_urls]
    
    def get_crawled_urls_count(self) -> int:
        """获取已抓取的URL总数"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM crawled_urls")
        # 注意：不关闭连接，因为这是共享的连接池连接
        return cursor.fetchone()[0]
    
    def clear_old_crawled_urls(self, days: int = 30):
        """清理N天前的URL记录（可选，用于节省空间）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM crawled_urls
            WHERE datetime(crawled_at) < datetime('now', '-' || ? || ' days')
        """, (days,))
        
        deleted_count = cursor.rowcount
        conn.commit()
        # 注意：不关闭连接，因为这是共享的连接池连接
        return deleted_count
    
    def get_statistics_with_urls(self) -> Dict:
        """获取统计信息（包含URL去重统计）"""
        stats = self.get_statistics()
        
        # 添加URL去重统计
        stats['crawled_urls_count'] = self.get_crawled_urls_count()
        stats['news_count'] = stats.get('total', 0)
        
        return stats

    def save_report(
        self,
        summary: str,
        selected_news_ids: List[int],
        language: str = "zh",
        processing_time_ms: int = 0
    ) -> int:
        """
        保存播报记录到 news_reports 表
        
        Args:
            summary: 生成的摘要/播报稿
            selected_news_ids: 本次播报包含的新闻ID列表
            language: 播报语言，默认 'zh'
            processing_time_ms: 处理耗时（毫秒）
            
        Returns:
            插入的记录ID
        """
        from datetime import date
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            today = date.today().isoformat()
            selected_ids_json = json.dumps(selected_news_ids)
            news_count = len(selected_news_ids)
            # 使用本地时间（CST）而不是UTC时间
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute("""
                INSERT INTO news_reports
                (report_date, summary, selected_news_ids, news_count, language, processing_time_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (today, summary, selected_ids_json, news_count, language, processing_time_ms, now))
            
            conn.commit()
            report_id = cursor.lastrowid
            return report_id
        except sqlite3.Error as e:
            logger.error(f"保存播报记录失败: {e}")
            return -1
        # 注意：不关闭连接，因为这是共享的连接池连接

    def get_reports_by_date(self, target_date: str) -> List[Dict]:
        """
        获取指定日期的播报记录
        
        Args:
            target_date: 目标日期（YYYY-MM-DD格式）
            
        Returns:
            播报记录列表
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM news_reports
            WHERE report_date = ?
            ORDER BY created_at DESC
        """, (target_date,))
        
        rows = cursor.fetchall()
        # 注意：不关闭连接，因为这是共享的连接池连接
        return [dict(row) for row in rows]

