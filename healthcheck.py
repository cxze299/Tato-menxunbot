import json, sys
from datetime import datetime, timezone
from pathlib import Path

path=Path(__file__).resolve().parent/"data"/"health.json"
try:
    value=json.loads(path.read_text(encoding="utf-8")); updated=datetime.fromisoformat(value["updated_at"])
    age=(datetime.now(timezone.utc)-updated.astimezone(timezone.utc)).total_seconds()
    if value.get("status") not in {"running","starting"} or age>150: raise ValueError(f"heartbeat age={age:.0f}s")
except Exception as error:
    print(f"unhealthy: {error}"); sys.exit(1)
print("healthy")
