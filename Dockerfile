FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for compiling some python packages like bcrypt)
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Default port (Render injects PORT=10000 by default)
ENV PORT=10000
EXPOSE 10000

# Command to run the application
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
