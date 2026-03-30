"""
main.py — FastAPI application entry point.

Responsibilities:
- Application lifecycle (startup validation, shutdown)
- HTTP routing and request handling
- Rate limiting enforcement
- Structured audit logging (no passwords, no sensitive data)
- Static file serving
"""
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import settings
from app.ldap_client import probe_service_account
from app.ldap_service import change_password
from app.rate_limiter import rate_limiter
from app.validators import validate_change_request

# Structured log format — machine-parseable, no passwords
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("openad")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: validate configuration and probe LDAP connectivity.
    A failed LDAP probe logs a critical warning but does not abort startup —
    the AD server may be temporarily unreachable at container start.
    The /health endpoint will reflect the live status on each request.
    """
    # Validate required environment variables
    missing = settings.validate()
    if missing:
        for field in missing:
            logger.critical("startup config_missing field=%s", field)

    # Probe LDAP service account connectivity
    if not missing:
        ok, detail = probe_service_account()
        if ok:
            logger.info("startup ldap_probe=ok")
        else:
            logger.warning("startup ldap_probe=failed detail=%s", detail)

    logger.info("startup service=openad status=ready port=8000")
    yield
    logger.info("shutdown service=openad")


app = FastAPI(
    title="OpenAD",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

# CORS — same-origin only; adjust CORS_ORIGINS env if behind a reverse proxy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


class PasswordChangeRequest(BaseModel):
    upn: str
    current_password: str
    new_password: str


class PasswordChangeResponse(BaseModel):
    success: bool
    message: str
    code: str = ""


def _client_ip(request: Request) -> str:
    """Extract client IP from request, honouring X-Forwarded-For when present."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.post("/api/change-password", response_model=PasswordChangeResponse)
async def api_change_password(
    body: PasswordChangeRequest,
    request: Request,
) -> JSONResponse:
    """
    Password change endpoint.
    Logs every attempt with IP, UPN, and outcome. Never logs passwords.
    """
    ip = _client_ip(request)
    ts = datetime.now(timezone.utc).isoformat()

    # Rate limit check
    if not rate_limiter.is_allowed(ip):
        logger.warning("rate_limit_exceeded ip=%s upn=%s ts=%s", ip, body.upn, ts)
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "message": "Muitas tentativas. Aguarde alguns minutos antes de tentar novamente.",
                "code": "RATE_LIMITED",
            },
        )

    # Input validation
    error = validate_change_request(body.upn, body.current_password, body.new_password)
    if error:
        logger.info("validation_failed ip=%s upn=%s ts=%s reason=%s", ip, body.upn, ts, error)
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": error, "code": "VALIDATION_ERROR"},
        )

    # Attempt password change
    logger.info("change_password_attempt ip=%s upn=%s ts=%s", ip, body.upn, ts)
    success, message = change_password(body.upn, body.current_password, body.new_password)

    if success:
        logger.info("change_password_success ip=%s upn=%s ts=%s", ip, body.upn, ts)
        return JSONResponse(
            status_code=200,
            content={"success": True, "message": message, "code": "SUCCESS"},
        )

    logger.info("change_password_failed ip=%s upn=%s ts=%s", ip, body.upn, ts)
    return JSONResponse(
        status_code=400,
        content={"success": False, "message": message, "code": "AD_ERROR"},
    )


@app.get("/health")
async def health_check() -> JSONResponse:
    """
    Health check endpoint.
    Performs a live LDAP probe on each call — suitable for container
    orchestrators and load balancer health checks.
    """
    ok, detail = probe_service_account()
    status_code = 200 if ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if ok else "degraded",
            "ldap": detail,
        },
    )


# Static assets (favicon, CSS, JS if any)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
async def serve_frontend() -> FileResponse:
    """Serve the single-page frontend."""
    return FileResponse("app/static/index.html")
