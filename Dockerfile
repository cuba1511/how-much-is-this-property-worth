# FastAPI + Playwright Chromium (PDF reports). Scraping uses Bright Data CDP.
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/

WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1
ENV HV_DB_PATH=/data/prophero.db

EXPOSE 8000

# Railway/Render inject PORT; local default 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
