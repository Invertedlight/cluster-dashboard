FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

RUN useradd --create-home --uid 1000 appuser
COPY pyproject.toml README.md alembic.ini ./
COPY app ./app
COPY alembic ./alembic
RUN pip install --no-cache-dir . && chown -R appuser:appuser /app

USER appuser
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
