import sqlite3

DB_PATH = "security.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.execute(
    """
    SELECT id, timestamp, event_type, label, confidence, track_id, snapshot_path
    FROM events
    ORDER BY id DESC
    """
)

rows = cursor.fetchall()

if not rows:
    print("No events recorded yet.")
else:
    for row in rows:
        print(row)

conn.close()
