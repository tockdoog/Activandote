# backend/app/licensing/service.py
# Lógica de negocio del sistema de licencias mensuales.
# La clave y fecha de vencimiento se leen del .env via settings.
# Incluye validación de fechas de calendario para evitar el bug de 2027-06-31.

from datetime import datetime, timezone
from sqlalchemy.orm import Session
import hmac
import logging
import calendar

from app.licensing.models import License
from app.licensing.schemas import LicenseStatusResponse
from app.config import settings

logger = logging.getLogger(__name__)


class LicenseService:
    """
    Servicio central de licencias.
    Toda la lógica depende de dos variables del .env:
      - LICENSE_KEY:    clave que el usuario debe ingresar para renovar
      - LICENSE_EXPIRY: fecha de vencimiento en formato YYYY-MM-DD
    """

    # -----------------------------------------------
    # VERIFICACIÓN DE ESTADO
    # -----------------------------------------------

    @staticmethod
    def obtener_estado(db: Session, user_id: int) -> LicenseStatusResponse:
        """
        Verifica si la licencia está vigente comparando la fecha actual
        contra LICENSE_EXPIRY del .env.
        Crea el registro en DB automáticamente si el usuario no tiene uno.
        """
        # Obtener o crear el registro de licencia del usuario en la DB
        licencia = db.query(License).filter(
            License.user_id == user_id
        ).first()

        if not licencia:
            licencia = LicenseService._crear_registro(db, user_id)
            logger.info(f"Registro de licencia creado para user_id={user_id}")

        # Parsear la fecha de vencimiento desde el .env con validación estricta
        fecha_expiry = LicenseService._parsear_fecha_expiry()

        # Si la fecha es inválida, bloquear como medida de seguridad
        if fecha_expiry is None:
            return LicenseStatusResponse(
                acceso_permitido=False,
                mensaje=(
                    f"Fecha de licencia inválida en configuración: "
                    f"'{settings.LICENSE_EXPIRY}'. "
                    "Contacta al administrador."
                ),
                dias_restantes=-1,
                segundos_restantes=0,
                fecha_vencimiento="Fecha inválida",
                mostrar_advertencia=False
            )

        # Calcular tiempo restante exacto
        ahora = datetime.now(timezone.utc)
        diferencia = fecha_expiry - ahora
        dias_restantes = diferencia.days
        segundos_restantes = max(int(diferencia.total_seconds()), 0)

        # Determinar si tiene acceso: registro activo Y fecha vigente
        esta_vigente = licencia.esta_activa and diferencia.total_seconds() > 0

        # Formatear fecha de vencimiento en español
        fecha_formateada = LicenseService._formatear_fecha(fecha_expiry)

        # Construir mensaje descriptivo según el estado actual
        if not licencia.esta_activa:
            mensaje = "Tu acceso ha sido desactivado. Contacta al administrador."
        elif dias_restantes < 0:
            dias_vencida = abs(dias_restantes)
            mensaje = (
                f"Tu licencia venció hace {dias_vencida} día(s). "
                "Ingresa la clave de renovación para continuar."
            )
        elif dias_restantes == 0:
            mensaje = "Tu licencia vence hoy. ¡Renueva ahora para no perder el acceso!"
        elif dias_restantes <= settings.LICENSE_WARNING_DAYS:
            mensaje = (
                f"Tu licencia vence en {dias_restantes} día(s) "
                f"({fecha_formateada}). Renueva pronto."
            )
        else:
            mensaje = f"Licencia activa. Vence el {fecha_formateada}."

        return LicenseStatusResponse(
            acceso_permitido=esta_vigente,
            mensaje=mensaje,
            dias_restantes=dias_restantes,
            segundos_restantes=segundos_restantes,
            fecha_vencimiento=fecha_formateada,
            mostrar_advertencia=(
                esta_vigente and dias_restantes <= settings.LICENSE_WARNING_DAYS
            )
        )

    # -----------------------------------------------
    # RENOVACIÓN CON CLAVE DEL .ENV
    # -----------------------------------------------

    @staticmethod
    def renovar_licencia(
        db: Session,
        user_id: int,
        clave_ingresada: str
    ) -> tuple[bool, str]:
        """
        Valida la clave ingresada contra LICENSE_KEY del .env.
        Usa hmac.compare_digest para comparación timing-safe.
        Si es válida: registra la renovación en la DB para auditoría.
        """
        # Obtener o crear el registro de licencia
        licencia = db.query(License).filter(
            License.user_id == user_id
        ).first()

        if not licencia:
            licencia = LicenseService._crear_registro(db, user_id)

        # Verificar que el registro no esté bloqueado manualmente
        if not licencia.esta_activa:
            return False, "Tu acceso está desactivado. Contacta al administrador."

        # Verificar que la fecha configurada en el .env sea válida antes de renovar
        fecha_expiry = LicenseService._parsear_fecha_expiry()
        if fecha_expiry is None:
            logger.error(
                f"Intento de renovación con fecha inválida en .env: "
                f"'{settings.LICENSE_EXPIRY}'"
            )
            return (
                False,
                f"Fecha de licencia inválida: '{settings.LICENSE_EXPIRY}'. "
                "El administrador debe corregir LICENSE_EXPIRY en el archivo .env. "
                "Formato correcto: YYYY-MM-DD con fecha real del calendario."
            )

        # Comparación timing-safe de la clave ingresada vs LICENSE_KEY del .env
        # hmac.compare_digest previene ataques de timing que revelan cuántos
        # caracteres son correctos midiendo el tiempo de respuesta
        clave_correcta = hmac.compare_digest(
            clave_ingresada.strip(),
            settings.LICENSE_KEY.strip()
        )

        if not clave_correcta:
            logger.warning(
                f"Intento de renovación con clave incorrecta: user_id={user_id}"
            )
            return False, "Clave de renovación incorrecta. Verifica e intenta de nuevo."

        # ✅ Clave válida — registrar la renovación en la DB para auditoría
        ahora = datetime.now(timezone.utc)
        licencia.renovaciones_count += 1
        licencia.ultima_renovacion = ahora
        licencia.esta_activa = True

        db.commit()
        db.refresh(licencia)

        # Leer la nueva fecha de vencimiento del .env para informar al usuario
        fecha_formateada = settings.LICENSE_EXPIRY
        try:
            fecha_formateada = LicenseService._formatear_fecha(fecha_expiry)
        except Exception:
            pass

        logger.info(
            f"Licencia renovada: user_id={user_id}, "
            f"renovación #{licencia.renovaciones_count}, "
            f"válida hasta {settings.LICENSE_EXPIRY}"
        )

        return (
            True,
            f"¡Acceso renovado exitosamente! Válido hasta el {fecha_formateada}."
        )

    # -----------------------------------------------
    # DEPENDENCY: bloquear endpoints si licencia vencida
    # -----------------------------------------------

    @staticmethod
    def verificar_acceso(db: Session, user_id: int) -> None:
        """
        Lanza HTTPException 402 si la licencia no está vigente.
        Úsala como dependencia en routers que requieren licencia activa.
        """
        from fastapi import HTTPException, status

        estado = LicenseService.obtener_estado(db, user_id)

        if not estado.acceso_permitido:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "codigo": "LICENCIA_VENCIDA",
                    "mensaje": estado.mensaje,
                    "dias_restantes": estado.dias_restantes,
                    "fecha_vencimiento": estado.fecha_vencimiento
                }
            )

    # -----------------------------------------------
    # MÉTODOS PRIVADOS DE APOYO
    # -----------------------------------------------

    @staticmethod
    def _parsear_fecha_expiry() -> datetime | None:
        """
        Parsea y valida la fecha LICENSE_EXPIRY del .env.
        Verifica que la fecha exista en el calendario real
        (por ejemplo, 2027-06-31 no existe porque junio tiene 30 días).
        Retorna None si la fecha es inválida para que el llamador pueda
        manejar el error apropiadamente en lugar de fallar silenciosamente.
        """
        try:
            # Separar los componentes de la fecha
            partes = settings.LICENSE_EXPIRY.strip().split("-")
            if len(partes) != 3:
                raise ValueError("Formato incorrecto")

            anio, mes, dia = int(partes[0]), int(partes[1]), int(partes[2])

            # Verificar que el día exista en ese mes y año usando calendar
            # calendar.monthrange retorna (dia_semana_inicio, total_dias_mes)
            _, dias_en_mes = calendar.monthrange(anio, mes)
            if dia > dias_en_mes:
                logger.error(
                    f"LICENSE_EXPIRY inválido: el mes {mes:02d}/{anio} "
                    f"solo tiene {dias_en_mes} días, no {dia}. "
                    f"Valor configurado: '{settings.LICENSE_EXPIRY}'. "
                    f"Corrección sugerida: {anio}-{mes:02d}-{dias_en_mes:02d}"
                )
                return None

            # Construir el datetime con zona horaria UTC
            return datetime(anio, mes, dia, 23, 59, 59, tzinfo=timezone.utc)

        except (ValueError, TypeError, AttributeError) as e:
            logger.error(
                f"LICENSE_EXPIRY con formato incorrecto: "
                f"'{settings.LICENSE_EXPIRY}'. "
                f"Formato esperado: YYYY-MM-DD. Error: {e}"
            )
            return None

    @staticmethod
    def _crear_registro(db: Session, user_id: int) -> License:
        """
        Crea el registro de licencia en la DB para un usuario nuevo.
        La fecha de vencimiento real viene del .env, no de aquí.
        """
        nuevo = License(
            user_id=user_id,
            esta_activa=True,
            renovaciones_count=0,
        )
        db.add(nuevo)
        db.commit()
        db.refresh(nuevo)
        return nuevo

    @staticmethod
    def _formatear_fecha(fecha: datetime) -> str:
        """
        Formatea una fecha datetime a texto en español.
        Ejemplo: '30 de junio de 2027'
        """
        meses = {
            1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
            5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
            9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
        }
        return f"{fecha.day} de {meses[fecha.month]} de {fecha.year}"