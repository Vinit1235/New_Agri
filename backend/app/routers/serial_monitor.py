"""/api/serial — live serial-port monitor for ESP32 over USB.

Streams ESP32 Serial output to the browser via Server-Sent Events (SSE).
Works even when the ESP32 has no WiFi — useful for debugging and first-time setup.

Endpoints:
  GET /api/serial/ports          — list available serial ports
  GET /api/serial/stream?port=X  — SSE stream of raw serial lines
  POST /api/serial/connect       — open/switch port
  POST /api/serial/disconnect    — close the port
  GET /api/serial/status         — current port + connection state

Requires:  pip install pyserial
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/serial", tags=["serial"])

# ---------------------------------------------------------------------------
# Serial state (one global connection — one device at a time)
# ---------------------------------------------------------------------------
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

_port_lock  = threading.Lock()
_serial_con: Optional["serial.Serial"] = None
_port_name: Optional[str] = None
_log_lines: list[str] = []        # rolling in-memory buffer (last 500 lines)
MAX_LOG_LINES = 500

# Parse known ESP32 telemetry lines into structured dict
def _parse_telemetry_line(line: str) -> Optional[dict]:
    """Try to extract key=value pairs from SoilEdge [Telemetry] log lines."""
    if "[Telemetry]" not in line:
        return None
    # Expected format:
    # [Telemetry] M=42.1%  T=28.3C  RH=64.0%  Turb=12 NTU  Flow=1.23 L/m  Sess=0.041 L  Total=1.234 L  Pump=OFF
    result: dict = {}
    try:
        parts = line.split("]", 1)[-1].strip().split()
        for p in parts:
            if "=" in p:
                k, v = p.split("=", 1)
                # Strip units
                for unit in ["%", "C", "NTU", "L/m", "L"]:
                    v = v.rstrip(unit)
                try:
                    result[k] = float(v)
                except ValueError:
                    result[k] = v
    except Exception:
        pass
    return result if result else None


def _reader_thread():
    """Background thread: reads lines from the serial port into _log_lines."""
    global _serial_con, _log_lines
    while True:
        with _port_lock:
            con = _serial_con
        if con is None or not con.is_open:
            time.sleep(0.3)
            continue
        try:
            raw = con.readline()
            if raw:
                line = raw.decode("utf-8", errors="replace").rstrip()
                ts   = time.strftime("%H:%M:%S")
                entry = f"[{ts}] {line}"
                with _port_lock:
                    _log_lines.append(entry)
                    if len(_log_lines) > MAX_LOG_LINES:
                        _log_lines.pop(0)
        except Exception:
            time.sleep(0.1)


# Start the background reader once
_reader = threading.Thread(target=_reader_thread, daemon=True)
_reader.start()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ConnectRequest(BaseModel):
    port: str
    baud: int = 115200


class StatusOut(BaseModel):
    connected: bool
    port: Optional[str] = None
    baud: Optional[int] = None
    serial_available: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/ports")
def list_ports():
    """Return available serial ports on the host machine."""
    if not SERIAL_AVAILABLE:
        return {"ok": False, "error": "pyserial not installed", "ports": []}
    ports = [
        {"device": p.device, "description": p.description, "hwid": p.hwid}
        for p in serial.tools.list_ports.comports()
    ]
    return {"ok": True, "ports": ports}


@router.get("/status", response_model=StatusOut)
def serial_status():
    global _serial_con, _port_name
    with _port_lock:
        connected = _serial_con is not None and _serial_con.is_open
        baud = _serial_con.baudrate if connected else None
    return StatusOut(
        connected=connected,
        port=_port_name if connected else None,
        baud=baud,
        serial_available=SERIAL_AVAILABLE,
    )


@router.post("/connect")
def connect_port(req: ConnectRequest):
    global _serial_con, _port_name, _log_lines
    if not SERIAL_AVAILABLE:
        raise HTTPException(status_code=503, detail="pyserial not installed on server")

    with _port_lock:
        # Close existing
        if _serial_con and _serial_con.is_open:
            try:
                _serial_con.close()
            except Exception:
                pass
        try:
            _serial_con = serial.Serial(req.port, req.baud, timeout=1)
            _port_name  = req.port
            _log_lines  = []   # clear old log
            return {"ok": True, "port": req.port, "baud": req.baud}
        except Exception as e:
            _serial_con = None
            _port_name  = None
            raise HTTPException(status_code=400, detail=f"Could not open port: {e}")


@router.post("/disconnect")
def disconnect_port():
    global _serial_con, _port_name
    with _port_lock:
        if _serial_con and _serial_con.is_open:
            try:
                _serial_con.close()
            except Exception:
                pass
        _serial_con = None
        _port_name  = None
    return {"ok": True}


@router.get("/stream")
async def stream_serial():
    """
    SSE endpoint — yields new serial lines as they arrive.
    Connect from JS:  const es = new EventSource('/api/serial/stream');
    """
    async def generator():
        last_idx = 0
        # Send a heartbeat comment every ~3 s to keep the connection alive
        yield "retry: 2000\n\n"
        while True:
            with _port_lock:
                lines = _log_lines[last_idx:]
                last_idx = len(_log_lines)
            for line in lines:
                # Escape newlines inside the data payload
                safe = line.replace("\n", " ").replace("\r", "")
                # Try to detect structured telemetry and add a parsed event
                parsed = _parse_telemetry_line(safe)
                if parsed:
                    import json
                    yield f"event: telemetry\ndata: {json.dumps(parsed)}\n\n"
                yield f"data: {safe}\n\n"
            if not lines:
                # Heartbeat comment
                yield ": ping\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/log")
def get_log(n: int = Query(default=100, ge=1, le=500)):
    """Return the last N buffered log lines (for initial page load)."""
    with _port_lock:
        return {"ok": True, "lines": _log_lines[-n:]}
