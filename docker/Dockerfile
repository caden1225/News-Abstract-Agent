# Python Agent Dockerfile for News TTS Agent
# 使用与参考项目相同的基础镜像
FROM news-agent-dev:20260119_ready_1

# 指定运行时的系统环境变量
ENV APP_NAME=news-tts-agent \
    APP_HOME=/home/caden/${APP_NAME} \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

# 安装 tzdata（Python zoneinfo 模块需要）
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

# 设置时区
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 复制依赖文件
COPY requirements.txt /tmp/requirements.txt
# COPY /home/caden/c2_module /home/caden/c2_module  # 注释：该目录不在构建上下文中，如需使用请先将其复制到构建上下文或使用相对路径
# # 安装Python依赖
# RUN eval "$(micromamba shell hook --shell bash)" && \
#     micromamba activate /opt/conda && \
#     pip install --no-cache-dir -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r /tmp/requirements.txt && \
#     mkdir -p ${APP_HOME}/

# 复制应用代码
COPY . ${APP_HOME}
WORKDIR ${APP_HOME}

# 设置执行权限
RUN chmod +x ${APP_HOME}/start.sh

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# 启动命令 - 使用 start.sh
ENTRYPOINT ${APP_HOME}/start.sh
