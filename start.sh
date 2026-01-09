#!/bin/bash

# 新闻播报Agent启动脚本
# 参考 banma-nlu-aliyun 的启动方式

# 激活 conda 环境
eval "$(micromamba shell hook --shell bash)"
micromamba activate /opt/conda

# 设置环境变量
export APP_HOME=$PWD
export LOG_PATH=/home/logs/agent
export OMP_NUM_THREADS=1

# 设置默认的环境变量（如果未指定）
export TEST_MODE=${TEST_MODE:-true}
export USE_MOCK_TTS=${USE_MOCK_TTS:-true}

# 创建日志目录
mkdir -p $LOG_PATH

echo "========================================"
echo "Starting News TTS Agent..."
echo "========================================"
echo "APP_HOME: $APP_HOME"
echo "LOG_PATH: $LOG_PATH"
echo "TEST_MODE: $TEST_MODE"
echo "USE_MOCK_TTS: $USE_MOCK_TTS"
echo "========================================"

# 启动应用
cd $APP_HOME
exec uvicorn main:app --host 0.0.0.0 --port 8080
