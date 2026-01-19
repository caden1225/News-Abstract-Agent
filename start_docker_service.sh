#!/bin/bash
# News TTS Agent - Docker 容器启动脚本

set -e

# 配置变量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="news-tts-agent-dev"
IMAGE_NAME="${PROJECT_NAME}:latest"
BASE_IMAGE="news-agent-dev:20260116_ready"
CONTAINER_NAME="${PROJECT_NAME}-container"
DOCKERFILE_PATH="${SCRIPT_DIR}/docker/Dockerfile"
PORT=8080

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

echo "=================================="
echo "News TTS Agent - Docker 容器启动"
echo "=================================="

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    print_error "Docker 未安装，请先安装 Docker"
    exit 1
fi
print_info "Docker 已安装"

# 检查 Docker 服务是否运行
if ! docker info &> /dev/null; then
    print_error "Docker 服务未运行，请启动 Docker 服务"
    exit 1
fi
print_info "Docker 服务正在运行"

# 检查基础镜像是否存在
if ! docker images | grep -q "^${BASE_IMAGE%:*}"; then
    print_warn "基础镜像 ${BASE_IMAGE} 不存在"
    print_warn "请确保基础镜像已构建或从仓库拉取"
    read -p "是否继续构建应用镜像? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    print_info "基础镜像 ${BASE_IMAGE} 存在"
fi

# 检查 Dockerfile 是否存在
if [ ! -f "${DOCKERFILE_PATH}" ]; then
    print_error "Dockerfile 不存在: ${DOCKERFILE_PATH}"
    exit 1
fi
print_info "Dockerfile 存在: ${DOCKERFILE_PATH}"

# 检查容器状态
if docker ps | grep -q "${CONTAINER_NAME}"; then
    print_warn "容器 ${CONTAINER_NAME} 已在运行中"
    echo ""
    echo "📋 查看日志: docker logs -f ${CONTAINER_NAME}"
    echo "🛑 停止容器: docker stop ${CONTAINER_NAME}"
    echo "🌐 API地址: http://localhost:${PORT}"
    echo "📚 文档地址: http://localhost:${PORT}/docs"
    echo ""
    read -p "是否要查看容器日志? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker logs -f "${CONTAINER_NAME}"
    fi
    exit 0
elif docker ps -a | grep -q "${CONTAINER_NAME}"; then
    print_warn "发现已停止的容器: ${CONTAINER_NAME}"
    read -p "是否启动已存在的容器? (y/n，选n将删除并重建) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🚀 启动已存在的容器..."
        docker start "${CONTAINER_NAME}"
        if [ $? -eq 0 ]; then
            print_info "容器启动成功"
            echo ""
            echo "=================================="
            echo "容器信息:"
            echo "=================================="
            docker ps | grep "${CONTAINER_NAME}"
            echo ""
            echo "📋 查看日志: docker logs -f ${CONTAINER_NAME}"
            echo "🛑 停止容器: docker stop ${CONTAINER_NAME}"
            echo "🌐 API地址: http://localhost:${PORT}"
            echo "📚 文档地址: http://localhost:${PORT}/docs"
            echo ""
            read -p "是否要查看容器日志? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                docker logs -f "${CONTAINER_NAME}"
            fi
        else
            print_error "容器启动失败"
            exit 1
        fi
        exit 0
    else
        echo "正在删除旧容器..."
        docker rm "${CONTAINER_NAME}" 2>/dev/null || true
        print_info "旧容器已删除"
    fi
fi

# 构建 Docker 镜像
echo ""
echo "🔨 开始构建 Docker 镜像..."
echo "   镜像名称: ${IMAGE_NAME}"
echo "   Dockerfile: ${DOCKERFILE_PATH}"
echo ""

cd "${SCRIPT_DIR}"
docker build -f "${DOCKERFILE_PATH}" -t "${IMAGE_NAME}" .

if [ $? -eq 0 ]; then
    print_info "镜像构建成功"
else
    print_error "镜像构建失败"
    exit 1
fi

# 运行容器
echo ""
echo "🚀 启动 Docker 容器..."
echo "   容器名称: ${CONTAINER_NAME}"
echo "   端口映射: ${PORT}:8080"
echo "   镜像: ${IMAGE_NAME}"
echo ""

# 创建数据目录挂载点（如果需要持久化数据）
DATA_DIR="${SCRIPT_DIR}/data"
mkdir -p "${DATA_DIR}"

# 运行容器
docker run -d \
    --name "${CONTAINER_NAME}" \
    -p "${PORT}:8080" \
    -v "${DATA_DIR}:/home/caden/${PROJECT_NAME}/data" \
    -v "${SCRIPT_DIR}/config:/home/caden/${PROJECT_NAME}/config" \
    --restart unless-stopped \
    "${IMAGE_NAME}"

if [ $? -eq 0 ]; then
    print_info "容器启动成功"
    echo ""
    echo "等待服务启动..."
    sleep 2
    
    echo "=================================="
    echo "容器信息:"
    echo "=================================="
    docker ps | grep "${CONTAINER_NAME}"
    echo ""
    echo "=================================="
    echo "服务信息:"
    echo "=================================="
    echo "📋 查看日志: docker logs -f ${CONTAINER_NAME}"
    echo "🛑 停止容器: docker stop ${CONTAINER_NAME}"
    echo "🗑️  删除容器: docker rm ${CONTAINER_NAME}"
    echo "🔄 重启容器: docker restart ${CONTAINER_NAME}"
    echo ""
    echo "🌐 API地址: http://localhost:${PORT}"
    echo "📚 文档地址: http://localhost:${PORT}/docs"
    echo "❤️  健康检查: http://localhost:${PORT}/health"
    echo ""
    
    # 显示最近的日志
    echo "=================================="
    echo "最近的服务日志:"
    echo "=================================="
    docker logs --tail 20 "${CONTAINER_NAME}"
    echo ""
    
    read -p "是否要实时查看服务日志? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "按 Ctrl+C 退出日志查看"
        docker logs -f "${CONTAINER_NAME}"
    else
        print_info "容器正在运行中，服务已启动"
        echo "提示: 使用 'docker logs -f ${CONTAINER_NAME}' 查看实时日志"
    fi
else
    print_error "容器启动失败"
    exit 1
fi
