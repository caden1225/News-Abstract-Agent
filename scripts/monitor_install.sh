#!/bin/bash
# 实时监控 TensorRT 安装进度

PID=2049293
CHILD_PID=2049510

echo "=========================================="
echo "TensorRT 安装实时监控"
echo "=========================================="
echo "主进程 PID: $PID"
echo "子进程 PID: $CHILD_PID"
echo ""

# 检查进程是否还在运行
if ! ps -p $PID > /dev/null 2>&1; then
    echo "❌ 主进程已结束"
    exit 1
fi

if ! ps -p $CHILD_PID > /dev/null 2>&1; then
    echo "❌ 子进程已结束"
    exit 1
fi

echo "✅ 进程正在运行"
echo ""

# 监控循环
for i in {1..10}; do
    echo "--- 检查 #$i ($(date +%H:%M:%S)) ---"
    
    # 主进程状态
    MAIN_STAT=$(ps -p $PID -o %cpu,%mem,etime,stat --no-headers 2>/dev/null)
    echo "主进程: $MAIN_STAT"
    
    # 子进程状态
    CHILD_STAT=$(ps -p $CHILD_PID -o %cpu,%mem,etime,stat,wchan --no-headers 2>/dev/null)
    echo "子进程: $CHILD_STAT"
    
    # 网络连接
    NETWORK=$(ss -tnp 2>/dev/null | grep "$PID\|$CHILD_PID" | wc -l)
    echo "网络连接数: $NETWORK"
    
    # 检查临时文件
    TEMP_FILES=$(find /var/tmp -name "tmp*" -user $USER 2>/dev/null | wc -l)
    echo "临时文件数: $TEMP_FILES"
    
    # 检查磁盘IO（如果可用）
    if command -v iostat > /dev/null 2>&1; then
        DISK_IO=$(iostat -x 1 1 2>/dev/null | grep -E "nvme|sda" | tail -1 | awk '{print "读:"$4"kB/s 写:"$5"kB/s"}')
        echo "磁盘IO: $DISK_IO"
    fi
    
    echo ""
    
    # 如果进程结束，退出
    if ! ps -p $PID > /dev/null 2>&1; then
        echo "安装进程已结束"
        break
    fi
    
    sleep 5
done

echo ""
echo "=========================================="
echo "检查安装结果..."
echo "=========================================="

# 检查是否安装成功
if command -v conda > /dev/null 2>&1; then
    conda activate 310 2>/dev/null
    pip list | grep -i tensorrt && echo "✅ TensorRT 安装成功！" || echo "❌ TensorRT 未安装"
fi
