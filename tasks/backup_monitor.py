"""Read *only* host-written backup metadata, never backup archive or secrets."""
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
import json

from django.conf import settings
from django.utils import timezone

STATUS_PATH = Path("/app/backup_status/backup_status.json")


def get_backup_status(path=None):
    path = Path(path) if path is not None else STATUS_PATH
    fallback = {
        "state": "unknown", "label": "Нет сведений о резервных копиях",
        "archive_name": "", "completed_at": None, "size_bytes": 0,
        "media_included": False, "sha256": "", "age_hours": None,
    }
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        completed = datetime.fromisoformat(str(raw["completed_at"]).replace("Z", "+00:00"))
        if completed.tzinfo is None: completed = completed.replace(tzinfo=dt_timezone.utc)
        age = max(0, (timezone.now() - completed).total_seconds() / 3600)
        # Avoid trusting arbitrary path-like strings shown in the UI.
        name = Path(str(raw.get("archive_name", ""))).name[:200]
        media = raw.get("media_included") is True
        sha = str(raw.get("sha256", ""))[:64]
        valid_sha = len(sha) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in sha)
        if age > 36:
            state, label = "stale", "Последний backup старше 36 часов"
        elif not media:
            state, label = "partial", "Последняя копия без media"
        elif not valid_sha:
            state, label = "partial", "Нет контрольной суммы"
        else:
            state, label = "ok", "Последний backup выполнен"
        return {
            "state": state, "label": label, "archive_name": name,
            "completed_at": completed, "size_bytes": int(raw.get("size_bytes", 0)),
            "size_megabytes": round(int(raw.get("size_bytes", 0)) / 1048576, 2),
            "media_included": media, "sha256": sha if valid_sha else "",
            "age_hours": round(age, 1), "host_os": str(raw.get("host_os", ""))[:40],
        }
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return fallback
