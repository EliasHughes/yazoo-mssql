"""Authentication & RBAC for YLMS."""
import os
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import Request, HTTPException, Depends

from db import get_db

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 60 * 12  # 12 hours (enterprise workday)

# Role hierarchy & granular permissions
ROLES = [
    "admin",
    "quality_manager",
    "supervisor",
    "analyst",
    "microbiologist",
    "chemist",
    "auxiliary",
    "production",
    "warehouse",
    "auditor",
    "management",
]

ROLE_LABELS_ES = {
    "admin": "Administrador",
    "quality_manager": "Gerente de Calidad",
    "supervisor": "Supervisor",
    "analyst": "Analista",
    "microbiologist": "Microbiólogo",
    "chemist": "Químico",
    "auxiliary": "Auxiliar",
    "production": "Producción",
    "warehouse": "Almacén",
    "auditor": "Auditor",
    "management": "Gerencia",
}

# Module permissions matrix (True = allowed)
# Modules: users, products, tests, reagents, equipment, samples, executions,
#          batches, audit, reports, dashboard, coa
PERMISSIONS = {
    "admin": {"*": True},
    "quality_manager": {
        "users": "read", "products": "write", "tests": "write", "reagents": "write",
        "equipment": "write", "samples": "write", "executions": "write",
        "batches": "write", "audit": "read", "reports": "read", "dashboard": "read", "coa": "write",
    },
    "supervisor": {
        "products": "read", "tests": "read", "reagents": "read", "equipment": "read",
        "samples": "write", "executions": "write", "batches": "write",
        "audit": "read", "reports": "read", "dashboard": "read", "coa": "write",
    },
    "analyst": {
        "products": "read", "tests": "read", "reagents": "read", "equipment": "read",
        "samples": "read", "executions": "write", "dashboard": "read", "coa": "read",
    },
    "microbiologist": {
        "products": "read", "tests": "read", "reagents": "read", "equipment": "read",
        "samples": "read", "executions": "write", "dashboard": "read", "coa": "read",
    },
    "chemist": {
        "products": "read", "tests": "read", "reagents": "read", "equipment": "read",
        "samples": "read", "executions": "write", "dashboard": "read", "coa": "read",
    },
    "auxiliary": {
        "samples": "write", "reagents": "read", "equipment": "read", "dashboard": "read",
    },
    "production": {
        "samples": "read", "batches": "read", "dashboard": "read", "coa": "read",
    },
    "warehouse": {
        "reagents": "write", "samples": "read", "dashboard": "read",
        "batches": "read",
    },
    "auditor": {
        "*": "read",
    },
    "management": {
        "*": "read",
    },
}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])


async def get_current_user(request: Request) -> dict:
    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Tipo de token inválido")
        db = get_db()
        user = await db.users.find_one({"id": payload["sub"]})
        if not user:
            raise HTTPException(status_code=401, detail="Usuario no encontrado")
        if not user.get("active", True):
            raise HTTPException(status_code=403, detail="Usuario desactivado")
        user.pop("password_hash", None)
        user.pop("_id", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")


def has_permission(role: str, module: str, level: str = "read") -> bool:
    """level = 'read' or 'write'."""
    perms = PERMISSIONS.get(role, {})
    if perms.get("*") is True:
        return True
    star = perms.get("*")
    if star == "write":
        return True
    if star == "read" and level == "read":
        return True
    mod_perm = perms.get(module)
    if mod_perm is True or mod_perm == "write":
        return True
    if mod_perm == "read" and level == "read":
        return True
    return False


def require_permission(module: str, level: str = "read"):
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if not has_permission(user.get("role", ""), module, level):
            raise HTTPException(
                status_code=403,
                detail=f"Permiso denegado: se requiere acceso {level} a {module}",
            )
        return user
    return dep


def require_role(*allowed_roles: str):
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in allowed_roles and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Rol no autorizado")
        return user
    return dep
