// Nucleo (API, DIVISIONES_CSI, state, templateCatalog, fmt/esc/api, bus) movido a core.js.
// core.js DEBE cargarse ANTES que app.js en index.html / index_preview.html.

// --- INIT ---
document.addEventListener("DOMContentLoaded", () => {
  loadObras();
  loadTemplateCatalog();
  document.getElementById("btn-nueva-obra")?.addEventListener("click", () => openModalObra());
  initExportMenu();
  document.getElementById("btn-actualizar")?.addEventListener("click", actualizarObra);
  document.getElementById("btn-toggle-typemark")?.addEventListener("click", toggleTypeMark);
  document.getElementById("btn-toggle-auditoria")?.addEventListener("click", toggleAuditoria);
  document.getElementById("btn-toggle-solomo")?.addEventListener("click", toggleSoloMO);
  document.getElementById("btn-hide-sidebar")?.addEventListener("click", () => setSidebarCollapsed(true));
  document.getElementById("btn-show-sidebar")?.addEventListener("click", () => setSidebarCollapsed(false));
  setSidebarCollapsed(localStorage.getItem("estimastruct.sidebarCollapsed") === "1");
  document.getElementById("btn-modo")?.addEventListener("click", toggleModo);
  initDevMenu();
  initModalScriptOut();
  initModalAbout();
  initModalCsvPick();
  initModalTemplateVersion();
  initModalBases();
  initSessionLogModal();
  initModalUpdater();
  initColorPicker();
  initTableScaleControls();
  applyModoUI();
  loadUnidades();
  initModalObra();
  initModalRename();
  initModalDelete();
  initPanelBottom();
  initPanelTabs();
  initVinetas();
  initSobrecostoPill();
  initDisenoView();
  initEtabsView();
  initAceroView();
  initConexionView();
  initDisenoImportEtabs();
  initModuloDropdown();
  initCronograma();
  initExportPdf();
  initExportPdfBanco();
});

// --- OBRAS ---
async function loadObras() {
  const list = document.getElementById("obras-list");
  if (list && !state.presupuestos.length && !state.activeId) {
    list.innerHTML = `<div class="empty-state" style="padding:20px;"><p>Cargando proyectos...</p><small>Conectando con el backend</small></div>`;
  }

  try {
    state.presupuestos = await api("GET", "/presupuestos");
    loadObrasAttempts = 0;
    if (loadObrasRetryHandle) {
      clearTimeout(loadObrasRetryHandle);
      loadObrasRetryHandle = null;
    }
    renderSidebar();
    if (state.activeId) {
      const still = state.presupuestos.find(p => p.id === state.activeId);
      if (still) loadObra(state.activeId);
      else clearMain();
    } else {
      const first = state.presupuestos.find(p => !p.es_template);
      if (first) loadObra(first.id);
      else clearMain();
    }
  } catch (err) {
    loadObrasAttempts += 1;
    if (list) {
      list.innerHTML = `<div class="empty-state" style="padding:20px;"><p>No se pudieron cargar proyectos</p><small>${esc(err.message || "Error de conexión")}</small></div>`;
    }
    if (loadObrasAttempts < 10) {
      loadObrasRetryHandle = setTimeout(() => loadObras(), 1500);
    }
    return null;
  }
}

function renderObraDropdown(proyectos) {
  const dd = document.getElementById("obra-dropdown");
  if (!dd) return;
  if (!proyectos.length) {
    dd.innerHTML = `<option value="">Sin obras</option>`;
    return;
  }
  dd.innerHTML = proyectos.map(p =>
    `<option value="${p.id}" ${p.id === state.activeId ? "selected" : ""}>${esc(p.nombre)}</option>`
  ).join("");
  if (state.activeId) dd.value = state.activeId;
  // onchange (propiedad, no addEventListener) → no duplica handlers entre renders
  dd.onchange = () => { if (dd.value) loadObra(dd.value); };
}

function renderSidebar() {
  const list = document.getElementById("obras-list");
  const proyectos = state.presupuestos.filter(p => !p.es_template);
  renderObraDropdown(proyectos);
  if (!proyectos.length) {
    list.innerHTML = `<div class="empty-state" style="padding:20px;"><p>Sin obras</p><small>Crea una nueva</small></div>`;
    return;
  }
  // El dropdown lista todas; la lista muestra solo la obra ACTIVA (con sus opciones renombrar/duplicar/borrar)
  const activos = proyectos.filter(p => p.id === state.activeId);
  if (!activos.length) { list.innerHTML = ""; return; }
  list.innerHTML = activos.map(p => {
    const isProtected = (p.nombre || "").trim().toUpperCase() === "OBRA #1 TEST";
    const delBtn = isProtected
      ? `<span class="obra-protected" title="Obra protegida">🔒</span>`
      : `<button class="btn-del-obra" data-id="${p.id}" data-nombre="${esc(p.nombre)}" title="Borrar obra">✕</button>`;
    const dupBtn = `<button class="btn-dup-obra" data-id="${p.id}" data-nombre="${esc(p.nombre)}" title="Duplicar obra">⎘</button>`;
    return `
    <div class="obra-item ${p.id === state.activeId ? "active" : ""}" data-id="${p.id}">
      <div class="obra-name-wrap">
        <span class="obra-name">${esc(p.nombre)}</span>
        <button class="btn-rename-obra" data-id="${p.id}" data-nombre="${esc(p.nombre)}" title="Renombrar">✎</button>
        ${dupBtn}
        ${delBtn}
      </div>
      <div class="obra-total">${p.moneda} ${fmt(p.total_con_indirectos)}</div>
    </div>`;
  }).join("");

  list.querySelectorAll(".obra-item").forEach(el =>
    el.addEventListener("click", (e) => {
      if (e.target.classList.contains("btn-rename-obra")) return;
      if (e.target.classList.contains("btn-del-obra")) return;
      if (e.target.classList.contains("btn-dup-obra")) return;
      loadObra(el.dataset.id);
    })
  );
  list.querySelectorAll(".btn-del-obra").forEach(btn =>
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      borrarObra(btn.dataset.id, btn.dataset.nombre);
    })
  );
  list.querySelectorAll(".btn-dup-obra").forEach(btn =>
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const nombre = prompt(`Nombre para la copia de "${btn.dataset.nombre}":`, `${btn.dataset.nombre} (copia)`);
      if (!nombre) return;
      try {
        const res = await api("POST", `/presupuestos/${btn.dataset.id}/duplicar`, { nuevo_nombre: nombre.trim() });
        await loadObras();
        if (res.id) loadObra(res.id);
      } catch (err) {
        alert("Error: " + (err.message || err));
      }
    })
  );
  list.querySelectorAll(".btn-rename-obra").forEach(btn =>
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openModalRename(btn.dataset.id, btn.dataset.nombre);
    })
  );
}

async function loadObra(id) {
  state.activeId = id;
  state.selectedPartida = null;
  document.getElementById("panel-bottom").classList.add("hidden");
  document.getElementById("export-menu-wrap").classList.remove("hidden");
  document.getElementById("btn-cronograma")?.classList.remove("hidden");
  document.getElementById("btn-actualizar").classList.remove("hidden");
  document.getElementById("btn-modo").classList.remove("hidden");

  const data = await api("GET", `/presupuestos/${id}`);
  state.activeData = data;
  updateTotalesHeader(data);
  updateTemplateVersionBadge(data);
  renderSidebar();
  renderTable(data);
  updateUnidadesSelect(data);
  document.getElementById("recursos-bar").classList.remove("hidden");
  document.getElementById("sel-modulo")?.classList.remove("hidden");
  applyModoUI(); // re-aplica visibilidad según modo
  const pill = document.getElementById("sobrecosto-pill");
  const sc = data.config?.sobrecosto ?? 20;
  document.getElementById("sobrecosto-val").textContent = fmt(sc, 1) + "%";
  document.getElementById("sobrecosto-input").value = sc;
  if (state.modo === "desarrollador") pill.classList.remove("hidden");
  else pill.classList.add("hidden");
}

// Sumas globales en la barra de recursos: Σ Mano de Obra, Σ Insumos, Σ Total.
// Σ MO = Σ(cantidad × costo_mo), Σ Ins = Σ(cantidad × (costo_ma + unitario_matriz))
// — insumos = MATERIAL + resto de non-MO (SUBCONTRATO/HERRAMIENTA/EQUIPO/FLETE/DISEÑO),
// igual que la columna INSUMOS de la tabla (ver tabla-render.js). Recalcula con cada
// updateTotalesHeader (carga obra, editar cantidad, cambiar modo).
function renderRecursosSums(data) {
  const box = document.getElementById("recursos-sums");
  if (!box) return;
  let sumMo = 0, sumIns = 0;
  for (const cap of (data.capitulos || [])) {
    for (const p of (cap.partidas || [])) {
      const q = parseFloat(p.cantidad) || 0;
      sumMo  += q * (parseFloat(p.costo_mo) || 0);
      sumIns += q * ((parseFloat(p.costo_ma) || 0) + (parseFloat(p.unitario_matriz) || 0));
    }
  }
  const total = data.total_con_indirectos ?? data.costo_directo ?? 0;
  const m = data.moneda || "";
  box.innerHTML =
    `<span class="sum-mo">Mano de Obra:<b>${m} ${fmt(sumMo)}</b></span>` +
    `<span class="sum-ins">Insumos:<b>${m} ${fmt(sumIns)}</b></span>` +
    `<span class="sum-tot">Total:<b>${m} ${fmt(total)}</b></span>`;
}

function updateTotalesHeader(data) {
  document.querySelector(".obra-titulo").textContent = data.nombre;
  renderRecursosSums(data);
  const isDev = state.modo === "desarrollador";
  // Costo Directo del front = Total general de la hoja global de insumos:
  // Materiales + Mano de obra, sin sobrecosto.
  const total = data.total_con_indirectos ?? data.costo_directo ?? 0;
  document.querySelector(".totales").innerHTML = isDev
    ? `
      <span>Costo Directo: <b>${data.moneda} ${fmt(data.costo_directo)}</b></span>
      <span>Sobrecosto: <b>${data.moneda} ${fmt(Math.max(0, total - (data.costo_directo || 0)))}</b></span>
      <span>Total: <b>${data.moneda} ${fmt(total)}</b></span>
    `
    : `<span>Total: <b>${data.moneda} ${fmt(total)}</b></span>`;
}

function updateTemplateVersionBadge(data) {
  const badge = document.getElementById("template-version-badge");
  badge.style.display = "none";   // oculto por requerimiento (no mostrar version BD en header)
  return;
  if (data.config?.template_version) {
    const version = data.config.template_version;
    const versionText = version === "v1.0"
      ? "V1.0 Original"
      : version === "v1.1"
        ? "V1.1 Legacy"
        : "V1.2 Vigente";
    badge.textContent = `[DB: ${versionText}]`;
    badge.style.display = "inline";
    badge.style.marginLeft = "8px";
    badge.style.fontSize = "12px";
    badge.style.color = "var(--text-dim)";
  } else {
    badge.style.display = "none";
  }
}

async function refreshTotals() {
  const data = await api("GET", `/presupuestos/${state.activeId}`);
  state.activeData = data;
  updateTotalesHeader(data);
  renderSidebar();
}

function clearMain() {
  document.getElementById("table-area").innerHTML =
    `<div class="empty-state"><p>Crea una nueva obra para comenzar</p></div>`;
  document.querySelector(".obra-titulo").textContent = "— Sin obra activa —";
  document.querySelector(".totales").innerHTML = "";
  document.getElementById("export-menu-wrap").classList.add("hidden");
  document.getElementById("btn-cronograma")?.classList.add("hidden");
  document.getElementById("btn-actualizar").classList.add("hidden");
  document.getElementById("btn-modo").classList.add("hidden");
  document.getElementById("recursos-bar").classList.add("hidden");
  const _selM = document.getElementById("sel-modulo");
  if (_selM) { _selM.classList.add("hidden"); _selM.value = ""; }
  document.getElementById("sobrecosto-pill").classList.add("hidden");
  document.getElementById("bases-drawer").classList.add("hidden");
  document.getElementById("content-wrapper").classList.remove("hidden");
  updateBasesToggleLabel(false);
}

// --- EXPORT ---
function exportarObra() {
  if (!state.activeId) return;
  window.open(`${API}/presupuestos/${state.activeId}/export`, "_blank");
}
function exportarBaseDatos() {
  if (!state.activeId) return;
  window.open(`${API}/presupuestos/${state.activeId}/export-db`, "_blank");
}
function exportarInsumosNecesarios() {
  if (!state.activeId) return;
  window.open(`${API}/presupuestos/${state.activeId}/export-insumos`, "_blank");
}
function exportarReporteAuditoria() {
  if (!state.activeId) return;
  window.open(`${API}/presupuestos/${state.activeId}/audit-report`, "_blank");
}
function initExportMenu() {
  const btn = document.getElementById("btn-exportar");
  const menu = document.getElementById("export-menu");
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    menu.classList.toggle("hidden");
  });
  document.addEventListener("click", (e) => {
    if (!document.getElementById("export-menu-wrap").contains(e.target)) {
      menu.classList.add("hidden");
    }
  });
  menu.querySelectorAll(".export-menu-item").forEach(it => {
    it.addEventListener("click", () => {
      menu.classList.add("hidden");
      const kind = it.dataset.kind;
      if (kind === "presupuesto") exportarObra();
      else if (kind === "insumos") exportarInsumosNecesarios();
      else if (kind === "audit") exportarReporteAuditoria();
      else if (kind === "db") exportarBaseDatos();
      else if (kind === "cronograma-xlsx") exportarCronograma();
      else if (kind === "pdf-membrete") openExportPdf();
      else if (kind === "pdf-banco") openExportPdfBanco();
      else if (kind === "publish-portal") publicarAPortal();
      else if (kind === "sync-precios") sincronizarPrecios();
    });
  });
}

// --- EXPORT PDF CON MEMBRETE ---
const PDF_SUBTITULO = {
  presupuesto: "ESTIMACIÓN DE OBRA POR ACTIVIDAD",
  cronograma:  "CRONOGRAMA DE EJECUCIÓN",
  insumos:     "INSUMOS NECESARIOS POR ACTIVIDAD",
  db:          "BASE DE DATOS DE ACTIVIDADES",
  audit:       "REPORTE DE AUDITORÍA",
};

function _codInterno(nombre) {
  const m = (nombre || "").match(/CC\s*-?\s*(\d+)/i);
  return m ? `CC-${new Date().getFullYear()}-${m[1]}` : "";
}

function openExportPdf() {
  if (!state.activeId) { alert("Abrí una obra primero."); return; }
  const d = state.activeData || {};
  const nombre = d.nombre || "";
  const set = (id, v) => { const e = document.getElementById(id); if (e) e.value = v; };
  document.getElementById("epdf-report").value = "presupuesto";
  set("epdf-subtitulo", PDF_SUBTITULO.presupuesto);
  set("epdf-proyecto", nombre);
  set("epdf-codnom", nombre);
  set("epdf-cliente", d.cliente || "");
  set("epdf-rtncli", "");
  set("epdf-ubic", "");
  const hoy = new Date();
  set("epdf-fecha", `${hoy.getDate()}/${hoy.getMonth() + 1}/${hoy.getFullYear()}`);
  set("epdf-codint", _codInterno(nombre));
  document.getElementById("modal-export-pdf").classList.remove("hidden");
}

function _pdfParams() {
  const v = (id) => (document.getElementById(id)?.value || "").trim();
  return new URLSearchParams({
    report: v("epdf-report") || "presupuesto",
    subtitulo: v("epdf-subtitulo"),
    proyecto: v("epdf-proyecto"),
    codigo_nombre: v("epdf-codnom"),
    cliente: v("epdf-cliente"),
    rtn_cliente: v("epdf-rtncli"),
    ubicacion: v("epdf-ubic"),
    fecha: v("epdf-fecha"),
    codigo_interno: v("epdf-codint"),
  });
}

function generarPdf() {
  if (!state.activeId) return;
  window.open(`${API}/presupuestos/${state.activeId}/export-pdf?${_pdfParams().toString()}`, "_blank");
  document.getElementById("modal-export-pdf").classList.add("hidden");
}

// Vista previa HTML (WYSIWYG, márgenes editables) — abre la página de preview.
function previewPdfHtml() {
  if (!state.activeId) return;
  window.open(`${API}/presupuestos/${state.activeId}/preview-pdf?${_pdfParams().toString()}`, "_blank");
  document.getElementById("modal-export-pdf").classList.add("hidden");
}

function initExportPdf() {
  const rep = document.getElementById("epdf-report");
  if (rep) rep.addEventListener("change", (e) => {
    const s = document.getElementById("epdf-subtitulo");
    if (s) s.value = PDF_SUBTITULO[e.target.value] || "";
  });
  document.getElementById("epdf-cancel")?.addEventListener("click", () =>
    document.getElementById("modal-export-pdf").classList.add("hidden"));
  document.getElementById("epdf-gen")?.addEventListener("click", generarPdf);
  document.getElementById("epdf-preview")?.addEventListener("click", previewPdfHtml);
  const modal = document.getElementById("modal-export-pdf");
  if (modal) modal.addEventListener("click", (e) => {
    if (e.target.id === "modal-export-pdf") e.target.classList.add("hidden");
  });
}

// --- EXPORT PDF PARA BANCO (presupuesto + Gantt prorrateados a valor_banco) ---
function _epdfbActualizarPct() {
  const d = state.activeData || {};
  const costoDirecto = Number(d.costo_directo || 0);
  const valor = Number(document.getElementById("epdfb-valor")?.value || 0);
  const out = document.getElementById("epdfb-pct");
  if (!out) return;
  if (!(costoDirecto > 0) || !(valor > 0)) {
    out.textContent = "";
    return;
  }
  const pct = (valor / costoDirecto - 1) * 100;
  if (pct < 0) {
    out.textContent = "⚠ Valor DEBAJO del costo directo real del presupuesto";
    out.style.color = "#c0392b";
    out.style.fontWeight = "700";
  } else {
    out.textContent = "";
    out.style.color = "";
    out.style.fontWeight = "";
  }
}

async function openExportPdfBanco() {
  if (!state.activeId) { alert("Abrí una obra primero."); return; }
  const d = state.activeData || {};
  const nombre = d.nombre || "";
  const set = (id, v) => { const e = document.getElementById(id); if (e) e.value = v; };
  set("epdfb-valor", "");
  set("epdfb-proyecto", nombre);
  set("epdfb-codnom", nombre);
  set("epdfb-cliente", d.cliente || "");
  set("epdfb-rtncli", "");
  set("epdfb-ubic", "");
  const hoy = new Date();
  set("epdfb-fecha", `${hoy.getDate()}/${hoy.getMonth() + 1}/${hoy.getFullYear()}`);
  set("epdfb-codint", _codInterno(nombre));
  document.getElementById("modal-export-pdf-banco").classList.remove("hidden");
  // Autopopular con lo último ingresado para esta obra (persistente):
  // valor + RTN + ubicación + cliente + proyecto + código interno.
  try {
    const res = await api("GET", `/presupuestos/${state.activeId}/valor-banco`);
    if (res) {
      if (res.valor_banco != null) set("epdfb-valor", res.valor_banco);
      if (res.rtn_cliente) set("epdfb-rtncli", res.rtn_cliente);
      if (res.ubicacion) set("epdfb-ubic", res.ubicacion);
      if (res.cliente) set("epdfb-cliente", res.cliente);
      if (res.proyecto) set("epdfb-proyecto", res.proyecto);
      if (res.codigo_interno) set("epdfb-codint", res.codigo_interno);
    }
  } catch (e) { /* sin datos guardados: quedan los defaults de la obra */ }
  _epdfbActualizarPct();
}

function _pdfBancoParams() {
  const v = (id) => (document.getElementById(id)?.value || "").trim();
  return new URLSearchParams({
    report: "banco",
    valor_banco: v("epdfb-valor") || "0",
    proyecto: v("epdfb-proyecto"),
    codigo_nombre: v("epdfb-codnom"),
    cliente: v("epdfb-cliente"),
    rtn_cliente: v("epdfb-rtncli"),
    ubicacion: v("epdfb-ubic"),
    fecha: v("epdfb-fecha"),
    codigo_interno: v("epdfb-codint"),
  });
}

function generarPdfBanco() {
  if (!state.activeId) return;
  const valor = Number(document.getElementById("epdfb-valor")?.value || 0);
  if (!(valor > 0)) { alert("Ingresá el valor final para el Banco."); return; }
  window.open(`${API}/presupuestos/${state.activeId}/export-pdf?${_pdfBancoParams().toString()}`, "_blank");
  document.getElementById("modal-export-pdf-banco").classList.add("hidden");
}

function initExportPdfBanco() {
  document.getElementById("epdfb-valor")?.addEventListener("input", _epdfbActualizarPct);
  document.getElementById("epdfb-cancel")?.addEventListener("click", () =>
    document.getElementById("modal-export-pdf-banco").classList.add("hidden"));
  document.getElementById("epdfb-gen")?.addEventListener("click", generarPdfBanco);
  const modal = document.getElementById("modal-export-pdf-banco");
  if (modal) modal.addEventListener("click", (e) => {
    if (e.target.id === "modal-export-pdf-banco") e.target.classList.add("hidden");
  });
}

// --- CRONOGRAMA (GANTT) ---
function exportarCronograma() {
  if (!state.activeId) return;
  window.open(`${API}/presupuestos/${state.activeId}/export-cronograma`, "_blank");
}

async function abrirCronograma() {
  if (!state.activeId) { alert("Abrí una obra primero."); return; }
  document.getElementById("modal-cronograma").classList.remove("hidden");
  cargarGantt();
}

async function cargarGantt(keepScroll = false) {
  const body = document.getElementById("gantt-body");
  const sx = keepScroll ? body.scrollLeft : 0;
  const sy = keepScroll ? body.scrollTop : 0;
  if (!keepScroll) body.innerHTML = `<div class="gantt-loading">Calculando cronograma…</div>`;
  try {
    const data = await api("GET", `/presupuestos/${state.activeId}/cronograma`);
    renderGantt(data);
    body.scrollLeft = sx; body.scrollTop = sy;
  } catch (err) {
    body.innerHTML = `<div class="gantt-loading" style="color:var(--accent2)">Error: ${esc(err.message || err)}</div>`;
  }
}

const CUAD_MAX = 6;   // opciones de cuadrillas en el selector

function renderGantt(data) {
  document.getElementById("gantt-titulo").textContent = `Cronograma — ${data.nombre}`;
  document.getElementById("gantt-meta").textContent =
    `${data.fecha_inicio} → entrega est. ${data.fecha_fin} · ${data.dias_laborables ?? data.dias_calendario} días laborables (L-V + sáb ½) · ${data.semanas} semanas · ${data.meses ?? ""} meses · ${data.actividades.length} actividades · Esp/Ay = cuadrilla en paralelo (1 cuadrilla = 3 esp + 3 ay)`;

  const PXD = 7;                       // px por día calendario
  const totalDias = data.dias_calendario;
  const width = totalDias * PXD;
  const d0 = new Date(data.fecha_inicio + "T00:00:00");

  // Eje: una marca por semana
  let ticks = "";
  for (let w = 0; w * 7 < totalDias; w++) {
    const x = w * 7 * PXD;
    const dt = new Date(d0.getTime() + w * 7 * 86400000);
    ticks += `<div class="g-tick" style="left:${x}px"><b>S${w + 1}</b><small>${dt.getDate()}/${dt.getMonth() + 1}</small></div>`;
  }

  // Filas agrupadas por fase
  let rows = "";
  let faseAct = null;
  data.actividades.forEach(a => {
    if (a.fase !== faseAct) {
      faseAct = a.fase;
      rows += `<div class="g-row g-faserow"><div class="g-label g-fase-lbl">${esc(a.fase)}</div><div class="g-track" style="width:${width}px"></div></div>`;
    }
    const x = a.offset_dias * PXD;
    const w = Math.max(PXD, a.span_dias * PXD);
    const ne = a.n_esp ?? 3, na = a.n_ay ?? 3;
    const pid = esc(a.partida_id || "");
    const tip = `${esc(a.csi)} — ${esc(a.descripcion)} | ${fmt(a.cantidad)} ${esc(a.unidad)} · ${a.duracion_dias}d · ${ne} esp + ${na} ay · jh ${a.jh_esp}/${a.jh_ay} · ${a.fecha_inicio}→${a.fecha_fin} · ${esc(a.fuente)}`;
    rows += `<div class="g-row">
        <div class="g-label" title="${tip}">
          <span class="g-ord">${a.orden + 1}</span>
          <span class="g-dot" style="background:${a.fase_color}"></span>
          <span class="g-csi">${esc(a.csi)}</span>
          <span class="g-desc">${esc(a.descripcion)}</span>
          <span class="g-pers">
            <input type="number" min="1" max="12" value="${ne}" class="g-esp ${ne !== 3 ? "g-pers-on" : ""}" data-pid="${pid}" title="Especialistas (albañil, armador, soldador…)" />
            <input type="number" min="1" max="12" value="${na}" class="g-ay ${na !== 3 ? "g-pers-on" : ""}" data-pid="${pid}" title="Ayudantes / peones" />
          </span>
        </div>
        <div class="g-track" style="width:${width}px">
          <div class="g-bar" style="left:${x}px;width:${w}px;background:${a.fase_color}" title="${tip}"><span class="g-bar-d">${a.duracion_dias}d</span></div>
        </div>
      </div>`;
  });

  document.getElementById("gantt-body").innerHTML =
    `<div class="g-axis-row"><div class="g-axis-spacer"><span class="g-hdr-pers g-hdr-esp" title="Especialistas (albañil, armador, soldador…)">Esp</span><span class="g-hdr-pers g-hdr-ay" title="Ayudantes / peones">Ay</span></div><div class="g-axis" style="width:${width}px">${ticks}</div></div>
     <div class="g-rows">${rows}</div>`;

  document.querySelectorAll("#gantt-body .g-esp, #gantt-body .g-ay").forEach(inp =>
    inp.addEventListener("change", (e) => {
      const pid = e.target.dataset.pid;
      const esp = document.querySelector(`#gantt-body .g-esp[data-pid="${pid}"]`);
      const ay = document.querySelector(`#gantt-body .g-ay[data-pid="${pid}"]`);
      setPersonal(pid, parseInt(esp.value, 10) || 1, parseInt(ay.value, 10) || 1);
    }));
}

async function setPersonal(partidaId, nEsp, nAy) {
  if (!partidaId) return;
  try {
    await api("POST", `/presupuestos/${state.activeId}/cronograma/personal`,
      { partida_id: partidaId, n_esp: nEsp, n_ay: nAy });
    cargarGantt(true);   // re-calcula fechas, conserva scroll
  } catch (err) {
    alert("No se pudo ajustar personal: " + (err.message || err));
  }
}

function initCronograma() {
  const btn = document.getElementById("btn-cronograma");
  if (btn) btn.addEventListener("click", abrirCronograma);
  const close = document.getElementById("modal-cronograma-close");
  if (close) close.addEventListener("click", () =>
    document.getElementById("modal-cronograma").classList.add("hidden"));
  const exp = document.getElementById("btn-gantt-export");
  if (exp) exp.addEventListener("click", exportarCronograma);
  const modal = document.getElementById("modal-cronograma");
  if (modal) modal.addEventListener("click", (e) => {
    if (e.target.id === "modal-cronograma") e.target.classList.add("hidden");
  });
}

async function publicarAPortal() {
  if (!state.activeId) { alert("Abrí una obra primero."); return; }
  const obra = state.obras?.find(o => o.id === state.activeId);
  if (!confirm(`Publicar "${obra?.nombre || "esta obra"}" al Portal (Supabase)?\n\nSube partidas con valor + MO/MA. Republicar resetea el cronograma de la obra en el portal.`)) return;
  showScriptOut("Portal — Publicar", "Publicando a Supabase...", "running");
  try {
    const res = await api("POST", `/presupuestos/${state.activeId}/publish-supabase`);
    showScriptOut("Portal — Publicar",
      `✅ Publicada\n\nObra: ${res.nombre}\nPartidas: ${res.partidas}\nTotal: ${fmt(res.total)} HNL\nobra_id portal: ${res.obra_id}`,
      "ok");
  } catch (err) {
    showScriptOut("Portal — Error", err.message || String(err), "error");
  }
}

async function sincronizarPrecios() {
  if (!state.activeId) { alert("Abrí una obra primero."); return; }
  const obra = state.obras?.find(o => o.id === state.activeId);
  if (!confirm(`Sincronizar precios de "${obra?.nombre || "esta obra"}" al Portal?\n\nActualiza MA/MO/total/sobrecosto SIN tocar cronograma, avance ni movimientos.`)) return;
  showScriptOut("Portal — Sync precios", "Sincronizando precios a Supabase...", "running");
  try {
    const res = await api("POST", `/presupuestos/${state.activeId}/sync-precios-supabase`);
    showScriptOut("Portal — Sync precios",
      `✅ Precios sincronizados\n\nObra: ${res.nombre}\nSobrecosto: ${res.sobrecosto}%\nTotal: ${fmt(res.total)} HNL\nActualizadas: ${res.actualizadas}\nNuevas: ${res.nuevas}\nHuérfanas en portal: ${res.huerfanas_en_portal}`,
      "ok");
  } catch (err) {
    showScriptOut("Portal — Error", err.message || String(err), "error");
  }
}

// --- TABLE LAYOUT ---
const TABLE_FONT_KEY = "estimastruct.table-font";
const TABLE_WIDTHS_KEY = "estimastruct.table-widths";
const TABLE_FONT_STEPS = [11, 12, 13, 14];

function getTableFontSize() {
  const saved = parseInt(localStorage.getItem(TABLE_FONT_KEY), 10);
  return TABLE_FONT_STEPS.includes(saved) ? saved : 12;
}

function setTableFontSize(size) {
  const next = TABLE_FONT_STEPS.includes(size) ? size : 12;
  localStorage.setItem(TABLE_FONT_KEY, String(next));
  applyTableScale();
  if (state.activeData) renderTable(state.activeData);
}

function bumpTableFontSize(delta) {
  const current = getTableFontSize();
  const idx = TABLE_FONT_STEPS.indexOf(current);
  const next = TABLE_FONT_STEPS[Math.min(TABLE_FONT_STEPS.length - 1, Math.max(0, idx + delta))];
  setTableFontSize(next);
}

function loadTableWidths() {
  try {
    return JSON.parse(localStorage.getItem(TABLE_WIDTHS_KEY) || "{}") || {};
  } catch (_) {
    return {};
  }
}

function saveTableWidths(widths) {
  localStorage.setItem(TABLE_WIDTHS_KEY, JSON.stringify(widths || {}));
}

function applyTableScale() {
  const size = getTableFontSize();
  document.documentElement.style.setProperty("--table-font-size", `${size}px`);
  document.documentElement.style.setProperty("--table-row-padding-y", size <= 11 ? "4px" : size >= 14 ? "7px" : "5px");
}

function initTableScaleControls() {
  applyTableScale();
  const less = document.getElementById("btn-table-font-less");
  const more = document.getElementById("btn-table-font-more");
  const reset = document.getElementById("btn-table-font-reset");
  if (less) less.addEventListener("click", () => bumpTableFontSize(-1));
  if (more) more.addEventListener("click", () => bumpTableFontSize(1));
  if (reset) reset.addEventListener("click", () => setTableFontSize(12));
}

// --- UNIDADES (datalist global) ---
async function loadUnidades() {
  try {
    const r = await api("GET", "/unidades");
    state.unidades = r.unidades || [];
    renderUnidadesDatalist();
  } catch (e) { /* silent */ }
}
function renderUnidadesDatalist() {
  const dl = document.getElementById("unidades-list");
  if (!dl) return;
  dl.innerHTML = state.unidades.map(u => `<option value="${esc(u)}"></option>`).join("");
}
function ensureUnidad(u) {
  if (u && !state.unidades.includes(u)) {
    state.unidades.push(u);
    state.unidades.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
    renderUnidadesDatalist();
  }
}

// --- Esconder/mostrar barra de obras ---
function setSidebarCollapsed(collapsed) {
  document.getElementById("layout").classList.toggle("sidebar-collapsed", collapsed);
  document.getElementById("btn-show-sidebar").classList.toggle("hidden", !collapsed);
  localStorage.setItem("estimastruct.sidebarCollapsed", collapsed ? "1" : "0");
}

// --- TYPE MARK toggle ---
function toggleTypeMark() {
  if (state.modo !== "desarrollador") return;
  state.showTypeMark = !state.showTypeMark;
  document.getElementById("btn-toggle-typemark").classList.toggle("active", state.showTypeMark);
  if (state.activeData) renderTable(state.activeData);
}

// --- AUDITORÍA toggle ---
// Reemplaza columnas Costo Directo y Precio Unitario por
// Total Insumos (Cant × Insumos) y Total Mano de Obra (Cant × Mano de Obra).
function toggleAuditoria() {
  if (state.modo !== "desarrollador") return;
  state.auditMode = !state.auditMode;
  if (state.auditMode) {   // auditoría y MO son excluyentes
    state.moMode = false;
    document.getElementById("btn-toggle-solomo").classList.remove("active");
  }
  document.getElementById("btn-toggle-auditoria").classList.toggle("active", state.auditMode);
  if (state.activeData) renderTable(state.activeData);
}

// --- MANO DE OBRA (solo) toggle ---
// Muestra solo Cantidad, Mano de Obra y Total Mano de Obra (Cant × Mano de Obra).
function toggleSoloMO() {
  if (state.modo !== "desarrollador") return;
  state.moMode = !state.moMode;
  if (state.moMode) {   // MO y auditoría son excluyentes
    state.auditMode = false;
    document.getElementById("btn-toggle-auditoria").classList.remove("active");
  }
  document.getElementById("btn-toggle-solomo").classList.toggle("active", state.moMode);
  if (state.activeData) renderTable(state.activeData);
}

// --- MODO Cliente/Desarrollador ---
function toggleModo() {
  state.modo = state.modo === "cliente" ? "desarrollador" : "cliente";
  localStorage.setItem("estimastruct.modo", state.modo);
  applyModoUI();
  if (state.activeData) renderTable(state.activeData);
}
function applyModoUI() {
  const isDev = state.modo === "desarrollador";
  const btn = document.getElementById("btn-modo");
  btn.classList.toggle("dev", isDev);
  btn.textContent = isDev ? "🛠 Desarrollador" : "👤 Cliente";
  // Type Mark toggle solo visible en dev
  const tmBtn = document.getElementById("btn-toggle-typemark");
  if (tmBtn) tmBtn.style.display = isDev ? "" : "none";
  // Auditoría toggle solo visible en dev; al salir de dev se apaga
  const audBtn = document.getElementById("btn-toggle-auditoria");
  if (audBtn) audBtn.style.display = isDev ? "" : "none";
  if (!isDev && state.auditMode) {
    state.auditMode = false;
    if (audBtn) audBtn.classList.remove("active");
  }
  // Mano de Obra (solo) toggle: solo dev; al salir de dev se apaga
  const moBtn = document.getElementById("btn-toggle-solomo");
  if (moBtn) moBtn.style.display = isDev ? "" : "none";
  if (!isDev && state.moMode) {
    state.moMode = false;
    if (moBtn) moBtn.classList.remove("active");
  }
  const basesWrap = document.getElementById("bases-sidebar-toggle-wrap");
  if (basesWrap) {
    if (isDev) basesWrap.classList.remove("hidden");
    else basesWrap.classList.add("hidden");
  }
  // Menú visible en modo dev (no requiere obra activa — Bases de Datos es global)
  const devMenu = document.getElementById("dev-menu-wrap");
  if (devMenu) {
    if (isDev) devMenu.classList.remove("hidden");
    else devMenu.classList.add("hidden");
  }
  // recursos-bar (vinetas) solo en dev
  const recBar = document.getElementById("recursos-bar");
  if (recBar && state.activeId) {
    if (isDev) recBar.classList.remove("hidden");
    else recBar.classList.add("hidden");
  }
  const pill = document.getElementById("sobrecosto-pill");
  if (pill) {
    if (isDev && state.activeId) pill.classList.remove("hidden");
    else pill.classList.add("hidden");
  }
  // En cliente: cerrar panel inferior si estaba abierto
  if (!isDev) {
    document.getElementById("panel-bottom").classList.add("hidden");
    state.selectedPartida = null;
    if (basesState.visible) hideBasesDrawer();
  }
  // Re-render header totals when mode changes (oculta/muestra costo directo y sobrecosto)
  if (state.activeData) updateTotalesHeader(state.activeData);
}

// --- DEV MENU (Pasos del flujo) ---
function initDevMenu() {
  const btn = document.getElementById("btn-dev-menu");
  const menu = document.getElementById("dev-menu");
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    menu.classList.toggle("hidden");
  });
  document.addEventListener("click", (e) => {
    if (!document.getElementById("dev-menu-wrap").contains(e.target)) {
      menu.classList.add("hidden");
    }
  });
  menu.querySelectorAll(".dev-menu-item").forEach(it => {
    it.addEventListener("click", () => {
      menu.classList.add("hidden");
      const step = it.dataset.step;
      if (step === "about") openModalAbout();
      if (step === "session-log") openSessionLogModal();
      if (step === "bases") toggleBasesDrawer();
      else if (step === "table-less") bumpTableFontSize(-1);
      else if (step === "table-more") bumpTableFontSize(1);
      else if (step === "table-reset") setTableFontSize(12);
      else if (step === "agregar") openModalUpdater();
      else if (step === "2") runStep2Keynotes();
      else if (step === "4") openStep4PickCsv();
    });
  });
}

function initModalAbout() {
  const modal = document.getElementById("modal-about");
  document.getElementById("modal-about-close").addEventListener("click", () => {
    modal.classList.add("hidden");
  });
  modal.addEventListener("click", e => {
    if (e.target === modal) modal.classList.add("hidden");
  });
}

function openModalAbout() {
  document.getElementById("modal-about").classList.remove("hidden");
}

async function runStep2Keynotes() {
  if (!state.activeId) return;
  showScriptOut("Paso 2 — Keynotes", "Ejecutando...", "running");
  try {
    const res = await api("POST", `/presupuestos/${state.activeId}/scripts/keynotes`);
    const body =
      `${res.message}\n\n` +
      `Archivo: ${res.path}\n` +
      `Líneas: ${res.lines}\n` +
      `Divisiones: ${res.divisiones}\n` +
      `Partidas: ${res.partidas}\n` +
      `Tamaño: ${res.size_bytes} bytes`;
    showScriptOut("Paso 2 — Keynotes", body, "ok");
  } catch (err) {
    showScriptOut("Paso 2 — Error", err.message || String(err), "error");
  }
}

async function openStep4PickCsv() {
  if (!state.activeId) return;
  let data;
  try {
    data = await api("GET", "/scripts/schedules-csvs");
  } catch (err) {
    showScriptOut("Paso 4 — Error", err.message || String(err), "error");
    return;
  }
  const list = document.getElementById("csv-pick-list");
  if (!data.files.length) {
    list.innerHTML = `<div style="padding:14px;color:var(--text-dim);text-align:center">No hay exports de schedules de PyRevit en S5_schedules</div>`;
  } else {
    list.innerHTML = data.files.map(f => {
      const dt = new Date(f.mtime * 1000).toLocaleString("es-HN");
      return `<div class="csv-pick-item" data-name="${esc(f.name)}">
        <span>${esc(f.name)}</span>
        <span class="csv-pick-meta">${dt} · ${(f.size/1024).toFixed(1)} KB</span>
      </div>`;
    }).join("");
    list.querySelectorAll(".csv-pick-item").forEach(it => {
      it.addEventListener("click", () => {
        list.querySelectorAll(".csv-pick-item").forEach(x => x.classList.remove("selected"));
        it.classList.add("selected");
        document.getElementById("modal-csv-pick").dataset.selected = it.dataset.name;
        document.getElementById("modal-csv-ok").disabled = false;
      });
    });
    const latestName = data.latest || null;
    const latest = latestName
      ? list.querySelector(`.csv-pick-item[data-name="${CSS.escape(latestName)}"]`)
      : list.querySelector(".csv-pick-item");
    if (latest) {
      latest.classList.add("selected");
      document.getElementById("modal-csv-pick").dataset.selected = latest.dataset.name;
      document.getElementById("modal-csv-ok").disabled = false;
    }
  }
  if (!data.files.length) {
    document.getElementById("modal-csv-ok").disabled = true;
    delete document.getElementById("modal-csv-pick").dataset.selected;
  }
  document.getElementById("modal-csv-pick").classList.remove("hidden");
}

function initModalCsvPick() {
  document.getElementById("modal-csv-cancel").addEventListener("click", () => {
    document.getElementById("modal-csv-pick").classList.add("hidden");
  });
  document.getElementById("modal-csv-ok").addEventListener("click", async () => {
    const filename = document.getElementById("modal-csv-pick").dataset.selected;
    if (!filename) return;
    document.getElementById("modal-csv-pick").classList.add("hidden");
    showScriptOut("Paso 4 — Importar schedules", `Procesando ${filename}...`, "running");
    try {
      const res = await api("POST", `/presupuestos/${state.activeId}/scripts/import-quantities`, { filename });
      let body = `${res.message}\n\n` +
        `Archivo: ${res.csv_path}\n` +
        `Keynotes en CSV: ${res.csv_keynotes}\n` +
        `Coincidencias: ${res.matched}\n` +
        `Sin cantidad (zeroed): ${res.zeroed}\n` +
        `Sin contraparte: ${res.unmatched_count}`;
      if (res.unmatched_csv && res.unmatched_csv.length) {
        body += `\n\nKeynotes del CSV no encontrados en la obra:\n  ` +
          res.unmatched_csv.join("\n  ");
      }
      showScriptOut("Paso 4 — Cantidades importadas", body, "ok");
      await loadObra(state.activeId);
    } catch (err) {
      showScriptOut("Paso 4 — Error", err.message || String(err), "error");
    }
  });
}

function initModalScriptOut() {
  document.getElementById("modal-script-close").addEventListener("click", () => {
    document.getElementById("modal-script-out").classList.add("hidden");
  });
}
function showScriptOut(title, body, kind) {
  document.getElementById("modal-script-title").textContent = title;
  const el = document.getElementById("modal-script-body");
  el.textContent = body;
  el.classList.remove("ok", "error", "running");
  if (kind) el.classList.add(kind);
  document.getElementById("modal-script-out").classList.remove("hidden");
}

// --- EDIT helpers (con confirmación) ---
async function editPartidaDescripcion(pid, current) {
  const nuevo = prompt("Editar nombre de la matriz:", current || "");
  if (nuevo === null) return;
  const limpio = nuevo.replace(/_x000D_/g, "").replace(/\r/g, "").trim();
  if (limpio === current.trim()) return;
  if (!confirm(`¿Confirmar cambio?\n\nAntes:\n${current}\n\nDespués:\n${limpio}`)) return;
  await api("PATCH", `/partidas/${pid}/descripcion`, { descripcion: limpio });
  if (state.activeId) await loadObra(state.activeId);
}
async function editPartidaTypeMark(pid, current) {
  const nuevo = prompt("Editar Type Mark:", current || "");
  if (nuevo === null) return;
  const limpio = (nuevo || "").trim();
  if (limpio === (current || "").trim()) return;
  await api("PATCH", `/partidas/${pid}/type-mark`, { type_mark: limpio });
  if (state.activeId) await loadObra(state.activeId);
}
async function editPartidaCsi(pid, current) {
  const nuevo = prompt("Editar Código CSI:", current || "");
  if (nuevo === null) return;
  const limpio = (nuevo || "").trim();
  if (!limpio || limpio === (current || "").trim()) return;
  if (!confirm(`¿Confirmar cambio?\n\nAntes: ${current}\nDespués: ${limpio}`)) return;
  await api("PATCH", `/partidas/${pid}/clave-csi`, { clave_csi: limpio });
  if (state.activeId) await loadObra(state.activeId);
}
async function editInsumoDescripcion(iid, current) {
  const nuevo = prompt("Editar nombre del insumo:", current || "");
  if (nuevo === null) return;
  const limpio = nuevo.replace(/_x000D_/g, "").replace(/\r/g, "").trim();
  if (limpio === current.trim()) return;
  if (!confirm(`¿Confirmar cambio?\n\nAntes:\n${current}\n\nDespués:\n${limpio}`)) return;
  await api("PATCH", `/insumos/${iid}`, { descripcion: limpio });
  if (state.selectedPartida) await loadInsumos(state.selectedPartida.id);
}
async function editInsumoUnidad(iid, current) {
  const opciones = state.unidades.join(", ");
  const nuevo = prompt(`Editar unidad del insumo (existentes: ${opciones}):`, current || "");
  if (nuevo === null) return;
  const limpio = (nuevo || "").trim();
  if (!limpio || limpio === (current || "").trim()) return;
  await api("PATCH", `/insumos/${iid}`, { unidad: limpio });
  ensureUnidad(limpio);
  if (state.selectedPartida) await loadInsumos(state.selectedPartida.id);
}
async function editPartidaUnidad(pid, current) {
  const opciones = state.unidades.join(", ");
  const nuevo = prompt(`Editar unidad de la matriz (existentes: ${opciones}):`, current || "");
  if (nuevo === null) return;
  const limpio = (nuevo || "").trim();
  if (!limpio || limpio === (current || "").trim()) return;
  await api("PATCH", `/partidas/${pid}/unidad`, { unidad: limpio });
  ensureUnidad(limpio);
  if (state.activeId) await loadObra(state.activeId);
}

// --- ACTUALIZAR (recalcular toda la obra) ---
async function actualizarObra() {
  if (!state.activeId) return;
  const btn = document.getElementById("btn-actualizar");
  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = "⟳ Calculando...";
  try {
    await api("POST", `/presupuestos/${state.activeId}/calcular`);
    await loadObra(state.activeId);
  } catch (e) {
    alert("Error al recalcular: " + (e.message || e));
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

// [TABLE render/handlers] movido a tabla-render.js (cargado tras app.js).

// --- PANEL TABS ---
function initPanelTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      const tab = document.getElementById(`tab-${btn.dataset.tab}`);
      if (tab) tab.classList.add("active");
    });
  });
}

// --- PANEL INFERIOR ---
function initPanelBottom() {
  document.getElementById("panel-close").addEventListener("click", () => {
    document.getElementById("panel-bottom").classList.add("hidden");
    state.selectedPartida = null;
    document.querySelectorAll(".partida-row").forEach(r => r.classList.remove("selected"));
  });

  // Edición inline en el header del panel (CSI, Type Mark, Descripción)
  document.getElementById("panel-edit-csi").addEventListener("dblclick", (e) => {
    const pid = e.currentTarget.dataset.pid;
    if (pid) editPartidaCsi(pid, state.selectedPartida?.clave_csi || "");
  });
  document.getElementById("panel-edit-tm").addEventListener("dblclick", (e) => {
    const pid = e.currentTarget.dataset.pid;
    if (pid) editPartidaTypeMark(pid, state.selectedPartida?.type_mark || "");
  });
  document.getElementById("panel-edit-desc").addEventListener("dblclick", (e) => {
    const pid = e.currentTarget.dataset.pid;
    if (pid) editPartidaDescripcion(pid, state.selectedPartida?.descripcion || "");
  });

  // Unidad edit button
  document.getElementById("btn-unidad-edit").addEventListener("click", () => {
    const display = document.getElementById("detail-unidad");
    const sel = document.getElementById("select-unidad");
    sel.value = display.textContent.trim();
    display.classList.add("hidden");
    sel.classList.remove("hidden");
    sel.focus();
  });

  document.getElementById("select-unidad").addEventListener("change", async () => {
    if (!state.selectedPartida) return;
    const sel = document.getElementById("select-unidad");
    const newUnidad = sel.value;
    try {
      await api("PATCH", `/partidas/${state.selectedPartida.id}/unidad`, { unidad: newUnidad });
      state.selectedPartida.unidad = newUnidad;
      document.getElementById("detail-unidad").textContent = newUnidad;
      const row = document.querySelector(`.partida-row[data-id="${state.selectedPartida.id}"]`);
      if (row) {
        const udCell = row.querySelector(".ud-cell");
        if (udCell) {
          udCell.textContent = newUnidad;
          udCell.dataset.ud = newUnidad;
        }
      }
      ensureUnidad(newUnidad);
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      sel.classList.add("hidden");
      document.getElementById("detail-unidad").classList.remove("hidden");
    }
  });
  document.getElementById("select-unidad").addEventListener("blur", () => {
    document.getElementById("select-unidad").classList.add("hidden");
    document.getElementById("detail-unidad").classList.remove("hidden");
  });

  // Matriz event delegation (delete + qty edit)
  document.getElementById("matriz-table-wrap").addEventListener("click", (e) => {
    const delBtn = e.target.closest(".btn-del-insumo");
    if (delBtn && currentInsumosPid) { deleteInsumo(delBtn.dataset.iid, currentInsumosPid); return; }
    const qtyCell = e.target.closest(".insumo-qty-cell");
    if (qtyCell && !qtyCell.querySelector("input") && currentInsumosPid) {
      editInsumoQty(qtyCell, currentInsumosPid);
    }
  });
  // Doble-clic en descripción / unidad de insumo
  document.getElementById("matriz-table-wrap").addEventListener("dblclick", (e) => {
    const dCell = e.target.closest(".insumo-desc-cell");
    if (dCell) { editInsumoDescripcion(dCell.dataset.iid, dCell.dataset.desc); return; }
    const uCell = e.target.closest(".insumo-ud-cell");
    if (uCell) { editInsumoUnidad(uCell.dataset.iid, uCell.dataset.ud); }
  });

  setupInsumoSearch();

}

function syncTableCells(pid, result) {
  const row = document.querySelector(`.partida-row[data-id="${pid}"]`);
  if (!row) return;
  const qCell = row.querySelector(".qty-cell");
  const tCell = row.querySelector(".tot-cell");
  if (qCell && result.cantidad !== undefined) {
    qCell.textContent = result.cantidad > 0 ? fmt(result.cantidad) : "—";
    qCell.classList.toggle("qty-filled", result.cantidad > 0);
  }
  if (tCell && result.total !== undefined) {
    tCell.textContent = result.total > 0 ? fmt(result.total) : "—";
    tCell.classList.toggle("total-filled", result.total > 0);
  }
}

function showPanelPartida(partida) {
  state.selectedPartida = partida;
  const panel = document.getElementById("panel-bottom");
  panel.classList.remove("hidden");

  // Encabezado editable: CSI · Type Mark — Descripción
  const csiEl  = document.getElementById("panel-edit-csi");
  const tmEl   = document.getElementById("panel-edit-tm");
  const descEl = document.getElementById("panel-edit-desc");
  csiEl.textContent  = partida.clave_csi || "—";
  tmEl.textContent   = partida.type_mark || "—";
  descEl.textContent = partida.descripcion || "—";
  csiEl.dataset.pid = partida.id;
  tmEl.dataset.pid  = partida.id;
  descEl.dataset.pid = partida.id;

  updatePanelValues(partida);

  // Switch to detalle tab
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
  document.querySelector(".tab-btn[data-tab='detalle']").classList.add("active");
  document.getElementById("tab-detalle").classList.add("active");

  initInsumoSearch(partida.id);
  loadInsumos(partida.id);
}

function updatePanelValues(partida) {
  document.getElementById("detail-unidad").textContent   = partida.unidad;
  document.getElementById("detail-mo").textContent       = fmt(partida.costo_mo);
  // Label es "INSUMOS" (no "Materiales") → debe incluir MATERIAL + resto de non-MO
  // (unitario_matriz), igual que la columna INSUMOS de la tabla.
  document.getElementById("detail-ma").textContent       = fmt((parseFloat(partida.costo_ma) || 0) + (parseFloat(partida.unitario_matriz) || 0));
  document.getElementById("detail-base").textContent     = fmt(partida.costo_base);
  document.getElementById("detail-pu").textContent       = fmt(partida.precio_unitario);
  document.getElementById("detail-cantidad").textContent = partida.cantidad > 0 ? fmt(partida.cantidad) : "—";
  document.getElementById("detail-total").textContent    =
    `${state.activeData?.moneda || "HNL"} ${fmt(partida.total)}`;
}

function updateUnidadesSelect(proyectoData) {
  const unidadesHistoricas = new Set(state.unidades || []);
  if (proyectoData.capitulos) {
    for (const cap of proyectoData.capitulos) {
      for (const partida of cap.partidas) {
        if (partida.unidad) unidadesHistoricas.add(partida.unidad);
      }
    }
  }
  const selUd = document.getElementById("select-unidad");
  selUd.innerHTML = "";
  const unidList = Array.from(unidadesHistoricas).sort((a,b) => a.toLowerCase().localeCompare(b.toLowerCase()));
  for (const u of unidList) {
    const opt = document.createElement("option");
    opt.value = u;
    opt.textContent = u;
    selUd.appendChild(opt);
  }
}

// --- VIÑETAS DE RECURSOS ---
const VINETA_META = {
  INSUMOS:     { label: "Insumos",      color: "#56ccf2", tipos: ["MATERIAL", "EQUIPO", "SUBCONTRATO", "HERRAMIENTA", "DISEÑO", "FLETE"] },
  MANO_OBRA:   { label: "Mano de Obra", color: "#eb5757", tipos: ["MANO_OBRA"] },
};

// Subtipos de INSUMOS (submenú desplegable en la viñeta INSUMOS).
// sigla = texto corto del botón; label = texto largo (title) / título del panel lateral.
const INSUMO_SUBTIPOS = {
  MATERIAL:     { sigla: "MA",  color: "#56ccf2", label: "Materiales" },
  EQUIPO:       { sigla: "EQ",  color: "#27ae60", label: "Equipo" },
  SUBCONTRATO:  { sigla: "SC",  color: "#bb6bd9", label: "Subcontrato" },
  HERRAMIENTA:  { sigla: "HER", color: "#f2994a", label: "Herramienta" },
  FLETE:        { sigla: "FL",  color: "#f2c94c", label: "Flete" },
  "DISEÑO":     { sigla: "DIS", color: "#9b9b9b", label: "Diseño" },
};

// Cada subtipo se comporta como una VINETA_META de un solo tipo → reutiliza
// toggleVineta()/renderRecursos() sin duplicar lógica.
const SUBTIPO_META = {};
for (const [tipo, meta] of Object.entries(INSUMO_SUBTIPOS)) {
  SUBTIPO_META[tipo] = { label: meta.label, color: meta.color, tipos: [tipo] };
}

let recursosCache = {};      // tipo → array
let vinetaActiva = null;
let searchDebounce = null;

// Devuelve la meta de una viñeta principal (INSUMOS/MANO_OBRA) o de un
// subtipo de INSUMOS (MATERIAL/EQUIPO/...), para que toggleVineta/renderRecursos
// funcionen igual sin importar el origen del click.
function getVinetaMeta(tipo) {
  return VINETA_META[tipo] || SUBTIPO_META[tipo];
}

// Carga (si hace falta) y devuelve del cache los recursos de un tipo puntual.
async function ensureRecursoCache(tipo) {
  if (!recursosCache[tipo]) {
    try {
      recursosCache[tipo] = await api("GET", `/recursos?tipo=${encodeURIComponent(tipo)}`);
    } catch { recursosCache[tipo] = []; }
  }
  return recursosCache[tipo];
}

async function initVinetas() {
  // Cargar conteos al arrancar
  for (const [key, meta] of Object.entries(VINETA_META)) {
    let totalCount = 0;
    try {
      for (const tipo of meta.tipos) {
        const data = await api("GET", `/recursos?tipo=${encodeURIComponent(tipo)}`);
        recursosCache[tipo] = data;
        totalCount += data.length;
      }
      const btn = document.querySelector(`.vineta[data-tipo="${key}"]`);
      if (btn) btn.querySelector(".vineta-count").textContent = `(${totalCount})`;
    } catch { /* ignorar si falla */ }
  }

  // Mostrar barra solo cuando hay obra activa
  // (se muestra en loadObra)

  // Click en viñeta principal (INSUMOS = todos los non-MO, MANO_OBRA = MO)
  document.querySelectorAll(".vineta").forEach(btn => {
    btn.addEventListener("click", () => toggleVineta(btn.dataset.tipo));
  });

  // Click en subtipo del submenú de INSUMOS (MA/EQ/SC/HER/FL/DIS)
  document.querySelectorAll(".vineta-sub").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const tipo = btn.dataset.tipo;
      await ensureRecursoCache(tipo);
      toggleVineta(tipo);
      // Cerrar el submenú tras seleccionar (modo click con .open)
      btn.closest(".vineta-wrap")?.classList.remove("open");
    });
  });

  // Búsqueda
  document.getElementById("recurso-search").addEventListener("input", (e) => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      if (vinetaActiva) renderRecursos(vinetaActiva, e.target.value.trim());
    }, 200);
  });

  // Cerrar panel lateral
  document.getElementById("panel-lateral-close").addEventListener("click", () => {
    document.getElementById("recursos-panel-lateral").classList.add("hidden");
    vinetaActiva = null;
    document.querySelectorAll(".vineta, .vineta-sub").forEach(b => b.classList.remove("active"));
    document.getElementById("recurso-search").value = "";
  });
}

function toggleVineta(tipo) {
  const panel = document.getElementById("recursos-panel-lateral");
  const meta = getVinetaMeta(tipo);
  if (vinetaActiva === tipo) {
    // Cerrar
    vinetaActiva = null;
    panel.classList.add("hidden");
    document.querySelectorAll(".vineta, .vineta-sub").forEach(b => b.classList.remove("active"));
    document.getElementById("recurso-search").value = "";
  } else {
    vinetaActiva = tipo;
    // Highlight: viñetas principales (INSUMOS/MANO_OBRA) solo se marcan active
    // cuando el tipo activo ES esa clave exacta (no un subtipo).
    document.querySelectorAll(".vineta").forEach(b => {
      b.classList.toggle("active", b.dataset.tipo === tipo);
    });
    // Subtipos del submenú: active solo el que coincide.
    document.querySelectorAll(".vineta-sub").forEach(b => {
      b.classList.toggle("active", b.dataset.tipo === tipo);
    });
    // Aplicar color activo al borde de la viñeta principal correspondiente
    document.querySelectorAll(".vineta.active").forEach(b => {
      b.style.borderColor = meta?.color || "var(--accent2)";
    });
    document.querySelectorAll(".vineta:not(.active)").forEach(b => {
      b.style.borderColor = "";
    });
    // Actualizar título del panel lateral
    document.getElementById("panel-lateral-title").textContent = meta.label;
    panel.classList.remove("hidden");
    renderRecursos(tipo, document.getElementById("recurso-search").value.trim());
  }
}

function renderRecursos(vinetaKey, q = "") {
  const lista = document.getElementById("recursos-lista");
  const meta = getVinetaMeta(vinetaKey);

  // Combinar items de todos los tipos de esta viñeta
  let items = [];
  if (meta && meta.tipos) {
    for (const tipo of meta.tipos) {
      items = items.concat(recursosCache[tipo] || []);
    }
  }

  if (q) {
    const ql = q.toLowerCase();
    items = items.filter(r =>
      r.clave.toLowerCase().includes(ql) ||
      r.descripcion.toLowerCase().includes(ql)
    );
  }

  if (!items.length) {
    lista.innerHTML = `<div style="padding:10px 14px;color:var(--text-dim);font-size:12px;">Sin resultados</div>`;
    return;
  }

  const unidOpts = UNIDADES.map(u => `<option value="${u}"${u === '__CUR__' ? ' selected' : ''}>${u}</option>`).join("");

  lista.innerHTML = items.map(r => `
    <div class="recurso-row" data-rid="${r.id}">
      <span class="recurso-clave" style="color:${meta?.color || 'var(--text-dim)'}">${esc(r.clave)}</span>
      <span class="recurso-desc">${esc(r.descripcion)}</span>
      <select class="recurso-ud-sel" data-rid="${r.id}" data-val="${esc(r.unidad)}" title="Cambiar unidad">
        ${UNIDADES.map(u => `<option value="${u}"${u === r.unidad ? ' selected' : ''}>${u}</option>`).join("")}
      </select>
      <span class="recurso-precio editable-precio" data-rid="${r.id}" data-val="${r.precio_unitario}" title="Click para editar precio">${fmt(r.precio_unitario)}</span>
    </div>
  `).join("");

  lista.querySelectorAll(".editable-precio").forEach(span => {
    span.addEventListener("click", (e) => { e.stopPropagation(); editRecursoPrecio(span, vinetaKey); });
  });

  lista.querySelectorAll(".recurso-ud-sel").forEach(sel => {
    sel.addEventListener("change", async () => {
      const rid = sel.dataset.rid;
      const newUd = sel.value;
      try {
        await api("PATCH", `/recursos/${rid}/unidad`, { unidad: newUd });
        sel.dataset.val = newUd;
        const r = Object.values(recursosCache).flat().find(x => x.id === rid);
        if (r) r.unidad = newUd;
      } catch (err) {
        sel.value = sel.dataset.val;
        alert("Error: " + err.message);
      }
    });
  });
}

// --- MODAL NUEVA OBRA ---
function initModalObra() {
  const modal = document.getElementById("modal-obra");
  document.getElementById("modal-obra-cancel").addEventListener("click", () => modal.classList.add("hidden"));

  // Sincronizar selector cuando cambia (actualizar descripción)
  document.getElementById("obra-template-version").addEventListener("change", () => {
    updateTemplateDesc();
  });

  document.getElementById("modal-obra-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const nombre    = document.getElementById("obra-nombre").value.trim();
    const cliente   = document.getElementById("obra-cliente").value.trim();
    const moneda    = document.getElementById("obra-moneda").value;
    const sobrecosto = parseFloat(document.getElementById("obra-sobrecosto").value) || 20;
    const templateVersion = document.getElementById("obra-template-version").value;
    if (!nombre) return;
    const btn = e.target.querySelector("button[type=submit]");
    btn.disabled = true; btn.textContent = "Creando...";
    try {
      const result = await api("POST", "/presupuestos/from-template", {
        nombre, cliente, moneda,
        template_version: templateVersion,
        config: { sobrecosto, administracion: 0, utilidad: 0, imprevistos: 0, iva: 15, otros_factor: 0 }
      });
      modal.classList.add("hidden");
      await loadObras();
      loadObra(result.id);
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      btn.disabled = false; btn.textContent = "Crear Obra";
    }
  });
}

function openModalObra() {
  document.getElementById("obra-nombre").value = "";
  document.getElementById("obra-cliente").value = "";
  document.getElementById("obra-moneda").value = "HNL";
  document.getElementById("obra-sobrecosto").value = "20";
  // Sincronizar selector con valor global de localStorage
  document.getElementById("obra-template-version").value = state.templateVersion;
  updateTemplateDesc();
  loadTemplateCatalog();
  document.getElementById("modal-obra").classList.remove("hidden");
  document.getElementById("obra-nombre").focus();
}

function updateTemplateDesc() {
  const selectedVersion = document.getElementById("obra-template-version").value;
  const info = templateCatalog[selectedVersion] || {};
  const total = Number.isFinite(info.fichas_total) ? info.fichas_total : null;
  const countLabel = total === null ? "" : ` (${total} fichas)`;
  const desc = selectedVersion === "v1.0"
    ? `Template V1.0 — Original${countLabel}`
    : selectedVersion === "v1.1"
      ? `Template V1.1 — Legacy${countLabel}`
      : `Template V1.2 — Vigente${countLabel}`;
  document.getElementById("template-desc").textContent = desc;
  refreshTemplateOptionLabels();
}

async function loadTemplateCatalog() {
  try {
    const versions = await api("GET", "/bases");
    for (const item of versions || []) {
      const version = item.version || item;
      const total = typeof item === "object" ? item.fichas_total : null;
      if (!version) continue;
      templateCatalog[version] = {
        fichas_total: Number.isFinite(total) ? total : null,
      };
    }
    refreshTemplateOptionLabels();
    updateTemplateDesc();
  } catch (_) {
    // Si falla, la UI sigue funcionando con labels sin conteo.
  }
}

function refreshTemplateOptionLabels() {
  const v10 = document.querySelector('#obra-template-version option[value="v1.0"]');
  const v11 = document.querySelector('#obra-template-version option[value="v1.1"]');
  const v12 = document.querySelector('#obra-template-version option[value="v1.2"]');
  if (v10) {
    const total = templateCatalog["v1.0"]?.fichas_total;
    v10.textContent = total == null ? "V1.0 — Original" : `V1.0 — Original (${total} fichas)`;
  }
  if (v11) {
    const total = templateCatalog["v1.1"]?.fichas_total;
    v11.textContent = total == null ? "V1.1 — Legacy" : `V1.1 — Legacy (${total} fichas)`;
  }
  if (v12) {
    const total = templateCatalog["v1.2"]?.fichas_total;
    v12.textContent = total == null ? "V1.2 — Vigente" : `V1.2 — Vigente (${total} fichas)`;
  }
  const labelV10 = document.getElementById("label-v1-0");
  const labelV11 = document.getElementById("label-v1-1");
  const labelV12 = document.getElementById("label-v1-2");
  if (labelV10) {
    const total = templateCatalog["v1.0"]?.fichas_total;
    const desc = labelV10.querySelector("div div:last-child");
    if (desc) desc.textContent = total == null ? "Datos originales" : `Datos originales (${total} fichas)`;
  }
  if (labelV11) {
    const total = templateCatalog["v1.1"]?.fichas_total;
    const desc = labelV11.querySelector("div div:last-child");
    if (desc) desc.textContent = total == null ? "Versión legacy" : `Versión legacy (${total} fichas)`;
  }
  if (labelV12) {
    const total = templateCatalog["v1.2"]?.fichas_total;
    const desc = labelV12.querySelector("div div:last-child");
    if (desc) desc.textContent = total == null ? "Versión vigente" : `Versión vigente (${total} fichas)`;
  }
}

// --- TEMPLATE VERSION SELECTOR ---
function initModalTemplateVersion() {
  const modal = document.getElementById("modal-template-version");
  const radioButtons = document.querySelectorAll('input[name="template-version"]');
  const versionSelected = document.getElementById("version-selected");
  const labelV10 = document.getElementById("label-v1-0");
  const labelV11 = document.getElementById("label-v1-1");
  const labelV12 = document.getElementById("label-v1-2");

  // Set initial value
  document.querySelector(`input[value="${state.templateVersion}"]`).checked = true;
  updateVersionDisplay();

  radioButtons.forEach(radio => {
    radio.addEventListener("change", updateVersionDisplay);
  });

  function updateVersionDisplay() {
    const selected = document.querySelector('input[name="template-version"]:checked').value;
    versionSelected.textContent = selected === "v1.0" ? "V1.0" : selected === "v1.1" ? "V1.1" : "V1.2";

    // Update label styles
    labelV10.style.borderColor = selected === "v1.0" ? "var(--accent)" : "var(--border)";
    labelV10.style.backgroundColor = selected === "v1.0" ? "var(--bg-dark)" : "transparent";
    labelV11.style.borderColor = selected === "v1.1" ? "var(--accent)" : "var(--border)";
    labelV11.style.backgroundColor = selected === "v1.1" ? "var(--bg-dark)" : "transparent";
    if (labelV12) {
      labelV12.style.borderColor = selected === "v1.2" ? "var(--accent)" : "var(--border)";
      labelV12.style.backgroundColor = selected === "v1.2" ? "var(--bg-dark)" : "transparent";
    }
  }

  document.getElementById("modal-tv-cancel").addEventListener("click", () => {
    modal.classList.add("hidden");
  });

  document.getElementById("modal-tv-ok").addEventListener("click", () => {
    const selected = document.querySelector('input[name="template-version"]:checked').value;
    state.templateVersion = selected;
    localStorage.setItem("estimastruct.template-version", selected);
    updateTemplateDesc();
    modal.classList.add("hidden");
  });
}

function openModalTemplateVersionDialog() {
  const modal = document.getElementById("modal-template-version");
  document.querySelector(`input[value="${state.templateVersion}"]`).checked = true;
  const versionSelected = document.getElementById("version-selected");
  versionSelected.textContent = state.templateVersion === "v1.0" ? "V1.0" : state.templateVersion === "v1.1" ? "V1.1" : "V1.2";
  modal.classList.remove("hidden");
}

// --- DELETE OBRA ---
function initModalDelete() {
  const modal = document.getElementById("modal-delete");
  const chk = document.getElementById("del-confirm-check");
  const btnOk = document.getElementById("modal-delete-ok");
  document.getElementById("modal-delete-cancel").addEventListener("click", () => {
    modal.classList.add("hidden");
  });
  chk.addEventListener("change", () => { btnOk.disabled = !chk.checked; });
  btnOk.addEventListener("click", async () => {
    const id = modal.dataset.obraId;
    if (!id) return;
    btnOk.disabled = true; btnOk.textContent = "Borrando...";
    try {
      await api("DELETE", `/presupuestos/${id}`);
      modal.classList.add("hidden");
      if (state.activeId === id) {
        state.activeId = null;
        clearMain();
      }
      await loadObras();
    } catch (err) {
      alert("Error: " + (err.message || err));
    } finally {
      btnOk.disabled = false; btnOk.textContent = "Borrar";
    }
  });
}

function borrarObra(id, nombre) {
  const modal = document.getElementById("modal-delete");
  modal.dataset.obraId = id;
  document.getElementById("modal-delete-msg").innerHTML =
    `Vas a borrar la obra <b>${esc(nombre)}</b> con todos sus capítulos, partidas e insumos. Esta acción es <b>irreversible</b>.`;
  document.getElementById("del-confirm-check").checked = false;
  document.getElementById("modal-delete-ok").disabled = true;
  modal.classList.remove("hidden");
}

// --- RENAME OBRA ---
function initModalRename() {
  document.getElementById("modal-rename-cancel").addEventListener("click", () => {
    document.getElementById("modal-rename").classList.add("hidden");
  });
  document.getElementById("modal-rename-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const nombre = document.getElementById("rename-nombre").value.trim();
    const id = document.getElementById("modal-rename").dataset.obraId;
    if (!nombre || !id) return;
    const btn = e.target.querySelector("button[type=submit]");
    btn.disabled = true; btn.textContent = "Guardando...";
    try {
      await api("PATCH", `/presupuestos/${id}/nombre`, { nombre });
      document.getElementById("modal-rename").classList.add("hidden");
      await loadObras();
      if (state.activeId === id) {
        document.querySelector(".obra-titulo").textContent = nombre;
      }
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      btn.disabled = false; btn.textContent = "Guardar";
    }
  });
}

function openModalRename(id, currentNombre) {
  const modal = document.getElementById("modal-rename");
  modal.dataset.obraId = id;
  document.getElementById("rename-nombre").value = currentNombre;
  modal.classList.remove("hidden");
  document.getElementById("rename-nombre").focus();
  document.getElementById("rename-nombre").select();
}

// --- SOBRECOSTO PILL ---
function initSobrecostoPill() {
  const pill = document.getElementById("sobrecosto-pill");
  const popover = document.getElementById("sobrecosto-popover");

  pill.addEventListener("click", (e) => {
    if (e.target.closest("#sobrecosto-popover")) return;
    popover.classList.toggle("hidden");
    if (!popover.classList.contains("hidden")) {
      document.getElementById("sobrecosto-input").focus();
      document.getElementById("sobrecosto-input").select();
    }
  });

  document.getElementById("btn-sc-cancel").addEventListener("click", (e) => {
    e.stopPropagation();
    popover.classList.add("hidden");
  });

  document.getElementById("btn-sc-ok").addEventListener("click", async (e) => {
    e.stopPropagation();
    if (!state.activeId) return;
    const sc = parseFloat(document.getElementById("sobrecosto-input").value);
    if (isNaN(sc) || sc < 0) return;
    const btn = document.getElementById("btn-sc-ok");
    btn.disabled = true; btn.textContent = "...";
    try {
      await api("PATCH", `/presupuestos/${state.activeId}/sobrecosto`, { sobrecosto: sc });
      document.getElementById("sobrecosto-val").textContent = fmt(sc, 1) + "%";
      popover.classList.add("hidden");
      await loadObra(state.activeId);
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      btn.disabled = false; btn.textContent = "Aplicar";
    }
  });

  document.getElementById("sobrecosto-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") document.getElementById("btn-sc-ok").click();
    if (e.key === "Escape") popover.classList.add("hidden");
  });

  // Cerrar al hacer clic fuera
  document.addEventListener("click", (e) => {
    if (!pill.contains(e.target)) popover.classList.add("hidden");
  });
}

// --- MATRIZ DE INSUMOS ---

const TIPO_COLOR = {
  MATERIAL:    "#56ccf2",
  MANO_OBRA:   "#eb5757",
  EQUIPO:      "#bb87fc",
  SUBCONTRATO: "#f2994a",
  HERRAMIENTA: "#6fcf97",
  "DISEÑO":    "#f2c94c",
  FLETE:       "#a0a0a0",
};

const UNIDADES = [
  "m2","m3","m","mL","ml","kg","ton","global","glb","pza","unidad",
  "mes","hr","jor","viaje","und","lt","gal","lb","pie2","pie3",
  "caja","rollo","saco","bolsa","par","juego","set","km","cm","mm",
];

let currentInsumosPid = null;
let insumoSearchSelected = null;

async function loadInsumos(pid) {
  try {
    const data = await api("GET", `/partidas/${pid}/insumos`);
    const partida = findPartida(pid);
    if (partida && data.partida) Object.assign(partida, data.partida);
    renderMatriz(data, pid);
    if (state.selectedPartida?.id === pid && partida) {
      updatePanelValues(partida);
      syncTableCells(pid, data.partida || {});
    }
  } catch (err) {
    console.error("Error cargando insumos:", err);
  }
}

function renderMatriz(data, pid) {
  const tots = data.totales || {};
  const maTotal = (tots.MATERIAL || 0) + (tots.EQUIPO || 0) + (tots.SUBCONTRATO || 0) + (tots.HERRAMIENTA || 0) + (tots["DISEÑO"] || 0) + (tots.FLETE || 0);
  document.getElementById("mt-todos").textContent  = fmt(data.total_todos || 0);
  document.getElementById("mt-ma").textContent     = fmt(maTotal);
  document.getElementById("mt-mo").textContent     = fmt(tots.MANO_OBRA || 0);

  const p = data.partida || {};
  document.getElementById("detail-mo").textContent      = fmt(p.costo_mo || 0);
  // Label es "INSUMOS": usar maTotal (MATERIAL + EQUIPO + SUBCONTRATO + HERRAMIENTA + DISEÑO + FLETE),
  // no solo costo_ma (MATERIAL). maTotal ya viene de los totales reales por tipo de la matriz (línea 1702).
  document.getElementById("detail-ma").textContent      = fmt(maTotal);
  document.getElementById("detail-base").textContent    = fmt(p.costo_base || 0);
  document.getElementById("detail-pu").textContent      = fmt(p.precio_unitario || 0);
  document.getElementById("detail-total").textContent   =
    `${state.activeData?.moneda || "HNL"} ${fmt(p.total || 0)}`;

  const tbody = document.getElementById("matriz-body");
  if (!data.insumos || !data.insumos.length) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--text-dim);padding:14px;font-size:11px">Sin insumos — busca y agrega recursos abajo</td></tr>`;
  } else {
    const claveSort = (a, b) => (a.clave || "").localeCompare(b.clave || "", "es", { sensitivity: "base" });
    const insumosGrupo = data.insumos.filter(i => i.tipo !== "MANO_OBRA").sort(claveSort);
    const manoObra    = data.insumos.filter(i => i.tipo === "MANO_OBRA").sort(claveSort);
    let html = "";
    let n = 1;
    if (insumosGrupo.length) {
      html += `<tr class="grupo-header"><td colspan="8" style="background:var(--surface2);color:#56ccf2;font-weight:700;padding:6px 10px;font-size:11px;letter-spacing:0.5px">INSUMOS</td></tr>`;
      for (const ins of insumosGrupo) html += renderInsumoRow(ins, n++);
    }
    if (manoObra.length) {
      html += `<tr class="grupo-header"><td colspan="8" style="background:var(--surface2);color:#eb5757;font-weight:700;padding:6px 10px;font-size:11px;letter-spacing:0.5px">MANO DE OBRA</td></tr>`;
      for (const ins of manoObra) html += renderInsumoRow(ins, n++);
    }
    tbody.innerHTML = html;
  }

  initInsumoSearch(pid);
}

function renderInsumoRow(ins, num) {
  const color = TIPO_COLOR[ins.tipo] || "var(--text-dim)";
  return `
    <tr class="insumo-row">
      <td style="color:var(--text-dim);font-size:11px">${num}</td>
      <td style="font-size:10px;color:${color}">${esc(ins.clave)}</td>
      <td class="insumo-desc-cell" data-iid="${ins.id}" data-desc="${esc(ins.descripcion || "")}" style="max-width:220px;overflow:hidden;text-overflow:ellipsis;cursor:pointer" title="Doble-clic para editar">${esc(ins.descripcion)}</td>
      <td class="insumo-ud-cell" data-iid="${ins.id}" data-ud="${esc(ins.unidad || "")}" style="color:var(--text-dim);font-size:11px;cursor:pointer" title="Doble-clic para editar">${esc(ins.unidad)}</td>
      <td class="num insumo-qty-cell" data-iid="${ins.id}" data-val="${ins.cantidad}">${fmt(ins.cantidad, 4)}</td>
      <td class="num">${fmt(ins.costo_unit)}</td>
      <td class="num" style="color:var(--accent2)">${fmt(ins.total)}</td>
      <td style="text-align:center">
        <button class="btn-del-insumo" data-iid="${ins.id}" title="Eliminar">✕</button>
      </td>
    </tr>`;
}

async function deleteInsumo(iid, pid) {
  try {
    await api("DELETE", `/insumos/${iid}`);
    await loadInsumos(pid);
    await refreshTotals();
  } catch (err) {
    alert("Error: " + err.message);
  }
}

function editInsumoQty(cell, pid) {
  const iid = cell.dataset.iid;
  const prevVal = parseFloat(cell.dataset.val) || 0;
  cell.innerHTML = `<input type="number" class="inline-qty-input" value="${prevVal}" min="0" step="any" style="width:70px" />`;
  const inp = cell.querySelector("input");
  inp.focus(); inp.select();

  let saved = false;
  const save = async () => {
    if (saved) return;
    saved = true;
    const newVal = parseFloat(inp.value) || 0;
    if (newVal === prevVal) { cell.innerHTML = fmt(prevVal, 4); return; }
    try {
      await api("PATCH", `/insumos/${iid}`, { cantidad: newVal });
      await loadInsumos(pid);
      await refreshTotals();
    } catch (err) {
      cell.innerHTML = fmt(prevVal, 4);
      alert("Error: " + err.message);
    }
  };
  inp.addEventListener("keydown", (e) => {
    if (e.key === "Enter") inp.blur();
    if (e.key === "Escape") { saved = true; cell.innerHTML = fmt(prevVal, 4); }
  });
  inp.addEventListener("blur", save);
}

async function addInsumo(pid) {
  if (!insumoSearchSelected) { alert("Selecciona un recurso primero"); return; }
  try {
    await api("POST", `/partidas/${pid}/insumos`, { recurso_id: insumoSearchSelected.id, cantidad: 1.0 });
    insumoSearchSelected = null;
    await loadInsumos(pid);
    await refreshTotals();
  } catch (err) {
    alert("Error: " + err.message);
  }
}

function editRecursoPrecio(span, tipo) {
  if (span.querySelector("input")) return;
  const rid = span.dataset.rid;
  const prevVal = parseFloat(span.dataset.val) || 0;
  span.innerHTML = `<input type="number" class="inline-qty-input precio-input" value="${prevVal}" min="0" step="0.01" style="width:80px;text-align:right" />`;
  const inp = span.querySelector("input");
  inp.focus(); inp.select();

  let saved = false;
  const save = async () => {
    if (saved) return;
    saved = true;
    const newVal = parseFloat(inp.value) || 0;
    if (newVal === prevVal) { span.innerHTML = fmt(newVal); span.dataset.val = newVal; return; }
    try {
      await api("PATCH", `/recursos/${rid}/precio`, { precio_unitario: newVal });
      span.innerHTML = fmt(newVal);
      span.dataset.val = newVal;
      // Update cache
      const allRec = Object.values(recursosCache).flat();
      const r = allRec.find(x => x.id === rid);
      if (r) r.precio_unitario = newVal;
    } catch (err) {
      span.innerHTML = fmt(prevVal);
      alert("Error: " + err.message);
    }
  };
  inp.addEventListener("keydown", (e) => {
    if (e.key === "Enter") inp.blur();
    if (e.key === "Escape") { saved = true; span.innerHTML = fmt(prevVal); }
  });
  inp.addEventListener("blur", save);
}

function setupInsumoSearch() {
  const searchInput = document.getElementById("insumo-search");
  const dropdown    = document.getElementById("insumo-dropdown");
  const selLabel    = document.getElementById("insumo-selected-label");

  let debounce = null;
  searchInput.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      const raw = searchInput.value.trim();
      if (!raw) {
        dropdown.classList.add("hidden");
        insumoSearchSelected = null;
        selLabel.textContent = "—";
        return;
      }
      const q = raw.toLowerCase();
      const allRec = Object.values(recursosCache).flat();

      // Exact clave match → auto-select, no dropdown
      const exact = allRec.find(r => r.clave.toLowerCase() === q);
      if (exact) {
        insumoSearchSelected = exact;
        selLabel.textContent = exact.descripcion;
        dropdown.classList.add("hidden");
        return;
      }

      // Partial match → show dropdown
      insumoSearchSelected = null;
      selLabel.textContent = "—";
      const matches = allRec.filter(r =>
        r.clave.toLowerCase().includes(q) || r.descripcion.toLowerCase().includes(q)
      ).slice(0, 15);
      if (!matches.length) { dropdown.classList.add("hidden"); return; }
      dropdown.innerHTML = matches.map(r => `
        <div class="insumo-option" data-id="${r.id}">
          <span style="color:${TIPO_COLOR[r.tipo]||'var(--text-dim)'}">${esc(r.clave)}</span>
          <span style="margin-left:8px;flex:1;overflow:hidden;text-overflow:ellipsis">${esc(r.descripcion)}</span>
          <span class="insumo-opt-ud">${esc(r.unidad)}</span>
        </div>`).join("");
      dropdown.classList.remove("hidden");
      dropdown.querySelectorAll(".insumo-option").forEach(opt => {
        opt.addEventListener("mousedown", (e) => {
          e.preventDefault();
          const r = Object.values(recursosCache).flat().find(x => x.id === opt.dataset.id);
          if (!r) return;
          insumoSearchSelected = r;
          searchInput.value = r.clave;
          selLabel.textContent = r.descripcion;
          dropdown.classList.add("hidden");
        });
      });
    }, 150);
  });

  searchInput.addEventListener("blur", () => setTimeout(() => dropdown.classList.add("hidden"), 150));
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      dropdown.classList.add("hidden");
      searchInput.value = "";
      insumoSearchSelected = null;
      selLabel.textContent = "—";
    }
  });

  document.getElementById("btn-add-insumo").addEventListener("click", () => {
    if (currentInsumosPid) addInsumo(currentInsumosPid);
  });
}

function initInsumoSearch(pid) {
  currentInsumosPid = pid;
  insumoSearchSelected = null;
  document.getElementById("insumo-search").value = "";
  document.getElementById("insumo-selected-label").textContent = "—";
  document.getElementById("insumo-dropdown").classList.add("hidden");
}

// [BASES DE DATOS] movido a bases-drawer.js (cargado tras app.js).

// ─── MÓDULO DROPDOWN + SOLDADURA HOJA MATHCAD (Fase B) ──────────────────────

function initModuloDropdown() {
  const sel = document.getElementById("sel-modulo");
  if (!sel) return;
  sel.addEventListener("change", () => setModuloActivo(sel.value));

  // Patch close buttons para resetear el select
  const patchClose = (btnId) => {
    document.getElementById(btnId)?.addEventListener("click", () => {
      const s = document.getElementById("sel-modulo"); if (s) s.value = "";
    });
  };
  patchClose("btn-cerrar-diseno-view");
  patchClose("btn-cerrar-etabs-view");
  patchClose("btn-cerrar-acero-view");
  patchClose("btn-cerrar-conexion-view");
}

function setModuloActivo(m) {
  // Cierra todos los paneles de módulo, abre el solicitado.
  ["diseno", "etabs", "acero", "conexion"].forEach(v => {
    const el = document.getElementById(`${v}-view`);
    if (el) el.style.display = (v === m) ? "flex" : "none";
  });
  const sel = document.getElementById("sel-modulo");
  if (sel) sel.value = m || "";

  if (m === "diseno" && state.activeId) { loadElementos(state.activeId); renderHoja(); }
  if (m === "etabs") etabsPrecargarContexto().then(() => renderEtabs()).catch(() => {});
  if (m === "acero") renderAcero();
  if (m === "conexion") renderConexion();
}


// [DISEÑO/ETABS/ACERO/CONEXION] movido a calculo-estructural.js (cargado tras app.js).
