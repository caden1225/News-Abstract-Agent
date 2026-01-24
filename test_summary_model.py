#!/usr/bin/env python3
"""
测试摘要模型脚本
打印返回的全部文本，包括thinking和content，以及原始response
"""
import asyncio
import json
import sys
from typing import Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, '/home/caden/workspace/news_c2')

from prompts import build_news_summary_messages
from llm_utils.llm_service import LLMService, llm_config
from llm_utils.config import config
from core.constants import LLM_CONFIG


# 测试新闻数据
SAMPLE_NEWS = [
    {
        "title": "人工智能技术取得重大突破",
        "summary": "研究团队在深度学习领域取得突破性进展，新算法在图像识别任务中超越人类水平。专家认为这将推动自动驾驶技术的快速发展。该技术预计将在明年投入商用。",
        "ai_summary": "研究团队在深度学习领域取得突破性进展，新算法在图像识别任务中超越人类水平。专家认为这将推动自动驾驶技术的快速发展。"
    },
    {
        "title": "全球气候峰会达成新协议",
        "summary": "各国代表在气候峰会上达成减排新协议，承诺在2030年前减少50%的碳排放。环保组织对此表示欢迎，认为这是应对气候变化的重要一步。",
        "ai_summary": "各国代表在气候峰会上达成减排新协议，承诺在2030年前减少50%的碳排放。环保组织对此表示欢迎。"
    },
    {
        "title": "新型电池技术问世",
        "summary": "科技公司宣布研发出新型固态电池，续航里程提升100%，充电时间缩短至10分钟。这将彻底改变电动汽车行业格局，预计2025年量产。",
        "ai_summary": "科技公司宣布研发出新型固态电池，续航里程提升100%，充电时间缩短至10分钟。这将彻底改变电动汽车行业格局。"
    }
]


def print_separator(title: str = ""):
    """打印分隔线"""
    if title:
        print(f"\n{'='*80}")
        print(f"  {title}")
        print(f"{'='*80}\n")
    else:
        print(f"\n{'-'*80}\n")


def print_dict_pretty(data: Dict[str, Any], indent: int = 0):
    """递归打印字典，格式化输出"""
    indent_str = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            print(f"{indent_str}{key}:")
            print_dict_pretty(value, indent + 1)
        elif isinstance(value, list):
            print(f"{indent_str}{key}: [列表，长度={len(value)}]")
            if len(value) > 0 and isinstance(value[0], dict):
                print(f"{indent_str}  第一个元素:")
                print_dict_pretty(value[0], indent + 2)
        elif isinstance(value, str) and len(value) > 200:
            print(f"{indent_str}{key}: [字符串，长度={len(value)}]")
            print(f"{indent_str}  预览: {value[:200]}...")
        else:
            print(f"{indent_str}{key}: {value}")


async def test_summary_model_with_thinking():
    """测试摘要模型（使用call_llm_with_thinking）"""
    print_separator("测试摘要模型 - call_llm_with_thinking")
    
    # 构建消息
    target_language = "zh"
    messages = build_news_summary_messages(SAMPLE_NEWS, target_language=target_language)
    
    print("📝 输入消息:")
    print(f"  消息数量: {len(messages)}")
    for i, msg in enumerate(messages, 1):
        print(f"\n  消息 {i} ({msg.get('role', 'unknown')}):")
        content = msg.get('content', '')
        if len(content) > 500:
            print(f"    {content[:500]}...")
        else:
            print(f"    {content}")
    
    print_separator()
    
    # 获取配置
    model_name = llm_config['model']
    enable_thinking = config.get_thinking_config()["enable_thinking"]
    
    print(f"🔧 配置信息:")
    print(f"  模型: {model_name}")
    print(f"  启用thinking: {enable_thinking}")
    print(f"  温度: {LLM_CONFIG.SUMMARY_TEMPERATURE}")
    print(f"  最大tokens: {LLM_CONFIG.SUMMARY_MAX_TOKENS}")
    print(f"  目标语言: {target_language}")
    
    print_separator()
    print("🤖 调用LLM...")
    
    try:
        # 调用LLM（需要修改LLMService以返回原始response）
        # 由于call_llm_with_thinking不返回原始response，我们需要直接调用API
        from openai import AsyncOpenAI
        from llm_utils.config import config as llm_config_module
        
        llm_cfg = llm_config_module.get_llm_config()
        client = AsyncOpenAI(
            api_key=llm_cfg['api_key'],
            base_url=llm_cfg['base_url'],
        )
        
        params = {
            'model': model_name,
            'messages': messages,
            'temperature': LLM_CONFIG.SUMMARY_TEMPERATURE,
            'max_tokens': LLM_CONFIG.SUMMARY_MAX_TOKENS,
        }
        
        # 添加thinking配置
        thinking_config = config.get_thinking_config()
        if enable_thinking and thinking_config["enable_thinking"]:
            params['extra_body'] = {
                'enable_thinking': True,
                'thinking_budget': thinking_config["thinking_budget"]
            }
        
        # 调用API获取原始response
        print("  正在调用API...")
        response = await client.chat.completions.create(**params)
        
        print_separator("原始Response对象")
        
        # 打印原始response对象的结构
        print("📦 Response对象类型:", type(response))
        print("\n📋 Response对象属性:")
        print_dict_pretty({
            "id": response.id,
            "object": response.object,
            "created": response.created,
            "model": response.model,
            "choices_count": len(response.choices) if response.choices else 0,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                "completion_tokens": response.usage.completion_tokens if response.usage else None,
                "total_tokens": response.usage.total_tokens if response.usage else None,
            } if response.usage else None,
        })
        
        print_separator("Response.choices[0] 详细信息")
        
        if response.choices and len(response.choices) > 0:
            choice = response.choices[0]
            message = choice.message
            
            print("📦 Choice对象:")
            print(f"  index: {choice.index}")
            print(f"  finish_reason: {choice.finish_reason}")
            
            print("\n📦 Message对象:")
            print(f"  role: {message.role}")
            print(f"  content: [字符串，长度={len(message.content) if message.content else 0}]")
            
            # 检查是否有thinking相关字段
            print("\n🔍 检查thinking相关字段:")
            thinking_fields = {}
            
            # 检查reasoning_content
            if hasattr(message, 'reasoning_content'):
                reasoning = getattr(message, 'reasoning_content', None)
                thinking_fields['reasoning_content'] = reasoning
                print(f"  ✓ reasoning_content: {'存在' if reasoning else '不存在/为空'}")
            
            # 检查thinking
            if hasattr(message, 'thinking'):
                thinking = getattr(message, 'thinking', None)
                thinking_fields['thinking'] = thinking
                print(f"  ✓ thinking: {'存在' if thinking else '不存在/为空'}")
            
            # 检查其他可能的字段
            print(f"\n📋 Message对象所有属性:")
            message_attrs = dir(message)
            for attr in message_attrs:
                if not attr.startswith('_'):
                    try:
                        value = getattr(message, attr)
                        if not callable(value):
                            if isinstance(value, str) and len(value) > 200:
                                print(f"  {attr}: [字符串，长度={len(value)}]")
                                print(f"    预览: {value[:200]}...")
                            else:
                                print(f"  {attr}: {value}")
                    except:
                        pass
            
            print_separator("提取的Thinking和Content")
            
            # 使用LLMService的方法提取thinking和content
            thinking_content, answer_content = await LLMService.call_llm_with_thinking(
                model_name=model_name,
                messages=messages,
                temperature=LLM_CONFIG.SUMMARY_TEMPERATURE,
                max_tokens=LLM_CONFIG.SUMMARY_MAX_TOKENS,
                enable_thinking=enable_thinking
            )
            
            print("💭 Thinking内容:")
            if thinking_content:
                print(f"  长度: {len(thinking_content)} 字符")
                print(f"  内容:\n{thinking_content}")
            else:
                print("  (无thinking内容)")
            
            print_separator()
            
            print("📝 Content内容:")
            if answer_content:
                print(f"  长度: {len(answer_content)} 字符")
                print(f"  内容:\n{answer_content}")
            else:
                print("  (无content内容)")
            
            print_separator()
            
            print("📄 原始Message.content:")
            if message.content:
                print(f"  长度: {len(message.content)} 字符")
                print(f"  内容:\n{message.content}")
            else:
                print("  (无content)")
            
            print_separator("完整Response JSON（序列化）")
            
            # 尝试序列化response（可能不完整，但尽量展示）
            try:
                response_dict = {
                    "id": response.id,
                    "object": response.object,
                    "created": response.created,
                    "model": response.model,
                    "choices": [
                        {
                            "index": choice.index,
                            "finish_reason": choice.finish_reason,
                            "message": {
                                "role": message.role,
                                "content": message.content,
                                "reasoning_content": getattr(message, 'reasoning_content', None),
                                "thinking": getattr(message, 'thinking', None),
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                        "completion_tokens": response.usage.completion_tokens if response.usage else None,
                        "total_tokens": response.usage.total_tokens if response.usage else None,
                    } if response.usage else None,
                }
                
                print(json.dumps(response_dict, ensure_ascii=False, indent=2))
            except Exception as e:
                print(f"⚠️  序列化失败: {e}")
                print("   尝试打印原始对象...")
                print(str(response))
        
        print_separator("测试完成")
        
    except Exception as e:
        print_separator("错误")
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


async def test_summary_model_stream():
    """测试摘要模型（流式模式）"""
    print_separator("测试摘要模型 - 流式模式")
    
    # 构建消息
    target_language = "zh"
    messages = build_news_summary_messages(SAMPLE_NEWS, target_language=target_language)
    
    # 获取配置
    model_name = llm_config['model']
    enable_thinking = config.get_thinking_config()["enable_thinking"]
    
    print(f"🔧 配置信息:")
    print(f"  模型: {model_name}")
    print(f"  启用thinking: {enable_thinking}")
    print(f"  温度: {LLM_CONFIG.SUMMARY_TEMPERATURE}")
    print(f"  最大tokens: {LLM_CONFIG.SUMMARY_MAX_TOKENS}")
    
    print_separator()
    print("🤖 调用LLM（流式）...")
    
    try:
        thinking_parts = []
        content_parts = []
        
        async for token_type, token_content in LLMService.call_llm_stream(
            model_name=model_name,
            messages=messages,
            temperature=LLM_CONFIG.SUMMARY_TEMPERATURE,
            max_tokens=LLM_CONFIG.SUMMARY_MAX_TOKENS,
            enable_thinking=enable_thinking
        ):
            if token_type == "done":
                break
            elif token_type == "thinking":
                thinking_parts.append(token_content)
                print(f"[THINKING] {token_content}", end="", flush=True)
            elif token_type == "content":
                content_parts.append(token_content)
                print(f"[CONTENT] {token_content}", end="", flush=True)
        
        print("\n")
        print_separator("流式结果汇总")
        
        thinking_full = "".join(thinking_parts)
        content_full = "".join(content_parts)
        
        print("💭 Thinking内容（完整）:")
        if thinking_full:
            print(f"  长度: {len(thinking_full)} 字符")
            print(f"  内容:\n{thinking_full}")
        else:
            print("  (无thinking内容)")
        
        print_separator()
        
        print("📝 Content内容（完整）:")
        if content_full:
            print(f"  长度: {len(content_full)} 字符")
            print(f"  内容:\n{content_full}")
        else:
            print("  (无content内容)")
        
        print_separator("流式测试完成")
        
    except Exception as e:
        print_separator("错误")
        print(f"❌ 流式测试失败: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """主函数"""
    print("\n" + "="*80)
    print("  摘要模型测试脚本")
    print("="*80)
    
    # 测试1: 非流式模式（带原始response）
    await test_summary_model_with_thinking()
    
    print("\n\n")
    
    # 测试2: 流式模式
    await test_summary_model_stream()
    
    print("\n" + "="*80)
    print("  所有测试完成")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

