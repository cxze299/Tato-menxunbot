FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tzdata ca-certificates && rm -rf /var/lib/apt/lists/*

COPY bot.py admin_key.py set_admin_key.py healthcheck.py ./
COPY reference/menxun_bot.py ./reference/menxun_bot.py

RUN mkdir -p /app/data && python -m py_compile bot.py admin_key.py set_admin_key.py healthcheck.py reference/menxun_bot.py

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=4 CMD ["python", "healthcheck.py"]
CMD ["python", "bot.py"]
