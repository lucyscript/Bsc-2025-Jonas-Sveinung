FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y \
    build-essential \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./src ./src

# Copy data directory and ensure it's writable
COPY ./data ./data
RUN chmod -R 777 ./data

EXPOSE 8085

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8085"]
