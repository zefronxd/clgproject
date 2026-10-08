FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py distress_keywords.py helplines.json insight_config.json ./
COPY templates/ ./templates/
COPY static/ ./static/

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/instance \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 5000

CMD ["sh", "-c", "exec gunicorn main:app --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 4 --timeout 90"]
