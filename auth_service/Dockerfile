# Stage 1: Build stage
FROM python:3.13-slim AS builder

RUN apt-get update && apt-get install -y \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Stage 2: Runtime stage
FROM python:3.13-slim

RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -r appuser
WORKDIR /app

COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy code
COPY --chown=appuser:appuser . .


# Django env
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV BASE_ROUTE=/auth

# Create dirs
RUN mkdir -p /app/email_files /app/Logs /app/staticfiles && \
    chown -R appuser:appuser /app/email_files /app/Logs /app/staticfiles

RUN cp -r /usr/local/lib/python3.13/site-packages/rest_framework/static/rest_framework /app/staticfiles/
RUN cp -r /usr/local/lib/python3.13/site-packages/drf_yasg/static/drf-yasg /app/staticfiles/

USER appuser

EXPOSE 8001

CMD ["gunicorn", "--bind", "0.0.0.0:8001", "--workers", "3", "auth_service.wsgi:application"]
