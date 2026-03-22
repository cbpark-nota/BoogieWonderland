FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY collect_daily.py .
COPY crontab /etc/cron.d/collector-cron

RUN chmod 0644 /etc/cron.d/collector-cron \
    && crontab /etc/cron.d/collector-cron \
    && touch /var/log/cron.log

# 환경변수를 cron에서도 사용할 수 있도록
CMD printenv > /etc/environment && cron && tail -f /var/log/cron.log
