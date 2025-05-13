FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    netcat-openbsd \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Clean any existing directories to avoid conflicts with volume mounts
RUN rm -rf media/uploads || true

# Create necessary directories with clean structure
RUN mkdir -p media staticfiles data logs
RUN mkdir -p media/uploads
RUN chmod -R 777 data media staticfiles logs

# Make start script executable
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8000

CMD ["./start.sh"] 