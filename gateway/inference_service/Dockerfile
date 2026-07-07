FROM python:3.11-slim@sha256:b27df5841f3355e9473f9a516d38a6783b6c8dfeacaf2d14a240f443b368ddb6
WORKDIR /app
COPY gateway/inference_service /app/gateway/inference_service
ENV PYTHONPATH=/app
CMD ["python", "-m", "gateway.inference_service.app"]
