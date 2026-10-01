FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (cached across builds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Run gunicorn directly (port is dynamically injected by Railway via $PORT)
CMD ["sh", "-c", "gunicorn --workers 2 --bind 0.0.0.0:${PORT:-8080} tron_app:app"]