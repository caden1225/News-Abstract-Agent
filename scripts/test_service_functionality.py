#!/usr/bin/env python3
"""
服务功能测试脚本
测试优化后的服务是否仍然正常工作
"""
import sys
import asyncio
import requests
import json
import time
from pathlib import Path
from typing import Dict, List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class ServiceTester:
    """服务测试器"""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.results: List[Dict] = []
    
    def print_header(self, title: str):
        """打印标题"""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70)
    
    def test_endpoint(self, method: str, endpoint: str, **kwargs) -> Dict:
        """测试API端点"""
        url = f"{self.base_url}{endpoint}"
        try:
            start_time = time.time()
            
            if method.upper() == "GET":
                response = requests.get(url, timeout=30, **kwargs)
            elif method.upper() == "POST":
                response = requests.post(url, timeout=30, **kwargs)
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")
            
            elapsed = time.time() - start_time
            
            result = {
                "endpoint": endpoint,
                "method": method,
                "status_code": response.status_code,
                "elapsed": elapsed,
                "success": 200 <= response.status_code < 300,
                "error": None
            }
            
            try:
                result["response"] = response.json()
            except:
                result["response"] = response.text[:200]
            
            return result
        except Exception as e:
            return {
                "endpoint": endpoint,
                "method": method,
                "status_code": None,
                "elapsed": 0,
                "success": False,
                "error": str(e),
                "response": None
            }
    
    def test_health_check(self):
        """测试健康检查"""
        self.print_header("1. 健康检查测试")
        
        result = self.test_endpoint("GET", "/health")
        self.results.append(result)
        
        if result["success"]:
            print(f"✅ 健康检查通过")
            print(f"   状态码: {result['status_code']}")
            print(f"   响应时间: {result['elapsed']:.3f}秒")
            if result.get("response"):
                print(f"   状态: {result['response'].get('status', 'unknown')}")
        else:
            print(f"❌ 健康检查失败")
            if result.get("error"):
                print(f"   错误: {result['error']}")
            else:
                print(f"   状态码: {result['status_code']}")
    
    def test_root_endpoint(self):
        """测试根端点"""
        self.print_header("2. 根端点测试")
        
        result = self.test_endpoint("GET", "/")
        self.results.append(result)
        
        if result["success"]:
            print(f"✅ 根端点访问成功")
            print(f"   响应时间: {result['elapsed']:.3f}秒")
        else:
            print(f"❌ 根端点访问失败")
            if result.get("error"):
                print(f"   错误: {result['error']}")
    
    def test_chat_endpoint(self):
        """测试聊天端点（非流式）"""
        self.print_header("3. 聊天端点测试（非流式）")
        
        payload = {
            "query": "今天有什么新闻",
            "stream": False,
            "request_id": f"test_{int(time.time())}"
        }
        
        result = self.test_endpoint("POST", "/api/v1/chat", json=payload)
        self.results.append(result)
        
        if result["success"]:
            print(f"✅ 聊天端点测试通过")
            print(f"   响应时间: {result['elapsed']:.3f}秒")
            
            response = result.get("response", {})
            if isinstance(response, dict):
                if response.get("code") == 0:
                    print(f"   返回码: {response.get('code')}")
                    data = response.get("data", {})
                    if data.get("complete_content"):
                        content_len = len(data["complete_content"])
                        print(f"   内容长度: {content_len} 字符")
                else:
                    print(f"   返回码: {response.get('code')}")
                    print(f"   错误: {response.get('message', 'unknown')}")
        else:
            print(f"❌ 聊天端点测试失败")
            if result.get("error"):
                print(f"   错误: {result['error']}")
            else:
                print(f"   状态码: {result['status_code']}")
    
    def test_chat_stream_endpoint(self):
        """测试聊天端点（流式）"""
        self.print_header("4. 聊天端点测试（流式）")
        
        payload = {
            "query": "今天有什么新闻",
            "stream": True,
            "request_id": f"test_stream_{int(time.time())}"
        }
        
        try:
            url = f"{self.base_url}/api/v1/chat"
            start_time = time.time()
            
            response = requests.post(url, json=payload, stream=True, timeout=60)
            
            if response.status_code == 200:
                frame_count = 0
                for line in response.iter_lines():
                    if line:
                        frame_count += 1
                        if frame_count >= 5:  # 只读取前5帧
                            break
                
                elapsed = time.time() - start_time
                
                result = {
                    "endpoint": "/api/v1/chat",
                    "method": "POST",
                    "status_code": 200,
                    "elapsed": elapsed,
                    "success": True,
                    "frames_received": frame_count
                }
                
                print(f"✅ 流式端点测试通过")
                print(f"   响应时间: {elapsed:.3f}秒")
                print(f"   收到帧数: {frame_count}")
                
                self.results.append(result)
            else:
                result = {
                    "endpoint": "/api/v1/chat",
                    "method": "POST",
                    "status_code": response.status_code,
                    "elapsed": 0,
                    "success": False,
                    "error": f"HTTP {response.status_code}"
                }
                print(f"❌ 流式端点测试失败: HTTP {response.status_code}")
                self.results.append(result)
        except Exception as e:
            result = {
                "endpoint": "/api/v1/chat",
                "method": "POST",
                "status_code": None,
                "elapsed": 0,
                "success": False,
                "error": str(e)
            }
            print(f"❌ 流式端点测试失败: {str(e)}")
            self.results.append(result)
    
    def test_rate_limiting(self):
        """测试速率限制"""
        self.print_header("5. 速率限制测试")
        
        # 快速发送多个请求
        request_count = 15  # 超过10次/分钟的限制
        success_count = 0
        rate_limited_count = 0
        
        print(f"发送 {request_count} 个请求测试速率限制...")
        
        for i in range(request_count):
            payload = {
                "query": f"测试请求 {i}",
                "stream": False,
                "request_id": f"rate_test_{i}_{int(time.time())}"
            }
            
            result = self.test_endpoint("POST", "/api/v1/chat", json=payload)
            
            if result["status_code"] == 429:
                rate_limited_count += 1
            elif result["success"]:
                success_count += 1
            
            # 稍微延迟避免过快
            time.sleep(0.1)
        
        print(f"   成功: {success_count} 个")
        print(f"   被限制: {rate_limited_count} 个")
        
        if rate_limited_count > 0:
            print(f"✅ 速率限制正常工作（检测到 {rate_limited_count} 个被限制的请求）")
        else:
            print(f"⚠️  速率限制可能未生效（未检测到429响应）")
        
        result = {
            "endpoint": "/api/v1/chat",
            "method": "POST",
            "success": True,
            "rate_limited_count": rate_limited_count,
            "success_count": success_count
        }
        self.results.append(result)
    
    def test_stats_endpoint(self):
        """测试统计端点"""
        self.print_header("6. 统计端点测试")
        
        result = self.test_endpoint("GET", "/api/v1/stats")
        self.results.append(result)
        
        if result["success"]:
            print(f"✅ 统计端点测试通过")
            print(f"   响应时间: {result['elapsed']:.3f}秒")
        else:
            print(f"❌ 统计端点测试失败")
            if result.get("error"):
                print(f"   错误: {result['error']}")
    
    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "=" * 70)
        print("  服务功能测试")
        print("=" * 70)
        
        self.test_health_check()
        self.test_root_endpoint()
        self.test_chat_endpoint()
        self.test_chat_stream_endpoint()
        self.test_rate_limiting()
        self.test_stats_endpoint()
        
        self.print_summary()
    
    def print_summary(self):
        """打印测试总结"""
        self.print_header("测试总结")
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r.get("success", False))
        failed = total - passed
        
        print(f"总计测试: {total} 项")
        print(f"通过: {passed} 项 ✅")
        print(f"失败: {failed} 项 ❌")
        
        if failed > 0:
            print("\n失败的测试:")
            for result in self.results:
                if not result.get("success", False):
                    print(f"  - {result.get('endpoint', 'unknown')}: {result.get('error', 'unknown error')}")
        
        # 性能统计
        elapsed_times = [r.get("elapsed", 0) for r in self.results if r.get("elapsed", 0) > 0]
        if elapsed_times:
            avg_time = sum(elapsed_times) / len(elapsed_times)
            max_time = max(elapsed_times)
            print(f"\n性能统计:")
            print(f"   平均响应时间: {avg_time:.3f}秒")
            print(f"   最大响应时间: {max_time:.3f}秒")
        
        print("\n" + "=" * 70)
        
        if failed == 0:
            print("🎉 所有功能测试通过！服务运行正常。")
        else:
            print("⚠️  部分功能测试失败，请检查服务状态。")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="测试服务功能")
    parser.add_argument(
        "--url",
        default="http://localhost:8080",
        help="服务URL（默认: http://localhost:8080）"
    )
    
    args = parser.parse_args()
    
    tester = ServiceTester(base_url=args.url)
    tester.run_all_tests()


if __name__ == "__main__":
    main()
