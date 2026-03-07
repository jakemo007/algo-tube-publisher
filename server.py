#!/usr/bin/env python3
"""
server.py  —  ZooTots Pipeline Dashboard Server
================================================
Runs main.py as a subprocess, tails pipeline.log in real-time,
parses every line into structured JSON, and broadcasts to all
connected dashboard clients via WebSocket.

Setup:
    pip install fastapi uvicorn

Run:
    python server.py

Open:
    http://localhost:8000        <- dashboard
    ws://localhost:8000/ws      <- WebSocket
    http://localhost:8000/status <- JSON status

WebSocket messages (server → client):
  init           Full state snapshot on connect
  log            One parsed log line
  step_state     Step changed: running | done | error
  api_hit        One API call detected
  pipeline_state Pipeline changed: running | done | error | idle
  ping           Heartbeat every 20 s (reply with pong)
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

# ── Config ─────────────────────────────────────────────────────────────────
LOG_FILE       = "pipeline.log"
MAIN_SCRIPT    = "main.py"
DASHBOARD_FILE = "dashboard.html"
HOST           = "0.0.0.0"
PORT           = 8000
MAX_HISTORY    = 500

# Map module names → step index (matches STEPS array in dashboard.html)
MODULE_STEP: dict[str, int] = {
    "fetch_data":      0,
    "generate_script": 1,
    "generate_media":  2,
    "assemble_video":  3,
    "upload_video":    4,
    "upload_drive":    5,
}

# ── Regex patterns ──────────────────────────────────────────────────────────
LOG_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[(\w+)\] ([\w\.]+) — (.+)$"
)
STEP_START_RE    = re.compile(r"STEP (\d+) \u2014")   # "STEP N —"
STEP_DONE_RE     = re.compile(r"Step (\d+) complete")
PIPELINE_DONE_RE = re.compile(r"ZooTots Daily Pipeline \u2014 Finished")

# API hit detection — each matching log line increments the counter once
_API_TRIGGERS_RAW = [
    ("openai",     r"Fetching today.s animal topic"),
    ("openai",     r"Generating script for:"),
    ("flux",       r"Generating FLUX character"),
    ("imgbb",      r"Uploading character image to ImgBB"),
    ("elevenlabs", r"generating ElevenLabs voiceover"),
    ("luma",       r"Submitting Luma"),
    ("drive",      r"Drive folder ready"),
    ("drive",      r"Uploaded '.*?' to Drive"),
    ("drive",      r"Backed up '.*?' to Drive"),
    ("drive",      r"Downloading Drive file"),
    ("youtube",    r"Uploading 'final_video"),
]
API_TRIGGERS = [(api, re.compile(pat)) for api, pat in _API_TRIGGERS_RAW]


# ── FastAPI app ─────────────────────────────────────────────────────────────
app = FastAPI(title="ZooTots Pipeline Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Server state ────────────────────────────────────────────────────────────
class PState:
    def __init__(self):
        self.pipeline:     str                = "idle"
        self.steps:        dict[str, str]     = {}   # string keys: {"0":"done"}
        self.api_counts:   dict[str, int]     = {}
        self.log_history:  list[dict]         = []
        self.current_step: int                = -1
        self.process: Optional[asyncio.subprocess.Process] = None

    def reset(self):
        self.pipeline     = "running"
        self.steps        = {}
        self.api_counts   = {}
        self.log_history  = []
        self.current_step = -1


state = PState()


# ── WebSocket manager ───────────────────────────────────────────────────────
class Manager:
    def __init__(self):
        self._clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.append(ws)
        # Send full snapshot — step_states uses string keys intentionally
        await ws.send_json({
            "type":           "init",
            "pipeline_state": state.pipeline,
            "step_states":    state.steps,
            "api_counts":     state.api_counts,
            "logs":           state.log_history[-200:],
        })

    def disconnect(self, ws: WebSocket):
        self._clients = [c for c in self._clients if c is not ws]

    async def broadcast(self, msg: dict):
        dead = []
        for ws in self._clients:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = Manager()


# ── Log parser ──────────────────────────────────────────────────────────────
def parse_line(raw: str) -> Optional[dict]:
    m = LOG_RE.match(raw.strip())
    if not m:
        return None
    dt, level, module, msg = m.groups()
    ts   = dt[11:]  # HH:MM:SS
    step = MODULE_STEP.get(module, -1)

    if module == "__main__":
        sm = STEP_START_RE.search(msg)
        sd = STEP_DONE_RE.search(msg)
        if sm:
            step = int(sm.group(1))
        elif sd:
            step = int(sd.group(1))
        else:
            step = -1

    return {"type": "log", "ts": ts, "level": level,
            "module": module, "step": step, "msg": msg}


def detect_api_hits(msg: str) -> list[str]:
    return [api for api, pat in API_TRIGGERS if pat.search(msg)]


# ── Pipeline runner ─────────────────────────────────────────────────────────
async def run_pipeline():
    if not Path(MAIN_SCRIPT).exists():
        await _set_pipeline("error", f"'{MAIN_SCRIPT}' not found.")
        return

    state.reset()
    Path(LOG_FILE).write_text("", encoding="utf-8")
    await manager.broadcast({"type": "pipeline_state", "state": "running"})

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, MAIN_SCRIPT,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        state.process = proc
    except Exception as exc:
        await _set_pipeline("error", str(exc))
        return

    await _tail_log(proc)


async def _tail_log(proc: asyncio.subprocess.Process):
    # Wait up to 5 s for the log file to appear
    for _ in range(50):
        if Path(LOG_FILE).exists() and Path(LOG_FILE).stat().st_size > 0:
            break
        await asyncio.sleep(0.1)

    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            while True:
                line = f.readline()

                if not line:
                    if proc.returncode is not None:
                        await _handle_exit(proc.returncode)
                        break
                    await asyncio.sleep(0.1)
                    continue

                parsed = parse_line(line)
                if not parsed:
                    continue

                if parsed["step"] == -1 and parsed["module"] not in ("__main__",):
                    parsed["step"] = state.current_step

                state.log_history.append(parsed)
                if len(state.log_history) > MAX_HISTORY:
                    state.log_history.pop(0)

                await manager.broadcast(parsed)

                msg    = parsed["msg"]
                module = parsed["module"]

                # Step transitions — use string keys to match JS
                if module == "__main__":
                    sm = STEP_START_RE.search(msg)
                    sd = STEP_DONE_RE.search(msg)

                    if sm:
                        n = int(sm.group(1))
                        state.current_step  = n
                        state.steps[str(n)] = "running"
                        await manager.broadcast({
                            "type": "step_state",
                            "step": str(n),   # string key
                            "state": "running"
                        })
                    elif sd:
                        n = int(sd.group(1))
                        state.steps[str(n)] = "done"
                        await manager.broadcast({
                            "type": "step_state",
                            "step": str(n),   # string key
                            "state": "done"
                        })
                    elif PIPELINE_DONE_RE.search(msg):
                        await _set_pipeline("done")

                # API hit counting
                for api in detect_api_hits(msg):
                    state.api_counts[api] = state.api_counts.get(api, 0) + 1
                    await manager.broadcast({
                        "type":  "api_hit",
                        "api":   api,
                        "total": state.api_counts[api],
                    })

    except Exception as exc:
        await _set_pipeline("error", str(exc))
    finally:
        state.process = None


async def _handle_exit(returncode: int):
    if returncode == 0:
        if state.pipeline != "done":
            await _set_pipeline("done")
    else:
        for k, v in list(state.steps.items()):
            if v == "running":
                state.steps[k] = "error"
                await manager.broadcast({
                    "type": "step_state", "step": k, "state": "error"
                })
        await _set_pipeline("error", f"Process exited with code {returncode}")


async def _set_pipeline(new_state: str, msg: str = ""):
    state.pipeline = new_state
    payload = {"type": "pipeline_state", "state": new_state}
    if msg:
        payload["msg"] = msg
    await manager.broadcast(payload)


# ── REST endpoints ──────────────────────────────────────────────────────────
@app.get("/")
async def serve_dashboard():
    if not Path(DASHBOARD_FILE).exists():
        return JSONResponse({"error": f"'{DASHBOARD_FILE}' not found next to server.py"}, status_code=404)
    return FileResponse(DASHBOARD_FILE, media_type="text/html")

@app.post("/start")
async def start_pipeline():
    if state.pipeline == "running":
        return JSONResponse({"ok": False, "msg": "Pipeline already running."})
    asyncio.create_task(run_pipeline())
    return JSONResponse({"ok": True})

@app.post("/stop")
async def stop_pipeline():
    if state.process:
        try:
            state.process.terminate()
            await asyncio.sleep(2)
            if state.process.returncode is None:
                state.process.kill()
        except Exception:
            pass
    for k, v in list(state.steps.items()):
        if v == "running":
            state.steps[k] = "error"
    state.pipeline     = "idle"
    state.current_step = -1
    await manager.broadcast({"type": "pipeline_state", "state": "idle"})
    return JSONResponse({"ok": True})

@app.get("/status")
async def get_status():
    return {
        "pipeline":  state.pipeline,
        "steps":     state.steps,
        "apis":      state.api_counts,
        "log_lines": len(state.log_history),
    }

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=20.0)
                msg  = json.loads(data)
                # pong from client — nothing to do
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
            except WebSocketDisconnect:
                break
            except Exception:
                break
    finally:
        manager.disconnect(websocket)


# ── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  ZooTots Pipeline Server")
    print(f"  Dashboard  →  http://localhost:{PORT}")
    print(f"  WebSocket  →  ws://localhost:{PORT}/ws")
    print("=" * 50)
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")