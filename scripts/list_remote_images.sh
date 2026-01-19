#!/bin/bash
# 查看远程 Docker 仓库中的镜像列表
# 用法:
#   ./list_remote_images.sh dockerhub <username>
#   ./list_remote_images.sh registry <registry-url> [repository-name]
#   ./list_remote_images.sh tags <registry-url> <repository-name>

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_usage() {
    echo "用法:"
    echo "  $0 dockerhub <username>                    # 查看 Docker Hub 上用户的所有仓库"
    echo "  $0 registry <registry-url> [repo]          # 查看私有 Registry 的仓库列表"
    echo "  $0 tags <registry-url> <repository-name>   # 查看指定仓库的所有标签"
    echo ""
    echo "示例:"
    echo "  $0 dockerhub ebanma"
    echo "  $0 registry registry.example.com"
    echo "  $0 tags registry.example.com ebanma/llm-agent"
}

# 检查依赖
check_dependencies() {
    if ! command -v curl &> /dev/null; then
        echo -e "${RED}错误: 需要安装 curl${NC}"
        exit 1
    fi
    
    if ! command -v jq &> /dev/null; then
        echo -e "${YELLOW}警告: 未安装 jq，输出可能不够美观${NC}"
        JQ_AVAILABLE=false
    else
        JQ_AVAILABLE=true
    fi
}

# 查询 Docker Hub
query_dockerhub() {
    local username=$1
    
    if [ -z "$username" ]; then
        echo -e "${RED}错误: 请提供用户名${NC}"
        print_usage
        exit 1
    fi
    
    echo -e "${GREEN}正在查询 Docker Hub 用户: ${username}${NC}"
    
    local url="https://hub.docker.com/v2/repositories/${username}/?page_size=100"
    local response=$(curl -s "$url")
    
    if [ "$JQ_AVAILABLE" = true ]; then
        echo "$response" | jq -r '.results[] | "\(.name) - \(.pull_count) pulls - \(.last_updated)"'
        local count=$(echo "$response" | jq '.count')
        echo -e "\n${GREEN}总计: ${count} 个仓库${NC}"
    else
        echo "$response" | grep -o '"name":"[^"]*"' | sed 's/"name":"//g' | sed 's/"//g'
    fi
}

# 查询私有 Registry 的仓库列表
query_registry_catalog() {
    local registry=$1
    local repo=$2
    
    if [ -z "$registry" ]; then
        echo -e "${RED}错误: 请提供 Registry 地址${NC}"
        print_usage
        exit 1
    fi
    
    # 移除协议前缀（如果有）
    registry=$(echo "$registry" | sed 's|^https\?://||')
    
    if [ -n "$repo" ]; then
        # 查询指定仓库的标签
        query_registry_tags "$registry" "$repo"
        return
    fi
    
    echo -e "${GREEN}正在查询 Registry: ${registry}${NC}"
    
    local url="https://${registry}/v2/_catalog?n=1000"
    local response=$(curl -s "$url")
    
    if echo "$response" | grep -q "unauthorized"; then
        echo -e "${RED}错误: 需要认证。请先登录: docker login ${registry}${NC}"
        exit 1
    fi
    
    if [ "$JQ_AVAILABLE" = true ]; then
        echo "$response" | jq -r '.repositories[]'
        local count=$(echo "$response" | jq '.repositories | length')
        echo -e "\n${GREEN}总计: ${count} 个仓库${NC}"
    else
        echo "$response" | grep -o '"[^"]*"' | sed 's/"//g'
    fi
}

# 查询指定仓库的所有标签
query_registry_tags() {
    local registry=$1
    local repo=$2
    
    if [ -z "$registry" ] || [ -z "$repo" ]; then
        echo -e "${RED}错误: 请提供 Registry 地址和仓库名${NC}"
        print_usage
        exit 1
    fi
    
    # 移除协议前缀（如果有）
    registry=$(echo "$registry" | sed 's|^https\?://||')
    
    echo -e "${GREEN}正在查询 ${registry}/${repo} 的所有标签...${NC}"
    
    local url="https://${registry}/v2/${repo}/tags/list"
    local response=$(curl -s "$url")
    
    if echo "$response" | grep -q "unauthorized\|UNAUTHORIZED"; then
        echo -e "${YELLOW}需要认证，尝试使用 Docker 凭证...${NC}"
        # 尝试从 Docker config 获取认证信息
        if [ -f "$HOME/.docker/config.json" ]; then
            local auth=$(cat "$HOME/.docker/config.json" | jq -r ".auths.\"${registry}\".auth" 2>/dev/null)
            if [ -n "$auth" ] && [ "$auth" != "null" ]; then
                response=$(curl -s -H "Authorization: Basic ${auth}" "$url")
            else
                echo -e "${RED}错误: 未找到认证信息。请先登录: docker login ${registry}${NC}"
                exit 1
            fi
        else
            echo -e "${RED}错误: 需要认证。请先登录: docker login ${registry}${NC}"
            exit 1
        fi
    fi
    
    if echo "$response" | grep -q "NAME_UNKNOWN\|not found"; then
        echo -e "${RED}错误: 仓库不存在${NC}"
        exit 1
    fi
    
    if [ "$JQ_AVAILABLE" = true ]; then
        local tags=$(echo "$response" | jq -r '.tags[]?' 2>/dev/null)
        if [ -n "$tags" ]; then
            echo "$tags"
            local count=$(echo "$tags" | wc -l)
            echo -e "\n${GREEN}总计: ${count} 个标签${NC}"
        else
            echo -e "${YELLOW}该仓库没有标签${NC}"
        fi
    else
        echo "$response" | grep -o '"tags":\[[^]]*\]' | sed 's/"tags":\[//g' | sed 's/\]//g' | tr ',' '\n' | sed 's/"//g'
    fi
}

# 主函数
main() {
    check_dependencies
    
    case "$1" in
        dockerhub)
            query_dockerhub "$2"
            ;;
        registry)
            query_registry_catalog "$2" "$3"
            ;;
        tags)
            query_registry_tags "$2" "$3"
            ;;
        *)
            print_usage
            exit 1
            ;;
    esac
}

main "$@"




