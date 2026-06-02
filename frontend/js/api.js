// frontend/js/api.js

// ───────────────────────────────────────────────────────────────────────────────
// Detección automática del entorno de ejecución.
// - Desarrollo local (Live Server puerto 5500/5501): usa URL completa al backend.
// - Docker / Producción (nginx puerto 80): usa ruta relativa, nginx la proxea.
// ───────────────────────────────────────────────────────────────────────────────
const _PUERTOS_DEV = ['5500', '5501', '3000', '8080'];
const _ES_DESARROLLO = _PUERTOS_DEV.includes(window.location.port);

const API_BASE_URL = _ES_DESARROLLO
  ? 'http://127.0.0.1:8000/api/v1'   // Desarrollo: apunta directo al backend local
  : '/api/v1';                         // Docker/Producción: nginx lo proxea al backend


class ApiClient {

  constructor() {
    // Claves usadas en localStorage para persistir la sesión entre páginas
    this._accessKey  = 'fp_at';
    this._refreshKey = 'fp_rt';
    this._userKey    = 'fp_user';

    // Flag interno para evitar bucles infinitos al renovar el token
    this._renovandoToken = false;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // GESTIÓN DE TOKENS Y SESIÓN
  // ─────────────────────────────────────────────────────────────────────────

  /** Guarda los tokens y datos del usuario en localStorage */
  guardarSesion(tokenData) {
    localStorage.setItem(this._accessKey,  tokenData.access_token);
    localStorage.setItem(this._refreshKey, tokenData.refresh_token);
    localStorage.setItem(this._userKey,    JSON.stringify(tokenData.user));
  }

  /** Elimina todos los datos de sesión del localStorage */
  limpiarSesion() {
    localStorage.removeItem(this._accessKey);
    localStorage.removeItem(this._refreshKey);
    localStorage.removeItem(this._userKey);
  }

  /** Retorna el access token actual o null si no existe */
  getAccessToken() {
    return localStorage.getItem(this._accessKey);
  }

  /** Retorna el objeto de usuario guardado o null */
  getUsuario() {
    const data = localStorage.getItem(this._userKey);
    return data ? JSON.parse(data) : null;
  }

  /** Retorna true si hay un access token almacenado */
  estaAutenticado() {
    return !!this.getAccessToken();
  }

  // ─────────────────────────────────────────────────────────────────────────
  // MÉTODO HTTP GENÉRICO CON MANEJO DE ERRORES
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Ejecuta una petición HTTP al backend.
   * Adjunta el token Bearer automáticamente.
   * Si recibe 401 en rutas protegidas, intenta renovar el token antes de reintentar.
   */
  async request(endpoint, opciones = {}) {
    const token = this.getAccessToken();

    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...(token && { 'Authorization': `Bearer ${token}` }),
        ...opciones.headers
      },
      ...opciones
    };

    // Los endpoints /auth/* manejan sus propios errores 401 (credenciales incorrectas)
    const esRutaAuth = endpoint.startsWith('/auth/');

    try {
      const respuesta = await fetch(`${API_BASE_URL}${endpoint}`, config);

      // Intentar renovar el token si expiró (solo en rutas protegidas)
      if (respuesta.status === 401 && !esRutaAuth && !this._renovandoToken) {
        const renovado = await this._renovarToken();
        if (renovado) {
          config.headers['Authorization'] = `Bearer ${this.getAccessToken()}`;
          const reintento = await fetch(`${API_BASE_URL}${endpoint}`, config);
          return await this._procesarRespuesta(reintento);
        } else {
          this.limpiarSesion();
          window.location.href = 'index.html';
          return;
        }
      }

      return await this._procesarRespuesta(respuesta);

    } catch (error) {
      console.error('Error de red:', error);
      mostrarToast('Error de conexión con el servidor', 'error');
      throw error;
    }
  }

  /** Procesa la respuesta HTTP: extrae JSON o lanza error con mensaje descriptivo */
  async _procesarRespuesta(respuesta) {
    if (respuesta.status === 204) return null;

    let datos;
    try {
      datos = await respuesta.json();
    } catch {
      datos = null;
    }

    if (respuesta.ok) return datos;

    const mensajeError = datos?.detail || datos?.detalle || this._mensajeError(respuesta.status);
    const error = new Error(mensajeError);
    error.status = respuesta.status;
    error.datos  = datos;
    throw error;
  }

  /**
   * Intenta renovar el access token usando el refresh token almacenado.
   * Usa un flag _renovandoToken para evitar llamadas recursivas infinitas.
   */
  async _renovarToken() {
    const refreshToken = localStorage.getItem(this._refreshKey);
    if (!refreshToken) return false;

    this._renovandoToken = true;

    try {
      const respuesta = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken })
      });

      if (respuesta.ok) {
        const datos = await respuesta.json();
        this.guardarSesion(datos);
        return true;
      }

      return false;
    } catch {
      return false;
    } finally {
      this._renovandoToken = false;
    }
  }

  /** Retorna un mensaje de error legible según el código HTTP recibido */
  _mensajeError(status) {
    const mensajes = {
      400: 'Solicitud incorrecta',
      401: 'Credenciales incorrectas',
      403: 'Acceso denegado',
      404: 'Recurso no encontrado',
      409: 'El registro ya existe',
      422: 'Datos del formulario inválidos',
      429: 'Demasiadas solicitudes. Espere un momento.',
      500: 'Error interno del servidor',
      503: 'Servicio no disponible'
    };
    return mensajes[status] || `Error HTTP ${status}`;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // MÉTODOS HTTP CONVENIENTES
  // ─────────────────────────────────────────────────────────────────────────

  get(endpoint)          { return this.request(endpoint, { method: 'GET' }); }
  post(endpoint, datos)  { return this.request(endpoint, { method: 'POST',   body: JSON.stringify(datos) }); }
  put(endpoint, datos)   { return this.request(endpoint, { method: 'PUT',    body: JSON.stringify(datos) }); }
  patch(endpoint, datos) { return this.request(endpoint, { method: 'PATCH',  body: JSON.stringify(datos) }); }
  delete(endpoint)       { return this.request(endpoint, { method: 'DELETE' }); }

  // ─────────────────────────────────────────────────────────────────────────
  // ENDPOINTS DE AUTENTICACIÓN
  // ─────────────────────────────────────────────────────────────────────────

  async login(email, password) {
    const datos = await this.post('/auth/login', { email, password });
    this.guardarSesion(datos);
    return datos;
  }

  async registro(datosUsuario) {
    const datos = await this.post('/auth/registro', datosUsuario);
    this.guardarSesion(datos);
    return datos;
  }

  async logout() {
    try { await this.post('/auth/logout', {}); } catch { /* ignorar error de red */ }
    this.limpiarSesion();
    window.location.href = 'index.html';
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ENDPOINTS DE PACIENTES
  // ─────────────────────────────────────────────────────────────────────────

  listarPacientes(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.get(`/patients${qs ? '?' + qs : ''}`);
  }

  obtenerPaciente(id)           { return this.get(`/patients/${id}`); }
  crearPaciente(datos)          { return this.post('/patients/', datos); }
  actualizarPaciente(id, datos) { return this.put(`/patients/${id}`, datos); }
  eliminarPaciente(id)          { return this.delete(`/patients/${id}`); }

  // ─────────────────────────────────────────────────────────────────────────
  // ENDPOINTS DE EVALUACIONES
  // ─────────────────────────────────────────────────────────────────────────

  listarEvaluaciones(patientId)     { return this.get(`/evaluations/patients/${patientId}`); }
  crearEvaluacion(patientId, datos) { return this.post(`/evaluations/patients/${patientId}`, datos); }
  obtenerEvaluacion(id)             { return this.get(`/evaluations/${id}`); }
  actualizarEvaluacion(id, datos)   { return this.put(`/evaluations/${id}`, datos); }
  eliminarEvaluacion(id)            { return this.delete(`/evaluations/${id}`); }

  compararEvaluaciones(patientId, id1, id2) {
    return this.get(`/evaluations/patients/${patientId}/comparar?eval_id_1=${id1}&eval_id_2=${id2}`);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // EXPORTACIÓN POR PACIENTE (Excel individual)
  // ─────────────────────────────────────────────────────────────────────────

  /** Descarga el historial de evaluaciones de un paciente como archivo Excel */
  async exportarExcel(patientId, nombrePaciente) {
    const token = this.getAccessToken();

    const respuesta = await fetch(
      `${API_BASE_URL}/evaluations/patients/${patientId}/export/excel`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    );

    if (!respuesta.ok) throw new Error('Error al generar el archivo Excel');

    const blob = await respuesta.blob();
    const url  = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href     = url;
    link.download = `fitpro_${nombrePaciente.replace(/\s+/g, '_')}.xlsx`;
    link.click();
    URL.revokeObjectURL(url);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // EXPORTACIÓN GLOBAL — Nuevos endpoints del reporte global
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Obtiene los datos del reporte global en JSON.
   * Usado para la previsualización en el modal antes de exportar.
   */
  obtenerReporteGlobal() {
    return this.get('/dashboard/reporte-global');
  }

  /**
   * Descarga el reporte global completo en formato Excel (.xlsx).
   * Realiza la petición con fetch directo para manejar la respuesta binaria.
   * El archivo tiene 4 hojas: Resumen, Pacientes, Evolución, Alertas.
   */
  async exportarReporteGlobalExcel() {
    const token = this.getAccessToken();

    const respuesta = await fetch(
      `${API_BASE_URL}/dashboard/reporte-global/excel`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    );

    if (!respuesta.ok) throw new Error('Error al generar el reporte Excel');

    // Obtener nombre del archivo desde la cabecera Content-Disposition
    const disposition = respuesta.headers.get('Content-Disposition') || '';
    const match       = disposition.match(/filename=([^;]+)/);
    const nombre      = match ? match[1].trim() : 'fitpro_reporte_global.xlsx';

    // Crear enlace temporal para descargar el blob binario
    const blob = await respuesta.blob();
    const url  = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href     = url;
    link.download = nombre;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  /**
   * Descarga el reporte global completo en formato PDF.
   * Diseño deportivo con paleta rojo/negro/blanco.
   */
  async exportarReporteGlobalPDF() {
    const token = this.getAccessToken();

    const respuesta = await fetch(
      `${API_BASE_URL}/dashboard/reporte-global/pdf`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    );

    if (!respuesta.ok) throw new Error('Error al generar el reporte PDF');

    // Obtener nombre del archivo desde la cabecera
    const disposition = respuesta.headers.get('Content-Disposition') || '';
    const match       = disposition.match(/filename=([^;]+)/);
    const nombre      = match ? match[1].trim() : 'fitpro_reporte_global.pdf';

    const blob = await respuesta.blob();
    const url  = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href     = url;
    link.download = nombre;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ENDPOINTS DEL DASHBOARD
  // ─────────────────────────────────────────────────────────────────────────

  obtenerEstadisticas()     { return this.get('/dashboard/stats'); }
  obtenerEvolucion()        { return this.get('/dashboard/evoluciones'); }
  obtenerAlertasRecientes() { return this.get('/dashboard/alertas-recientes'); }
  obtenerTopPacientes()     { return this.get('/dashboard/top-pacientes'); }
}

// ─────────────────────────────────────────────────────────────────────────────
// Instancia global singleton — compartida por todos los archivos JS del frontend
// ─────────────────────────────────────────────────────────────────────────────
const api = new ApiClient();


// ─────────────────────────────────────────────────────────────────────────────
// SISTEMA DE NOTIFICACIONES TOAST
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Muestra una notificación tipo toast en la esquina inferior derecha.
 * @param {string} mensaje  - Texto a mostrar
 * @param {string} tipo     - 'exito' | 'error' | 'info' | 'advertencia'
 * @param {number} duracion - Milisegundos hasta desaparecer (default 3500)
 */
function mostrarToast(mensaje, tipo = 'info', duracion = 3500) {
  let contenedor = document.getElementById('toast-container');
  if (!contenedor) {
    contenedor = document.createElement('div');
    contenedor.id        = 'toast-container';
    contenedor.className = 'toast-container';
    document.body.appendChild(contenedor);
  }

  const iconos = { exito: '✓', error: '✕', info: 'ℹ', advertencia: '⚠' };

  const toast = document.createElement('div');
  toast.className = `toast-fitpro ${tipo}`;
  toast.innerHTML = `
    <span style="margin-right:8px;font-weight:700;font-size:1rem">${iconos[tipo] || 'ℹ'}</span>
    <span>${mensaje}</span>
  `;

  contenedor.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'toastEntrada 0.3s ease reverse forwards';
    setTimeout(() => {
      if (toast.parentNode) toast.remove();
    }, 300);
  }, duracion);
}


// ─────────────────────────────────────────────────────────────────────────────
// INDICADOR DE CARGA GLOBAL
// ─────────────────────────────────────────────────────────────────────────────

function mostrarCargando() {
  let overlay = document.getElementById('loading-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id        = 'loading-overlay';
    overlay.className = 'loading-overlay';
    overlay.innerHTML = `
      <div class="spinner"></div>
      <p style="color:var(--gris-claro);font-size:.85rem;margin-top:8px">Cargando...</p>
    `;
    document.body.appendChild(overlay);
  }
  overlay.style.display = 'flex';
}

function ocultarCargando() {
  const overlay = document.getElementById('loading-overlay');
  if (overlay) overlay.style.display = 'none';
}


// ─────────────────────────────────────────────────────────────────────────────
// UTILIDADES DE FORMATO
// ─────────────────────────────────────────────────────────────────────────────

/** Formatea una fecha ISO a formato legible en español colombiano */
function formatearFecha(fechaISO) {
  if (!fechaISO) return 'N/A';
  const opciones = { year: 'numeric', month: 'long', day: 'numeric' };
  return new Date(fechaISO + 'T00:00:00').toLocaleDateString('es-CO', opciones);
}

/** Formatea un número con N decimales */
function formatearNumero(valor, decimales = 1) {
  if (valor == null) return 'N/A';
  return Number(valor).toFixed(decimales);
}

/** Retorna el estilo CSS de color según si el indicador es mejora o empeoramiento */
function claseProgreso(esMejora) {
  if (esMejora === true)  return 'color:var(--verde-ok)';
  if (esMejora === false) return 'color:var(--rojo-suave)';
  return 'color:var(--gris-claro)';
}