#!/bin/bash
# 检查 TensorRT 安装进程状态

echo "=========================================="
echo "TensorRT 安装进程状态检查"
echo "=========================================="
echo ""

# 查找相关进程
PIP_PIDS=$(pgrep -f "pip install tensorrt" 2>/dev/null)

if [ -z "$PIP_PIDS" ]; then
    echo "❌ 未找到 pip install tensorrt 进程"
    echo "安装可能已完成或已终止"
    exit 0
fi

echo "✅ 找到安装进程: $PIP_PIDS"
echo ""

# 检查主进程状态
for PID in $PIP_PIDS; do
    if ps -p $PID > /dev/null 2>&1; then
        echo "进程 PID: $PID"
        ps -p $PID -o pid,ppid,%cpu,%mem,etime,stat,cmd --no-headers | awk '{
            printf "  - CPU使用率: %s%%\n", $3
            printf "  - 内存使用: %s%%\n", $4
            printf "  - 运行时间: %s\n", $5
            printf "  - 状态: %s\n", $6
        }'
        
        # 检查进程状态详情
        STATE=$(cat /proc/$PID/status 2>/dev/null | grep "^State:" | awk '{print $2}')
        echo "  - 详细状态: $STATE"
        
        # 检查网络连接
        echo ""
        echo "网络连接状态:"
        ss -tnp 2>/dev/null | grep "pid=$PID" | awk '{
            if ($1 == "ESTABLISHED") printf "  ✅ 活跃连接: %s -> %s\n", $4, $5
            else if ($1 == "CLOSE_WAIT") printf "  ⚠️  关闭等待: %s -> %s\n", $4, $5
            else printf "  ℹ️  %s: %s -> %s\n", $1, $4, $5
        }' || echo "  ℹ️  无活跃网络连接（可能在编译或处理本地文件）"
        
        # 检查子进程
        CHILD_PIDS=$(pgrep -P $PID 2>/dev/null)
        if [ -n "$CHILD_PIDS" ]; then
            echo ""
            echo "子进程:"
            for CHILD in $CHILD_PIDS; do
                ps -p $CHILD -o pid,%cpu,%mem,cmd --no-headers 2>/dev/null | awk '{
                    printf "  - PID %s: CPU=%s%%, MEM=%s%%, CMD=%s\n", $1, $2, $3, substr($0, index($0,$4))
                }'
            done
        fi
        
        echo ""
    fi
done

# 检查是否有下载活动
echo "=========================================="
echo "下载/编译活动检查"
echo "=========================================="

# 检查磁盘IO
echo "检查磁盘活动（最近5秒）..."
if command -v iostat > /dev/null 2>&1; then
    iostat -x 1 2 2>/dev/null | tail -3 | grep -v "^$" || echo "无法获取磁盘IO统计"
else
    echo "iostat 未安装，跳过磁盘IO检查"
fi

# 检查 pip 缓存
echo ""
echo "检查 pip 缓存目录..."
if [ -d ~/.cache/pip ]; then
    CACHE_SIZE=$(du -sh ~/.cache/pip 2>/dev/null | awk '{print $1}')
    echo "  pip 缓存大小: $CACHE_SIZE"
    
    # 检查是否有 tensorrt 相关文件
    TENSORRT_FILES=$(find ~/.cache/pip -name "*tensorrt*" 2>/dev/null | wc -l)
    if [ "$TENSORRT_FILES" -gt 0 ]; then
        echo "  ✅ 找到 $TENSORRT_FILES 个 tensorrt 相关文件"
        find ~/.cache/pip -name "*tensorrt*" -type f 2>/dev/null | head -3 | while read file; do
            echo "    - $(basename $file) ($(du -h "$file" 2>/dev/null | awk '{print $1}'))"
        done
    else
        echo "  ℹ️  缓存中暂无 tensorrt 文件（可能正在下载或使用临时目录）"
    fi
else
    echo "  ℹ️  未找到 ~/.cache/pip 目录"
fi

# 检查 conda 环境中的 tensorrt
echo ""
echo "检查已安装的 tensorrt 包..."
if command -v conda > /dev/null 2>&1; then
    # 尝试检测当前激活的环境
    if [ -n "$CONDA_DEFAULT_ENV" ]; then
        ENV=$CONDA_DEFAULT_ENV
    else
        # 从进程路径推断
        ENV_PATH=$(ps -p $PIP_PIDS -o cmd --no-headers 2>/dev/null | head -1 | grep -o "/envs/[^/]*" | cut -d/ -f2)
        if [ -n "$ENV_PATH" ]; then
            ENV=$ENV_PATH
        fi
    fi
    
    if [ -n "$ENV" ]; then
        echo "  检测到环境: $ENV"
        if [ -d "/data/anaconda3/envs/$ENV/lib/python3.10/site-packages" ]; then
            TENSORRT_INSTALLED=$(find "/data/anaconda3/envs/$ENV/lib/python3.10/site-packages" -name "*tensorrt*" -type d 2>/dev/null | wc -l)
            if [ "$TENSORRT_INSTALLED" -gt 0 ]; then
                echo "  ✅ 找到已安装的 tensorrt 包目录"
            else
                echo "  ℹ️  环境中尚未安装 tensorrt"
            fi
        fi
    fi
fi

echo ""
echo "=========================================="
echo "建议"
echo "=========================================="
echo "1. 如果进程状态为 'S' (sleeping) 且有网络连接，说明正在下载"
echo "2. 如果进程 CPU 使用率 > 0%，说明正在处理（编译/解压）"
echo "3. TensorRT 安装包很大，可能需要 10-30 分钟"
echo "4. 如果长时间无活动，可以按 Ctrl+C 终止后重试"
echo "5. 如果不需要 TensorRT，可以在 config.yaml 中设置 tensorrt: false"
echo "=========================================="
