#!/usr/bin/env python3
"""
Prompt 调试脚本

功能：
1. 预览 prompt 模板（原始和渲染后）
2. 测试不同参数组合
3. 实际调用 LLM 测试 prompt 效果
4. 对比不同语言/版本的 prompt
5. 交互式调试模式

使用方法：
    # 预览模板
    python debug_prompt.py --template intent_analysis --preview
    
    # 测试渲染
    python debug_prompt.py --template news_summary --test-render --language zh
    
    # 实际调用 LLM 测试
    python debug_prompt.py --template news_summary --test-llm --language zh
    
    # 交互式调试
    python debug_prompt.py --interactive
"""
import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import date, timedelta

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from prompts import (
    PromptManager,
    get_prompt_manager,
    build_news_summary_messages,
    build_intent_analysis_prompt,
    format_news_items,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 可选导入 LLM 相关模块（用于测试 LLM 调用）
try:
    from llm_utils.llm_service import LLMService
    from llm_utils.config import config
    LLM_AVAILABLE = True
except ImportError as e:
    LLM_AVAILABLE = False
    logger.warning(f"LLM 模块不可用: {e}，--test-llm 功能将无法使用")


# ==================== 测试数据 ====================

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

SAMPLE_QUERIES = [
    "今天有什么新闻",
    "昨天的科技新闻",
    "搜索人工智能相关新闻",
    "用英文播报今天的新闻",
    "使用韩语播报",
    "今天的热点新闻",
]


# ==================== 预览功能 ====================

def preview_template(template_name: str, **kwargs):
    """预览模板内容（原始和渲染后）"""
    manager = get_prompt_manager()
    
    print(f"\n{'='*80}")
    print(f"📄 预览模板: {template_name}")
    print(f"{'='*80}\n")
    
    try:
        # 加载原始模板
        import prompts.templates.intent_analysis as intent_analysis
        import prompts.templates.news_summary as news_summary
        
        if template_name == "intent_analysis":
            print("【原始 SYSTEM_PROMPT】")
            print(intent_analysis.SYSTEM_PROMPT or "(空)")
            print("\n【原始 USER_PROMPT】")
            print(intent_analysis.USER_PROMPT)
            print("\n" + "-"*80 + "\n")
            
            # 渲染模板
            query = kwargs.get("query", "今天有什么新闻")
            today = date.today().strftime("%Y-%m-%d")
            yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
            
            rendered = manager.render_template(
                template_name,
                query=query,
                today=today,
                yesterday=yesterday
            )
            
            print("【渲染后的 SYSTEM_PROMPT】")
            print(rendered["system"] or "(空)")
            print("\n【渲染后的 USER_PROMPT】")
            print(rendered["user"])
            
        elif template_name == "news_summary":
            print("【原始 SYSTEM_PROMPT】")
            print(news_summary.get_system_prompt())
            print("\n【原始 USER_PROMPT (中文)】")
            print(news_summary.get_user_prompt("zh"))
            print("\n" + "-"*80 + "\n")
            
            # 渲染模板
            target_language = kwargs.get("language", "zh")
            messages = build_news_summary_messages(SAMPLE_NEWS, target_language=target_language)
            
            print(f"【渲染后的 Messages (目标语言: {target_language})】")
            for msg in messages:
                print(f"\n[{msg['role'].upper()}]")
                print(msg['content'])
                print()
        
        print(f"{'='*80}\n")
        return True
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== 测试渲染功能 ====================

def test_render(template_name: str, **kwargs):
    """测试模板渲染"""
    print(f"\n{'='*80}")
    print(f"🧪 测试模板渲染: {template_name}")
    print(f"{'='*80}\n")
    
    try:
        if template_name == "intent_analysis":
            # 测试不同查询
            for query in SAMPLE_QUERIES[:3]:
                print(f"\n【查询】: {query}")
                print("-" * 80)
                prompt = build_intent_analysis_prompt(query)
                print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
                print()
        
        elif template_name == "news_summary":
            # 测试不同语言
            for lang in ["zh", "en", "ko"]:
                print(f"\n【目标语言】: {lang}")
                print("-" * 80)
                messages = build_news_summary_messages(SAMPLE_NEWS, target_language=lang)
                for msg in messages:
                    print(f"[{msg['role'].upper()}]")
                    content = msg['content']
                    # 只显示前300字符
                    if len(content) > 300:
                        print(content[:300] + "...")
                    else:
                        print(content)
                    print()
        
        print(f"{'='*80}\n")
        return True
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== 测试 LLM 调用 ====================

async def test_llm_call(template_name: str, **kwargs):
    """实际调用 LLM 测试 prompt 效果"""
    if not LLM_AVAILABLE:
        print("❌ LLM 模块不可用，无法执行 LLM 测试")
        print("   请确保已安装所有依赖并配置好 LLM 服务")
        return False
    
    print(f"\n{'='*80}")
    print(f"🤖 测试 LLM 调用: {template_name}")
    print(f"{'='*80}\n")
    
    try:
        llm_config = config.get_llm_config()
        model_name = llm_config['model']
        
        print(f"模型: {model_name}")
        print(f"模式: {llm_config['mode']}\n")
        
        if template_name == "intent_analysis":
            # 测试意图分析
            query = kwargs.get("query", "今天有什么新闻")
            print(f"【用户查询】: {query}\n")
            
            prompt = build_intent_analysis_prompt(query)
            messages = [{"role": "user", "content": prompt}]
            
            print("【发送的 Prompt】")
            print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
            print("\n" + "-"*80 + "\n")
            
            print("【等待 LLM 响应...】\n")
            response = await LLMService.call_llm(
                model_name=model_name,
                messages=messages,
                temperature=0.3,
                max_tokens=500
            )
            
            print("【LLM 响应】")
            print(response)
            print("\n" + "-"*80 + "\n")
            
            # 尝试解析 JSON
            try:
                # 提取 JSON 部分
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    parsed = json.loads(json_str)
                    print("【解析后的 JSON】")
                    print(json.dumps(parsed, ensure_ascii=False, indent=2))
                else:
                    print("⚠️  无法找到 JSON 格式的响应")
            except json.JSONDecodeError as e:
                print(f"⚠️  JSON 解析失败: {e}")
        
        elif template_name == "news_summary":
            # 测试新闻摘要
            target_language = kwargs.get("language", "zh")
            print(f"【目标语言】: {target_language}\n")
            
            messages = build_news_summary_messages(SAMPLE_NEWS, target_language=target_language)
            
            print("【发送的 Messages】")
            for msg in messages:
                print(f"\n[{msg['role'].upper()}]")
                content = msg['content']
                if len(content) > 500:
                    print(content[:500] + "...")
                else:
                    print(content)
            print("\n" + "-"*80 + "\n")
            
            print("【等待 LLM 响应...】\n")
            
            # 获取thinking配置
            thinking_config = config.get_thinking_config()
            enable_thinking = thinking_config.get("enable_thinking", False)
            
            if enable_thinking:
                # 使用流式调用查看thinking过程
                print("【流式输出（包含thinking）】\n")
                thinking_content = ""
                content_buffer = ""
                in_thinking = True
                
                async for token_type, token_content in LLMService.call_llm_stream(
                    model_name=model_name,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2000,
                    enable_thinking=True
                ):
                    if token_type == "done":
                        break  # 流式响应结束
                    elif token_type == "thinking":
                        thinking_content += token_content
                        print(f"{token_content}", end="", flush=True)
                    elif token_type == "content":
                        if in_thinking:
                            in_thinking = False
                            print("\n\n【CONTENT】\n")
                        content_buffer += token_content
                        print(token_content, end="", flush=True)
                
                print("\n\n" + "-"*80)
                print(f"\n【统计】")
                print(f"Thinking 长度: {len(thinking_content)} 字符")
                print(f"Content 长度: {len(content_buffer)} 字符")
            else:
                # 普通调用
                response = await LLMService.call_llm(
                    model_name=model_name,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2000
                )
                
                print("【LLM 响应】")
                print(response)
                print(f"\n【统计】")
                print(f"响应长度: {len(response)} 字符")
        
        print(f"\n{'='*80}\n")
        return True
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== 对比功能 ====================

def compare_languages(template_name: str = "news_summary"):
    """对比不同语言的 prompt"""
    print(f"\n{'='*80}")
    print(f"🔍 对比不同语言的 Prompt: {template_name}")
    print(f"{'='*80}\n")
    
    if template_name != "news_summary":
        print("⚠️  目前只支持 news_summary 模板的语言对比")
        return False
    
    languages = ["zh", "en", "ko"]
    
    for lang in languages:
        print(f"\n【{lang.upper()} 版本】")
        print("=" * 80)
        messages = build_news_summary_messages(SAMPLE_NEWS, target_language=lang)
        
        for msg in messages:
            print(f"\n[{msg['role'].upper()}]")
            content = msg['content']
            # 只显示关键部分
            if msg['role'] == 'system':
                print(content)
            else:
                # 显示语言指令部分
                if "重要：语言要求" in content:
                    start = content.find("重要：语言要求")
                    end = content.find("## 多语言素材处理：") + len("## 多语言素材处理：") + 200
                    print(content[start:end] + "...")
                else:
                    print(content[:300] + "...")
        print()
    
    print(f"{'='*80}\n")
    return True


# ==================== 交互式调试 ====================

async def interactive_mode():
    """交互式调试模式"""
    print(f"\n{'='*80}")
    print("🎮 交互式 Prompt 调试模式")
    print(f"{'='*80}\n")
    print("可用命令:")
    print("  1. preview <template> [args]  - 预览模板")
    print("  2. render <template> [args]  - 测试渲染")
    print("  3. test <template> [args]    - 调用 LLM 测试")
    print("  4. compare                   - 对比不同语言")
    print("  5. help                      - 显示帮助")
    print("  6. quit/exit                 - 退出")
    print()
    
    while True:
        try:
            cmd = input("> ").strip()
            if not cmd:
                continue
            
            parts = cmd.split()
            command = parts[0].lower()
            
            if command in ["quit", "exit", "q"]:
                print("👋 再见！")
                break
            
            elif command == "help":
                print("\n命令说明:")
                print("  preview intent_analysis [query='今天有什么新闻']")
                print("  preview news_summary [language=zh]")
                print("  render intent_analysis")
                print("  render news_summary [language=zh]")
                print("  test intent_analysis [query='今天有什么新闻']")
                print("  test news_summary [language=zh]")
                print("  compare")
                print()
            
            elif command == "preview":
                if len(parts) < 2:
                    print("❌ 用法: preview <template> [args]")
                    continue
                template = parts[1]
                kwargs = {}
                for part in parts[2:]:
                    if "=" in part:
                        k, v = part.split("=", 1)
                        kwargs[k] = v
                preview_template(template, **kwargs)
            
            elif command == "render":
                if len(parts) < 2:
                    print("❌ 用法: render <template> [args]")
                    continue
                template = parts[1]
                kwargs = {}
                for part in parts[2:]:
                    if "=" in part:
                        k, v = part.split("=", 1)
                        kwargs[k] = v
                test_render(template, **kwargs)
            
            elif command == "test":
                if len(parts) < 2:
                    print("❌ 用法: test <template> [args]")
                    continue
                template = parts[1]
                kwargs = {}
                for part in parts[2:]:
                    if "=" in part:
                        k, v = part.split("=", 1)
                        kwargs[k] = v
                await test_llm_call(template, **kwargs)
            
            elif command == "compare":
                compare_languages()
            
            else:
                print(f"❌ 未知命令: {command}，输入 help 查看帮助")
        
        except KeyboardInterrupt:
            print("\n👋 再见！")
            break
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()


# ==================== 主函数 ====================

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Prompt 调试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 预览意图分析模板
  python debug_prompt.py --template intent_analysis --preview
  
  # 测试新闻摘要模板渲染（中文）
  python debug_prompt.py --template news_summary --test-render --language zh
  
  # 实际调用 LLM 测试新闻摘要（英文）
  python debug_prompt.py --template news_summary --test-llm --language en
  
  # 对比不同语言的 prompt
  python debug_prompt.py --compare
  
  # 交互式调试模式
  python debug_prompt.py --interactive
        """
    )
    
    parser.add_argument(
        '--template',
        type=str,
        choices=['intent_analysis', 'news_summary'],
        help='模板名称'
    )
    parser.add_argument(
        '--preview',
        action='store_true',
        help='预览模板（原始和渲染后）'
    )
    parser.add_argument(
        '--test-render',
        action='store_true',
        help='测试模板渲染'
    )
    parser.add_argument(
        '--test-llm',
        action='store_true',
        help='实际调用 LLM 测试 prompt 效果'
    )
    parser.add_argument(
        '--compare',
        action='store_true',
        help='对比不同语言的 prompt'
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='交互式调试模式'
    )
    parser.add_argument(
        '--query',
        type=str,
        help='用户查询（用于 intent_analysis 模板）'
    )
    parser.add_argument(
        '--language',
        type=str,
        choices=['zh', 'en', 'ko'],
        default='zh',
        help='目标语言（用于 news_summary 模板）'
    )
    
    args = parser.parse_args()
    
    # 如果没有参数，显示帮助
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    
    success = True
    
    try:
        if args.interactive:
            asyncio.run(interactive_mode())
        
        elif args.compare:
            success = compare_languages()
        
        elif args.template:
            kwargs = {}
            if args.query:
                kwargs['query'] = args.query
            if args.language:
                kwargs['language'] = args.language
            
            if args.preview:
                success = preview_template(args.template, **kwargs)
            elif args.test_render:
                success = test_render(args.template, **kwargs)
            elif args.test_llm:
                success = asyncio.run(test_llm_call(args.template, **kwargs))
            else:
                print("❌ 请指定操作: --preview, --test-render, 或 --test-llm")
                parser.print_help()
                success = False
        else:
            parser.print_help()
            success = False
    
    except KeyboardInterrupt:
        print("\n\n👋 已取消")
        return 0
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

