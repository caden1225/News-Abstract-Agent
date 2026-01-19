#!/bin/bash
# TensorRT 安装脚本 - 解决安装卡住问题

set -e

echo "=========================================="
echo "TensorRT 安装辅助脚本"
echo "=========================================="

# 检查 CUDA 版本
echo "检查 CUDA 版本..."
if command -v nvcc &> /dev/null; then
    CUDA_VERSION=$(nvcc --version | grep "release" | sed 's/.*release \([0-9]\+\.[0-9]\+\).*/\1/')
    echo "检测到 CUDA 版本: $CUDA_VERSION"
else
    echo "警告: 未找到 nvcc，请确保 CUDA 已正确安装"
fi

# 方案1: 使用 pip 安装（增加超时和重试）
echo ""
echo "方案1: 使用 pip 安装（推荐）"
echo "----------------------------------------"
echo "正在尝试安装 tensorrt（使用官方 PyPI 源，增加超时时间）..."

# 先取消之前的安装（如果卡住了）
pkill -f "pip install tensorrt" 2>/dev/null || true

# 使用官方源安装，增加超时时间
pip install --timeout=1000 --retries=5 tensorrt || {
    echo "pip 安装失败，尝试其他方案..."
}

# 方案2: 手动下载 wheel 文件安装
echo ""
echo "方案2: 手动下载 wheel 文件（如果方案1失败）"
echo "----------------------------------------"
echo "访问以下链接下载对应版本的 wheel 文件："
echo "https://pypi.org/project/tensorrt/#files"
echo ""
echo "然后使用以下命令安装："
echo "pip install tensorrt-*.whl"

# 方案3: 使用 NVIDIA 官方安装方法
echo ""
echo "方案3: 从 NVIDIA 官方安装（最可靠）"
echo "----------------------------------------"
echo "1. 访问: https://developer.nvidia.com/tensorrt"
echo "2. 下载对应 CUDA 版本的 TensorRT tar 包"
echo "3. 解压后安装 Python 包："
echo "   cd TensorRT-*/python"
echo "   pip install tensorrt-*-cp3*-linux_x86_64.whl"

echo ""
echo "=========================================="
echo "注意:"
echo "1. TensorRT 安装包很大（可能几GB），需要良好的网络连接"
echo "2. 如果不需要 TensorRT 加速，可以在 config.yaml 中设置 tensorrt: false"
echo "3. FP16 加速已经可以提供 2倍速度提升，不一定需要 TensorRT"
echo "=========================================="
