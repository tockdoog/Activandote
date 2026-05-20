// frontend/js/license.js
// Sistema de verificación y countdown de licencia en el frontend.
// Se incluye en todas las páginas protegidas DESPUÉS de api.js.
// Gestiona: verificación al cargar, banner de advertencia, countdown en tiempo real
// y verificación periódica en segundo plano.

// -----------------------------------------------
// Configuración del módulo
// -----------------------------------------------
const LICENSE_CONFIG = {
  // Páginas que NO verifican licencia
  PAGINAS_EXCLUIDAS: ['index.html', 'license-expired.html', ''],

  // Cada cuántos minutos re-verificar con el servidor en segundo plano
  INTERVALO_VERIFICACION_MINUTOS: 10,
};

// Variable global para el intervalo del countdown del banner
let _countdownInterval = null;


// -----------------------------------------------
// VERIFICACIÓN PRINCIPAL
// Se ejecuta automáticamente al cargar el script en cualquier página protegida
// -----------------------------------------------

/**
 * Verifica el estado de la licencia contra el backend.
 * - Vencida → redirige a license-expired.html
 * - Próxima a vencer → muestra banner con countdown
 * - Vigente → no hace nada visible
 */
async function verificarLicencia() {
  // No ejecutar en páginas excluidas (login, bloqueo)
  const paginaActual = window.location.pathname.split('/').pop();
  if (LICENSE_CONFIG.PAGINAS_EXCLUIDAS.includes(paginaActual)) return;

  // No ejecutar sin sesión activa
  if (!api.estaAutenticado()) return;

  try {
    // Consultar estado al backend — incluye segundos_restantes para el countdown
    const estado = await api.get('/licensing/estado');

    // Guardar en sessionStorage para acceso rápido sin repetir la petición
    sessionStorage.setItem('license_status', JSON.stringify({
      ...estado,
      verificado_en: Date.now()
    }));

    // Sin acceso: redirigir inmediatamente a la página de bloqueo
    if (!estado.acceso_permitido) {
      window.location.href = 'license-expired.html';
      return;
    }

    // Próxima a vencer: mostrar banner con countdown en tiempo real
    if (estado.mostrar_advertencia) {
      mostrarBannerAdvertencia(estado);
    }

  } catch (error) {
    // Error 402 explícito del servidor: bloquear de inmediato
    if (error.status === 402) {
      window.location.href = 'license-expired.html';
      return;
    }
    // Otros errores de red: no bloquear, solo loguear
    console.warn('[FitPro License] No se pudo verificar la licencia:', error.message);
  }
}


// -----------------------------------------------
// BANNER DE ADVERTENCIA CON COUNTDOWN
// Aparece en la parte superior cuando quedan <= N días
// -----------------------------------------------

/**
 * Inyecta el banner rojo con countdown en tiempo real.
 * El countdown corre localmente en JS sin nuevas peticiones al servidor.
 * @param {object} estado - Respuesta del endpoint /licensing/estado
 */
function mostrarBannerAdvertencia(estado) {
  // No duplicar si ya existe
  if (document.getElementById('license-warning-banner')) return;

  // Calcular la fecha exacta de vencimiento desde segundos_restantes
  const fechaVencimiento = new Date(Date.now() + (estado.segundos_restantes * 1000));

  // Crear el elemento del banner
  const banner = document.createElement('div');
  banner.id = 'license-warning-banner';
  banner.style.cssText = `
    position: fixed;
    top: 0; left: 0; right: 0;
    z-index: 99999;
    background: linear-gradient(135deg, #8B0000, #CC0000);
    color: #ffffff;
    padding: 0 20px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    font-family: 'Inter', sans-serif;
    font-size: 0.82rem;
    font-weight: 500;
    box-shadow: 0 2px 16px rgba(204,0,0,0.40);
    animation: licenseSlideDown 0.35s cubic-bezier(0.16,1,0.3,1);
  `;

  // Inyectar keyframe de animación si no existe aún
  if (!document.getElementById('license-anim-style')) {
    const styleEl = document.createElement('style');
    styleEl.id = 'license-anim-style';
    styleEl.textContent = `
      @keyframes licenseSlideDown {
        from { transform: translateY(-100%); opacity: 0; }
        to   { transform: translateY(0);     opacity: 1; }
      }
      #license-countdown {
        font-variant-numeric: tabular-nums;
        font-weight: 700;
        color: #FFD0D0;
        letter-spacing: 0.5px;
      }
    `;
    document.head.appendChild(styleEl);
  }

  // HTML interno del banner con el countdown
  banner.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;flex:1;min-width:0">
      <span style="font-size:1rem;flex-shrink:0">⚠️</span>
      <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
        <strong>Licencia próxima a vencer</strong> —
        Expira el ${estado.fecha_vencimiento}.
        Tiempo restante: <span id="license-countdown">calculando...</span>
      </span>
    </div>
    <div style="display:flex;align-items:center;gap:8px;flex-shrink:0">
      <button
        onclick="window.location.href='license-expired.html'"
        style="
          background: rgba(255,255,255,0.15);
          border: 1px solid rgba(255,255,255,0.30);
          color: #fff;
          border-radius: 6px;
          padding: 5px 12px;
          font-size: 0.78rem;
          font-weight: 700;
          cursor: pointer;
          font-family: inherit;
          white-space: nowrap;
          transition: background 0.2s;
        "
        onmouseover="this.style.background='rgba(255,255,255,0.25)'"
        onmouseout="this.style.background='rgba(255,255,255,0.15)'"
      >🔑 Renovar ahora</button>
      <button
        onclick="_descartarBannerLicencia()"
        style="
          background: none;
          border: none;
          color: rgba(255,255,255,0.60);
          cursor: pointer;
          font-size: 1.2rem;
          padding: 0 4px;
          line-height: 1;
          transition: color 0.2s;
        "
        onmouseover="this.style.color='#fff'"
        onmouseout="this.style.color='rgba(255,255,255,0.60)'"
        title="Descartar advertencia"
      >×</button>
    </div>
  `;

  // Insertar como primer hijo del body
  document.body.insertBefore(banner, document.body.firstChild);

  // Compensar el alto del banner en el contenido de la página
  const alturaBanner = 48;
  const paddingActual = parseInt(document.body.style.paddingTop || '0');
  document.body.style.paddingTop = (paddingActual + alturaBanner) + 'px';

  // Iniciar el countdown en tiempo real usando la fecha calculada
  _iniciarCountdown(fechaVencimiento);
}

/**
 * Elimina el banner y limpia el intervalo del countdown.
 */
function _descartarBannerLicencia() {
  const banner = document.getElementById('license-warning-banner');
  if (banner) {
    const alturaBanner = banner.offsetHeight;
    banner.remove();
    const paddingActual = parseInt(document.body.style.paddingTop || '0');
    document.body.style.paddingTop = Math.max(0, paddingActual - alturaBanner) + 'px';
  }
  if (_countdownInterval) {
    clearInterval(_countdownInterval);
    _countdownInterval = null;
  }
}

/**
 * Inicia el countdown que actualiza el texto cada segundo.
 * Cuando llega a cero, redirige a la página de bloqueo.
 * @param {Date} fechaVencimiento - Fecha exacta de expiración
 */
function _iniciarCountdown(fechaVencimiento) {
  // Limpiar cualquier countdown previo
  if (_countdownInterval) clearInterval(_countdownInterval);

  function actualizarCountdown() {
    const ahora = Date.now();
    const diferencia = fechaVencimiento.getTime() - ahora;
    const el = document.getElementById('license-countdown');

    // Si ya venció mientras el usuario estaba en la app
    if (diferencia <= 0) {
      clearInterval(_countdownInterval);
      if (el) el.textContent = '¡EXPIRADA!';
      // Esperar 2 segundos y redirigir al bloqueo
      setTimeout(() => {
        window.location.href = 'license-expired.html';
      }, 2000);
      return;
    }

    // Calcular días, horas, minutos y segundos restantes
    const dias    = Math.floor(diferencia / (1000 * 60 * 60 * 24));
    const horas   = Math.floor((diferencia % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutos = Math.floor((diferencia % (1000 * 60 * 60)) / (1000 * 60));
    const segs    = Math.floor((diferencia % (1000 * 60)) / 1000);

    // Formatear con ceros a la izquierda para consistencia visual
    const pad = (n) => String(n).padStart(2, '0');

    let textoCountdown;
    if (dias > 0) {
      // Más de un día: mostrar días y horas
      textoCountdown = `${dias}d ${pad(horas)}h ${pad(minutos)}m ${pad(segs)}s`;
    } else {
      // Menos de un día: mostrar solo horas, minutos y segundos
      textoCountdown = `${pad(horas)}h ${pad(minutos)}m ${pad(segs)}s`;
    }

    if (el) el.textContent = textoCountdown;
  }

  // Ejecutar inmediatamente y luego cada segundo
  actualizarCountdown();
  _countdownInterval = setInterval(actualizarCountdown, 1000);
}


// -----------------------------------------------
// VERIFICACIÓN PERIÓDICA EN SEGUNDO PLANO
// Re-consulta al servidor cada N minutos para detectar cambios
// -----------------------------------------------

/**
 * Si la licencia vence mientras el usuario está usando la app,
 * esta función lo detecta y redirige automáticamente.
 */
function iniciarVerificacionPeriodica() {
  const intervaloMs = LICENSE_CONFIG.INTERVALO_VERIFICACION_MINUTOS * 60 * 1000;

  setInterval(async () => {
    if (!api.estaAutenticado()) return;

    try {
      const estado = await api.get('/licensing/estado');

      if (!estado.acceso_permitido) {
        // Mostrar toast de aviso antes de redirigir
        if (typeof mostrarToast === 'function') {
          mostrarToast('Tu licencia ha vencido. Redirigiendo...', 'error', 3000);
        }
        setTimeout(() => {
          window.location.href = 'license-expired.html';
        }, 3000);
      }

    } catch (error) {
      if (error.status === 402) {
        window.location.href = 'license-expired.html';
      }
    }
  }, intervaloMs);
}


// -----------------------------------------------
// INTERCEPTOR GLOBAL DE ERROR 402
// Captura respuestas 402 de cualquier endpoint y redirige al bloqueo
// -----------------------------------------------
(function interceptar402() {
  // Verificar que ApiClient existe antes de extenderlo
  if (typeof ApiClient === 'undefined') return;

  const _original = ApiClient.prototype._procesarRespuesta;
  if (!_original) return;

  ApiClient.prototype._procesarRespuesta = async function(respuesta) {
    if (respuesta.status === 402) {
      const pagina = window.location.pathname.split('/').pop();
      // No redirigir si ya estamos en la página de bloqueo (evita bucle)
      if (pagina !== 'license-expired.html') {
        window.location.href = 'license-expired.html';
        return;
      }
    }
    return _original.call(this, respuesta);
  };
})();


// -----------------------------------------------
// AUTO-EJECUCIÓN al incluir el script
// -----------------------------------------------
verificarLicencia();
iniciarVerificacionPeriodica();