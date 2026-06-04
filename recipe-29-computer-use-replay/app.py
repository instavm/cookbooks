from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import agent
from lib.config import FRAMES_DIR, SCREEN_H, SCREEN_W
from lib.frames import frame_gallery_html

app = FastAPI(title="Computer Use Replay")

_capture: agent.CaptureResult | None = None


def _ensure_frames() -> agent.CaptureResult:
    global _capture
    if _capture is None:
        _capture = agent.capture_frames()
    return _capture


app.mount("/frames", StaticFiles(directory=str(FRAMES_DIR)), name="frames")


@app.get("/health")
def health() -> dict[str, str]:
    capture = _ensure_frames()
    return {
        "ok": "true",
        "slug": "recipe-29-computer-use-replay",
        "frame_count": str(capture.frame_count),
        "desktop": f"{SCREEN_W}x{SCREEN_H}",
    }


@app.get("/", response_class=HTMLResponse)
def gallery() -> str:
    _ensure_frames()
    paths = sorted(FRAMES_DIR.glob("frame_*.png"))
    return frame_gallery_html(paths, screen_w=SCREEN_W, screen_h=SCREEN_H)


@app.post("/capture")
def capture() -> JSONResponse:
    global _capture
    _capture = agent.capture_frames()
    return JSONResponse({"frame_count": _capture.frame_count, "frames_dir": _capture.frames_dir})
