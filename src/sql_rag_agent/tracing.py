from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from uuid import uuid4


DEFAULT_TRACE_DIR = Path(__file__).resolve().parents[2] / "logs" / "agent_traces"


class TraceWriter:
    def __init__(self, log_dir: str | Path = DEFAULT_TRACE_DIR, trace_id: str | None = None):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.trace_id = trace_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
        self.path = self.log_dir / f"{self.trace_id}.jsonl"

    def write(self, event: str, payload: dict) -> None:
        record = {
            "trace_id": self.trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "payload": _json_safe(payload),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


class NullTraceWriter:
    trace_id = ""
    path = None

    def write(self, event: str, payload: dict) -> None:
        return None


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value

