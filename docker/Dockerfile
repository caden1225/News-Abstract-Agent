# Python Agent Dockerfile for News TTS Agent
# 使用与参考项目相同的基础镜像
FROM ebanma/banma-nlu-aliyun_base:20250827141948

# 指定运行时的系统环境变量
ENV APP_NAME=news-tts-agent \
    APP_HOME=/home/admin/${APP_NAME}/target \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

# 设置时区
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 复制依赖文件（从 APP-META 目录）
COPY APP-META/docker-config/environment/requirements.txt /tmp/requirements.txt

# 安装Python依赖
RUN eval "$(micromamba shell hook --shell bash)" && \
    micromamba activate /opt/conda && \
    pip install --no-cache-dir -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r /tmp/requirements.txt && \
    mkdir -p ${APP_HOME}/

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
