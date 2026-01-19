"""
快速测试debug_info - 简化版
直接调用orchestrator，不依赖HTTP服务
"""
import asyncio
import json
from core.orchestrator import NewsAgentOrchestrator
from models.state import NewsAgentState


async def quick_test():
    """快速测试debug_info"""
    print("=" * 80)
    print("快速测试 Debug Info")
    print("=" * 80)
    
    # 创建orchestrator
    orchestrator = NewsAgentOrchestrator()
    
    # 测试查询
    query = "今天有什么新闻？"
    request_id = "test_debug_001"
    
    print(f"\n查询: {query}")
    print(f"请求ID: {request_id}")
    print("-" * 80)
    
    # 收集所有响应帧
    frames = []
    final_frame = None
    
    try:
        print("\n📡 开始处理请求...\n")
        
        async for response in orchestrator.process_query(
            query=query,
            request_id=request_id,
            stream=True
        ):
            # 解析SSE响应
            if "data:" in response:
                try:
                    data_str = response.split("data:", 1)[1].strip()
                    frame_data = json.loads(data_str)
                    frames.append(frame_data)
                    
                    # 检查是否是最终帧
                    data = frame_data.get("data", {})
                    if data.get("frame_is_final"):
                        final_frame = frame_data
                        print("✅ 收到最终帧")
                except json.JSONDecodeError:
                    pass
        
        if not final_frame:
            print("❌ 未找到最终帧")
            return
        
        # 分析debug_info
        data = final_frame.get("data", {})
        debug_info = data.get("debug_info")
        
        if debug_info:
            print("\n" + "=" * 80)
            print("✅ Debug Info 存在！")
            print("=" * 80)
            
            # 显示关键信息
            print(f"\n📊 关键信息:")
            print("-" * 80)
            
            # 请求信息
            if "request" in debug_info:
                req = debug_info["request"]
                print(f"查询: {req.get('query')}")
                print(f"请求ID: {req.get('requestId')}")
            
            # 数据获取
            if "dataFetch" in debug_info:
                df = debug_info["dataFetch"]
                print(f"\n数据获取:")
                print(f"  - 缓存命中: {df.get('cacheHit')}")
                print(f"  - 新闻数量: {df.get('newsCount')}")
                print(f"  - 选中数量: {df.get('selectedNewsCount')}")
            
            # 性能指标
            if "performance" in debug_info:
                perf = debug_info["performance"]
                print(f"\n性能指标:")
                print(f"  - 总耗时: {perf.get('totalCostMs', 'N/A')}ms")
            
            # 处理步骤
            if "processing" in debug_info:
                proc = debug_info["processing"]
                print(f"\n处理步骤 ({proc.get('stepCount', 0)} 步):")
                for i, step in enumerate(proc.get("steps", [])[:5], 1):
                    print(f"  {i}. {step}")
            
            # 内容生成
            if "contentGeneration" in debug_info:
                cg = debug_info["contentGeneration"]
                print(f"\n内容生成:")
                print(f"  - 摘要长度: {cg.get('summaryLength')} 字符")
                print(f"  - 思维链步骤: {cg.get('thinkingSteps')}")
            
            # TTS信息
            if "tts" in debug_info:
                tts = debug_info["tts"]
                print(f"\nTTS信息:")
                print(f"  - 语言: {tts.get('language')}")
                print(f"  - 置信度: {tts.get('languageConfidence')}")
                print(f"  - 音频块数: {tts.get('audioChunkCount')}")
            
            # 完整debug_info
            print("\n" + "=" * 80)
            print("完整 Debug Info (JSON):")
            print("=" * 80)
            print(json.dumps(debug_info, ensure_ascii=False, indent=2))
            
            # 保存到文件
            output_file = "quick_test_debug_info.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump({
                    "query": query,
                    "request_id": request_id,
                    "total_frames": len(frames),
                    "final_frame": final_frame,
                    "debug_info": debug_info
                }, f, ensure_ascii=False, indent=2)
            print(f"\n💾 结果已保存到: {output_file}")
            
        else:
            print("\n❌ Debug Info 不存在！")
            print("最终帧数据:")
            print(json.dumps(final_frame, ensure_ascii=False, indent=2))
    
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(quick_test())

