#!/usr/bin/env python3
"""
Prompt 预览和测试工具

使用方法：
    python prompts/preview.py --template news_summary
    python prompts/preview.py --test
"""
import sys
import json
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from prompts import (
    PromptManager,
    get_prompt_manager,
    build_news_summary_prompt,
)


def preview_template(template_name: str, version: str = "default"):
    """预览模板内容"""
    manager = get_prompt_manager()

    print(f"\n{'='*70}")
    print(f"预览模板: {template_name} (版本: {version})")
    print(f"{'='*70}\n")

    try:
        # 加载并渲染模板（使用示例数据）
        rendered = manager.render_template(
            template_name,
            version=version,
            language_instruction="请使用中文",
            news_items="1. 示例新闻标题：示例新闻内容"
        )

        # 显示 System Prompt
        if rendered["system"]:
            print("【System Prompt】")
            print(rendered["system"])
            print()

        # 显示 User Prompt
        print("【User Prompt】")
        print(rendered["user"])
        print()
        print(f"{'='*70}")
        print(f"✅ 模块: prompts.templates.{template_name}")
        print(f"{'='*70}\n")

    except FileNotFoundError as e:
        print(f"❌ 错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

    return True


def test_news_summary_prompt():
    """测试新闻摘要 prompt 生成"""
    print(f"\n{'='*70}")
    print("测试：新闻摘要 Prompt 生成")
    print(f"{'='*70}\n")

    # 测试数据
    test_news = [
        {
            "title": "人工智能技术取得重大突破",
            "summary": "研究团队在深度学习领域取得突破性进展，新算法在图像识别任务中超越人类水平。专家认为这将推动自动驾驶技术的快速发展。"
        },
        {
            "title": "全球气候峰会达成新协议",
            "summary": "各国代表在气候峰会上达成减排新协议，承诺在2030年前减少50%的碳排放。环保组织对此表示欢迎。"
        },
        {
            "title": "新型电池技术问世",
            "summary": "科技公司宣布研发出新型固态电池，续航里程提升100%，充电时间缩短至10分钟。这将彻底改变电动汽车行业格局。"
        }
    ]

    # 中文版本
    print("\n【中文版本】")
    print("-" * 70)
    prompt_zh = build_news_summary_prompt(test_news, target_language="zh", version="default")
    print(prompt_zh[:500] + "..." if len(prompt_zh) > 500 else prompt_zh)

    # 英文版本
    print("\n【英文版本】")
    print("-" * 70)
    prompt_en = build_news_summary_prompt(test_news, target_language="en", version="default")
    print(prompt_en[:500] + "..." if len(prompt_en) > 500 else prompt_en)

    # 简单版本
    print("\n【简单版本】")
    print("-" * 70)
    prompt_simple = build_news_summary_prompt(test_news, target_language="zh", version="simple")
    print(prompt_simple)

    print(f"\n{'='*70}")
    print(f"✅ 测试完成")
    print(f"{'='*70}\n")

    return True


def list_all_prompts():
    """列出所有可用的 prompts"""
    manager = get_prompt_manager()

    print(f"\n{'='*70}")
    print("可用的 Prompt 模板")
    print(f"{'='*70}\n")

    # 列出模板
    templates = manager.list_templates()
    print("【Prompt 模板】")
    for template in templates:
        print(f"  📄 {template}")

    print(f"\n{'='*70}")
    print(f"✅ 共 {len(templates)} 个模板")
    print(f"{'='*70}\n")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Prompt 预览和测试工具")
    parser.add_argument(
        '--template',
        type=str,
        help='预览模板（如 news_summary, intent_analysis）'
    )
    parser.add_argument(
        '--version',
        type=str,
        default='default',
        help='模板版本（默认: default）'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='运行测试'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='列出所有可用的 prompts'
    )

    args = parser.parse_args()

    # 如果没有参数，显示帮助
    if len(sys.argv) == 1:
        parser.print_help()
        return

    # 执行相应的操作
    success = True

    if args.list:
        list_all_prompts()
    elif args.template:
        success = preview_template(args.template, args.version)
    elif args.test:
        success = test_news_summary_prompt()
    else:
        parser.print_help()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
