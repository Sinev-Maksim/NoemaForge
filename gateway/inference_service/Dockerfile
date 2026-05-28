FROM python:3.11-slim
WORKDIR /app
COPY gateway/inference_service /app/gateway/inference_service
ENV PYTHONPATH=/app
CMD ["python", "-m", "gateway.inference_service.app"]
