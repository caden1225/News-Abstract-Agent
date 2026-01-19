#!/bin/bash
# DBeaver 缓存清理脚本
# 注意：清理前请确保 DBeaver 已完全关闭

set -e

echo "开始清理 DBeaver 缓存..."

# DBeaver 缓存目录
DBEAVER_HOME="$HOME/.dbeaver"
DBEAVER_WORKSPACE="$HOME/.dbeaver/workspace6"

# 检查 DBeaver 是否在运行
if pgrep -x "dbeaver" > /dev/null; then
    echo "警告：检测到 DBeaver 正在运行，请先关闭 DBeaver 后再执行清理"
    exit 1
fi

# 清理工作区元数据缓存
if [ -d "$DBEAVER_WORKSPACE/.metadata" ]; then
    echo "清理工作区元数据缓存..."
    
    # 清理 Eclipse 核心资源缓存
    if [ -d "$DBEAVER_WORKSPACE/.metadata/.plugins/org.eclipse.core.resources/.projects" ]; then
        find "$DBEAVER_WORKSPACE/.metadata/.plugins/org.eclipse.core.resources/.projects" -type f -name "*.index" -delete 2>/dev/null || true
        find "$DBEAVER_WORKSPACE/.metadata/.plugins/org.eclipse.core.resources/.projects" -type d -name ".markers" -exec rm -rf {} + 2>/dev/null || true
        echo "  - 已清理项目索引和标记"
    fi
    
    # 清理工作台缓存
    if [ -d "$DBEAVER_WORKSPACE/.metadata/.plugins/org.eclipse.ui.workbench" ]; then
        find "$DBEAVER_WORKSPACE/.metadata/.plugins/org.eclipse.ui.workbench" -type f -name "*.bak" -delete 2>/dev/null || true
        find "$DBEAVER_WORKSPACE/.metadata/.plugins/org.eclipse.ui.workbench" -type f -name "workbench.xml.bak" -delete 2>/dev/null || true
        echo "  - 已清理工作台缓存"
    fi
    
    # 清理日志文件
    if [ -d "$DBEAVER_WORKSPACE/.metadata" ]; then
        find "$DBEAVER_WORKSPACE/.metadata" -type f -name "*.log" -delete 2>/dev/null || true
        find "$DBEAVER_WORKSPACE/.metadata" -type f -name ".log" -delete 2>/dev/null || true
        echo "  - 已清理日志文件"
    fi
    
    # 清理临时文件
    find "$DBEAVER_WORKSPACE/.metadata" -type f -name "*.tmp" -delete 2>/dev/null || true
    find "$DBEAVER_WORKSPACE/.metadata" -type f -name "*.temp" -delete 2>/dev/null || true
    echo "  - 已清理临时文件"
fi

# 清理配置缓存（可选，更彻底）
if [ "$1" == "--full" ]; then
    echo "执行完整清理（包括配置缓存）..."
    
    # 清理设置缓存
    if [ -d "$DBEAVER_WORKSPACE/.metadata/.plugins/org.eclipse.core.runtime/.settings" ]; then
        find "$DBEAVER_WORKSPACE/.metadata/.plugins/org.eclipse.core.runtime/.settings" -type f -name "*.prefs.bak" -delete 2>/dev/null || true
        echo "  - 已清理设置备份文件"
    fi
    
    # 清理插件缓存
    if [ -d "$DBEAVER_WORKSPACE/.metadata/.plugins" ]; then
        find "$DBEAVER_WORKSPACE/.metadata/.plugins" -type d -name ".cache" -exec rm -rf {} + 2>/dev/null || true
        echo "  - 已清理插件缓存"
    fi
fi

# 清理系统临时目录中的 DBeaver 文件
if [ -d "/tmp" ]; then
    find /tmp -type d -name "*dbeaver*" -exec rm -rf {} + 2>/dev/null || true
    find /tmp -type f -name "*dbeaver*" -delete 2>/dev/null || true
    echo "  - 已清理系统临时文件"
fi

echo "DBeaver 缓存清理完成！"
echo ""
echo "提示："
echo "  - 如果问题仍然存在，可以使用 --full 参数进行完整清理"
echo "  - 完整清理命令：$0 --full"
echo "  - 如需重置所有设置，可以删除整个工作区目录：rm -rf $DBEAVER_WORKSPACE"

