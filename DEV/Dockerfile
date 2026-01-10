# FilePath: /DEV/Dockerfile
# Base image: Python 3.13+ (Slim version for mindre image size)
FROM python:3.13-slim

# Set environment variables for bedre Python afvikling i Docker
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Create work directory
WORKDIR /app

# Install system dependencies
# Vi har brug for gcc og libpq-dev for at kunne bygge visse python-pakker (f.eks. database drivers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Vi kopierer requirements filen først for at udnytte Docker cache
COPY requirements.txt .

# Upgrade pip og installer dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy resten af applikationskoden ind i containeren
COPY . .

# Opret logs mappen (så applikationen ikke fejler ved start)
RUN mkdir -p logs

# Expose porten som Orchestrator kører på
EXPOSE 8000

# Start Orchestrator Serveren
# Vi bruger array-syntaks for bedre signal-håndtering (Ctrl+C virker hurtigere)
CMD ["uvicorn", "orchestrator.orchestrator_server:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
