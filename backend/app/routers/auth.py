# backend/app/routers/auth.py
# Endpoints de autenticación: registro, login, refresh y perfil de usuario

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

from app.database import get_db
from app.models.user import User
from app.schemas import (
    UserCreate, UserLogin, UserResponse, TokenResponse, RefreshTokenRequest
)
from app.utils.security import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, decode_token, validate_password_strength,
    get_current_active_user
)
from app.config import settings

# -----------------------------------------------
# Configuración del router con prefijo y etiqueta Swagger
# -----------------------------------------------
router = APIRouter(prefix="/auth", tags=["Autenticación"])
logger = logging.getLogger(__name__)


@router.post("/registro", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def registrar_usuario(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """
    Registra un nuevo entrenador en el sistema.
    Valida unicidad del email, fortaleza de contraseña y genera tokens al instante.
    """
    # Verificar que el email no esté registrado previamente
    usuario_existente = db.query(User).filter(
        User.email == user_data.email.lower()
    ).first()

    if usuario_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El correo electrónico ya está registrado"
        )

    # Validar que la contraseña cumpla la política de seguridad
    es_valida, mensaje = validate_password_strength(user_data.password)
    if not es_valida:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=mensaje
        )

    # Crear nuevo usuario con contraseña hasheada mediante bcrypt
    nuevo_usuario = User(
        nombre_completo=user_data.nombre_completo.strip(),
        email=user_data.email.lower().strip(),
        telefono=user_data.telefono,
        hashed_password=hash_password(user_data.password),
        is_active=True,
        is_verified=False
    )

    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)

    logger.info(f"Nuevo usuario registrado: {nuevo_usuario.email}")

    # Generar tokens para inicio de sesión automático tras el registro
    return _generar_tokens(nuevo_usuario)


@router.post("/login", response_model=TokenResponse)
async def iniciar_sesion(
    credentials: UserLogin,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Autentica al entrenador y genera el par de tokens JWT.
    Mensaje de error genérico para prevenir enumeración de usuarios (User Enumeration).
    """
    # Buscar usuario por email normalizado a minúsculas
    usuario = db.query(User).filter(
        User.email == credentials.email.lower()
    ).first()

    # Usar mensaje genérico para no revelar si el email existe o no
    if not usuario or not verify_password(credentials.password, usuario.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verificar que la cuenta esté activa antes de permitir el acceso
    if not usuario.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada. Contacte al administrador."
        )

    # Registrar la fecha y hora del último inicio de sesión exitoso
    usuario.last_login = datetime.now(timezone.utc)
    db.commit()

    logger.info(f"Login exitoso: {usuario.email} desde {request.client.host}")

    return _generar_tokens(usuario)


@router.post("/refresh", response_model=TokenResponse)
async def refrescar_token(
    request_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Renueva el access token usando el refresh token enviado en el body JSON.
    Permite mantener la sesión activa sin que el usuario vuelva a ingresar credenciales.
    BUG FIX: El parámetro era str (query param), ahora es RefreshTokenRequest (JSON body).
    """
    # Decodificar y validar la firma del refresh token
    payload = decode_token(request_data.refresh_token)

    # Verificar que sea un refresh token y no un access token reutilizado
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token inválido para esta operación"
        )

    # Obtener y verificar que el usuario siga activo en la base de datos
    user_id = payload.get("sub")
    usuario = db.query(User).filter(
        User.id == int(user_id),
        User.is_active == True
    ).first()

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo"
        )

    return _generar_tokens(usuario)


@router.get("/perfil", response_model=UserResponse)
async def obtener_perfil(
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna los datos del perfil del entrenador autenticado.
    Endpoint protegido que requiere Bearer token válido en el header.
    """
    return current_user


@router.post("/logout")
async def cerrar_sesion(
    current_user: User = Depends(get_current_active_user)
):
    """
    Registra el cierre de sesión en el servidor.
    El cliente debe eliminar los tokens almacenados en localStorage.
    """
    logger.info(f"Logout: {current_user.email}")
    return {"mensaje": "Sesión cerrada exitosamente"}


# -----------------------------------------------
# Función interna: generación de par de tokens JWT
# -----------------------------------------------

def _generar_tokens(usuario: User) -> TokenResponse:
    """
    Genera el par access_token + refresh_token para un usuario dado.
    Centraliza la lógica para evitar duplicación en registro y login.
    """
    # Payload mínimo con el ID del usuario como subject (sub)
    token_data = {"sub": str(usuario.id)}

    # Generar token de acceso de corta duración
    access_token = create_access_token(
        data=token_data,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Generar token de refresco de larga duración
    refresh_token = create_refresh_token(data=token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convertir a segundos
        user=UserResponse.model_validate(usuario)
    )