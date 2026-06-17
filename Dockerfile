FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY frontend/dist/ frontend/dist/

EXPOSE 9000 9001

CMD ["sh", "-c", "if [ \"$ROLE\" = 'worker' ]; then uvicorn app.worker:worker_app --host 0.0.0.0 --port ${WORKER_PORT:-9001}; else uvicorn app.main:app --host 0.0.0.0 --port 9000; fi"]
