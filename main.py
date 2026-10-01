import os
import cv2
import time
import sqlite3
from datetime import datetime
from ultralytics import YOLO

# -----------------------------
# CONFIGURATION
# -----------------------------
CAMERA_INDEX = 0
MODEL_PATH = "yolov8n.pt"

LOITER_SECONDS = 5
EVENT_COOLDOWN_SECONDS = 10

# Normalized restricted zone: x1, y1, x2, y2
# Change these values to move/resize the zone.
RESTRICTED_ZONE = (0.35, 0.20, 0.65, 0.90)

# COCO classes available in the standard YOLO model.
# You can add/remove labels here.
SUSPICIOUS_OBJECTS = {"knife", "scissors"}

DB_PATH = "security.db"
SNAPSHOT_DIR = "snapshots"

os.makedirs(SNAPSHOT_DIR, exist_ok=True)


# -----------------------------
# DATABASE
# -----------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            label TEXT,
            confidence REAL,
            track_id INTEGER,
            snapshot_path TEXT
        )
        """
    )
    conn.commit()
    return conn


def save_snapshot(frame, prefix):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{prefix}_{timestamp}.jpg"
    path = os.path.join(SNAPSHOT_DIR, filename)
    cv2.imwrite(path, frame)
    return path


def log_event(conn, frame, event_type, label=None, confidence=None, track_id=None):
    snapshot_path = save_snapshot(frame, event_type.lower().replace(" ", "_"))
    timestamp = datetime.now().isoformat(timespec="seconds")

    conn.execute(
        """
        INSERT INTO events
        (timestamp, event_type, label, confidence, track_id, snapshot_path)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (timestamp, event_type, label, confidence, track_id, snapshot_path),
    )
    conn.commit()

    print(
        f"[ALERT] {timestamp} | {event_type} | "
        f"label={label} | confidence={confidence} | track_id={track_id}"
    )


# -----------------------------
# HELPERS
# -----------------------------
def point_inside_rect(x, y, rect):
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2


def can_trigger(last_event_times, key):
    now = time.time()
    last_time = last_event_times.get(key, 0)

    if now - last_time >= EVENT_COOLDOWN_SECONDS:
        last_event_times[key] = now
        return True

    return False


# -----------------------------
# MAIN APPLICATION
# -----------------------------
def main():
    print("Loading YOLO model...")
    model = YOLO(MODEL_PATH)

    conn = init_db()

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        raise RuntimeError(
            "Could not open webcam. Try CAMERA_INDEX = 1 if you have multiple cameras."
        )

    # Per-person tracking state.
    inside_since = {}
    loiter_alerted = set()

    # Cooldowns for repeated alerts.
    last_event_times = {}

    print("Security system started.")
    print("Press Q or ESC to quit.")

    while True:
        ok, frame = cap.read()
        if not ok:
            print("Failed to read webcam frame.")
            break

        height, width = frame.shape[:2]

        zx1 = int(RESTRICTED_ZONE[0] * width)
        zy1 = int(RESTRICTED_ZONE[1] * height)
        zx2 = int(RESTRICTED_ZONE[2] * width)
        zy2 = int(RESTRICTED_ZONE[3] * height)
        zone = (zx1, zy1, zx2, zy2)

        # Track objects so each person can keep a stable track ID.
        results = model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            verbose=False
        )

        result = results[0]
        annotated = frame.copy()

        current_person_ids_in_zone = set()

        if result.boxes is not None:
            for box in result.boxes:
                cls_id = int(box.cls[0].item())
                label = model.names[cls_id]
                confidence = float(box.conf[0].item())

                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                center_x = int((x1 + x2) / 2)
                center_y = int((y1 + y2) / 2)

                track_id = None
                if box.id is not None:
                    track_id = int(box.id[0].item())

                # Default drawing.
                box_color = (0, 255, 0)
                status = f"{label} {confidence:.2f}"

                # -----------------------------
                # Suspicious object detection
                # -----------------------------
                if label in SUSPICIOUS_OBJECTS:
                    box_color = (0, 0, 255)
                    status = f"ALERT: {label} {confidence:.2f}"

                    key = f"object:{label}"
                    if can_trigger(last_event_times, key):
                        log_event(
                            conn,
                            frame,
                            event_type="Suspicious Object",
                            label=label,
                            confidence=confidence,
                            track_id=track_id,
                        )

                # -----------------------------
                # Suspicious behavior:
                # Loitering inside restricted zone
                # -----------------------------
                if label == "person" and track_id is not None:
                    inside = point_inside_rect(center_x, center_y, zone)

                    if inside:
                        current_person_ids_in_zone.add(track_id)

                        if track_id not in inside_since:
                            inside_since[track_id] = time.time()

                        dwell = time.time() - inside_since[track_id]

                        if dwell >= LOITER_SECONDS:
                            box_color = (0, 0, 255)
                            status = f"LOITERING {dwell:.1f}s"

                            if track_id not in loiter_alerted:
                                log_event(
                                    conn,
                                    frame,
                                    event_type="Suspicious Behavior",
                                    label="Loitering in restricted zone",
                                    confidence=confidence,
                                    track_id=track_id,
                                )
                                loiter_alerted.add(track_id)
                        else:
                            box_color = (0, 165, 255)
                            status = f"IN ZONE {dwell:.1f}s"

                    else:
                        inside_since.pop(track_id, None)
                        loiter_alerted.discard(track_id)

                # Draw object box and label.
                cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2)
                cv2.putText(
                    annotated,
                    status,
                    (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    box_color,
                    2,
                )

                # Draw center point.
                cv2.circle(annotated, (center_x, center_y), 4, box_color, -1)

        # Remove stale tracking entries.
        for track_id in list(inside_since.keys()):
            if track_id not in current_person_ids_in_zone:
                inside_since.pop(track_id, None)
                loiter_alerted.discard(track_id)

        # Draw restricted zone.
        cv2.rectangle(annotated, (zx1, zy1), (zx2, zy2), (255, 0, 0), 2)
        cv2.putText(
            annotated,
            f"RESTRICTED ZONE - loiter alert after {LOITER_SECONDS}s",
            (zx1, max(20, zy1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 0, 0),
            2,
        )

        cv2.putText(
            annotated,
            "AI Security Prototype | Q/ESC = Quit",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )

        cv2.imshow("AI Security System - Webcam", annotated)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break

    cap.release()
    cv2.destroyAllWindows()
    conn.close()


if __name__ == "__main__":
    main()
