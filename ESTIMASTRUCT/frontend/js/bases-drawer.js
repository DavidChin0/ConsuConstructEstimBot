// bases-drawer.js — Editor de Bases de Datos (rendimientos/precios de fichas V1.x).
// Cargado DESPUES de app.js. Scope global clasico: usa state/api/esc/bus (core) y helpers de app.js.

// --- BASES DE DATOS ---
let basesState = {
  versions: [],
  activeVersion: null,
  fichas: {},          // version → deep-cloned fichas array (editable)
  selectedFichaIdx: null,
  collapsedDivs: new Set(),  // divisiones CSI colapsadas en la vista auditoría
  changesCount: 0,
  filterText: "",
  saving: false,
  visible: false,
};

const BASES_COLOR_OPTIONS = ["blanco", "rosa", "amarillo", "verde", "azul"];

// ════════════════════════════════════════════════════════════════════
// LOG DE CAMBIOS MANUALES (debug) — persiste en localStorage, se ve en ⚙ Menú
// ════════════════════════════════════════════════════════════════════
const SESSION_LOG_KEY = "estimastruct_session_log";
const SESSION_LOG_MAX = 2000;
let sessionLog = [];

function loadSessionLog() {
  try { sessionLog = JSON.parse(localStorage.getItem(SESSION_LOG_KEY) || "[]"); }
  catch { sessionLog = []; }
}
function persistSessionLog() {
  try { localStorage.setItem(SESSION_LOG_KEY, JSON.stringify(sessionLog.slice(-SESSION_LOG_MAX))); }
  catch { /* localStorage lleno/no disponible — ignorar */ }
}

// Registra un cambio. area: "BD"|"Presupuesto"|... ; action: verbo corto ; detail: objeto contexto.
function logChange(area, action, detail = {}) {
  const entry = { ts: new Date().toISOString(), area, action, detail };
  sessionLog.push(entry);
  persistSessionLog();
  const modal = document.getElementById("modal-session-log");
  if (modal && !modal.classList.contains("hidden")) renderSessionLog();
  return entry;
}

// Referencia legible de una ficha BD para el log.
function basesFichaRef(ficha) {
  if (!ficha) return "—";
  return `${basesState.activeVersion || "?"} · ${ficha.csi || "—"} · ${ficha.codigo || "—"}`;
}

function formatLogEntry(e) {
  const t = (e.ts || "").replace("T", " ").replace("Z", "").slice(0, 19);
  let d = "";
  if (e.detail && typeof e.detail === "object") {
    const parts = [];
    for (const [k, v] of Object.entries(e.detail)) {
      if (v === undefined || v === null || v === "") continue;
      parts.push(`${k}=${typeof v === "object" ? JSON.stringify(v) : v}`);
    }
    d = parts.join("  ");
  } else if (e.detail) {
    d = String(e.detail);
  }
  return `[${t}] ${e.area} · ${e.action}${d ? " — " + d : ""}`;
}

function sessionLogToText() {
  return sessionLog.map(formatLogEntry).join("\n");
}

function renderSessionLog() {
  const box = document.getElementById("session-log-body");
  const count = document.getElementById("session-log-count");
  if (!box) return;
  if (count) count.textContent = `${sessionLog.length} evento(s)`;
  if (!sessionLog.length) {
    box.innerHTML = `<div style="padding:14px;color:var(--text-dim);font-size:12px">Sin cambios registrados en esta sesión.</div>`;
    return;
  }
  // más reciente arriba
  box.innerHTML = sessionLog.slice().reverse().map(e => {
    const t = (e.ts || "").replace("T", " ").replace("Z", "").slice(11, 19);
    let d = "";
    if (e.detail && typeof e.detail === "object") {
      const parts = [];
      for (const [k, v] of Object.entries(e.detail)) {
        if (v === undefined || v === null || v === "") continue;
        parts.push(`<span class="slog-k">${esc(k)}</span>=<span class="slog-v">${esc(typeof v === "object" ? JSON.stringify(v) : String(v))}</span>`);
      }
      d = parts.join(" · ");
    } else if (e.detail) { d = esc(String(e.detail)); }
    return `<div class="slog-row">
      <span class="slog-ts">${esc(t)}</span>
      <span class="slog-area slog-area-${esc((e.area || "").toLowerCase())}">${esc(e.area || "")}</span>
      <span class="slog-act">${esc(e.action || "")}</span>
      <span class="slog-det">${d}</span>
    </div>`;
  }).join("");
}

function openSessionLogModal() {
  const modal = document.getElementById("modal-session-log");
  if (!modal) return;
  renderSessionLog();
  modal.classList.remove("hidden");
}
function closeSessionLogModal() {
  document.getElementById("modal-session-log")?.classList.add("hidden");
}

function initSessionLogModal() {
  loadSessionLog();
  document.getElementById("modal-session-log-close")?.addEventListener("click", closeSessionLogModal);
  document.getElementById("modal-session-log")?.addEventListener("click", e => {
    if (e.target === document.getElementById("modal-session-log")) closeSessionLogModal();
  });
  document.getElementById("btn-session-log-copy")?.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(sessionLogToText()); }
    catch { /* fallback: seleccionar no disponible */ }
    const btn = document.getElementById("btn-session-log-copy");
    const orig = btn.textContent; btn.textContent = "✓ Copiado";
    setTimeout(() => { btn.textContent = orig; }, 1200);
  });
  document.getElementById("btn-session-log-download")?.addEventListener("click", () => {
    const blob = new Blob([sessionLogToText()], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    a.href = url; a.download = `estimastruct_log_${stamp}.txt`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  document.getElementById("btn-session-log-clear")?.addEventListener("click", () => {
    if (!confirm("¿Borrar todo el log de cambios de esta sesión?")) return;
    sessionLog = [];
    persistSessionLog();
    renderSessionLog();
  });
}

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
  const disabled = basesState.selectedFichaIdx === null || basesState.selectedFichaIdx === undefined;
  const delBtn = document.getElementById("btn-bases-delete");
  if (delBtn) delBtn.disabled = disabled;
  const dupBtn = document.getElementById("btn-bases-dup");
  if (dupBtn) dupBtn.disabled = disabled;
}

function escapeAttr(str) {
  return esc(str).replace(/`/g, "&#96;");
}

function updateBasesToggleLabel(open) {
  const btn = document.getElementById("btn-bases-sidebar");
  if (!btn) return;
  btn.textContent = open ? "Bases de Datos ▾" : "Bases de Datos ▸";
}

async function showBasesDrawer() {
  const drawer = document.getElementById("bases-drawer");
  const content = document.getElementById("content-wrapper");
  if (!drawer || !content) return;
  drawer.classList.remove("hidden");
  content.classList.add("hidden");
  basesState.visible = true;
  updateBasesToggleLabel(true);
  document.getElementById("bases-search").value = "";
  basesState.filterText = "";
  if (!basesState.versions.length) {
    document.getElementById("bases-version-tabs").innerHTML = "<span style='color:var(--text-dim);font-size:12px'>Cargando...</span>";
    await loadBasesVersions();
  } else {
    renderBasesVersionTabs();
    if (!basesState.activeVersion) {
      await selectBasesVersion(basesState.versions[0]?.version);
    } else {
      renderBasesTable();
      renderBasesRight(basesState.selectedFichaIdx);
    }
  }
}

function hideBasesDrawer() {
  const drawer = document.getElementById("bases-drawer");
  const content = document.getElementById("content-wrapper");
  if (!drawer || !content) return;
  drawer.classList.add("hidden");
  content.classList.remove("hidden");
  basesState.visible = false;
  updateBasesToggleLabel(false);
}

function toggleBasesDrawer() {
  if (!state.modo || state.modo !== "desarrollador") return;
  if (basesState.visible) hideBasesDrawer();
  else showBasesDrawer();
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
  if (!tabs) return;
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
  basesState.collapsedDivs = new Set();
  basesState.changesCount = 0;
  renderBasesVersionTabs();
  updateBasesChangesCount();

  if (!basesState.fichas[version]) {
    document.getElementById("bases-table-area").innerHTML =
      "<div style='padding:12px;color:var(--text-dim);font-size:12px'>Cargando fichas...</div>";
    try {
      const raw = await api("GET", `/bases/${encodeURIComponent(version)}`);
      basesState.fichas[version] = JSON.parse(JSON.stringify(raw)); // deep clone
    } catch (err) {
      document.getElementById("bases-table-area").innerHTML =
        `<div style='padding:12px;color:red;font-size:12px'>${esc(err.message)}</div>`;
      return;
    }
  }
  try {
    const status = await api("GET", `/bases/${encodeURIComponent(version)}/undo-status`);
    updateBasesUndoBtn(status.undo_levels);
  } catch (_) { updateBasesUndoBtn(0); }
  renderBasesTable();
  renderBasesRight(null);  // no auto-abrir panel; el usuario clickea una fila
}

// ── Vista auditoría BD — espejo del editor de presupuesto ──
// Deriva tipo de insumo por prefijo de código (MO- = mano de obra).
// Tipo de un insumo: usa `tipo` si la ficha lo trae (insumos agregados desde catálogo),
// si no lo deriva por prefijo de código (MO- = mano de obra). Acepta objeto insumo o código.
function basesInsumoTipo(ins) {
  const t = (ins && typeof ins === "object") ? ins.tipo : null;
  if (t) return String(t).toUpperCase() === "MANO_OBRA" ? "MANO_OBRA" : "INSUMOS";
  const cod = (ins && typeof ins === "object") ? ins.codigo : ins;
  return /^MO/i.test(String(cod || "").trim()) ? "MANO_OBRA" : "INSUMOS";
}

// Suma costos de una ficha desde sus insumos (rendimiento × P.unitario).
function basesFichaCostos(ficha) {
  let mo = 0, ma = 0;
  for (const ins of ficha.insumos || []) {
    const t = (parseFloat(ins.cantidad) || 0) * (parseFloat(ins.precioUnitario) || 0);
    if (basesInsumoTipo(ins) === "MANO_OBRA") mo += t; else ma += t;
  }
  return { mo, ma, base: mo + ma };
}

// División CSI (2 primeros dígitos) para agrupar como capítulos.
function basesDivision(csi) {
  const m = String(csi || "").trim().match(/^(\d{2})/);
  return m ? m[1] : "00";
}

// En el template NO hay sobrecosto: precio unitario = costo directo (base).
// El sobrecosto se aplica por-proyecto al crear la obra (base × (1+SC%)), así que
// el precio_unitario de la ficha debe seguir a sus insumos. Solo se auto-sincroniza
// si hay insumos; sin insumos queda como valor manual (fallback de costo).
function basesSyncPrecioUnitario(ficha) {
  if ((ficha.insumos || []).length > 0) {
    ficha.precio_unitario = basesFichaCostos(ficha).base;
  }
}

// Precio unitario a MOSTRAR: si la ficha tiene insumos = costo directo en vivo
// (refleja la realidad aunque el precio_unitario guardado esté stale); sin insumos
// = el precio_unitario guardado (valor manual).
function basesPrecioUnitario(ficha) {
  if ((ficha.insumos || []).length > 0) return basesFichaCostos(ficha).base;
  return parseFloat(ficha.precio_unitario) || 0;
}

// Alias: los callers legacy llaman renderBasesLeft() → ahora renderiza la tabla agrupada.
function renderBasesLeft() {
  renderBasesTable();
}

// Tabla agrupada por división CSI (capítulos colapsables), filas = fichas.
function renderBasesTable() {
  const area = document.getElementById("bases-table-area");
  if (!area) return;
  const fichas = getBasesFichas();

  if (!fichas.length) {
    area.innerHTML = `<div class="empty-state"><p>Base de datos vacía</p><small>Usa + para agregar una matriz</small></div>`;
    return;
  }

  const q = basesState.filterText.toLowerCase();
  const matches = f => !q ||
    (f.descripcion || "").toLowerCase().includes(q) ||
    (f.codigo || "").toLowerCase().includes(q) ||
    (f.csi || "").toLowerCase().includes(q);

  // Fichas ya vienen ordenadas por CSI desde el backend → agrupar consecutivas por división.
  const groups = [];
  let cur = null;
  fichas.forEach((f, idx) => {
    if (!matches(f)) return;
    const div = basesDivision(f.csi);
    if (!cur || cur.div !== div) { cur = { div, items: [] }; groups.push(cur); }
    cur.items.push({ f, idx });
  });

  if (!groups.length) {
    area.innerHTML = `<div class="empty-state"><p>Sin coincidencias</p></div>`;
    return;
  }

  let rows = `<table><thead><tr>
    <th style="width:118px">CSI</th>
    <th style="width:90px">Type Mark</th>
    <th>Descripción</th>
    <th style="width:56px">Ud</th>
    <th class="num" style="width:80px">Cantidad</th>
    <th class="num" style="width:100px">Mano de Obra</th>
    <th class="num" style="width:90px">INSUMOS</th>
    <th class="num" style="width:108px">Costo Directo</th>
    <th class="num" style="width:116px">Precio Unitario</th>
  </tr></thead><tbody>`;

  for (const g of groups) {
    const collapsed = basesState.collapsedDivs.has(g.div);
    const sumPU = g.items.reduce((s, it) => s + basesPrecioUnitario(it.f), 0);
    rows += `<tr class="capitulo-row bases-cap-row" data-div="${esc(g.div)}">
      <td colspan="8"><span class="toggle">${collapsed ? "▶" : "▼"}</span> <b>${esc(g.div)}</b> — ${esc(DIVISIONES_CSI[g.div] || "Otros")} <span style="color:var(--text-dim);font-weight:400;text-transform:none">(${g.items.length})</span></td>
      <td class="num"><b>${fmt(sumPU)}</b></td>
    </tr>`;
    for (const { f, idx } of g.items) {
      const c = basesFichaCostos(f);
      const col = f.color_tipo || "blanco";
      const sel = idx === basesState.selectedFichaIdx ? " selected" : "";
      rows += `<tr class="partida-row row-${col} bases-ficha-row${collapsed ? " collapsed" : ""}${sel}" data-idx="${idx}" data-div="${esc(g.div)}">
        <td style="font-size:11px;color:var(--text-dim)"><span class="color-dot ${col}" data-bases-idx="${idx}" title="Cambiar color"></span>${esc(f.csi || "—")}</td>
        <td class="bases-tm-cell" data-idx="${idx}" style="font-size:11px;color:var(--accent);cursor:pointer" title="Doble-clic para editar">${esc(f.codigo || "—")}</td>
        <td class="bases-desc-cell" data-idx="${idx}" style="cursor:pointer;max-width:380px;overflow:hidden;text-overflow:ellipsis" title="Doble-clic para editar">${esc(f.descripcion || "—")}</td>
        <td style="color:var(--text-dim)">${esc(f.unidad || "—")}</td>
        <td class="num" style="color:var(--text-dim)">0</td>
        <td class="num">${fmt(c.mo)}</td>
        <td class="num">${fmt(c.ma)}</td>
        <td class="num">${fmt(c.base)}</td>
        <td class="num" style="color:var(--accent);font-weight:600">${fmt(basesPrecioUnitario(f))}</td>
      </tr>`;
    }
  }
  rows += `</tbody></table>`;
  area.innerHTML = rows;
  attachBasesTableHandlers(area);
}

function attachBasesTableHandlers(area) {
  // Colapsar/expandir división
  area.querySelectorAll(".bases-cap-row").forEach(row => {
    row.addEventListener("click", () => {
      const div = row.dataset.div;
      if (basesState.collapsedDivs.has(div)) basesState.collapsedDivs.delete(div);
      else basesState.collapsedDivs.add(div);
      renderBasesTable();
    });
  });

  // Color dot — abre picker, muta estado local
  area.querySelectorAll(".color-dot[data-bases-idx]").forEach(dot => {
    dot.addEventListener("click", e => {
      e.stopPropagation();
      const idx = parseInt(dot.dataset.basesIdx);
      const fichas = getBasesFichas();
      openColorPicker(dot, color => {
        if (fichas[idx]) {
          const antes = fichas[idx].color_tipo || "blanco";
          if (color === antes) return;
          fichas[idx].color_tipo = color;
          basesState.changesCount++;
          updateBasesChangesCount();
          logChange("BD", "Editar color", { ficha: basesFichaRef(fichas[idx]), antes, despues: color });
          renderBasesTable();
          if (basesState.selectedFichaIdx === idx) showBasesPanel(idx);
        }
      });
    });
  });

  // Click fila → abre panel inferior con la matriz
  area.querySelectorAll(".bases-ficha-row").forEach(row => {
    row.addEventListener("click", e => {
      if (e.target.closest(".color-dot")) return;
      const idx = parseInt(row.dataset.idx);
      basesState.selectedFichaIdx = idx;
      area.querySelectorAll(".bases-ficha-row").forEach(r => r.classList.remove("selected"));
      row.classList.add("selected");
      refreshBasesDeleteBtn();
      showBasesPanel(idx);
    });
  });

  // Doble-clic descripción / type mark → editar (en memoria)
  area.querySelectorAll(".bases-desc-cell").forEach(cell => {
    cell.addEventListener("dblclick", e => {
      e.stopPropagation();
      basesEditFichaField(parseInt(cell.dataset.idx), "descripcion", "Nombre de la matriz");
    });
  });
  area.querySelectorAll(".bases-tm-cell").forEach(cell => {
    cell.addEventListener("dblclick", e => {
      e.stopPropagation();
      basesEditFichaField(parseInt(cell.dataset.idx), "codigo", "Type Mark");
    });
  });
}

// Alias legacy: renderBasesRight(idx) → abre/cierra el panel inferior.
function renderBasesRight(fichaIdx) {
  const panel  = document.getElementById("bases-panel-bottom");
  if (fichaIdx === null || fichaIdx === undefined) {
    if (panel) panel.classList.add("hidden");
    refreshBasesDeleteBtn();
    return;
  }
  showBasesPanel(fichaIdx);
}

// Panel inferior — encabezado editable + barra info + matriz INSUMOS/MANO DE OBRA.
function showBasesPanel(idx) {
  const fichas = getBasesFichas();
  const ficha  = fichas[idx];
  const panel  = document.getElementById("bases-panel-bottom");
  if (!panel) return;
  if (!ficha) { panel.classList.add("hidden"); refreshBasesDeleteBtn(); return; }

  panel.classList.remove("hidden");
  basesState.selectedFichaIdx = idx;
  refreshBasesDeleteBtn();

  const csiEl  = document.getElementById("bases-edit-csi");
  const tmEl   = document.getElementById("bases-edit-tm");
  const descEl = document.getElementById("bases-edit-desc");
  csiEl.textContent  = ficha.csi || "—";        csiEl.dataset.idx  = idx;
  tmEl.textContent   = ficha.codigo || "—";      tmEl.dataset.idx   = idx;
  descEl.textContent = ficha.descripcion || "—"; descEl.dataset.idx = idx;

  renderBasesMatriz(ficha);
}

function renderBasesMatriz(ficha) {
  const insumos = ficha.insumos || [];
  const insGroup = [], moGroup = [];
  insumos.forEach((ins, i) => {
    (basesInsumoTipo(ins) === "MANO_OBRA" ? moGroup : insGroup).push({ ins, i });
  });

  let n = 1;
  const rowFor = ({ ins, i }) => {
    const cant = parseFloat(ins.cantidad) || 0;
    const pu   = parseFloat(ins.precioUnitario) || 0;
    const tot  = cant * pu;
    return `<tr data-i="${i}">
      <td style="color:var(--text-dim);font-size:11px">${n++}</td>
      <td style="font-size:10px;color:var(--text-dim)">${esc(ins.codigo || "—")}</td>
      <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis">${esc(ins.descripcion || "—")}</td>
      <td style="color:var(--text-dim);font-size:11px">${esc(ins.unidad || "—")}</td>
      <td class="num"><input class="bases-mtz-input" type="number" step="any" data-field="cantidad" value="${cant}" /></td>
      <td class="num"><input class="bases-mtz-input" type="number" step="any" data-field="precioUnitario" value="${pu}" /></td>
      <td class="num bases-mtz-total" style="color:var(--accent2)">${fmt(tot)}</td>
      <td style="text-align:center"><button class="btn-del-insumo" title="Eliminar insumo">✕</button></td>
    </tr>`;
  };

  const grupo = (label, color) =>
    `<tr class="grupo-header"><td colspan="8" style="background:var(--surface2);color:${color};font-weight:700;padding:6px 10px;font-size:11px;letter-spacing:0.5px">${label}</td></tr>`;

  let html = "";
  if (insGroup.length) { html += grupo("INSUMOS", "#56ccf2"); for (const it of insGroup) html += rowFor(it); }
  if (moGroup.length)  { html += grupo("MANO DE OBRA", "#eb5757"); for (const it of moGroup) html += rowFor(it); }
  if (!insumos.length) html = `<tr><td colspan="8" style="text-align:center;color:var(--text-dim);padding:14px;font-size:11px">Sin insumos — usa “＋ Agregar insumo”</td></tr>`;
  document.getElementById("bases-matriz-body").innerHTML = html;

  basesUpdatePanelTotals(ficha);
  attachBasesMatrizHandlers(ficha);
}

function basesUpdatePanelTotals(ficha) {
  const c = basesFichaCostos(ficha);
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set("bases-mt-todos", fmt(c.base));
  set("bases-mt-ma", fmt(c.ma));
  set("bases-mt-mo", fmt(c.mo));
  set("bases-detail-mo", fmt(c.mo));
  set("bases-detail-ma", fmt(c.ma));
  set("bases-detail-base", fmt(c.base));
  set("bases-detail-pu", fmt(basesPrecioUnitario(ficha)));
  set("bases-detail-unidad", ficha.unidad || "—");
}

function attachBasesMatrizHandlers(ficha) {
  document.querySelectorAll("#bases-matriz-body .bases-mtz-input").forEach(inp => {
    inp.addEventListener("change", () => {
      const tr = inp.closest("tr");
      const i  = parseInt(tr.dataset.i);
      if (!ficha.insumos[i]) return;
      const field = inp.dataset.field;
      const val   = parseFloat(inp.value) || 0;
      const antes = parseFloat(ficha.insumos[i][field]) || 0;
      if (val === antes) return;
      ficha.insumos[i][field] = val;
      const ins = ficha.insumos[i];
      const tot = (parseFloat(ins.cantidad) || 0) * (parseFloat(ins.precioUnitario) || 0);
      ins.total = tot;
      tr.querySelector(".bases-mtz-total").textContent = fmt(tot);
      basesState.changesCount++;
      updateBasesChangesCount();
      basesSyncPrecioUnitario(ficha);   // precio unitario sigue al costo directo
      basesUpdatePanelTotals(ficha);
      logChange("BD", field === "cantidad" ? "Editar rendimiento" : "Editar precio unitario", {
        ficha: basesFichaRef(ficha), insumo: ins.codigo, campo: field, antes, despues: val,
        pu_nuevo: ficha.precio_unitario,
      });
      renderBasesTable();   // refresca MO/INSUMOS/Costo Directo de la fila
    });
  });

  // Eliminar insumo de la ficha (en memoria)
  document.querySelectorAll("#bases-matriz-body .btn-del-insumo").forEach(btn => {
    btn.addEventListener("click", () => {
      const i = parseInt(btn.closest("tr").dataset.i);
      deleteBasesInsumo(ficha, i);
    });
  });
}

function deleteBasesInsumo(ficha, i) {
  if (!ficha.insumos || !ficha.insumos[i]) return;
  const ins = ficha.insumos[i];
  if (!confirm(`¿Eliminar insumo de la matriz?\n\n${ins.codigo || "—"} · ${ins.descripcion || "—"}`)) return;
  ficha.insumos.splice(i, 1);
  basesState.changesCount++;
  updateBasesChangesCount();
  basesSyncPrecioUnitario(ficha);   // precio unitario sigue al costo directo
  logChange("BD", "Eliminar insumo", {
    ficha: basesFichaRef(ficha), insumo: ins.codigo, descripcion: ins.descripcion,
    rendimiento: ins.cantidad, precio: ins.precioUnitario, pu_nuevo: ficha.precio_unitario,
  });
  renderBasesMatriz(ficha);
  renderBasesTable();
}

// ── Popup: catálogo de recursos para agregar insumo a la ficha ──
const BASES_INSUMO_GRUPOS = [
  { label: "INSUMOS / MATERIALES", color: "#56ccf2", tipos: ["MATERIAL", "EQUIPO", "SUBCONTRATO", "HERRAMIENTA", "DISEÑO", "FLETE"] },
  { label: "MANO DE OBRA",          color: "#eb5757", tipos: ["MANO_OBRA"] },
];
let basesInsumoRecursos = null;  // cache de /recursos

async function openBasesInsumoModal() {
  if (basesState.selectedFichaIdx === null || basesState.selectedFichaIdx === undefined) {
    alert("Selecciona una matriz primero.");
    return;
  }
  const modal = document.getElementById("modal-bases-insumo");
  modal.classList.remove("hidden");
  cancelBasesCreateRecurso();  // asegurar vista de lista (no el form de crear)
  const search = document.getElementById("bases-insumo-search");
  search.value = "";
  const list = document.getElementById("bases-insumo-list");
  list.innerHTML = "<div style='padding:14px;color:var(--text-dim);font-size:12px'>Cargando recursos...</div>";
  try {
    if (!basesInsumoRecursos) {
      basesInsumoRecursos = (await api("GET", "/recursos")) || [];
    }
    renderBasesInsumoList("");
    setTimeout(() => search.focus(), 0);
  } catch (err) {
    list.innerHTML = `<div style='padding:14px;color:red;font-size:12px'>${esc(err.message)}</div>`;
  }
}

function closeBasesInsumoModal() {
  cancelBasesCreateRecurso();
  document.getElementById("modal-bases-insumo").classList.add("hidden");
}

function renderBasesInsumoList(q) {
  const list = document.getElementById("bases-insumo-list");
  const ql = (q || "").toLowerCase();
  const all = basesInsumoRecursos || [];
  const ficha = getBasesFichas()[basesState.selectedFichaIdx];
  const yaUsados = new Set((ficha?.insumos || []).map(i => String(i.codigo || "").trim().toUpperCase()));

  let html = "";
  for (const g of BASES_INSUMO_GRUPOS) {
    let items = all.filter(r => g.tipos.includes(String(r.tipo || "").toUpperCase()));
    if (ql) items = items.filter(r =>
      (r.clave || "").toLowerCase().includes(ql) || (r.descripcion || "").toLowerCase().includes(ql));
    items.sort((a, b) => String(a.clave || "").localeCompare(String(b.clave || ""), "es", { numeric: true, sensitivity: "base" }));
    if (!items.length) continue;
    html += `<div class="bases-insumo-group" style="color:${g.color}">${g.label} <span style="color:var(--text-dim);font-weight:400">(${items.length})</span></div>`;
    for (const r of items) {
      const usado = yaUsados.has(String(r.clave || "").trim().toUpperCase());
      html += `<div class="bases-insumo-pick${usado ? " usado" : ""}" data-rid="${esc(String(r.id))}">
        <span class="bi-clave" style="color:${g.color}">${esc(r.clave)}</span>
        <span class="bi-desc">${esc(r.descripcion || "—")}</span>
        <span class="bi-ud">${esc(r.unidad || "—")}</span>
        <span class="bi-precio">${usado ? "✓ ya está" : fmt(parseFloat(r.precio_unitario) || 0)}</span>
      </div>`;
    }
  }
  // CTA crear recurso: cuando hay texto y no existe un recurso con esa clave exacta
  const qTrim = (q || "").trim();
  const existeClave = qTrim && all.some(r => String(r.clave || "").trim().toLowerCase() === qTrim.toLowerCase());
  let cta = "";
  if (qTrim && !existeClave) {
    cta = `<div class="bases-insumo-cta">
      No existe un recurso con código <b>${esc(qTrim)}</b>.
      <button type="button" id="bic-open" data-clave="${esc(qTrim)}">➕ Crear recurso «${esc(qTrim)}»</button>
    </div>`;
  }
  if (!html) html = `<div style="padding:14px;color:var(--text-dim);font-size:12px">Sin coincidencias.</div>`;
  list.innerHTML = cta + html;

  document.getElementById("bic-open")?.addEventListener("click", e => {
    openBasesCreateRecurso(e.currentTarget.dataset.clave || qTrim);
  });

  list.querySelectorAll(".bases-insumo-pick:not(.usado)").forEach(el => {
    el.addEventListener("click", () => {
      const r = (basesInsumoRecursos || []).find(x => String(x.id) === el.dataset.rid);
      if (r) addBasesInsumo(r);
    });
  });
}

function addBasesInsumo(r) {
  const ficha = getBasesFichas()[basesState.selectedFichaIdx];
  if (!ficha) return;
  if (!Array.isArray(ficha.insumos)) ficha.insumos = [];
  const clave = String(r.clave || "").trim();
  if (ficha.insumos.some(i => String(i.codigo || "").trim().toUpperCase() === clave.toUpperCase())) {
    alert(`"${clave}" ya está en esta matriz.`);
    return;
  }
  const pu = parseFloat(r.precio_unitario) || 0;
  ficha.insumos.push({
    codigo: clave,
    descripcion: r.descripcion || "",
    unidad: r.unidad || "",
    cantidad: 1,
    precioUnitario: pu,
    total: pu,
    tipo: String(r.tipo || "").toUpperCase(),
  });
  basesState.changesCount++;
  updateBasesChangesCount();
  basesSyncPrecioUnitario(ficha);   // precio unitario sigue al costo directo
  logChange("BD", "Agregar insumo", {
    ficha: basesFichaRef(ficha), insumo: clave, descripcion: r.descripcion,
    tipo: String(r.tipo || "").toUpperCase(), precio: pu, pu_nuevo: ficha.precio_unitario,
  });
  renderBasesMatriz(ficha);
  renderBasesTable();
  renderBasesInsumoList(document.getElementById("bases-insumo-search").value.trim());  // marca como agregado, popup sigue abierto
}

// ── Crear recurso nuevo desde el popup (cuando el código no existe) ──
function guessTipoFromClave(clave) {
  const p = String(clave || "").toUpperCase().trim();
  if (p.startsWith("MO")) return "MANO_OBRA";
  if (p.startsWith("EQ")) return "EQUIPO";
  if (p.startsWith("SC")) return "SUBCONTRATO";
  if (p.startsWith("HER")) return "HERRAMIENTA";
  if (p.startsWith("DIS")) return "DISEÑO";
  if (p.startsWith("FL")) return "FLETE";
  return "MATERIAL";
}

function openBasesCreateRecurso(clave) {
  document.getElementById("bases-insumo-list").classList.add("hidden");
  document.getElementById("bases-insumo-search").classList.add("hidden");
  document.getElementById("bases-insumo-create").classList.remove("hidden");
  document.getElementById("bic-clave").value  = clave || "";
  document.getElementById("bic-tipo").value   = guessTipoFromClave(clave);
  document.getElementById("bic-desc").value   = "";
  document.getElementById("bic-ud").value     = "";
  document.getElementById("bic-precio").value = "";
  setTimeout(() => document.getElementById("bic-desc").focus(), 0);
}

function cancelBasesCreateRecurso() {
  document.getElementById("bases-insumo-create")?.classList.add("hidden");
  document.getElementById("bases-insumo-list")?.classList.remove("hidden");
  document.getElementById("bases-insumo-search")?.classList.remove("hidden");
}

async function saveBasesCreateRecurso() {
  const clave  = document.getElementById("bic-clave").value.trim();
  const tipo   = document.getElementById("bic-tipo").value;
  const desc   = document.getElementById("bic-desc").value.trim();
  const ud     = document.getElementById("bic-ud").value.trim();
  const precio = parseFloat(document.getElementById("bic-precio").value) || 0;
  if (!clave || !desc || !ud) { alert("Completa código, descripción y unidad."); return; }

  const btn = document.getElementById("bic-save");
  const orig = btn.textContent;
  btn.disabled = true; btn.textContent = "Creando...";
  try {
    const nuevo = await api("POST", "/recursos", {
      clave, descripcion: desc, unidad: ud, tipo, precio_unitario: precio,
    });
    // El recurso se persiste de inmediato en el catálogo (DB). Refrescar cache local.
    if (Array.isArray(basesInsumoRecursos)) basesInsumoRecursos.push(nuevo);
    else basesInsumoRecursos = [nuevo];
    ensureUnidad(ud);
    logChange("BD", "Crear recurso (catálogo)", {
      clave: nuevo.clave, tipo: nuevo.tipo, unidad: nuevo.unidad, precio: nuevo.precio_unitario,
    });
    addBasesInsumo(nuevo);              // lo agrega a la matriz actual (cambio pendiente)
    cancelBasesCreateRecurso();
    document.getElementById("bases-insumo-search").value = "";
    renderBasesInsumoList("");
  } catch (err) {
    const msg = (err && err.message) ? err.message : String(err);
    alert("Error al crear recurso: " + msg + (/ya existe/i.test(msg) ? "" : ""));
  } finally {
    btn.disabled = false; btn.textContent = orig;
  }
}

// Edición de campos de cabecera de ficha (en memoria, vía prompt).
function basesEditFichaField(idx, key, label) {
  const fichas = getBasesFichas();
  const ficha  = fichas[idx];
  if (!ficha) return;
  const current = String(ficha[key] || "");
  const nuevo = prompt(`Editar ${label}:`, current);
  if (nuevo === null) return;
  const limpio = nuevo.replace(/_x000D_/g, "").replace(/\r/g, "").trim();
  if (limpio === current.trim()) return;
  if (key === "codigo") {
    if (!limpio) { alert("Type Mark no puede quedar vacío."); return; }
    const dup = fichas.some((f, i) => i !== idx && String(f.codigo || "").trim().toLowerCase() === limpio.toLowerCase());
    if (dup) { alert("Ya existe otra matriz con ese Type Mark."); return; }
  }
  ficha[key] = limpio;
  basesState.changesCount++;
  updateBasesChangesCount();
  logChange("BD", `Editar ${label}`, {
    ficha: `${basesState.activeVersion || "?"} · ${ficha.csi || "—"} · ${ficha.codigo || "—"}`,
    campo: key, antes: current, despues: limpio,
  });
  renderBasesTable();
  showBasesPanel(idx);
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
  logChange("BD", "Agregar ficha", { ficha: basesFichaRef(nueva), nombre: nombre, color });
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

  logChange("BD", "Eliminar ficha", {
    ficha: basesFichaRef(ficha), nombre: ficha.descripcion, insumos: (ficha.insumos || []).length,
  });
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

// Duplica una ficha completa (todos los insumos). Sufijo " (N)" en CSI, Type Mark y descripción.
// Queda como cambio pendiente (no auto-guarda) para que el Director edite antes de sincronizar.
function duplicateBasesFicha(idx) {
  const fichas = getBasesFichas();
  const orig = fichas[idx];
  if (!orig) return;

  const baseCodigo = String(orig.codigo || "TM").trim();
  const exists = c => fichas.some(f => String(f.codigo || "").trim().toLowerCase() === c.trim().toLowerCase());
  let n = 2;
  while (exists(`${baseCodigo} (${n})`)) n++;   // siguiente sufijo libre (normalmente 2)
  const suf = ` (${n})`;

  const copia = JSON.parse(JSON.stringify(orig));   // deep clone → entran todos los insumos
  copia.codigo      = baseCodigo + suf;
  copia.csi         = (orig.csi ? String(orig.csi) : "") + suf;
  copia.descripcion = (orig.descripcion ? String(orig.descripcion) : "") + suf;
  basesSyncPrecioUnitario(copia);   // precio unitario de la copia = costo directo de sus insumos

  fichas.push(copia);
  fichas.sort(compareBasesFichas);
  setBasesFichas(fichas);
  basesState.selectedFichaIdx = fichas.indexOf(copia);
  basesState.collapsedDivs.delete(basesDivision(copia.csi));   // mostrar la copia
  basesState.changesCount++;
  updateBasesChangesCount();
  logChange("BD", "Duplicar ficha", {
    origen: `${orig.csi || "—"} · ${orig.codigo || "—"}`,
    copia: `${copia.csi} · ${copia.codigo}`, insumos: (copia.insumos || []).length,
  });
  renderBasesTable();
  showBasesPanel(basesState.selectedFichaIdx);
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
    logChange("BD", "Guardar y Sincronizar", {
      version: res.version, origen: source,
      fichas_json: res.fichas_en_json, presup_afectados: res.presupuestos_afectados,
      partidas_act: res.partidas_actualizadas, insumos_act: res.insumos_actualizados,
      undo_levels: res.undo_levels,
    });
    basesState.changesCount = 0;
    updateBasesChangesCount();
    updateBasesUndoBtn(res.undo_levels);
    renderBasesLeft();
    renderBasesRight(basesState.selectedFichaIdx ?? null);
    await loadTemplateCatalog();
    return true;
  } catch (err) {
    logChange("BD", "ERROR al sincronizar", { version: v, origen: source, error: err.message || String(err) });
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
    hideBasesDrawer()
  );
  const sidebarBtn = document.getElementById("btn-bases-sidebar");
  if (sidebarBtn) sidebarBtn.addEventListener("click", toggleBasesDrawer);

  // Panel inferior de auditoría: cerrar + edición de cabecera (CSI / Type Mark / Nombre)
  document.getElementById("bases-panel-close")?.addEventListener("click", () => {
    document.getElementById("bases-panel-bottom").classList.add("hidden");
    basesState.selectedFichaIdx = null;
    refreshBasesDeleteBtn();
    renderBasesTable();
  });
  document.getElementById("bases-edit-csi")?.addEventListener("dblclick", e => {
    const idx = parseInt(e.currentTarget.dataset.idx);
    if (!isNaN(idx)) basesEditFichaField(idx, "csi", "Código CSI");
  });
  document.getElementById("bases-edit-tm")?.addEventListener("dblclick", e => {
    const idx = parseInt(e.currentTarget.dataset.idx);
    if (!isNaN(idx)) basesEditFichaField(idx, "codigo", "Type Mark");
  });
  document.getElementById("bases-edit-desc")?.addEventListener("dblclick", e => {
    const idx = parseInt(e.currentTarget.dataset.idx);
    if (!isNaN(idx)) basesEditFichaField(idx, "descripcion", "Nombre de la matriz");
  });

  // Popup catálogo de recursos → agregar insumo
  document.getElementById("btn-bases-add-insumo")?.addEventListener("click", openBasesInsumoModal);
  document.getElementById("modal-bases-insumo-close")?.addEventListener("click", closeBasesInsumoModal);
  document.getElementById("modal-bases-insumo")?.addEventListener("click", e => {
    if (e.target === document.getElementById("modal-bases-insumo")) closeBasesInsumoModal();
  });
  document.getElementById("bases-insumo-search")?.addEventListener("input", e => {
    renderBasesInsumoList(e.target.value.trim());
  });
  document.getElementById("bases-insumo-search")?.addEventListener("keydown", e => {
    if (e.key === "Escape") closeBasesInsumoModal();
  });
  // Form crear recurso nuevo
  document.getElementById("bic-cancel")?.addEventListener("click", cancelBasesCreateRecurso);
  document.getElementById("bic-save")?.addEventListener("click", saveBasesCreateRecurso);
  document.getElementById("bic-clave")?.addEventListener("input", e => {
    document.getElementById("bic-tipo").value = guessTipoFromClave(e.target.value);
  });
  ["bic-desc", "bic-ud", "bic-precio"].forEach(id => {
    document.getElementById(id)?.addEventListener("keydown", e => {
      if (e.key === "Enter") { e.preventDefault(); saveBasesCreateRecurso(); }
      if (e.key === "Escape") cancelBasesCreateRecurso();
    });
  });
  document.getElementById("btn-bases-add").addEventListener("click", openBasesAddModal);
  document.getElementById("btn-bases-dup")?.addEventListener("click", () => {
    if (basesState.selectedFichaIdx === null || basesState.selectedFichaIdx === undefined) return;
    duplicateBasesFicha(basesState.selectedFichaIdx);
  });
  document.getElementById("btn-bases-delete").addEventListener("click", async () => {
    if (basesState.selectedFichaIdx === null || basesState.selectedFichaIdx === undefined) return;
    await deleteBasesFicha(basesState.selectedFichaIdx);
  });
  document.getElementById("btn-bases-cancel").addEventListener("click", () =>
    hideBasesDrawer()
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
      logChange("BD", "Deshacer (undo)", { version: v, fichas_restauradas: res.fichas_restauradas, undo_levels: res.undo_levels });
      renderBasesLeft();
      renderBasesRight(null);
      updateBasesUndoBtn(res.undo_levels);
    } catch (err) {
      logChange("BD", "ERROR al deshacer", { version: v, error: err.message || String(err) });
      showScriptOut("Deshacer — Error", err.message || String(err), "error");
      updateBasesUndoBtn(0);
    }
  });
  document.getElementById("bases-search").addEventListener("input", e => {
    basesState.filterText = e.target.value.trim();
    renderBasesLeft();
  });
  document.getElementById("btn-bases-dedup")?.addEventListener("click", async () => {
    const v = basesState.activeVersion;
    if (!v) return;
    if (!confirm(`Configurar repetidos en "${v}"?\n\nFichas con CSI o Type Mark igual reciben sufijo único (-2, .b, etc).\nNo se elimina ninguna ficha. Reversible con Deshacer.`)) return;
    try {
      const res = await api("POST", `/bases/${encodeURIComponent(v)}/dedup`);
      if (res.reasignaciones === 0) {
        alert("Sin duplicados — todas las fichas tienen CSI y Type Mark únicos.");
      } else {
        const detalle = (res.detalle || []).map(d => `  ${d.campo}: "${d.original}" → "${d.nuevo}"`).join("\n");
        logChange("BD", "Configurar repetidos (dedup)", { version: v, reasignaciones: res.reasignaciones });
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

