# backend/app/routers/patients.py
# Endpoints CRUD completos para gestión de pacientes del entrenador autenticado.
#
# CONTROL DE ACCESO: el ÚNICO mecanismo de bloqueo de esta app es la licencia
# mensual (ver app/licensing/service.py). NO existe límite de cantidad de
# pacientes por plan — se eliminó intencionalmente esa validación.
#
# La licencia se valida aquí, en el servidor, y no solo en el frontend:
# si un cliente llama a la API directamente (curl, Postman, etc.) sin pasar
# por la UI, igual debe quedar bloqueado si la licencia está vencida. Por eso
# el router completo depende de _verificar_licencia_activa().
#
# Si la licencia está vencida, se responde 402 Payment Required con
# codigo "LICENCIA_VENCIDA" (mismo formato que ya interpreta el frontend
# en frontend/js/license.js). Ese código HTTP es EXCLUSIVO de licencia:
# no reutilizarlo para ningún otro tipo de error de negocio.

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
import logging

from app.database import get_db
from app.models.user import User
from app.models.patient import Patient
from app.models.evaluation import Evaluation
from app.schemas import PatientCreate, PatientUpdate, PatientResponse, PaginatedResponse
from app.utils.security import get_current_active_user
from app.licensing.service import LicenseService

logger = logging.getLogger(__name__)


# -----------------------------------------------
# Dependencia de licencia — se aplica a TODO el router.
# Reutiliza get_current_active_user (FastAPI cachea el resultado de la
# dependencia dentro de la misma petición, no se consulta el usuario dos veces).
# -----------------------------------------------
def _verificar_licencia_activa(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Bloquea la petición con 402 si la licencia mensual del entrenador
    autenticado está vencida. Es la única puerta de acceso de pago del
    sistema; no hay límites de plan por cantidad de pacientes.
    """
    LicenseService.verificar_acceso(db, current_user.id)


# -----------------------------------------------
# Configuración del router de pacientes
# dependencies=[...] aplica la verificación de licencia a TODOS los
# endpoints de este router automáticamente, sin repetirla en cada función.
# -----------------------------------------------
router = APIRouter(
    prefix="/patients",
    tags=["Pacientes"],
    dependencies=[Depends(_verificar_licencia_activa)],
)


@router.post("/", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def crear_paciente(
    patient_data: PatientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Registra un nuevo paciente asociado al entrenador autenticado.
    Sin límite de cantidad: el único control de acceso es la licencia mensual,
    ya verificada por la dependencia del router antes de llegar aquí.
    """
    nuevo_paciente = Patient(
        trainer_id=current_user.id,
        **patient_data.model_dump(exclude_none=False)
    )

    db.add(nuevo_paciente)
    db.commit()
    db.refresh(nuevo_paciente)

    logger.info(f"Paciente creado: {nuevo_paciente.id} por trainer: {current_user.id}")

    # Añadir conteo de evaluaciones al response (paciente recién creado: 0)
    response = PatientResponse.model_validate(nuevo_paciente)
    response.total_evaluaciones = 0
    return response


@router.get("/", response_model=PaginatedResponse)
async def listar_pacientes(
    page: int = Query(1, ge=1, description="Número de página"),
    per_page: int = Query(20, ge=1, le=100, description="Registros por página"),
    buscar: Optional[str] = Query(None, description="Búsqueda por nombre, teléfono o correo"),
    estado: Optional[str] = Query(None, description="Filtrar por estado: activo, inactivo"),
    genero: Optional[str] = Query(None, description="Filtrar por género"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Lista todos los pacientes del entrenador con paginación y filtros avanzados.
    Solo retorna pacientes del entrenador autenticado (aislamiento de datos).
    """
    # Consulta base filtrada por el entrenador actual
    query = db.query(Patient).filter(
        Patient.trainer_id == current_user.id,
        Patient.is_active == True
    )

    # Aplicar filtro de búsqueda por texto en múltiples campos
    if buscar:
        termino = f"%{buscar.strip()}%"
        query = query.filter(
            or_(
                Patient.nombre_completo.ilike(termino),
                Patient.telefono.ilike(termino),
                Patient.correo.ilike(termino)
            )
        )

    # Filtro por estado del paciente
    if estado:
        query = query.filter(Patient.estado == estado)

    # Filtro por género
    if genero:
        query = query.filter(Patient.genero == genero)

    # Contar total para paginación
    total = query.count()
    total_pages = (total + per_page - 1) // per_page

    # Aplicar paginación y ordenar por nombre
    pacientes = query.order_by(Patient.nombre_completo).offset(
        (page - 1) * per_page
    ).limit(per_page).all()

    # Construir respuesta con conteo de evaluaciones por paciente
    items = []
    for paciente in pacientes:
        response = PatientResponse.model_validate(paciente)
        response.total_evaluaciones = db.query(Evaluation).filter(
            Evaluation.patient_id == paciente.id
        ).count()
        items.append(response)

    return PaginatedResponse(
        total=total,
        page=page,
        per_page=per_page,
        pages=total_pages,
        items=items
    )


@router.get("/{patient_id}", response_model=PatientResponse)
async def obtener_paciente(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Obtiene los datos completos de un paciente específico.
    Verifica que el paciente pertenezca al entrenador autenticado.
    """
    paciente = _get_patient_or_404(patient_id, current_user.id, db)

    response = PatientResponse.model_validate(paciente)
    response.total_evaluaciones = db.query(Evaluation).filter(
        Evaluation.patient_id == patient_id
    ).count()

    return response


@router.put("/{patient_id}", response_model=PatientResponse)
async def actualizar_paciente(
    patient_id: int,
    patient_data: PatientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Actualiza los datos de un paciente existente (actualización parcial).
    Solo actualiza los campos proporcionados en el request.
    """
    paciente = _get_patient_or_404(patient_id, current_user.id, db)

    # Actualizar solo los campos que vienen en el request (semántica PATCH)
    update_data = patient_data.model_dump(exclude_unset=True, exclude_none=True)
    for campo, valor in update_data.items():
        setattr(paciente, campo, valor)

    db.commit()
    db.refresh(paciente)

    logger.info(f"Paciente actualizado: {patient_id}")

    response = PatientResponse.model_validate(paciente)
    response.total_evaluaciones = db.query(Evaluation).filter(
        Evaluation.patient_id == patient_id
    ).count()
    return response


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_paciente(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Eliminación lógica del paciente (soft delete).
    No elimina físicamente los datos para preservar el historial clínico.
    """
    paciente = _get_patient_or_404(patient_id, current_user.id, db)

    # Soft delete: marcar como inactivo en lugar de eliminar
    paciente.is_active = False
    paciente.estado = "inactivo"
    db.commit()

    logger.info(f"Paciente desactivado: {patient_id}")


@router.get("/{patient_id}/evaluaciones")
async def obtener_evaluaciones_paciente(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Obtiene todas las evaluaciones históricas de un paciente específico.
    Ordenadas cronológicamente para análisis de progreso.
    """
    # Verificar que el paciente pertenece al entrenador
    _get_patient_or_404(patient_id, current_user.id, db)

    evaluaciones = db.query(Evaluation).filter(
        Evaluation.patient_id == patient_id
    ).order_by(Evaluation.fecha_evaluacion.asc()).all()

    return {"patient_id": patient_id, "evaluaciones": evaluaciones}


def _get_patient_or_404(patient_id: int, trainer_id: int, db: Session) -> Patient:
    """
    Función auxiliar para obtener un paciente y verificar propiedad.
    Lanza 404 si no existe o 403 si no pertenece al entrenador autenticado.
    """
    paciente = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.is_active == True
    ).first()

    if not paciente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paciente no encontrado"
        )

    # Verificar que el paciente pertenece al entrenador autenticado
    if paciente.trainer_id != trainer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para acceder a este paciente"
        )

    return paciente