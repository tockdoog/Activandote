// frontend/js/dashboard.js
// Lógica del panel estadístico: carga de métricas, gráficas con Chart.js,
// alertas recientes, modal QR y exportación global (Excel, PDF, Impresión).

// -----------------------------------------------
// Verificación de autenticación al cargar la página
// -----------------------------------------------
(function verificarAuth() {
  if (!api.estaAutenticado()) {
    window.location.href = 'index.html';
  }
})();

// Variables globales para instancias de Chart.js
let graficaEvoluciones  = null;
let graficaTopPacientes = null;

// Variable global para la URL de red — usada por copiarURLRed()
let _urlRedLocal = '';

// Instancia global del modal QR de Bootstrap
let _modalQRInstancia = null;

// Instancia global del modal de exportación de Bootstrap
let _modalExportInstancia = null;

// Datos del reporte global cargados en memoria para la impresión
let _datosReporte = null;

// -----------------------------------------------
// INICIALIZACIÓN DEL DASHBOARD
// -----------------------------------------------
document.addEventListener('DOMContentLoaded', async function () {
  inicializarUsuario();
  mostrarFechaHoy();

  // Cargar todos los datos en paralelo para reducir tiempo de carga
  await Promise.all([
    cargarEstadisticas(),
    cargarGraficaEvoluciones(),
    cargarAlertasRecientes(),
    cargarTopPacientes()
  ]);
});

// -----------------------------------------------
// INFORMACIÓN DEL USUARIO EN SIDEBAR
// -----------------------------------------------

/**
 * Muestra el nombre del entrenador y su plan en el sidebar.
 * Genera las iniciales del nombre para el avatar circular.
 */
function inicializarUsuario() {
  const usuario = api.getUsuario();
  if (!usuario) return;

  const iniciales = usuario.nombre_completo
    .split(' ').slice(0, 2).map(n => n[0]).join('').toUpperCase();

  const avatarEl = document.getElementById('user-avatar');
  const nameEl   = document.getElementById('user-name');
  const planEl   = document.getElementById('user-plan');

  if (avatarEl) avatarEl.textContent = iniciales;
  if (nameEl)   nameEl.textContent   = usuario.nombre_completo;
  if (planEl)   planEl.textContent   = `Plan ${usuario.plan.toUpperCase()}`;

  // Saludo personalizado con el primer nombre
  const saludoEl = document.getElementById('saludo-nombre');
  if (saludoEl) saludoEl.textContent = usuario.nombre_completo.split(' ')[0];
}

/**
 * Muestra la fecha actual en el hero del dashboard.
 * Número del día en grande + texto completo en español.
 */
function mostrarFechaHoy() {
  const hoy   = new Date();
  const diaEl = document.getElementById('fecha-dia');
  const hoyEl = document.getElementById('fecha-hoy');

  if (diaEl) diaEl.textContent = hoy.getDate();

  if (hoyEl) {
    const opciones = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    hoyEl.textContent = hoy.toLocaleDateString('es-CO', opciones);
  }
}

// -----------------------------------------------
// CARGA DE ESTADÍSTICAS GLOBALES
// -----------------------------------------------

/**
 * Obtiene las métricas del backend y actualiza las tarjetas.
 * Activa el badge de alerta si hay pacientes críticos.
 */
async function cargarEstadisticas() {
  try {
    const stats = await api.obtenerEstadisticas();

    // Actualizar cada tarjeta con animación de contador ascendente
    actualizarStatConAnimacion('stat-total-pacientes',    stats.total_pacientes);
    actualizarStatConAnimacion('stat-pacientes-activos',  stats.pacientes_activos);
    actualizarStatConAnimacion('stat-total-evaluaciones', stats.total_evaluaciones);
    actualizarStatConAnimacion('stat-eval-mes',           stats.evaluaciones_este_mes);
    actualizarStatConAnimacion('stat-con-alerta',         stats.pacientes_con_alerta);

    // IMC promedio con un decimal
    const imcEl = document.getElementById('stat-imc');
    if (imcEl) {
      imcEl.textContent = stats.promedio_imc
        ? formatearNumero(stats.promedio_imc)
        : '—';
    }

    // Badge rojo si hay alertas activas
    if (stats.pacientes_con_alerta > 0) {
      const badge = document.getElementById('badge-alertas');
      if (badge) badge.style.display = 'block';
    }

  } catch (error) {
    console.error('Error cargando estadísticas:', error);
    mostrarToast('Error al cargar estadísticas del dashboard', 'error');
  }
}

/**
 * Anima el contador de una tarjeta stat desde 0 hasta el valor final.
 * Easing ease-out cúbico durante 600ms con requestAnimationFrame.
 */
function actualizarStatConAnimacion(elementId, valorFinal) {
  const el = document.getElementById(elementId);
  if (!el || valorFinal == null) return;

  const duracion = 600;
  const inicio   = performance.now();
  const valorNum = Number(valorFinal);

  function animar(ahora) {
    const transcurrido = ahora - inicio;
    const progreso     = Math.min(transcurrido / duracion, 1);
    const ease         = 1 - Math.pow(1 - progreso, 3);
    el.textContent     = Math.round(valorNum * ease);
    if (progreso < 1) requestAnimationFrame(animar);
  }

  requestAnimationFrame(animar);
}

// -----------------------------------------------
// GRÁFICA DE EVOLUCIÓN MENSUAL
// -----------------------------------------------

/**
 * Carga evaluaciones por mes (últimos 12 meses) y renderiza barras verdes.
 */
async function cargarGraficaEvoluciones() {
  try {
    const datos    = await api.obtenerEvolucion();
    const periodos = datos.datos.map(d => d.periodo);
    const totales  = datos.datos.map(d => d.total_evaluaciones);

    const canvas = document.getElementById('grafica-evoluciones');
    if (!canvas) return;

    if (graficaEvoluciones) graficaEvoluciones.destroy();

    graficaEvoluciones = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: periodos,
        datasets: [{
          label:           'Evaluaciones',
          data:            totales,
          backgroundColor: 'rgba(22, 163, 74, 0.78)',
          borderColor:     '#16A34A',
          borderWidth:     1,
          borderRadius:    5,
          borderSkipped:   false
        }]
      },
      options: {
        responsive: true,
        animation: { duration: 800, easing: 'easeOutQuart' },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#FFFFFF',
            borderColor:     '#DDE8DD',
            borderWidth:     1,
            titleColor:      '#111827',
            bodyColor:       '#374E37',
            padding:         10
          }
        },
        scales: {
          x: {
            ticks: { color: '#374E37', font: { size: 11, family: 'Inter' } },
            grid:  { color: 'rgba(0,0,0,0.04)' }
          },
          y: {
            beginAtZero: true,
            ticks: { color: '#374E37', stepSize: 1, font: { size: 11, family: 'Inter' } },
            grid: { color: 'rgba(0,0,0,0.06)' }
          }
        }
      }
    });

  } catch (error) {
    console.error('Error cargando gráfica de evoluciones:', error);
  }
}

// -----------------------------------------------
// GRÁFICA TOP 5 PACIENTES
// -----------------------------------------------

/**
 * Carga los 5 pacientes con más evaluaciones y renderiza barras horizontales.
 */
async function cargarTopPacientes() {
  try {
    const datos = await api.obtenerTopPacientes();

    const nombres      = datos.top_pacientes.map(p => p.nombre.split(' ')[0]);
    const evaluaciones = datos.top_pacientes.map(p => p.total_evaluaciones);

    const canvas = document.getElementById('grafica-top-pacientes');
    if (!canvas) return;

    if (graficaTopPacientes) graficaTopPacientes.destroy();

    const colores = [
      'rgba(22, 163, 74, 0.90)',
      'rgba(22, 163, 74, 0.72)',
      'rgba(22, 163, 74, 0.55)',
      'rgba(22, 163, 74, 0.38)',
      'rgba(22, 163, 74, 0.22)'
    ];

    graficaTopPacientes = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: nombres,
        datasets: [{
          label:           'Evaluaciones',
          data:            evaluaciones,
          backgroundColor: colores,
          borderColor:     '#16A34A',
          borderWidth:     1,
          borderRadius:    5,
          borderSkipped:   false
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        animation: { duration: 800, easing: 'easeOutQuart' },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#FFFFFF',
            borderColor:     '#DDE8DD',
            borderWidth:     1,
            titleColor:      '#111827',
            bodyColor:       '#374E37',
            padding:         10
          }
        },
        scales: {
          x: {
            beginAtZero: true,
            ticks: { color: '#374E37', stepSize: 1, font: { size: 11, family: 'Inter' } },
            grid: { color: 'rgba(0,0,0,0.06)' }
          },
          y: {
            ticks: { color: '#1F3A1F', font: { size: 12, weight: '600', family: 'Inter' } },
            grid: { display: false }
          }
        }
      }
    });

  } catch (error) {
    console.error('Error cargando top pacientes:', error);
  }
}

// -----------------------------------------------
// TABLA DE ALERTAS RECIENTES
// -----------------------------------------------

/**
 * Carga evaluaciones con alertas activas y las muestra en la tabla.
 */
async function cargarAlertasRecientes() {
  const tbody = document.getElementById('tbody-alertas');
  if (!tbody) return;

  try {
    const datos = await api.obtenerAlertasRecientes();

    if (datos.alertas.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="4">
            <div class="estado-vacio" style="padding:2rem">
              <div class="estado-vacio-icono">
                <i class="bi bi-check-circle-fill"
                   style="color:var(--verde-primario);font-size:2.5rem"></i>
              </div>
              <div class="estado-vacio-titulo">Sin alertas activas</div>
              <div class="estado-vacio-desc">
                Todos tus pacientes están dentro de rangos saludables
              </div>
            </div>
          </td>
        </tr>`;
      return;
    }

    tbody.innerHTML = datos.alertas.map(alerta => `
      <tr>
        <td>
          <a
            href="patient-detail.html?id=${alerta.patient_id}"
            style="color:#111827;text-decoration:none;font-weight:600;
                   font-size:.875rem;display:flex;align-items:center;gap:8px"
          >
            <div style="width:32px;height:32px;min-width:32px;border-radius:50%;
                        background:var(--verde-translucido);
                        border:1.5px solid var(--verde-borde);
                        display:flex;align-items:center;justify-content:center;
                        font-size:.75rem;font-weight:700;color:#15803D;
                        font-family:var(--fuente-display)">
              ${alerta.nombre_paciente.split(' ').slice(0,2).map(n=>n[0]).join('').toUpperCase()}
            </div>
            ${alerta.nombre_paciente}
          </a>
        </td>
        <td style="color:#374E37;font-size:.85rem">
          <i class="bi bi-calendar3 me-1" style="color:var(--verde-primario)"></i>
          ${formatearFecha(alerta.fecha)}
        </td>
        <td>
          <span style="color:#991B1B;font-size:.82rem;font-weight:500;
                       display:flex;align-items:flex-start;gap:5px">
            <i class="bi bi-exclamation-triangle-fill"
               style="color:var(--rojo-alerta);flex-shrink:0;margin-top:1px"></i>
            ${alerta.detalle || 'Sin detalle'}
          </span>
        </td>
        <td>
          <a href="patient-detail.html?id=${alerta.patient_id}"
             class="btn btn-secundario btn-sm">
            <i class="bi bi-eye me-1"></i> Ver
          </a>
        </td>
      </tr>
    `).join('');

  } catch (error) {
    console.error('Error cargando alertas recientes:', error);
    tbody.innerHTML = `
      <tr>
        <td colspan="4" style="text-align:center;color:#516651;padding:2rem">
          <i class="bi bi-exclamation-triangle me-2"
             style="color:var(--rojo-alerta)"></i>
          Error al cargar alertas. Intenta recargar la página.
        </td>
      </tr>`;
  }
}

// -----------------------------------------------
// MODAL QR — Acceso en red local
// -----------------------------------------------

/**
 * Abre el modal con el código QR de acceso en red local.
 */
async function abrirModalQR() {
  if (!_modalQRInstancia) {
    const elModal = document.getElementById('modal-qr');
    if (!elModal) return;
    _modalQRInstancia = new bootstrap.Modal(elModal);
  }

  const contenedorQR = document.getElementById('qr-canvas-container');
  const elUrlTexto   = document.getElementById('url-acceso-red');

  if (contenedorQR) contenedorQR.innerHTML = '';
  if (elUrlTexto)   elUrlTexto.textContent  = 'Detectando IP de red...';

  _modalQRInstancia.show();

  try {
    const info = await api.get('/dashboard/network-info');
    _urlRedLocal = info.url;

    if (elUrlTexto) elUrlTexto.textContent = _urlRedLocal;

    if (contenedorQR && typeof QRCode !== 'undefined') {
      new QRCode(contenedorQR, {
        text:         _urlRedLocal,
        width:        200,
        height:       200,
        colorDark:    '#000000',
        colorLight:   '#FFFFFF',
        correctLevel: QRCode.CorrectLevel.M
      });
    } else if (contenedorQR) {
      contenedorQR.innerHTML = `
        <div style="width:200px;height:200px;display:flex;align-items:center;
                    justify-content:center;color:var(--verde-primario);font-size:.8rem;
                    text-align:center;padding:16px;background:var(--gris-100);
                    border-radius:var(--radio-md);border:1px solid var(--gris-borde)">
          <div>
            <i class="bi bi-qr-code" style="font-size:2rem;display:block;
               margin-bottom:8px;color:var(--verde-primario)"></i>
            QR no disponible.<br>Usa la URL de arriba.
          </div>
        </div>`;
    }

  } catch (error) {
    console.error('Error obteniendo info de red:', error);
    _urlRedLocal = window.location.origin;
    if (elUrlTexto) elUrlTexto.textContent = _urlRedLocal;
  }
}

/** Copia la URL de red local al portapapeles con fallback para navegadores legacy */
async function copiarURLRed() {
  const url = _urlRedLocal || window.location.origin;
  try {
    await navigator.clipboard.writeText(url);
    mostrarToast('URL copiada al portapapeles', 'exito', 2000);
  } catch {
    const input = document.createElement('input');
    input.value          = url;
    input.style.position = 'fixed';
    input.style.opacity  = '0';
    document.body.appendChild(input);
    input.select();
    document.execCommand('copy');
    document.body.removeChild(input);
    mostrarToast('URL copiada al portapapeles', 'exito', 2000);
  }
}

// -----------------------------------------------
// EXPORTACIÓN DE REPORTE GLOBAL
// -----------------------------------------------

/**
 * Abre el modal de exportación con previsualización de los datos del reporte.
 * Carga los datos del backend y muestra un resumen antes de elegir el formato.
 */
async function exportarReporte() {
  // Inicializar instancia del modal la primera vez
  if (!_modalExportInstancia) {
    const elModal = document.getElementById('modal-exportar');
    if (!elModal) return;
    _modalExportInstancia = new bootstrap.Modal(elModal);
  }

  // Mostrar el modal con estado de carga
  _modalExportInstancia.show();
  _mostrarEstadoCargaExport(true);

  try {
    // Obtener los datos del reporte global del backend
    _datosReporte = await api.obtenerReporteGlobal();
    _mostrarEstadoCargaExport(false);
    _renderizarPreviaExport(_datosReporte);

  } catch (error) {
    console.error('Error cargando datos del reporte:', error);
    _mostrarEstadoCargaExport(false);
    _mostrarErrorExport('No se pudieron cargar los datos del reporte. Por favor, intenta de nuevo.');
  }
}

/**
 * Muestra u oculta el spinner de carga dentro del modal de exportación.
 * @param {boolean} cargando - true para mostrar spinner, false para ocultarlo
 */
function _mostrarEstadoCargaExport(cargando) {
  const spinner    = document.getElementById('export-spinner');
  const contenido  = document.getElementById('export-contenido');
  const acciones   = document.getElementById('export-acciones');

  if (spinner)   spinner.style.display   = cargando ? 'flex'  : 'none';
  if (contenido) contenido.style.display = cargando ? 'none'  : 'block';
  if (acciones)  acciones.style.display  = cargando ? 'none'  : 'flex';
}

/**
 * Muestra un mensaje de error dentro del modal de exportación.
 * @param {string} mensaje - Texto del error a mostrar
 */
function _mostrarErrorExport(mensaje) {
  const contenido = document.getElementById('export-contenido');
  if (!contenido) return;
  contenido.style.display = 'block';
  contenido.innerHTML = `
    <div style="text-align:center;padding:2rem;color:#B71C1C">
      <i class="bi bi-exclamation-triangle-fill" style="font-size:2.5rem;
         display:block;margin-bottom:1rem;color:#CC0000"></i>
      <p style="font-size:.9rem;font-weight:600">${mensaje}</p>
    </div>`;
}

/**
 * Renderiza la previsualización del reporte dentro del modal.
 * Muestra las estadísticas clave, top pacientes y alertas activas.
 * @param {Object} datos - Datos del reporte obtenidos del backend
 */
function _renderizarPreviaExport(datos) {
  const contenido = document.getElementById('export-contenido');
  if (!contenido) return;

  const r = datos.resumen;

  // Calcular porcentaje activos para la barra visual
  const pctActivos = r.total_pacientes > 0
    ? Math.round((r.pacientes_activos / r.total_pacientes) * 100)
    : 0;

  contenido.innerHTML = `
    <!-- Encabezado del reporte -->
    <div class="export-reporte-header">
      <div class="export-reporte-logo">
        <i class="bi bi-clipboard2-pulse-fill"></i>
      </div>
      <div>
        <div class="export-reporte-titulo">Reporte Global FitPro</div>
        <div class="export-reporte-meta">
          Entrenador: <strong>${datos.entrenador}</strong>
          &nbsp;·&nbsp; Generado: <strong>${datos.generado_en}</strong>
        </div>
      </div>
    </div>

    <!-- KPIs en grilla 3x2 -->
    <div class="export-kpi-grid">
      ${_kpiCard('bi-people-fill', r.total_pacientes, 'Total Pacientes')}
      ${_kpiCard('bi-person-check-fill', r.pacientes_activos, 'Activos')}
      ${_kpiCard('bi-clipboard2-pulse-fill', r.total_evaluaciones, 'Evaluaciones')}
      ${_kpiCard('bi-calendar3', r.evaluaciones_mes, 'Este Mes')}
      ${_kpiCard('bi-exclamation-triangle-fill', r.pacientes_con_alerta, 'Alertas', r.pacientes_con_alerta > 0)}
      ${_kpiCard('bi-calculator-fill', r.promedio_imc || '—', 'IMC Prom.')}
    </div>

    <!-- Barra de progreso activos -->
    <div class="export-seccion-titulo">
      <i class="bi bi-bar-chart-fill"></i> Pacientes Activos
    </div>
    <div style="margin-bottom:1rem">
      <div style="display:flex;justify-content:space-between;
                  font-size:.78rem;color:#424242;margin-bottom:4px">
        <span>${r.pacientes_activos} activos de ${r.total_pacientes} totales</span>
        <strong style="color:#CC0000">${pctActivos}%</strong>
      </div>
      <div style="height:8px;background:#F5F5F5;border-radius:100px;overflow:hidden">
        <div style="height:100%;width:${pctActivos}%;
                    background:linear-gradient(90deg,#CC0000,#E53935);
                    border-radius:100px;transition:width 0.8s ease"></div>
      </div>
    </div>

    <!-- Top 5 pacientes -->
    ${datos.top_pacientes.length > 0 ? `
      <div class="export-seccion-titulo">
        <i class="bi bi-trophy-fill"></i> Top 5 Pacientes
      </div>
      <div class="export-top-lista">
        ${datos.top_pacientes.map((p, i) => `
          <div class="export-top-item">
            <div class="export-top-rank">${i + 1}</div>
            <div class="export-top-nombre">${p.nombre}</div>
            <div class="export-top-total">${p.total} eval.</div>
          </div>
        `).join('')}
      </div>
    ` : ''}

    <!-- Alertas activas (si las hay) -->
    ${datos.alertas.length > 0 ? `
      <div class="export-seccion-titulo" style="color:#CC0000">
        <i class="bi bi-exclamation-triangle-fill"></i>
        ${datos.alertas.length} Alerta(s) Activa(s)
      </div>
      <div class="export-alertas-lista">
        ${datos.alertas.slice(0, 4).map(a => `
          <div class="export-alerta-item">
            <div class="export-alerta-nombre">${a.nombre}</div>
            <div class="export-alerta-detalle">${a.detalle}</div>
          </div>
        `).join('')}
        ${datos.alertas.length > 4 ? `
          <div style="text-align:center;font-size:.75rem;color:#757575;
                      padding:6px;font-style:italic">
            + ${datos.alertas.length - 4} alerta(s) más en el reporte completo
          </div>
        ` : ''}
      </div>
    ` : `
      <div style="background:#E8F5E9;border:1px solid #A5D6A7;border-radius:8px;
                  padding:10px 14px;font-size:.82rem;color:#2E7D32;
                  display:flex;align-items:center;gap:8px">
        <i class="bi bi-check-circle-fill"></i>
        Sin alertas activas — todos los pacientes en rangos saludables
      </div>
    `}

    <!-- Nota sobre contenido del reporte -->
    <div style="margin-top:1rem;padding:10px 14px;
                background:#FFF3E0;border-radius:8px;
                border-left:3px solid #FB8C00;
                font-size:.75rem;color:#424242;line-height:1.5">
      <i class="bi bi-info-circle-fill" style="color:#FB8C00"></i>
      El reporte incluye: resumen estadístico, listado completo de
      <strong>${datos.pacientes.length} paciente(s)</strong>,
      evolución mensual (${datos.evolucion.length} meses) y alertas activas.
    </div>
  `;
}

/**
 * Genera el HTML de una tarjeta KPI individual para el modal de exportación.
 * @param {string} icono      - Clase del icono Bootstrap Icons
 * @param {*}      valor      - Valor numérico o texto del KPI
 * @param {string} etiqueta   - Etiqueta descriptiva
 * @param {boolean} esAlerta  - Si es true, colorea en rojo de alerta
 */
function _kpiCard(icono, valor, etiqueta, esAlerta = false) {
  const colorValor = esAlerta ? '#CC0000' : '#1A1A1A';
  const bgColor    = esAlerta ? '#FFEBEE' : '#FAFAFA';
  const borderClr  = esAlerta ? '#FFCDD2' : '#EEEEEE';

  return `
    <div style="background:${bgColor};border:1px solid ${borderClr};
                border-radius:8px;padding:12px;text-align:center">
      <i class="bi ${icono}" style="color:#CC0000;font-size:1.1rem;
         display:block;margin-bottom:4px"></i>
      <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.6rem;
                  font-weight:800;color:${colorValor};line-height:1">
        ${valor}
      </div>
      <div style="font-size:.65rem;color:#757575;text-transform:uppercase;
                  letter-spacing:1px;margin-top:2px;font-weight:600">
        ${etiqueta}
      </div>
    </div>
  `;
}

// ─────────────────────────────────────────────────────────────────────────────
// ACCIONES DE EXPORTACIÓN DESDE EL MODAL
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Descarga el reporte global en formato Excel (.xlsx).
 * Desactiva el botón durante la descarga para evitar doble clic.
 */
async function descargarExcelGlobal() {
  const btn = document.getElementById('btn-descargar-excel');

  try {
    // Deshabilitar botón y mostrar estado de carga
    if (btn) {
      btn.disabled     = true;
      btn.innerHTML    = '<span class="spinner-sm"></span> Generando...';
    }

    await api.exportarReporteGlobalExcel();
    mostrarToast('Reporte Excel descargado correctamente', 'exito', 3500);

    // Cerrar el modal después de la descarga exitosa
    if (_modalExportInstancia) _modalExportInstancia.hide();

  } catch (error) {
    console.error('Error descargando Excel:', error);
    mostrarToast('Error al generar el archivo Excel. Intenta de nuevo.', 'error');
  } finally {
    // Restaurar el botón siempre, éxito o fallo
    if (btn) {
      btn.disabled  = false;
      btn.innerHTML = '<i class="bi bi-file-earmark-excel-fill me-2"></i>Descargar Excel';
    }
  }
}

/**
 * Descarga el reporte global en formato PDF.
 * Desactiva el botón durante la generación del PDF.
 */
async function descargarPDFGlobal() {
  const btn = document.getElementById('btn-descargar-pdf');

  try {
    if (btn) {
      btn.disabled  = true;
      btn.innerHTML = '<span class="spinner-sm"></span> Generando PDF...';
    }

    await api.exportarReporteGlobalPDF();
    mostrarToast('Reporte PDF descargado correctamente', 'exito', 3500);

    if (_modalExportInstancia) _modalExportInstancia.hide();

  } catch (error) {
    console.error('Error descargando PDF:', error);
    mostrarToast('Error al generar el PDF. Intenta de nuevo.', 'error');
  } finally {
    if (btn) {
      btn.disabled  = false;
      btn.innerHTML = '<i class="bi bi-file-earmark-pdf-fill me-2"></i>Descargar PDF';
    }
  }
}

/**
 * Abre el diálogo de impresión con un diseño deportivo optimizado.
 * Construye dinámicamente el contenido HTML de la ventana de impresión
 * usando los datos ya cargados en _datosReporte.
 */
function imprimirReporteGlobal() {
  // Verificar que existan datos del reporte
  if (!_datosReporte) {
    mostrarToast('Cargando datos, espera un momento...', 'info', 2000);
    return;
  }

  const datos = _datosReporte;
  const r     = datos.resumen;

  // ─── Construir tabla de pacientes para impresión ────────────────────────
  const filasTabla = datos.pacientes.map((pac, i) => {
    const bg = pac.tiene_alerta
      ? '#FFCDD2'
      : (i % 2 === 0 ? '#FFFFFF' : '#F5F5F5');

    return `
      <tr style="background:${bg}">
        <td>${pac.nombre}</td>
        <td style="text-align:center">${pac.edad}</td>
        <td style="text-align:center">${(pac.estado || '—').charAt(0).toUpperCase() + (pac.estado || '').slice(1)}</td>
        <td style="text-align:center">${pac.ultima_evaluacion || 'Sin eval.'}</td>
        <td style="text-align:center">${pac.peso_actual_kg ?? '—'}</td>
        <td style="text-align:center">${pac.imc ?? '—'}</td>
        <td style="text-align:center">${pac.porcentaje_grasa ?? '—'}</td>
        <td style="text-align:center;font-weight:700">${pac.total_evaluaciones}</td>
      </tr>`;
  }).join('');

  // ─── Construir tabla de alertas para impresión ──────────────────────────
  const filasAlertas = datos.alertas.length > 0
    ? datos.alertas.map(a => `
        <tr>
          <td style="font-weight:700">${a.nombre}</td>
          <td style="text-align:center">${a.fecha}</td>
          <td style="color:#B71C1C">${a.detalle}</td>
        </tr>`
      ).join('')
    : `<tr><td colspan="3" style="text-align:center;color:#2E7D32;
          font-style:italic;padding:12px">
          ✅ Sin alertas activas — Todos los pacientes en rangos saludables
       </td></tr>`;

  // ─── Construir tabla de evolución mensual ──────────────────────────────
  const maxEval = Math.max(...datos.evolucion.map(m => m.total), 1);
  const filasEvolucion = datos.evolucion.map((m, i) => {
    const barra = Math.round((m.total / maxEval) * 20);
    return `
      <tr style="background:${i % 2 === 0 ? '#fff' : '#f5f5f5'}">
        <td>${m.periodo}</td>
        <td style="text-align:center;font-weight:700">${m.total}</td>
        <td style="color:#CC0000;letter-spacing:-1px">${'█'.repeat(barra)}</td>
      </tr>`;
  }).join('');

  // ─── HTML completo de la ventana de impresión ───────────────────────────
  const htmlImpresion = `
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="UTF-8">
      <title>FitPro — Reporte Global ${datos.generado_en}</title>
      <style>
        /* ─── Reset e impresión ─────────────────────── */
        * { box-sizing: border-box; margin: 0; padding: 0; }

        @page {
          size: A4;
          margin: 1.2cm 1.5cm;
        }

        body {
          font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
          font-size: 9pt;
          color: #1A1A1A;
          background: #fff;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
        }

        /* ─── Portada / encabezado ───────────────────── */
        .cabecera {
          background: #CC0000;
          color: #fff;
          padding: 14px 18px 12px;
          margin-bottom: 0;
          page-break-after: avoid;
        }

        .cabecera-logo {
          font-size: 26pt;
          font-weight: 900;
          letter-spacing: 3px;
          line-height: 1;
          margin-bottom: 2px;
        }

        .cabecera-logo span { color: rgba(255,255,255,0.6); }

        .cabecera-subtitulo {
          font-size: 12pt;
          font-weight: 700;
          letter-spacing: 1px;
          text-transform: uppercase;
          color: rgba(255,255,255,0.9);
        }

        .cabecera-meta {
          margin-top: 6px;
          font-size: 8pt;
          color: rgba(255,255,255,0.75);
        }

        /* Banda negra bajo la cabecera */
        .banda-negra {
          background: #1A1A1A;
          color: #fff;
          padding: 5px 18px;
          font-size: 7.5pt;
          display: flex;
          justify-content: space-between;
          margin-bottom: 14px;
        }

        /* ─── KPI Cards ─────────────────────────────── */
        .kpi-grid {
          display: grid;
          grid-template-columns: repeat(6, 1fr);
          gap: 6px;
          margin-bottom: 14px;
          page-break-inside: avoid;
        }

        .kpi-card {
          background: #FFF5F5;
          border: 1px solid #FFCDD2;
          border-radius: 6px;
          padding: 8px 6px;
          text-align: center;
          page-break-inside: avoid;
        }

        .kpi-num {
          font-size: 20pt;
          font-weight: 900;
          color: #CC0000;
          line-height: 1;
          margin-bottom: 2px;
        }

        .kpi-label {
          font-size: 6.5pt;
          color: #757575;
          text-transform: uppercase;
          letter-spacing: 0.8px;
          font-weight: 700;
        }

        .kpi-card.alerta { background: #FFCDD2; border-color: #CC0000; }
        .kpi-card.alerta .kpi-num { color: #B71C1C; }

        /* ─── Encabezados de sección ─────────────────── */
        .seccion-titulo {
          background: #1A1A1A;
          color: #fff;
          padding: 6px 12px;
          font-size: 8.5pt;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 1.5px;
          margin-bottom: 4px;
          page-break-after: avoid;
        }

        .seccion-titulo.rojo { background: #CC0000; }

        /* ─── Tablas ─────────────────────────────────── */
        table {
          width: 100%;
          border-collapse: collapse;
          margin-bottom: 14px;
          font-size: 8pt;
        }

        thead tr {
          background: #CC0000;
          color: #fff;
        }

        thead th {
          padding: 6px 8px;
          font-weight: 700;
          font-size: 7.5pt;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        tbody td {
          padding: 5px 8px;
          border-bottom: 1px solid #EEEEEE;
          vertical-align: middle;
        }

        tbody tr:hover { background: #FFF5F5; }

        /* ─── Top 5 ─────────────────────────────────── */
        .top-lista {
          display: grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 6px;
          margin-bottom: 14px;
          page-break-inside: avoid;
        }

        .top-item {
          border: 1px solid #EEEEEE;
          border-radius: 6px;
          padding: 8px 6px;
          text-align: center;
          background: #FAFAFA;
        }

        .top-rank {
          font-size: 14pt;
          font-weight: 900;
          color: #CC0000;
          line-height: 1;
        }

        .top-nombre {
          font-size: 7.5pt;
          font-weight: 600;
          color: #1A1A1A;
          margin: 3px 0 2px;
          word-break: break-word;
        }

        .top-total {
          font-size: 7pt;
          color: #757575;
        }

        /* ─── Pie de página ──────────────────────────── */
        .pie-pagina {
          margin-top: 16px;
          border-top: 1.5px solid #CC0000;
          padding-top: 6px;
          display: flex;
          justify-content: space-between;
          font-size: 7pt;
          color: #757575;
        }

        /* ─── Saltos de página ───────────────────────── */
        .salto-pagina { page-break-before: always; }

        @media print {
          .no-imprimir { display: none !important; }
        }
      </style>
    </head>
    <body>

      <!-- ── CABECERA PRINCIPAL ── -->
      <div class="cabecera">
        <div style="display:flex;justify-content:space-between;align-items:flex-end">
          <div>
            <div class="cabecera-logo">FIT<span>PRO</span></div>
            <div class="cabecera-subtitulo">Reporte Global de Rendimiento</div>
          </div>
          <div style="text-align:right">
            <div style="font-size:9pt;color:rgba(255,255,255,0.85)">
              Entrenador: <strong>${datos.entrenador}</strong>
            </div>
            <div style="font-size:8pt;color:rgba(255,255,255,0.7);margin-top:2px">
              Generado: ${datos.generado_en}
            </div>
          </div>
        </div>
      </div>

      <!-- Banda negra con resumen rápido -->
      <div class="banda-negra">
        <span>📊 ${r.total_pacientes} pacientes &nbsp;·&nbsp;
              ${r.total_evaluaciones} evaluaciones totales &nbsp;·&nbsp;
              ${r.evaluaciones_mes} eval. este mes</span>
        <span>IMC Promedio: ${r.promedio_imc || '—'} &nbsp;·&nbsp;
              Alertas activas: ${r.pacientes_con_alerta}</span>
      </div>

      <!-- ── KPI GRID ── -->
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-num">${r.total_pacientes}</div>
          <div class="kpi-label">Total<br>Pacientes</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-num">${r.pacientes_activos}</div>
          <div class="kpi-label">Pacientes<br>Activos</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-num">${r.total_evaluaciones}</div>
          <div class="kpi-label">Total<br>Evaluaciones</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-num">${r.evaluaciones_mes}</div>
          <div class="kpi-label">Eval.<br>Este Mes</div>
        </div>
        <div class="kpi-card ${r.pacientes_con_alerta > 0 ? 'alerta' : ''}">
          <div class="kpi-num">${r.pacientes_con_alerta}</div>
          <div class="kpi-label">Con<br>Alerta</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-num">${r.promedio_imc || '—'}</div>
          <div class="kpi-label">IMC<br>Promedio</div>
        </div>
      </div>

      <!-- ── TOP 5 PACIENTES ── -->
      ${datos.top_pacientes.length > 0 ? `
        <div class="seccion-titulo">🏆 Top 5 Pacientes — Más Evaluaciones</div>
        <div class="top-lista">
          ${datos.top_pacientes.map((p, i) => `
            <div class="top-item">
              <div class="top-rank">${i + 1}</div>
              <div class="top-nombre">${p.nombre}</div>
              <div class="top-total">${p.total} eval.</div>
            </div>
          `).join('')}
        </div>
      ` : ''}

      <!-- ── ALERTAS ACTIVAS ── -->
      <div class="seccion-titulo rojo">
        ⚠ Alertas Activas${datos.alertas.length > 0 ? ' — ' + datos.alertas.length + ' paciente(s)' : ''}
      </div>
      <table>
        <thead>
          <tr>
            <th>Paciente</th>
            <th style="width:100px;text-align:center">Fecha</th>
            <th>Detalle de la Alerta</th>
          </tr>
        </thead>
        <tbody>${filasAlertas}</tbody>
      </table>

      <!-- ── TABLA DE PACIENTES (nueva página) ── -->
      <div class="salto-pagina"></div>
      <div class="cabecera" style="margin-bottom:0">
        <div class="cabecera-subtitulo">
          Listado Completo de Pacientes — ${datos.pacientes.length} registros
        </div>
        <div class="cabecera-meta">
          Entrenador: ${datos.entrenador} &nbsp;·&nbsp; ${datos.generado_en}
        </div>
      </div>
      <div class="banda-negra">
        <span>★ Filas en rojo indican pacientes con alertas activas</span>
        <span>FitPro Sistema Deportivo</span>
      </div>

      <table>
        <thead>
          <tr>
            <th>Nombre Completo</th>
            <th style="text-align:center">Edad</th>
            <th style="text-align:center">Estado</th>
            <th style="text-align:center">Ú. Evaluación</th>
            <th style="text-align:center">Peso (kg)</th>
            <th style="text-align:center">IMC</th>
            <th style="text-align:center">% Grasa</th>
            <th style="text-align:center">Evals.</th>
          </tr>
        </thead>
        <tbody>${filasTabla}</tbody>
      </table>

      <!-- ── EVOLUCIÓN MENSUAL ── -->
      <div class="seccion-titulo">📅 Evolución Mensual — Últimos 12 Meses</div>
      <table>
        <thead>
          <tr>
            <th style="width:100px">Período</th>
            <th style="width:80px;text-align:center">Evaluaciones</th>
            <th>Actividad</th>
          </tr>
        </thead>
        <tbody>${filasEvolucion}</tbody>
      </table>

      <!-- ── PIE DE PÁGINA ── -->
      <div class="pie-pagina">
        <span>FitPro — Sistema de Gestión Deportiva Profesional</span>
        <span>Entrenador: ${datos.entrenador} &nbsp;·&nbsp; ${datos.generado_en}</span>
        <span>Documento confidencial</span>
      </div>

    </body>
    </html>
  `;

  // Abrir ventana de impresión con el contenido generado
  const ventana = window.open('', '_blank', 'width=900,height=700');
  if (!ventana) {
    mostrarToast('Habilita las ventanas emergentes para poder imprimir', 'advertencia', 5000);
    return;
  }

  ventana.document.write(htmlImpresion);
  ventana.document.close();

  // Esperar a que los estilos carguen antes de abrir el diálogo
  ventana.onload = function () {
    setTimeout(() => {
      ventana.focus();
      ventana.print();
    }, 400);
  };

  // Cerrar el modal de exportación después de abrir la ventana de impresión
  if (_modalExportInstancia) _modalExportInstancia.hide();
}

// -----------------------------------------------
// NAVEGACIÓN Y UTILIDADES
// -----------------------------------------------

/** Desplaza la vista hasta la sección de alertas */
function scrollToAlertas() {
  const el = document.getElementById('seccion-alertas');
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/** Abre o cierra el sidebar en dispositivos móviles */
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const abierto = sidebar.classList.toggle('abierto');
  overlay.style.display = abierto ? 'block' : 'none';
}