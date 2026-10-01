# Unified AI Company Operations Portal

This folder combines the existing modules in `company_ai_system` behind one website.

## Modules

- **Security System** — reads existing events from `security.db`; the current `main.py` remains the YOLOv8 + ByteTrack webcam detector.
- **Administrative System**
  - Existing RAG chatbot through `rag_engine.py` and `ai_service.py`.
  - Face Clock attendance bridge through `/api/attendance`.
- **Logistics System** — reuses `database.py` and `inventory.db` for barcode lookup, batches, expiry, stock IN and stock OUT.

## FaceClock note

The repository currently stores FaceClock as `FaceClock zip.zip`. GitHub's source connector cannot inspect files inside that binary archive. Extract the FaceClock source into a normal folder in this repository, then connect its successful recognition event to:

```http
POST /api/attendance
Content-Type: application/json

{
  "employee_id": "EMP001",
  "employee_name": "Example User",
  "event_type": "CLOCK_IN",
  "method": "face_recognition",
  "confidence": 0.98
}
```

## Run

Install the portal web dependencies plus your existing project requirements:

```bash
pip install -r requirements.txt
pip install -r unified_portal/requirements.txt
```

Then start:

```bash
python -m uvicorn unified_portal.app:app --host 0.0.0.0 --port 8080 --reload
```

Open:

```
http://127.0.0.1:8080
```

For Windows, you can also run `unified_portal\RUN_PORTAL.bat`.

## Security webcam

Run the existing detector separately so it can own the webcam and continuously populate `security.db`:

```bash
python main.py
```

The portal will show the resulting events automatically when refreshed.

## Raspberry Pi deployment

For Raspberry Pi deployment, keep this portal as the central web/API layer. Camera-dependent AI processes can run as separate workers and write/post their results to the portal databases/APIs. This avoids multiple web servers fighting over ports and keeps the UI unified.
