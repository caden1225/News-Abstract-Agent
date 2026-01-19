#!/usr/bin/env python3
"""
性能测试脚本
测试优化后的性能提升
"""
import sys
import time
import asyncio
import statistics
from pathlib import Path
from typing import List, Dict
import sqlite3
import tempfile
import os

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class PerformanceTester:
    """性能测试器"""
    
    def __init__(self):
        self.results: Dict[str, List[float]] = {}
    
    def print_header(self, title: str):
        """打印标题"""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70)
    
    def test_database_query_performance(self):
        """测试数据库查询性能"""
        self.print_header("数据库查询性能测试")
        
        try:
            from news_crawler.database import Database
            from models.news import NewsItem
            from datetime import datetime, timedelta
            
            # 创建临时数据库
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
                db_path = f.name
            
            try:
                db = Database(db_path=db_path)
                
                # 插入测试数据
                print("插入测试数据...")
                test_news = []
                for i in range(100):
                    news = NewsItem(
                        title=f"测试新闻 {i}",
                        url=f"https://example.com/news/{i}",
                        source="测试来源",
                        source_site="test",
                        category="hot_news" if i % 2 == 0 else "today_focus",
                        content="这是一条测试新闻内容，长度超过20字以满足要求。" * 5,
                        publish_time=datetime.now() - timedelta(days=i % 7)
                    )
                    test_news.append(news)
                
                db.insert_news_batch(test_news)
                print(f"已插入 {len(test_news)} 条测试数据")
                
                # 测试查询性能（多次运行取平均值）
                query_times: List[float] = []
                iterations = 10
                
                print(f"\n执行 {iterations} 次查询测试...")
                for i in range(iterations):
                    start = time.time()
                    news_list = db.get_news_by_category("hot_news", limit=50)
                    elapsed = time.time() - start
                    query_times.append(elapsed)
                    print(f"  查询 {i+1}: {elapsed*1000:.2f}ms, 结果数: {len(news_list)}")
                
                avg_time = statistics.mean(query_times)
                min_time = min(query_times)
                max_time = max(query_times)
                std_dev = statistics.stdev(query_times) if len(query_times) > 1 else 0
                
                print(f"\n查询性能统计:")
                print(f"  平均时间: {avg_time*1000:.2f}ms")
                print(f"  最小时间: {min_time*1000:.2f}ms")
                print(f"  最大时间: {max_time*1000:.2f}ms")
                print(f"  标准差: {std_dev*1000:.2f}ms")
                
                self.results["database_query"] = query_times
                
                # 检查索引
                conn = db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='index' AND name LIKE 'idx_news%'
                """)
                indexes = [row[0] for row in cursor.fetchall()]
                
                print(f"\n索引检查:")
                print(f"  找到索引: {len(indexes)} 个")
                for idx in indexes:
                    print(f"    - {idx}")
                
                if avg_time < 0.1:  # 100ms以内认为性能良好
                    print(f"\n✅ 数据库查询性能良好（平均 {avg_time*1000:.2f}ms）")
                else:
                    print(f"\n⚠️  数据库查询性能可能需要优化（平均 {avg_time*1000:.2f}ms）")
                
            finally:
                # 清理
                try:
                    os.unlink(db_path)
                except:
                    pass
        except Exception as e:
            print(f"❌ 数据库性能测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def test_connection_pool_performance(self):
        """测试连接池性能"""
        self.print_header("连接池性能测试")
        
        try:
            from news_crawler.database import Database
            import tempfile
            
            # 创建临时数据库
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
                db_path = f.name
            
            try:
                db = Database(db_path=db_path)
                
                # 测试连接获取性能
                connection_times: List[float] = []
                iterations = 100
                
                print(f"执行 {iterations} 次连接获取测试...")
                for i in range(iterations):
                    start = time.time()
                    conn = db.get_connection()
                    conn.execute("SELECT 1").fetchone()
                    elapsed = time.time() - start
                    connection_times.append(elapsed)
                
                avg_time = statistics.mean(connection_times)
                min_time = min(connection_times)
                max_time = max(connection_times)
                
                print(f"\n连接获取性能统计:")
                print(f"  平均时间: {avg_time*1000:.3f}ms")
                print(f"  最小时间: {min_time*1000:.3f}ms")
                print(f"  最大时间: {max_time*1000:.3f}ms")
                
                self.results["connection_pool"] = connection_times
                
                # 检查连接复用（应该返回同一个连接）
                conn1 = db.get_connection()
                conn2 = db.get_connection()
                
                if conn1 is conn2:
                    print(f"\n✅ 连接池正常工作（连接复用）")
                else:
                    print(f"\n⚠️  连接池可能未正常工作（未复用连接）")
                
            finally:
                # 清理
                try:
                    os.unlink(db_path)
                except:
                    pass
        except Exception as e:
            print(f"❌ 连接池性能测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_retry_mechanism_performance(self):
        """测试重试机制性能"""
        self.print_header("重试机制性能测试")
        
        try:
            from core.retry import retry_async, RetryConfig
            
            # 测试重试机制的开销
            @retry_async(RetryConfig(max_attempts=3, initial_delay=0.01), "测试")
            async def test_func():
                await asyncio.sleep(0.001)
                return "success"
            
            retry_times: List[float] = []
            iterations = 50
            
            print(f"执行 {iterations} 次重试机制测试...")
            for i in range(iterations):
                start = time.time()
                await test_func()
                elapsed = time.time() - start
                retry_times.append(elapsed)
            
            avg_time = statistics.mean(retry_times)
            
            print(f"\n重试机制性能统计:")
            print(f"  平均时间: {avg_time*1000:.3f}ms")
            
            self.results["retry_mechanism"] = retry_times
            
            if avg_time < 0.01:  # 10ms以内认为开销很小
                print(f"\n✅ 重试机制开销很小（平均 {avg_time*1000:.3f}ms）")
            else:
                print(f"\n⚠️  重试机制可能有较大开销（平均 {avg_time*1000:.3f}ms）")
        except Exception as e:
            print(f"❌ 重试机制性能测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def run_all_tests(self):
        """运行所有性能测试"""
        print("\n" + "=" * 70)
        print("  性能测试")
        print("=" * 70)
        
        self.test_database_query_performance()
        self.test_connection_pool_performance()
        asyncio.run(self.test_retry_mechanism_performance())
        
        self.print_summary()
    
    def print_summary(self):
        """打印性能测试总结"""
        self.print_header("性能测试总结")
        
        if self.results:
            print("性能指标:")
            for test_name, times in self.results.items():
                if times:
                    avg = statistics.mean(times)
                    print(f"  {test_name}:")
                    print(f"    平均: {avg*1000:.3f}ms")
                    print(f"    最小: {min(times)*1000:.3f}ms")
                    print(f"    最大: {max(times)*1000:.3f}ms")
        
        print("\n" + "=" * 70)
        print("性能测试完成！")


def main():
    """主函数"""
    tester = PerformanceTester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()
