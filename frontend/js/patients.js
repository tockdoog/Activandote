// frontend/js/patients.js
// Lógica CRUD completa de pacientes: listado, búsqueda, creación, edición y eliminación

// -----------------------------------------------
// Verificación de sesión activa
// -----------------------------------------------
(function verificarAuth() {
  if (!api.estaAutenticado()) {
    window.location.href = 'index.html';
  }
})();

// Estado global de la página de pacientes
const estado = {
  paginaActual: 1,
  porPagina: 20,
  totalPaginas: 1,
  pacienteIdEliminar: null,  // ID del paciente pendiente de eliminación
  modoEdicion: false          // false = crear, true = editar
};

// -----------------------------------------------
// INICIALIZACIÓN AL CARGAR LA PÁGINA
// -----------------------------------------------
document.addEventListener('DOMContentLoaded', function () {
  inicializarUsuario();
  cargarPacientes();
});

// -----------------------------------------------
// INFO DEL USUARIO EN SIDEBAR
// -----------------------------------------------

/** Muestra el nombre y plan del entrenador en el sidebar */
function inicializarUsuario() {
  const usuario = api.getUsuario();
  if (!usuario) return;
  const iniciales = usuario.nombre_completo
    .split(' ').slice(0, 2).map(n => n[0]).join('').toUpperCase();
  document.getElementById('user-avatar').textContent = iniciales;
  document.getElementById('user-name').textContent = usuario.nombre_completo;
  document.getElementById('user-plan').textContent = `Plan ${usuario.plan.toUpperCase()}`;
}

// -----------------------------------------------
// CARGA Y FILTRADO DE PACIENTES
// -----------------------------------------------

/**
 * Carga la lista de pacientes con los filtros activos.
 * Aplica paginación y muestra los resultados en la tabla.
 */
async function cargarPacientes(pagina = 1) {
  estado.paginaActual = pagina;

  // Recoger valores de los filtros activos
  const buscar      = document.getElementById('input-busqueda').value.trim();
  const genero      = document.getElementById('filtro-genero').value;
  const estadoFilt  = document.getElementById('filtro-estado').value;

  // Construir parámetros para la API
  const params = {
    page: pagina,
    per_page: estado.porPagina,
    ...(buscar     && { buscar }),
    ...(genero     && { genero }),
    ...(estadoFilt && { estado: estadoFilt })
  };

  const tbody = document.getElementById('tbody-pacientes');

  // Spinner de carga mientras se obtienen los datos
  tbody.innerHTML = `
    <tr>
      <td colspan="7">
        <div class="estado-vacio" style="padding:2rem">
          <div class="spinner"></div>
        </div>
      </td>
    </tr>`;

  try {
    const respuesta = await api.listarPacientes(params);
    estado.totalPaginas = respuesta.pages;

    // Actualizar contador en el encabezado
    const contadorEl = document.getElementById('contador-pacientes');
    if (contadorEl) {
      contadorEl.textContent =
        ` · ${respuesta.total} paciente${respuesta.total !== 1 ? 's' : ''}`;
    }

    if (respuesta.items.length === 0) {
      renderizarEstadoVacio(tbody, buscar);
      document.getElementById('paginacion').style.display = 'none';
      return;
    }

    // Renderizar filas
    tbody.innerHTML = respuesta.items.map(p => renderizarFilaPaciente(p)).join('');

    // Paginación
    renderizarPaginacion(respuesta);

  } catch (error) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align:center;color:#516651;padding:2rem">
          <i class="bi bi-exclamation-triangle me-2" style="color:var(--rojo-alerta)"></i>
          Error al cargar pacientes: ${error.message}
        </td>
      </tr>`;
  }
}

/**
 * Genera el HTML de una fila de paciente para la tabla.
 * Todos los colores usan la paleta verde/blanco del nuevo diseño.
 */
function renderizarFilaPaciente(p) {
  // Iniciales del nombre para el avatar
  const iniciales = p.nombre_completo
    .split(' ').slice(0, 2).map(n => n[0]).join('').toUpperCase();

  // Badge de estado
  const estadoBadge = p.estado === 'activo'
    ? '<span class="badge badge-activo">Activo</span>'
    : '<span class="badge badge-inactivo">Inactivo</span>';

  // Contador de evaluaciones con color diferenciado
  const evalClass  = p.total_evaluaciones > 0 ? 'con-evals' : 'sin-evals';

  // Ícono de género
  const generoIcono = p.genero === 'masculino' ? 'bi-gender-male'
    : p.genero === 'femenino' ? 'bi-gender-female'
    : 'bi-gender-ambiguous';

  return `
    <tr class="patient-row">
      <!-- Nombre con avatar de iniciales -->
      <td>
        <div class="avatar-pack">
          <div class="avatar-iniciales">${iniciales}</div>
          <div>
            <div class="avatar-nombre">${p.nombre_completo}</div>
            <div class="avatar-fecha">
              <i class="bi bi-calendar3" style="color:var(--verde-primario);font-size:.7rem"></i>
              Ingresó: ${p.fecha_ingreso ? formatearFecha(p.fecha_ingreso) : 'No registrado'}
            </div>
          </div>
        </div>
      </td>

      <!-- Edad y género -->
      <td>
        <div style="font-weight:700;color:#111827;font-size:.9rem">${p.edad} años</div>
        <div class="genero-pill mt-1">
          <i class="bi ${generoIcono}" style="color:var(--verde-primario)"></i>
          ${capitalizarPrimera(p.genero.replace('_', ' '))}
        </div>
      </td>

      <!-- Contacto -->
      <td>
        ${p.telefono
          ? `<div class="contacto-item">
               <i class="bi bi-telephone-fill"></i> ${p.telefono}
             </div>`
          : ''}
        ${p.correo
          ? `<div class="contacto-item mt-1">
               <i class="bi bi-envelope-fill"></i>
               <span style="font-size:.78rem">${p.correo}</span>
             </div>`
          : (!p.telefono
              ? `<span style="color:#516651;font-size:.8rem">Sin contacto</span>`
              : '')}
      </td>

      <!-- Talla y peso inicial -->
      <td>
        <div class="datos-fisicos">${p.talla_metros} m</div>
        <div class="datos-fisicos-sub">
          <i class="bi bi-arrow-right" style="font-size:.65rem"></i>
          ${p.peso_inicial_kg} kg inicial
        </div>
      </td>

      <!-- Evaluaciones -->
      <td style="text-align:center">
        <div class="eval-count ${evalClass}">${p.total_evaluaciones}</div>
      </td>

      <!-- Estado -->
      <td>${estadoBadge}</td>

      <!-- Acciones -->
      <td>
        <div class="acciones-grupo">
          <!-- Ver detalle -->
          <a
            href="patient-detail.html?id=${p.id}"
            class="btn btn-secundario btn-sm"
            title="Ver detalle y evaluaciones"
          >
            <i class="bi bi-eye"></i>
          </a>
          <!-- Nueva evaluación -->
          <a
            href="evaluations.html?patient_id=${p.id}"
            class="btn btn-primario btn-sm"
            title="Nueva evaluación"
          >
            <i class="bi bi-clipboard2-plus"></i>
          </a>
          <!-- Editar -->
          <button
            class="btn btn-secundario btn-sm"
            onclick="abrirModalEditarPaciente(${p.id})"
            title="Editar paciente"
          >
            <i class="bi bi-pencil"></i>
          </button>
          <!-- Desactivar -->
          <button
            class="btn btn-peligro btn-sm"
            onclick="abrirModalEliminar(${p.id}, '${p.nombre_completo.replace(/'/g, "\\'")}')"
            title="Desactivar paciente"
          >
            <i class="bi bi-person-dash"></i>
          </button>
        </div>
      </td>
    </tr>`;
}

/** Renderiza el estado vacío cuando no hay resultados */
function renderizarEstadoVacio(tbody, busqueda) {
  tbody.innerHTML = `
    <tr>
      <td colspan="7">
        <div class="estado-vacio">
          <div class="estado-vacio-icono">
            <i class="bi bi-people" style="color:var(--gris-300)"></i>
          </div>
          <div class="estado-vacio-titulo">
            ${busqueda
              ? `Sin resultados para "${busqueda}"`
              : 'No tienes pacientes registrados'}
          </div>
          <div class="estado-vacio-desc">
            ${busqueda
              ? 'Intenta con otro término de búsqueda o limpia los filtros'
              : 'Registra tu primer paciente para comenzar el seguimiento'}
          </div>
          ${!busqueda
            ? `<button class="btn btn-primario" onclick="abrirModalNuevoPaciente()">
                 <i class="bi bi-person-plus me-2"></i>Registrar primer paciente
               </button>`
            : ''}
        </div>
      </td>
    </tr>`;
}

/** Renderiza los controles de paginación */
function renderizarPaginacion(respuesta) {
  const contenedorPag = document.getElementById('paginacion');
  const infoPag       = document.getElementById('paginacion-info');
  const btnsPag       = document.getElementById('paginacion-botones');

  const inicio = (respuesta.page - 1) * respuesta.per_page + 1;
  const fin    = Math.min(respuesta.page * respuesta.per_page, respuesta.total);

  infoPag.textContent = `Mostrando ${inicio}–${fin} de ${respuesta.total} pacientes`;

  // Botón anterior
  let html = `
    <button class="paginacion-btn" onclick="cargarPacientes(${respuesta.page - 1})"
      ${respuesta.page <= 1 ? 'disabled' : ''}>
      <i class="bi bi-chevron-left"></i>
    </button>`;

  // Botones numéricos con elipsis
  for (let i = 1; i <= respuesta.pages; i++) {
    if (
      i === 1 ||
      i === respuesta.pages ||
      Math.abs(i - respuesta.page) <= 1
    ) {
      html += `
        <button class="paginacion-btn ${i === respuesta.page ? 'activo' : ''}"
          onclick="cargarPacientes(${i})">${i}
        </button>`;
    } else if (Math.abs(i - respuesta.page) === 2) {
      html += `<span style="color:#516651;padding:0 4px;line-height:32px">…</span>`;
    }
  }

  // Botón siguiente
  html += `
    <button class="paginacion-btn" onclick="cargarPacientes(${respuesta.page + 1})"
      ${respuesta.page >= respuesta.pages ? 'disabled' : ''}>
      <i class="bi bi-chevron-right"></i>
    </button>`;

  btnsPag.innerHTML = html;
  contenedorPag.style.display = 'flex';
}

// -----------------------------------------------
// FILTROS Y BÚSQUEDA
// -----------------------------------------------

/** Aplica filtros activos y recarga desde página 1 */
function filtrarPacientes() {
  cargarPacientes(1);
}

/** Limpia todos los filtros y recarga */
function limpiarFiltros() {
  document.getElementById('input-busqueda').value = '';
  document.getElementById('filtro-genero').value  = '';
  document.getElementById('filtro-estado').value  = '';
  cargarPacientes(1);
}

// -----------------------------------------------
// MODAL CREAR / EDITAR PACIENTE
// -----------------------------------------------

/** Abre el modal en modo creación con formulario limpio */
function abrirModalNuevoPaciente() {
  estado.modoEdicion = false;
  document.getElementById('modal-paciente-titulo').innerHTML =
    '<i class="bi bi-person-plus me-2" style="color:var(--verde-primario)"></i>Nuevo Paciente';
  document.getElementById('paciente-id').value = '';
  limpiarFormularioPaciente();
  // Fecha de ingreso por defecto: hoy
  document.getElementById('p-fecha-ingreso').value =
    new Date().toISOString().split('T')[0];
  abrirModal('modal-paciente');
}

/** Carga los datos de un paciente y abre el modal en modo edición */
async function abrirModalEditarPaciente(id) {
  estado.modoEdicion = true;
  document.getElementById('modal-paciente-titulo').innerHTML =
    '<i class="bi bi-pencil me-2" style="color:var(--verde-primario)"></i>Editar Paciente';

  try {
    mostrarCargando();
    const paciente = await api.obtenerPaciente(id);
    ocultarCargando();

    // Rellenar el formulario con los datos del paciente
    document.getElementById('paciente-id').value       = paciente.id;
    document.getElementById('p-nombre').value          = paciente.nombre_completo || '';
    document.getElementById('p-edad').value            = paciente.edad || '';
    document.getElementById('p-genero').value          = paciente.genero || '';
    document.getElementById('p-telefono').value        = paciente.telefono || '';
    document.getElementById('p-correo').value          = paciente.correo || '';
    document.getElementById('p-talla').value           = paciente.talla_metros || '';
    document.getElementById('p-peso').value            = paciente.peso_inicial_kg || '';
    document.getElementById('p-fecha-ingreso').value   = paciente.fecha_ingreso || '';
    document.getElementById('p-fecha-nac').value       = paciente.fecha_nacimiento || '';
    document.getElementById('p-objetivos').value       = paciente.objetivos || '';
    document.getElementById('p-condicion').value       = paciente.condicion_medica || '';
    document.getElementById('p-observaciones').value   = paciente.observaciones || '';

    abrirModal('modal-paciente');

  } catch (error) {
    ocultarCargando();
    mostrarToast('Error al cargar datos del paciente', 'error');
  }
}

/** Guarda el paciente (crea o actualiza según modo) */
async function guardarPaciente() {
  if (!validarFormularioPaciente()) return;

  const id = document.getElementById('paciente-id').value;

  // Recoger todos los valores del formulario
  const datos = {
    nombre_completo:  document.getElementById('p-nombre').value.trim(),
    edad:             parseInt(document.getElementById('p-edad').value),
    genero:           document.getElementById('p-genero').value,
    talla_metros:     parseFloat(document.getElementById('p-talla').value),
    peso_inicial_kg:  parseFloat(document.getElementById('p-peso').value),
    telefono:         document.getElementById('p-telefono').value.trim()   || null,
    correo:           document.getElementById('p-correo').value.trim()     || null,
    fecha_nacimiento: document.getElementById('p-fecha-nac').value         || null,
    fecha_ingreso:    document.getElementById('p-fecha-ingreso').value     || null,
    objetivos:        document.getElementById('p-objetivos').value.trim()  || null,
    condicion_medica: document.getElementById('p-condicion').value.trim()  || null,
    observaciones:    document.getElementById('p-observaciones').value.trim() || null
  };

  const btn = document.getElementById('btn-guardar-paciente');
  btn.disabled = true;
  btn.innerHTML = `
    <span class="spinner-border spinner-border-sm me-2"></span> Guardando...`;

  try {
    if (estado.modoEdicion && id) {
      await api.actualizarPaciente(id, datos);
      mostrarToast('Paciente actualizado correctamente', 'exito');
    } else {
      await api.crearPaciente(datos);
      mostrarToast('Paciente registrado exitosamente', 'exito');
    }
    cerrarModal('modal-paciente');
    cargarPacientes(estado.paginaActual);

  } catch (error) {
    mostrarToast(error.message || 'Error al guardar el paciente', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-check-lg me-1"></i> Guardar Paciente';
  }
}

// -----------------------------------------------
// MODAL DE CONFIRMACIÓN DE ELIMINACIÓN
// -----------------------------------------------

/** Abre el modal de confirmación de desactivación */
function abrirModalEliminar(id, nombre) {
  estado.pacienteIdEliminar = id;
  document.getElementById('nombre-eliminar').textContent = nombre;
  abrirModal('modal-eliminar');
}

/** Ejecuta el soft delete del paciente */
async function confirmarEliminar() {
  if (!estado.pacienteIdEliminar) return;

  const btn = document.getElementById('btn-confirmar-eliminar');
  btn.disabled = true;
  btn.innerHTML = `
    <span class="spinner-border spinner-border-sm me-2"></span> Procesando...`;

  try {
    await api.eliminarPaciente(estado.pacienteIdEliminar);
    mostrarToast('Paciente desactivado correctamente', 'exito');
    cerrarModal('modal-eliminar');
    cargarPacientes(estado.paginaActual);
  } catch (error) {
    mostrarToast(error.message || 'Error al desactivar el paciente', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-person-dash me-1"></i> Desactivar paciente';
    estado.pacienteIdEliminar = null;
  }
}

// -----------------------------------------------
// VALIDACIÓN DEL FORMULARIO
// -----------------------------------------------

/**
 * Valida los campos requeridos del formulario de paciente.
 * Retorna true si todo es válido.
 */
function validarFormularioPaciente() {
  let valido = true;

  // Limpiar errores previos
  document.querySelectorAll('.campo-error').forEach(e => e.style.display = 'none');
  document.querySelectorAll('.form-control').forEach(c => c.classList.remove('invalido'));

  const nombre = document.getElementById('p-nombre').value.trim();
  if (!nombre || nombre.length < 3) {
    mostrarErrorCampo('err-p-nombre', 'p-nombre');
    valido = false;
  }

  const edad = parseInt(document.getElementById('p-edad').value);
  if (!edad || edad < 5 || edad > 120) {
    mostrarErrorCampo('err-p-edad', 'p-edad');
    valido = false;
  }

  if (!document.getElementById('p-genero').value) {
    mostrarErrorCampo('err-p-genero', 'p-genero');
    valido = false;
  }

  const talla = parseFloat(document.getElementById('p-talla').value);
  if (!talla || talla < 0.5 || talla > 2.5) {
    mostrarErrorCampo('err-p-talla', 'p-talla');
    valido = false;
  }

  const peso = parseFloat(document.getElementById('p-peso').value);
  if (!peso || peso < 10 || peso > 500) {
    mostrarErrorCampo('err-p-peso', 'p-peso');
    valido = false;
  }

  return valido;
}

/** Marca un campo como inválido y muestra su mensaje de error */
function mostrarErrorCampo(errorId, campoId) {
  const errorEl = document.getElementById(errorId);
  const campoEl = document.getElementById(campoId);
  if (errorEl) errorEl.style.display = 'block';
  if (campoEl) campoEl.classList.add('invalido');
}

/** Limpia todos los campos del formulario */
function limpiarFormularioPaciente() {
  [
    'p-nombre', 'p-edad', 'p-genero', 'p-fecha-nac', 'p-telefono',
    'p-correo', 'p-talla', 'p-peso', 'p-fecha-ingreso',
    'p-objetivos', 'p-condicion', 'p-observaciones'
  ].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  // Limpiar errores
  document.querySelectorAll('#form-paciente .campo-error')
    .forEach(e => e.style.display = 'none');
  document.querySelectorAll('#form-paciente .form-control')
    .forEach(c => c.classList.remove('invalido'));
}

// -----------------------------------------------
// FUNCIONES DE MODAL
// -----------------------------------------------

/** Abre un modal por su ID */
function abrirModal(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.add('activo');
    document.body.style.overflow = 'hidden';
  }
}

/** Cierra un modal por su ID */
function cerrarModal(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.remove('activo');
    document.body.style.overflow = '';
  }
}

/** Cierra modales al hacer clic en el overlay */
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', function (e) {
    if (e.target === this) cerrarModal(this.id);
  });
});

// -----------------------------------------------
// SIDEBAR MÓVIL Y UTILIDADES
// -----------------------------------------------

/** Capitaliza la primera letra de un texto */
function capitalizarPrimera(texto) {
  return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : '';
}

/** Abre o cierra el sidebar en pantallas pequeñas */
function toggleSidebar() {
  const sidebar  = document.getElementById('sidebar');
  const overlay  = document.getElementById('sidebar-overlay');
  const abierto  = sidebar.classList.toggle('abierto');
  overlay.style.display = abierto ? 'block' : 'none';
}

/**
 * Función debounce: retrasa la búsqueda mientras el usuario escribe.
 * Evita llamadas excesivas a la API.
 */
function debounce(fn, delay) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

// Vincular búsqueda con debounce de 400ms al input
const inputBusqueda = document.getElementById('input-busqueda');
if (inputBusqueda) {
  inputBusqueda.addEventListener('input', debounce(filtrarPacientes, 400));
}