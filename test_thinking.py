#!/usr/bin/env python3
"""
测试脚本：测试 LLM 调用是否返回 thinking 文本
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from llm_utils.llm_service import LLMService
from llm_utils.config import config

async def test_thinking():
    """测试 thinking 功能"""
    print("=" * 80)
    print("🧪 测试 LLM Thinking 功能")
    print("=" * 80)
    print()
    
    # 获取配置
    llm_config = config.get_llm_config()
    thinking_config = config.get_thinking_config()
    
    print("📋 配置信息:")
    print(f"  LLM模式: {llm_config['mode']}")
    print(f"  Base URL: {llm_config['base_url']}")
    print(f"  模型: {llm_config['model']}")
    print(f"  启用thinking: {thinking_config['enable_thinking']}")
    print(f"  Thinking预算: {thinking_config['thinking_budget']}")
    print()
    
    # 构建测试消息
    messages = [
        {
            "role": "user",
            "content": "请用中文回答：1+1等于几？请先思考再回答。"
        }
    ]
    
    model_name = llm_config['model']
    enable_thinking = thinking_config['enable_thinking']
    
    print("=" * 80)
    print("📤 发送请求")
    print("=" * 80)
    print(f"模型: {model_name}")
    print(f"启用thinking: {enable_thinking}")
    print(f"消息: {messages[0]['content']}")
    print()
    
    # 测试流式调用
    print("=" * 80)
    print("🔄 流式调用测试")
    print("=" * 80)
    
    thinking_parts = []
    content_parts = []
    chunk_count = 0
    thinking_chunk_count = 0
    content_chunk_count = 0
    
    try:
        async for token_type, token_content in LLMService.call_llm_stream(
            model_name=model_name,
            messages=messages,
            temperature=0.7,
            max_tokens=500,
            enable_thinking=enable_thinking
        ):
            chunk_count += 1
            
            if token_type == "done":
                print(f"\n✅ 流式响应结束（共收到 {chunk_count} 个chunk）")
                break
            elif token_type == "thinking":
                thinking_chunk_count += 1
                thinking_parts.append(token_content)
                print(f"[THINKING #{thinking_chunk_count}] {token_content}", end="", flush=True)
            elif token_type == "content":
                content_chunk_count += 1
                content_parts.append(token_content)
                print(f"[CONTENT #{content_chunk_count}] {token_content}", end="", flush=True)
            else:
                print(f"[UNKNOWN #{chunk_count}] type={token_type}, content={token_content[:50]}...")
        
        print("\n")
        print("=" * 80)
        print("📊 结果统计")
        print("=" * 80)
        
        thinking_full = "".join(thinking_parts)
        content_full = "".join(content_parts)
        
        print(f"总chunk数: {chunk_count}")
        print(f"Thinking chunk数: {thinking_chunk_count}")
        print(f"Content chunk数: {content_chunk_count}")
        print()
        
        print("💭 Thinking内容:")
        if thinking_full:
            print(f"  ✅ 收到thinking内容！")
            print(f"  长度: {len(thinking_full)} 字符")
            print(f"  内容预览（前200字符）:")
            print(f"  {thinking_full[:200]}...")
            if len(thinking_full) > 200:
                print(f"  ... (共 {len(thinking_full)} 字符)")
        else:
            print(f"  ❌ 未收到thinking内容")
            print(f"  可能的原因：")
            print(f"    1. LLM服务端不支持thinking功能")
            print(f"    2. 模型不支持thinking")
            print(f"    3. 响应格式不同（不是reasoning_content或thinking字段）")
        print()
        
        print("📝 Content内容:")
        if content_full:
            print(f"  ✅ 收到content内容")
            print(f"  长度: {len(content_full)} 字符")
            print(f"  内容: {content_full}")
        else:
            print(f"  ⚠️  未收到content内容")
        print()
        
        # 总结
        print("=" * 80)
        print("📋 测试总结")
        print("=" * 80)
        if thinking_full:
            print("✅ Thinking功能正常工作！")
        else:
            print("❌ Thinking功能未返回内容")
            print()
            print("💡 建议检查：")
            print("  1. 查看日志中的 [THINKING调试] 信息")
            print("  2. 检查LLM服务端是否支持thinking功能")
            print("  3. 检查模型是否支持thinking")
            print("  4. 检查响应格式是否正确")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    asyncio.run(test_thinking())


