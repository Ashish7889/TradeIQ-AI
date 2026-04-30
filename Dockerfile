FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for compiling some python packages like bcrypt, pandas-ta)
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

# Expose port (Cloud Run uses 8080 by default, Render uses 10000, but we can set it via ENV)
ENV PORT=8080
EXPOSE 8080

# Command to run the application
CMD ["sh", "-c", "streamlit run streamlit_app.py --server.port ${PORT} --server.address 0.0.0.0"]
