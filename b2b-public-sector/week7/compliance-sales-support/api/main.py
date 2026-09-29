# -*- coding: utf-8 -*-
"""FastAPI application for regulations, customer support, reports, and projects.
Run: uvicorn api.main:app --reload --port 8000
API documentation: http://localhost:8000/docs
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Add the project root to sys.path so the service layer and database modules can be imported.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from api.regulations import router as reg_router
from api.clients import router as client_router
from api.reports import router as report_router
from api.projects import router as project_router
from api.intelligence import router as intel_router
from api.rag import router as rag_router
from api.matching import router as matching_router
from api.auth import router as auth_router
from api.sprints import router as sprint_router
from api.tasks import router as task_router
from api.commercial import router as commercial_router
from api.product import router as product_router

# Initialize the database at startup.
import db
db.bootstrap()
from rss_scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        await stop_scheduler()

app = FastAPI(
    title="B2B Public Sector Compliance and Sales Support API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(reg_router)
app.include_router(client_router)
app.include_router(report_router)
app.include_router(project_router)
app.include_router(intel_router)
app.include_router(rag_router)
app.include_router(matching_router)
app.include_router(auth_router)
app.include_router(sprint_router)
app.include_router(task_router)
app.include_router(commercial_router)
app.include_router(product_router)

# Serve the frontend from a route so it does not intercept API requests.
STATIC = Path(__file__).resolve().parent.parent / "static"
INDEX_HTML = (STATIC / "index.html").read_text(encoding="utf-8") if STATIC.exists() else ""


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    return INDEX_HTML or "<h1>static/index.html was not found</h1>"
