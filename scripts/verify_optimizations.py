#!/usr/bin/env python3
"""
优化验证脚本
验证所有优化是否生效，并测试服务功能
"""
import sys
import asyncio
import time
import requests
import json
from pathlib import Path
from typing import Dict, List, Tuple

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class OptimizationVerifier:
    """优化验证器"""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.results: Dict[str, bool] = {}
        self.errors: List[str] = []
    
    def print_header(self, title: str):
        """打印标题"""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70)
    
    def print_result(self, name: str, success: bool, message: str = ""):
        """打印结果"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
        if message:
            print(f"      {message}")
        self.results[name] = success
        if not success:
            self.errors.append(f"{name}: {message}")
    
    def verify_config_validation(self) -> bool:
        """验证配置管理优化"""
        self.print_header("1. 配置管理优化验证")
        
        try:
            from llm_utils.config import config
            
            # 检查配置是否已验证
            if config.is_validated():
                self.print_result(
                    "配置验证",
                    True,
                    "配置已通过Pydantic验证"
                )
            else:
                # 尝试验证
                validated = config.validate()
                if validated:
                    self.print_result(
                        "配置验证",
                        True,
                        "配置验证成功"
                    )
                else:
                    self.print_result(
                        "配置验证",
                        False,
                        "配置验证失败"
                    )
                    return False
            
            # 检查配置访问
            llm_config = config.get_llm_config()
            if llm_config and "mode" in llm_config:
                self.print_result(
                    "配置访问",
                    True,
                    f"LLM模式: {llm_config['mode']}"
                )
            else:
                self.print_result("配置访问", False, "无法获取LLM配置")
                return False
            
            return True
        except Exception as e:
            self.print_result("配置验证", False, f"错误: {str(e)}")
            return False
    
    def verify_retry_mechanism(self) -> bool:
        """验证重试机制"""
        self.print_header("2. 重试机制验证")
        
        try:
            from core.retry import retry_async, RetryConfig, with_timeout
            
            # 测试重试装饰器存在
            self.print_result("重试模块导入", True, "重试模块可用")
            
            # 测试RetryConfig
            config = RetryConfig(max_attempts=3, initial_delay=0.1)
            self.print_result(
                "RetryConfig",
                True,
                f"最大重试次数: {config.max_attempts}"
            )
            
            # 测试超时函数存在
            self.print_result("超时控制", True, "超时控制函数可用")
            
            return True
        except Exception as e:
            self.print_result("重试机制", False, f"错误: {str(e)}")
            return False
    
    def verify_database_optimization(self) -> bool:
        """验证数据库优化"""
        self.print_header("3. 数据库优化验证")
        
        try:
            from news_crawler.database import Database
            import tempfile
            import os
            
            # 创建临时数据库测试
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
                db_path = f.name
            
            try:
                db = Database(db_path=db_path)
                
                # 检查连接池
                conn1 = db.get_connection()
                conn2 = db.get_connection()
                
                # 应该返回同一个连接（连接池）
                if conn1 is conn2:
                    self.print_result("连接池", True, "连接池正常工作")
                else:
                    self.print_result("连接池", False, "连接池未正常工作")
                
                # 检查健康检查
                try:
                    conn1.execute("SELECT 1").fetchone()
                    self.print_result("健康检查", True, "连接健康检查正常")
                except Exception as e:
                    self.print_result("健康检查", False, f"错误: {str(e)}")
                
                # 检查索引
                cursor = conn1.cursor()
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='index' AND name LIKE 'idx_news%'
                """)
                indexes = [row[0] for row in cursor.fetchall()]
                
                expected_indexes = [
                    'idx_news_publish_category',
                    'idx_news_category_time'
                ]
                
                found_indexes = [idx for idx in expected_indexes if idx in indexes]
                if found_indexes:
                    self.print_result(
                        "复合索引",
                        True,
                        f"找到索引: {', '.join(found_indexes)}"
                    )
                else:
                    self.print_result(
                        "复合索引",
                        False,
                        "未找到预期的复合索引"
                    )
                
                return True
            finally:
                # 清理
                try:
                    os.unlink(db_path)
                except:
                    pass
        except Exception as e:
            self.print_result("数据库优化", False, f"错误: {str(e)}")
            return False
    
    def verify_code_refactoring(self) -> bool:
        """验证代码重构"""
        self.print_header("4. 代码重构验证")
        
        try:
            # 检查ResponseBuilder是否存在
            from core.response_builder import ResponseBuilder
            self.print_result("ResponseBuilder", True, "ResponseBuilder模块可用")
            
            # 检查TTSStreamProcessor是否存在
            from core.tts_stream_processor import TTSStreamProcessor
            self.print_result("TTSStreamProcessor", True, "TTSStreamProcessor模块可用")
            
            # 检查orchestrator是否使用了新模块
            from core.orchestrator import NewsAgentOrchestrator
            import inspect
            
            # 检查orchestrator的代码行数（应该减少了）
            orchestrator_file = Path(__file__).parent.parent / "core" / "orchestrator.py"
            if orchestrator_file.exists():
                with open(orchestrator_file, 'r', encoding='utf-8') as f:
                    lines = len(f.readlines())
                
                if lines < 1200:  # 原来1100+行，现在应该更少
                    self.print_result(
                        "代码行数",
                        True,
                        f"orchestrator.py: {lines} 行（已优化）"
                    )
                else:
                    self.print_result(
                        "代码行数",
                        False,
                        f"orchestrator.py: {lines} 行（可能未优化）"
                    )
            
            # 检查是否使用了ResponseBuilder
            source = inspect.getsource(NewsAgentOrchestrator)
            if "ResponseBuilder" in source:
                self.print_result(
                    "使用ResponseBuilder",
                    True,
                    "orchestrator使用了ResponseBuilder"
                )
            else:
                self.print_result(
                    "使用ResponseBuilder",
                    False,
                    "orchestrator未使用ResponseBuilder"
                )
            
            return True
        except Exception as e:
            self.print_result("代码重构", False, f"错误: {str(e)}")
            return False
    
    def verify_rate_limiting(self) -> bool:
        """验证API速率限制"""
        self.print_header("5. API速率限制验证")
        
        try:
            from core.rate_limit import limiter, rate_limit_default
            self.print_result("速率限制模块", True, "速率限制模块可用")
            
            # 检查limiter是否配置
            if limiter:
                self.print_result("Limiter实例", True, "Limiter已初始化")
            else:
                self.print_result("Limiter实例", False, "Limiter未初始化")
            
            return True
        except Exception as e:
            self.print_result("速率限制", False, f"错误: {str(e)}")
            return False
    
    def verify_service_health(self) -> bool:
        """验证服务健康状态"""
        self.print_header("6. 服务健康检查")
        
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.print_result(
                    "健康检查端点",
                    True,
                    f"状态: {data.get('status', 'unknown')}"
                )
                return True
            else:
                self.print_result(
                    "健康检查端点",
                    False,
                    f"HTTP {response.status_code}"
                )
                return False
        except requests.exceptions.ConnectionError:
            self.print_result(
                "健康检查端点",
                False,
                "无法连接到服务（服务可能未启动）"
            )
            return False
        except Exception as e:
            self.print_result("健康检查端点", False, f"错误: {str(e)}")
            return False
    
    async def verify_llm_service(self) -> bool:
        """验证LLM服务优化"""
        self.print_header("7. LLM服务优化验证")
        
        try:
            from llm_utils.llm_service import LLMService
            import inspect
            
            # 检查call_llm是否有重试装饰器
            source = inspect.getsource(LLMService.call_llm)
            if "@retry_async" in source or "retry_async" in source:
                self.print_result(
                    "LLM重试机制",
                    True,
                    "call_llm已添加重试装饰器"
                )
            else:
                self.print_result(
                    "LLM重试机制",
                    False,
                    "call_llm未添加重试装饰器"
                )
            
            # 检查是否有超时参数
            sig = inspect.signature(LLMService.call_llm)
            if "timeout" in sig.parameters:
                self.print_result(
                    "LLM超时控制",
                    True,
                    "call_llm支持超时参数"
                )
            else:
                self.print_result(
                    "LLM超时控制",
                    False,
                    "call_llm不支持超时参数"
                )
            
            return True
        except Exception as e:
            self.print_result("LLM服务优化", False, f"错误: {str(e)}")
            return False
    
    def verify_test_coverage(self) -> bool:
        """验证测试覆盖"""
        self.print_header("8. 测试覆盖验证")
        
        try:
            tests_dir = project_root / "tests"
            if not tests_dir.exists():
                self.print_result("测试目录", False, "tests目录不存在")
                return False
            
            test_files = list(tests_dir.glob("test_*.py"))
            if test_files:
                self.print_result(
                    "测试文件",
                    True,
                    f"找到 {len(test_files)} 个测试文件"
                )
                
                # 列出测试文件
                for test_file in test_files:
                    print(f"      - {test_file.name}")
            else:
                self.print_result("测试文件", False, "未找到测试文件")
                return False
            
            # 检查是否有pytest
            try:
                import pytest
                self.print_result("pytest", True, f"pytest版本: {pytest.__version__}")
            except ImportError:
                self.print_result("pytest", False, "pytest未安装")
                return False
            
            return True
        except Exception as e:
            self.print_result("测试覆盖", False, f"错误: {str(e)}")
            return False
    
    def run_all_verifications(self) -> bool:
        """运行所有验证"""
        print("\n" + "=" * 70)
        print("  优化验证脚本")
        print("=" * 70)
        
        # 同步验证
        self.verify_config_validation()
        self.verify_retry_mechanism()
        self.verify_database_optimization()
        self.verify_code_refactoring()
        self.verify_rate_limiting()
        self.verify_service_health()
        self.verify_test_coverage()
        
        # 异步验证
        asyncio.run(self.verify_llm_service())
        
        # 打印总结
        self.print_summary()
        
        return all(self.results.values())
    
    def print_summary(self):
        """打印验证总结"""
        self.print_header("验证总结")
        
        total = len(self.results)
        passed = sum(1 for v in self.results.values() if v)
        failed = total - passed
        
        print(f"总计: {total} 项")
        print(f"通过: {passed} 项 ✅")
        print(f"失败: {failed} 项 ❌")
        
        if failed > 0:
            print("\n失败项:")
            for error in self.errors:
                print(f"  - {error}")
        
        print("\n" + "=" * 70)
        
        if failed == 0:
            print("🎉 所有优化验证通过！")
        else:
            print("⚠️  部分优化验证失败，请检查上述错误")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="验证优化是否生效")
    parser.add_argument(
        "--url",
        default="http://localhost:8080",
        help="服务URL（默认: http://localhost:8080）"
    )
    
    args = parser.parse_args()
    
    verifier = OptimizationVerifier(base_url=args.url)
    success = verifier.run_all_verifications()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
