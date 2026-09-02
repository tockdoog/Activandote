// frontend/js/consent.js
// Lógica del módulo de Habeas Data y Consentimiento Informado: carga del
// documento vigente, validación de checkboxes, captura de firma en canvas,
// validación de identidad, envío de la evidencia al backend y descarga
// del PDF de evidencia legal (para responder ante un reclamo del paciente).

// -----------------------------------------------
// Verificación de sesión activa
// -----------------------------------------------
(function verificarAuth() {
  if (!api.estaAutenticado()) {
    window.location.href = 'index.html';
  }
})();

// -----------------------------------------------
// ESTADO DEL MÓDULO
// -----------------------------------------------
const paramsUrl = new URLSearchParams(window.location.search);
const patientId = paramsUrl.get('patient_id');
const destinoRetorno = paramsUrl.get('return') || 'evaluations';

let pacienteActual = null;
let documentoVigente = null;
let dibujando = false;
let firmaTieneTrazo = false;
let ctx = null;

// Referencias reutilizables del canvas de firma, para poder redimensionarlo
// cada vez que el paso 2 se muestra (ver justificación en ajustarTamanoCanvas)
let canvasFirmaEl = null;
let eventosFirmaVinculados = false;

// ID del consentimiento recién registrado — se usa para descargar su
// PDF de evidencia desde el botón del panel de éxito (paso 4)
let consentimientoIdActual = null;

// -----------------------------------------------
// INICIALIZACIÓN
// -----------------------------------------------
document.addEventListener('DOMContentLoaded', async function () {
  if (!patientId) {
    mostrarToast('No se especificó un paciente', 'error');
    setTimeout(() => window.location.href = 'patients.html', 1200);
    return;
  }

  document.getElementById('link-volver').href = `patient-detail.html?id=${patientId}`;
  document.getElementById('btn-ir-evaluacion').onclick = () => irADestinoRetorno();

  // Solo se vinculan los eventos de dibujo aquí (una sola vez).
  // El tamaño real del canvas se calcula más adelante, cuando el paso 2
  // sea visible en pantalla (ver irAPaso).
  vincularEventosFirma();

  try {
    // Cargar en paralelo: datos del paciente, documento vigente y estado de consentimiento
    const [paciente, documento, estado] = await Promise.all([
      api.obtenerPaciente(patientId),
      api.obtenerDocumentoVigente(),
      api.obtenerEstadoConsentimiento(patientId)
    ]);

    pacienteActual = paciente;
    documentoVigente = documento;

    document.getElementById('topbar-nombre-paciente').textContent = paciente.nombre_completo;
    document.getElementById('contenido-documento-completo').textContent = documento.contenido;

    // Si ya tiene un consentimiento válido y vigente, no repetir el proceso
    if (estado.tiene_consentimiento_valido) {
      mostrarToast('Este paciente ya tiene un consentimiento vigente registrado', 'info');
      setTimeout(() => irADestinoRetorno(), 900);
      return;
    }

    // Determinar el primer paso: si falta el número de documento, iniciar en el paso 0
    if (!estado.numero_documento_registrado) {
      irAPaso(0);
    } else {
      irAPaso(1);
    }

  } catch (error) {
    mostrarToast('Error al cargar la información del paciente', 'error');
    console.error(error);
  }
});

// -----------------------------------------------
// NAVEGACIÓN ENTRE PASOS
// -----------------------------------------------

/** Muestra el panel del paso indicado y oculta los demás */
function irAPaso(numeroPaso) {
  [0, 1, 2, 3, 4].forEach(p => {
    const panel = document.getElementById(`panel-paso-${p}`);
    if (panel) panel.style.display = p === numeroPaso ? 'block' : 'none';
  });

  // Actualizar indicador visual de pasos
  document.querySelectorAll('.consent-paso').forEach(el => {
    const paso = parseInt(el.dataset.paso);
    el.classList.remove('activo', 'completado');
    if (paso === numeroPaso) el.classList.add('activo');
    else if (paso < numeroPaso) el.classList.add('completado');
  });

  // ── CORRECCIÓN DEL BUG DE FIRMA ────────────────────────────────────
  // El canvas de firma vive dentro del panel del paso 2. Mientras ese
  // panel tiene display:none, su ancho/alto medido en pantalla es 0,
  // así que si el canvas se dimensiona en ese momento queda con un
  // lienzo de 0x0 píxeles y no se puede dibujar nada en él (aunque los
  // eventos de mouse/touch sí se disparan).
  //
  // Por eso el tamaño del canvas se recalcula justo aquí, cada vez que
  // se entra al paso 2, después de que el navegador ya aplicó
  // display:block (con requestAnimationFrame para asegurar el reflow).
  if (numeroPaso === 2) {
    requestAnimationFrame(ajustarTamanoCanvas);
  }
}

/** Redirige a la página de destino tras completar (o saltar) el consentimiento */
function irADestinoRetorno() {
  if (destinoRetorno === 'evaluations') {
    window.location.href = `evaluations.html?patient_id=${patientId}`;
  } else {
    window.location.href = `patient-detail.html?id=${patientId}`;
  }
}

// -----------------------------------------------
// PASO 0: REGISTRO DEL NÚMERO DE DOCUMENTO
// -----------------------------------------------

/** Guarda el número de documento del paciente antes de continuar */
async function guardarNumeroDocumento() {
  const valor = document.getElementById('input-numero-documento').value.trim();

  if (!valor || valor.length < 4) {
    mostrarToast('Ingrese un número de documento válido', 'error');
    return;
  }

  const btn = document.getElementById('btn-guardar-doc');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Guardando...';

  try {
    await api.actualizarPaciente(patientId, { numero_documento: valor });
    mostrarToast('Número de documento registrado', 'exito');
    irAPaso(1);
  } catch (error) {
    mostrarToast(error.message || 'Error al guardar el número de documento', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Guardar y continuar <i class="bi bi-arrow-right ms-1"></i>';
  }
}

// -----------------------------------------------
// PASO 1: CHECKBOXES DE AUTORIZACIÓN
// -----------------------------------------------

/** Habilita/deshabilita los botones de avance según el estado de los checkboxes */
function actualizarEstadoChecks() {
  // Paso 1: los 4 checkboxes de autorización
  const ids1 = ['chk-datos-personales', 'chk-datos-sensibles', 'chk-consentimiento-informado', 'chk-profesional-confirma'];
  const todosMarcados1 = ids1.every(id => document.getElementById(id)?.checked);
  const btn1 = document.getElementById('btn-continuar-paso1');
  if (btn1) btn1.disabled = !todosMarcados1;

  // Efecto visual de tarjeta marcada
  const mapaItems = {
    'chk-datos-personales': 'chk-item-1',
    'chk-datos-sensibles': 'chk-item-2',
    'chk-consentimiento-informado': 'chk-item-3',
    'chk-profesional-confirma': 'chk-item-4',
    'chk-confirmacion-final': 'chk-item-final'
  };
  Object.entries(mapaItems).forEach(([chkId, itemId]) => {
    const chk = document.getElementById(chkId);
    const item = document.getElementById(itemId);
    if (chk && item) item.classList.toggle('marcado', chk.checked);
  });

  // Paso 3: confirmación final
  const btnFinal = document.getElementById('btn-confirmar-final');
  if (btnFinal) {
    btnFinal.disabled = !document.getElementById('chk-confirmacion-final')?.checked;
  }
}

/** Abre el modal con el contenido completo del documento vigente */
function abrirModalInformacion() {
  document.getElementById('modal-informacion').classList.add('activo');
}

function cerrarModalInformacion() {
  document.getElementById('modal-informacion').classList.remove('activo');
}

// -----------------------------------------------
// PASO 2: FIRMA EN CANVAS
// -----------------------------------------------

/**
 * Vincula los eventos de mouse y táctiles del canvas de firma.
 * Se ejecuta UNA sola vez (en DOMContentLoaded), sin depender de que el
 * panel esté visible: solo registra los listeners, no mide tamaños.
 */
function vincularEventosFirma() {
  if (eventosFirmaVinculados) return;

  canvasFirmaEl = document.getElementById('canvas-firma');
  if (!canvasFirmaEl) return;

  const obtenerPosicion = (evento) => {
    const rect = canvasFirmaEl.getBoundingClientRect();
    const punto = evento.touches ? evento.touches[0] : evento;
    return { x: punto.clientX - rect.left, y: punto.clientY - rect.top };
  };

  const iniciarTrazo = (evento) => {
    evento.preventDefault();
    dibujando = true;
    const pos = obtenerPosicion(evento);
    ctx.beginPath();
    ctx.moveTo(pos.x, pos.y);
    document.getElementById('firma-placeholder').style.display = 'none';
  };

  const dibujarTrazo = (evento) => {
    if (!dibujando) return;
    evento.preventDefault();
    const pos = obtenerPosicion(evento);
    ctx.lineTo(pos.x, pos.y);
    ctx.stroke();
    firmaTieneTrazo = true;
    validarPaso2();
  };

  const terminarTrazo = () => { dibujando = false; };

  // Eventos de mouse
  canvasFirmaEl.addEventListener('mousedown', iniciarTrazo);
  canvasFirmaEl.addEventListener('mousemove', dibujarTrazo);
  window.addEventListener('mouseup', terminarTrazo);

  // Eventos táctiles
  canvasFirmaEl.addEventListener('touchstart', iniciarTrazo);
  canvasFirmaEl.addEventListener('touchmove', dibujarTrazo);
  canvasFirmaEl.addEventListener('touchend', terminarTrazo);

  // Reajustar el canvas si la ventana cambia de tamaño (ej: rotar el
  // dispositivo) mientras el paso 2 está visible
  window.addEventListener('resize', () => {
    const panel2 = document.getElementById('panel-paso-2');
    if (panel2 && panel2.style.display !== 'none') {
      ajustarTamanoCanvas();
    }
  });

  // Validar también al escribir los últimos 4 dígitos
  document.getElementById('input-ultimos-digitos').addEventListener('input', validarPaso2);

  eventosFirmaVinculados = true;
}

/**
 * Ajusta la resolución interna del canvas al tamaño real que ocupa en
 * pantalla. Debe llamarse SIEMPRE que el panel del paso 2 pase a estar
 * visible, nunca mientras está oculto (ver comentario en irAPaso).
 * Redimensionar el canvas borra su contenido, por eso también se
 * reinicia el estado de la firma.
 */
function ajustarTamanoCanvas() {
  if (!canvasFirmaEl) return;

  const rect = canvasFirmaEl.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) return; // aún no visible, no medir

  canvasFirmaEl.width = rect.width;
  canvasFirmaEl.height = rect.height;

  ctx = canvasFirmaEl.getContext('2d');
  ctx.strokeStyle = '#111827';
  ctx.lineWidth = 2.4;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  // Al redimensionar se pierde cualquier trazo previo dibujado en el bitmap
  firmaTieneTrazo = false;
  const placeholder = document.getElementById('firma-placeholder');
  if (placeholder) placeholder.style.display = 'flex';
  validarPaso2();
}

/** Limpia el canvas de firma y reinicia su estado */
function limpiarFirma() {
  if (!canvasFirmaEl || !ctx) return;
  ctx.clearRect(0, 0, canvasFirmaEl.width, canvasFirmaEl.height);
  firmaTieneTrazo = false;
  document.getElementById('firma-placeholder').style.display = 'flex';
  validarPaso2();
}

/** Habilita el botón de continuar del paso 2 solo si hay firma y 4 dígitos */
function validarPaso2() {
  const digitos = document.getElementById('input-ultimos-digitos').value;
  const btn = document.getElementById('btn-continuar-paso2');
  if (btn) btn.disabled = !(firmaTieneTrazo && digitos.length === 4);
}

// -----------------------------------------------
// PASO 3/4: ENVÍO DEL CONSENTIMIENTO Y EVIDENCIA EN PDF
// -----------------------------------------------

/** Envía la evidencia completa del consentimiento al backend */
async function confirmarConsentimiento() {
  const firmaBase64 = canvasFirmaEl.toDataURL('image/png');

  const datos = {
    acepta_datos_personales: document.getElementById('chk-datos-personales').checked,
    acepta_datos_sensibles: document.getElementById('chk-datos-sensibles').checked,
    acepta_consentimiento_informado: document.getElementById('chk-consentimiento-informado').checked,
    profesional_confirma: document.getElementById('chk-profesional-confirma').checked,
    confirmacion_final: document.getElementById('chk-confirmacion-final').checked,
    firma_base64: firmaBase64,
    ultimos_4_digitos: document.getElementById('input-ultimos-digitos').value
  };

  const btn = document.getElementById('btn-confirmar-final');
  document.getElementById('btn-confirmar-texto').style.display = 'none';
  document.getElementById('btn-confirmar-cargando').style.display = 'inline';
  btn.disabled = true;

  try {
    const respuesta = await api.registrarConsentimiento(patientId, datos);

    // Se guarda el ID para poder generar el PDF de evidencia desde el
    // botón del panel de éxito (paso 4)
    consentimientoIdActual = respuesta.id;

    document.getElementById('hash-evidencia-final').textContent = `Hash de evidencia: ${respuesta.hash_evidencia}`;

    // Vincular el botón de descarga con el consentimiento recién creado
    const btnDescargar = document.getElementById('btn-descargar-evidencia');
    if (btnDescargar) {
      btnDescargar.onclick = () => descargarEvidenciaPDF(btnDescargar);
    }

    irAPaso(4);
  } catch (error) {
    mostrarToast(error.message || 'Error al registrar el consentimiento', 'error');
    document.getElementById('btn-confirmar-texto').style.display = 'inline';
    document.getElementById('btn-confirmar-cargando').style.display = 'none';
    btn.disabled = false;
  }
}

/**
 * Descarga el PDF de evidencia legal del consentimiento recién registrado.
 * El documento incluye las autorizaciones aceptadas, la confirmación del
 * profesional, la firma capturada, la validación de identidad y el hash
 * de integridad — sirve como respaldo ante un eventual reclamo del paciente.
 */
async function descargarEvidenciaPDF(boton) {
  if (!consentimientoIdActual || !pacienteActual) {
    mostrarToast('No hay una evidencia disponible para descargar', 'error');
    return;
  }

  const textoOriginal = boton.innerHTML;
  boton.disabled = true;
  boton.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Generando...';

  try {
    await api.exportarEvidenciaConsentimientoPDF(consentimientoIdActual, pacienteActual.nombre_completo);
    mostrarToast('PDF de evidencia generado correctamente', 'exito');
  } catch (error) {
    mostrarToast(error.message || 'Error al generar el PDF de evidencia', 'error');
  } finally {
    boton.disabled = false;
    boton.innerHTML = textoOriginal;
  }
}