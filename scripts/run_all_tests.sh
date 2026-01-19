#!/bin/bash
# 运行所有测试脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "  运行所有测试和验证脚本"
echo "=========================================="

# 1. 验证优化是否生效
echo ""
echo "1. 验证优化是否生效..."
python3 "$SCRIPT_DIR/verify_optimizations.py"

# 2. 运行单元测试
echo ""
echo "2. 运行单元测试..."
if command -v pytest &> /dev/null; then
    pytest tests/ -v
else
    echo "⚠️  pytest未安装，跳过单元测试"
    echo "   安装命令: pip install pytest pytest-asyncio"
fi

# 3. 性能测试
echo ""
echo "3. 运行性能测试..."
python3 "$SCRIPT_DIR/performance_test.py"

# 4. 服务功能测试（如果服务正在运行）
echo ""
echo "4. 服务功能测试..."
if curl -s http://localhost:8080/health > /dev/null 2>&1; then
    echo "   检测到服务正在运行，开始功能测试..."
    python3 "$SCRIPT_DIR/test_service_functionality.py"
else
    echo "⚠️  服务未运行，跳过功能测试"
    echo "   启动服务后运行: python3 $SCRIPT_DIR/test_service_functionality.py"
fi

echo ""
echo "=========================================="
echo "  所有测试完成！"
echo "=========================================="
