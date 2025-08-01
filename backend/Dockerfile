FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies with no cache to avoid conflicts
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose port
EXPOSE 8000

# Start the application - use shell form to handle environment variables
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}