# backend/app/routers/patients.py
# Endpoints CRUD completos para gestión de pacientes del entrenador autenticado

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional, List
import logging

from app.database import get_db
from app.models.user import User
from app.models.patient import Patient
from app.models.evaluation import Evaluation
from app.schemas import PatientCreate, PatientUpdate, PatientResponse, PaginatedResponse
from app.utils.security import get_current_active_user

# -----------------------------------------------
# Configuración del router de pacientes
# -----------------------------------------------
router = APIRouter(prefix="/patients", tags=["Pacientes"])
logger = logging.getLogger(__name__)


@router.post("/", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def crear_paciente(
    patient_data: PatientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Registra un nuevo paciente asociado al entrenador autenticado.
    Verifica límite de pacientes según plan de suscripción.
    """
    # Verificar límite de pacientes según plan
    total_pacientes = db.query(Patient).filter(
        Patient.trainer_id == current_user.id,
        Patient.is_active == True
    ).count()

    limites = {"free": 10, "pro": 100, "enterprise": 99999}
    limite = limites.get(current_user.plan.value, 10)

    if total_pacientes >= limite:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Límite de pacientes alcanzado ({limite}) para el plan {current_user.plan.value}. Actualice su plan."
        )

    # Crear el nuevo paciente vinculado al entrenador
    nuevo_paciente = Patient(
        trainer_id=current_user.id,
        **patient_data.model_dump(exclude_none=False)
    )

    db.add(nuevo_paciente)
    db.commit()
    db.refresh(nuevo_paciente)

    logger.info(f"Paciente creado: {nuevo_paciente.id} por trainer: {current_user.id}")

    # Añadir conteo de evaluaciones al response
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
    Solo actualiza los campos proporcionados.
    """
    paciente = _get_patient_or_404(patient_id, current_user.id, db)

    # Actualizar solo los campos que vienen en el request (PATCH semántico)
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
    No elimina físicamente los datos para preservar historial.
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
    Lanza 404 si no existe o 403 si no pertenece al entrenador.
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