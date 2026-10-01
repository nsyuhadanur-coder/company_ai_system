# AI Security System - Webcam Prototype

This starter project uses a webcam to demonstrate:

1. AI object detection with YOLO.
2. Person tracking with ByteTrack.
3. Suspicious-object alerts for selected COCO object classes.
4. Suspicious-behavior detection using a loitering rule in a restricted zone.
5. SQLite event logging.
6. Automatic evidence snapshots.

## 1. Create a virtual environment

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

## 2. Install packages

```bash
pip install -r requirements.txt
```

## 3. Run

```bash
python main.py
```

The first YOLO run may download `yolov8n.pt`.

Press `Q` or `ESC` to close the camera.

## 4. View logged events

```bash
python view_events.py
```

Events are stored in:

```text
security.db
```

Evidence images are stored in:

```text
snapshots/
```

## Detection logic

### Suspicious objects

The current prototype flags:

- knife
- scissors

Edit this line in `main.py` to change the list:

```python
SUSPICIOUS_OBJECTS = {"knife", "scissors"}
```

The standard COCO model is only a prototype for this purpose. A custom weapon/object dataset and trained detector should be used for a production system.

### Suspicious behavior

The initial behavior rule is:

> A tracked person remaining inside the restricted zone for at least 5 seconds is marked as loitering.

Change:

```python
LOITER_SECONDS = 5
```

The restricted zone uses normalized coordinates:

```python
RESTRICTED_ZONE = (0.35, 0.20, 0.65, 0.90)
```

Format:

```text
(left, top, right, bottom)
```

All values range from `0.0` to `1.0`.

## Suggested next upgrades

- Fighting detection with pose/action recognition.
- Running detection using track speed.
- Fall detection using MediaPipe Pose.
- Restricted-object custom YOLO model.
- Face recognition for authorized staff.
- Flask/FastAPI backend.
- Web dashboard for live alerts and event history.
- Raspberry Pi camera deployment.
- Telegram/email alert notifications.
