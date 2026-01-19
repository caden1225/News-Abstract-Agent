#!/bin/bash
# 开发容器管理脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker 未运行，请先启动 Docker"
    exit 1
fi

# 如果第一个参数是 clean，则清理悬空镜像
if [ "$1" == "clean" ]; then
    echo "🧹 清理悬空镜像（<none>:<none>）..."
    DANGLING_IMAGES=$(docker images -f "dangling=true" -q)
    if [ -z "$DANGLING_IMAGES" ]; then
        echo "✅ 没有悬空镜像需要清理"
    else
        docker rmi $DANGLING_IMAGES
        echo "✅ 已清理悬空镜像"
    fi
    exit 0
fi

CONTAINER_NAME="news-tts-agent-dev-gpu"
IMAGE="b8088d01bb1e"

# 检查容器是否已存在
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "✅ 容器已在运行中"
        docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    else
        echo "🔄 启动已存在的容器..."
        docker start ${CONTAINER_NAME}
        echo "✅ 容器已启动"
    fi
else
    echo "🚀 创建并启动新容器..."
    docker run -d \
        --name ${CONTAINER_NAME} \
        --gpus all \
        --network host \
        --workdir /home/caden/workspace/news-tts-agent \
        -v /home/caden/workspace:/home/caden/workspace:cached \
        -v /home/caden/models:/home/caden/models:cached \
        -e PYTHONUNBUFFERED=1 \
        -e TZ=Asia/Shanghai \
        -it \
        ${IMAGE} \
        /bin/bash -c "while true; do sleep 3600; done"
    echo "✅ 容器已启动"
fi

echo ""
echo "在 Cursor 中连接:"
echo "  1. 按 Ctrl+Shift+P"
echo "  2. 选择: Dev Containers: Attach to Running Container"
echo "  3. 选择: ${CONTAINER_NAME}"
echo ""
echo "停止容器: docker stop ${CONTAINER_NAME}"
echo "删除容器: docker rm -f ${CONTAINER_NAME}"

