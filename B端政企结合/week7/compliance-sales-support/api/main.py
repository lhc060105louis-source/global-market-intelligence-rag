# -*- coding: utf-8 -*-
"""B端 FastAPI 入口 —— 法规 / 客户支持 / 报告 / 项目
启动: uvicorn api.main:app --reload --port 8000
文档: http://localhost:8000/docs
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 确保项目根目录在 sys.path,服务层和 db 可 import
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

# 启动时初始化数据库
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
    title="B端政企 · 合规与销售支持 API",
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

# 静态前端(不用 mount,用路由返回 index.html,避免吞掉 API)
STATIC = Path(__file__).resolve().parent.parent / "static"
INDEX_HTML = (STATIC / "index.html").read_text(encoding="utf-8") if STATIC.exists() else ""


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    return INDEX_HTML or "<h1>static/index.html 未找到</h1>"
