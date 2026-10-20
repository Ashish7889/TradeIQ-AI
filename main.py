import logging
import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

# Load environment variables FIRST before any service imports
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

import uvicorn

from database import Base, engine
from routers import api, auth

# Create DB tables
Base.metadata.create_all(bind=engine)

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from limiter import limiter

app = FastAPI(
    title="StockSense AI",
    description="Elite quantitative financial research terminal powered by LangChain + Groq AI",
    version="3.0.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
        f"[APM] {request.method} {request.url.path} | Status: {response.status_code} | Latency: {process_time:.4f}s"
    )
    return response


# Ensure static directory exists
os.makedirs("static", exist_ok=True)


# Cached static files with immutable Cache-Control for versioned assets
class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code < 400:
            if path.endswith(".html") or path == "":
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            else:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


# Mount the static directory
app.mount("/static", CachedStaticFiles(directory="static"), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    favicon_path = os.path.join("static", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/x-icon", headers={"Cache-Control": "public, max-age=86400"})
    return Response(status_code=404)


@app.api_route("/", methods=["GET", "HEAD"])
def serve_frontend():
    index_file = os.path.join("static", "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"message": "StockSense QuantCore v3.0 — Institutional Engine Active"}


@app.api_route("/health", methods=["GET", "HEAD"])
@app.api_route("/healthz", methods=["GET", "HEAD"])
def health_check():
    return {
        "status": "ok",
        "version": "3.0.0",
        "pipeline": "QuantCore Sequential Pipeline",
        "llm": "QuantCore 3.0 (Institutional Tier)",
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    reload = os.environ.get("ENV") != "production"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
