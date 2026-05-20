// frontend/js/evaluations.js
// Lógica de evaluaciones físicas: formulario, historial, gráficas y cálculos automáticos
// Usado tanto en evaluations.html (formulario) como en patient-detail.html (historial)

// -----------------------------------------------
// Verificación de sesión activa
// -----------------------------------------------
(function verificarAuth() {
  if (!api.estaAutenticado()) {
    window.location.href = 'index.html';
  }
})();

// -----------------------------------------------
// DETECCIÓN DE LA PÁGINA ACTIVA
// -----------------------------------------------
// Este archivo es compartido por evaluations.html y patient-detail.html.
// Se detecta cuál página está activa por el elemento raíz del formulario/historial.
const esFormulario = !!document.getElementById('form-evaluacion');
const esDetalle = !!document.getElementById('tbody-evaluaciones');

// Instancias de Chart.js para evitar duplicados
const graficas = {};

// -----------------------------------------------
// INICIALIZACIÓN SEGÚN LA PÁGINA
// -----------------------------------------------
document.addEventListener('DOMContentLoaded', function () {
  inicializarUsuario();

  if (esFormulario) {
    inicializarFormulario();
  } else if (esDetalle) {
    inicializarDetallePaciente();
  }
});

// -----------------------------------------------
// INFO DE USUARIO EN SIDEBAR
// -----------------------------------------------

/** Muestra nombre e iniciales del entrenador en el sidebar */
function inicializarUsuario() {
  const usuario = api.getUsuario();
  if (!usuario) return;
  const iniciales = usuario.nombre_completo.split(' ').slice(0, 2).map(n => n[0]).join('').toUpperCase();
  const avatarEl = document.getElementById('user-avatar');
  const nameEl = document.getElementById('user-name');
  const planEl = document.getElementById('user-plan');
  if (avatarEl) avatarEl.textContent = iniciales;
  if (nameEl) nameEl.textContent = usuario.nombre_completo;
  if (planEl) planEl.textContent = `Plan ${usuario.plan.toUpperCase()}`;
}

// ===============================================
// *** PÁGINA: FORMULARIO DE EVALUACIÓN ***
// ===============================================

/**
 * Inicializa el formulario de nueva evaluación.
 * Lee el patient_id de la URL y carga los datos del paciente.
 */
async function inicializarFormulario() {
  const params = new URLSearchParams(window.location.search);
  const patientId = params.get('patient_id');

  if (!patientId) {
    mostrarToast('No se especificó un paciente', 'error');
    setTimeout(() => window.location.href = 'patients.html', 1500);
    return;
  }

  // Poner la fecha de hoy por defecto
  document.getElementById('eval-fecha').value = new Date().toISOString().split('T')[0];

  // Cargar los datos del paciente para el contexto del formulario
  try {
    const paciente = await api.obtenerPaciente(patientId);
    const iniciales = paciente.nombre_completo.split(' ').slice(0, 2).map(n => n[0]).join('').toUpperCase();

    document.getElementById('eval-paciente-avatar').textContent = iniciales;
    document.getElementById('eval-paciente-nombre').textContent = paciente.nombre_completo;
    document.getElementById('eval-paciente-meta').textContent =
      `${paciente.edad} años · ${paciente.genero} · ${paciente.talla_metros} m · Peso inicial: ${paciente.peso_inicial_kg} kg`;

    // Mostrar el número de evaluación que corresponde
    const evals = await api.listarEvaluaciones(patientId);
    document.getElementById('eval-numero').textContent = evals.length + 1;

    // Configurar breadcrumb y botón cancelar
    const breadcrumb = document.getElementById('breadcrumb-paciente');
    if (breadcrumb) {
      breadcrumb.textContent = paciente.nombre_completo;
      breadcrumb.href = `patient-detail.html?id=${patientId}`;
    }

    const btnCancelar = document.getElementById('btn-cancelar-eval');
    if (btnCancelar) btnCancelar.href = `patient-detail.html?id=${patientId}`;

    // Pre-llenar talla del paciente si está disponible
    if (paciente.talla_metros) {
      document.getElementById('eval-talla').value = paciente.talla_metros;
    }

  } catch (error) {
    mostrarToast('Error al cargar datos del paciente', 'error');
  }

  // Vincular el envío del formulario
  document.getElementById('form-evaluacion').addEventListener('submit', enviarFormulario);
}

/**
 * Procesa el envío del formulario de evaluación.
 * Valida la fecha y construye el objeto de datos para la API.
 */
async function enviarFormulario(e) {
  e.preventDefault();

  const params = new URLSearchParams(window.location.search);
  const patientId = params.get('patient_id');

  const fecha = document.getElementById('eval-fecha').value;
  if (!fecha) {
    document.getElementById('err-eval-fecha').style.display = 'block';
    document.getElementById('eval-fecha').classList.add('invalido');
    return;
  }

  // Función auxiliar: leer número o null si está vacío
  const num = (id) => {
    const val = document.getElementById(id)?.value;
    return val !== '' && val != null ? parseFloat(val) : null;
  };

  const numInt = (id) => {
    const val = document.getElementById(id)?.value;
    return val !== '' && val != null ? parseInt(val) : null;
  };

  const str = (id) => {
    const val = document.getElementById(id)?.value?.trim();
    return val || null;
  };

  // Construir objeto con todos los campos del formulario
  const datos = {
    fecha_evaluacion: fecha,
    condicion_fisica: str('eval-condicion'),

    // Composición corporal
    peso_kg: num('eval-peso'),
    talla_metros: num('eval-talla'),
    porcentaje_grasa: num('eval-grasa'),
    porcentaje_agua: num('eval-agua'),
    porcentaje_hueso: num('eval-hueso'),
    musculo_kg: num('eval-musculo'),
    edad_metabolica: numInt('eval-edad-metabolica'),
    riesgo_cardiovascular: str('eval-riesgo-cv'),

    // Indicadores de salud
    oxigenacion_porcentaje: num('eval-oxigenacion'),
    frecuencia_cardiaca_rpm: numInt('eval-fc'),
    tension_sistolica: numInt('eval-ta-sistolica'),
    tension_diastolica: numInt('eval-ta-diastolica'),
    perimetro_abdominal_cm: num('eval-perimetro'),
    horas_sueno: num('eval-sueno'),

    // Evaluación física
    fc_reposo: numInt('eval-fc-reposo'),
    fc_post_esfuerzo: numInt('eval-fc-post'),
    fc_minuto_recuperacion: numInt('eval-fc-rec'),
    fuerza_manual_der_kg: num('eval-fuerza-der'),
    fuerza_manual_izq_kg: num('eval-fuerza-izq'),
    test_wells_cm: num('eval-wells'),
    notas_entrenador: str('eval-notas')
  };

  // Eliminar claves con valores null para no enviarlas
  Object.keys(datos).forEach(k => datos[k] === null && delete datos[k]);

  const btn = document.getElementById('btn-guardar-eval');
  document.getElementById('btn-eval-texto').style.display = 'none';
  document.getElementById('btn-eval-cargando').style.display = 'inline';
  btn.disabled = true;

  try {
    await api.crearEvaluacion(patientId, datos);
    mostrarToast('¡Evaluación guardada exitosamente!', 'exito');

    // Redirigir al detalle del paciente tras guardar
    setTimeout(() => {
      window.location.href = `patient-detail.html?id=${patientId}`;
    }, 900);

  } catch (error) {
    mostrarToast(error.message || 'Error al guardar la evaluación', 'error');
    document.getElementById('btn-eval-texto').style.display = 'inline';
    document.getElementById('btn-eval-cargando').style.display = 'none';
    btn.disabled = false;
  }
}

// -----------------------------------------------
// CÁLCULOS EN TIEMPO REAL DEL FORMULARIO
// -----------------------------------------------

/**
 * Calcula y muestra el IMC en tiempo real mientras el usuario ingresa
 * el peso y la talla en el formulario de evaluación.
 */
function calcularIMCPreview() {
  const peso = parseFloat(document.getElementById('eval-peso')?.value);
  const talla = parseFloat(document.getElementById('eval-talla')?.value);
  const valorEl = document.getElementById('imc-preview-valor');
  const catEl = document.getElementById('imc-preview-cat');

  if (!valorEl || !catEl) return;

  if (peso && talla && talla > 0) {
    const imc = peso / (talla * talla);
    valorEl.textContent = imc.toFixed(1);
    catEl.textContent = clasificarIMC(imc);
    // Colorear según categoría
    if (imc < 18.5 || imc >= 30) {
      valorEl.style.color = 'var(--rojo-suave)';
    } else {
      valorEl.style.color = '#00CC55';
    }
  } else {
    valorEl.textContent = '—';
    valorEl.style.color = 'var(--blanco-puro)';
    catEl.textContent = 'Ingrese peso y talla';
  }
}

/**
 * Calcula y muestra el índice de Ruffier en tiempo real
 * cuando se ingresan las tres frecuencias cardíacas del test.
 */
function calcularRuffierPreview() {
  const p1 = parseInt(document.getElementById('eval-fc-reposo')?.value);
  const p2 = parseInt(document.getElementById('eval-fc-post')?.value);
  const p3 = parseInt(document.getElementById('eval-fc-rec')?.value);
  const valorEl = document.getElementById('ruffier-preview-valor');
  const clasifEl = document.getElementById('ruffier-preview-clasif');

  if (!valorEl || !clasifEl) return;

  if (p1 && p2 && p3) {
    const ir = (p1 + p2 + p3 - 200) / 10;
    valorEl.textContent = ir.toFixed(1);
    clasifEl.textContent = clasificarRuffier(ir);
    valorEl.style.color = ir > 10 ? 'var(--rojo-suave)' : '#00CC55';
  } else {
    valorEl.textContent = '—';
    valorEl.style.color = 'var(--blanco-puro)';
    clasifEl.textContent = 'Ingrese las tres frecuencias';
  }
}

/** Clasificación del IMC según rangos OMS */
function clasificarIMC(imc) {
  if (imc < 16)   return 'Delgadez severa';
  if (imc < 17)   return 'Delgadez moderada';
  if (imc < 18.5) return 'Delgadez leve';
  if (imc < 25)   return 'Normal';
  if (imc < 30)   return 'Sobrepeso';
  if (imc < 35)   return 'Obesidad Grado I';
  if (imc < 40)   return 'Obesidad Grado II';
  return 'Obesidad Grado III';
}

/** Clasificación del índice de Ruffier */
function clasificarRuffier(ir) {
  if (ir < 0)   return 'Excelente';
  if (ir <= 5)  return 'Muy buena';
  if (ir <= 10) return 'Buena';
  if (ir <= 15) return 'Regular';
  return 'Deficiente';
}

// ===============================================
// *** PÁGINA: DETALLE DEL PACIENTE ***
// ===============================================

/**
 * Inicializa la vista de detalle del paciente.
 * Lee el patient_id de la URL y carga perfil, evaluaciones y gráficas.
 */
async function inicializarDetallePaciente() {
  const params = new URLSearchParams(window.location.search);
  const patientId = params.get('id');

  if (!patientId) {
    window.location.href = 'patients.html';
    return;
  }

  try {
    // Cargar perfil y evaluaciones en paralelo
    const [paciente, evaluaciones] = await Promise.all([
      api.obtenerPaciente(patientId),
      api.listarEvaluaciones(patientId)
    ]);

    renderizarPerfilPaciente(paciente);
    renderizarIndicadoresUltimos(evaluaciones);
    renderizarHistorialEvaluaciones(evaluaciones, patientId);
    renderizarGraficasProgreso(evaluaciones);

    // Configurar botón de exportar Excel
    const btnExcel = document.getElementById('btn-exportar-excel');
    if (btnExcel) {
      btnExcel.onclick = () => api.exportarExcel(patientId, paciente.nombre_completo);
    }

    // Configurar breadcrumb
    const breadcrumb = document.getElementById('breadcrumb-nombre');
    if (breadcrumb) breadcrumb.textContent = paciente.nombre_completo;

    // Configurar botón de nueva evaluación
    const btnNueva = document.querySelector('[onclick="abrirModalEvaluacion()"]');
    if (btnNueva) {
      btnNueva.setAttribute('onclick', `window.location.href='evaluations.html?patient_id=${patientId}'`);
    }

  } catch (error) {
    mostrarToast('Error al cargar el paciente', 'error');
    console.error(error);
  }
}

/** Renderiza la tarjeta de perfil del paciente */
function renderizarPerfilPaciente(p) {
  const el = document.getElementById('perfil-paciente');
  if (!el) return;

  const iniciales = p.nombre_completo.split(' ').slice(0, 2).map(n => n[0]).join('').toUpperCase();
  const estadoBadge = p.estado === 'activo'
    ? '<span class="badge badge-activo ms-2">Activo</span>'
    : '<span class="badge badge-inactivo ms-2">Inactivo</span>';

  el.innerHTML = `
    <div class="perfil-avatar">${iniciales}</div>
    <div class="flex-grow-1">
      <div class="perfil-nombre">
        ${p.nombre_completo} ${estadoBadge}
      </div>
      <div class="perfil-meta">
        <div class="perfil-meta-item"><i class="bi bi-calendar2"></i> ${p.edad} años</div>
        <div class="perfil-meta-item"><i class="bi bi-gender-ambiguous"></i> ${capitalizarPrimera(p.genero)}</div>
        <div class="perfil-meta-item"><i class="bi bi-rulers"></i> ${p.talla_metros} m</div>
        <div class="perfil-meta-item"><i class="bi bi-clipboard2"></i> Peso inicial: ${p.peso_inicial_kg} kg</div>
        ${p.telefono ? `<div class="perfil-meta-item"><i class="bi bi-telephone"></i> ${p.telefono}</div>` : ''}
        ${p.correo ? `<div class="perfil-meta-item"><i class="bi bi-envelope"></i> ${p.correo}</div>` : ''}
      </div>
      ${p.objetivos ? `<div class="mt-2" style="font-size:.82rem;color:var(--gris-claro)"><i class="bi bi-bullseye me-1" style="color:var(--rojo-suave)"></i>${p.objetivos}</div>` : ''}
    </div>
    <div>
      <a href="patients.html" class="btn btn-secundario btn-sm">
        <i class="bi bi-arrow-left me-1"></i> Volver
      </a>
    </div>`;
}

/** Actualiza las tarjetas de últimos indicadores con la evaluación más reciente */
function renderizarIndicadoresUltimos(evaluaciones) {
  if (!evaluaciones || evaluaciones.length === 0) return;

  const ultima = evaluaciones[evaluaciones.length - 1];
  const penultima = evaluaciones.length >= 2 ? evaluaciones[evaluaciones.length - 2] : null;

  // Función para calcular y mostrar el delta entre dos evaluaciones
  const mostrarDelta = (idEl, valorActual, valorAnterior, campoNegativo = false) => {
    const el = document.getElementById(idEl);
    if (!el || valorActual == null || valorAnterior == null) return;
    const delta = valorActual - valorAnterior;
    const mejora = campoNegativo ? delta < 0 : delta > 0;
    const icono = delta > 0 ? '▲' : delta < 0 ? '▼' : '→';
    el.innerHTML = `<span style="${claseProgreso(mejora)}">${icono} ${Math.abs(delta).toFixed(1)}</span>`;
  };

  // Actualizar cada indicador de la cuadrícula
  const actualizar = (id, valor, decimales = 1) => {
    const el = document.getElementById(id);
    if (el) el.textContent = valor != null ? formatearNumero(valor, decimales) : '—';
  };

  actualizar('ind-peso', ultima.peso_kg);
  actualizar('ind-imc', ultima.imc);
  actualizar('ind-grasa', ultima.porcentaje_grasa);
  actualizar('ind-musculo', ultima.musculo_kg);
  actualizar('ind-oxigenacion', ultima.oxigenacion_porcentaje);
  actualizar('ind-fc', ultima.frecuencia_cardiaca_rpm, 0);
  actualizar('ind-ruffier', ultima.indice_ruffier);

  // Tensión arterial como fracción sistólica/diastólica
  const taEl = document.getElementById('ind-ta');
  if (taEl) {
    taEl.textContent = (ultima.tension_sistolica && ultima.tension_diastolica)
      ? `${ultima.tension_sistolica}/${ultima.tension_diastolica}`
      : '—';
  }

  // Clasificación del índice de Ruffier
  const ruffierClasif = document.getElementById('ind-ruffier-clasif');
  if (ruffierClasif && ultima.indice_ruffier != null) {
    ruffierClasif.textContent = clasificarRuffier(ultima.indice_ruffier);
    ruffierClasif.style.color = 'var(--gris-claro)';
  }

  // Mostrar deltas si hay evaluación anterior
  if (penultima) {
    mostrarDelta('ind-peso-delta', ultima.peso_kg, penultima.peso_kg, true);
    mostrarDelta('ind-imc-delta', ultima.imc, penultima.imc, true);
    mostrarDelta('ind-grasa-delta', ultima.porcentaje_grasa, penultima.porcentaje_grasa, true);
    mostrarDelta('ind-musculo-delta', ultima.musculo_kg, penultima.musculo_kg, false);
  }
}

/** Renderiza la tabla del historial de evaluaciones */
function renderizarHistorialEvaluaciones(evaluaciones, patientId) {
  const tbody = document.getElementById('tbody-evaluaciones');
  if (!tbody) return;

  if (!evaluaciones || evaluaciones.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="12">
          <div class="estado-vacio">
            <div class="estado-vacio-icono"><i class="bi bi-clipboard2"></i></div>
            <div class="estado-vacio-titulo">Sin evaluaciones aún</div>
            <div class="estado-vacio-desc">Registra la primera evaluación de este paciente</div>
            <a href="evaluations.html?patient_id=${patientId}" class="btn btn-primario">
              <i class="bi bi-plus-lg me-2"></i> Primera Evaluación
            </a>
          </div>
        </td>
      </tr>`;
    return;
  }

  // Mostrar las evaluaciones en orden más reciente primero para la tabla
  const evalOrdenadas = [...evaluaciones].reverse();

  tbody.innerHTML = evalOrdenadas.map(e => {
    const alertaBadge = e.tiene_alerta
      ? `<span class="badge badge-alerta" title="${e.detalle_alerta}">⚠ Alerta</span>`
      : `<span class="badge badge-normal">✓ OK</span>`;

    const condicionBadge = e.condicion_fisica
      ? `<span style="font-size:.8rem;color:var(--gris-claro)">${capitalizarPrimera(e.condicion_fisica)}</span>`
      : '—';

    return `
      <tr class="${e.tiene_alerta ? 'eval-fila-alerta' : ''}">
        <td style="color:var(--rojo-suave);font-weight:700">${e.numero_evaluacion}</td>
        <td style="color:var(--blanco-hueso);white-space:nowrap">${formatearFecha(e.fecha_evaluacion)}</td>
        <td>${e.peso_kg != null ? e.peso_kg + ' kg' : '—'}</td>
        <td>${e.imc != null ? formatearNumero(e.imc) : '—'}</td>
        <td>${e.porcentaje_grasa != null ? e.porcentaje_grasa + '%' : '—'}</td>
        <td>${e.musculo_kg != null ? e.musculo_kg + ' kg' : '—'}</td>
        <td>${e.frecuencia_cardiaca_rpm != null ? e.frecuencia_cardiaca_rpm + ' lpm' : '—'}</td>
        <td>${e.tension_sistolica && e.tension_diastolica ? e.tension_sistolica + '/' + e.tension_diastolica : '—'}</td>
        <td>${e.indice_ruffier != null ? formatearNumero(e.indice_ruffier) : '—'}</td>
        <td>${condicionBadge}</td>
        <td>${alertaBadge}</td>
        <td>
          <div style="display:flex;gap:4px">
            <button class="btn btn-secundario btn-sm" onclick="verDetalleEvaluacion(${JSON.stringify(e).replace(/"/g, '&quot;')})" title="Ver detalle">
              <i class="bi bi-eye"></i>
            </button>
            <button class="btn btn-peligro btn-sm" onclick="prepararEliminarEval(${e.id}, '${e.fecha_evaluacion}')" title="Eliminar">
              <i class="bi bi-trash3"></i>
            </button>
          </div>
        </td>
      </tr>`;
  }).join('');
}

/** Renderiza las 4 gráficas de evolución histórica del paciente */
function renderizarGraficasProgreso(evaluaciones) {
  if (!evaluaciones || evaluaciones.length < 2) return;

  // Etiquetas del eje X: número de evaluación
  const labels = evaluaciones.map(e => `Eval ${e.numero_evaluacion}`);

  // Configuración base de Chart.js para reutilizar
  const baseConfig = {
    responsive: true,
    plugins: {
      legend: {
        labels: { color: '#888', font: { size: 11 } }
      },
      tooltip: {
        backgroundColor: '#1A1A1A',
        borderColor: '#3D3D3D',
        borderWidth: 1,
        titleColor: '#FFF',
        bodyColor: '#AAA'
      }
    },
    scales: {
      x: { ticks: { color: '#555', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } },
      y: { ticks: { color: '#555' }, grid: { color: 'rgba(255,255,255,0.06)' } }
    }
  };

  // Gráfica 1: Peso y Músculo
  crearGrafica('grafica-peso', {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Peso (kg)',
          data: evaluaciones.map(e => e.peso_kg),
          borderColor: '#CC0000',
          backgroundColor: 'rgba(204,0,0,0.1)',
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointBackgroundColor: '#CC0000'
        },
        {
          label: 'Músculo (kg)',
          data: evaluaciones.map(e => e.musculo_kg),
          borderColor: '#00CC55',
          backgroundColor: 'rgba(0,204,85,0.05)',
          fill: false,
          tension: 0.4,
          pointRadius: 4,
          pointBackgroundColor: '#00CC55'
        }
      ]
    },
    options: baseConfig
  });

  // Gráfica 2: % Grasa y % Agua
  crearGrafica('grafica-composicion', {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: '% Grasa',
          data: evaluaciones.map(e => e.porcentaje_grasa),
          borderColor: '#FF4444',
          backgroundColor: 'rgba(255,68,68,0.1)',
          fill: true,
          tension: 0.4,
          pointRadius: 4
        },
        {
          label: '% Agua',
          data: evaluaciones.map(e => e.porcentaje_agua),
          borderColor: '#4DB8FF',
          backgroundColor: 'rgba(77,184,255,0.05)',
          fill: false,
          tension: 0.4,
          pointRadius: 4
        }
      ]
    },
    options: baseConfig
  });

  // Gráfica 3: FC y Oxigenación
  crearGrafica('grafica-cardio', {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'FC Reposo (lpm)',
          data: evaluaciones.map(e => e.frecuencia_cardiaca_rpm),
          borderColor: '#CC0000',
          backgroundColor: 'rgba(204,0,0,0.08)',
          fill: false,
          tension: 0.4,
          pointRadius: 4
        },
        {
          label: 'Oxigenación (%)',
          data: evaluaciones.map(e => e.oxigenacion_porcentaje),
          borderColor: '#00DDAA',
          backgroundColor: 'rgba(0,221,170,0.05)',
          fill: false,
          tension: 0.4,
          pointRadius: 4,
          yAxisID: 'y2'
        }
      ]
    },
    options: {
      ...baseConfig,
      scales: {
        ...baseConfig.scales,
        y2: {
          type: 'linear',
          position: 'right',
          ticks: { color: '#555' },
          grid: { display: false }
        }
      }
    }
  });

  // Gráfica 4: IMC histórico con línea de referencia
  crearGrafica('grafica-imc', {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'IMC',
          data: evaluaciones.map(e => e.imc),
          borderColor: '#FFA500',
          backgroundColor: 'rgba(255,165,0,0.1)',
          fill: true,
          tension: 0.4,
          pointRadius: 5,
          pointBackgroundColor: '#FFA500'
        },
        {
          // Línea de referencia IMC normal (25)
          label: 'Límite Normal (25)',
          data: evaluaciones.map(() => 25),
          borderColor: 'rgba(0,204,85,0.4)',
          borderDash: [6, 4],
          borderWidth: 1,
          fill: false,
          pointRadius: 0
        }
      ]
    },
    options: baseConfig
  });
}

/**
 * Crea o actualiza una gráfica Chart.js por ID de canvas.
 * Destruye la instancia anterior si ya existía.
 */
function crearGrafica(canvasId, config) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  if (graficas[canvasId]) graficas[canvasId].destroy();
  graficas[canvasId] = new Chart(canvas, config);
}

// -----------------------------------------------
// MODAL DETALLE DE EVALUACIÓN
// -----------------------------------------------

/**
 * Muestra el detalle completo de una evaluación en un modal.
 * Presenta todos los indicadores organizados por sección.
 */
function verDetalleEvaluacion(evaluacion) {
  const body = document.getElementById('detalle-eval-body');
  if (!body) return;

  const fila = (label, valor, unidad = '') => valor != null
    ? `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--gris-oscuro)">
        <span style="color:var(--gris-claro);font-size:.85rem">${label}</span>
        <span style="color:var(--blanco-puro);font-weight:600">${valor}${unidad}</span>
       </div>`
    : '';

  body.innerHTML = `
    <div style="margin-bottom:1rem">
      <div style="font-size:.75rem;color:var(--gris-claro);text-transform:uppercase;letter-spacing:1px">
        Evaluación ${evaluacion.numero_evaluacion} · ${formatearFecha(evaluacion.fecha_evaluacion)}
      </div>
    </div>

    <div style="font-family:var(--fuente-display);font-size:.85rem;color:var(--rojo-suave);text-transform:uppercase;letter-spacing:2px;margin-bottom:.5rem">
      Composición Corporal
    </div>
    ${fila('Peso', evaluacion.peso_kg, ' kg')}
    ${fila('Talla', evaluacion.talla_metros, ' m')}
    ${fila('IMC', evaluacion.imc ? formatearNumero(evaluacion.imc) : null, ` — ${evaluacion.imc ? clasificarIMC(evaluacion.imc) : ''}`)}
    ${fila('% Grasa', evaluacion.porcentaje_grasa, '%')}
    ${fila('% Agua', evaluacion.porcentaje_agua, '%')}
    ${fila('% Hueso', evaluacion.porcentaje_hueso, '%')}
    ${fila('Músculo', evaluacion.musculo_kg, ' kg')}
    ${fila('Edad metabólica', evaluacion.edad_metabolica, ' años')}
    ${fila('Condición física', evaluacion.condicion_fisica ? capitalizarPrimera(evaluacion.condicion_fisica) : null)}
    ${fila('Riesgo cardiovascular', evaluacion.riesgo_cardiovascular ? capitalizarPrimera(evaluacion.riesgo_cardiovascular) : null)}

    <div style="font-family:var(--fuente-display);font-size:.85rem;color:var(--rojo-suave);text-transform:uppercase;letter-spacing:2px;margin:1rem 0 .5rem">
      Indicadores de Salud
    </div>
    ${fila('Oxigenación', evaluacion.oxigenacion_porcentaje, '%')}
    ${fila('FC reposo', evaluacion.frecuencia_cardiaca_rpm, ' lpm')}
    ${fila('Tensión arterial', evaluacion.tension_sistolica && evaluacion.tension_diastolica ? `${evaluacion.tension_sistolica}/${evaluacion.tension_diastolica}` : null, ' mmHg')}
    ${fila('Horas de sueño', evaluacion.horas_sueno, ' h')}
    ${fila('Perímetro abdominal', evaluacion.perimetro_abdominal_cm, ' cm')}

    <div style="font-family:var(--fuente-display);font-size:.85rem;color:var(--rojo-suave);text-transform:uppercase;letter-spacing:2px;margin:1rem 0 .5rem">
      Evaluación Física
    </div>
    ${fila('Índice Ruffier', evaluacion.indice_ruffier != null ? `${formatearNumero(evaluacion.indice_ruffier)} (${clasificarRuffier(evaluacion.indice_ruffier)})` : null)}
    ${fila('Fuerza manual derecha', evaluacion.fuerza_manual_der_kg, ' kg')}
    ${fila('Fuerza manual izquierda', evaluacion.fuerza_manual_izq_kg, ' kg')}
    ${fila('Test de Wells', evaluacion.test_wells_cm, ' cm')}

    ${evaluacion.tiene_alerta ? `
      <div class="alerta alerta-error mt-3">
        <i class="bi bi-exclamation-triangle-fill"></i>
        <span>${evaluacion.detalle_alerta}</span>
      </div>` : ''}

    ${evaluacion.notas_entrenador ? `
      <div class="mt-3" style="background:var(--negro-suave);border-radius:var(--radio-md);padding:var(--espaciado-md)">
        <div style="font-size:.75rem;color:var(--gris-claro);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">
          <i class="bi bi-pencil me-1"></i> Notas del entrenador
        </div>
        <div style="font-size:.88rem;color:var(--blanco-hueso)">${evaluacion.notas_entrenador}</div>
      </div>` : ''}
  `;

  // Configurar botón de eliminar con el ID de la evaluación
  const btnEliminar = document.getElementById('btn-eliminar-eval');
  if (btnEliminar) {
    btnEliminar.onclick = () => {
      cerrarModal('modal-detalle-eval');
      prepararEliminarEval(evaluacion.id, evaluacion.fecha_evaluacion);
    };
  }

  abrirModal('modal-detalle-eval');
}

// Variable global para ID de evaluación a eliminar
let evalIdEliminar = null;

/** Prepara y abre el modal de confirmación de eliminación */
function prepararEliminarEval(evalId, fecha) {
  evalIdEliminar = evalId;
  const el = document.getElementById('fecha-eval-eliminar');
  if (el) el.textContent = formatearFecha(fecha);
  abrirModal('modal-eliminar-eval');
}

/** Ejecuta la eliminación permanente de la evaluación */
async function confirmarEliminarEval() {
  if (!evalIdEliminar) return;

  const btn = document.getElementById('btn-confirmar-eliminar-eval');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Eliminando...';

  try {
    await api.eliminarEvaluacion(evalIdEliminar);
    mostrarToast('Evaluación eliminada', 'exito');
    cerrarModal('modal-eliminar-eval');

    // Recargar la página para actualizar el historial
    setTimeout(() => window.location.reload(), 700);

  } catch (error) {
    mostrarToast(error.message || 'Error al eliminar', 'error');
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-trash3 me-1"></i> Eliminar permanentemente';
  }
}

// -----------------------------------------------
// FUNCIONES DE MODAL Y UTILIDADES
// -----------------------------------------------

/** Abre un modal por ID */
function abrirModal(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.add('activo');
    document.body.style.overflow = 'hidden';
  }
}

/** Cierra un modal por ID */
function cerrarModal(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.remove('activo');
    document.body.style.overflow = '';
  }
}

/** Cierra modales al hacer clic fuera del cuadro */
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', function (e) {
    if (e.target === this) cerrarModal(this.id);
  });
});

/** Capitaliza la primera letra */
function capitalizarPrimera(texto) {
  if (!texto) return '';
  return texto.charAt(0).toUpperCase() + texto.slice(1).replace(/_/g, ' ');
}

/** Toggle del sidebar en móvil */
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const abierto = sidebar.classList.toggle('abierto');
  overlay.style.display = abierto ? 'block' : 'none';
}