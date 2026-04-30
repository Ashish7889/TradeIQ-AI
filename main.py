import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import time
import logging
from dotenv import load_dotenv

# Load environment variables FIRST before any service imports
load_dotenv()

from database import engine, Base
from routers import api, auth
import uvicorn

# Create DB tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="StockSense AI",
    description="Elite quantitative financial research terminal powered by LangChain + Groq AI",
    version="3.0.0",
)

app.include_router(api.router, prefix="/api")
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])

# --- APM Observability Middleware ---
logger = logging.getLogger("stocksense.apm")

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    
    # Structured log for observability (Datadog/ELK ready)
    logger.info(
        f"[APM] {request.method} {request.url.path} | "
        f"Status: {response.status_code} | "
        f"Latency: {process_time:.4f}s"
    )
    return response

# Ensure static directory exists
os.makedirs("static", exist_ok=True)

# Mount the static directory
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_frontend():
    index_file = os.path.join("static", "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "StockSense QuantCore v3.0 — Institutional Engine Active"}

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "version": "3.0.0",
        "pipeline": "QuantCore Sequential Pipeline",
        "llm": "QuantCore 3.0 (Institutional Tier)",
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
