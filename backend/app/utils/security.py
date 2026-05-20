# backend/app/utils/security.py
# Utilidades de seguridad: JWT, hashing de contraseñas y validaciones

from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import bcrypt
import re

from app.config import settings
from app.database import get_db

# -----------------------------------------------
# Esquema de seguridad Bearer Token
# -----------------------------------------------
security_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    """
    Genera hash seguro de contraseña con bcrypt puro.
    Trunca a 72 bytes (límite de bcrypt) y usa salt automático.
    """
    # bcrypt tiene límite de 72 bytes — truncamos para evitar el ValueError
    password_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica si una contraseña plana coincide con su hash bcrypt.
    """
    try:
        password_bytes = plain_password.encode('utf-8')[:72]
        return bcrypt.checkpw(password_bytes, hashed_password.encode('utf-8'))
    except Exception:
        return False


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Valida fortaleza de contraseña según política de seguridad.
    Retorna (es_valida, mensaje_error).
    """
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        return False, f"La contraseña debe tener mínimo {settings.MIN_PASSWORD_LENGTH} caracteres"

    if not re.search(r"[A-Z]", password):
        return False, "Debe contener al menos una letra mayúscula"

    if not re.search(r"[a-z]", password):
        return False, "Debe contener al menos una letra minúscula"

    if not re.search(r"\d", password):
        return False, "Debe contener al menos un número"

    return True, "Contraseña válida"


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Genera token JWT de acceso con tiempo de expiración configurable."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access"
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Genera token JWT de refresco de larga duración."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh"
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """Decodifica y valida un token JWT. Lanza excepción si es inválido o expirado."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db)
):
    """Dependencia FastAPI: obtiene el usuario autenticado desde el Bearer token."""
    from app.models.user import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(credentials.credentials)
    user_id: Optional[int] = payload.get("sub")

    if user_id is None:
        raise credentials_exception

    user = db.query(User).filter(
        User.id == int(user_id),
        User.is_active == True
    ).first()

    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(current_user=Depends(get_current_user)):
    """Verifica que el usuario autenticado esté activo."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario inactivo"
        )
    return current_user