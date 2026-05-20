# backend/app/utils/calculations.py
# Funciones de cálculo clínico-deportivo: IMC, Ruffier, alertas de salud

from typing import Optional, Tuple


# -----------------------------------------------
# Cálculo del Índice de Masa Corporal (IMC)
# -----------------------------------------------
def calcular_imc(peso_kg: float, talla_metros: float) -> Optional[float]:
    """
    Calcula el Índice de Masa Corporal.
    Fórmula: IMC = peso(kg) / talla(m)²
    """
    if not peso_kg or not talla_metros or talla_metros <= 0:
        return None
    return round(peso_kg / (talla_metros ** 2), 2)


def clasificar_imc(imc: float) -> str:
    """
    Clasifica el IMC según estándares OMS.
    Retorna categoría en español.
    """
    if imc < 16.0:
        return "Delgadez severa"
    elif imc < 17.0:
        return "Delgadez moderada"
    elif imc < 18.5:
        return "Delgadez leve"
    elif imc < 25.0:
        return "Normal"
    elif imc < 30.0:
        return "Sobrepeso"
    elif imc < 35.0:
        return "Obesidad grado I"
    elif imc < 40.0:
        return "Obesidad grado II"
    else:
        return "Obesidad grado III"


# -----------------------------------------------
# Cálculo del Índice de Ruffier (resistencia CV)
# -----------------------------------------------
def calcular_indice_ruffier(
    fc_reposo: int,        # P1: FC antes del esfuerzo
    fc_post_esfuerzo: int, # P2: FC inmediatamente después (30 sentadillas)
    fc_recuperacion: int   # P3: FC al minuto de recuperación
) -> Optional[float]:
    """
    Calcula el Índice de Ruffier-Dickson para medir resistencia cardiovascular.
    Fórmula: IR = (P1 + P2 + P3 - 200) / 10
    """
    if None in [fc_reposo, fc_post_esfuerzo, fc_recuperacion]:
        return None
    return round((fc_reposo + fc_post_esfuerzo + fc_recuperacion - 200) / 10, 2)


def clasificar_ruffier(indice: float) -> str:
    """
    Clasifica el resultado del Test de Ruffier.
    Menor índice = mejor condición cardiovascular.
    """
    if indice < 0:
        return "Excelente"
    elif indice <= 5:
        return "Muy buena"
    elif indice <= 10:
        return "Buena"
    elif indice <= 15:
        return "Regular"
    else:
        return "Deficiente"


# -----------------------------------------------
# Clasificación de Wells para flexibilidad
# -----------------------------------------------
def clasificar_wells(valor_cm: float, genero: str, edad: int) -> str:
    """
    Clasifica el resultado del Test de Wells según género y edad.
    Valores positivos = flexibilidad adelante del cero.
    """
    # Parámetros simplificados por género (adultos)
    if genero.lower() == "femenino":
        if valor_cm > 30:
            return "Excelente"
        elif valor_cm > 25:
            return "Muy buena"
        elif valor_cm > 20:
            return "Buena"
        elif valor_cm > 15:
            return "Regular"
        else:
            return "Deficiente"
    else:
        if valor_cm > 25:
            return "Excelente"
        elif valor_cm > 20:
            return "Muy buena"
        elif valor_cm > 15:
            return "Buena"
        elif valor_cm > 10:
            return "Regular"
        else:
            return "Deficiente"


# -----------------------------------------------
# Sistema de alertas automáticas de salud
# -----------------------------------------------
def generar_alertas(evaluacion_data: dict) -> Tuple[bool, str]:
    """
    Analiza los datos de una evaluación y genera alertas si hay indicadores
    fuera de rangos saludables. Retorna (tiene_alerta, detalle_alerta).
    """
    alertas = []

    # Alerta por IMC fuera de rango saludable
    imc = evaluacion_data.get("imc")
    if imc:
        if imc < 18.5:
            alertas.append(f"⚠️ IMC bajo ({imc}) - Posible delgadez")
        elif imc >= 30:
            alertas.append(f"⚠️ IMC elevado ({imc}) - Obesidad")

    # Alerta por presión arterial alta (HTA)
    ta_sistolica = evaluacion_data.get("tension_sistolica")
    ta_diastolica = evaluacion_data.get("tension_diastolica")
    if ta_sistolica and ta_diastolica:
        if ta_sistolica >= 140 or ta_diastolica >= 90:
            alertas.append(f"⚠️ Tensión arterial elevada ({ta_sistolica}/{ta_diastolica} mmHg)")

    # Alerta por saturación de oxígeno baja
    oxigenacion = evaluacion_data.get("oxigenacion_porcentaje")
    if oxigenacion and oxigenacion < 95:
        alertas.append(f"⚠️ Oxigenación baja ({oxigenacion}%) - Revisar con médico")

    # Alerta por frecuencia cardíaca en reposo elevada
    fc = evaluacion_data.get("frecuencia_cardiaca_rpm")
    if fc:
        if fc > 100:
            alertas.append(f"⚠️ FC en reposo elevada ({fc} lpm) - Posible taquicardia")
        elif fc < 50:
            alertas.append(f"ℹ️ FC en reposo muy baja ({fc} lpm) - Verificar")

    # Alerta por grasa corporal muy alta
    grasa = evaluacion_data.get("porcentaje_grasa")
    if grasa:
        if grasa > 35:
            alertas.append(f"⚠️ % Grasa muy elevado ({grasa}%)")

    tiene_alerta = len(alertas) > 0
    detalle = " | ".join(alertas) if alertas else ""

    return tiene_alerta, detalle


# -----------------------------------------------
# Comparación de progreso entre evaluaciones
# -----------------------------------------------
def comparar_evaluaciones(eval_anterior: dict, eval_nueva: dict) -> dict:
    """
    Compara dos evaluaciones y calcula deltas (cambios) para cada indicador.
    Positivo = mejora o aumento, negativo = reducción.
    """
    campos_comparables = [
        "peso_kg", "porcentaje_grasa", "porcentaje_agua",
        "musculo_kg", "imc", "oxigenacion_porcentaje",
        "frecuencia_cardiaca_rpm", "perimetro_abdominal_cm",
        "fuerza_manual_der_kg", "test_wells_cm", "indice_ruffier"
    ]

    comparacion = {}
    for campo in campos_comparables:
        val_ant = eval_anterior.get(campo)
        val_nue = eval_nueva.get(campo)

        if val_ant is not None and val_nue is not None:
            delta = round(val_nue - val_ant, 2)
            porcentaje_cambio = round((delta / val_ant) * 100, 1) if val_ant != 0 else 0

            comparacion[campo] = {
                "anterior": val_ant,
                "actual": val_nue,
                "delta": delta,
                "porcentaje_cambio": porcentaje_cambio,
                "mejoro": _determinar_mejora(campo, delta)
            }

    return comparacion


def _determinar_mejora(campo: str, delta: float) -> Optional[bool]:
    """
    Determina si un cambio en un campo es una mejora o empeoramiento.
    Depende del contexto del campo (algunos deben bajar, otros subir).
    """
    # Campos donde subir es bueno (músculo, agua, fuerza, flexibilidad, oxigenación)
    campos_positivos = [
        "musculo_kg", "porcentaje_agua", "fuerza_manual_der_kg",
        "fuerza_manual_izq_kg", "test_wells_cm", "oxigenacion_porcentaje"
    ]

    # Campos donde bajar es bueno (grasa, IMC, FC en reposo, perímetro abdominal, Ruffier)
    campos_negativos = [
        "porcentaje_grasa", "imc", "frecuencia_cardiaca_rpm",
        "perimetro_abdominal_cm", "indice_ruffier", "peso_kg"
    ]

    if campo in campos_positivos:
        return delta > 0
    elif campo in campos_negativos:
        return delta < 0

    return None