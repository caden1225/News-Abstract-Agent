#!/bin/bash

# 新闻播报Agent启动脚本

eval "$(micromamba shell hook --shell bash)"
micromamba activate /opt/conda

export APP_HOME=$PWD
export LOG_PATH=/home/logs/agent
export OMP_NUM_THREADS=1

mkdir -p $LOG_PATH

echo "Starting News TTS Agent..."
echo "APP_HOME: $APP_HOME"
echo "LOG_PATH: $LOG_PATH"

# 启动应用
cd $APP_HOME
uvicorn main:app --host 0.0.0.0 --port 8080
