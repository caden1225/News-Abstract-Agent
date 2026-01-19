#!/bin/bash
# 数据库实时同步脚本

REMOTE_USER="caden"
REMOTE_HOST="10.109.253.69"
REMOTE_PATH="/home/${REMOTE_USER}/news-tts-agent/data"
DB_FILE="/home/caden/workspace/news-tts-agent/data/news.db"

# 确保远程目录存在
ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p ${REMOTE_PATH}" 2>&1

# 监控文件变化并同步
inotifywait -m -e close_write --format '%w%f' "$DB_FILE" 2>&1 | while read file; do
    echo "$(date '+%Y-%m-%d %H:%M:%S') - 检测到变化，开始同步..."
    rsync -avz -e "ssh" "$DB_FILE" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/" 2>&1
    echo "$(date '+%Y-%m-%d %H:%M:%S') - 同步完成"
done

