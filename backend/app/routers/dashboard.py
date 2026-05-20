# backend/app/routers/dashboard.py
# Endpoints del panel estadístico: métricas globales y análisis del entrenador.
# El endpoint /network-info usa HOST_IP inyectada por el script .ps1 de Windows,
# que es la única forma confiable de obtener la IP real de la máquina anfitriona
# desde dentro de un contenedor Docker corriendo en WSL2.

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import date, timedelta
import logging
import socket
import os

from app.database import get_db
from app.models.user import User
from app.models.patient import Patient
from app.models.evaluation import Evaluation
from app.schemas import DashboardStats
from app.utils.security import get_current_active_user

# -----------------------------------------------
# Configuración del router del dashboard
# -----------------------------------------------
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
logger = logging.getLogger(__name__)


@router.get("/stats", response_model=DashboardStats)
async def obtener_estadisticas_globales(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna estadísticas globales del entrenador autenticado.
    Incluye conteos, promedios e indicadores clave del mes actual.
    """
    trainer_id = current_user.id
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)

    # Conteo total de pacientes registrados (activos e inactivos)
    total_pacientes = db.query(Patient).filter(
        Patient.trainer_id == trainer_id
    ).count()

    # Solo pacientes con estado activo actualmente
    pacientes_activos = db.query(Patient).filter(
        Patient.trainer_id == trainer_id,
        Patient.is_active == True,
        Patient.estado == "activo"
    ).count()

    # Total histórico de evaluaciones del entrenador
    total_evaluaciones = db.query(Evaluation).filter(
        Evaluation.trainer_id == trainer_id
    ).count()

    # Evaluaciones registradas en el mes en curso
    evaluaciones_mes = db.query(Evaluation).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.fecha_evaluacion >= inicio_mes
    ).count()

    # Cantidad de pacientes con al menos una alerta activa
    pacientes_con_alerta = db.query(Evaluation).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.tiene_alerta == True
    ).distinct(Evaluation.patient_id).count()

    # Promedio de IMC de todas las evaluaciones con IMC registrado
    promedio_imc = db.query(func.avg(Evaluation.imc)).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.imc.isnot(None)
    ).scalar()

    # Promedio de porcentaje de grasa corporal
    promedio_grasa = db.query(func.avg(Evaluation.porcentaje_grasa)).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.porcentaje_grasa.isnot(None)
    ).scalar()

    return DashboardStats(
        total_pacientes=total_pacientes,
        pacientes_activos=pacientes_activos,
        total_evaluaciones=total_evaluaciones,
        evaluaciones_este_mes=evaluaciones_mes,
        pacientes_con_alerta=pacientes_con_alerta,
        promedio_imc=round(float(promedio_imc), 2) if promedio_imc else None,
        promedio_grasa=round(float(promedio_grasa), 2) if promedio_grasa else None
    )


@router.get("/evoluciones")
async def obtener_evolucion_mensual(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna el número de evaluaciones registradas por mes (últimos 12 meses).
    """
    hoy = date.today()
    hace_12_meses = hoy - timedelta(days=365)

    # Agrupar evaluaciones por mes y año dentro del rango de 12 meses
    evaluaciones_por_mes = db.query(
        extract("year", Evaluation.fecha_evaluacion).label("anio"),
        extract("month", Evaluation.fecha_evaluacion).label("mes"),
        func.count(Evaluation.id).label("total")
    ).filter(
        Evaluation.trainer_id == current_user.id,
        Evaluation.fecha_evaluacion >= hace_12_meses
    ).group_by("anio", "mes").order_by("anio", "mes").all()

    # Nombres cortos de meses en español para el eje X de la gráfica
    meses_es = {
        1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr",
        5: "May", 6: "Jun", 7: "Jul", 8: "Ago",
        9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
    }

    return {
        "datos": [
            {
                "periodo": f"{meses_es[int(r.mes)]} {int(r.anio)}",
                "total_evaluaciones": r.total
            }
            for r in evaluaciones_por_mes
        ]
    }


@router.get("/alertas-recientes")
async def obtener_alertas_recientes(
    limite: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna las evaluaciones más recientes que tienen alertas activas.
    """
    # Unir evaluaciones con el nombre del paciente, filtrar alertas activas
    alertas = db.query(Evaluation, Patient.nombre_completo).join(
        Patient, Evaluation.patient_id == Patient.id
    ).filter(
        Evaluation.trainer_id == current_user.id,
        Evaluation.tiene_alerta == True
    ).order_by(
        Evaluation.fecha_evaluacion.desc()
    ).limit(limite).all()

    return {
        "alertas": [
            {
                "evaluacion_id": eval.id,
                "patient_id": eval.patient_id,
                "nombre_paciente": nombre,
                "fecha": str(eval.fecha_evaluacion),
                "detalle": eval.detalle_alerta
            }
            for eval, nombre in alertas
        ]
    }


@router.get("/top-pacientes")
async def obtener_top_pacientes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna los 5 pacientes con más evaluaciones registradas.
    """
    # Contar evaluaciones por paciente activo y ordenar de mayor a menor
    top = db.query(
        Patient.id,
        Patient.nombre_completo,
        func.count(Evaluation.id).label("total_evaluaciones")
    ).join(
        Evaluation, Patient.id == Evaluation.patient_id, isouter=True
    ).filter(
        Patient.trainer_id == current_user.id,
        Patient.is_active == True
    ).group_by(Patient.id, Patient.nombre_completo).order_by(
        func.count(Evaluation.id).desc()
    ).limit(5).all()

    return {
        "top_pacientes": [
            {
                "id": r.id,
                "nombre": r.nombre_completo,
                "total_evaluaciones": r.total_evaluaciones
            }
            for r in top
        ]
    }


@router.get("/network-info")
async def obtener_info_red(
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna la IP de red local del servidor Windows anfitrión para el QR.

    Problema Docker + WSL2:
      El contenedor backend corre dentro de WSL2, cuya red interna es 172.x.x.x.
      Cualquier método de detección de IP desde dentro del contenedor
      (socket, hostname, interfaces) retorna esa IP interna, no la IP WiFi
      real de Windows (192.168.x.x) que es la que necesitan los otros dispositivos.

    Solución:
      El script iniciar-fitpro.ps1 detecta la IP real de Windows ANTES de
      arrancar Docker y la pasa al contenedor como variable de entorno HOST_IP
      mediante: HOST_IP=192.168.x.x docker compose up -d

      Este endpoint lee HOST_IP con os.getenv() y la retorna directamente.
      Si HOST_IP no está disponible (arranque manual sin el script), usa el
      socket UDP como respaldo, que en ese caso puede retornar la IP del
      contenedor — el frontend mostrará una advertencia.
    """
    # PRIORIDAD 1: IP de Windows inyectada por iniciar-fitpro.ps1
    # Esta es siempre la IP correcta cuando se usa el script de inicio
    host_ip = os.getenv("HOST_IP", "").strip()

    # Validar que sea una IP real (no vacía, no localhost, no IP interna Docker)
    es_ip_valida = (
        host_ip
        and host_ip != "localhost"
        and not host_ip.startswith("127.")
        and not host_ip.startswith("172.")
    )

    if es_ip_valida:
        logger.info(f"IP de red desde HOST_IP (Windows): {host_ip}")
        return {
            "ip":     host_ip,
            "url":    f"http://{host_ip}",
            "puerto": 80,
            "fuente": "host"   # Indica que viene del anfitrión Windows
        }

    # PRIORIDAD 2: socket UDP ficticio como respaldo
    # Útil si se arranca con "docker compose up" directo sin el script .ps1
    # NOTA: dentro de Docker/WSL2 esto retorna la IP del contenedor (172.x.x.x),
    # no la de Windows. El frontend mostrará una advertencia en este caso.
    ip_socket = None
    try:
        # Conexión UDP a 8.8.8.8 sin enviar datos — solo fuerza la selección
        # de interfaz de red para exponer la IP local de esa interfaz
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2)
        sock.connect(("8.8.8.8", 80))
        ip_socket = sock.getsockname()[0]
        sock.close()
    except Exception:
        pass

    # Último recurso: hostname del contenedor
    if not ip_socket:
        try:
            ip_socket = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip_socket = "localhost"

    logger.warning(
        f"HOST_IP no disponible. IP detectada por socket: {ip_socket}. "
        "Para obtener la IP correcta de red, usa iniciar-fitpro.bat"
    )

    return {
        "ip":     ip_socket,
        "url":    f"http://{ip_socket}",
        "puerto": 80,
        "fuente": "socket"  # Indica que es la IP del contenedor, no del anfitrión
    }