"""Audit trail helper for YLMS."""
import uuid
from datetime import datetime, timezone
from typing import Optional, Any

from db import get_db


async def log_audit(
    user: dict,
    action: str,
    module: str,
    entity_id: Optional[str] = None,
    entity_code: Optional[str] = None,
    details: Optional[dict] = None,
    ip: Optional[str] = None,
) -> None:
    db = get_db()
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user.get("id"),
        "user_email": user.get("email"),
        "user_name": user.get("name"),
        "user_role": user.get("role"),
        "action": action,
        "module": module,
        "entity_id": entity_id,
        "entity_code": entity_code,
        "details": details or {},
        "ip": ip,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await db.audit_logs.insert_one(doc)


def get_ip(request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
