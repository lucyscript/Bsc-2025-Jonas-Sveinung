FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app

# Install system dependencies including Tesseract-OCR
RUN apt-get update && apt-get install -y \
    build-essential \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the src directory from your repository so that the folder structure remains
COPY ./src ./src

# Expose the port the app runs on
EXPOSE 8080

# Command to run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
