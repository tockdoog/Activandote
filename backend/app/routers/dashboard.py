# backend/app/routers/dashboard.py
# Endpoints del panel estadístico: métricas globales y análisis del entrenador.
# El endpoint /network-info usa HOST_IP inyectada por los scripts de lanzamiento
# (lanzador_programa.vbs / lanzar_programa.sh / lanzador_programa.command),
# que detectan la IP real de la máquina anfitriona ANTES de levantar Docker
# y la pasan al contenedor como variable de entorno HOST_IP.

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
    Retorna la IP de red local del servidor anfitrión para el código QR.

    Flujo de detección (en orden de prioridad):

    PRIORIDAD 1 — HOST_IP inyectada por los scripts de lanzamiento:
      Los scripts (lanzador_programa.vbs / lanzar_programa.sh /
      lanzador_programa.command) detectan la IP real de la máquina
      ANTES de arrancar Docker y la pasan al contenedor como:
        HOST_IP=192.168.x.x docker compose up -d
      Esta IP es siempre la correcta para acceso en red WiFi local.

    PRIORIDAD 2 — Cabecera X-Forwarded-For de nginx:
      Si la petición llega desde la red local (no desde localhost),
      nginx inyecta la IP del cliente en X-Forwarded-For.
      En ese caso asumimos que la IP del servidor es alcanzable
      por el mismo segmento de red, pero esto NO garantiza la IP
      del servidor — solo sirve como indicador de conectividad.

    PRIORIDAD 3 — Socket UDP ficticio:
      Útil SOLO en desarrollo local sin Docker. Dentro de Docker/WSL2
      retorna la IP interna del contenedor (172.x.x.x), que NO es
      accesible desde otros dispositivos. Se incluye únicamente como
      último recurso con advertencia en los logs.

    Problema Docker + WSL2 / HyperKit (macOS):
      El contenedor backend corre dentro de una VM (WSL2 en Windows,
      HyperKit/VZ en Mac). Cualquier detección de IP desde dentro del
      contenedor retorna la IP interna del bridge Docker (172.x.x.x),
      no la IP WiFi real del host. Por eso el script de lanzamiento
      DEBE inyectar HOST_IP antes de arrancar Docker.
    """
    # -----------------------------------------------
    # PRIORIDAD 1: IP inyectada por el script de lanzamiento.
    # Esta es siempre la IP correcta cuando se usa el lanzador.
    # -----------------------------------------------
    host_ip = os.getenv("HOST_IP", "").strip()

    # Validar que sea una IPv4 real de red local (no vacía, no loopback,
    # no IP interna de Docker, no APIPA sin conexión)
    def es_ip_red_valida(ip: str) -> bool:
        if not ip:
            return False
        segmentos_invalidos = ("127.", "172.", "169.254.", "0.")
        invalidos = ["localhost", ""]
        if ip in invalidos:
            return False
        for seg in segmentos_invalidos:
            if ip.startswith(seg):
                return False
        # Verificar que tenga formato IPv4 básico (x.x.x.x)
        partes = ip.split(".")
        if len(partes) != 4:
            return False
        return all(p.isdigit() and 0 <= int(p) <= 255 for p in partes)

    if es_ip_red_valida(host_ip):
        logger.info(f"IP de red desde HOST_IP (script de lanzamiento): {host_ip}")
        return {
            "ip":     host_ip,
            "url":    f"http://{host_ip}",
            "puerto": 80,
            "fuente": "host"
        }

    # -----------------------------------------------
    # PRIORIDAD 2: Socket UDP ficticio como respaldo.
    # NOTA: dentro de Docker/WSL2 esto retorna 172.x.x.x (IP del contenedor).
    # Solo es útil en desarrollo local sin Docker o en Linux nativo.
    # -----------------------------------------------
    ip_socket = None
    try:
        # Conexión UDP a 8.8.8.8 sin enviar datos — solo fuerza la selección
        # de la interfaz de red para exponer la IP local de esa interfaz.
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
        f"HOST_IP no disponible o inválida. IP detectada por socket: {ip_socket}. "
        "Para el QR correcto, usa el script de lanzamiento correspondiente a tu SO."
    )

    return {
        "ip":     ip_socket,
        "url":    f"http://{ip_socket}",
        "puerto": 80,
        "fuente": "socket"
    }