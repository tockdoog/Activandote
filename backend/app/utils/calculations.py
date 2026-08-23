# backend/app/utils/calculations.py
# Funciones de cálculo clínico-deportivo: IMC, Ruffier, alertas de salud,
# rangos de referencia saludable por género/edad y veredicto general del
# paciente. Usado por el reporte PDF orientado al paciente (visual y claro).

from typing import Optional, Tuple, List, Dict, Any


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
# Utilidad interna: normaliza el género a un perfil binario
# de referencia (masculino/femenino) para las tablas clínicas.
# "otro" y "prefiere_no_decir" usan el rango masculino como base
# neutra (se marca con nota en el reporte visual).
# -----------------------------------------------
def _perfil_genero(genero: str) -> str:
    """Retorna 'femenino' o 'masculino' según el valor recibido"""
    return "femenino" if genero and genero.lower() == "femenino" else "masculino"


def _es_genero_binario(genero: str) -> bool:
    """Indica si el género corresponde a una de las dos tablas de referencia clínica"""
    return bool(genero) and genero.lower() in ("masculino", "femenino")


# =================================================================
# TABLAS DE RANGOS DE REFERENCIA SALUDABLE POR INDICADOR
# Cada función "_limites_*" centraliza los puntos de corte para que
# la clasificación (texto) y el análisis visual (barras del PDF)
# usen siempre los mismos valores.
# =================================================================

def _limites_grasa_corporal(genero: str, edad: int) -> list:
    """Retorna [límite_excelente, límite_buena, límite_regular] de % de grasa corporal"""
    es_mujer = _perfil_genero(genero) == "femenino"
    if edad < 40:
        return [23, 30, 34] if es_mujer else [15, 19, 24]
    elif edad < 60:
        return [25, 32, 36] if es_mujer else [17, 21, 26]
    else:
        return [27, 33, 38] if es_mujer else [19, 23, 27]


def clasificar_grasa_corporal(porcentaje: float, genero: str, edad: int) -> str:
    """
    Clasifica el porcentaje de grasa corporal según género y rango de edad.
    Los rangos difieren entre hombres y mujeres por composición fisiológica base,
    y se ajustan por edad porque el % de grasa saludable aumenta con los años.
    """
    if porcentaje is None:
        return "Sin datos"

    rangos = _limites_grasa_corporal(genero, edad)

    if porcentaje < rangos[0]:
        return "Excelente"
    elif porcentaje < rangos[1]:
        return "Buena"
    elif porcentaje < rangos[2]:
        return "Regular"
    else:
        return "Elevada — requiere seguimiento"


def _limites_perimetro_abdominal(genero: str) -> Tuple[float, float]:
    """Retorna (límite_riesgo_moderado, límite_riesgo_alto) en cm según la OMS"""
    es_mujer = _perfil_genero(genero) == "femenino"
    return (80.0, 88.0) if es_mujer else (94.0, 102.0)


def clasificar_perimetro_abdominal(cm: float, genero: str) -> str:
    """
    Clasifica el riesgo cardiometabólico según perímetro abdominal y género,
    de acuerdo con los puntos de corte recomendados por la OMS.
    """
    if cm is None:
        return "Sin datos"

    limite_moderado, limite_alto = _limites_perimetro_abdominal(genero)

    if cm < limite_moderado:
        return "Riesgo bajo"
    elif cm < limite_alto:
        return "Riesgo moderado"
    else:
        return "Riesgo alto"


def _limites_agua_corporal(genero: str) -> Tuple[float, float]:
    """Retorna (mínimo, máximo) saludable de % de agua corporal total"""
    es_mujer = _perfil_genero(genero) == "femenino"
    return (45.0, 60.0) if es_mujer else (50.0, 65.0)


def clasificar_agua_corporal(porcentaje: float, genero: str) -> str:
    """Clasifica el porcentaje de agua corporal según el rango saludable por género"""
    if porcentaje is None:
        return "Sin datos"

    minimo, maximo = _limites_agua_corporal(genero)

    if porcentaje < minimo - 5:
        return "Muy bajo — riesgo de deshidratación"
    elif porcentaje < minimo:
        return "Bajo"
    elif porcentaje <= maximo:
        return "Saludable"
    else:
        return "Elevado"


def _limites_masa_osea(genero: str) -> Tuple[float, float]:
    """Retorna (mínimo, máximo) saludable de % de masa ósea respecto al peso corporal"""
    es_mujer = _perfil_genero(genero) == "femenino"
    return (2.5, 4.5) if es_mujer else (3.0, 5.5)


def clasificar_masa_osea(porcentaje_hueso: float, genero: str) -> str:
    """Clasifica el porcentaje de masa ósea según el rango saludable por género"""
    if porcentaje_hueso is None:
        return "Sin datos"

    minimo, maximo = _limites_masa_osea(genero)

    if porcentaje_hueso < minimo:
        return "Baja — vigilar salud ósea"
    elif porcentaje_hueso <= maximo:
        return "Normal"
    else:
        return "Alta"


def clasificar_presion_arterial(sistolica: int, diastolica: int) -> str:
    """
    Clasifica la presión arterial según las categorías estándar
    (American Heart Association). No varía por género.
    """
    if sistolica is None or diastolica is None:
        return "Sin datos"

    if sistolica >= 180 or diastolica >= 120:
        return "Crisis hipertensiva — atención médica inmediata"
    elif sistolica >= 140 or diastolica >= 90:
        return "Hipertensión etapa 2"
    elif sistolica >= 130 or diastolica >= 80:
        return "Hipertensión etapa 1"
    elif sistolica >= 120:
        return "Elevada"
    else:
        return "Normal"


def calcular_grasa_kg(peso_kg: float, porcentaje_grasa: float) -> Optional[float]:
    """
    Convierte el porcentaje de grasa corporal a kilogramos de grasa,
    usando el peso actual del paciente.
    Fórmula: kg de grasa = peso(kg) × (% grasa / 100)
    """
    if peso_kg is None or porcentaje_grasa is None:
        return None
    return round(peso_kg * (porcentaje_grasa / 100), 1)


def calcular_masa_magra_kg(peso_kg: float, porcentaje_grasa: float) -> Optional[float]:
    """
    Calcula la masa corporal libre de grasa (masa magra) en kilogramos:
    músculo, huesos, órganos y agua. Es el complemento de la grasa corporal.
    """
    grasa_kg = calcular_grasa_kg(peso_kg, porcentaje_grasa)
    if grasa_kg is None or peso_kg is None:
        return None
    return round(peso_kg - grasa_kg, 1)


def calcular_rango_peso_saludable(talla_metros: float) -> Optional[Tuple[float, float]]:
    """
    Calcula el rango de peso saludable de referencia según la talla,
    usando los límites de IMC normal de la OMS (18.5 – 24.9).
    Es una referencia general: no considera contextura ósea individual.
    """
    if not talla_metros or talla_metros <= 0:
        return None
    peso_min = round(18.5 * (talla_metros ** 2), 1)
    peso_max = round(24.9 * (talla_metros ** 2), 1)
    return peso_min, peso_max


# -----------------------------------------------
# Sistema de alertas automáticas de salud
# -----------------------------------------------
def generar_alertas(evaluacion_data: dict) -> Tuple[bool, str]:
    """
    Analiza los datos de una evaluación y genera alertas si hay indicadores
    fuera de rangos saludables. Retorna (tiene_alerta, detalle_alerta).
    """
    alertas = []

    imc = evaluacion_data.get("imc")
    if imc:
        if imc < 18.5:
            alertas.append(f"⚠️ IMC bajo ({imc}) - Posible delgadez")
        elif imc >= 30:
            alertas.append(f"⚠️ IMC elevado ({imc}) - Obesidad")

    ta_sistolica = evaluacion_data.get("tension_sistolica")
    ta_diastolica = evaluacion_data.get("tension_diastolica")
    if ta_sistolica and ta_diastolica:
        if ta_sistolica >= 140 or ta_diastolica >= 90:
            alertas.append(f"⚠️ Tensión arterial elevada ({ta_sistolica}/{ta_diastolica} mmHg)")

    oxigenacion = evaluacion_data.get("oxigenacion_porcentaje")
    if oxigenacion and oxigenacion < 95:
        alertas.append(f"⚠️ Oxigenación baja ({oxigenacion}%) - Revisar con médico")

    fc = evaluacion_data.get("frecuencia_cardiaca_rpm")
    if fc:
        if fc > 100:
            alertas.append(f"⚠️ FC en reposo elevada ({fc} lpm) - Posible taquicardia")
        elif fc < 50:
            alertas.append(f"ℹ️ FC en reposo muy baja ({fc} lpm) - Verificar")

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
    campos_positivos = [
        "musculo_kg", "porcentaje_agua", "fuerza_manual_der_kg",
        "fuerza_manual_izq_kg", "test_wells_cm", "oxigenacion_porcentaje"
    ]
    campos_negativos = [
        "porcentaje_grasa", "imc", "frecuencia_cardiaca_rpm",
        "perimetro_abdominal_cm", "indice_ruffier", "peso_kg"
    ]

    if campo in campos_positivos:
        return delta > 0
    elif campo in campos_negativos:
        return delta < 0

    return None


# -----------------------------------------------
# Promedios históricos de todas las evaluaciones del paciente
# -----------------------------------------------
def calcular_promedios_evaluaciones(evaluaciones: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """
    Calcula el promedio de cada indicador numérico a través de todo el
    historial de evaluaciones del paciente. Ignora valores nulos por campo.
    """
    campos_promediables = [
        "peso_kg", "imc", "porcentaje_grasa", "porcentaje_agua",
        "musculo_kg", "oxigenacion_porcentaje", "frecuencia_cardiaca_rpm",
        "perimetro_abdominal_cm", "indice_ruffier",
        "fuerza_manual_der_kg", "fuerza_manual_izq_kg", "test_wells_cm"
    ]

    promedios: Dict[str, Optional[float]] = {}
    for campo in campos_promediables:
        valores = [e.get(campo) for e in evaluaciones if e.get(campo) is not None]
        promedios[campo] = round(sum(valores) / len(valores), 2) if valores else None

    return promedios


# -----------------------------------------------
# Resumen de progreso: compara la primera y la última evaluación
# -----------------------------------------------
def generar_resumen_progreso(evaluaciones: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Genera un resumen de progreso comparando la primera y la última evaluación
    registrada. Retorna None si el paciente tiene menos de dos evaluaciones.
    """
    if not evaluaciones or len(evaluaciones) < 2:
        return None

    primera = evaluaciones[0]
    ultima = evaluaciones[-1]

    return {
        "fecha_inicial": str(primera.get("fecha_evaluacion")),
        "fecha_final": str(ultima.get("fecha_evaluacion")),
        "total_evaluaciones": len(evaluaciones),
        "comparacion": comparar_evaluaciones(primera, ultima)
    }


# =================================================================
# ANÁLISIS VISUAL PARA EL PACIENTE
# Construye, para cada indicador, una "ficha" con: valor actual,
# clasificación en texto, si está o no en rango saludable, y los
# límites numéricos (escala completa + zona saludable) que el PDF
# usa para dibujar la barra de rango con el marcador del resultado.
# =================================================================

def _ficha_indicador(
    campo: str, nombre: str, valor: Optional[float], unidad: str,
    clasificacion: str, es_saludable: Optional[bool],
    escala_min: float, escala_max: float,
    zona_min: float, zona_max: float,
    texto_referencia: str,
    nota_extra: Optional[str] = None
) -> Dict[str, Any]:
    """
    Construye el diccionario estándar de un indicador para el reporte visual.
    nota_extra es un dato complementario opcional (ej. equivalencia en kg)
    que se muestra debajo de la barra de rango en el PDF.
    """
    return {
        "campo": campo,
        "nombre": nombre,
        "valor": valor,
        "unidad": unidad,
        "clasificacion": clasificacion,
        "es_saludable": es_saludable,
        "escala_min": escala_min,
        "escala_max": escala_max,
        "zona_min": zona_min,
        "zona_max": zona_max,
        "texto_referencia": texto_referencia,
        "nota_extra": nota_extra
    }


def generar_analisis_completo(evaluacion: Dict[str, Any], genero: str, edad: int,
                               talla_metros: Optional[float]) -> Dict[str, Any]:
    """
    Genera el análisis visual completo de una evaluación: una ficha por cada
    indicador de salud/composición corporal con su rango saludable, más un
    veredicto general del estado del paciente.

    Retorna {"indicadores": [...], "veredicto": {...}}
    """
    indicadores: List[Dict[str, Any]] = []
    nota_genero = "" if _es_genero_binario(genero) else \
        " (rango de referencia general, no específico por género)"

    # ── IMC ──────────────────────────────────────────────────────────────
    imc = evaluacion.get("imc")
    if imc is not None:
        indicadores.append(_ficha_indicador(
            "imc", "Índice de Masa Corporal (IMC)", imc, "",
            clasificar_imc(imc), 18.5 <= imc < 25.0,
            escala_min=14, escala_max=40, zona_min=18.5, zona_max=24.9,
            texto_referencia="18.5 – 24.9 (normal)"
        ))

    # ── Peso vs. rango saludable según talla ────────────────────────────
    peso = evaluacion.get("peso_kg")
    rango_peso = calcular_rango_peso_saludable(talla_metros) if talla_metros else None
    if peso is not None and rango_peso:
        peso_min, peso_max = rango_peso
        indicadores.append(_ficha_indicador(
            "peso_kg", "Peso corporal", peso, "kg",
            "Dentro del rango" if peso_min <= peso <= peso_max else
            ("Por debajo del rango" if peso < peso_min else "Por encima del rango"),
            peso_min <= peso <= peso_max,
            escala_min=max(peso_min - 20, 10), escala_max=peso_max + 20,
            zona_min=peso_min, zona_max=peso_max,
            texto_referencia=f"{peso_min} – {peso_max} kg según su talla"
        ))

    # ── % Grasa corporal (con equivalencia en kilogramos) ────────────────
    grasa = evaluacion.get("porcentaje_grasa")
    if grasa is not None:
        limites = _limites_grasa_corporal(genero, edad)
        grasa_kg = calcular_grasa_kg(peso, grasa)
        masa_magra_kg = calcular_masa_magra_kg(peso, grasa)

        nota_kg = None
        if grasa_kg is not None and masa_magra_kg is not None:
            nota_kg = (
                f"De sus {peso} kg de peso total: {grasa_kg} kg son grasa corporal "
                f"y {masa_magra_kg} kg corresponden a masa magra (músculo, huesos, órganos y agua)"
            )
        elif grasa_kg is not None:
            nota_kg = f"Equivale a {grasa_kg} kg de grasa corporal"

        indicadores.append(_ficha_indicador(
            "porcentaje_grasa", f"% Grasa corporal{nota_genero}", grasa, "%",
            clasificar_grasa_corporal(grasa, genero, edad),
            grasa < limites[1],
            escala_min=5, escala_max=limites[2] + 10, zona_min=0, zona_max=limites[1],
            texto_referencia=f"Menos de {limites[1]}% (excelente/buena)",
            nota_extra=nota_kg
        ))

    # ── % Agua corporal ──────────────────────────────────────────────────
    agua = evaluacion.get("porcentaje_agua")
    if agua is not None:
        minimo, maximo = _limites_agua_corporal(genero)
        indicadores.append(_ficha_indicador(
            "porcentaje_agua", f"% Agua corporal{nota_genero}", agua, "%",
            clasificar_agua_corporal(agua, genero),
            minimo <= agua <= maximo,
            escala_min=30, escala_max=75, zona_min=minimo, zona_max=maximo,
            texto_referencia=f"{minimo} – {maximo}%"
        ))

    # ── % Masa ósea ──────────────────────────────────────────────────────
    hueso = evaluacion.get("porcentaje_hueso")
    if hueso is not None:
        minimo, maximo = _limites_masa_osea(genero)
        indicadores.append(_ficha_indicador(
            "porcentaje_hueso", f"% Masa ósea{nota_genero}", hueso, "%",
            clasificar_masa_osea(hueso, genero),
            minimo <= hueso <= maximo,
            escala_min=1, escala_max=8, zona_min=minimo, zona_max=maximo,
            texto_referencia=f"{minimo} – {maximo}%"
        ))

    # ── Perímetro abdominal ──────────────────────────────────────────────
    perimetro = evaluacion.get("perimetro_abdominal_cm")
    if perimetro is not None:
        limite_moderado, limite_alto = _limites_perimetro_abdominal(genero)
        indicadores.append(_ficha_indicador(
            "perimetro_abdominal_cm", f"Circunferencia abdominal{nota_genero}", perimetro, "cm",
            clasificar_perimetro_abdominal(perimetro, genero),
            perimetro < limite_moderado,
            escala_min=60, escala_max=limite_alto + 20, zona_min=0, zona_max=limite_moderado,
            texto_referencia=f"Menos de {limite_moderado} cm (riesgo bajo)"
        ))

    # ── Presión arterial (dos indicadores: sistólica y diastólica) ──────
    sistolica = evaluacion.get("tension_sistolica")
    diastolica = evaluacion.get("tension_diastolica")
    if sistolica is not None and diastolica is not None:
        clasif_presion = clasificar_presion_arterial(sistolica, diastolica)
        es_normal = clasif_presion == "Normal"
        indicadores.append(_ficha_indicador(
            "tension_sistolica", "Presión sistólica", sistolica, "mmHg",
            clasif_presion, es_normal,
            escala_min=80, escala_max=200, zona_min=90, zona_max=119,
            texto_referencia="Menos de 120 mmHg"
        ))
        indicadores.append(_ficha_indicador(
            "tension_diastolica", "Presión diastólica", diastolica, "mmHg",
            clasif_presion, es_normal,
            escala_min=40, escala_max=130, zona_min=60, zona_max=79,
            texto_referencia="Menos de 80 mmHg"
        ))

    # ── Veredicto general del estado del paciente ────────────────────────
    veredicto = _generar_veredicto_general(indicadores)

    return {"indicadores": indicadores, "veredicto": veredicto}


def _generar_veredicto_general(indicadores: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calcula un veredicto general del estado del paciente a partir del
    porcentaje de indicadores que están dentro de su rango saludable.
    """
    evaluables = [i for i in indicadores if i["es_saludable"] is not None]
    fuera_de_rango = [i for i in evaluables if i["es_saludable"] is False]

    if not evaluables:
        return {
            "estado": "Sin datos suficientes",
            "color": "gris",
            "mensaje": "Aún no hay suficientes indicadores registrados para generar un veredicto.",
            "porcentaje_saludable": None,
            "indicadores_fuera_de_rango": []
        }

    porcentaje_saludable = round(
        (len(evaluables) - len(fuera_de_rango)) / len(evaluables) * 100
    )

    if porcentaje_saludable == 100:
        estado, color = "Excelente", "verde"
        mensaje = "Todos sus indicadores evaluados están dentro del rango saludable. ¡Siga así!"
    elif porcentaje_saludable >= 75:
        estado, color = "Buena", "verde"
        mensaje = "La mayoría de sus indicadores están en rango saludable, con algunos puntos a mejorar."
    elif porcentaje_saludable >= 50:
        estado, color = "Regular", "amarillo"
        mensaje = "Varios indicadores requieren atención. Se recomienda ajustar hábitos y dar seguimiento cercano."
    else:
        estado, color = "Requiere atención", "rojo"
        mensaje = "La mayoría de sus indicadores están fuera del rango saludable. Se recomienda consultar con su entrenador o médico."

    return {
        "estado": estado,
        "color": color,
        "mensaje": mensaje,
        "porcentaje_saludable": porcentaje_saludable,
        "indicadores_fuera_de_rango": [i["nombre"] for i in fuera_de_rango]
    }