// frontend/js/dashboard.js
// Lógica del panel estadístico: carga de métricas, gráficas con Chart.js,
// alertas recientes y modal QR para acceso en red local.

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
// GRÁFICA DE EVOLUCIÓN MENSUAL — Paleta verde
// -----------------------------------------------

/**
 * Carga evaluaciones por mes (últimos 12 meses) y renderiza barras verdes.
 * Tooltips con fondo blanco y texto oscuro para legibilidad.
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
            // Fondo blanco — legible sobre el fondo claro del sistema
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
            ticks: {
              color:    '#374E37',
              stepSize: 1,
              font:     { size: 11, family: 'Inter' }
            },
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
// GRÁFICA TOP 5 PACIENTES — Barras horizontales verdes
// -----------------------------------------------

/**
 * Carga los 5 pacientes con más evaluaciones con opacidad decreciente.
 * Ejes con texto oscuro y legible sobre fondo blanco.
 */
async function cargarTopPacientes() {
  try {
    const datos = await api.obtenerTopPacientes();

    const nombres      = datos.top_pacientes.map(p => p.nombre.split(' ')[0]);
    const evaluaciones = datos.top_pacientes.map(p => p.total_evaluaciones);

    const canvas = document.getElementById('grafica-top-pacientes');
    if (!canvas) return;

    if (graficaTopPacientes) graficaTopPacientes.destroy();

    // Verde con opacidad decreciente para efecto ranking
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
            ticks: {
              color:    '#374E37',
              stepSize: 1,
              font:     { size: 11, family: 'Inter' }
            },
            grid: { color: 'rgba(0,0,0,0.06)' }
          },
          y: {
            ticks: {
              // Texto oscuro y legible — el fondo es blanco
              color: '#1F3A1F',
              font:  { size: 12, weight: '600', family: 'Inter' }
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
// TABLA DE ALERTAS RECIENTES — Paleta verde/blanco
// -----------------------------------------------

/**
 * Carga evaluaciones con alertas activas y las muestra en la tabla.
 * HTML generado con colores de la paleta verde/blanco.
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

    // Generar filas con avatares y colores del nuevo diseño
    tbody.innerHTML = datos.alertas.map(alerta => `
      <tr>
        <td>
          <a
            href="patient-detail.html?id=${alerta.patient_id}"
            style="
              color:#111827;
              text-decoration:none;
              font-weight:600;
              font-size:.875rem;
              display:flex;
              align-items:center;
              gap:8px
            "
          >
            <!-- Avatar con iniciales en paleta verde -->
            <div style="
              width:32px;height:32px;min-width:32px;
              border-radius:50%;
              background:var(--verde-translucido);
              border:1.5px solid var(--verde-borde);
              display:flex;align-items:center;justify-content:center;
              font-size:.75rem;font-weight:700;color:#15803D;
              font-family:var(--fuente-display)
            ">
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
          <span style="
            color:#991B1B;
            font-size:.82rem;
            font-weight:500;
            display:flex;
            align-items:flex-start;
            gap:5px
          ">
            <i class="bi bi-exclamation-triangle-fill"
               style="color:var(--rojo-alerta);flex-shrink:0;margin-top:1px"></i>
            ${alerta.detalle || 'Sin detalle'}
          </span>
        </td>
        <td>
          <a
            href="patient-detail.html?id=${alerta.patient_id}"
            class="btn btn-secundario btn-sm"
          >
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
 *
 * Flujo:
 * 1. Consulta GET /api/v1/dashboard/network-info al backend.
 *    El backend lee HOST_IP inyectada por iniciar-fitpro.ps1, que es la IP
 *    real de Windows (192.168.x.x), accesible desde otros dispositivos WiFi.
 * 2. Genera el QR con QRCode.js apuntando a esa URL.
 * 3. Muestra la URL en texto con botón de copiar.
 *
 * Por qué no usar window.location.hostname:
 *   En la PC del servidor vale "localhost", inaccesible desde otros dispositivos.
 */
async function abrirModalQR() {
  // Inicializar instancia de Bootstrap solo la primera vez
  if (!_modalQRInstancia) {
    const elModal = document.getElementById('modal-qr');
    if (!elModal) return;
    _modalQRInstancia = new bootstrap.Modal(elModal);
  }

  // Limpiar QR anterior y mostrar estado de carga
  const contenedorQR = document.getElementById('qr-canvas-container');
  const elUrlTexto   = document.getElementById('url-acceso-red');

  if (contenedorQR) contenedorQR.innerHTML = '';
  if (elUrlTexto)   elUrlTexto.textContent  = 'Detectando IP de red...';

  _modalQRInstancia.show();

  try {
    const info = await api.get('/dashboard/network-info');
    _urlRedLocal = info.url;

    if (elUrlTexto) elUrlTexto.textContent = _urlRedLocal;

    // Generar QR con colores negro/blanco para máximo contraste en escáner
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
      // QRCode.js no cargó — fallback de texto
      contenedorQR.innerHTML = `
        <div style="
          width:200px;height:200px;
          display:flex;align-items:center;justify-content:center;
          color:var(--verde-primario);font-size:.8rem;
          text-align:center;padding:16px;
          background:var(--gris-100);
          border-radius:var(--radio-md);
          border:1px solid var(--gris-borde)
        ">
          <div>
            <i class="bi bi-qr-code"
               style="font-size:2rem;display:block;margin-bottom:8px;
                      color:var(--verde-primario)"></i>
            QR no disponible.<br>Usa la URL de arriba.
          </div>
        </div>`;
    }

  } catch (error) {
    console.error('Error obteniendo info de red:', error);
    _urlRedLocal = window.location.origin;

    if (elUrlTexto) elUrlTexto.textContent = _urlRedLocal;

    if (contenedorQR) {
      contenedorQR.innerHTML = `
        <div style="
          width:200px;height:200px;
          display:flex;align-items:center;justify-content:center;
          color:var(--rojo-alerta);font-size:.8rem;
          text-align:center;padding:16px;
          background:var(--rojo-bg);
          border-radius:var(--radio-md);
          border:1px solid rgba(239,68,68,0.3)
        ">
          <div>
            <i class="bi bi-wifi-off"
               style="font-size:2rem;display:block;margin-bottom:8px"></i>
            No se pudo detectar<br>la IP de red.<br>
            <span style="color:#516651;font-size:.75rem">
              Ejecuta iniciar-fitpro.bat
            </span>
          </div>
        </div>`;
    }
  }
}

/**
 * Copia la URL de red local al portapapeles.
 * Clipboard API moderna con fallback a execCommand para navegadores legacy.
 */
async function copiarURLRed() {
  const url = _urlRedLocal || window.location.origin;

  try {
    await navigator.clipboard.writeText(url);
    mostrarToast('URL copiada al portapapeles', 'exito', 2000);
  } catch {
    // Fallback para navegadores sin Clipboard API
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

/** Notifica que la exportación global estará disponible próximamente. */
function exportarReporte() {
  mostrarToast(
    'La exportación de reportes globales estará disponible en la próxima versión',
    'info',
    4000
  );
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