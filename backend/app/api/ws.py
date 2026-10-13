"""WebSocket streaming of job progress and live agent messages (PRD §17).

    WS /ws/jobs/{job_id}

A client that connects after a job started receives the replay buffer first, so
the live debate view survives a page reload mid-run.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.logging import get_logger
from ..jobs import get_job, hub

router = APIRouter()
log = get_logger("ws")

HEARTBEAT_SECONDS = 20.0
TERMINAL = {"succeeded", "failed"}


@router.websocket("/ws/jobs/{job_id}")
async def job_socket(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()

    job = get_job(job_id)
    if job is None:
        await websocket.send_json({"type": "error", "error": "job not found", "job_id": job_id})
        await websocket.close(code=4404)
        return

    queue, backlog = hub.subscribe(job_id)
    try:
        # Current state first, so a late client is immediately consistent.
        await websocket.send_json({
            "type": "snapshot", "job_id": job_id,
            "status": job["status"], "progress": job["progress"], "step": job["step"],
            "events": job["events"], "error": job["error"],
            "replayed": len(backlog),
        })
        for event in backlog:
            await websocket.send_json(event)

        if job["status"] in TERMINAL:
            await websocket.send_json({
                "type": "status", "status": job["status"],
                "result": job["result"], "error": job["error"], "final": True,
            })
            await websocket.close()
            return

        while True:
            try:
                event: dict[str, Any] = await asyncio.wait_for(
                    queue.get(), timeout=HEARTBEAT_SECONDS
                )
            except asyncio.TimeoutError:
                # A heartbeat keeps proxies from closing an idle socket during a
                # long solve, and lets the client show "still working".
                current = get_job(job_id) or {}
                await websocket.send_json({
                    "type": "heartbeat", "job_id": job_id,
                    "status": current.get("status"), "progress": current.get("progress"),
                    "step": current.get("step"),
                })
                if current.get("status") in TERMINAL:
                    await websocket.send_json({
                        "type": "status", "status": current.get("status"),
                        "result": current.get("result"), "error": current.get("error"),
                        "final": True,
                    })
                    break
                continue

            await websocket.send_json(event)
            if event.get("type") == "status" and event.get("status") in TERMINAL:
                final = get_job(job_id) or {}
                await websocket.send_json({
                    "type": "status", "status": final.get("status"),
                    "result": final.get("result"), "error": final.get("error"),
                    "final": True,
                })
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("ws_error", job=job_id, error=str(exc))
    finally:
        hub.unsubscribe(job_id, queue)
        try:
            await websocket.close()
        except Exception:
            pass
