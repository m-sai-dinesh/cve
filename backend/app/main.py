"""FastAPI application factory."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import routes_council, routes_projects, routes_roadmap, routes_twin, ws
from .config import settings
from .core.audit import record
from .core.llm import get_llm
from .core.logging import configure_logging, get_logger
from .db.session import init_db
from .jobs import hub

log = get_logger("main")

DESCRIPTION = """\
**ModernRx** - GxP-aware AI application modernization advisor.

Generic AI tools rewrite code. ModernRx tells a pharma company *what* to
modernize, *in which order*, and *how to prove to FDA/EMA that nothing broke*.

Seven engines, in a pipeline:

1. **Living Architecture Twin** - code, data, config and runtime traces into one knowledge graph
2. **GxP Criticality Scanner** - Part 11 / Annex 11 / CSA risk tagging
3. **Cloud Readiness Scorer** - 12-factor, tech debt, dependencies
4. **Blast-Radius-Aware Decomposition** - HDBSCAN plus a GxP constraint
5. **AI Architecture Council** - five specialist agents debate, a moderator decides
6. **Roadmap Optimizer & Monte Carlo** - CP-SAT wave plan, P50/P80/P95 dates
7. **Evidence Pack Generator** - CSA assurance plan, characterisation tests, PDF

Every AI output is schema-validated, must cite knowledge-graph node ids, and
stays *Proposed* until a named human approves it. Every action is written to an
append-only, hash-chained audit log.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    hub.bind_loop(asyncio.get_running_loop())
    settings.ensure_dirs()
    llm = get_llm()
    log.info("startup", llm=llm.status(), data_dir=str(settings.data_dir),
             neo4j=bool(settings.neo4j_uri))
    if not llm.available:
        log.warning(
            "llm_unavailable",
            detail="No GEMINI_API_KEY configured. Engine 2's classifier, Engine 5's "
                   "Council and Ask-the-Twin will run their deterministic reasoners. "
                   "Every output records generator='deterministic'.",
        )
    record("system.started", payload={"llm": llm.status()["mode"],
                                      "version": app.version})
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ModernRx",
        version="1.0.0",
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000",
                       "http://localhost:3001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(KeyError)
    async def key_error_handler(_: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": f"not found: {exc}"})

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(routes_projects.router)
    app.include_router(routes_twin.router)
    app.include_router(routes_council.router)
    app.include_router(routes_roadmap.router)
    app.include_router(ws.router)

    @app.get("/", tags=["meta"])
    def root() -> dict[str, Any]:
        return {
            "name": "ModernRx",
            "tagline": "Modernize pharma apps faster, and prove nothing broke.",
            "version": app.version,
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()
