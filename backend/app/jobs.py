"""In-process background jobs (PRD §5: "everything is a job").

Long work runs on a thread so the API never blocks; progress and live agent
messages stream to WebSocket subscribers through ``hub``. Job state is persisted
to SQLite, so a client that reconnects can still read the outcome, and a page
reload mid-analysis picks the progress back up.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import threading
import traceback
from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from .core.audit import record
from .core.logging import get_logger
from .db.models import Job
from .db.session import session_scope

log = get_logger("jobs")


# =============================================================================
# WebSocket hub
# =============================================================================

class EventHub:
    """Fan-out of job events to WebSocket subscribers.

    Jobs run on worker threads while WebSockets live on the event loop, so
    events are handed over with ``call_soon_threadsafe``. Each job keeps a
    replay buffer: a client that connects after a job started still sees
    everything it missed, which is what makes the live debate view survive a
    page reload.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._replay: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, job_id: str) -> tuple[asyncio.Queue, list[dict[str, Any]]]:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        with self._lock:
            self._subscribers.setdefault(job_id, []).append(q)
            backlog = list(self._replay.get(job_id, []))
        return q, backlog

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        with self._lock:
            subs = self._subscribers.get(job_id, [])
            if q in subs:
                subs.remove(q)
            if not subs:
                self._subscribers.pop(job_id, None)

    def publish(self, job_id: str, event: dict[str, Any]) -> None:
        event = {"job_id": job_id,
                 "ts": dt.datetime.now(dt.timezone.utc).isoformat(), **event}
        with self._lock:
            buf = self._replay.setdefault(job_id, [])
            buf.append(event)
            if len(buf) > 1200:
                del buf[: len(buf) - 1200]
            queues = list(self._subscribers.get(job_id, []))
        if not queues:
            return
        loop = self._loop
        for q in queues:
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(_offer, q, event)
            else:
                _offer(q, event)

    def clear(self, job_id: str) -> None:
        with self._lock:
            self._replay.pop(job_id, None)


def _offer(q: asyncio.Queue, event: dict[str, Any]) -> None:
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        # Drop the oldest rather than the newest: progress is more useful fresh.
        try:
            q.get_nowait()
            q.put_nowait(event)
        except Exception:
            pass


hub = EventHub()


# =============================================================================
# Job records
# =============================================================================

def create_job(project_id: str, job_type: str) -> str:
    with session_scope() as s:
        job = Job(project_id=project_id, type=job_type, status="queued", progress=0.0)
        s.add(job)
        s.flush()
        return job.id


def _update(job_id: str, **fields: Any) -> None:
    with session_scope() as s:
        job = s.get(Job, job_id)
        if job is None:
            return
        for k, v in fields.items():
            setattr(job, k, v)


def get_job(job_id: str) -> dict[str, Any] | None:
    with session_scope() as s:
        job = s.get(Job, job_id)
        if job is None:
            return None
        return {
            "id": job.id, "project_id": job.project_id, "type": job.type,
            "status": job.status, "progress": round(job.progress, 4), "step": job.step,
            "error": job.error, "events": job.events_json or [],
            "result": job.result_json or {},
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }


def list_jobs(project_id: str, limit: int = 25) -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(
            select(Job).where(Job.project_id == project_id)
            .order_by(Job.started_at.desc().nullslast(), Job.id.desc()).limit(limit)
        ).scalars().all()
        return [{
            "id": j.id, "type": j.type, "status": j.status,
            "progress": round(j.progress, 4), "step": j.step, "error": j.error,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        } for j in rows]


class JobContext:
    """Handed to a job body: report progress, stream events, log steps."""

    def __init__(self, job_id: str, project_id: str, job_type: str) -> None:
        self.job_id = job_id
        self.project_id = project_id
        self.job_type = job_type
        self._events: list[dict[str, Any]] = []
        self._progress = 0.0

    # ---- progress -------------------------------------------------------
    def progress(self, fraction: float, step: str = "") -> None:
        self._progress = max(0.0, min(1.0, float(fraction)))
        _update(self.job_id, progress=self._progress, step=step[:200])
        hub.publish(self.job_id, {
            "type": "progress", "progress": round(self._progress, 4), "step": step,
        })

    def stage(self, name: str, lo: float, hi: float) -> Callable[[float, str], None]:
        """A sub-progress callback mapped into the [lo, hi] band of the job.

        Engines report 0..1 of their own work; this keeps the overall bar
        monotonic across seven engines without each engine knowing about the
        others.
        """
        def inner(fraction: float, step: str = "") -> None:
            self.progress(lo + (hi - lo) * max(0.0, min(1.0, fraction)),
                          f"{name}: {step}" if step else name)
        return inner

    # ---- events ---------------------------------------------------------
    def event(self, payload: dict[str, Any]) -> None:
        self._events.append(payload)
        if len(self._events) > 600:
            del self._events[: len(self._events) - 600]
        _update(self.job_id, events_json=list(self._events))
        hub.publish(self.job_id, payload)

    def note(self, text: str, **extra: Any) -> None:
        self.event({"type": "note", "text": text, **extra})

    def engine(self, index: int, name: str, detail: str = "") -> None:
        self.event({"type": "engine", "index": index, "name": name, "detail": detail})


# =============================================================================
# Runner
# =============================================================================

JobBody = Callable[[JobContext], dict[str, Any]]


def run_in_background(
    project_id: str, job_type: str, body: JobBody, *, actor: str = "system"
) -> str:
    """Start a job on a worker thread and return its id immediately."""
    job_id = create_job(project_id, job_type)

    def runner() -> None:
        ctx = JobContext(job_id, project_id, job_type)
        _update(job_id, status="running", started_at=dt.datetime.now(dt.timezone.utc))
        hub.publish(job_id, {"type": "status", "status": "running"})
        record("job.started", actor=actor, entity="job", entity_id=job_id,
               payload={"project_id": project_id, "type": job_type})
        try:
            result = body(ctx) or {}
            _update(job_id, status="succeeded", progress=1.0,
                    result_json=result, finished_at=dt.datetime.now(dt.timezone.utc))
            hub.publish(job_id, {"type": "status", "status": "succeeded",
                                 "result": _summarise(result)})
            record("job.succeeded", actor=actor, entity="job", entity_id=job_id,
                   payload={"project_id": project_id, "type": job_type,
                            "summary": _summarise(result)})
            log.info("job_succeeded", job=job_id, type=job_type)
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            tb = traceback.format_exc(limit=12)
            _update(job_id, status="failed", error=detail[:4000],
                    finished_at=dt.datetime.now(dt.timezone.utc))
            hub.publish(job_id, {"type": "status", "status": "failed", "error": detail})
            record("job.failed", actor=actor, entity="job", entity_id=job_id,
                   payload={"project_id": project_id, "type": job_type, "error": detail})
            log.error("job_failed", job=job_id, type=job_type, error=detail, traceback=tb)

    threading.Thread(target=runner, name=f"job-{job_type}-{job_id}", daemon=True).start()
    return job_id


def _summarise(result: dict[str, Any]) -> dict[str, Any]:
    """Keep job-completion events small; the full result is fetched by REST."""
    out: dict[str, Any] = {}
    for k, v in (result or {}).items():
        if isinstance(v, (int, float, str, bool)) or v is None:
            out[k] = v
        elif isinstance(v, (list, tuple)):
            out[k] = {"count": len(v)}
        elif isinstance(v, dict):
            out[k] = {"keys": len(v)}
    return out
