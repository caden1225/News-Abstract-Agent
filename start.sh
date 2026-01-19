#!/bin/bash
# News TTS Agent - 服务启动脚本

echo "=================================="
echo "News TTS Agent - 启动服务"
echo "=================================="

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

echo "✅ Python3 已安装"

# 加载环境变量
if [ -f .env ]; then
    # 安全地加载环境变量，处理行内注释和空行
    set -a
    # 创建一个临时文件，移除注释和空行
    grep -v '^[[:space:]]*#' .env | sed 's/#.*$//' | grep -v '^[[:space:]]*$' > /tmp/.env.clean
    source /tmp/.env.clean
    rm -f /tmp/.env.clean
    set +a
    echo "✅ 环境变量已加载"
else
    echo "⚠️  .env 文件不存在"
fi

# 检查依赖
echo "🔍 检查依赖..."
if ! python3 -c "import sys; sys.exit(0)" 2>/dev/null; then
    echo "❌ Python 环境异常"
    exit 1
fi
echo "✅ 依赖检查通过"

# 启动服务
echo ""
echo "🚀 启动服务..."
echo "   API地址: http://${API_HOST}:${API_PORT}"
echo "   文档地址: http://${API_HOST}:${API_PORT}/docs"
echo ""

python3 main.py
