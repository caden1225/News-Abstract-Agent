docker run -d \
    --name "news-tts-agent-dev" \
    -p "8080:8080" \
    -v "/home/caden/workspace:/home/caden/workspace" \
    -v "/home/caden/models:/home/caden/models" \
    -e PYTHONUNBUFFERED=1 \
    -e TZ=Asia/Shanghai \
    "news-agent-dev:20260116_ready" \
    /bin/bash -c "while true; do sleep 3600; done"