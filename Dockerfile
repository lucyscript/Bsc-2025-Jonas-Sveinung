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

# Create a volume for persistent data storage
VOLUME ["/app/data"]

# Make sure the data directory exists and copy initial README
COPY ./data/README.md /app/data/

EXPOSE 8085

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8085"]
