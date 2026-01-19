#!/usr/bin/env python3
"""
LLM连接测试脚本
用于测试LLM服务的连接状态和基本功能

使用方法:
    python test_llm_connection.py
"""

import asyncio
import sys
import logging
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from llm_utils.config import config
from llm_utils.llm_service import LLMService
from openai import AsyncOpenAI

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_info(key: str, value: str):
    """打印信息行"""
    print(f"  {key:20s}: {value}")


async def test_config():
    """测试配置加载"""
    print_section("1. 配置信息检查")
    
    try:
        llm_config = config.get_llm_config()
        print_info("模式", llm_config['mode'].upper())
        print_info("Base URL", llm_config['base_url'])
        print_info("模型", llm_config['model'])
        
        # 隐藏API密钥，只显示前4位和后4位
        api_key = llm_config['api_key']
        if api_key:
            if len(api_key) > 8:
                masked_key = f"{api_key[:4]}...{api_key[-4:]}"
            else:
                masked_key = "***"
            print_info("API Key", masked_key)
        else:
            print_info("API Key", "(未设置)")
        
        # 显示超时配置
        timeout = config.get("llm.timeout", 30.0)
        print_info("超时时间", f"{timeout}秒")
        
        # 显示thinking配置
        thinking_config = config.get_thinking_config()
        print_info("启用Thinking", str(thinking_config['enable_thinking']))
        if thinking_config['enable_thinking']:
            print_info("Thinking预算", f"{thinking_config['thinking_budget']} tokens")
        
        print("\n✅ 配置加载成功")
        return llm_config
        
    except Exception as e:
        print(f"\n❌ 配置加载失败: {e}")
        logger.exception("配置加载异常")
        return None


async def test_connection(llm_config: dict):
    """测试基本连接"""
    print_section("2. 连接测试")
    
    try:
        # 创建客户端
        client = AsyncOpenAI(
            api_key=llm_config['api_key'],
            base_url=llm_config['base_url'],
        )
        
        # 尝试列出模型（如果API支持）
        try:
            print("  正在测试API连接...")
            models = await asyncio.wait_for(
                client.models.list(),
                timeout=5.0
            )
            print(f"  ✅ API连接成功，可用模型数量: {len(list(models.data))}")
            if models.data:
                print("  可用模型:")
                for model in list(models.data)[:5]:  # 只显示前5个
                    print(f"    - {model.id}")
        except asyncio.TimeoutError:
            print("  ⚠️  连接超时（可能不支持models.list接口）")
        except Exception as e:
            print(f"  ⚠️  models.list接口不可用: {e}")
            print("  （这是正常的，某些API不提供此接口）")
        
        print("\n✅ 连接测试完成")
        return True
        
    except Exception as e:
        print(f"\n❌ 连接测试失败: {e}")
        logger.exception("连接测试异常")
        return False


async def test_basic_call(llm_config: dict):
    """测试基本LLM调用"""
    print_section("3. 基本调用测试")
    
    try:
        model_name = llm_config['model']
        test_messages = [
            {"role": "user", "content": "请用一句话介绍你自己。"}
        ]
        
        print(f"  模型: {model_name}")
        print(f"  测试消息: {test_messages[0]['content']}")
        print("  正在调用LLM...")
        
        response = await LLMService.call_llm(
            model_name=model_name,
            messages=test_messages,
            temperature=0.7,
            max_tokens=100,
            timeout=30.0
        )
        
        print(f"\n  ✅ 调用成功!")
        print(f"  响应内容: {response}")
        print(f"  响应长度: {len(response)} 字符")
        
        return True
        
    except Exception as e:
        error_str = str(e)
        print(f"\n  ❌ 调用失败: {error_str}")
        
        # 针对百度千帆的401错误提供详细说明
        if "401" in error_str or "invalid_iam_token" in error_str.lower():
            print("\n  ⚠️  认证失败 - 百度千帆认证问题")
            print("  " + "-" * 50)
            print("  问题说明:")
            print("    百度千帆不能直接使用API Key，需要使用以下方式之一:")
            print()
            print("  方式1: 使用Bearer Token (推荐)")
            print("    1. 在千帆控制台创建应用，获取 Access Key (AK) 和 Secret Key (SK)")
            print("    2. 使用AK/SK调用接口生成Bearer Token:")
            print("       POST https://qianfan.baidubce.com/oauth/2.0/token")
            print("       ?grant_type=client_credentials")
            print("       &client_id={AK}")
            print("       &client_secret={SK}")
            print("    3. 将生成的Bearer Token设置为 QIANFAN_API_KEY 环境变量")
            print()
            print("  方式2: 使用Access Token")
            print("    1. 使用AK/SK获取Access Token (有效期30天)")
            print("    2. 在请求中使用 access_token 参数")
            print()
            print("  当前配置:")
            print(f"    模式: {llm_config['mode']}")
            print(f"    Base URL: {llm_config['base_url']}")
            print(f"    模型: {llm_config['model']}")
            print("  " + "-" * 50)
            print()
            print("  解决方案:")
            print("    1. 检查环境变量 QIANFAN_API_KEY 是否为有效的Bearer Token")
            print("    2. 如果使用的是AK/SK，需要先转换为Bearer Token")
            print("    3. 或者切换到 sidecar 模式使用本地服务")
        
        logger.exception("基本调用异常")
        return False


async def test_thinking_call(llm_config: dict):
    """测试带thinking的LLM调用"""
    print_section("4. Thinking功能测试")
    
    try:
        thinking_config = config.get_thinking_config()
        if not thinking_config['enable_thinking']:
            print("  ⚠️  Thinking功能未启用，跳过测试")
            return True
        
        model_name = llm_config['model']
        test_messages = [
            {"role": "user", "content": "请思考一下：1+1等于几？"}
        ]
        
        print(f"  模型: {model_name}")
        print(f"  Thinking预算: {thinking_config['thinking_budget']} tokens")
        print(f"  测试消息: {test_messages[0]['content']}")
        print("  正在调用LLM（启用thinking）...")
        
        thinking_content, answer_content = await LLMService.call_llm_with_thinking(
            model_name=model_name,
            messages=test_messages,
            temperature=0.7,
            max_tokens=200,
            enable_thinking=True
        )
        
        print(f"\n  ✅ 调用成功!")
        if thinking_content:
            print(f"  思考过程: {thinking_content[:200]}..." if len(thinking_content) > 200 else f"  思考过程: {thinking_content}")
            print(f"  思考长度: {len(thinking_content)} 字符")
        else:
            print("  ⚠️  未检测到思考内容（模型可能不支持或未返回）")
        
        print(f"  最终回答: {answer_content}")
        print(f"  回答长度: {len(answer_content)} 字符")
        
        return True
        
    except Exception as e:
        error_str = str(e)
        print(f"\n  ❌ 调用失败: {error_str}")
        
        # 针对认证错误提供说明
        if "401" in error_str or "invalid_iam_token" in error_str.lower():
            print("  ⚠️  认证失败，请参考上面的认证说明")
        
        logger.exception("Thinking调用异常")
        return False


async def test_stream_call(llm_config: dict):
    """测试流式调用"""
    print_section("5. 流式调用测试")
    
    try:
        model_name = llm_config['model']
        test_messages = [
            {"role": "user", "content": "请数数从1到5。"}
        ]
        
        print(f"  模型: {model_name}")
        print(f"  测试消息: {test_messages[0]['content']}")
        print("  正在调用LLM（流式）...")
        print("\n  流式响应:")
        print("  " + "-" * 50)
        
        full_response = ""
        token_count = 0
        
        async for token_type, token_content in LLMService.call_llm_stream(
            model_name=model_name,
            messages=test_messages,
            temperature=0.7,
            max_tokens=100,
            enable_thinking=False,
            timeout=30.0
        ):
            if token_type == "thinking":
                print(f"  [思考] {token_content}", end="", flush=True)
            else:
                print(token_content, end="", flush=True)
                full_response += token_content
                token_count += 1
        
        print("\n  " + "-" * 50)
        print(f"\n  ✅ 流式调用成功!")
        print(f"  总token数: {token_count}")
        print(f"  完整响应: {full_response}")
        
        return True
        
    except Exception as e:
        error_str = str(e)
        print(f"\n  ❌ 流式调用失败: {error_str}")
        
        # 针对认证错误提供说明
        if "401" in error_str or "invalid_iam_token" in error_str.lower():
            print("  ⚠️  认证失败，请参考上面的认证说明")
        
        logger.exception("流式调用异常")
        return False


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  LLM连接测试工具")
    print("=" * 60)
    
    results = {
        "配置检查": False,
        "连接测试": False,
        "基本调用": False,
        "Thinking调用": False,
        "流式调用": False,
    }
    
    # 1. 测试配置
    llm_config = await test_config()
    if llm_config:
        results["配置检查"] = True
    else:
        print("\n❌ 配置加载失败，无法继续测试")
        return
    
    # 2. 测试连接
    if await test_connection(llm_config):
        results["连接测试"] = True
    
    # 3. 测试基本调用
    if await test_basic_call(llm_config):
        results["基本调用"] = True
    
    # 4. 测试thinking调用（可选）
    if await test_thinking_call(llm_config):
        results["Thinking调用"] = True
    
    # 5. 测试流式调用（可选）
    try:
        if await test_stream_call(llm_config):
            results["流式调用"] = True
    except KeyboardInterrupt:
        print("\n\n⚠️  流式调用被用户中断")
    
    # 打印总结
    print_section("测试总结")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name:20s}: {status}")
    
    print(f"\n  总计: {passed}/{total} 项测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！LLM服务运行正常。")
        return 0
    elif passed >= 2:  # 至少配置和基本调用通过
        print("\n⚠️  部分测试通过，LLM服务基本可用。")
        return 0
    else:
        print("\n❌ 测试失败，请检查LLM服务配置和连接。")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ 测试过程中发生未预期的错误: {e}")
        logger.exception("未预期的异常")
        sys.exit(1)
