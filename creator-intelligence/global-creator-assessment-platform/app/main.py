import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import campaigns, closures, collections, comparisons, contracts, events, exports, imports, kols, migrations, monitoring, post_campaign, reinvestment, reviews, settings, shortlists, sync, workflows
from app.database import configure_database
from app.config import validate_weights
from app.security import SESSION_COOKIE, create_session_token, is_loopback_request, require_loopback_session

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(database_url: str | None = None, session_token: str | None = None) -> FastAPI:
    validate_weights()
    app = FastAPI(title="Creator Partnership Management Platform", version="3.0")
    app.state.session_token = session_token or create_session_token()
    configure_database(app, database_url)

    @app.middleware("http")
    async def local_session_security(request: Request, call_next):
        if not is_loopback_request(request):
            return JSONResponse(status_code=403, content={"detail": "Loopback access only"})
        protected_download = request.url.path.startswith("/exports/") or (
            request.url.path.startswith("/shortlists/") and request.url.path.endswith("/export")
        )
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} or protected_download:
            try:
                require_loopback_session(request)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def sanitized_settings_validation(request, exc):
        if request.url.path == "/settings/youtube":
            return JSONResponse(
                status_code=422,
                content={"detail": "Invalid YouTube settings request"},
            )
        from fastapi.exception_handlers import request_validation_exception_handler

        return await request_validation_exception_handler(request, exc)
    app.include_router(collections.router)
    app.include_router(imports.router)
    app.include_router(exports.router)
    app.include_router(kols.router)
    app.include_router(comparisons.router)
    app.include_router(shortlists.router)
    app.include_router(workflows.router)
    app.include_router(contracts.router)
    app.include_router(campaigns.router)
    app.include_router(monitoring.router)
    app.include_router(post_campaign.router)
    app.include_router(reinvestment.router)
    app.include_router(closures.router)
    app.include_router(reviews.router)
    app.include_router(migrations.router)
    app.include_router(settings.router)
    app.include_router(settings.cloud_router)
    app.include_router(sync.router)
    app.include_router(events.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def chinese_home() -> HTMLResponse:
        html = (STATIC_DIR / "index.html").read_text("utf-8")
        bootstrap = f'<script>window.__KOL_SESSION_TOKEN__ = {json.dumps(app.state.session_token)};</script>'
        html = html.replace("</head>", f"{bootstrap}\n</head>", 1)
        response = HTMLResponse(html)
        response.set_cookie(
            SESSION_COOKIE, app.state.session_token, max_age=300, httponly=True,
            secure=True, samesite="strict", path="/",
        )
        return response
    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "favicon.png",
            media_type="image/png",
    )
    
    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
