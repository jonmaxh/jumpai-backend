FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

USER root
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R pwuser:pwuser /app
USER pwuser

CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
