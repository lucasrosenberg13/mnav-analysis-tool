FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Use python main.py since it already handles PORT correctly
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
