#!/usr/bin/env python3
"""
生成 LangGraph 工作流的可视化图

使用方法:
    python3 scripts/generate_langgraph_diagram.py

输出:
    - docs/langgraph_workflow.mmd (Mermaid 格式)
    - docs/langgraph_workflow.png (PNG 图片，如果可用)
    - docs/langgraph_workflow.txt (ASCII 格式)
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.graph.workflow import build_news_workflow


def generate_langgraph_diagrams():
    """生成 LangGraph 工作流的各种格式图表"""
    print("=" * 80)
    print(" " * 25 + "生成 LangGraph 工作流图表")
    print("=" * 80 + "\n")

    # 构建工作流
    print("📦 构建工作流...")
    workflow = build_news_workflow()
    
    # 获取图对象
    print("🔍 获取图对象...")
    graph = workflow.get_graph()
    
    # 输出目录
    docs_dir = Path(__file__).parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)
    
    # 1. 生成 Mermaid 格式
    print("\n📝 生成 Mermaid 格式...")
    try:
        mermaid_code = graph.draw_mermaid()
        mermaid_file = docs_dir / "langgraph_workflow.mmd"
        with open(mermaid_file, "w", encoding="utf-8") as f:
            f.write(mermaid_code)
        print(f"✅ Mermaid 文件已保存: {mermaid_file}")
        print(f"   大小: {len(mermaid_code)} 字符")
    except Exception as e:
        print(f"❌ 生成 Mermaid 格式失败: {e}")
    
    # 2. 生成 ASCII 格式
    print("\n📝 生成 ASCII 格式...")
    try:
        ascii_graph = graph.draw_ascii()
        ascii_file = docs_dir / "langgraph_workflow.txt"
        with open(ascii_file, "w", encoding="utf-8") as f:
            f.write(ascii_graph)
        print(f"✅ ASCII 文件已保存: {ascii_file}")
        print(f"   大小: {len(ascii_graph)} 字符")
    except Exception as e:
        print(f"❌ 生成 ASCII 格式失败: {e}")
    
    # 3. 生成 PNG 图片 (Mermaid)
    print("\n🖼️  生成 PNG 图片 (Mermaid)...")
    try:
        png_data = graph.draw_mermaid_png()
        png_file = docs_dir / "langgraph_workflow.png"
        with open(png_file, "wb") as f:
            f.write(png_data)
        print(f"✅ PNG 图片已保存: {png_file}")
        print(f"   大小: {len(png_data)} 字节")
    except Exception as e:
        print(f"⚠️  生成 PNG 图片失败: {e}")
        print("   提示: 可能需要安装 graphviz")
        print("   Ubuntu/Debian: sudo apt-get install graphviz")
        print("   macOS: brew install graphviz")
    
    # 4. 尝试生成标准 PNG (如果可用)
    print("\n🖼️  尝试生成标准 PNG...")
    try:
        png_data = graph.draw_png()
        png_file_std = docs_dir / "langgraph_workflow_std.png"
        with open(png_file_std, "wb") as f:
            f.write(png_data)
        print(f"✅ 标准 PNG 图片已保存: {png_file_std}")
        print(f"   大小: {len(png_data)} 字节")
    except Exception as e:
        print(f"⚠️  生成标准 PNG 失败: {e}")
    
    # 打印 Mermaid 代码预览
    print("\n" + "=" * 80)
    print(" " * 25 + "Mermaid 代码预览")
    print("=" * 80 + "\n")
    try:
        mermaid_code = graph.draw_mermaid()
        # 只显示前 50 行
        lines = mermaid_code.split('\n')
        preview = '\n'.join(lines[:50])
        print(preview)
        if len(lines) > 50:
            print(f"\n... (还有 {len(lines) - 50} 行，请查看完整文件)")
    except Exception as e:
        print(f"无法显示预览: {e}")
    
    print("\n" + "=" * 80)
    print(" " * 30 + "✅ 完成")
    print("=" * 80 + "\n")
    print("生成的文件:")
    print(f"  - {docs_dir / 'langgraph_workflow.mmd'} (Mermaid 格式)")
    print(f"  - {docs_dir / 'langgraph_workflow.txt'} (ASCII 格式)")
    if (docs_dir / "langgraph_workflow.png").exists():
        print(f"  - {docs_dir / 'langgraph_workflow.png'} (PNG 图片)")
    print("\n提示: Mermaid 文件可以在支持 Mermaid 的编辑器中查看（如 VS Code + Mermaid 插件）")


if __name__ == "__main__":
    generate_langgraph_diagrams()


