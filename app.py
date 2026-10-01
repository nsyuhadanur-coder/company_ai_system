import os
import json
import uuid
import datetime
from typing import Dict, Any, List

from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse, HTMLResponse
from starlette.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from rag_engine import RAGEngine
from ai_service import AIService

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POLICIES_DIR = os.path.join(BASE_DIR, "policies")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

TICKETS_FILE = os.path.join(DATA_DIR, "tickets.json")
ANALYTICS_FILE = os.path.join(DATA_DIR, "analytics.json")

# Initialize RAG Engine and AI Service
rag = RAGEngine(POLICIES_DIR, UPLOADS_DIR)
ai_service = AIService()


def load_tickets() -> List[Dict[str, Any]]:
    if os.path.exists(TICKETS_FILE):
        try:
            with open(TICKETS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_tickets(tickets: List[Dict[str, Any]]):
    with open(TICKETS_FILE, "w", encoding="utf-8") as f:
        json.dump(tickets, f, indent=2)


def load_analytics() -> Dict[str, Any]:
    if os.path.exists(ANALYTICS_FILE):
        try:
            with open(ANALYTICS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "totalQueries": 0,
        "satisfiedCount": 0,
        "escalatedCount": 0,
        "topTopics": [],
        "recentQueries": []
    }


def save_analytics(data: Dict[str, Any]):
    with open(ANALYTICS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# Route Handlers
async def index(request: Request):
    html_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content)
    return HTMLResponse("<h1>Astra HR & Ops Chatbot Backend Ready</h1>")


async def chat_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    message = body.get("message", "").strip()
    history = body.get("history", [])

    if not message:
        return JSONResponse({"error": "Message is required"}, status_code=400)

    # 1. Retrieve grounded policy chunks
    retrieved_chunks = rag.retrieve(message, top_k=4)

    # 2. Generate response (Gemini 3.8 Flash or Grounded Local Synthesizer)
    result = ai_service.generate_response(message, retrieved_chunks, history)

    # 3. Update Analytics
    try:
        analytics = load_analytics()
        analytics["totalQueries"] = analytics.get("totalQueries", 0) + 1
        
        # Categorize query
        cat = "General"
        if retrieved_chunks:
            cat = retrieved_chunks[0].get("category", "General")
        
        # Keep rolling recent queries
        recent = analytics.get("recentQueries", [])
        recent.insert(0, {
            "query": message[:80],
            "category": cat,
            "engine": result["engine"],
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
        analytics["recentQueries"] = recent[:20]
        save_analytics(analytics)
    except Exception as e:
        print(f"Error updating analytics: {e}")

    return JSONResponse(result)


async def list_policies(request: Request):
    docs = rag.list_documents()
    return JSONResponse({"documents": docs, "total_chunks": len(rag.chunks)})


async def get_policy(request: Request):
    doc_id = request.path_params.get("doc_id", "")
    doc = rag.get_document(doc_id)
    if not doc:
        return JSONResponse({"error": "Policy document not found"}, status_code=404)
    return JSONResponse(doc)


async def upload_document(request: Request):
    try:
        form = await request.form()
        uploaded_file = form.get("file")
        if not uploaded_file:
            return JSONResponse({"error": "No file provided"}, status_code=400)

        filename = uploaded_file.filename
        ext = os.path.splitext(filename)[1].lower()
        if ext not in [".md", ".txt", ".docx", ".pdf"]:
            return JSONResponse({
                "error": f"Unsupported file format '{ext}'. Allowed: .md, .txt, .docx, .pdf"
            }, status_code=400)

        # Secure filename and save
        safe_filename = filename.replace(" ", "_")
        dest_path = os.path.join(UPLOADS_DIR, safe_filename)
        
        content = await uploaded_file.read()
        with open(dest_path, "wb") as f:
            f.write(content)

        # Index new document
        doc_info = rag.add_uploaded_file(dest_path, safe_filename)

        return JSONResponse({
            "message": "File uploaded and indexed successfully",
            "document": doc_info,
            "total_chunks": len(rag.chunks)
        })
    except Exception as e:
        return JSONResponse({"error": f"Upload failed: {str(e)}"}, status_code=500)


async def delete_document(request: Request):
    doc_id = request.path_params.get("doc_id", "")
    success = rag.delete_document(doc_id)
    if success:
        return JSONResponse({"message": f"Document '{doc_id}' deleted successfully"})
    return JSONResponse({"error": "Document not found or cannot be deleted"}, status_code=404)


async def get_tickets(request: Request):
    tickets = load_tickets()
    return JSONResponse(tickets)


async def create_ticket(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    subject = data.get("subject", "").strip()
    description = data.get("description", "").strip()
    if not subject or not description:
        return JSONResponse({"error": "Subject and description are required"}, status_code=400)

    tickets = load_tickets()
    ticket_num = len(tickets) + 8030
    new_ticket = {
        "id": f"TICK-{ticket_num}",
        "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "employeeName": data.get("employeeName", "Employee User"),
        "employeeEmail": data.get("employeeEmail", "employee@company.com"),
        "department": data.get("department", "Operations"),
        "category": data.get("category", "General"),
        "priority": data.get("priority", "Medium"),
        "subject": subject,
        "description": description,
        "status": "Open",
        "assignedTo": "Triage Specialist",
        "resolutionNotes": "Ticket queued for review."
    }

    tickets.insert(0, new_ticket)
    save_tickets(tickets)

    # Increment escalated count in analytics
    try:
        analytics = load_analytics()
        analytics["escalatedCount"] = analytics.get("escalatedCount", 0) + 1
        save_analytics(analytics)
    except Exception:
        pass

    return JSONResponse(new_ticket, status_code=201)


async def calculate_leave(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    start_date_str = data.get("startDate")
    end_date_str = data.get("endDate")
    leave_type = data.get("leaveType", "annual")

    if not start_date_str or not end_date_str:
        return JSONResponse({"error": "Start and End dates are required"}, status_code=400)

    try:
        start_date = datetime.date.fromisoformat(start_date_str)
        end_date = datetime.date.fromisoformat(end_date_str)
    except ValueError:
        return JSONResponse({"error": "Invalid date format. Use YYYY-MM-DD"}, status_code=400)

    if end_date < start_date:
        return JSONResponse({"error": "End date cannot be earlier than start date"}, status_code=400)

    # Calculate business days (Monday=0 to Friday=4)
    total_days = 0
    cur = start_date
    while cur <= end_date:
        if cur.weekday() < 5:  # Weekday
            total_days += 1
        cur += datetime.timedelta(days=1)

    # Policy guidelines based on HR-POL-001
    quotas = {
        "annual": {"total": 20, "name": "Annual Paid Time Off (PTO)", "notice": "48 hours for <3 days, 2 weeks for >= 3 days"},
        "sick": {"total": 10, "name": "Paid Sick & Medical Leave", "notice": "Doctor note required if >2 consecutive days"},
        "parental": {"total": 80, "name": "Parental Leave (16 Weeks Primary)", "notice": "Requires 6 months tenure, 30 days notice"},
        "bereavement": {"total": 5, "name": "Bereavement Leave", "notice": "5 days for immediate family, 2 days for extended"},
        "floating": {"total": 2, "name": "Floating Personal Holiday", "notice": "24 hours advance notification"}
    }

    info = quotas.get(leave_type, quotas["annual"])
    remaining_balance_simulated = max(0, info["total"] - total_days)

    return JSONResponse({
        "leaveType": info["name"],
        "startDate": str(start_date),
        "endDate": str(end_date),
        "requestedWorkingDays": total_days,
        "annualEntitlement": info["total"],
        "projectedRemaining": remaining_balance_simulated,
        "policyNoticeRequirement": info["notice"],
        "status": "Eligible for submission",
        "simulationId": f"REQ-{str(uuid.uuid4())[:8].upper()}"
    })


async def get_analytics(request: Request):
    data = load_analytics()
    return JSONResponse(data)


async def record_feedback(request: Request):
    try:
        data = await request.json()
        rating = data.get("rating")
        analytics = load_analytics()
        if rating == "up":
            analytics["satisfiedCount"] = analytics.get("satisfiedCount", 0) + 1
        save_analytics(analytics)
        return JSONResponse({"message": "Feedback recorded. Thank you!"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def config_status(request: Request):
    return JSONResponse({
        "gemini_active": ai_service.is_gemini_active(),
        "model": ai_service.model_name,
        "total_documents": len(rag.documents),
        "total_chunks": len(rag.chunks)
    })


async def update_api_key(request: Request):
    try:
        data = await request.json()
        key = data.get("apiKey", "").strip()
        success = ai_service.set_api_key(key)
        return JSONResponse({
            "success": success,
            "gemini_active": ai_service.is_gemini_active(),
            "model": ai_service.model_name,
            "engine": "gemini-3.8-flash" if ai_service.is_gemini_active() else "local-rag-synthesizer"
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# Starlette Application Routes
routes = [
    Route("/", endpoint=index, methods=["GET"]),
    Route("/api/chat", endpoint=chat_endpoint, methods=["POST"]),
    Route("/api/policies", endpoint=list_policies, methods=["GET"]),
    Route("/api/policies/{doc_id}", endpoint=get_policy, methods=["GET"]),
    Route("/api/documents/upload", endpoint=upload_document, methods=["POST"]),
    Route("/api/documents/{doc_id}", endpoint=delete_document, methods=["DELETE"]),
    Route("/api/tickets", endpoint=get_tickets, methods=["GET"]),
    Route("/api/tickets", endpoint=create_ticket, methods=["POST"]),
    Route("/api/leave/calculate", endpoint=calculate_leave, methods=["POST"]),
    Route("/api/analytics", endpoint=get_analytics, methods=["GET"]),
    Route("/api/feedback", endpoint=record_feedback, methods=["POST"]),
    Route("/api/config/status", endpoint=config_status, methods=["GET"]),
    Route("/api/config/key", endpoint=update_api_key, methods=["POST"]),
    Mount("/static", app=StaticFiles(directory=STATIC_DIR), name="static")
]

middleware = [
    Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
]

app = Starlette(debug=True, routes=routes, middleware=middleware)

if __name__ == "__main__":
    import uvicorn
    print("Starting Astra HR & Operations AI Chatbot Server at http://127.0.0.1:8000 ...")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
