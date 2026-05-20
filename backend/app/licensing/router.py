# backend/app/licensing/router.py
# Endpoints del sistema de licencias mensuales.
# Versión simplificada: clave desde .env, sin hash, sin endpoint de admin.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import logging

from app.database import get_db
from app.utils.security import get_current_active_user
from app.models.user import User
from app.licensing.schemas import (
    LicenseStatusResponse,
    LicenseResponse,
    RenovarLicenciaRequest
)
from app.licensing.service import LicenseService
from app.licensing.models import License

# -----------------------------------------------
# Configuración del router
# -----------------------------------------------
router = APIRouter(prefix="/licensing", tags=["Licencias"])
logger = logging.getLogger(__name__)


@router.get("/estado", response_model=LicenseStatusResponse)
async def obtener_estado_licencia(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Retorna el estado actual de la licencia del usuario autenticado.
    Incluye segundos_restantes para el countdown en tiempo real del frontend.
    El frontend llama este endpoint al cargar cada página protegida.
    """
    return LicenseService.obtener_estado(db, current_user.id)


@router.post("/renovar", response_model=dict)
async def renovar_licencia(
    datos: RenovarLicenciaRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Renueva el acceso comparando la clave ingresada contra LICENSE_KEY del .env.
    Si es correcta, registra la renovación y retorna éxito.
    El admin debe haber actualizado LICENSE_KEY y LICENSE_EXPIRY en el .env previamente.
    """
    exito, mensaje = LicenseService.renovar_licencia(
        db=db,
        user_id=current_user.id,
        clave_ingresada=datos.clave
    )

    if not exito:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=mensaje
        )

    return {"exito": True, "mensaje": mensaje}


@router.get("/detalle", response_model=LicenseResponse)
async def obtener_detalle_licencia(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Retorna el detalle completo de la licencia: historial de renovaciones,
    estado y tiempo restante. Útil para mostrar en el perfil del usuario.
    """
    # Obtener o crear el registro de licencia
    licencia = db.query(License).filter(
        License.user_id == current_user.id
    ).first()

    if not licencia:
        licencia = LicenseService._crear_registro(db, current_user.id)

    # Obtener estado calculado con todos los campos dinámicos
    estado = LicenseService.obtener_estado(db, current_user.id)

    return LicenseResponse(
        id=licencia.id,
        user_id=licencia.user_id,
        esta_activa=licencia.esta_activa,
        esta_vigente=estado.acceso_permitido,
        dias_restantes=estado.dias_restantes,
        segundos_restantes=estado.segundos_restantes,
        renovaciones_count=licencia.renovaciones_count,
        ultima_renovacion=licencia.ultima_renovacion,
        fecha_vencimiento=estado.fecha_vencimiento
    )