// frontend/js/dashboard.js
// Lógica del panel estadístico: carga de métricas, gráficas con Chart.js,
// alertas recientes y modal QR para acceso en red local.

// -----------------------------------------------
// Verificación de autenticación al cargar la página.
// Si no hay token en localStorage, redirigir al login.
// -----------------------------------------------
(function verificarAuth() {
  if (!api.estaAutenticado()) {
    window.location.href = 'index.html';
  }
})();

// Variables globales para instancias de Chart.js — evitan el error
// "Canvas already in use" al recargar datos sin recargar la página
let graficaEvoluciones  = null;
let graficaTopPacientes = null;

// Variable global para la URL de red — usada por copiarURLRed()
let _urlRedLocal = '';

// Instancia global del modal QR de Bootstrap — reutilizada en cada apertura
let _modalQRInstancia = null;

// -----------------------------------------------
// INICIALIZACIÓN DEL DASHBOARD AL CARGAR LA PÁGINA
// -----------------------------------------------
document.addEventListener('DOMContentLoaded', async function () {
  // Mostrar datos del entrenador autenticado en el sidebar
  inicializarUsuario();

  // Mostrar fecha de hoy en el bloque hero del dashboard
  mostrarFechaHoy();

  // Cargar todos los datos en paralelo para reducir el tiempo total de carga
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

  // Extraer las dos primeras iniciales del nombre completo para el avatar
  const iniciales = usuario.nombre_completo
    .split(' ')
    .slice(0, 2)
    .map(n => n[0])
    .join('')
    .toUpperCase();

  const avatarEl = document.getElementById('user-avatar');
  const nameEl   = document.getElementById('user-name');
  const planEl   = document.getElementById('user-plan');

  if (avatarEl) avatarEl.textContent = iniciales;
  if (nameEl)   nameEl.textContent   = usuario.nombre_completo;
  if (planEl)   planEl.textContent   = `Plan ${usuario.plan.toUpperCase()}`;

  // Saludo personalizado con el primer nombre en el hero del dashboard
  const saludoEl = document.getElementById('saludo-nombre');
  if (saludoEl) {
    saludoEl.textContent = usuario.nombre_completo.split(' ')[0];
  }
}

/**
 * Muestra la fecha actual en el bloque hero del dashboard.
 * Formato: número del día grande + texto completo en español.
 */
function mostrarFechaHoy() {
  const hoy   = new Date();
  const diaEl = document.getElementById('fecha-dia');
  const hoyEl = document.getElementById('fecha-hoy');

  // Número del día en fuente grande (elemento decorativo)
  if (diaEl) diaEl.textContent = hoy.getDate();

  // Texto completo: "martes, 15 de octubre de 2024"
  if (hoyEl) {
    const opciones = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    hoyEl.textContent = hoy.toLocaleDateString('es-CO', opciones);
  }
}

// -----------------------------------------------
// CARGA DE ESTADÍSTICAS GLOBALES
// -----------------------------------------------

/**
 * Obtiene las métricas del backend y actualiza las tarjetas del dashboard.
 * Activa el badge rojo de alerta en el topbar si hay pacientes críticos.
 */
async function cargarEstadisticas() {
  try {
    const stats = await api.obtenerEstadisticas();

    // Actualizar cada tarjeta stat con animación de contador ascendente
    actualizarStatConAnimacion('stat-total-pacientes',    stats.total_pacientes);
    actualizarStatConAnimacion('stat-pacientes-activos',  stats.pacientes_activos);
    actualizarStatConAnimacion('stat-total-evaluaciones', stats.total_evaluaciones);
    actualizarStatConAnimacion('stat-eval-mes',           stats.evaluaciones_este_mes);
    actualizarStatConAnimacion('stat-con-alerta',         stats.pacientes_con_alerta);

    // IMC promedio con un decimal — mostrar guión si no hay datos
    const imcEl = document.getElementById('stat-imc');
    if (imcEl) {
      imcEl.textContent = stats.promedio_imc
        ? formatearNumero(stats.promedio_imc)
        : '—';
    }

    // Mostrar badge rojo en el botón de alertas del topbar si hay alertas activas
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
 * Usa requestAnimationFrame con easing ease-out cúbico durante 600ms.
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
    // Easing ease-out cúbico: rápido al inicio, suave al final
    const ease         = 1 - Math.pow(1 - progreso, 3);
    el.textContent     = Math.round(valorNum * ease);

    if (progreso < 1) requestAnimationFrame(animar);
  }

  requestAnimationFrame(animar);
}

// -----------------------------------------------
// GRÁFICA DE EVOLUCIÓN MENSUAL (Chart.js — Barras verticales)
// -----------------------------------------------

/**
 * Carga evaluaciones agrupadas por mes (últimos 12 meses) y renderiza
 * una gráfica de barras verticales con paleta rojo/negro.
 */
async function cargarGraficaEvoluciones() {
  try {
    const datos    = await api.obtenerEvolucion();
    const periodos = datos.datos.map(d => d.periodo);
    const totales  = datos.datos.map(d => d.total_evaluaciones);

    const canvas = document.getElementById('grafica-evoluciones');
    if (!canvas) return;

    // Destruir instancia anterior para evitar el error "Canvas already in use"
    if (graficaEvoluciones) graficaEvoluciones.destroy();

    graficaEvoluciones = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: periodos,
        datasets: [{
          label: 'Evaluaciones',
          data: totales,
          backgroundColor: 'rgba(204, 0, 0, 0.75)',
          borderColor:     '#CC0000',
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
            backgroundColor: '#1A1A1A',
            borderColor:     '#CC0000',
            borderWidth:     1,
            titleColor:      '#FFFFFF',
            bodyColor:       '#CCCCCC',
            padding:         10
          }
        },
        scales: {
          x: {
            ticks: { color: '#999999', font: { size: 11, family: 'Inter' } },
            grid:  { color: 'rgba(255,255,255,0.05)' }
          },
          y: {
            beginAtZero: true,
            ticks: {
              color: '#999999',
              stepSize: 1,
              font: { size: 11, family: 'Inter' }
            },
            grid: { color: 'rgba(255,255,255,0.05)' }
          }
        }
      }
    });

  } catch (error) {
    console.error('Error cargando gráfica de evoluciones:', error);
  }
}

// -----------------------------------------------
// GRÁFICA TOP 5 PACIENTES (Chart.js — Barras horizontales)
// -----------------------------------------------

/**
 * Carga los 5 pacientes con más evaluaciones y los muestra en
 * una gráfica de barras horizontal con opacidad decreciente.
 */
async function cargarTopPacientes() {
  try {
    const datos = await api.obtenerTopPacientes();

    // Usar solo el primer nombre para que quepan en el eje Y de la gráfica
    const nombres      = datos.top_pacientes.map(p => p.nombre.split(' ')[0]);
    const evaluaciones = datos.top_pacientes.map(p => p.total_evaluaciones);

    const canvas = document.getElementById('grafica-top-pacientes');
    if (!canvas) return;

    if (graficaTopPacientes) graficaTopPacientes.destroy();

    // Paleta roja con opacidad decreciente para efecto de ranking visual
    const colores = [
      'rgba(204, 0, 0, 0.90)',
      'rgba(204, 0, 0, 0.70)',
      'rgba(204, 0, 0, 0.52)',
      'rgba(204, 0, 0, 0.35)',
      'rgba(204, 0, 0, 0.20)'
    ];

    graficaTopPacientes = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: nombres,
        datasets: [{
          label: 'Evaluaciones',
          data: evaluaciones,
          backgroundColor: colores,
          borderColor:     '#CC0000',
          borderWidth:     1,
          borderRadius:    5,
          borderSkipped:   false
        }]
      },
      options: {
        indexAxis: 'y',  // Barras horizontales
        responsive: true,
        animation: { duration: 800, easing: 'easeOutQuart' },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1A1A1A',
            borderColor:     '#CC0000',
            borderWidth:     1,
            titleColor:      '#FFFFFF',
            bodyColor:       '#CCCCCC',
            padding:         10
          }
        },
        scales: {
          x: {
            beginAtZero: true,
            ticks: {
              color: '#999999',
              stepSize: 1,
              font: { size: 11, family: 'Inter' }
            },
            grid: { color: 'rgba(255,255,255,0.05)' }
          },
          y: {
            ticks: {
              color: '#FFFFFF',
              font: { size: 12, weight: '600', family: 'Inter' }
            },
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
 * Carga las evaluaciones con alertas activas y las muestra en la tabla.
 * Cada fila incluye enlace directo al detalle del paciente.
 */
async function cargarAlertasRecientes() {
  const tbody = document.getElementById('tbody-alertas');
  if (!tbody) return;

  try {
    const datos = await api.obtenerAlertasRecientes();

    if (datos.alertas.length === 0) {
      // Estado vacío positivo: todos los pacientes están dentro de rangos
      tbody.innerHTML = `
        <tr>
          <td colspan="4">
            <div class="estado-vacio" style="padding:2rem">
              <div class="estado-vacio-icono">
                <i class="bi bi-check-circle-fill" style="color:#00CC55;font-size:2.5rem"></i>
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

    // Generar una fila por cada alerta con enlace al detalle del paciente
    tbody.innerHTML = datos.alertas.map(alerta => `
      <tr>
        <td>
          <a href="patient-detail.html?id=${alerta.patient_id}"
             style="color:var(--blanco-puro);text-decoration:none;font-weight:600;
                    font-size:.875rem;display:flex;align-items:center;gap:8px">
            <div style="width:32px;height:32px;min-width:32px;border-radius:50%;
                        background:rgba(204,0,0,0.15);border:1.5px solid rgba(204,0,0,0.3);
                        display:flex;align-items:center;justify-content:center;
                        font-size:.75rem;font-weight:700;color:#FF4444;
                        font-family:var(--fuente-display)">
              ${alerta.nombre_paciente.split(' ').slice(0,2).map(n=>n[0]).join('').toUpperCase()}
            </div>
            ${alerta.nombre_paciente}
          </a>
        </td>
        <td style="color:#999999;font-size:.85rem">
          <i class="bi bi-calendar3 me-1" style="color:#CC0000"></i>
          ${formatearFecha(alerta.fecha)}
        </td>
        <td>
          <span style="color:#FF9999;font-size:.82rem;font-weight:500;
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
        <td colspan="4" style="text-align:center;color:#999999;padding:2rem">
          <i class="bi bi-exclamation-triangle me-2" style="color:var(--rojo-alerta)"></i>
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
 *
 * Flujo:
 * 1. Consulta GET /api/v1/dashboard/network-info al backend.
 *    El backend usa un socket UDP ficticio para detectar su propia IP de red
 *    real (192.168.x.x), que es la que deben usar los otros dispositivos.
 * 2. Construye la URL: http://<IP-del-servidor>
 * 3. Genera el QR con la librería QRCode.js apuntando a esa URL.
 * 4. Muestra la URL en texto con botón de copiar.
 *
 * Por qué no usar window.location.hostname:
 *   En la PC del servidor, window.location.hostname es "localhost", que no
 *   es accesible desde otros dispositivos. Necesitamos la IP de red real.
 */
async function abrirModalQR() {
  // Inicializar la instancia del modal de Bootstrap solo la primera vez
  if (!_modalQRInstancia) {
    const elModal = document.getElementById('modal-qr');
    if (!elModal) return;
    _modalQRInstancia = new bootstrap.Modal(elModal);
  }

  // Limpiar el contenedor del QR anterior antes de regenerar
  const contenedorQR = document.getElementById('qr-canvas-container');
  const elUrlTexto   = document.getElementById('url-acceso-red');

  if (contenedorQR) contenedorQR.innerHTML = '';
  if (elUrlTexto)   elUrlTexto.textContent  = 'Detectando IP de red...';

  // Mostrar el modal inmediatamente con estado de carga
  _modalQRInstancia.show();

  try {
    // Consultar al backend la IP real del servidor en la red local
    const info = await api.get('/dashboard/network-info');

    // Guardar en variable global para que copiarURLRed() pueda usarla
    _urlRedLocal = info.url;

    // Actualizar el texto de la URL en el modal
    if (elUrlTexto) elUrlTexto.textContent = _urlRedLocal;

    // Generar el código QR con QRCode.js apuntando a la URL de red local.
    // errorCorrectionLevel: 'M' (15% de corrección) — buen equilibrio entre
    // densidad del QR y tolerancia a daños en la imagen impresa o pantalla.
    if (contenedorQR && typeof QRCode !== 'undefined') {
      new QRCode(contenedorQR, {
        text:               _urlRedLocal,
        width:              200,
        height:             200,
        colorDark:          '#000000',  // Módulos oscuros en negro para máximo contraste
        colorLight:         '#FFFFFF',  // Fondo blanco requerido por escáneres de celular
        correctLevel:       QRCode.CorrectLevel.M
      });
    } else if (contenedorQR) {
      // QRCode.js no cargó — mostrar URL como texto de respaldo
      contenedorQR.innerHTML = `
        <div style="width:200px;height:200px;display:flex;align-items:center;
                    justify-content:center;color:#CC0000;font-size:.8rem;
                    text-align:center;padding:16px;background:#1A1A1A;
                    border-radius:8px;border:1px solid #3D3D3D">
          <div>
            <i class="bi bi-qr-code" style="font-size:2rem;display:block;margin-bottom:8px"></i>
            QR no disponible.<br>Usa la URL de arriba.
          </div>
        </div>`;
    }

  } catch (error) {
    // Error de red o servidor caído: mostrar URL de localhost como respaldo
    console.error('Error obteniendo info de red:', error);
    _urlRedLocal = window.location.origin;

    if (elUrlTexto) elUrlTexto.textContent = _urlRedLocal;

    if (contenedorQR) {
      contenedorQR.innerHTML = `
        <div style="width:200px;height:200px;display:flex;align-items:center;
                    justify-content:center;color:#CC0000;font-size:.8rem;
                    text-align:center;padding:16px;background:#1A1A1A;
                    border-radius:8px;border:1px solid #CC0000">
          <div>
            <i class="bi bi-wifi-off" style="font-size:2rem;display:block;margin-bottom:8px"></i>
            No se pudo detectar<br>la IP de red.<br>
            <span style="color:#999;font-size:.75rem">Ejecuta iniciar-fitpro.bat</span>
          </div>
        </div>`;
    }
  }
}

/**
 * Copia la URL de red local al portapapeles.
 * Usa la Clipboard API moderna con fallback a execCommand para navegadores legacy.
 */
async function copiarURLRed() {
  const url = _urlRedLocal || window.location.origin;

  try {
    // Clipboard API — disponible en navegadores modernos con HTTPS o localhost
    await navigator.clipboard.writeText(url);
    mostrarToast('URL copiada al portapapeles', 'exito', 2000);
  } catch {
    // Fallback para navegadores que no soportan Clipboard API
    const input = document.createElement('input');
    input.value = url;
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
 * Notifica al usuario que la exportación de reportes globales estará disponible
 * en la próxima versión. Función requerida por los botones del HTML.
 */
function exportarReporte() {
  mostrarToast(
    'La exportación de reportes globales estará disponible en la próxima versión',
    'info',
    4000
  );
}

// -----------------------------------------------
// NAVEGACIÓN Y UTILIDADES DE UI
// -----------------------------------------------

/** Desplaza la vista con animación suave hasta la sección de alertas recientes */
function scrollToAlertas() {
  const el = document.getElementById('seccion-alertas');
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/** Abre o cierra el sidebar en dispositivos móviles con overlay de fondo */
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const abierto = sidebar.classList.toggle('abierto');
  overlay.style.display = abierto ? 'block' : 'none';
}