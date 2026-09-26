FROM python:3.12-alpine

ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

WORKDIR /app
COPY bot.py admin_key.py set_admin_key.py healthcheck.py ./
COPY reference/menxun_bot.py ./reference/menxun_bot.py

RUN mkdir -p /app/data && python -m py_compile bot.py admin_key.py set_admin_key.py healthcheck.py reference/menxun_bot.py

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=4 CMD ["python", "healthcheck.py"]
CMD ["python", "bot.py"]
