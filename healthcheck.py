import json, sys, time
from datetime import datetime, timezone
from pathlib import Path

path=Path(__file__).resolve().parent/"data"/"health.json"
api_path=path.with_name("api-health.json")
try:
    value=json.loads(path.read_text(encoding="utf-8")); updated=datetime.fromisoformat(value["updated_at"])
    age=(datetime.now(timezone.utc)-updated.astimezone(timezone.utc)).total_seconds()
    if value.get("status") not in {"running","starting"} or age>150: raise ValueError(f"heartbeat age={age:.0f}s")
    api_value=json.loads(api_path.read_text(encoding="utf-8"))
    api_age=time.time()-float(api_value["updated_at"])
    if api_age>150: raise ValueError(f"Potato API heartbeat age={api_age:.0f}s")
except Exception as error:
    print(f"unhealthy: {error}"); sys.exit(1)
print("healthy")
