FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Non-root user for reduced attack surface
RUN useradd --no-create-home --shell /bin/false appuser

COPY app/ ./app/

# Change ownership to appuser
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Single worker — respects 150 MB memory limit defined in docker-compose
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
