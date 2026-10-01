import os
import sys
import json
import sqlite3
import datetime
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rag_engine import RAGEngine
from ai_service import AIService
import database as inventory_db

PORTAL_DIR = Path(__file__).resolve().parent
ATTENDANCE_DB = PORTAL_DIR / "attendance.db"
SECURITY_DB = ROOT / "security.db"
FACE_CLOCK_ARCHIVE = ROOT / "FaceClock zip.zip"
TEMPLATE = PORTAL_DIR / "index.html"

rag = RAGEngine(str(ROOT / "policies"), str(ROOT / "uploads"))
ai_service = AIService()
inventory_db.init_db()


def init_attendance_db():
    conn = sqlite3.connect(ATTENDANCE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            employee_name TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN ('CLOCK_IN','CLOCK_OUT')),
            method TEXT NOT NULL DEFAULT 'face_recognition',
            confidence REAL,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_attendance_db()


def security_events(limit=20):
    if not SECURITY_DB.exists():
        return []
    conn = sqlite3.connect(SECURITY_DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def attendance_events(limit=20):
    conn = sqlite3.connect(ATTENDANCE_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM attendance ORDER BY id DESC LIMIT ?", (int(limit),)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def home(request: Request):
    return HTMLResponse(TEMPLATE.read_text(encoding="utf-8"))


async def overview(request: Request):
    inv = inventory_db.get_dashboard_summary()
    events = security_events(100)
    attendance = attendance_events(100)
    return JSONResponse({
        "system": "AI Company Operations Portal",
        "modules": {
            "security": {
                "status": "ready" if SECURITY_DB.exists() else "database_not_initialized",
                "event_count_loaded": len(events),
                "latest_event": events[0] if events else None,
                "engine": "YOLOv8 + ByteTrack"
            },
            "administrative": {
                "chatbot": "ready",
                "face_clock_bridge": "ready",
                "face_clock_source_archive_detected": FACE_CLOCK_ARCHIVE.exists(),
                "attendance_count_loaded": len(attendance)
            },
            "logistics": {
                "status": "ready",
                "summary": inv
            }
        }
    })


async def get_security_events(request: Request):
    limit = min(int(request.query_params.get("limit", 20)), 100)
    return JSONResponse({"events": security_events(limit)})


async def chat(request: Request):
    try:
        body = await request.json()
        message = str(body.get("message", "")).strip()
        history = body.get("history", [])
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    if not message:
        return JSONResponse({"error": "Message is required"}, status_code=400)

    chunks = rag.retrieve(message, top_k=4)
    result = ai_service.generate_response(message, chunks, history)
    return JSONResponse(result)


async def get_inventory(request: Request):
    return JSONResponse({
        "summary": inventory_db.get_dashboard_summary(),
        "products": inventory_db.get_all_products()
    })


async def get_inventory_product(request: Request):
    barcode = request.path_params["barcode"]
    product = inventory_db.get_product_by_barcode(barcode)
    if not product:
        return JSONResponse({"error": "Product not found"}, status_code=404)
    return JSONResponse(product)


async def stock_in(request: Request):
    try:
        d = await request.json()
        result = inventory_db.stock_in(
            barcode=str(d["barcode"]),
            name=str(d.get("name") or f"Item {d['barcode']}"),
            quantity=int(d["quantity"]),
            expiration_date=d.get("expiration_date"),
            batch_no=d.get("batch_no"),
            reference=d.get("reference", "Portal stock received"),
            category=d.get("category", "General"),
            unit=d.get("unit", "Unit"),
            cost_price=d.get("cost_price"),
            selling_price=d.get("selling_price"),
            user_name=d.get("user_name", "Portal User")
        )
        return JSONResponse(result, status_code=201)
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def stock_out(request: Request):
    try:
        d = await request.json()
        result = inventory_db.stock_out(
            barcode=str(d["barcode"]),
            quantity=int(d["quantity"]),
            batch_id=d.get("batch_id"),
            reference=d.get("reference", "Portal stock dispatched"),
            user_name=d.get("user_name", "Portal User")
        )
        return JSONResponse(result)
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_attendance(request: Request):
    limit = min(int(request.query_params.get("limit", 20)), 100)
    return JSONResponse({
        "records": attendance_events(limit),
        "face_clock_archive_detected": FACE_CLOCK_ARCHIVE.exists(),
        "integration_note": "FaceClock source is currently stored as a ZIP. Extract it into the repository and post recognized attendance events to /api/attendance."
    })


async def post_attendance(request: Request):
    try:
        d = await request.json()
        employee_id = str(d["employee_id"]).strip()
        employee_name = str(d["employee_name"]).strip()
        event_type = str(d.get("event_type", "CLOCK_IN")).upper()
        method = str(d.get("method", "face_recognition"))
        confidence = d.get("confidence")
        if event_type not in {"CLOCK_IN", "CLOCK_OUT"}:
            raise ValueError("event_type must be CLOCK_IN or CLOCK_OUT")
        if not employee_id or not employee_name:
            raise ValueError("employee_id and employee_name are required")
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = sqlite3.connect(ATTENDANCE_DB)
    cur = conn.execute(
        """INSERT INTO attendance
           (employee_id, employee_name, event_type, method, confidence, timestamp)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (employee_id, employee_name, event_type, method, confidence, ts)
    )
    conn.commit()
    record_id = cur.lastrowid
    conn.close()
    return JSONResponse({
        "id": record_id,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "event_type": event_type,
        "method": method,
        "confidence": confidence,
        "timestamp": ts
    }, status_code=201)


routes = [
    Route("/", home, methods=["GET"]),
    Route("/api/overview", overview, methods=["GET"]),
    Route("/api/security/events", get_security_events, methods=["GET"]),
    Route("/api/chat", chat, methods=["POST"]),
    Route("/api/inventory", get_inventory, methods=["GET"]),
    Route("/api/inventory/{barcode}", get_inventory_product, methods=["GET"]),
    Route("/api/inventory/stock-in", stock_in, methods=["POST"]),
    Route("/api/inventory/stock-out", stock_out, methods=["POST"]),
    Route("/api/attendance", get_attendance, methods=["GET"]),
    Route("/api/attendance", post_attendance, methods=["POST"]),
]

middleware = [
    Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
]

app = Starlette(debug=True, routes=routes, middleware=middleware)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("unified_portal.app:app", host="0.0.0.0", port=8080, reload=True)
