// frontend/js/auth.js
// Lógica de autenticación: login, registro, validaciones y redirección.
// Solo redirige al dashboard si el token almacenado es válido en el servidor.

// -----------------------------------------------
// Redirección automática si ya hay sesión VÁLIDA activa.
// Valida el token contra el backend antes de redirigir
// para evitar bucles cuando el token expiró o es inválido.
// -----------------------------------------------
(async function verificarSesionActiva() {
  // Si no hay token en localStorage, no hacer nada — mostrar login normalmente
  if (!api.estaAutenticado()) return;

  try {
    // Verificar que el token almacenado sea aceptado por el servidor.
    // Si el token expiró o fue revocado, el backend responde 401 y
    // this.request() ya limpia la sesión y no lanza excepción bloqueante.
    await api.get('/auth/me');

    // Token válido confirmado por el servidor: redirigir al dashboard
    window.location.href = 'dashboard.html';

  } catch (error) {
    // Token inválido, expirado o error de red:
    // limpiar sesión corrupta y mostrar el login normalmente
    api.limpiarSesion();
  }
})();

// -----------------------------------------------
// GESTIÓN DE PESTAÑAS LOGIN / REGISTRO
// -----------------------------------------------

/**
 * Cambia entre los paneles de Login y Registro.
 * Limpia errores visibles al cambiar de pestaña.
 */
function cambiarTab(tab) {
  // Ocultar todos los paneles y desactivar todas las pestañas
  document.querySelectorAll('.auth-panel').forEach(p => p.classList.remove('activo'));
  document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('activo'));

  // Activar el panel y pestaña seleccionados
  document.getElementById(`panel-${tab}`).classList.add('activo');
  document.getElementById(`tab-${tab}`).classList.add('activo');

  // Limpiar alertas de error al cambiar de pestaña
  ocultarErrores();
}

// -----------------------------------------------
// TOGGLE DE VISIBILIDAD DE CONTRASEÑA
// -----------------------------------------------

/**
 * Alterna la visibilidad del campo de contraseña.
 * Cambia el ícono del ojo según el estado.
 */
function togglePassword(campoId, boton) {
  const campo = document.getElementById(campoId);
  const icono = boton.querySelector('i');

  if (campo.type === 'password') {
    campo.type = 'text';
    icono.className = 'bi bi-eye-slash';
  } else {
    campo.type = 'password';
    icono.className = 'bi bi-eye';
  }
}

// -----------------------------------------------
// INDICADOR DE FORTALEZA DE CONTRASEÑA
// -----------------------------------------------

/**
 * Evalúa la fortaleza de la contraseña ingresada.
 * Actualiza la barra de progreso y el texto descriptivo.
 */
function evaluarFortaleza(password) {
  const fill = document.getElementById('strength-fill');
  const text = document.getElementById('strength-text');

  // Criterios de fortaleza: longitud, mayúscula, minúscula, número, símbolo
  let puntos = 0;
  if (password.length >= 8)  puntos++;
  if (password.length >= 12) puntos++;
  if (/[A-Z]/.test(password)) puntos++;
  if (/[a-z]/.test(password)) puntos++;
  if (/\d/.test(password))    puntos++;
  if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) puntos++;

  // Actualizar barra de progreso con color y ancho proporcional a los puntos
  const porcentaje = Math.min((puntos / 6) * 100, 100);
  fill.style.width = porcentaje + '%';

  if (puntos <= 2) {
    fill.style.backgroundColor = '#CC0000';
    text.textContent = 'Contraseña débil';
    text.style.color = '#FF4444';
  } else if (puntos <= 4) {
    fill.style.backgroundColor = '#FFA500';
    text.textContent = 'Contraseña moderada';
    text.style.color = '#FFA500';
  } else {
    fill.style.backgroundColor = '#00CC55';
    text.textContent = 'Contraseña fuerte';
    text.style.color = '#00CC55';
  }
}

// -----------------------------------------------
// MANEJO DEL FORMULARIO DE LOGIN
// -----------------------------------------------

/**
 * Procesa el envío del formulario de login.
 * Valida los campos y llama al endpoint de autenticación.
 */
document.getElementById('form-login').addEventListener('submit', async function (e) {
  e.preventDefault();

  const email    = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;

  // Validación básica de campos antes de llamar al servidor
  let valido = true;

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    mostrarCampoError('error-login-email', 'login-email');
    valido = false;
  } else {
    limpiarCampoError('error-login-email', 'login-email');
  }

  if (!password) {
    mostrarCampoError('error-login-password', 'login-password');
    valido = false;
  } else {
    limpiarCampoError('error-login-password', 'login-password');
  }

  if (!valido) return;

  // Mostrar estado de carga en el botón mientras se procesa
  setBotonCargando('btn-login', 'btn-login-texto', 'btn-login-cargando', true);

  try {
    // Llamar al endpoint de login y guardar la sesión automáticamente
    await api.login(email, password);
    mostrarToast('¡Bienvenido! Redirigiendo...', 'exito');

    // Breve pausa para que el toast sea visible antes de redirigir
    setTimeout(() => {
      window.location.href = 'dashboard.html';
    }, 800);

  } catch (error) {
    // Mostrar error específico del servidor o mensaje genérico
    mostrarAlertaError(
      'error-login',
      'error-login-msg',
      error.message || 'Credenciales incorrectas'
    );
  } finally {
    setBotonCargando('btn-login', 'btn-login-texto', 'btn-login-cargando', false);
  }
});

// -----------------------------------------------
// MANEJO DEL FORMULARIO DE REGISTRO
// -----------------------------------------------

/**
 * Procesa el envío del formulario de registro.
 * Valida todos los campos incluyendo coincidencia de contraseñas.
 */
document.getElementById('form-registro').addEventListener('submit', async function (e) {
  e.preventDefault();

  const nombre   = document.getElementById('reg-nombre').value.trim();
  const email    = document.getElementById('reg-email').value.trim();
  const telefono = document.getElementById('reg-telefono').value.trim();
  const password = document.getElementById('reg-password').value;
  const confirm  = document.getElementById('reg-confirm').value;

  // Validar todos los campos del formulario antes de enviar
  let valido = true;

  if (!nombre || nombre.length < 3) {
    mostrarCampoError('error-reg-nombre', 'reg-nombre');
    valido = false;
  } else {
    limpiarCampoError('error-reg-nombre', 'reg-nombre');
  }

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    mostrarCampoError('error-reg-email', 'reg-email');
    valido = false;
  } else {
    limpiarCampoError('error-reg-email', 'reg-email');
  }

  // Verificar requisitos mínimos de seguridad de la contraseña
  if (!password || password.length < 8 || !/[A-Z]/.test(password) || !/\d/.test(password)) {
    mostrarCampoError('error-reg-password', 'reg-password');
    valido = false;
  } else {
    limpiarCampoError('error-reg-password', 'reg-password');
  }

  // Verificar que ambas contraseñas ingresadas sean idénticas
  if (password !== confirm) {
    mostrarCampoError('error-reg-confirm', 'reg-confirm');
    valido = false;
  } else {
    limpiarCampoError('error-reg-confirm', 'reg-confirm');
  }

  if (!valido) return;

  // Mostrar estado de carga en el botón de registro
  setBotonCargando('btn-registro', 'btn-reg-texto', 'btn-reg-cargando', true);

  try {
    // Construir objeto con los datos del nuevo usuario
    const datosUsuario = {
      nombre_completo: nombre,
      email:           email,
      password:        password,
      ...(telefono && { telefono })
    };

    await api.registro(datosUsuario);
    mostrarToast('¡Cuenta creada! Redirigiendo...', 'exito');

    setTimeout(() => {
      window.location.href = 'dashboard.html';
    }, 800);

  } catch (error) {
    mostrarAlertaError(
      'error-registro',
      'error-registro-msg',
      error.message || 'Error al crear la cuenta'
    );
  } finally {
    setBotonCargando('btn-registro', 'btn-reg-texto', 'btn-reg-cargando', false);
  }
});

// -----------------------------------------------
// FUNCIONES AUXILIARES DE UI
// -----------------------------------------------

/** Muestra el mensaje de error debajo de un campo específico del formulario */
function mostrarCampoError(errorId, campoId) {
  document.getElementById(errorId).style.display = 'block';
  document.getElementById(campoId).classList.add('invalido');
}

/** Oculta el mensaje de error de un campo específico del formulario */
function limpiarCampoError(errorId, campoId) {
  document.getElementById(errorId).style.display = 'none';
  document.getElementById(campoId).classList.remove('invalido');
}

/** Muestra la alerta de error global en la parte superior del formulario */
function mostrarAlertaError(alertaId, msgId, mensaje) {
  document.getElementById(alertaId).style.display = 'flex';
  document.getElementById(msgId).textContent = mensaje;
}

/** Oculta todas las alertas y marcas de error de campos en la página */
function ocultarErrores() {
  document.querySelectorAll('.alerta').forEach(a => a.style.display = 'none');
  document.querySelectorAll('.campo-error').forEach(e => e.style.display = 'none');
  document.querySelectorAll('.form-control').forEach(c => c.classList.remove('invalido'));
}

/**
 * Alterna el estado de carga de un botón de submit.
 * Deshabilita el botón y muestra el spinner mientras hay una petición en curso.
 */
function setBotonCargando(btnId, textoId, cargandoId, activo) {
  const btn = document.getElementById(btnId);
  btn.disabled = activo;
  document.getElementById(textoId).style.display  = activo ? 'none'   : 'inline';
  document.getElementById(cargandoId).style.display = activo ? 'inline' : 'none';
}