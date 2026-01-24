#!/usr/bin/env python3
"""
精简测试脚本：打印response的原始内容
- 打印每种类型数据的第一和最后一个response
- 打印最终response
"""
import asyncio
import json
import sys
from typing import Dict, Optional

from core.orchestrator import NewsAgentOrchestrator


def parse_response(raw_response: str) -> Optional[Dict]:
    """解析SSE格式的response"""
    if not raw_response.strip():
        return None
    
    # SSE格式: event:data\ndata:{JSON}\n\n
    lines = raw_response.strip().split('\n')
    for line in lines:
        if line.startswith('data:'):
            data_str = line[5:].strip()
            if data_str:
                try:
                    return json.loads(data_str)
                except json.JSONDecodeError:
                    pass
    return None


def get_response_type(response: Dict) -> str:
    """识别response类型"""
    if not response:
        return "unknown"
    
    code = response.get("code", 0)
    if code != 0:
        return "error"
    
    data = response.get("data", {})
    if not data:
        return "unknown"
    
    frame_is_final = data.get("frame_is_final", False)
    if frame_is_final:
        return "final"
    
    response_type = data.get("response_type", "")
    extension = data.get("extension", {})
    token_type = extension.get("token_type", "")
    
    if response_type == "image" or token_type == "image":
        return "image"
    elif response_type == "thinking" or token_type == "thinking":
        return "thinking"
    elif response_type == "text" or token_type == "content":
        return "text"
    elif response_type == "audio" or token_type == "audio":
        return "audio"
    else:
        return "unknown"


async def test_response_print():
    """测试并打印response"""
    query = "今天有什么新闻？"
    request_id = "test_response_print"
    
    print("=" * 80)
    print(f"测试查询: {query}")
    print("=" * 80)
    print()
    
    # 初始化orchestrator
    orchestrator = NewsAgentOrchestrator()
    
    # 存储每种类型的第一和最后一个response
    first_responses: Dict[str, str] = {}
    last_responses: Dict[str, str] = {}
    final_response: Optional[str] = None
    
    # 统计信息
    type_counts: Dict[str, int] = {}
    
    print("📥 开始接收流式响应...")
    print()
    
    try:
        async for raw_response in orchestrator.process_query(
            query=query,
            request_id=request_id,
            stream=True
        ):
            # 解析response
            response = parse_response(raw_response)
            if not response:
                continue
            
            # 识别类型
            resp_type = get_response_type(response)
            type_counts[resp_type] = type_counts.get(resp_type, 0) + 1
            
            # 记录第一个response
            if resp_type not in first_responses:
                first_responses[resp_type] = raw_response
            
            # 记录最后一个response（总是更新）
            last_responses[resp_type] = raw_response
            
            # 记录最终response
            if resp_type == "final":
                final_response = raw_response
            
            # 打印进度
            print(f"[进度] 收到 {resp_type} 类型响应 (总数: {type_counts[resp_type]})", flush=True)
    
    except Exception as e:
        print(f"❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print()
    print("=" * 80)
    print("📊 统计信息")
    print("=" * 80)
    for resp_type, count in sorted(type_counts.items()):
        print(f"{resp_type}: {count} 个")
    print()
    
    # 打印每种类型的第一和最后一个response
    print("=" * 80)
    print("📋 每种类型的第一和最后一个response")
    print("=" * 80)
    print()
    
    for resp_type in sorted(set(list(first_responses.keys()) + list(last_responses.keys()))):
        print(f"\n{'=' * 80}")
        print(f"类型: {resp_type.upper()}")
        print(f"{'=' * 80}")
        
        # 第一个response
        if resp_type in first_responses:
            print(f"\n【第一个 {resp_type} 类型响应】")
            print("-" * 80)
            first_resp = parse_response(first_responses[resp_type])
            if first_resp:
                print(json.dumps(first_resp, indent=2, ensure_ascii=False))
            else:
                print(first_responses[resp_type])
            print("-" * 80)
        else:
            print(f"\n⚠️  未收到第一个 {resp_type} 类型响应")
        
        # 最后一个response（如果与第一个不同）
        if resp_type in last_responses:
            if first_responses.get(resp_type) != last_responses[resp_type]:
                print(f"\n【最后一个 {resp_type} 类型响应】")
                print("-" * 80)
                last_resp = parse_response(last_responses[resp_type])
                if last_resp:
                    print(json.dumps(last_resp, indent=2, ensure_ascii=False))
                else:
                    print(last_responses[resp_type])
                print("-" * 80)
            else:
                print(f"\nℹ️  第一个和最后一个 {resp_type} 类型响应相同（仅有一个）")
        else:
            print(f"\n⚠️  未收到最后一个 {resp_type} 类型响应")
    
    # 打印最终response
    print()
    print("=" * 80)
    print("📋 最终response")
    print("=" * 80)
    if final_response:
        print()
        final_resp = parse_response(final_response)
        if final_resp:
            print(json.dumps(final_resp, indent=2, ensure_ascii=False))
        else:
            print(final_response)
    else:
        print("\n⚠️  未收到最终response")
    
    print()
    print("=" * 80)
    print("✅ 测试完成")
    print("=" * 80)


async def main():
    """主函数"""
    await test_response_print()


if __name__ == "__main__":
    asyncio.run(main())

