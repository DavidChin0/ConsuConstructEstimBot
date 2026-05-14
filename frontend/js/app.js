const API = window.__ESTIMASTRUCT_API__ || "http://localhost:8002";

const DIVISIONES_CSI = {
  "00": "Preliminares y Contratos",
  "01": "Requerimientos Generales",
  "02": "Condiciones Existentes",
  "03": "Concreto",
  "04": "Mampostería",
  "05": "Metales",
  "06": "Madera y Carpintería",
  "07": "Protección Térmica e Impermeabilización",
  "08": "Puertas y Ventanas",
  "09": "Acabados",
  "10": "Especialidades",
  "11": "Equipamiento",
  "12": "Mobiliario",
  "21": "Protección contra Incendios",
  "22": "Plomería",
  "23": "HVAC",
  "25": "Iluminación",
  "26": "Eléctrico",
  "27": "Comunicaciones",
  "28": "Seguridad Electrónica",
  "31": "Movimiento de Tierra",
  "32": "Obras Exteriores",
  "33": "Utilidades del Sitio",
};

let state = {
  presupuestos: [],
  activeId: null,
  activeData: null,
  selectedPartida: null,
  collapsedCaps: new Set(),
  showTypeMark: false,
  unidades: [],
  modo: localStorage.getItem("estimastruct.modo") || "cliente",
  templateVersion: localStorage.getItem("estimastruct.template-version") === "v1.0"
    ? "v1.0"
    : "v1.1",
  soldaduras: [],
};

let templateCatalog = {
  "v1.0": { fichas_total: null },
  "v1.1": { fichas_total: null },
};

let loadObrasAttempts = 0;
let loadObrasRetryHandle = null;

// --- UTILS ---
function fmt(n, dec = 2) {
  const num = parseFloat(n) || 0;
  return num.toLocaleString("es-HN", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
async function api(method, path, body = null) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

// --- INIT ---
document.addEventListener("DOMContentLoaded", () => {
  loadObras();
  loadTemplateCatalog();
  document.getElementById("btn-nueva-obra").addEventListener("click", () => openModalObra());
  initExportMenu();
  document.getElementById("btn-actualizar").addEventListener("click", actualizarObra);
  document.getElementById("btn-toggle-typemark").addEventListener("click", toggleTypeMark);
  document.getElementById("btn-modo").addEventListener("click", toggleModo);
  initDevMenu();
  initModalScriptOut();
  initModalAbout();
  initModalCsvPick();
  initModalTemplateVersion();
  initModalBases();
  initModalUpdater();
  initColorPicker();
  applyModoUI();
  loadUnidades();
  initModalObra();
  initModalRename();
  initModalDelete();
  initPanelBottom();
  initPanelTabs();
  initVinetas();
  initSobrecostoPill();
  initSoldaduraView();
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

function renderSidebar() {
  const list = document.getElementById("obras-list");
  const proyectos = state.presupuestos.filter(p => !p.es_template);
  if (!proyectos.length) {
    list.innerHTML = `<div class="empty-state" style="padding:20px;"><p>Sin obras</p><small>Crea una nueva</small></div>`;
    return;
  }
  list.innerHTML = proyectos.map(p => {
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
  applyModoUI(); // re-aplica visibilidad según modo
  // Mostrar sobrecosto pill
  const pill = document.getElementById("sobrecosto-pill");
  pill.classList.remove("hidden");
  const sc = data.config?.sobrecosto ?? 20;
  document.getElementById("sobrecosto-val").textContent = fmt(sc, 1) + "%";
  document.getElementById("sobrecosto-input").value = sc;
}

function updateTotalesHeader(data) {
  document.querySelector(".obra-titulo").textContent = data.nombre;
  const isDev = state.modo === "desarrollador";
  document.querySelector(".totales").innerHTML =
    (isDev ? `<span>Costo Directo: <b>${data.moneda} ${fmt(data.costo_directo)}</b></span>` : "") +
    `<span>Total: <b>${data.moneda} ${fmt(data.total_con_indirectos)}</b></span>`;
}

function updateTemplateVersionBadge(data) {
  const badge = document.getElementById("template-version-badge");
  if (data.config?.template_version) {
    const version = data.config.template_version;
    const versionText = version === "v1.0" ? "V1.0 Original" : "V1.1 Updated";
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
  document.getElementById("btn-actualizar").classList.add("hidden");
  document.getElementById("btn-modo").classList.add("hidden");
  document.getElementById("recursos-bar").classList.add("hidden");
  document.getElementById("sobrecosto-pill").classList.add("hidden");
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
      else if (kind === "db") exportarBaseDatos();
    });
  });
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

// --- TYPE MARK toggle ---
function toggleTypeMark() {
  if (state.modo !== "desarrollador") return;
  state.showTypeMark = !state.showTypeMark;
  document.getElementById("btn-toggle-typemark").classList.toggle("active", state.showTypeMark);
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
  // En cliente: cerrar panel inferior si estaba abierto
  if (!isDev) {
    document.getElementById("panel-bottom").classList.add("hidden");
    state.selectedPartida = null;
  }
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
      if (step === "bases") openModalBases();
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
  }
  document.getElementById("modal-csv-ok").disabled = true;
  delete document.getElementById("modal-csv-pick").dataset.selected;
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

// --- TABLE ---
function renderTable(data) {
  const area = document.getElementById("table-area");
  if (!data.capitulos || !data.capitulos.length) {
    area.innerHTML = buildEmptyWithNueva();
    attachNuevaActividadHandlers(area);
    return;
  }

  const isDev = state.modo === "desarrollador";
  const showTm = isDev && state.showTypeMark;
  // Header conditional
  const tmHeader = showTm ? `<th style="width:90px">Type Mark</th>` : "";
  const headerCells = isDev
    ? `<th style="width:120px">CSI</th>${tmHeader}<th>Descripción</th><th style="width:50px">Ud</th><th class="num" style="width:95px">Cantidad</th><th class="num" style="width:88px">Mano de Obra</th><th class="num" style="width:88px">INSUMOS</th><th class="num" style="width:105px">COSTO DIRECTO</th><th class="num" style="width:110px">PRECIO UNITARIO</th><th class="num" style="width:110px">Total</th>`
    : `<th style="width:120px">CSI</th><th>Descripción</th><th class="num" style="width:95px">Cantidad</th><th class="num" style="width:120px">PRECIO UNITARIO</th><th class="num" style="width:120px">Total</th>`;
  const totalCols = isDev ? (showTm ? 10 : 9) : 5;

  let rows = `
    <table>
      <thead>
        <tr>${headerCells}</tr>
      </thead>
      <tbody>
  `;

  for (const cap of data.capitulos) {
    const collapsed = state.collapsedCaps.has(cap.id);
    // capítulo: primera celda con descripción, última con total, resto vacías
    const middleEmpty = totalCols - 2;
    const capDescColspan = isDev ? (showTm ? 3 : 2) : 2;
    const remainingEmpty = totalCols - capDescColspan - 1; // -1 por la celda de total
    const capDesc = `<td colspan="${capDescColspan}"><span class="toggle">${collapsed ? "▶" : "▼"}</span> <b>${esc(cap.clave)}</b> — ${esc(cap.nombre)}</td>`;
    const capEmpty = "<td></td>".repeat(remainingEmpty);
    rows += `
      <tr class="capitulo-row" data-cap="${cap.id}">
        ${capDesc}
        ${capEmpty}
        <td class="num"><b>${fmt(cap.total)}</b></td>
      </tr>
    `;
    for (const p of cap.partidas) {
      const colorClass = `row-${p.color_tipo || 'blanco'}`;
      const isSelected = p.id === state.selectedPartida?.id;
      const tmCell = showTm
        ? `<td class="tm-cell" data-pid="${p.id}" data-tm="${esc(p.type_mark || "")}" style="font-size:11px;color:var(--text-dim);cursor:pointer" title="Doble-clic para editar">${esc(p.type_mark || "—")}</td>`
        : "";
      const costoDirecto = (parseFloat(p.costo_mo) || 0) + (parseFloat(p.costo_ma) || 0);
      const colorDot = isDev
        ? `<span class="color-dot ${p.color_tipo||'blanco'}" data-pid="${p.id}" title="Cambiar color"></span>`
        : "";
      const cells = isDev ? `
          <td style="font-size:11px;color:var(--text-dim)">${colorDot}${esc(p.clave_csi)}</td>
          ${tmCell}
          <td class="desc-cell" data-pid="${p.id}" data-desc="${esc(p.descripcion || "")}" style="max-width:300px;overflow:hidden;text-overflow:ellipsis;cursor:pointer" title="Doble-clic para editar">${esc(p.descripcion)}</td>
          <td class="ud-cell" data-pid="${p.id}" data-ud="${esc(p.unidad || "")}" style="color:var(--text-dim);cursor:pointer" title="Doble-clic para editar">${esc(p.unidad)}</td>
          <td class="qty-cell ${p.cantidad > 0 ? 'qty-filled' : ''}" data-pid="${p.id}">${p.cantidad > 0 ? fmt(p.cantidad) : "—"}</td>
          <td class="num">${fmt(p.costo_mo)}</td>
          <td class="num">${fmt(p.costo_ma)}</td>
          <td class="num cd-cell">${fmt(costoDirecto)}</td>
          <td class="num pu-cell">${fmt(p.precio_unitario)}</td>
          <td class="num tot-cell ${p.total > 0 ? 'total-filled' : ''}">${p.total > 0 ? fmt(p.total) : "—"}</td>
      ` : `
          <td style="font-size:11px;color:var(--text-dim)">${esc(p.clave_csi)}</td>
          <td style="max-width:380px;overflow:hidden;text-overflow:ellipsis">${esc(p.descripcion)}</td>
          <td class="num ${p.cantidad > 0 ? 'qty-filled' : ''}">${p.cantidad > 0 ? fmt(p.cantidad) : "—"}</td>
          <td class="num pu-cell">${fmt(p.precio_unitario)}</td>
          <td class="num tot-cell ${p.total > 0 ? 'total-filled' : ''}">${p.total > 0 ? fmt(p.total) : "—"}</td>
      `;
      rows += `
        <tr class="partida-row ${colorClass} ${collapsed ? "collapsed" : ""} ${isSelected ? "selected" : ""}"
            data-id="${p.id}" data-cap="${cap.id}">
          ${cells}
        </tr>
      `;
    }
  }

  if (isDev) {
    const naColspan = totalCols - 3; // CSI + Desc + Ud son 3 inputs, resto colspan
    rows += `
        </tbody>
        <tfoot>
          <tr id="row-nueva-act">
            <td><input id="na-csi" class="na-input" placeholder="CSI (opcional)" maxlength="20" /></td>
            ${showTm ? "<td></td>" : ""}
            <td><input id="na-desc" class="na-input" placeholder="Descripción de la actividad" /></td>
            <td><input id="na-ud" class="na-input" placeholder="Ud" list="unidades-list" /></td>
            <td colspan="${naColspan - (showTm ? 1 : 0)}" style="text-align:left;padding-left:8px">
              <button id="btn-na-add" class="btn-primary" style="font-size:11px;padding:3px 10px">+ Añadir</button>
              <span id="na-csi-info"></span>
            </td>
          </tr>
        </tfoot>
      </table>
    `;
  } else {
    rows += `</tbody></table>`;
  }

  area.innerHTML = rows;
  attachTableHandlers(area);
}

function buildEmptyWithNueva() {
  return `
    <table>
      <thead>
        <tr>
          <th style="width:120px">CSI</th><th>Descripción</th><th>Ud</th>
          <th>Cantidad</th><th>Mano de Obra</th>
          <th>INSUMOS</th><th>PRECIO UNITARIO</th><th>Total</th>
        </tr>
      </thead>
      <tbody></tbody>
      <tfoot>
        <tr id="row-nueva-act">
          <td><input id="na-csi" class="na-input" placeholder="CSI (opcional)" maxlength="20" /></td>
          <td><input id="na-desc" class="na-input" placeholder="Descripción de la actividad" /></td>
          <td><input id="na-ud" class="na-input" placeholder="Ud" list="unidades-list" /></td>
          <td colspan="5" style="text-align:left;padding-left:8px">
            <button id="btn-na-add" class="btn-primary" style="font-size:11px;padding:3px 10px">+ Añadir</button>
            <span id="na-csi-info"></span>
          </td>
        </tr>
      </tfoot>
    </table>
  `;
}

function attachTableHandlers(area) {
  // Toggle capítulo
  area.querySelectorAll(".capitulo-row").forEach(row => {
    row.addEventListener("click", () => {
      const capId = row.dataset.cap;
      const partRows = area.querySelectorAll(`.partida-row[data-cap="${capId}"]`);
      const toggle = row.querySelector(".toggle");
      if (state.collapsedCaps.has(capId)) {
        state.collapsedCaps.delete(capId);
        partRows.forEach(r => r.classList.remove("collapsed"));
        toggle.textContent = "▼";
      } else {
        state.collapsedCaps.add(capId);
        partRows.forEach(r => r.classList.add("collapsed"));
        toggle.textContent = "▶";
      }
    });
  });

  // Click partida → panel (sólo en desarrollador)
  area.querySelectorAll(".partida-row").forEach(row => {
    row.addEventListener("click", (e) => {
      if (state.modo !== "desarrollador") return;
      if (e.target.classList.contains("qty-cell") || e.target.classList.contains("inline-qty-input")) return;
      // las celdas editables (desc/ud/tm) abren el panel con un click; doble-clic edita
      e.stopPropagation();
      area.querySelectorAll(".partida-row").forEach(r => r.classList.remove("selected"));
      row.classList.add("selected");
      const partida = findPartida(row.dataset.id);
      if (partida) showPanelPartida(partida);
    });
  });

  // Doble-clic en descripción / unidad / type mark
  area.querySelectorAll(".desc-cell").forEach(cell => {
    cell.addEventListener("dblclick", (e) => {
      e.stopPropagation();
      editPartidaDescripcion(cell.dataset.pid, cell.dataset.desc);
    });
  });
  area.querySelectorAll(".ud-cell").forEach(cell => {
    cell.addEventListener("dblclick", (e) => {
      e.stopPropagation();
      editPartidaUnidad(cell.dataset.pid, cell.dataset.ud);
    });
  });
  area.querySelectorAll(".tm-cell").forEach(cell => {
    cell.addEventListener("dblclick", (e) => {
      e.stopPropagation();
      editPartidaTypeMark(cell.dataset.pid, cell.dataset.tm);
    });
  });

  // Inline CANTIDAD edit
  area.querySelectorAll(".qty-cell").forEach(cell => {
    cell.addEventListener("click", (e) => {
      e.stopPropagation();
      if (cell.querySelector("input")) return;
      const pid = cell.dataset.pid;
      const partida = findPartida(pid);
      if (!partida) return;
      const prevVal = partida.cantidad || 0;
      const prevDisplay = prevVal > 0 ? fmt(prevVal) : "—";

      cell.innerHTML = `<input type="number" class="inline-qty-input" value="${prevVal > 0 ? prevVal : ''}" placeholder="0" min="0" step="any" />`;
      const inp = cell.querySelector("input");
      inp.focus();
      inp.select();

      let saved = false;
      const save = async () => {
        if (saved) return;
        saved = true;
        const newVal = parseFloat(inp.value) || 0;
        try {
          const result = await api("PATCH", `/partidas/${pid}/cantidad`, { cantidad: newVal });
          partida.cantidad = result.cantidad;
          partida.total = result.total;
          cell.innerHTML = result.cantidad > 0 ? fmt(result.cantidad) : "—";
          cell.classList.toggle("qty-filled", result.cantidad > 0);
          const row = cell.closest("tr");
          const tCell = row.querySelector(".tot-cell");
          const puCell = row.querySelector(".pu-cell");
          if (tCell) {
            tCell.textContent = result.total > 0 ? fmt(result.total) : "—";
            tCell.classList.toggle("total-filled", result.total > 0);
          }
          if (state.selectedPartida?.id === pid) {
            state.selectedPartida = partida;
            updatePanelValues(partida);
          }
          await refreshTotals();
        } catch (err) {
          cell.innerHTML = prevDisplay;
          alert("Error: " + err.message);
        }
      };

      inp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") inp.blur();
        if (e.key === "Escape") { saved = true; cell.innerHTML = prevDisplay; }
      });
      inp.addEventListener("blur", save);
    });
  });

  attachNuevaActividadHandlers(area);
}

function _inferCSIClient(csi, desc) {
  // Mirror of csi_utils.py — for live preview only
  const PREFIX_MAP = {
    "GRL":"01","DON":"02","PRM0":"02","ARM":"03","ENC":"03","CM":"03","CON":"03","CONC":"03",
    "GR":"03","P":"03","R":"03","S":"03","V":"03","C":"05","CG":"05","CV":"05","SF":"05",
    "VA":"05","VV":"05","RAI":"05","MD":"06","COA8":"06","AT":"07","COA1":"07","COA9":"07",
    "FB":"07","CW":"08","PM":"08","PP":"08","PT":"08","PV":"08","VP":"08","CEI":"09",
    "CER":"09","FL":"09","PN":"09","WS":"09","SIG":"10","COC":"11","LVA":"11","CLO":"12",
    "ESP":"12","FUR0":"12","MOB":"12","INC":"21","BOM":"22","PB":"22","PB01":"22","PB02":"22",
    "SN":"22","EXB":"23","GAS":"23","HV":"23","DMT":"25","ILU1":"25","CEM":"26","EL":"26",
    "ILU0":"26","TOM0":"26","UPS":"26","COM0":"27","TEL":"27","SEG":"28","EXT":"31",
  };
  const KEYWORD_MAP = [
    [/bomba|pump/i,"22"],[/plomer|sanitari|tuberi|drenaje sanitari/i,"22"],
    [/hvac|climatiz|aire acondicion|ventilac/i,"23"],
    [/el[eé]ctric|iluminac|luminari/i,"26"],[/incendio|rociador|fire/i,"21"],
    [/comunicac|datos|telecom|red inform/i,"27"],
    [/seguridad|c[aá]mara|acceso|alarma/i,"28"],
    [/concreto|losa|columna|viga|cimentac/i,"03"],
    [/mamposte|bloque|ladrillo|repello|alba[nñ]il/i,"04"],
    [/acero estructural|perfil|joist|deck met/i,"05"],
    [/madera|carpinter/i,"06"],[/impermeabiliz|cubierta|techo lamin/i,"07"],
    [/puerta|ventana|vidrio|aluminio/i,"08"],
    [/pintura|acabado|piso|baldosa|cer[aá]mica|cielo raso/i,"09"],
    [/excavac|relleno|compactac|movimiento de tierra/i,"31"],
    [/pavimento|acera|jardiner|cerca|muro sitio/i,"32"],
    [/agua potable|alcantarill|drenaje pluvial/i,"33"],
  ];
  const prefix = (csi || "").split("-")[0].toUpperCase();
  if (PREFIX_MAP[prefix]) return PREFIX_MAP[prefix];
  for (const [re, div] of KEYWORD_MAP) {
    if (re.test(desc || "")) return div;
  }
  return null;
}

function attachNuevaActividadHandlers(area) {
  const naCSI  = area.querySelector("#na-csi");
  const naDesc = area.querySelector("#na-desc");
  if (!naCSI) return;

  function updateInfo() {
    const csi  = naCSI.value.trim();
    const desc = naDesc ? naDesc.value.trim() : "";
    const info = area.querySelector("#na-csi-info");
    if (!info) return;
    if (csi.length >= 2 && /^\d{2}/.test(csi)) {
      const div = csi.slice(0, 2);
      info.textContent = `→ ${div}: ${DIVISIONES_CSI[div] || "División desconocida"}`;
      info.style.color = "var(--accent2)";
    } else {
      const div = _inferCSIClient(csi, desc);
      if (div) {
        info.textContent = `→ auto: ${div} ${DIVISIONES_CSI[div] || ""}`;
        info.style.color = "var(--text-dim)";
      } else {
        info.textContent = csi ? "→ no reconocido — se asignará a 00" : "opcional — se infiere por descripción";
        info.style.color = "var(--text-dim)";
      }
    }
  }

  naCSI.addEventListener("input", updateInfo);
  if (naDesc) naDesc.addEventListener("input", updateInfo);

  area.querySelector("#btn-na-add")?.addEventListener("click", async () => {
    const csi  = naCSI.value.trim();
    const desc = naDesc?.value.trim();
    const ud   = area.querySelector("#na-ud")?.value.trim();

    if (!desc || !ud) {
      alert("Completa Descripción y Unidad");
      return;
    }
    if (!state.activeId) return;

    const btn = area.querySelector("#btn-na-add");
    btn.disabled = true;
    btn.textContent = "Añadiendo...";
    try {
      await api("POST", "/partidas/nueva-actividad", {
        presupuesto_id: state.activeId,
        clave_csi: csi,
        descripcion: desc,
        unidad: ud,
      });
      await loadObra(state.activeId);
    } catch (err) {
      alert("Error: " + err.message);
      btn.disabled = false;
      btn.textContent = "+ Añadir";
    }
  });
}

function findPartida(id) {
  if (!state.activeData) return null;
  for (const cap of state.activeData.capitulos) {
    const p = cap.partidas.find(p => p.id === id);
    if (p) return p;
  }
  return null;
}

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
  document.getElementById("detail-ma").textContent       = fmt(partida.costo_ma);
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

let recursosCache = {};      // tipo → array
let vinetaActiva = null;
let searchDebounce = null;

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

  // Click en viñeta
  document.querySelectorAll(".vineta").forEach(btn => {
    btn.addEventListener("click", () => toggleVineta(btn.dataset.tipo));
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
    document.querySelectorAll(".vineta").forEach(b => b.classList.remove("active"));
    document.getElementById("recurso-search").value = "";
  });
}

function toggleVineta(tipo) {
  const panel = document.getElementById("recursos-panel-lateral");
  const meta = VINETA_META[tipo];
  if (vinetaActiva === tipo) {
    // Cerrar
    vinetaActiva = null;
    panel.classList.add("hidden");
    document.querySelectorAll(".vineta").forEach(b => b.classList.remove("active"));
    document.getElementById("recurso-search").value = "";
  } else {
    vinetaActiva = tipo;
    document.querySelectorAll(".vineta").forEach(b => {
      b.classList.toggle("active", b.dataset.tipo === tipo);
    });
    // Aplicar color activo al borde de la viñeta
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
  const meta = VINETA_META[vinetaKey];

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
    : `Template V1.1 — Revisado${countLabel}`;
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
  if (v10) {
    const total = templateCatalog["v1.0"]?.fichas_total;
    v10.textContent = total == null ? "V1.0 — Original" : `V1.0 — Original (${total} fichas)`;
  }
  if (v11) {
    const total = templateCatalog["v1.1"]?.fichas_total;
    v11.textContent = total == null ? "V1.1 — Revisado" : `V1.1 — Revisado (${total} fichas)`;
  }
  const labelV10 = document.getElementById("label-v1-0");
  const labelV11 = document.getElementById("label-v1-1");
  if (labelV10) {
    const total = templateCatalog["v1.0"]?.fichas_total;
    const desc = labelV10.querySelector("div div:last-child");
    if (desc) desc.textContent = total == null ? "Datos originales" : `Datos originales (${total} fichas)`;
  }
  if (labelV11) {
    const total = templateCatalog["v1.1"]?.fichas_total;
    const desc = labelV11.querySelector("div div:last-child");
    if (desc) desc.textContent = total == null ? "Versión actualizada" : `Versión actualizada (${total} fichas)`;
  }
}

// --- TEMPLATE VERSION SELECTOR ---
function initModalTemplateVersion() {
  const modal = document.getElementById("modal-template-version");
  const radioButtons = document.querySelectorAll('input[name="template-version"]');
  const versionSelected = document.getElementById("version-selected");
  const labelV10 = document.getElementById("label-v1-0");
  const labelV11 = document.getElementById("label-v1-1");

  // Set initial value
  document.querySelector(`input[value="${state.templateVersion}"]`).checked = true;
  updateVersionDisplay();

  radioButtons.forEach(radio => {
    radio.addEventListener("change", updateVersionDisplay);
  });

  function updateVersionDisplay() {
    const selected = document.querySelector('input[name="template-version"]:checked').value;
    versionSelected.textContent = selected === "v1.0" ? "V1.0" : "V1.1";

    // Update label styles
    labelV10.style.borderColor = selected === "v1.0" ? "var(--accent)" : "var(--border)";
    labelV10.style.backgroundColor = selected === "v1.0" ? "var(--bg-dark)" : "transparent";
    labelV11.style.borderColor = selected === "v1.1" ? "var(--accent)" : "var(--border)";
    labelV11.style.backgroundColor = selected === "v1.1" ? "var(--bg-dark)" : "transparent";
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
  versionSelected.textContent = state.templateVersion === "v1.0" ? "V1.0" : "V1.1";
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
  document.getElementById("detail-ma").textContent      = fmt(p.costo_ma || 0);
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

// --- BASES DE DATOS ---
let basesState = {
  versions: [],
  activeVersion: null,
  fichas: {},          // version → deep-cloned fichas array (editable)
  selectedFichaIdx: null,
  changesCount: 0,
  filterText: "",
  saving: false,
};

const BASES_COLOR_OPTIONS = ["blanco", "rosa", "amarillo", "verde", "azul"];

function getBasesFichas() {
  return basesState.fichas[basesState.activeVersion] || [];
}

function setBasesFichas(fichas) {
  if (!basesState.activeVersion) return;
  basesState.fichas[basesState.activeVersion] = fichas;
}

function compareBasesFichas(a, b) {
  const norm = v => String(v || "").trim();
  return norm(a.csi).localeCompare(norm(b.csi), "es", { numeric: true, sensitivity: "base" }) ||
         norm(a.codigo).localeCompare(norm(b.codigo), "es", { numeric: true, sensitivity: "base" }) ||
         norm(a.descripcion).localeCompare(norm(b.descripcion), "es", { numeric: true, sensitivity: "base" });
}

function refreshBasesDeleteBtn() {
  const btn = document.getElementById("btn-bases-delete");
  if (!btn) return;
  btn.disabled = basesState.selectedFichaIdx === null || basesState.selectedFichaIdx === undefined;
}

function escapeAttr(str) {
  return esc(str).replace(/`/g, "&#96;");
}

function openModalBases() {
  document.getElementById("modal-bases").classList.remove("hidden");
  basesState = { versions: [], activeVersion: null, fichas: {}, selectedFichaIdx: null, changesCount: 0, filterText: "" };
  document.getElementById("bases-search").value = "";
  document.getElementById("bases-version-tabs").innerHTML = "<span style='color:var(--text-dim);font-size:12px'>Cargando...</span>";
  loadBasesVersions();
}

async function loadBasesVersions() {
  try {
    const versions = await api("GET", "/bases");
    basesState.versions = (versions || []).map(v => typeof v === "string" ? { version: v, fichas_total: null } : v);
    renderBasesVersionTabs();
    if (basesState.versions.length) await selectBasesVersion(basesState.versions[0].version);
  } catch (err) {
    document.getElementById("bases-version-tabs").innerHTML = `<span style='color:red;font-size:12px'>${esc(err.message)}</span>`;
  }
}

function renderBasesVersionTabs() {
  const tabs = document.getElementById("bases-version-tabs");
  tabs.innerHTML = basesState.versions.map(v => {
    const label = v.fichas_total == null ? v.version.toUpperCase() : `${v.version.toUpperCase()} (${v.fichas_total})`;
    return `<button class="bases-tab${v.version === basesState.activeVersion ? ' active' : ''}" data-v="${esc(v.version)}">${esc(label)}</button>`;
  }).join("");
  tabs.querySelectorAll(".bases-tab").forEach(btn =>
    btn.addEventListener("click", () => selectBasesVersion(btn.dataset.v))
  );
}

async function selectBasesVersion(version) {
  basesState.activeVersion = version;
  basesState.selectedFichaIdx = null;
  basesState.changesCount = 0;
  renderBasesVersionTabs();
  updateBasesChangesCount();

  if (!basesState.fichas[version]) {
    document.getElementById("bases-fichas-list").innerHTML =
      "<div style='padding:12px;color:var(--text-dim);font-size:12px'>Cargando fichas...</div>";
    try {
      const raw = await api("GET", `/bases/${encodeURIComponent(version)}`);
      basesState.fichas[version] = JSON.parse(JSON.stringify(raw)); // deep clone
    } catch (err) {
      document.getElementById("bases-fichas-list").innerHTML =
        `<div style='padding:12px;color:red;font-size:12px'>${esc(err.message)}</div>`;
      return;
    }
  }
  try {
    const status = await api("GET", `/bases/${encodeURIComponent(version)}/undo-status`);
    updateBasesUndoBtn(status.undo_levels);
  } catch (_) { updateBasesUndoBtn(0); }
  renderBasesLeft();
  renderBasesRight(null);
}

function renderBasesLeft() {
  const fichas = getBasesFichas();
  const q = basesState.filterText.toLowerCase();
  const visible = q
    ? fichas.filter(f =>
        (f.descripcion || "").toLowerCase().includes(q) ||
        (f.codigo || "").toLowerCase().includes(q) ||
        (f.csi || "").toLowerCase().includes(q))
    : fichas;

  const list = document.getElementById("bases-fichas-list");
  list.innerHTML = visible.map(f => {
    const idx  = fichas.indexOf(f);
    const col  = f.color_tipo || 'rosa';
    return `<div class="bases-ficha-item${idx === basesState.selectedFichaIdx ? ' selected' : ''}" data-idx="${idx}">
      <span class="color-dot ${col}" data-bases-idx="${idx}" title="Cambiar color"></span>
      <span class="bases-ficha-csi">${esc(f.csi || '—')}</span>
      <span class="bases-ficha-tm">${esc(f.codigo || '—')}</span>
      <span class="bases-ficha-desc">${esc(f.descripcion || '—')}</span>
      <button class="bases-ficha-del" data-delete-idx="${idx}" title="Eliminar matriz">✕</button>
    </div>`;
  }).join("");

  list.querySelectorAll(".bases-ficha-item").forEach(el => {
    // Color dot click — open picker, update local state only
    const dot = el.querySelector(".color-dot[data-bases-idx]");
    if (dot) {
      dot.addEventListener("click", e => {
        e.stopPropagation();
        const idx    = parseInt(dot.dataset.basesIdx);
        const fichas = basesState.fichas[basesState.activeVersion];
        openColorPicker(dot, color => {
          if (fichas && fichas[idx]) {
            fichas[idx].color_tipo = color;
            basesState.changesCount++;
            updateBasesChangesCount();
            renderBasesLeft();
          }
        });
      });
    }
    // Row click — select ficha
    el.addEventListener("click", () => {
      basesState.selectedFichaIdx = parseInt(el.dataset.idx);
      renderBasesLeft();
      renderBasesRight(basesState.selectedFichaIdx);
    });
  });

  list.querySelectorAll(".bases-ficha-del").forEach(btn => {
    btn.addEventListener("click", async e => {
      e.stopPropagation();
      await deleteBasesFicha(parseInt(btn.dataset.deleteIdx, 10));
    });
  });
}

function renderBasesRight(fichaIdx) {
  const empty  = document.getElementById("bases-ficha-empty");
  const detail = document.getElementById("bases-ficha-detail");
  const delBtn = document.getElementById("btn-bases-delete");
  if (fichaIdx === null || fichaIdx === undefined) {
    empty.classList.remove("hidden");
    detail.classList.add("hidden");
    if (delBtn) delBtn.disabled = true;
    return;
  }
  const fichas = getBasesFichas();
  const ficha  = fichas[fichaIdx];
  if (!ficha) {
    if (delBtn) delBtn.disabled = true;
    return;
  }

  empty.classList.add("hidden");
  detail.classList.remove("hidden");
  if (delBtn) delBtn.disabled = false;

  document.getElementById("bases-ficha-title").innerHTML =
    `<div class="bases-edit-grid">
      <div class="bases-edit-field">
        <label>Color</label>
        <select id="bases-edit-color">
          ${BASES_COLOR_OPTIONS.map(color => `<option value="${color}"${(ficha.color_tipo || "rosa") === color ? " selected" : ""}>${color.charAt(0).toUpperCase() + color.slice(1)}</option>`).join("")}
        </select>
      </div>
      <div class="bases-edit-field">
        <label>Numero CSI</label>
        <input id="bases-edit-csi" type="text" value="${escapeAttr(ficha.csi || "")}" />
      </div>
      <div class="bases-edit-field">
        <label>Type Mark</label>
        <input id="bases-edit-typemark" type="text" value="${escapeAttr(ficha.codigo || "")}" />
      </div>
      <div class="bases-edit-field bases-edit-field-wide">
        <label>Nombre</label>
        <input id="bases-edit-nombre" type="text" value="${escapeAttr(ficha.descripcion || "")}" />
      </div>
    </div>`;

  attachBasesEditHandlers(fichaIdx);

  const insumos = ficha.insumos || [];
  document.getElementById("bases-insumos-body").innerHTML = insumos.map((ins, i) => {
    const total = (parseFloat(ins.cantidad) || 0) * (parseFloat(ins.precioUnitario) || 0);
    return `<tr data-i="${i}">
      <td style="color:var(--text-dim)">${esc(ins.codigo || '—')}</td>
      <td>${esc(ins.descripcion || '—')}</td>
      <td style="color:var(--text-dim)">${esc(ins.unidad || '—')}</td>
      <td><input class="bases-input" type="number" step="any" data-field="cantidad" value="${parseFloat(ins.cantidad) || 0}" /></td>
      <td><input class="bases-input" type="number" step="any" data-field="precioUnitario" value="${parseFloat(ins.precioUnitario) || 0}" /></td>
      <td class="bases-total">${fmt(total)}</td>
    </tr>`; 
  }).join("");

  document.getElementById("bases-insumos-body").querySelectorAll(".bases-input").forEach(inp => {
    inp.addEventListener("change", () => {
      const i     = parseInt(inp.closest("tr").dataset.i);
      const field = inp.dataset.field;
      const val   = parseFloat(inp.value) || 0;
      ficha.insumos[i][field] = val;
      const ins      = ficha.insumos[i];
      const newTotal = (parseFloat(ins.cantidad) || 0) * (parseFloat(ins.precioUnitario) || 0);
      inp.closest("tr").querySelector(".bases-total").textContent = fmt(newTotal);
      basesState.changesCount++;
      updateBasesChangesCount();
    });
  });
}

function attachBasesEditHandlers(fichaIdx) {
  const fichas = getBasesFichas();
  const ficha = fichas[fichaIdx];
  if (!ficha) return;

  const bindInput = (id, key, label, transform = v => v.trim()) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", () => {
      const nuevo = transform(el.value);
      const actual = String(ficha[key] || "");
      if (nuevo === actual) return;
      ficha[key] = nuevo;
      basesState.changesCount++;
      updateBasesChangesCount();
      renderBasesLeft();
      renderBasesRight(fichaIdx);
    });
  };

  const colorEl = document.getElementById("bases-edit-color");
  if (colorEl) {
    colorEl.addEventListener("change", () => {
      const nuevo = colorEl.value || "rosa";
      if (nuevo === (ficha.color_tipo || "rosa")) return;
      ficha.color_tipo = nuevo;
      basesState.changesCount++;
      updateBasesChangesCount();
      renderBasesLeft();
      renderBasesRight(fichaIdx);
    });
  }

  bindInput("bases-edit-csi", "csi", "Numero CSI");
  bindInput("bases-edit-nombre", "descripcion", "Nombre");

  const tmEl = document.getElementById("bases-edit-typemark");
  if (tmEl) {
    tmEl.addEventListener("change", () => {
      const nuevo = tmEl.value.trim();
      const actual = String(ficha.codigo || "").trim();
      if (nuevo === actual) return;
      if (!nuevo) {
        alert("Type Mark no puede quedar vacío.");
        renderBasesRight(fichaIdx);
        return;
      }
      const dup = fichas.some((f, idx) => idx !== fichaIdx && String(f.codigo || "").trim().toLowerCase() === nuevo.toLowerCase());
      if (dup) {
        alert("Ya existe otra matriz con ese Type Mark.");
        renderBasesRight(fichaIdx);
        return;
      }
      ficha.codigo = nuevo;
      basesState.changesCount++;
      updateBasesChangesCount();
      renderBasesLeft();
      renderBasesRight(fichaIdx);
    });
  }
}

function openBasesAddModal() {
  if (!basesState.activeVersion) {
    alert("No hay una base de datos activa.");
    return;
  }
  const modal = document.getElementById("modal-bases-add");
  document.getElementById("bases-new-color").value = "blanco";
  document.getElementById("bases-new-csi").value = "";
  document.getElementById("bases-new-nombre").value = "";
  document.getElementById("bases-new-typemark").value = "";
  modal.classList.remove("hidden");
  setTimeout(() => document.getElementById("bases-new-csi").focus(), 0);
}

function closeBasesAddModal() {
  document.getElementById("modal-bases-add").classList.add("hidden");
}

async function saveBasesNewFicha() {
  if (!basesState.activeVersion) {
    alert("No hay una base de datos activa.");
    return;
  }
  const color = document.getElementById("bases-new-color").value || "blanco";
  const csi = document.getElementById("bases-new-csi").value.trim();
  const nombre = document.getElementById("bases-new-nombre").value.trim();
  const typemark = document.getElementById("bases-new-typemark").value.trim();

  if (!csi || !nombre || !typemark) {
    alert("Completa Color, numero CSI, Nombre y Type Mark.");
    return;
  }

  const fichas = getBasesFichas();
  const typemarkKey = typemark.toLowerCase();
  if (fichas.some(f => String(f.codigo || "").trim().toLowerCase() === typemarkKey)) {
    alert("Ya existe una matriz con ese Type Mark.");
    return;
  }

  const nueva = {
    color_tipo: color,
    csi,
    codigo: typemark,
    descripcion: nombre,
    insumos: [],
  };

  fichas.push(nueva);
  fichas.sort(compareBasesFichas);
  setBasesFichas(fichas);
  basesState.selectedFichaIdx = fichas.indexOf(nueva);
  basesState.changesCount++;
  updateBasesChangesCount();
  renderBasesLeft();
  renderBasesRight(basesState.selectedFichaIdx);
  const ok = await saveBasesChanges("auto-add");
  if (ok) closeBasesAddModal();
}

async function deleteBasesFicha(idx) {
  const fichas = getBasesFichas();
  const ficha = fichas[idx];
  if (!ficha) return;
  if (!confirm(`Esta seguro que quiere eliminar esta matriz?\n\n${ficha.csi || "—"} · ${ficha.codigo || "—"} · ${ficha.descripcion || "—"}`)) {
    return;
  }

  fichas.splice(idx, 1);
  setBasesFichas(fichas);
  basesState.changesCount++;

  if (!fichas.length) {
    basesState.selectedFichaIdx = null;
  } else if (basesState.selectedFichaIdx === idx) {
    basesState.selectedFichaIdx = Math.min(idx, fichas.length - 1);
  } else if (basesState.selectedFichaIdx > idx) {
    basesState.selectedFichaIdx -= 1;
  }

  updateBasesChangesCount();
  renderBasesLeft();
  renderBasesRight(basesState.selectedFichaIdx);
  await saveBasesChanges("auto-delete");
}

function updateBasesUndoBtn(levels) {
  const btn = document.getElementById("btn-bases-undo");
  document.getElementById("bases-undo-levels").textContent = levels;
  btn.disabled = levels === 0;
}

function updateBasesChangesCount() {
  const span = document.getElementById("bases-changes-count");
  const btn  = document.getElementById("btn-bases-save");
  if (basesState.changesCount === 0) {
    span.textContent = "Sin cambios pendientes";
    btn.disabled = true;
  } else {
    span.textContent = `${basesState.changesCount} cambio(s) pendiente(s)`;
    btn.disabled = false;
  }
}

async function saveBasesChanges(source = "manual") {
  const v = basesState.activeVersion;
  if (!v) return;
  if (basesState.saving) return false;
  const fichas = basesState.fichas[v];
  const btn = document.getElementById("btn-bases-save");
  const prevText = btn.textContent;
  basesState.saving = true;
  btn.disabled = true;
  btn.textContent = "Guardando...";
  try {
    const res = await api("POST", `/bases/${encodeURIComponent(v)}/sync`, fichas);
    const refreshed = await api("GET", `/bases/${encodeURIComponent(v)}`);
    basesState.fichas[v] = JSON.parse(JSON.stringify(refreshed));
    showScriptOut(
      "Bases de Datos — Sincronización",
      `✅ Guardado correctamente\n\n` +
      `Versión: ${res.version}\n` +
      `Fichas en JSON: ${res.fichas_en_json}\n` +
      `Presupuestos afectados: ${res.presupuestos_afectados}\n` +
      `Partidas actualizadas: ${res.partidas_actualizadas}\n` +
      `Insumos actualizados: ${res.insumos_actualizados}`,
      "ok"
    );
    basesState.changesCount = 0;
    updateBasesChangesCount();
    updateBasesUndoBtn(res.undo_levels);
    renderBasesLeft();
    renderBasesRight(basesState.selectedFichaIdx != null ? basesState.fichas[v][basesState.selectedFichaIdx] || null : null);
    await loadTemplateCatalog();
    return true;
  } catch (err) {
    showScriptOut("Bases de Datos — Error", err.message || String(err), "error");
    return false;
  } finally {
    basesState.saving = false;
    btn.disabled = false;
    btn.textContent = prevText;
  }
}

function initModalBases() {
  document.getElementById("modal-bases-close").addEventListener("click", () =>
    document.getElementById("modal-bases").classList.add("hidden")
  );
  document.getElementById("btn-bases-add").addEventListener("click", openBasesAddModal);
  document.getElementById("btn-bases-delete").addEventListener("click", async () => {
    if (basesState.selectedFichaIdx === null || basesState.selectedFichaIdx === undefined) return;
    await deleteBasesFicha(basesState.selectedFichaIdx);
  });
  document.getElementById("btn-bases-cancel").addEventListener("click", () =>
    document.getElementById("modal-bases").classList.add("hidden")
  );
  document.getElementById("btn-bases-save").addEventListener("click", saveBasesChanges);
  document.getElementById("btn-bases-undo").addEventListener("click", async () => {
    const v = basesState.activeVersion;
    if (!v) return;
    const btn = document.getElementById("btn-bases-undo");
    btn.disabled = true;
    try {
      const res = await api("POST", `/bases/${encodeURIComponent(v)}/undo`);
      const raw = await api("GET", `/bases/${encodeURIComponent(v)}`);
      basesState.fichas[v] = JSON.parse(JSON.stringify(raw));
      basesState.changesCount = 0;
      updateBasesChangesCount();
      renderBasesLeft();
      renderBasesRight(null);
      updateBasesUndoBtn(res.undo_levels);
    } catch (err) {
      showScriptOut("Deshacer — Error", err.message || String(err), "error");
      updateBasesUndoBtn(0);
    }
  });
  document.getElementById("bases-search").addEventListener("input", e => {
    basesState.filterText = e.target.value.trim();
    renderBasesLeft();
  });
  document.getElementById("modal-bases").addEventListener("click", e => {
    if (e.target === document.getElementById("modal-bases"))
      document.getElementById("modal-bases").classList.add("hidden");
  });
  document.getElementById("btn-bases-dedup").addEventListener("click", async () => {
    const v = basesState.activeVersion;
    if (!v) return;
    if (!confirm(`Configurar repetidos en "${v}"?\n\nFichas con CSI o Type Mark igual reciben sufijo único (-2, .b, etc).\nNo se elimina ninguna ficha. Reversible con Deshacer.`)) return;
    try {
      const res = await api("POST", `/bases/${encodeURIComponent(v)}/dedup`);
      if (res.reasignaciones === 0) {
        alert("Sin duplicados — todas las fichas tienen CSI y Type Mark únicos.");
      } else {
        const detalle = (res.detalle || []).map(d => `  ${d.campo}: "${d.original}" → "${d.nuevo}"`).join("\n");
        alert(`${res.reasignaciones} reasignacion(es) aplicadas:\n${detalle}`);
        const raw = await api("GET", `/bases/${encodeURIComponent(v)}`);
        basesState.fichas[v] = JSON.parse(JSON.stringify(raw));
        basesState.changesCount = 0;
        updateBasesChangesCount();
        updateBasesUndoBtn(1);
        renderBasesLeft();
        renderBasesRight(null);
      }
    } catch (err) {
      alert("Error: " + err.message);
    }
  });
  document.getElementById("modal-bases-add-cancel").addEventListener("click", closeBasesAddModal);
  document.getElementById("modal-bases-add-save").addEventListener("click", saveBasesNewFicha);
  document.getElementById("modal-bases-add").addEventListener("click", e => {
    if (e.target === document.getElementById("modal-bases-add")) closeBasesAddModal();
  });
  ["bases-new-csi", "bases-new-nombre", "bases-new-typemark"].forEach(id => {
    document.getElementById(id).addEventListener("keydown", e => {
      if (e.key === "Enter") saveBasesNewFicha();
      if (e.key === "Escape") closeBasesAddModal();
    });
  });
  document.getElementById("bases-new-color").addEventListener("keydown", e => {
    if (e.key === "Escape") closeBasesAddModal();
  });
}

// --- AGREGAR / ACTUALIZAR FICHAS ---
async function openModalUpdater() {
  const modal = document.getElementById("modal-updater");
  const list  = document.getElementById("updater-pick-list");
  const okBtn = document.getElementById("modal-updater-ok");

  okBtn.disabled = true;
  delete modal.dataset.selected;
  list.innerHTML = "<div style='padding:14px;color:var(--text-dim);text-align:center;font-size:12px'>Cargando...</div>";
  modal.classList.remove("hidden");

  try {
    const data = await api("GET", "/updater/files");
    if (!data.length) {
      list.innerHTML = "<div style='padding:14px;color:var(--text-dim);text-align:center;font-size:12px'>No hay archivos Excel en la carpeta Updater</div>";
      return;
    }
    list.innerHTML = data.map(f => {
      const dt = new Date(f.mtime * 1000).toLocaleString("es-HN");
      return `<div class="csv-pick-item" data-name="${esc(f.name)}">
        <span>${esc(f.name)}</span>
        <span class="csv-pick-meta">${dt} · ${(f.size / 1024).toFixed(1)} KB</span>
      </div>`;
    }).join("");
    list.querySelectorAll(".csv-pick-item").forEach(it => {
      it.addEventListener("click", () => {
        list.querySelectorAll(".csv-pick-item").forEach(x => x.classList.remove("selected"));
        it.classList.add("selected");
        modal.dataset.selected = it.dataset.name;
        okBtn.disabled = false;
      });
    });
  } catch (err) {
    list.innerHTML = `<div style='padding:14px;color:red;font-size:12px'>${esc(err.message)}</div>`;
  }
}

// --- COLOR PICKER ---
let _cpCallback = null;

function openColorPicker(triggerEl, callback) {
  const popup = document.getElementById("color-picker-popup");
  _cpCallback = callback;
  const rect = triggerEl.getBoundingClientRect();
  popup.style.top  = (rect.bottom + 4) + "px";
  popup.style.left = Math.min(rect.left, window.innerWidth - 220) + "px";
  popup.classList.remove("hidden");
}

function initColorPicker() {
  const popup = document.getElementById("color-picker-popup");

  // Table context: delegated click on color-dot that has data-pid
  document.getElementById("table-area").addEventListener("click", e => {
    const dot = e.target.closest(".color-dot[data-pid]");
    if (!dot) return;
    e.stopPropagation();
    const pid = dot.dataset.pid;
    openColorPicker(dot, async color => {
      try {
        await api("PATCH", `/partidas/${pid}/color`, { color_tipo: color });
        dot.className = `color-dot ${color}`;
        const row = dot.closest("tr");
        if (row) row.className = row.className.replace(/\brow-\w+\b/, `row-${color}`);
        if (state.activeData) {
          for (const cap of state.activeData.capitulos || []) {
            const p = (cap.partidas || []).find(x => x.id === pid);
            if (p) { p.color_tipo = color; break; }
          }
        }
      } catch (err) {
        alert("Error al cambiar color: " + err.message);
      }
    });
  });

  // Color choice (shared handler for all contexts)
  popup.querySelectorAll(".cp-item").forEach(item => {
    item.addEventListener("click", () => {
      popup.classList.add("hidden");
      if (_cpCallback) { _cpCallback(item.dataset.color); _cpCallback = null; }
    });
  });

  // Close on outside click
  document.addEventListener("click", e => {
    if (!popup.classList.contains("hidden") && !popup.contains(e.target)) {
      popup.classList.add("hidden");
      _cpCallback = null;
    }
  });
}

async function runSyncColors() {
  showScriptOut("Sincronizar Colores", "Leyendo BaseDatosOpus2026.xlsx...", "running");
  try {
    const res = await api("POST", "/updater/sync-colors");
    const jsonLines = Object.entries(res.json_actualizados || {})
      .map(([v, n]) => `  ${v}: ${n} fichas`).join("\n") || "  (ninguno)";
    showScriptOut(
      "Sincronizar Colores — Resultado",
      `✅ Sincronización completada\n\n` +
      `Colores extraídos del Excel: ${res.colores_extraidos}\n` +
      `Partidas en DB actualizadas: ${res.partidas_actualizadas}\n` +
      `JSONs actualizados:\n${jsonLines}`,
      "ok"
    );
    if (state.activeId) await loadObra(state.activeId);
  } catch (err) {
    showScriptOut("Sincronizar Colores — Error", err.message || String(err), "error");
  }
}

function initModalUpdater() {
  const modal = document.getElementById("modal-updater");

  document.getElementById("modal-updater-cancel").addEventListener("click", () =>
    modal.classList.add("hidden")
  );

  document.getElementById("modal-updater-ok").addEventListener("click", async () => {
    const filename = modal.dataset.selected;
    const version  = document.getElementById("updater-version").value;
    if (!filename) return;

    modal.classList.add("hidden");
    showScriptOut("Agregar Fichas", "Importando fichas desde Excel...", "running");

    try {
      const res = await api("POST", "/updater/import", { filename, version });
      const body =
        `✅ Importación completada\n\n` +
        `Base de datos: ${res.version.toUpperCase()}\n` +
        `Fichas en archivo: ${res.fichas_en_archivo}\n` +
        `Fichas nuevas (${res.agregadas.length}): ${res.agregadas.join(", ") || "ninguna"}\n` +
        `Fichas actualizadas (${res.actualizadas.length}): ${res.actualizadas.join(", ") || "ninguna"}\n` +
        `Total fichas en JSON: ${res.total_en_json}`;
      showScriptOut("Agregar Fichas — Resultado", body, "ok");
      await loadTemplateCatalog();
    } catch (err) {
      showScriptOut("Agregar Fichas — Error", err.message || String(err), "error");
    }
  });
}

// --- SOLDADURAS ESTRUCTURALES ---
function initSoldaduraView() {
  const btnOpen  = document.getElementById("btn-soldadura-view");
  const btnClose = document.getElementById("btn-cerrar-soldadura-view");
  const btnSync  = document.getElementById("btn-sync-soldaduras");
  const btnNueva = document.getElementById("btn-nueva-soldadura");
  const btnCalc  = document.getElementById("btn-calc-todas-soldaduras");

  if (btnOpen) btnOpen.addEventListener("click", () => {
    document.getElementById("soldadura-view").style.display = "flex";
    if (state.activeId) loadSoldaduras(state.activeId);
  });
  if (btnClose) btnClose.addEventListener("click", () => {
    document.getElementById("soldadura-view").style.display = "none";
  });
  if (btnSync) btnSync.addEventListener("click", syncSoldaduras);
  if (btnNueva) btnNueva.addEventListener("click", nuevaSoldaduraConexion);
  if (btnCalc)  btnCalc.addEventListener("click", calcularTodasSoldaduras);
}

async function syncSoldaduras() {
  if (!state.activeId) { alert("Selecciona un proyecto primero."); return; }
  const badge = document.getElementById("soldadura-status-badge");
  if (badge) badge.textContent = "Sincronizando...";
  try {
    const res = await api("POST", `/soldadura-estructural/sync/${state.activeId}`);
    if (res.status === "sin_acero") {
      if (badge) badge.textContent = "Sin vigas/columnas con cantidad > 0";
      return;
    }
    if (badge) badge.textContent = `OK: ${res.conexiones_creadas} creadas, ${res.conexiones_actualizadas} actualizadas`;
    await loadSoldaduras(state.activeId);
    await loadObra(state.activeId);
  } catch (err) {
    if (badge) badge.textContent = "Error: " + err.message;
    alert("Error sync: " + err.message);
  }
}

async function loadSoldaduras(pid) {
  try {
    const res = await api("GET", `/soldadura-estructural/presupuesto/${pid}`);
    state.soldaduras = res.conexiones || [];
    renderSoldaduras(state.soldaduras);
    attachSoldaduraHandlers();
  } catch (err) {
    const wrap = document.getElementById("soldadura-tabla-wrap");
    if (wrap) wrap.innerHTML = `<div style="padding:12px;color:red;font-size:12px">${esc(err.message)}</div>`;
  }
}

function renderSoldaduras(conexiones) {
  const tbody = document.getElementById("soldadura-body");
  if (!tbody) return;

  tbody.innerHTML = conexiones.map((item, i) => renderSoldaduraRow(item, i + 1)).join("");

  const totalesDiv = document.getElementById("soldadura-totales");
  if (totalesDiv && conexiones.length > 0) {
    const costTotal = conexiones.reduce((s, c) => s + (parseFloat(c.costo_total) || 0), 0);
    const pesTotal = conexiones.reduce((s, c) => s + (parseFloat(c.peso_electrodo_kg) || 0), 0);
    const hhTotal = conexiones.reduce((s, c) => s + (parseFloat(c.horas_hombre) || 0), 0);
    const lrfdPass = conexiones.filter(c => c.cumple_lrfd).length;
    totalesDiv.innerHTML = `
      Totales: <strong>${conexiones.length}</strong> conexiones |
      Costo: <strong>L ${fmt(costTotal)}</strong> |
      Peso electrodo: <strong>${fmt(pesTotal)} kg</strong> |
      HH: <strong>${fmt(hhTotal)}</strong> |
      LRFD OK: <strong style="color:var(--accent)">${lrfdPass}/${conexiones.length}</strong>
    `;
  }
}

function renderSoldaduraRow(item, num) {
  const clase_lrfd = item.cumple_lrfd ? "row-green" : "row-red";
  return `<tr class="${clase_lrfd}" data-sid="${item.id}">
    <td style="color:var(--text-dim)">${num}</td>
    <td>${esc(item.clave_csi_nuevo)}</td>
    <td data-field="type_mark" class="editable">${esc(item.type_mark)}</td>
    <td data-field="clave_csi_origen" class="editable">${esc(item.clave_csi_origen || "—")}</td>
    <td data-field="perfil_w" class="editable">${esc(item.perfil_w)}</td>
    <td data-field="tipo_elemento" class="editable">${esc(item.tipo_elemento)}</td>
    <td data-field="tipo_conexion" class="editable">${esc(item.tipo_conexion)}</td>
    <td data-field="tipo_soldadura" class="editable">${esc(item.tipo_soldadura)}</td>
    <td data-field="tamano_filete" class="editable">${esc(item.tamano_filete)}</td>
    <td data-field="longitud_perfil_m" class="editable-num">${fmt(item.longitud_perfil_m, 4)}</td>
    <td style="color:var(--text-dim)">${fmt(item.longitud_soldadura_m, 4)}</td>
    <td style="color:var(--text-dim)">${fmt(item.peso_electrodo_kg, 4)}</td>
    <td style="color:var(--text-dim)">${fmt(item.horas_hombre, 4)}</td>
    <td data-field="precio_electrodo" class="editable-num">${fmt(item.precio_electrodo, 2)}</td>
    <td data-field="precio_soldador" class="editable-num">${fmt(item.precio_soldador, 2)}</td>
    <td style="color:var(--text-dim)">${fmt(item.costo_material, 2)}</td>
    <td style="color:var(--text-dim)">${fmt(item.costo_mano_obra, 2)}</td>
    <td style="font-weight:600">${fmt(item.costo_total, 2)}</td>
    <td data-field="vu_aplicado" class="editable-num">${fmt(item.vu_aplicado, 4)}</td>
    <td style="color:${item.cumple_lrfd ? "var(--accent)" : "red"};font-weight:600">${item.cumple_lrfd ? "✓" : "✗"}</td>
    <td data-field="notas" class="editable">${esc(item.notas)}</td>
    <td><button class="btn-delete-soldadura" data-sid="${item.id}" style="padding:2px 6px;font-size:11px">✕</button></td>
  </tr>`;
}

function attachSoldaduraHandlers() {
  const tbody = document.getElementById("soldadura-body");
  if (!tbody) return;

  tbody.querySelectorAll("tr").forEach(row => {
    const sid = row.dataset.sid;

    row.querySelectorAll(".editable, .editable-num").forEach(cell => {
      cell.addEventListener("click", async (e) => {
        if (e.target.tagName === "INPUT") return;
        const field = cell.dataset.field;
        const actual = state.soldaduras.find(s => s.id === sid)?.[field] || "";
        const input = document.createElement("input");
        input.type = cell.classList.contains("editable-num") ? "number" : "text";
        input.step = cell.classList.contains("editable-num") ? "any" : "";
        input.value = actual;
        input.style.cssText = "width:100%;padding:4px;font-size:inherit";
        cell.innerHTML = "";
        cell.appendChild(input);
        input.focus();
        input.select();

        const guardar = async () => {
          const nuevo = input.value.trim();
          if (!nuevo && !cell.classList.contains("editable-num")) {
            cell.textContent = "—";
            return;
          }
          try {
            await api("PATCH", `/soldadura-estructural/${sid}`, { [field]: cell.classList.contains("editable-num") ? parseFloat(nuevo) || 0 : nuevo });
            state.soldaduras = (await api("GET", `/soldadura-estructural/presupuesto/${state.activeId}`)).conexiones;
            renderSoldaduras(state.soldaduras);
            attachSoldaduraHandlers();
          } catch (err) {
            alert("Error: " + err.message);
            cell.textContent = actual;
          }
        };

        input.addEventListener("blur", guardar);
        input.addEventListener("keydown", (e) => {
          if (e.key === "Enter") guardar();
          if (e.key === "Escape") { cell.textContent = actual; }
        });
      });
    });

    row.querySelector(".btn-delete-soldadura")?.addEventListener("click", () => deleteSoldadura(sid));
  });

  document.getElementById("btn-nueva-soldadura")?.addEventListener("click", nuevaSoldaduraConexion);
  document.getElementById("btn-calc-todas-soldaduras")?.addEventListener("click", calcularTodasSoldaduras);
}

async function nuevaSoldaduraConexion() {
  const type_mark = prompt("Type Mark (ej: SC-001):");
  if (!type_mark) return;
  try {
    await api("POST", `/soldadura-estructural/presupuesto/${state.activeId}`, {
      type_mark: type_mark.trim(),
      clave_csi_nuevo: "05 12 00.01",
      perfil_w: "W8x48",
      longitud_perfil_m: 1,
    });
    await loadSoldaduras(state.activeId);
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function calcularTodasSoldaduras() {
  if (!state.soldaduras.length) return;
  try {
    for (const s of state.soldaduras) {
      await api("POST", `/soldadura-estructural/${s.id}/calcular`);
    }
    await loadSoldaduras(state.activeId);
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function deleteSoldadura(sid) {
  if (!confirm("Eliminar esta conexión?")) return;
  try {
    await api("DELETE", `/soldadura-estructural/${sid}`);
    await loadSoldaduras(state.activeId);
  } catch (err) {
    alert("Error: " + err.message);
  }
}
