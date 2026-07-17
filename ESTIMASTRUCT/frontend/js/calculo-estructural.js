// calculo-estructural.js — Modulos de calculo EstimaStruct (cargado DESPUES de app.js).
// DISEÑO ACI 318-19 + ETABS/CHOC-08 + ACERO AISC 360-16 (D-H) + CONEXION (J).
// Scope global clasico: usa state/api/esc/bus de core.js y helpers de app.js.

// ─── DISEÑO ESTRUCTURAL ACI 318-19 ───────────────────────────────────────────

let disenoState = { elementos: [], activeElemId: null, procCid: null };

function initDisenoView() {
  const btnOpen     = document.getElementById("btn-diseno-view");
  const btnClose    = document.getElementById("btn-cerrar-diseno-view");
  const btnCalcTodo = document.getElementById("btn-diseno-calcular-todo");
  const btnGenTodo  = document.getElementById("btn-diseno-generar-todo");
  const btnNuevo    = document.getElementById("btn-diseno-nuevo-elem");
  const btnGuardar  = document.getElementById("btn-diseno-guardar-geom");
  const btnDelete   = document.getElementById("btn-diseno-delete-elem");
  const btnAgrCaso  = document.getElementById("btn-diseno-agregar-caso");
  const btnCalcElem = document.getElementById("btn-diseno-calc-elem");
  const btnGenElem  = document.getElementById("btn-diseno-generar-elem");
  const btnSync     = document.getElementById("btn-diseno-sync-bases");
  const tipoSel     = document.getElementById("dg-tipo");

  if (btnOpen) btnOpen.addEventListener("click", () => {
    document.getElementById("diseno-view").style.display = "flex";
    if (state.activeId) loadElementos(state.activeId);
    renderHoja();  // hoja Mathcad es el tab por defecto
  });
  if (btnClose) btnClose.addEventListener("click", () => {
    document.getElementById("diseno-view").style.display = "none";
  });

  // Tab switching
  document.querySelectorAll("[data-dtab]").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-dtab]").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const tabName = btn.dataset.dtab;
      document.querySelectorAll(".tab-content[id^='dtab-']").forEach(div => {
        const isActive = div.id === `dtab-${tabName}`;
        div.style.display = isActive ? "" : "none";
        div.classList.toggle("active", isActive);
      });
      if (tabName === "procedimiento") cargarProcedimiento();
      if (tabName === "ayuda") renderAyudaDiseno();
    });
  });

  if (tipoSel) tipoSel.addEventListener("change", () => showGeomFields(tipoSel.value));
  if (btnSync)     btnSync.addEventListener("click", sincronizarBasesV11);
  if (btnNuevo)    btnNuevo.addEventListener("click", crearElemento);
  if (btnGuardar)  btnGuardar.addEventListener("click", guardarGeometria);
  if (btnDelete)   btnDelete.addEventListener("click", eliminarElemento);
  if (btnAgrCaso)  btnAgrCaso.addEventListener("click", agregarCaso);
  if (btnCalcElem) btnCalcElem.addEventListener("click", () => calcularCasos(disenoState.activeElemId));
  if (btnGenElem)  btnGenElem.addEventListener("click",  () => generarPartidasElem(disenoState.activeElemId));
  if (btnCalcTodo) btnCalcTodo.addEventListener("click", calcularTodo);
  if (btnGenTodo)  btnGenTodo.addEventListener("click",  generarTodo);
}

function showGeomFields(tipo) {
  const dprim = document.getElementById("dg-dprim-wrap");
  const bp    = document.getElementById("dg-bp-wrap");
  const tf    = document.getElementById("dg-tf-wrap");
  const lxw   = document.getElementById("dg-lx-wrap");
  const lyw   = document.getElementById("dg-ly-wrap");
  const bw    = document.getElementById("dg-b-wrap");
  const dw    = document.getElementById("dg-d-wrap");

  // Reset: hide conditional fields, show b/d
  [dprim, bp, tf, lxw, lyw].forEach(el => { if (el) el.style.display = "none"; });
  [bw, dw].forEach(el => { if (el) el.style.display = ""; });

  if (tipo === "VIGA_DOBLE") {
    if (dprim) dprim.style.display = "";
  } else if (tipo === "VIGA_T") {
    if (bp) bp.style.display = "";
    if (tf) tf.style.display = "";
  } else if (tipo === "COLUMNA") {
    if (bw) bw.style.display = "none";
    if (dw) dw.style.display = "none";
    if (lxw) lxw.style.display = "";
    if (lyw) lyw.style.display = "";
  }
  showCasoFields(tipo);
}

// Muestra los campos de carga relevantes según el tipo de elemento.
function showCasoFields(tipo) {
  const viga = document.getElementById("dc-viga-fields");
  const col  = document.getElementById("dc-col-fields");
  const esCol = (tipo === "COLUMNA");
  if (viga) viga.style.display = esCol ? "none" : "";
  if (col)  col.style.display  = esCol ? "" : "none";
}

async function loadElementos(pid) {
  try {
    const data = await api("GET", `/diseno/${pid}/elementos`);
    // Módulo Diseño = CONCRETO. Los elementos de ACERO viven en el módulo Acero.
    disenoState.elementos = ((data && data.elementos) || []).filter(e => (e.material_tipo || "CONCRETO") !== "ACERO");
    renderElementos();
    if (disenoState.activeElemId) {
      const still = disenoState.elementos.find(e => e.id === disenoState.activeElemId);
      if (still) selectElemento(still.id);
    } else if (disenoState.elementos.length) {
      selectElemento(disenoState.elementos[0].id);
    } else {
      renderCasos([]);
      renderResultados([]);
    }
  } catch (err) {
    const c = document.getElementById("diseno-elem-items");
    if (c) c.innerHTML = `<div style="padding:8px;font-size:11px;color:red">${esc(err.message)}</div>`;
  }
}

function renderElementos() {
  const container = document.getElementById("diseno-elem-items");
  if (!container) return;
  if (!disenoState.elementos.length) {
    container.innerHTML = `<div style="padding:8px;font-size:11px;color:var(--text-dim)">Sin elementos. Presiona + para agregar.</div>`;
    return;
  }
  const tipoLabel = { VIGA_SIMPLE: "Viga", VIGA_DOBLE: "Viga 2R", VIGA_T: "Viga T", COLUMNA: "Col" };
  container.innerHTML = disenoState.elementos.map(el => {
    const isActive = el.id === disenoState.activeElemId;
    const lbl = tipoLabel[el.tipo] || el.tipo;
    const mk = el.type_mark ? ` · ${esc(el.type_mark)}` : "";
    const isAcero = el.material_tipo === "ACERO";
    const badge = isAcero
      ? `<span style="font-size:9px;background:#5b6bbf;color:#fff;padding:0 4px;border-radius:3px;margin-left:4px">ACERO</span>`
      : "";
    const sub = isAcero
      ? `${lbl}${mk} | ${esc(el.perfil_acero || "—")} · ${esc(el.acero_grado || "A992")} | L=${fmt(el.longitud_m,1)} m`
      : `${lbl}${mk} | L=${fmt(el.longitud_m,1)} m | f'c=${el.fc_kg_cm2}`;
    return `
      <div class="diseno-elem-item${isActive ? " active" : ""}" data-eid="${el.id}"
           style="padding:6px 10px;cursor:pointer;border-bottom:1px solid var(--border);
                  background:${isActive ? "var(--surface2)" : ""};border-radius:3px;margin-bottom:2px">
        <div style="font-weight:600;font-size:13px;font-family:monospace">${esc(el.csi || "—")}${badge}</div>
        <div style="font-size:11px;color:var(--text-dim)">${sub}</div>
      </div>`;
  }).join("");
  container.querySelectorAll(".diseno-elem-item").forEach(div =>
    div.addEventListener("click", () => selectElemento(div.dataset.eid))
  );
}

function selectElemento(eid) {
  disenoState.activeElemId = eid;
  const el = disenoState.elementos.find(e => e.id === eid);
  if (!el) return;

  // Highlight list
  document.querySelectorAll(".diseno-elem-item").forEach(d => {
    const active = d.dataset.eid === eid;
    d.classList.toggle("active", active);
    d.style.background = active ? "var(--surface2)" : "";
  });

  // Mostrar form, ocultar mensaje vacío
  const emptyMsg = document.getElementById("diseno-geom-empty");
  const geomForm = document.getElementById("diseno-geom-form");
  if (emptyMsg) emptyMsg.style.display = "none";
  if (geomForm) geomForm.style.display = "";

  // Populate geometry form
  const setVal = (id, val) => { const el2 = document.getElementById(id); if (el2) el2.value = val ?? ""; };
  setVal("dg-csi",   el.csi        || "");
  setVal("dg-mark",  el.type_mark  || "");
  setVal("dg-tipo",  el.tipo       || "VIGA_SIMPLE");
  setVal("dg-fc",    el.fc_kg_cm2  ?? 210);
  setVal("dg-fy",    el.fy_kg_cm2  ?? 4200);
  setVal("dg-b",     el.b_cm       ?? 0);
  setVal("dg-d",     el.d_cm       ?? 0);
  setVal("dg-dprim", el.d_prima_cm ?? 5);
  setVal("dg-bp",    el.bp_cm      ?? 0);
  setVal("dg-tf",    el.t_cm       ?? 0);
  setVal("dg-lx",    el.lx_cm      ?? 0);
  setVal("dg-ly",    el.ly_cm      ?? 0);
  setVal("dg-long",  el.longitud_m ?? 0);
  setVal("dg-notas", el.notas      || "");
  showGeomFields(el.tipo || "VIGA_SIMPLE");

  renderCasos(el.casos || []);
  renderResultados(el.casos || []);
  disenoState.procCid = null;  // nuevo elemento → procedimiento recalcula caso gobernante
  if (document.querySelector("[data-dtab='procedimiento']")?.classList.contains("active"))
    cargarProcedimiento();
  cargarElementoEnHoja(el);   // carga propiedades del elemento (BD) en la Hoja Mathcad
}

function renderCasos(casos) {
  const tbody = document.getElementById("diseno-casos-body");
  if (!tbody) return;
  if (!casos.length) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:var(--text-dim);padding:8px;font-size:11px">Sin casos. Agrega uno abajo.</td></tr>`;
    return;
  }
  tbody.innerHTML = casos.map(c => `
    <tr data-cid="${c.id}">
      <td style="font-size:12px">${esc(c.nombre || "—")}</td>
      <td style="font-size:12px;text-align:right">${fmt(c.mu_tm, 2)}</td>
      <td style="font-size:12px;text-align:right">${fmt(c.vu_t, 2)}</td>
      <td style="font-size:12px;text-align:right">${fmt(c.tu_tm, 3)}</td>
      <td style="font-size:12px;text-align:right">${fmt(c.nu_t ?? c.pu_t, 2)}</td>
      <td style="font-size:12px;text-align:right">${fmt(c.mu_xx_tm, 2)}</td>
      <td style="font-size:12px;text-align:right">${fmt(c.mu_yy_tm, 2)}</td>
      <td style="text-align:center;font-size:14px">${c.gobierna ? "★" : ""}</td>
      <td><button class="btn-del-caso" data-cid="${c.id}"
            style="padding:1px 5px;font-size:10px;background:none;border:1px solid #e74c3c;
                   color:#e74c3c;border-radius:2px;cursor:pointer">✕</button></td>
    </tr>`).join("");
  tbody.querySelectorAll(".btn-del-caso").forEach(btn =>
    btn.addEventListener("click", () => eliminarCaso(btn.dataset.cid))
  );
}

function renderResultados(casos) {
  const tbody  = document.getElementById("diseno-res-body");
  const advDiv = document.getElementById("diseno-res-advertencias");
  if (!tbody) return;
  const conRes = casos.filter(c => c.resultado);
  if (!conRes.length) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:var(--text-dim);padding:8px;font-size:11px">Sin resultados. Calcula primero.</td></tr>`;
    if (advDiv) advDiv.innerHTML = "";
    return;
  }
  // ACERO LRFD: φRn/DC/cumple por estado gobernante (no As de concreto)
  const _activeEl = disenoState.elementos.find(e => e.id === disenoState.activeElemId);
  if (_activeEl && _activeEl.material_tipo === "ACERO") {
    tbody.innerHTML = conRes.map(c => {
      const r = c.resultado;
      const ok = r.acero_cumple;
      const status = ok ? `<span style="color:var(--accent)">✓ CUMPLE</span>`
                        : `<span style="color:#e74c3c">✗ NO CUMPLE</span>`;
      return `
        <tr class="diseno-res-row" data-cid="${c.id}" title="Clic para ver la hoja LRFD AISC de este caso"
            style="cursor:pointer${c.gobierna ? ';background:var(--surface2);font-weight:600' : ''}">
          <td style="font-size:11px">📖 ${esc(c.nombre || "—")}${c.gobierna ? " ★" : ""}</td>
          <td colspan="9" style="font-size:11px">
            ${esc(r.acero_estado_gob || "—")} · φRn=${fmt(r.acero_phi_rn_gob,2)} · DC=${fmt(r.acero_dc,3)} · ${status}
          </td>
        </tr>`;
    }).join("");
    tbody.querySelectorAll(".diseno-res-row").forEach(tr =>
      tr.addEventListener("click", () => {
        disenoState.procCid = tr.dataset.cid;
        document.querySelector("[data-dtab='procedimiento']")?.click();
      })
    );
    if (advDiv) advDiv.innerHTML = "";
    return;
  }
  tbody.innerHTML = conRes.map(c => {
    const r   = c.resultado;
    const sism = r.ok_sismico ? `<span style="color:var(--accent)">✓</span>` : `<span style="color:#e74c3c">✗</span>`;
    const pg   = r.ok_pg     ? `<span style="color:var(--accent)">✓</span>` : `<span style="color:#e74c3c">✗</span>`;
    return `
      <tr class="diseno-res-row" data-cid="${c.id}" title="Clic para ver la memoria de cálculo de este caso"
          style="cursor:pointer${c.gobierna ? ';background:var(--surface2);font-weight:600' : ''}">
        <td style="font-size:11px">📖 ${esc(c.nombre || "—")}${c.gobierna ? " ★" : ""}</td>
        <td style="font-size:11px;text-align:right">${fmt(r.as_cm2, 2)}</td>
        <td style="font-size:11px;text-align:right">${r.a_prima_cm2 > 0 ? fmt(r.a_prima_cm2, 2) : "—"}</td>
        <td style="font-size:11px;text-align:right">${fmt(r.av_cm2, 4)}</td>
        <td style="font-size:11px;text-align:right">${fmt(r.s_max_cm, 1)}</td>
        <td style="font-size:11px;text-align:right">${fmt(r.concreto_m3, 3)}</td>
        <td style="font-size:11px;text-align:right">${fmt(r.acero_kg, 1)}</td>
        <td style="font-size:11px;text-align:right">${fmt(r.estribos_kg, 1)}</td>
        <td style="font-size:11px;text-align:right">${fmt(r.encofrado_m2, 2)}</td>
        <td style="text-align:center">${sism} ${pg}</td>
      </tr>`;
  }).join("");
  tbody.querySelectorAll(".diseno-res-row").forEach(tr =>
    tr.addEventListener("click", () => {
      disenoState.procCid = tr.dataset.cid;
      document.querySelector("[data-dtab='procedimiento']")?.click();
    })
  );
  const advs = conRes.filter(c => c.resultado.advertencias).map(c => `${c.nombre}: ${c.resultado.advertencias}`);
  if (advDiv) advDiv.innerHTML = advs.length ? "⚠ " + advs.join(" | ") : "";
}

// ── PROCEDIMIENTO: cada fórmula demostrada en notación idéntica al MD (KaTeX) ─

// Render LaTeX → HTML con KaTeX; si falla o no hay latex, cae a monospace.
function kx(latex, fallbackText, display) {
  if (latex && typeof katex !== "undefined") {
    try {
      return katex.renderToString(latex, { throwOnError: true, displayMode: !!display });
    } catch (e) { /* fallback abajo */ }
  }
  const txt = (fallbackText != null ? fallbackText : (latex || ""));
  return `<code style="font-family:monospace;font-size:12px;color:var(--text)">${esc(txt)}</code>`;
}

// Carga (y auto-calcula si hace falta) el procedimiento del caso gobernante del elemento activo.
async function cargarProcedimiento() {
  const panel = document.getElementById("diseno-proc-panel");
  const empty = document.getElementById("diseno-proc-empty");
  if (!panel) return;
  const eid = disenoState.activeElemId;
  const el  = disenoState.elementos.find(e => e.id === eid);
  if (!el) {
    if (empty) { empty.style.display = ""; empty.textContent = "Selecciona un elemento."; }
    panel.innerHTML = ""; return;
  }
  const casos = el.casos || [];
  if (!casos.length) {
    if (empty) { empty.style.display = ""; empty.textContent = "Este elemento no tiene casos de carga. Agrégalos en el tab «Casos de Carga»."; }
    panel.innerHTML = ""; return;
  }
  let conRes = casos.filter(c => c.resultado);
  if (!conRes.length) {
    // auto-calcular todos los casos
    if (empty) { empty.style.display = ""; empty.textContent = "Calculando procedimiento…"; }
    panel.innerHTML = "";
    try {
      for (const c of casos) await api("POST", `/diseno/casos/${c.id}/calcular`);
      await loadElementos(state.activeId);
      const el2 = disenoState.elementos.find(e => e.id === eid);
      conRes = (el2?.casos || []).filter(c => c.resultado);
    } catch (err) {
      if (empty) empty.textContent = "Error calculando: " + err.message;
      return;
    }
  }
  if (!conRes.length) {
    if (empty) { empty.style.display = ""; empty.textContent = "No se pudo calcular ningún caso."; }
    panel.innerHTML = ""; return;
  }
  let cid = disenoState.procCid;
  if (!cid || !conRes.find(c => c.id === cid))
    cid = (conRes.find(c => c.gobierna) || conRes[0]).id;
  disenoState.procCid = cid;
  if (empty) empty.style.display = "none";
  panel.innerHTML = `<div style="color:var(--text-dim);font-size:12px;padding:8px">Cargando procedimiento…</div>`;
  try {
    const m = await api("GET", `/diseno/casos/${cid}/memoria`);
    m._casos = conRes.map(c => ({ id: c.id, nombre: c.nombre, gobierna: c.gobierna }));
    m._activeCid = cid;
    renderProcedimiento(m);
  } catch (err) {
    panel.innerHTML = `<div style="color:#e74c3c;font-size:12px;padding:8px">Error: ${esc(err.message)}</div>`;
  }
}

function renderProcedimiento(m) {
  const panel = document.getElementById("diseno-proc-panel");
  if (!panel) return;
  if (!m || !Array.isArray(m.pasos) || !m.pasos.length) { panel.innerHTML = ""; return; }
  const meta = m.meta || {};
  const tipoLbl = { VIGA_SIMPLE:"Viga Simple", VIGA_DOBLE:"Viga Doble Armada", VIGA_T:"Viga T", COLUMNA:"Columna" }[meta.tipo] || meta.tipo || "";

  const orden = [], grupos = {};
  m.pasos.forEach(p => {
    if (!grupos[p.seccion]) { grupos[p.seccion] = []; orden.push(p.seccion); }
    grupos[p.seccion].push(p);
  });

  const tipoColor = { input:"#56ccf2", intermedio:"#8a94a6", resultado:"#27ae60", check:"#f2c94c", takeoff:"#bb6bd9" };
  const tipoBadge = { input:"DATO", intermedio:"CÁLC", resultado:"RESULT", check:"CHECK", takeoff:"TAKEOFF" };

  const flexMod = { VIGA_SIMPLE:"Módulo A · MD §3", VIGA_DOBLE:"Módulo B · MD §4",
                    VIGA_T:"Módulo C · MD §5", COLUMNA:"Módulo G · MD §9" }[meta.tipo] || "MD §3";
  const flexIntro = meta.tipo === "COLUMNA"
    ? "Flexión de la columna (eje fuerte). El eje neutro biaxial (§9) y Bresler (§11) se resuelven con el acero importado de Revit."
    : "Acero a tensión que pide Mu: K → ρ → As = ρ·b·d, acotado entre As,min y As,max.";
  const SEC = {
    "Materiales":     ["MD §1–2 · ACI 318-19",  "β₁ fija la geometría del bloque de compresión. ρmax = 0.5·ρb es el techo sísmico — si As > ρmax·b·d la sección es insuficiente y hay que ampliar."],
    "Geometría":      ["MD §2",                  "d es el peralte EFECTIVO (fibra comprimida → centroide del acero), no la altura total h. Toda la cuantía depende de d."],
    "Flexión":        [flexMod,                  flexIntro],
    "Cortante":       ["Módulo D · MD §6",       "vc es lo que el concreto absorbe solo. El excedente (v_u − v_c) lo toman los estribos. La axial N_u corrige vc: compresión sube, tracción baja."],
    "Torsión":        ["Módulo E/F · MD §7–8",   "Σx²y es la inercia torsional. At (estribo cerrado) + Al (barra longitudinal) resisten el flujo torsor. Estribo final = Av + 2·At."],
    "Columna":        ["Módulo H/I · MD §10–11", "λ = k·lu/r > 22 → esbelta → δ amplifica el momento. Si Pu ≈ φPc, δ → ∞ (columna inestable). ρg verifica 1%–8% de acero."],
    "Takeoff CSI 03": ["CSI MasterFormat",       "Concreto (m³), encofrado (m²), acero longitudinal (kg +15% empalmes), estribos (kg). Van directo a las partidas 03 10/20/30."],
    "Verificación":   ["MD §12–13",              "Chequeos de falla dúctil (As ≤ ρmax·b·d) y cuantía de columna (1% ≤ ρg ≤ 8%). Si falla alguno el diseño es inválido para zona sísmica."],
  };

  const valorHtml = (p) => {
    if (typeof p.valor === "boolean")
      return p.valor ? `<span style="color:#27ae60;font-weight:700">✓ OK</span>`
                     : `<span style="color:#e74c3c;font-weight:700">✗ FALLA</span>`;
    const u = p.unidad ? ` <span style="color:var(--text-dim);font-weight:400;font-size:12px">${esc(p.unidad)}</span>` : "";
    return `<span style="font-weight:700">${esc(String(p.valor))}</span>${u}`;
  };

  const tagLbl = (t) => `<span style="flex:0 0 auto;width:74px;font-size:8px;font-weight:700;letter-spacing:.5px;color:var(--text-dim);text-transform:uppercase">${t}</span>`;

  const kxRow = (tag, latex, fallback, color) => `
    <div style="display:flex;gap:8px;align-items:center;background:var(--surface2);border:1px solid var(--border);border-radius:4px;padding:6px 9px;margin-bottom:5px;overflow-x:auto">
      ${tagLbl(tag)}
      <span style="flex:1 1 auto;font-size:1.05em;color:${color || 'var(--text)'};min-width:0">${kx(latex, fallback)}</span>
    </div>`;

  const cardHtml = (p) => {
    const col = tipoColor[p.tipo] || "var(--text-dim)";
    const badge = tipoBadge[p.tipo] || "";
    const isInput = p.tipo === "input";
    const hasF = !isInput && !!p.latex;
    const hasS = !isInput && !!p.latex_sub && p.formula !== "—";
    return `
      <div style="border:1px solid ${col}44;border-left:3px solid ${col};border-radius:5px;padding:9px 11px;margin-bottom:8px;background:var(--surface)">
        <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:7px">
          <span style="font-family:monospace;font-weight:700;font-size:18px;color:${col}">${esc(p.simbolo || "")}</span>
          <span style="font-size:12px;color:var(--text)">${esc(p.etiqueta || "")}</span>
          <span style="margin-left:auto;display:flex;gap:6px;align-items:center">
            ${p.referencia && p.referencia !== "—" ? `<span style="font-size:9px;font-weight:700;color:var(--accent);border:1px solid var(--accent);border-radius:8px;padding:1px 7px;white-space:nowrap">${esc(p.referencia)}</span>` : ""}
            <span style="font-size:8px;font-weight:700;letter-spacing:.5px;padding:1px 5px;border-radius:8px;background:${col}22;color:${col};border:1px solid ${col}55">${badge}</span>
          </span>
        </div>
        ${hasF ? kxRow("Fórmula", p.latex, p.formula) : ""}
        ${hasS ? kxRow("Sustitución", p.latex_sub, p.sustitucion, "#bb6bd9") : ""}
        <div style="display:flex;align-items:baseline;gap:8px;margin-top:6px">
          ${tagLbl("Resultado")}
          <span style="font-size:18px">= ${valorHtml(p)}</span>
        </div>
        ${p.descripcion ? `<div style="font-size:11px;color:var(--text-dim);line-height:1.45;margin-top:6px">${esc(p.descripcion)}</div>` : ""}
      </div>`;
  };

  const seccionHtml = (sec, i) => {
    const [mod, intro] = SEC[sec] || ["", ""];
    return `
    <div style="margin-bottom:16px">
      <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:6px;border-bottom:2px solid var(--accent);padding-bottom:4px">
        <span style="font-size:13px;font-weight:700;color:var(--text)">${i + 1}. ${esc(sec)}</span>
        ${mod ? `<span style="font-size:9px;font-weight:700;color:var(--accent);background:var(--surface);border:1px solid var(--accent);border-radius:8px;padding:1px 7px">${esc(mod)}</span>` : ""}
      </div>
      ${intro ? `<div style="font-size:11px;color:var(--text-dim);font-style:italic;margin-bottom:9px;line-height:1.45">${esc(intro)}</div>` : ""}
      ${grupos[sec].map(cardHtml).join("")}
    </div>`;
  };

  const isAceroProc = (disenoState.elementos.find(e => e.id === disenoState.activeElemId) || {}).material_tipo === "ACERO";
  let okS, okP;
  if (isAceroProc) {
    const dcTxt = meta.dc_gobernante != null ? ` (DC=${fmt(meta.dc_gobernante,3)})` : " (sin demanda)";
    okS = meta.cumple ? `<span style="color:#27ae60">✓ LRFD${dcTxt}</span>`
                      : `<span style="color:#e74c3c">✗ LRFD${dcTxt}</span>`;
    okP = meta.estado_gobernante ? ` · gobierna ${esc(meta.estado_gobernante)}` : "";
  } else {
    okS = meta.ok_sismico ? `<span style="color:#27ae60">✓ Sísmico</span>` : `<span style="color:#e74c3c">✗ Sísmico</span>`;
    okP = meta.tipo === "COLUMNA" ? (meta.ok_pg ? ` · <span style="color:#27ae60">✓ ρg</span>` : ` · <span style="color:#e74c3c">✗ ρg</span>`) : "";
  }

  const casos = m._casos || [];
  const selector = casos.length > 1 ? `
    <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:11px">
      <span style="font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:.5px">Caso de carga:</span>
      ${casos.map(c => `<button class="proc-caso-btn" data-cid="${c.id}" style="font-size:11px;padding:2px 10px;border-radius:10px;cursor:pointer;border:1px solid ${c.id === m._activeCid ? 'var(--accent)' : 'var(--border)'};background:${c.id === m._activeCid ? 'var(--accent)' : 'var(--surface2)'};color:${c.id === m._activeCid ? '#1a1a1a' : 'var(--text)'};font-weight:${c.id === m._activeCid ? '700' : '400'}">${esc(c.nombre || '—')}${c.gobierna ? ' ★' : ''}</button>`).join("")}
    </div>` : "";

  const legend = `
    <div style="font-size:10px;color:var(--text-dim);line-height:1.6;padding:7px 10px;background:var(--surface2);border:1px solid var(--border);border-radius:5px;margin-bottom:12px">
      Cada tarjeta demuestra una fórmula como en el MD: <b>símbolo</b> · <b>Fórmula</b> (notación real) · <b>Sustitución</b> numérica · <b>Resultado</b> · <b>Referencia</b> MD §.<br>
      Etiquetas:
      <span style="color:#56ccf2;font-weight:700">DATO</span> entrada ·
      <span style="color:#8a94a6;font-weight:700">CÁLC</span> intermedio ·
      <span style="color:#27ae60;font-weight:700">RESULT</span> resultado ·
      <span style="color:#f2c94c;font-weight:700">CHECK</span> verificación ·
      <span style="color:#bb6bd9;font-weight:700">TAKEOFF</span> cantidad de obra.
    </div>`;

  panel.innerHTML = `
    <div style="border:1px solid var(--accent);border-radius:6px;overflow:hidden">
      <div style="background:var(--surface2);padding:8px 12px;border-bottom:1px solid var(--border)">
        <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">
          <b style="font-size:13px">📐 Procedimiento de Cálculo</b>
          <span style="font-family:monospace;font-size:12px;color:var(--accent)">${esc(meta.csi || "")}</span>
          <span style="font-size:11px">${esc(tipoLbl)}${meta.type_mark ? " · " + esc(meta.type_mark) : ""}</span>
          <span style="font-size:11px;color:var(--text-dim)">${esc(meta.caso_nombre || "")}</span>
        </div>
        <div style="font-size:11px;color:var(--text-dim);margin-top:3px">
          Sección ${esc(meta.seccion || "")} · ${esc(meta.material || "")} · ${okS}${okP}
        </div>
      </div>
      <div style="padding:12px;max-height:620px;overflow-y:auto">
        ${selector}
        ${legend}
        ${orden.map(seccionHtml).join("")}
        <div style="font-size:10px;color:var(--text-dim);text-align:center;padding-top:4px;line-height:1.5">
          ${isAceroProc
            ? "Verificación LRFD <b>AISC 360-16</b> §D–H (miembros de acero). Chequeo cruzado independiente del Steel Frame Design de ETABS.<br>Valores del motor de miembros (sin recálculo)."
            : "Ingeniería inversa de <b>Viga-Colum.xls</b> (ACI 318-71), con factores φ de <b>ACI 318-19</b> para Honduras.<br>Notación idéntica al MD. Valores del motor de cálculo (sin recálculo)."}
        </div>
      </div>
    </div>`;

  panel.querySelectorAll(".proc-caso-btn").forEach(b =>
    b.addEventListener("click", () => { disenoState.procCid = b.dataset.cid; cargarProcedimiento(); }));
}

// ── HOJA DE CÁLCULO estilo Mathcad — una sola hoja, en vivo, sin DB ──────────
const mathcadState = {
  vista: "calculo",
  tipo: "VIGA_SIMPLE", fc: 210, fy: 4200,
  b: 40, d: 54, d_prima: 5, bp: 90, t: 12, lx: 40, ly: 40, L: 6,
  mu: 52, vu: 21, tu: 0, nu: 0, pu: 0, mxx: 0, myy: 0,
  lu: 0, kx: 1, ky: 1, bdx: 0.15, bdy: 0.15, cmx: 1, cmy: 1,
};
let hojaTimer = null;

// Carga las propiedades de un elemento (de la BD) en el estado de la Hoja.
// Los datos de sección/material vienen del elemento; las cargas, de su caso gobernante.
function cargarElementoEnHoja(el) {
  if (!el) return;
  const s = mathcadState, num = (v, d) => { const n = parseFloat(v); return isNaN(n) ? d : n; };
  s.tipo    = el.tipo || "VIGA_SIMPLE";
  s.fc      = num(el.fc_kg_cm2, 210);
  s.fy      = num(el.fy_kg_cm2, 4200);
  s.b       = num(el.b_cm, 0);
  s.d       = num(el.d_cm, 0);
  s.d_prima = num(el.d_prima_cm, 5);
  s.bp      = num(el.bp_cm, 0);
  s.t       = num(el.t_cm, 0);
  s.lx      = num(el.lx_cm, 0);
  s.ly      = num(el.ly_cm, 0);
  s.L       = num(el.longitud_m, 0);
  const caso = (el.casos || []).find(c => c.gobierna) || (el.casos || [])[0] || null;
  s.mu  = caso ? num(caso.mu_tm, 0)  : 0;
  s.vu  = caso ? num(caso.vu_t, 0)   : 0;
  s.tu  = caso ? num(caso.tu_tm, 0)  : 0;
  s.nu  = caso ? num(caso.nu_t, 0)   : 0;
  s.pu  = caso ? num(caso.pu_t, 0)   : 0;
  s.mxx = caso ? num(caso.mu_xx_tm, 0) : 0;
  s.myy = caso ? num(caso.mu_yy_tm, 0) : 0;
  s.lu  = caso ? num(caso.lu_cm, 0)  : 0;
  s.kx  = caso ? num(caso.k_x, 1)    : 1;
  s.ky  = caso ? num(caso.k_y, 1)    : 1;
  s.bdx = caso ? num(caso.bd_x, 0.15) : 0.15;
  s.bdy = caso ? num(caso.bd_y, 0.15) : 0.15;
  s.cmx = caso ? num(caso.cm_x, 1)   : 1;
  s.cmy = caso ? num(caso.cm_y, 1)   : 1;
  s._elemId = el.id;
  s._label  = (el.csi || "") + (el.type_mark ? " · " + el.type_mark : "");
  s._sinCaso = !caso;
  if (document.getElementById("hoja-panel")) renderHoja();
}

const HOJA_SECMOD = {
  "Materiales":"MD §1–2", "Geometría":"MD §2", "Flexión":"MD §3–5", "Cortante":"Módulo D · MD §6",
  "Torsión":"Módulo E/F · MD §7–8", "Columna":"Módulo H/I · MD §10–11",
  "Takeoff CSI 03":"CSI 03", "Verificación":"MD §12–13",
};
// Intro descriptivo por sección (la lógica de cada grupo de fórmulas).
const HOJA_SECDESC = {
  "Materiales":     "β₁ fija el bloque de compresión. ρmax = 0.5·ρb es el techo sísmico — si As > ρmax·b·d, ampliar sección.",
  "Geometría":      "d = peralte EFECTIVO (fibra comprimida → centroide del acero), no la altura total h. Toda la cuantía depende de d.",
  "Flexión":        "K adimensionaliza la demanda → ρ (cuantía) → As = ρ·b·d, acotado entre As,min y As,max. Si K>0.424 la sección es imposible.",
  "Cortante":       "vc lo aporta el concreto; el excedente (v_u − v_c) lo toman los estribos. El axial N_u corrige vc: compresión sube, tracción baja.",
  "Torsión":        "Σx²y = inercia torsional. At (estribo cerrado) + Al (barra longitudinal) resisten el torsor Tu. Estribo final = Av + 2·At.",
  "Columna":        "λ = k·lu/r > 22 → esbelta → δ amplifica Mu. Si Pu ≈ φPc, δ → ∞ (inestable). ρg verifica 1%–8% de acero.",
  "Takeoff CSI 03": "Concreto (m³), encofrado (m²), acero longitudinal (kg +15% empalmes), estribos (kg) → partidas 03 10/20/30.",
  "Verificación":   "Falla dúctil (As ≤ ρmax·b·d) y cuantía de columna (1% ≤ ρg ≤ 8%). Si falla alguno, diseño inválido para zona sísmica.",
};

function hojaBody() {
  const s = mathcadState;
  return {
    tipo: s.tipo, b_cm: s.b, d_cm: s.d, d_prima_cm: s.d_prima, bp_cm: s.bp, t_cm: s.t,
    lx_cm: s.lx, ly_cm: s.ly, fc_kg_cm2: s.fc, fy_kg_cm2: s.fy, longitud_m: s.L,
    mu_tm: s.mu, vu_t: s.vu, tu_tm: s.tu, nu_t: s.nu,
    pu_t: s.pu, mu_xx_tm: s.mxx, mu_yy_tm: s.myy,
    lu_cm: s.lu, k_x: s.kx, k_y: s.ky, bd_x: s.bdx, bd_y: s.bdy, cm_x: s.cmx, cm_y: s.cmy,
  };
}

function hojaInputDefs() {
  const s = mathcadState, esCol = s.tipo === "COLUMNA";
  const geom = [];
  if (esCol) { geom.push(["lx","L_x","cm"], ["ly","L_y","cm"]); }
  else {
    geom.push(["b","b","cm"], ["d","d","cm (h−rec)"]);
    if (s.tipo === "VIGA_DOBLE") geom.push(["d_prima","d'","cm"]);
    if (s.tipo === "VIGA_T") geom.push(["bp","b_p","cm"], ["t","t","cm"]);
  }
  geom.push(["L","L","m"]);
  const cargas = esCol
    ? [["pu","P_u","t"], ["mxx","M_{uxx}","t·m"], ["myy","M_{uyy}","t·m"]]
    : [["mu","M_u","t·m"], ["vu","V_u","t"], ["tu","T_u","t·m"], ["nu","N_u","t"]];
  const esb = esCol
    ? [["lu","l_u","cm"], ["kx","k_x",""], ["ky","k_y",""], ["bdx","\\beta_{dx}",""],
       ["bdy","\\beta_{dy}",""], ["cmx","C_{mx}",""], ["cmy","C_{my}",""]]
    : [];
  return { geom, cargas, esb };
}

function mcInput(key, sym, unit) {
  const v = mathcadState[key];
  return `<div style="display:flex;align-items:center;gap:5px;padding:2px 0">
    <span style="min-width:36px;text-align:right">${kx(sym, sym)}</span>
    <span style="color:var(--accent);font-weight:700">:=</span>
    <input data-mc="${key}" type="number" step="any" value="${v}"
      style="width:80px;background:var(--bg);border:1px solid var(--accent);color:var(--text);padding:2px 5px;border-radius:3px;font-family:monospace;font-weight:600"/>
    <span style="font-size:10px;color:var(--text-dim)">${esc(unit)}</span>
  </div>`;
}

function mcDevLine(p) {
  const result = (typeof p.valor === "boolean")
    ? (p.valor ? `<span style="color:#27ae60;font-weight:700">✓ OK</span>`
               : `<span style="color:#e74c3c;font-weight:700">✗ FALLA</span>`)
    : `<span style="font-weight:700;color:#27ae60">${esc(String(p.valor))}${p.unidad ? ` <span style="color:var(--text-dim);font-weight:400;font-size:.8em">${esc(p.unidad)}</span>` : ""}</span>`;
  const def = p.latex
    ? `<span style="flex:1;min-width:0;overflow-x:auto">${kx(p.latex, p.formula)}</span><span style="color:var(--text-dim)">=</span>`
    : (p.formula && p.formula !== "—"
        ? `<span style="flex:1;min-width:0;font-size:11px;color:var(--text-dim)">${esc(p.formula)}</span><span style="color:var(--text-dim)">=</span>`
        : `<span style="flex:1"></span>`);
  const sub = p.latex_sub
    ? `<div style="margin-left:42px;font-size:.82em;color:var(--text-dim);overflow-x:auto">${kx(p.latex_sub, p.sustitucion)}</div>`
    : "";
  return `<div style="padding:5px 0;border-bottom:1px dashed var(--border)">
    <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">
      <span style="font-weight:700">${kx(p.simbolo, p.simbolo)}</span>
      <span style="color:var(--accent);font-weight:700">:=</span>
      ${def}
      ${result}
    </div>
    ${sub}
    <div style="font-size:10px;color:var(--text-dim);margin-top:1px">${esc(p.etiqueta || "")}${p.referencia && p.referencia !== "—" ? ` · <span style="color:var(--accent)">${esc(p.referencia)}</span>` : ""}</div>
  </div>`;
}

async function recalcHoja() {
  const dev = document.getElementById("hoja-desarrollo");
  const con = document.getElementById("hoja-constantes");
  if (!dev) return;
  let m;
  try { m = await api("POST", "/diseno/memoria-rapida", hojaBody()); }
  catch (err) { dev.innerHTML = `<div style="color:#e74c3c;font-size:12px">Error: ${esc(err.message)}</div>`; return; }
  if (con && Array.isArray(m.constantes))
    con.innerHTML = m.constantes.map(c => `<div title="${esc(c.desc || "")}">${kx(c.latex, c.simbolo)}</div>`).join("");
  const orden = [], grupos = {};
  m.pasos.forEach(p => { if (p.tipo === "input") return; if (!grupos[p.seccion]) { grupos[p.seccion] = []; orden.push(p.seccion); } grupos[p.seccion].push(p); });
  const meta = m.meta || {};
  const okS = meta.ok_sismico ? `<span style="color:#27ae60">✓ Sísmico</span>` : `<span style="color:#e74c3c">✗ Sísmico</span>`;
  const okP = meta.tipo === "COLUMNA" ? (meta.ok_pg ? ` · <span style="color:#27ae60">✓ ρg</span>` : ` · <span style="color:#e74c3c">✗ ρg</span>`) : "";
  dev.innerHTML = `<div style="font-size:11px;color:var(--text-dim);margin-bottom:8px">${esc(meta.seccion || "")} · ${esc(meta.material || "")} · ${okS}${okP}</div>` +
    orden.map((sec, i) => `<div style="margin-bottom:12px">
      <div style="display:flex;align-items:baseline;gap:8px;border-bottom:2px solid var(--accent);padding-bottom:3px;margin-bottom:6px">
        <span style="font-size:12px;font-weight:700">${i + 1}. ${esc(sec)}</span>
        ${HOJA_SECMOD[sec] ? `<span style="font-size:9px;font-weight:700;color:var(--accent);border:1px solid var(--accent);border-radius:8px;padding:1px 7px">${esc(HOJA_SECMOD[sec])}</span>` : ""}
      </div>
      ${HOJA_SECDESC[sec] ? `<div style="font-size:11px;color:var(--text-dim);font-style:italic;margin-bottom:7px;line-height:1.45">${esc(HOJA_SECDESC[sec])}</div>` : ""}
      ${grupos[sec].map(mcDevLine).join("")}
    </div>`).join("");
}

function bindHojaInputs() {
  const fcSel = document.getElementById("mc-fc");
  if (fcSel) fcSel.addEventListener("change", () => { mathcadState.fc = parseFloat(fcSel.value) || 210; recalcHoja(); });
  const fySel = document.getElementById("mc-fy");
  if (fySel) fySel.addEventListener("change", () => { mathcadState.fy = parseFloat(fySel.value) || 4200; recalcHoja(); });
  document.querySelectorAll("#hoja-content input[data-mc]").forEach(inp => {
    inp.addEventListener("input", () => {
      const k = inp.dataset.mc, v = parseFloat(inp.value);
      mathcadState[k] = isNaN(v) ? 0 : v;
      clearTimeout(hojaTimer);
      hojaTimer = setTimeout(recalcHoja, 250);
    });
  });
}

// VISTA 1 — Cálculo en vivo (hoja Mathcad)
function vistaCalculoHTML() {
  const s = mathcadState;
  const { geom, cargas, esb } = hojaInputDefs();
  const selStyle = "background:var(--surface2);border:1px solid var(--accent);color:var(--text);padding:3px 6px;border-radius:3px;font-weight:600";
  const fcOpts = [180,210,240,280,350].map(v => `<option ${v === s.fc ? "selected" : ""}>${v}</option>`).join("");
  const fyOpts = [2800,4200].map(v => `<option ${v === s.fy ? "selected" : ""}>${v}</option>`).join("");
  const colBox = (titulo, items) => `<div style="min-width:160px"><div style="font-size:10px;font-weight:700;color:var(--accent);letter-spacing:.5px;margin-bottom:3px">${titulo}</div>${items}</div>`;
  return `
   <div style="padding:14px 16px;max-width:980px">
     <div style="border:1px solid var(--border);border-radius:5px;padding:8px 11px;margin-bottom:10px;background:var(--surface)">
       <div style="font-size:10px;font-weight:700;color:var(--text-dim);letter-spacing:.5px;margin-bottom:5px">CONSTANTES (fijas)</div>
       <div id="hoja-constantes" style="display:grid;grid-template-columns:repeat(3,1fr);gap:5px 20px;font-size:13px"></div>
     </div>
     <div style="border:1px solid var(--accent);border-radius:5px;padding:9px 12px;margin-bottom:12px;background:var(--surface)">
       <div style="font-size:10px;font-weight:700;color:var(--accent);letter-spacing:.5px;margin-bottom:6px">VARIABLES DE ENTRADA — edita aquí</div>
       <div style="display:flex;gap:26px;flex-wrap:wrap">
         ${colBox("Material", `
           <div style="display:flex;align-items:center;gap:5px;padding:2px 0"><span style="min-width:36px;text-align:right">${kx("f'_c","f'c")}</span><span style="color:var(--accent);font-weight:700">:=</span><select id="mc-fc" style="${selStyle};width:86px">${fcOpts}</select><span style="font-size:10px;color:var(--text-dim)">kg/cm²</span></div>
           <div style="display:flex;align-items:center;gap:5px;padding:2px 0"><span style="min-width:36px;text-align:right">${kx("f_y","fy")}</span><span style="color:var(--accent);font-weight:700">:=</span><select id="mc-fy" style="${selStyle};width:86px">${fyOpts}</select><span style="font-size:10px;color:var(--text-dim)">kg/cm²</span></div>
         `)}
         ${colBox("Geometría", geom.map(([k,sym,u]) => mcInput(k,sym,u)).join(""))}
         ${colBox("Cargas", cargas.map(([k,sym,u]) => mcInput(k,sym,u)).join(""))}
         ${esb.length ? colBox("Esbeltez (0 = corta)", esb.map(([k,sym,u]) => mcInput(k,sym,u)).join("")) : ""}
       </div>
     </div>
     <div style="font-size:11px;font-weight:700;color:var(--text-dim);letter-spacing:.5px;margin-bottom:6px">DESARROLLO — símbolo := fórmula = resultado</div>
     <div id="hoja-desarrollo" style="font-size:14px">cargando…</div>
     <div style="font-size:10px;color:var(--text-dim);text-align:center;margin-top:14px;line-height:1.5">
       Ingeniería inversa de <b>Viga-Colum.xls</b> (ACI 318-71), φ de <b>ACI 318-19</b> (Honduras). Notación idéntica al MD.
     </div>
   </div>`;
}

// VISTA 2 — Cómo usar y aplicar (guía)
function vistaGuiaHTML() {
  const box = (t, body) => `<div style="border:1px solid var(--border);border-radius:5px;padding:10px 13px;margin-bottom:10px;background:var(--surface)">
    <div style="font-size:12px;font-weight:700;color:var(--accent);margin-bottom:5px">${t}</div>
    <div style="font-size:12px;color:var(--text);line-height:1.6">${body}</div></div>`;
  return `<div style="padding:14px 16px;max-width:820px">
    ${box("¿Qué es esta hoja?", `Una calculadora de diseño de concreto reforzado (ACI 318-19, base Viga-Colum.xls) tipo <b>Mathcad</b>: una sola hoja donde las <b>constantes</b> están fijas y tú editas las <b>variables</b>; cada fórmula se demuestra en notación real y todo recalcula al instante.`)}
    ${box("Navegación (dropdown «Vista»)", `Arriba hay 2 dropdowns. <b>Tipo</b> elige el elemento (Viga Simple/Doble/T/Columna) y cambia qué variables se piden. <b>Vista</b> cambia lo que ves:<br>• <b>🧮 Cálculo en vivo</b> — la hoja con fórmulas y resultados.<br>• <b>📖 Cómo usar y aplicar</b> — esta guía.<br>• <b>📦 Aplicar a presupuesto</b> — vuelca las cantidades a partidas CSI 03.`)}
    ${box("¿De dónde salen los datos?", `<b>Nada viene automático de ETABS.</b> Tú lees Mu, Vu, Tu, Nu / Pu, Mxx, Myy en tu análisis (ETABS / SAP / manual) y los <b>escribes</b> en las variables. La geometría (b, d, …) sale de tus planos / predimensionamiento. (La importación automática futura es desde <b>Revit</b>, solo geometría.)`)}
    ${box("Variables de entrada", `<b>Material:</b> f'c, f'y (dropdown).<br><b>Viga:</b> b, d (peralte <b>efectivo</b> = h − recubrimiento, no la altura total), L; cargas Mu, Vu, Tu (0 si no hay), Nu (0 si no hay).<br><b>Columna:</b> Lx, Ly, L; cargas Pu, Mxx, Myy; <b>Esbeltez</b> lu, k, βd, Cm — deja <b>lu = 0</b> si la columna es corta (no amplifica, δ = 1).`)}
    ${box("Cómo leer el resultado", `• <b>${kx("A_s","As")}</b> (cm²) = acero de tensión requerido → eliges varillas que sumen ≥ As.<br>• <b>${kx("A'_s","A's")}</b> = acero de compresión (solo viga doble).<br>• <b>${kx("A_v/S","Av/S")}</b> = área de estribo por separación → defines diámetro y espaciamiento.<br>• <b>${kx("S_{max}","Smax")}</b> = separación máxima de estribos.<br>• <b>✓ Sísmico / ✓ ρg</b> = la sección pasa ductilidad / cuantía. Si sale ✗, cambia la sección.<br>• <b>Takeoff</b> (Vol, Enc, Acl, Aes) = cantidades de obra para el presupuesto.`)}
    ${box("Aplicar a presupuesto", `En la vista <b>📦 Aplicar a presupuesto</b>: con un presupuesto activo, el botón crea el elemento + caso, calcula y genera <b>3 partidas CSI 03</b> con cantidades reales: <b>03 10 00</b> encofrado (m²), <b>03 20 00</b> acero (kg), <b>03 30 00</b> concreto (m³). Requiere <b>L &gt; 0</b>.`)}
    ${box("Norma y alcance", `Fórmulas del XLS original son ACI 318-71; los factores φ se adaptan a <b>ACI 318-19</b> (flexión 0.90, cortante 0.75, columna 0.65) para Honduras (RSHNC). <b>Limitación honesta:</b> la columna se diseña a flexión en el eje fuerte; la interacción biaxial exacta (eje neutro §9, Bresler §11) se resolverá con el acero importado de <b>Revit</b> — está pendiente.`)}
  </div>`;
}

// TAB IZQUIERDO — "Cómo se usa" (guía completa del módulo Diseño)
function renderAyudaDiseno() {
  const panel = document.getElementById("diseno-ayuda-panel");
  if (!panel) return;
  const box = (t, body) => `<div style="border:1px solid var(--border);border-radius:5px;padding:10px 13px;margin-bottom:10px;background:var(--surface)">
    <div style="font-size:12px;font-weight:700;color:var(--accent);margin-bottom:5px">${t}</div>
    <div style="font-size:12px;color:var(--text);line-height:1.6">${body}</div></div>`;
  panel.innerHTML = `<div style="padding:14px 16px">
    <div style="font-size:14px;font-weight:700;margin-bottom:10px">📖 Cómo se usa — Módulo Diseño</div>
    ${box("¿Qué es?", `Diseño de elementos estructurales con <b>hoja de cálculo tipo Mathcad en vivo</b> (siempre visible a la derecha) y gestión por pestañas a la izquierda. Cubre <b>concreto reforzado</b> (ACI 318-19, vigas/columnas) y <b>acero estructural</b> (AISC 360-16 LRFD §D-H, miembros). Cada fórmula se demuestra en notación real; todo recalcula al instante.`)}
    ${box("Layout (split)", `<b>Derecha — Hoja de Cálculo:</b> SIEMPRE visible. Editas variables → resultados al instante. Dropdown <b>Tipo</b> (Viga/Columna) y <b>Vista</b> (🧮 Cálculo · 📦 Aplicar a presupuesto).<br><b>Izquierda — pestañas:</b> Geometría (sección+material), Casos de Carga (combos del análisis), Resultados (As/φRn/DC por caso), Procedimiento (memoria con fórmulas KaTeX), y esta guía.`)}
    ${box("Flujo de trabajo", `1) <b>Genera elementos:</b> crea uno (botón +), importa de ETABS, o sincroniza fichas V1.2 (⟳).<br>2) Al seleccionar o generar, <b>la Hoja se autopobla</b> con su geometría + caso gobernante.<br>3) Ajusta variables en la Hoja o agrega <b>Casos de Carga</b> (izquierda).<br>4) <b>Calcular</b> (pestaña Resultados) → As / φRn / DC.<br>5) <b>Generar partidas CSI</b> → vuelca cantidades al presupuesto.`)}
    ${box("Concreto (ACI 318-19)", `<b>Variables viga:</b> b, <b>d efectivo</b> (= h − recubrimiento, NO la altura total), L; cargas Mu, Vu, Tu (0 si no hay), Nu.<br><b>Variables columna:</b> Lx, Ly, L; Pu, Mxx, Myy; esbeltez lu/k/βd/Cm (deja <b>lu=0</b> para columna corta, δ=1).<br><b>Resultados:</b> ${kx("A_s","As")} (acero tensión) · ${kx("A'_s","A's")} (compresión, viga doble) · ${kx("A_v/S","Av/S")} (estribos) · Smax · ✓Sísmico/✓ρg · takeoff (concreto m³, encofrado m², acero kg). <b>Partidas:</b> 03 10 00 encofrado · 03 20 00 acero · 03 30 00 concreto.`)}
    ${box("Acero (AISC 360-16 LRFD)", `Los elementos de <b>acero</b> (badge ACERO en la lista) traen <b>perfil</b> (W/HSS) y grado (A992). El motor corre estados límite <b>§D</b> tracción · <b>§E</b> compresión (pandeo) · <b>§F</b> flexión (LTB) · <b>§G</b> cortante · <b>§H</b> interacción. Resultados: <b>φRn</b> por estado, <b>DC = demanda/φRn</b>, estado gobernante, cumple ✓/✗. Sin carga → muestra las capacidades del perfil (DC=0). <b>Partidas:</b> Div 05 (suministro mL + conexiones pza con insumos).`)}
    ${box("Importar de ETABS", `Sidebar izquierdo, botones <b>⬆ Importar de ETABS</b>:<br>• <b>Concreto:</b> pega/sube la tabla (Frame/Section/Combo/P/V2/M2/M3) → crea elementos + casos + corre ACI.<br>• <b>Acero LRFD:</b> mismas fuerzas → corre §D-H propio como <b>chequeo cruzado</b> del Steel Frame Design de ETABS.<br>Elige <b>unidad</b> (kgf/kN/ton). El perfil/sección debe existir en la tabla AISC. Columna asume compresión; uplift = caso manual.`)}
    ${box("Norma y alcance honesto", `Concreto: fórmulas base ACI 318-71 (Viga-Colum.xls) con φ adaptados a <b>ACI 318-19</b> (flexión 0.90, cortante 0.75, columna 0.65) para Honduras (RSHNC). Acero: <b>AISC 360-16</b> §D-H, perfil I compacto. <b>Pendiente:</b> interacción biaxial exacta de columna concreto (Bresler), pandeo local F3/E7 y HSS en acero. Import automático de geometría futura = <b>Revit</b>, no ETABS.`)}
  </div>`;
}

// VISTA 3 — Aplicar a presupuesto
function vistaAplicarHTML() {
  const s = mathcadState;
  const hayPres = !!(typeof state !== "undefined" && state.activeId);
  const tipoLbl = { VIGA_SIMPLE:"Viga Simple", VIGA_DOBLE:"Viga Doble", VIGA_T:"Viga T", COLUMNA:"Columna" }[s.tipo] || s.tipo;
  const esCol = s.tipo === "COLUMNA";
  const secc = esCol ? `${s.lx}×${s.ly} cm` : `b ${s.b} × d ${s.d} cm`;
  const cargas = esCol ? `Pu ${s.pu} t · Mxx ${s.mxx} · Myy ${s.myy} t·m`
                       : `Mu ${s.mu} t·m · Vu ${s.vu} t · Tu ${s.tu} · Nu ${s.nu}`;
  const warnL = (!s.L || s.L <= 0) ? `<div style="color:#e67e22;font-size:11px;margin-top:6px">⚠ Longitud L = 0 → no se generarán cantidades. Pon L &gt; 0 en la vista Cálculo.</div>` : "";
  const inner = !hayPres
    ? `<div style="color:#e74c3c;font-size:13px">No hay presupuesto activo. Abre/crea un presupuesto primero y vuelve aquí.</div>`
    : `
      <div style="font-size:13px;line-height:1.7;margin-bottom:10px">
        <b>Resumen del elemento a generar:</b><br>
        Tipo: <b>${tipoLbl}</b> · Sección: <b>${secc}</b> · Material: <b>f'c ${s.fc} / f'y ${s.fy}</b><br>
        Longitud: <b>${s.L} m</b> · Cargas: ${esc(cargas)}
      </div>
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
        <label style="font-size:11px;color:var(--text-dim)">Mark (opcional)</label>
        <input id="mc-mark" type="text" placeholder="VA-01" style="background:var(--bg);border:1px solid var(--border);color:var(--text);padding:4px 7px;border-radius:3px"/>
      </div>
      <div style="font-size:11px;color:var(--text-dim);margin-bottom:10px;line-height:1.6">
        Esto crea el elemento + caso en el presupuesto activo, lo calcula, y genera <b>3 partidas CSI 03</b>:
        <b>03 10 00</b> encofrado (m²) · <b>03 20 00</b> acero (kg) · <b>03 30 00</b> concreto (m³), con cantidades reales del takeoff.
      </div>
      <button id="mc-aplicar-btn" class="btn-primary" style="font-size:13px">📦 Generar partidas CSI 03</button>
      ${warnL}`;
  return `<div style="padding:16px 18px;max-width:680px">
    <div style="font-size:13px;font-weight:700;color:var(--accent);margin-bottom:10px">📦 Aplicar a presupuesto</div>
    ${inner}</div>`;
}

function bindAplicar() {
  const btn = document.getElementById("mc-aplicar-btn");
  if (btn) btn.addEventListener("click", aplicarPresupuesto);
}

async function aplicarPresupuesto() {
  if (typeof state === "undefined" || !state.activeId) { alert("Selecciona un presupuesto activo primero."); return; }
  const s = mathcadState;
  if (!s.L || s.L <= 0) { if (!confirm("Longitud L = 0 → no se generarán cantidades de obra. ¿Continuar igual?")) return; }
  const mark = document.getElementById("mc-mark")?.value.trim() || "";
  const btn = document.getElementById("mc-aplicar-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Generando…"; }
  try {
    const elem = await api("POST", `/diseno/${state.activeId}/elementos`, {
      tipo: s.tipo, type_mark: mark,
      b_cm: s.b, d_cm: s.d, d_prima_cm: s.d_prima, bp_cm: s.bp, t_cm: s.t,
      lx_cm: s.lx, ly_cm: s.ly, fc_kg_cm2: s.fc, fy_kg_cm2: s.fy, longitud_m: s.L,
      notas: "Generado desde Hoja de Cálculo",
    });
    const caso = await api("POST", `/diseno/elementos/${elem.id}/casos`, {
      nombre: "Hoja", mu_tm: s.mu, vu_t: s.vu, tu_tm: s.tu, nu_t: s.nu,
      pu_t: s.pu, mu_xx_tm: s.mxx, mu_yy_tm: s.myy,
      lu_cm: s.lu, k_x: s.kx, k_y: s.ky, bd_x: s.bdx, bd_y: s.bdy, cm_x: s.cmx, cm_y: s.cmy,
    });
    await api("POST", `/diseno/casos/${caso.id}/calcular`);
    await api("POST", `/diseno/casos/${caso.id}/generar-partidas`);
    if (typeof loadObra === "function") await loadObra(state.activeId);
    alert(`Partidas CSI 03 generadas en el presupuesto (elemento ${elem.csi || mark || "nuevo"}).`);
  } catch (err) {
    alert("Error aplicando a presupuesto: " + err.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "📦 Generar partidas CSI 03"; }
  }
}

function renderVista() {
  const c = document.getElementById("hoja-content");
  if (!c) return;
  const v = mathcadState.vista;
  if (v === "guia")    { c.innerHTML = vistaGuiaHTML(); return; }
  if (v === "aplicar") { c.innerHTML = vistaAplicarHTML(); bindAplicar(); return; }
  c.innerHTML = vistaCalculoHTML();
  bindHojaInputs();
  recalcHoja();
}

function renderHoja() {
  const panel = document.getElementById("hoja-panel");
  if (!panel) return;
  if (!mathcadState.vista || mathcadState.vista === "guia") mathcadState.vista = "calculo";
  const s = mathcadState;
  const selStyle = "background:var(--surface2);border:1px solid var(--accent);color:var(--text);padding:4px 8px;border-radius:3px;font-weight:600;font-size:13px";
  const tipoOpts = [["VIGA_SIMPLE","Viga Simple"], ["VIGA_DOBLE","Viga Doble"], ["VIGA_T","Viga T"], ["COLUMNA","Columna"]];
  const vistaOpts = [["calculo","🧮 Cálculo en vivo"], ["aplicar","📦 Aplicar a presupuesto"]];
  const elemChip = s._label
    ? `<span style="font-family:monospace;font-size:12px;color:var(--accent);background:var(--surface2);border:1px solid var(--accent);border-radius:10px;padding:2px 9px" title="Propiedades cargadas desde la base de datos">📥 ${esc(s._label)}</span>`
    : `<span style="font-size:11px;color:var(--text-dim);font-style:italic">← elige un elemento de la lista para cargar sus propiedades, o edita libre</span>`;
  const sinCasoHint = (s._label && s._sinCaso)
    ? `<div style="font-size:10px;color:#e67e22;padding:4px 16px 0">⚠ Este elemento no tiene cargas guardadas — teclea Mu/Vu/… (de tu análisis) en Variables.</div>`
    : "";
  panel.innerHTML = `
    <div style="position:sticky;top:0;z-index:5;background:var(--bg);display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:11px 16px;border-bottom:1px solid var(--border)">
      <b style="font-size:15px;margin-right:4px">Diseño Estructural</b>
      ${elemChip}
      <label style="font-size:11px;color:var(--text-dim);margin-left:8px">Tipo:</label>
      <select id="mc-tipo" style="${selStyle}">${tipoOpts.map(([v,l]) => `<option value="${v}" ${v === s.tipo ? "selected" : ""}>${l}</option>`).join("")}</select>
      <label style="font-size:11px;color:var(--text-dim);margin-left:8px">Vista:</label>
      <select id="mc-vista" style="${selStyle}">${vistaOpts.map(([v,l]) => `<option value="${v}" ${v === s.vista ? "selected" : ""}>${l}</option>`).join("")}</select>
    </div>
    ${sinCasoHint}
    <div id="hoja-content"></div>`;
  document.getElementById("mc-tipo").addEventListener("change", e => { mathcadState.tipo = e.target.value; renderVista(); });
  document.getElementById("mc-vista").addEventListener("change", e => { mathcadState.vista = e.target.value; renderVista(); });
  renderVista();
}

async function sincronizarBasesV11() {
  if (!state.activeId) { alert("Selecciona un proyecto primero."); return; }
  const btn = document.getElementById("btn-diseno-sync-bases");
  const prev = btn ? btn.textContent : "";
  if (btn) { btn.textContent = "..."; btn.disabled = true; }
  try {
    const res = await api("POST", `/diseno/${state.activeId}/importar-bases`, { version: "v1.2" });
    if (res.status === "sin_candidatos") {
      alert("No se encontraron vigas/columnas con sección en la base V1.2.");
    } else {
      disenoState.elementos = res.elementos || [];
      renderElementos();
      if (disenoState.elementos.length) selectElemento(disenoState.elementos[0].id);
      alert(`V1.2 importada: ${res.creados} creados, ${res.actualizados} actualizados (${res.total} candidatos).`);
    }
  } catch (err) {
    alert("Error importando V1.2: " + err.message);
  } finally {
    if (btn) { btn.textContent = prev; btn.disabled = false; }
  }
}

async function crearElemento() {
  if (!state.activeId) { alert("Selecciona un proyecto primero."); return; }
  // CSI manda: sin prompt — backend auto-asigna el siguiente CSI 03 31 00.NN
  try {
    const nuevo = await api("POST", `/diseno/${state.activeId}/elementos`, {
      tipo: "VIGA_SIMPLE",
      b_cm: 30, d_cm: 50, fc_kg_cm2: 210, fy_kg_cm2: 4200, longitud_m: 1,
    });
    disenoState.activeElemId = nuevo.id;
    await loadElementos(state.activeId);
  } catch (err) { alert("Error: " + err.message); }
}

async function guardarGeometria() {
  const eid = disenoState.activeElemId;
  if (!eid) { alert("Selecciona un elemento primero."); return; }
  const tipo = document.getElementById("dg-tipo").value;
  const body = {
    csi:        document.getElementById("dg-csi").value.trim(),
    type_mark:  document.getElementById("dg-mark").value.trim(),
    tipo,
    fc_kg_cm2:  parseFloat(document.getElementById("dg-fc").value)    || 210,
    fy_kg_cm2:  parseFloat(document.getElementById("dg-fy").value)    || 4200,
    b_cm:       parseFloat(document.getElementById("dg-b").value)     || 0,
    d_cm:       parseFloat(document.getElementById("dg-d").value)     || 0,
    d_prima_cm: parseFloat(document.getElementById("dg-dprim").value) || 5,
    bp_cm:      parseFloat(document.getElementById("dg-bp").value)    || 0,
    t_cm:       parseFloat(document.getElementById("dg-tf").value)    || 0,
    lx_cm:      parseFloat(document.getElementById("dg-lx").value)    || 0,
    ly_cm:      parseFloat(document.getElementById("dg-ly").value)    || 0,
    longitud_m: parseFloat(document.getElementById("dg-long").value)  || 0,
    notas:      document.getElementById("dg-notas").value.trim(),
  };
  try {
    await api("PATCH", `/diseno/elementos/${eid}`, body);
    await loadElementos(state.activeId);
  } catch (err) { alert("Error guardando: " + err.message); }
}

async function eliminarElemento() {
  const eid = disenoState.activeElemId;
  if (!eid) return;
  const el = disenoState.elementos.find(e => e.id === eid);
  if (!confirm(`¿Eliminar elemento "${el?.csi || el?.type_mark || eid}" y todos sus casos de carga?`)) return;
  try {
    await api("DELETE", `/diseno/elementos/${eid}`);
    disenoState.activeElemId = null;
    const emptyMsg = document.getElementById("diseno-geom-empty");
    const geomForm = document.getElementById("diseno-geom-form");
    if (emptyMsg) emptyMsg.style.display = "";
    if (geomForm) geomForm.style.display = "none";
    renderCasos([]);
    renderResultados([]);
    await loadElementos(state.activeId);
  } catch (err) { alert("Error eliminando: " + err.message); }
}

async function agregarCaso() {
  const eid = disenoState.activeElemId;
  if (!eid) { alert("Selecciona un elemento primero."); return; }
  const g = id => parseFloat(document.getElementById(id)?.value) || 0;
  const gd = (id, def) => { const v = parseFloat(document.getElementById(id)?.value); return isNaN(v) ? def : v; };
  const body = {
    nombre:   document.getElementById("dc-nombre")?.value.trim() || "Caso 1",
    mu_tm:    g("dc-mu"),
    vu_t:     g("dc-vu"),
    tu_tm:    g("dc-tu"),
    nu_t:     g("dc-nu"),
    pu_t:     g("dc-pu"),
    mu_xx_tm: g("dc-mxx"),
    mu_yy_tm: g("dc-myy"),
    // Esbeltez de columna
    lu_cm:    g("dc-lu"),
    k_x:      gd("dc-kx", 1),
    k_y:      gd("dc-ky", 1),
    bd_x:     gd("dc-bdx", 0.15),
    bd_y:     gd("dc-bdy", 0.15),
    cm_x:     gd("dc-cmx", 1),
    cm_y:     gd("dc-cmy", 1),
  };
  try {
    await api("POST", `/diseno/elementos/${eid}/casos`, body);
    // Reset add form (cargas a 0; esbeltez a sus defaults)
    ["dc-nombre","dc-mu","dc-vu","dc-tu","dc-nu","dc-pu","dc-mxx","dc-myy","dc-lu"].forEach(id => {
      const inp = document.getElementById(id);
      if (inp) inp.value = inp.type === "number" ? "0" : "";
    });
    const defs = { "dc-kx":1, "dc-ky":1, "dc-bdx":0.15, "dc-bdy":0.15, "dc-cmx":1, "dc-cmy":1 };
    Object.entries(defs).forEach(([id, v]) => { const inp = document.getElementById(id); if (inp) inp.value = v; });
    await loadElementos(state.activeId);
    selectElemento(eid);
  } catch (err) { alert("Error agregando caso: " + err.message); }
}

async function eliminarCaso(cid) {
  if (!confirm("¿Eliminar este caso de carga?")) return;
  try {
    await api("DELETE", `/diseno/casos/${cid}`);
    const eid = disenoState.activeElemId;
    await loadElementos(state.activeId);
    if (eid) selectElemento(eid);
  } catch (err) { alert("Error: " + err.message); }
}

async function calcularCasos(eid) {
  if (!eid) { alert("Selecciona un elemento."); return; }
  const el = disenoState.elementos.find(e => e.id === eid);
  if (!el?.casos?.length) { alert("El elemento no tiene casos de carga."); return; }
  const advDiv = document.getElementById("diseno-res-advertencias");
  if (advDiv) advDiv.textContent = "Calculando...";
  try {
    for (const caso of el.casos) {
      await api("POST", `/diseno/casos/${caso.id}/calcular`);
    }
    await loadElementos(state.activeId);
    selectElemento(eid);
    // Switch to resultados tab
    document.querySelector("[data-dtab='resultados']")?.click();
  } catch (err) {
    if (advDiv) advDiv.textContent = "Error: " + err.message;
    alert("Error calculando: " + err.message);
  }
}

async function generarPartidasElem(eid) {
  if (!eid) { alert("Selecciona un elemento."); return; }
  const el = disenoState.elementos.find(e => e.id === eid);
  const conRes = (el?.casos || []).filter(c => c.resultado);
  if (!conRes.length) { alert("Calcula primero antes de generar partidas."); return; }
  const governing = conRes.find(c => c.gobierna) || conRes[0];
  try {
    await api("POST", `/diseno/casos/${governing.id}/generar-partidas`);
    alert(`Partidas CSI 03 generadas para "${el.csi || el.type_mark || "elemento"}".`);
    await loadObra(state.activeId);
  } catch (err) { alert("Error generando partidas: " + err.message); }
}

async function calcularTodo() {
  if (!disenoState.elementos.length) { alert("No hay elementos."); return; }
  const advDiv = document.getElementById("diseno-res-advertencias");
  if (advDiv) advDiv.textContent = "Calculando todos los elementos...";
  let errors = 0;
  for (const el of disenoState.elementos) {
    for (const caso of (el.casos || [])) {
      try { await api("POST", `/diseno/casos/${caso.id}/calcular`); }
      catch { errors++; }
    }
  }
  await loadElementos(state.activeId);
  if (disenoState.activeElemId) selectElemento(disenoState.activeElemId);
  if (advDiv) advDiv.textContent = errors ? `${errors} error(es) al calcular` : "✓ Todo calculado OK";
}

async function generarTodo() {
  if (!disenoState.elementos.length) { alert("No hay elementos."); return; }
  let count = 0, errors = 0;
  for (const el of disenoState.elementos) {
    const conRes = (el.casos || []).filter(c => c.resultado);
    if (!conRes.length) continue;
    const governing = conRes.find(c => c.gobierna) || conRes[0];
    try {
      await api("POST", `/diseno/casos/${governing.id}/generar-partidas`);
      count++;
    } catch { errors++; }
  }
  if (count) await loadObra(state.activeId);
  alert(`${count} elemento(s) con partidas generadas.${errors ? ` ${errors} con errores.` : ""}`);
}

// ─── MÓDULO ETABS — ACCIÓN SÍSMICA CHOC-08 (estilo Mathcad) ───────────────────
// Aditivo: vista propia, endpoints /diseno/sismo/*. Reutiliza kx(), esc(), api().
// Defaults = proyecto piloto CC-135 (Comayagua). La hoja muestra TODAS las
// fórmulas al abrir, sin esperar input.

const etabsState = {
  zona: "3b", suelo: "S1", I: 1.0, Rw: 8, hn_m: 3, W_t: 1206,
  municipio: "", notas: "",
  tablas: null, ultima: null, timer: null,
  doc: null,            // {origen_inputs, procedimiento, export_doc} cacheado
  tab: "hoja",          // hoja | proc | carga
  // valores leidos del export de ETABS (informativos en la hoja)
  T_etabs: null, Vdin_etabs: null, deriva_etabs: null,
  // contexto sísmico persistente por presupuesto
  pid: null,            // presupuesto activo cuando se abrió ETABS (null = standalone)
  guardado: false,      // ¿el contexto está persistido en la BD?
  cargado_pid: null,    // pid cuyo contexto ya se precargó (evita recargar)
};

function etabsBody() {
  const s = etabsState;
  return { zona: s.zona, suelo: s.suelo, I: s.I, Rw: s.Rw, hn_m: s.hn_m, W_t: s.W_t };
}

// Cuerpo para PUT /diseno/{pid}/sismo (upsert del contexto persistente).
function etabsCtxBody() {
  const s = etabsState;
  return {
    municipio: s.municipio || "",
    zona: s.zona, suelo: s.suelo,
    importancia_i: s.I, rw: s.Rw, hn_m: s.hn_m, w_t: s.W_t,
    v_din_t: s.Vdin_etabs, deriva_real: s.deriva_etabs,
    notas: s.notas || "",
  };
}

// Precarga el contexto sísmico del presupuesto activo (si lo hay).
// Standalone (sin presupuesto): conserva los defaults CC-135 actuales.
async function etabsPrecargarContexto() {
  const s = etabsState;
  s.pid = (typeof state !== "undefined" && state) ? state.activeId : null;
  if (!s.pid) { s.guardado = false; s.cargado_pid = null; return; }
  if (s.cargado_pid === s.pid) return;   // ya precargado este presupuesto
  try {
    const ctx = await api("GET", `/diseno/${s.pid}/sismo`);
    s.zona  = ctx.zona  || s.zona;
    s.suelo = ctx.suelo || s.suelo;
    s.I     = ctx.importancia_i != null ? ctx.importancia_i : s.I;
    s.Rw    = ctx.rw   != null ? ctx.rw   : s.Rw;
    s.hn_m  = ctx.hn_m != null ? ctx.hn_m : s.hn_m;
    s.W_t   = ctx.w_t  != null ? ctx.w_t  : s.W_t;
    s.municipio   = ctx.municipio || "";
    s.notas       = ctx.notas || "";
    s.Vdin_etabs  = ctx.v_din_t != null ? ctx.v_din_t : s.Vdin_etabs;
    s.deriva_etabs = ctx.deriva_real != null ? ctx.deriva_real : s.deriva_etabs;
    s.guardado    = !!ctx.existe;
  } catch {
    s.guardado = false;
  }
  s.cargado_pid = s.pid;
}

function initEtabsView() {
  const btnOpen  = document.getElementById("btn-etabs-view");
  const btnClose = document.getElementById("btn-cerrar-etabs-view");
  const btnCsv   = document.getElementById("btn-etabs-export-csv");
  if (btnOpen) btnOpen.addEventListener("click", async () => {
    document.getElementById("etabs-view").style.display = "flex";
    await etabsPrecargarContexto();   // GET /diseno/{pid}/sismo si hay presupuesto activo
    renderEtabs();          // pinta inputs + recalcula al instante (no queda en "cargando")
  });
  if (btnClose) btnClose.addEventListener("click", () => {
    document.getElementById("etabs-view").style.display = "none";
  });
  if (btnCsv) btnCsv.addEventListener("click", exportarEspectroEtabs);
}

// Guarda (upsert) el contexto sísmico en el presupuesto activo.
async function guardarContextoSismico() {
  const s = etabsState;
  if (!s.pid) { alert("No hay un presupuesto activo. Abre un presupuesto para guardar su contexto sísmico."); return; }
  try {
    const ctx = await api("PUT", `/diseno/${s.pid}/sismo`, etabsCtxBody());
    s.guardado = !!ctx.existe;
    const badge = document.getElementById("etabs-ctx-badge");
    if (badge) badge.outerHTML = etabsCtxBadgeHTML();
    alert("✔ Contexto sísmico guardado en el presupuesto.");
  } catch (err) {
    alert("No se pudo guardar el contexto sísmico: " + (err.message || err));
  }
}

// Cabecera: indica si el contexto está vinculado a un presupuesto y si está guardado.
function etabsCtxBadgeHTML() {
  const s = etabsState;
  let txt, color, bg;
  if (!s.pid) {
    txt = "● Modo standalone (sin presupuesto) — defaults CC-135, no se guarda";
    color = "#e67e22"; bg = "rgba(230,126,34,.12)";
  } else if (s.guardado) {
    txt = "● Contexto guardado en este presupuesto";
    color = "#27ae60"; bg = "rgba(39,174,96,.12)";
  } else {
    txt = "● Sin guardar — usa «💾 Guardar contexto sísmico» para persistir";
    color = "#e67e22"; bg = "rgba(230,126,34,.12)";
  }
  return `<span id="etabs-ctx-badge" style="font-size:10.5px;font-weight:700;color:${color};background:${bg};border:1px solid ${color};border-radius:4px;padding:3px 9px">${esc(txt)}</span>`;
}

// Catálogos para los dropdowns (zonas/suelos). Se cachea.
async function etabsCargarTablas() {
  if (etabsState.tablas) return etabsState.tablas;
  try { etabsState.tablas = await api("GET", "/diseno/sismo/tablas"); }
  catch { etabsState.tablas = { zonas: [], suelos: [] }; }
  return etabsState.tablas;
}

// Material explicativo (origen de inputs + procedimiento + doc del export). Cacheado.
async function etabsCargarDoc() {
  if (etabsState.doc) return etabsState.doc;
  try { etabsState.doc = await api("GET", "/diseno/sismo/procedimiento"); }
  catch { etabsState.doc = { origen_inputs: {}, procedimiento: { meta: {}, pasos: [] }, export_doc: {} }; }
  return etabsState.doc;
}

// Estructura: pestañas (Hoja / Procedimiento / Cargar ETABS) + cabecera de inputs.
async function renderEtabs() {
  const cont = document.getElementById("etabs-content");
  if (!cont) return;
  const [tablas, doc] = await Promise.all([etabsCargarTablas(), etabsCargarDoc()]);
  const s = etabsState;
  const origen = (doc && doc.origen_inputs) || {};
  const selStyle = "background:var(--surface2);border:1px solid var(--accent);color:var(--text);padding:3px 6px;border-radius:3px;font-weight:600";
  const inpStyle = "width:90px;background:var(--bg);border:1px solid var(--accent);color:var(--text);padding:3px 6px;border-radius:3px;font-family:monospace;font-weight:600";

  const zonaOpts  = (tablas.zonas || []).map(z =>
    `<option value="${z.zona}" ${z.zona === s.zona ? "selected" : ""}>Zona ${z.zona} (Z=${z.Z})</option>`).join("");
  const sueloOpts = (tablas.suelos || []).map(su =>
    `<option value="${su.suelo}" ${su.suelo === s.suelo ? "selected" : ""}>${su.suelo} — ${esc(su.desc)}</option>`).join("");

  // Línea de ORIGEN bajo cada input (de dónde viene el dato + ícono ⓘ con tooltip).
  const origenLine = (key) => {
    const o = origen[key];
    if (!o) return "";
    const tip = `${o.titulo}\n\nOrigen: ${o.origen}\nReferencia: ${o.referencia}\nEjemplo CC-135: ${o.ejemplo_cc135}`;
    return `<div style="font-size:9.5px;color:var(--text-dim);line-height:1.35;margin:1px 0 4px 0">
        <span title="${escapeAttr(tip)}" style="cursor:help;color:var(--accent);font-weight:700">ⓘ</span>
        <span style="color:var(--accent)">${esc(o.referencia)}</span> · ${esc(o.origen)}
      </div>`;
  };

  const inRow = (key, sym, unit, val, step) => `
    <div style="padding:2px 0">
      <div style="display:flex;align-items:center;gap:5px">
        <span style="min-width:30px;text-align:right">${kx(sym, sym)}</span>
        <span style="color:var(--accent);font-weight:700">:=</span>
        <input data-et="${key}" type="number" step="${step || "any"}" value="${val}" style="${inpStyle}"/>
        <span style="font-size:10px;color:var(--text-dim)">${esc(unit)}</span>
      </div>
      ${origenLine(key)}
    </div>`;

  const tab = (id, label) =>
    `<button class="et-tab" data-ettab="${id}" style="background:${s.tab === id ? "var(--accent)" : "transparent"};color:${s.tab === id ? "#fff" : "var(--text)"};border:1px solid var(--accent);padding:5px 14px;border-radius:4px;font-size:12px;font-weight:700;cursor:pointer">${label}</button>`;

  cont.innerHTML = `
   <div style="padding:14px 16px;max-width:1040px">
     <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
       ${tab("hoja", "📐 Hoja de cálculo")}
       ${tab("proc", "📖 Procedimiento")}
       ${tab("carga", "⬆ Cargar datos de ETABS")}
     </div>

     <!-- PESTAÑA HOJA -->
     <div id="et-pane-hoja" style="display:${s.tab === "hoja" ? "block" : "none"}">
       <div style="font-size:11px;color:var(--text-dim);background:var(--surface2);border:1px solid var(--border);border-radius:4px;padding:8px 11px;margin-bottom:10px;line-height:1.5">
         🏗️ <b>Hoja sísmica CHOC-08</b> estilo Mathcad. Edita zona, suelo y parámetros; todas las fórmulas se recalculan al instante en notación <b>símbolo := fórmula = sustitución = resultado</b>. Cada dato de ingreso muestra <b>de dónde viene</b> (ⓘ). El diseño de elementos de concreto (ACI) está en el módulo <b>📐 Diseño</b>. Defaults = proyecto piloto <b>CC-135</b> (Comayagua).
       </div>
       <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px">
         ${etabsCtxBadgeHTML()}
         <button id="et-guardar-ctx" class="btn-primary" style="font-size:12px;padding:5px 12px"${s.pid ? "" : " disabled title='Abre un presupuesto para guardar'"}>💾 Guardar contexto sísmico</button>
       </div>
       <div style="border:1px solid var(--accent);border-radius:5px;padding:10px 12px;margin-bottom:12px;background:var(--surface)">
         <div style="font-size:10px;font-weight:700;color:var(--accent);letter-spacing:.5px;margin-bottom:7px">DATOS DE INGRESO — edita aquí · cada uno indica su origen (norma/tabla/documento)</div>
         <div style="display:flex;align-items:center;gap:6px;padding:3px 0;margin-bottom:4px">
           <span style="min-width:48px;font-size:11px;color:var(--text-dim)">Municipio</span>
           <input id="et-municipio" type="text" value="${escapeAttr(s.municipio || "")}" placeholder="p. ej. Comayagua" style="flex:1;max-width:280px;background:var(--bg);border:1px solid var(--accent);color:var(--text);padding:3px 6px;border-radius:3px"/>
         </div>
         <div style="display:flex;gap:30px;flex-wrap:wrap;align-items:flex-start">
           <div style="min-width:300px">
             <div style="display:flex;align-items:center;gap:6px;padding:3px 0">
               <span style="min-width:48px;font-size:11px;color:var(--text-dim)">Zona</span>
               <select id="et-zona" style="${selStyle};flex:1">${zonaOpts}</select>
             </div>
             ${origenLine("zona")}
             <div style="display:flex;align-items:center;gap:6px;padding:3px 0">
               <span style="min-width:48px;font-size:11px;color:var(--text-dim)">Suelo</span>
               <select id="et-suelo" style="${selStyle};flex:1">${sueloOpts}</select>
             </div>
             <div id="et-suelo-auto" style="font-size:10px;color:var(--text-dim);margin-top:2px;padding-left:54px"></div>
             ${origenLine("suelo")}
           </div>
           <div style="min-width:230px">
             <div style="font-size:10px;font-weight:700;color:var(--accent);margin-bottom:3px">Factores</div>
             ${inRow("I", "I", "", s.I, "0.05")}
             ${inRow("Rw", "R_w", "", s.Rw, "1")}
           </div>
           <div style="min-width:260px">
             <div style="font-size:10px;font-weight:700;color:var(--accent);margin-bottom:3px">Edificio (de ETABS / arquitectura)</div>
             ${inRow("hn_m", "h_n", "m", s.hn_m, "0.1")}
             ${inRow("W_t", "W", "kgf", s.W_t, "1")}
           </div>
         </div>
       </div>
       <div style="font-size:11px;font-weight:700;color:var(--text-dim);letter-spacing:.5px;margin-bottom:6px">DESARROLLO — símbolo := fórmula = sustitución = resultado</div>
       <div id="etabs-desarrollo" style="font-size:14px">cargando…</div>
       <div id="etabs-espectro-wrap" style="margin-top:16px"></div>
       <div style="border:1px solid var(--border);border-radius:5px;padding:8px 11px;margin-top:14px;background:var(--surface)">
         <div style="font-size:10px;font-weight:700;color:var(--text-dim);letter-spacing:.5px;margin-bottom:5px">CONSTANTES (fijas)</div>
         <div id="etabs-constantes" style="display:grid;grid-template-columns:repeat(3,1fr);gap:5px 20px;font-size:13px"></div>
       </div>
       <div style="font-size:10px;color:var(--text-dim);text-align:center;margin-top:14px;line-height:1.5">
         Acción sísmica <b>CHOC-08</b> (Tablas 1.3.4-1/2/3/6 · ecs. 1.3.6). Espectro a/g por ramas y deriva límite 1.3.5.8.2. Diseño de concreto: <b>ACI</b> (módulo 📐 Diseño).
       </div>
     </div>

     <!-- PESTAÑA PROCEDIMIENTO -->
     <div id="et-pane-proc" style="display:${s.tab === "proc" ? "block" : "none"}">
       ${etabsProcedimientoHTML(doc && doc.procedimiento)}
     </div>

     <!-- PESTAÑA CARGAR ETABS -->
     <div id="et-pane-carga" style="display:${s.tab === "carga" ? "block" : "none"}">
       ${etabsCargaHTML(doc && doc.export_doc)}
     </div>
   </div>`;

  bindEtabsTabs();
  if (s.tab === "hoja") { bindEtabsInputs(); recalcEtabs(); }
  if (s.tab === "carga") bindEtabsLoader();
}

// Cambio de pestaña (re-render para enganchar los binds correctos).
function bindEtabsTabs() {
  document.querySelectorAll("#etabs-content .et-tab").forEach(b => {
    b.addEventListener("click", () => { etabsState.tab = b.dataset.ettab; renderEtabs(); });
  });
}

// Marca el contexto como "modificado, sin guardar" y refresca el badge.
function etabsMarcarSucio() {
  const s = etabsState;
  if (!s.pid || !s.guardado) return;
  s.guardado = false;
  const badge = document.getElementById("etabs-ctx-badge");
  if (badge) badge.outerHTML = etabsCtxBadgeHTML();
}

function bindEtabsInputs() {
  const zSel = document.getElementById("et-zona");
  const sSel = document.getElementById("et-suelo");
  if (zSel) zSel.addEventListener("change", () => { etabsState.zona = zSel.value; etabsMarcarSucio(); recalcEtabs(); });
  if (sSel) sSel.addEventListener("change", () => { etabsState.suelo = sSel.value; etabsMarcarSucio(); recalcEtabs(); });
  document.querySelectorAll("#etabs-content input[data-et]").forEach(inp => {
    inp.addEventListener("input", () => {
      const k = inp.dataset.et, v = parseFloat(inp.value);
      etabsState[k] = isNaN(v) ? 0 : v;
      etabsMarcarSucio();
      clearTimeout(etabsState.timer);
      etabsState.timer = setTimeout(recalcEtabs, 250);
    });
  });
  const mun = document.getElementById("et-municipio");
  if (mun) mun.addEventListener("input", () => { etabsState.municipio = mun.value; etabsMarcarSucio(); });
  const btnG = document.getElementById("et-guardar-ctx");
  if (btnG) btnG.addEventListener("click", guardarContextoSismico);
}

async function recalcEtabs() {
  const dev = document.getElementById("etabs-desarrollo");
  const con = document.getElementById("etabs-constantes");
  const esp = document.getElementById("etabs-espectro-wrap");
  const badge = document.getElementById("etabs-status-badge");
  if (!dev) return;
  let m;
  try { m = await api("POST", "/diseno/sismo/memoria", etabsBody()); }
  catch (err) { dev.innerHTML = `<div style="color:#e74c3c;font-size:12px">Error: ${esc(err.message)}</div>`; return; }
  etabsState.ultima = m;
  const meta = m.meta || {};

  // Autollenado visible de S/Ta/Tb/c según suelo
  const sa = document.getElementById("et-suelo-auto");
  if (sa) sa.innerHTML = `auto → S=${meta.S} · Ta=${meta.Ta}s · Tb=${meta.Tb}s · c=${meta.c}`;

  if (badge) badge.textContent = meta.resumen || "";

  // Constantes
  if (con && Array.isArray(m.constantes))
    con.innerHTML = m.constantes.map(c => `<div title="${esc(c.desc || "")}">${kx(c.latex, c.simbolo)}</div>`).join("");

  // Desarrollo agrupado por sección (orden de aparición)
  const orden = [], grupos = {};
  m.pasos.forEach(p => { if (!grupos[p.seccion]) { grupos[p.seccion] = []; orden.push(p.seccion); } grupos[p.seccion].push(p); });
  const SISMO_SEC = {
    "Parámetros":    ["CHOC-08 §1.3.4",   "Datos de tabla: Z (factor de zona), perfil de suelo (S/Ta/Tb/c), I (importancia), Rw (reducción por ductilidad), hn y W (peso sísmico = CM + porción CV)."],
    "Periodo":       ["CHOC-08 §1.3.6.5.3","T_A = 0.0731·hn^(3/4) — periodo fundamental aproximado (Método A, marco de concreto). Define en qué punto del espectro cae el edificio."],
    "Cortante basal":["CHOC-08 §1.3.6",   "C = 1.25·S/T^(2/3) ≤ 2.75 es el coeficiente espectral. V = (Z·I·C/Rw)·W es la fuerza en la base. C/Rw ≥ 0.075 es el piso de diseño."],
    "Espectro":      ["CHOC-08 §1.3.6-10/12","Tres ramas: ascendente (T<Ta), meseta 2.75·Z (Ta≤T≤Tb), descendente (T>Tb). La ordenada en T_A da la aceleración real del edificio."],
    "Deriva":        ["CHOC-08 §1.3.5.8.2","Δ_lim = tope de deriva de entrepiso según T (0.7s). La deriva real de ETABS debe quedar por debajo de este límite, o aumentar rigidez."],
  };
  dev.innerHTML = orden.map((sec, i) => {
    const [ref, intro] = SISMO_SEC[sec] || ["CHOC-08", ""];
    return `<div style="margin-bottom:14px">
      <div style="display:flex;align-items:baseline;gap:8px;border-bottom:2px solid var(--accent);padding-bottom:3px;margin-bottom:6px">
        <span style="font-size:12px;font-weight:700">${i + 1}. ${esc(sec)}</span>
        <span style="font-size:9px;font-weight:700;color:var(--accent);border:1px solid var(--accent);border-radius:8px;padding:1px 7px">${esc(ref)}</span>
      </div>
      ${intro ? `<div style="font-size:11px;color:var(--text-dim);font-style:italic;margin-bottom:7px;line-height:1.45">${esc(intro)}</div>` : ""}
      ${grupos[sec].map(etabsDevLine).join("")}
    </div>`;
  }).join("");

  // Gráfica + tabla del espectro (+ comparación con lo leído de ETABS si existe)
  if (esp) esp.innerHTML = etabsEspectroHTML(m.espectro, meta) + etabsComparaEtabsHTML(meta);
}

// Bloque informativo: compara valores leídos del export de ETABS con la hoja.
function etabsComparaEtabsHTML(meta) {
  const s = etabsState;
  if (s.T_etabs == null && s.Vdin_etabs == null && s.deriva_etabs == null) return "";
  const dLim = meta.deriva_limite;
  const fila = (lbl, val, ref, ok) => `<tr>
    <td style="padding:3px 12px">${esc(lbl)}</td>
    <td style="padding:3px 12px;text-align:right;font-family:monospace;font-weight:700">${val == null ? "—" : esc(String(val))}</td>
    <td style="padding:3px 12px;text-align:right;font-family:monospace;color:var(--text-dim)">${ref}</td>
    <td style="padding:3px 12px">${ok == null ? "" : (ok ? '<span style="color:#27ae60;font-weight:700">✓</span>' : '<span style="color:#e74c3c;font-weight:700">✗</span>')}</td>
  </tr>`;
  const vEst = meta.V_kgf;
  const okV = (s.Vdin_etabs != null && vEst) ? (s.Vdin_etabs >= 0.9 * vEst) : null;
  const okD = (s.deriva_etabs != null && dLim != null) ? (s.deriva_etabs <= dLim) : null;
  return `<div style="border:1px solid #e67e22;border-radius:5px;padding:9px 12px;margin-top:14px;background:var(--surface)">
    <div style="font-size:10px;font-weight:700;color:#e67e22;letter-spacing:.5px;margin-bottom:6px">LEÍDO DEL EXPORT DE ETABS — verificación CHOC-08</div>
    <table style="border-collapse:collapse;font-size:12px;width:100%">
      <thead><tr style="color:var(--text-dim);font-size:10px;text-align:left">
        <th style="padding:2px 12px">Cantidad</th><th style="padding:2px 12px;text-align:right">ETABS</th><th style="padding:2px 12px;text-align:right">Referencia hoja</th><th style="padding:2px 12px">Chequeo</th>
      </tr></thead>
      <tbody>
        ${fila("Periodo T (modal)", s.T_etabs != null ? s.T_etabs + " s" : null, (meta.T_A != null ? meta.T_A + " s (Método A)" : "—"), null)}
        ${fila("Cortante dinámico V_din", s.Vdin_etabs != null ? s.Vdin_etabs + " kgf" : null, (vEst != null ? "≥ 90% de " + vEst + " kgf" : "—"), okV)}
        ${fila("Deriva máxima", s.deriva_etabs != null ? s.deriva_etabs : null, (dLim != null ? "≤ " + dLim : "—"), okD)}
      </tbody>
    </table>
    <div style="font-size:9.5px;color:var(--text-dim);margin-top:5px">El periodo T de ETABS se usó como dato; V_din y deriva se comparan contra los mínimos CHOC-08 (cap. 12 y 13). W del export reemplazó el W de la hoja.</div>
  </div>`;
}

// Una línea de desarrollo (símbolo := fórmula = sustitución = resultado).
function etabsDevLine(p) {
  const result = (typeof p.valor === "boolean")
    ? (p.valor ? `<span style="color:#27ae60;font-weight:700">✓ OK</span>`
               : `<span style="color:#e74c3c;font-weight:700">✗ FALLA</span>`)
    : (p.valor === "—" || p.valor == null)
      ? ""
      : `<span style="font-weight:700;color:#27ae60">${esc(String(p.valor))}${p.unidad ? ` <span style="color:var(--text-dim);font-weight:400;font-size:.8em">${esc(p.unidad)}</span>` : ""}</span>`;
  const def = p.latex
    ? `<span style="flex:1;min-width:0;overflow-x:auto">${kx(p.latex, p.formula)}</span>${result ? `<span style="color:var(--text-dim)">=</span>` : ""}`
    : (p.formula && p.formula !== "—"
        ? `<span style="flex:1;min-width:0;font-size:11px;color:var(--text-dim)">${esc(p.formula)}</span>${result ? `<span style="color:var(--text-dim)">=</span>` : ""}`
        : `<span style="flex:1"></span>`);
  const sub = p.latex_sub
    ? `<div style="margin-left:38px;font-size:.82em;color:var(--text-dim);overflow-x:auto">${kx(p.latex_sub, p.sustitucion)}</div>`
    : "";
  return `<div style="padding:5px 0;border-bottom:1px dashed var(--border)">
    <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">
      <span style="font-weight:700">${kx(p.simbolo, p.simbolo)}</span>
      <span style="color:var(--accent);font-weight:700">:=</span>
      ${def}
      ${result}
    </div>
    ${sub}
    <div style="font-size:10px;color:var(--text-dim);margin-top:1px">${esc(p.etiqueta || "")}${p.referencia && p.referencia !== "—" ? ` · <span style="color:var(--accent)">${esc(p.referencia)}</span>` : ""}</div>
  </div>`;
}

// Gráfica SVG del espectro + tabla de pares T, a/g.
function etabsEspectroHTML(espectro, meta) {
  if (!Array.isArray(espectro) || !espectro.length) return "";
  const W = 560, H = 240, padL = 46, padR = 14, padT = 14, padB = 30;
  const tMax = Math.max(...espectro.map(p => p[0])) || 1;
  const aMax = Math.max(...espectro.map(p => p[1])) || 1;
  const sx = t => padL + (t / tMax) * (W - padL - padR);
  const sy = a => H - padB - (a / aMax) * (H - padT - padB);
  const pts = espectro.map(p => `${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(" ");

  // Ticks
  const xticks = [], yticks = [];
  for (let t = 0; t <= tMax + 1e-6; t += 0.5) {
    const x = sx(t);
    xticks.push(`<line x1="${x}" y1="${H - padB}" x2="${x}" y2="${H - padB + 4}" stroke="var(--text-dim)"/>
      <text x="${x}" y="${H - padB + 16}" font-size="9" fill="var(--text-dim)" text-anchor="middle">${t.toFixed(1)}</text>`);
  }
  const ystep = aMax / 4;
  for (let i = 0; i <= 4; i++) {
    const a = ystep * i, y = sy(a);
    yticks.push(`<line x1="${padL - 4}" y1="${y}" x2="${padL}" y2="${y}" stroke="var(--text-dim)"/>
      <text x="${padL - 7}" y="${y + 3}" font-size="9" fill="var(--text-dim)" text-anchor="end">${a.toFixed(2)}</text>
      <line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--border)" stroke-dasharray="2,3"/>`);
  }
  // Marca del periodo del edificio T_A
  const tA = meta.T_A || 0;
  const tAline = (tA > 0 && tA <= tMax)
    ? `<line x1="${sx(tA)}" y1="${padT}" x2="${sx(tA)}" y2="${H - padB}" stroke="#e67e22" stroke-dasharray="4,3"/>
       <text x="${sx(tA) + 3}" y="${padT + 10}" font-size="9" fill="#e67e22">T_A=${tA}s</text>`
    : "";

  const svg = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px;background:var(--surface);border:1px solid var(--border);border-radius:5px">
    <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${H - padB}" stroke="var(--text-dim)"/>
    <line x1="${padL}" y1="${H - padB}" x2="${W - padR}" y2="${H - padB}" stroke="var(--text-dim)"/>
    ${yticks.join("")}${xticks.join("")}
    <polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="2"/>
    ${tAline}
    <text x="${W / 2}" y="${H - 4}" font-size="10" fill="var(--text-dim)" text-anchor="middle">T (s)</text>
    <text x="12" y="${H / 2}" font-size="10" fill="var(--text-dim)" text-anchor="middle" transform="rotate(-90 12 ${H / 2})">a/g</text>
  </svg>`;

  // Tabla compacta (puntos clave + muestreo)
  const filas = espectro.map(([t, a]) => `<tr><td style="padding:2px 10px;text-align:right;font-family:monospace">${t}</td><td style="padding:2px 10px;text-align:right;font-family:monospace">${a}</td></tr>`).join("");

  return `<div style="display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start">
    <div style="flex:1;min-width:320px">
      <div style="font-size:11px;font-weight:700;color:var(--text-dim);letter-spacing:.5px;margin-bottom:6px">ESPECTRO DE RESPUESTA CHOC-08 — a/g vs T</div>
      ${svg}
    </div>
    <div style="max-height:280px;overflow:auto;border:1px solid var(--border);border-radius:5px">
      <table style="border-collapse:collapse;font-size:11px">
        <thead><tr style="background:var(--surface2);position:sticky;top:0">
          <th style="padding:3px 10px;text-align:right">T (s)</th><th style="padding:3px 10px;text-align:right">a/g</th>
        </tr></thead>
        <tbody>${filas}</tbody>
      </table>
    </div>
  </div>`;
}

// Descarga el espectro como CSV (pares T,a/g) para pegar en ETABS.
async function exportarEspectroEtabs() {
  try {
    const res = await fetch(API + "/diseno/sismo/espectro-csv", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(etabsBody()),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const txt = await res.text();
    const s = etabsState;
    const blob = new Blob([txt], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `espectro_choc08_${s.zona}_${s.suelo}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert("No se pudo exportar el espectro: " + (err.message || err));
  }
}

// ─── PESTAÑA PROCEDIMIENTO ────────────────────────────────────────────────────
// Reproduce los pasos de los MD fuente: objetivo, navegación ETABS, datos+origen,
// verificación y errores comunes.
function etabsProcedimientoHTML(proc) {
  if (!proc || !Array.isArray(proc.pasos) || !proc.pasos.length)
    return `<div style="color:var(--text-dim);font-size:12px">No se pudo cargar el procedimiento.</div>`;
  const meta = proc.meta || {};
  const list = (arr, color) => (Array.isArray(arr) && arr.length)
    ? `<ul style="margin:3px 0 0 0;padding-left:18px;line-height:1.5">${arr.map(x => `<li style="${color ? `color:${color}` : ""}">${esc(x)}</li>`).join("")}</ul>`
    : "";

  const pasos = proc.pasos.map(p => `
    <details ${p.n === 8 ? "open" : ""} style="border:1px solid var(--border);border-radius:5px;margin-bottom:8px;background:var(--surface)">
      <summary style="cursor:pointer;padding:8px 12px;font-weight:700;font-size:13px;display:flex;align-items:baseline;gap:8px">
        <span style="color:var(--accent)">Paso ${p.n}</span>
        <span>${esc(p.titulo)}</span>
        <span style="margin-left:auto;font-size:9px;color:var(--text-dim);font-weight:400">${esc(p.capitulo || "")}</span>
      </summary>
      <div style="padding:4px 14px 12px 14px;font-size:12px;line-height:1.5">
        <div style="margin:4px 0"><b style="color:var(--accent)">Objetivo:</b> ${esc(p.objetivo || "")}</div>
        <div style="margin:6px 0"><b style="color:var(--accent)">Navegación ETABS:</b>
          <div style="margin-top:3px;display:flex;flex-direction:column;gap:3px">
            ${(p.navegacion || []).map(n => `<code style="background:var(--bg);border:1px solid var(--border);border-radius:3px;padding:2px 7px;font-size:11px;display:inline-block">${esc(n)}</code>`).join("")}
          </div>
        </div>
        ${(p.datos && p.datos.length) ? `<div style="margin:6px 0"><b style="color:var(--accent)">Datos de entrada y su origen:</b>${list(p.datos)}</div>` : ""}
        ${p.verificacion ? `<div style="margin:6px 0"><b style="color:#27ae60">✓ Verificación:</b> ${esc(p.verificacion)}</div>` : ""}
        ${(p.errores && p.errores.length) ? `<div style="margin:6px 0"><b style="color:#e74c3c">⚠ Errores comunes:</b>${list(p.errores, "#e74c3c")}</div>` : ""}
      </div>
    </details>`).join("");

  return `
    <div style="font-size:11px;color:var(--text-dim);background:var(--surface2);border:1px solid var(--border);border-radius:4px;padding:9px 12px;margin-bottom:12px;line-height:1.55">
      📖 <b>${esc(meta.titulo || "Procedimiento ETABS")}</b><br>
      Proyecto ejemplo: <b>${esc(meta.proyecto || "")}</b> · ${esc(meta.normas || "")} · ${esc(meta.etabs || "")}<br>
      <span style="color:var(--accent)">Datos ya resueltos:</span> ${esc(meta.datos_resueltos || "")}<br>
      <span style="font-size:10px">Fuente: ${(meta.fuentes || []).map(esc).join(" · ")}</span>
    </div>
    ${pasos}`;
}

// ─── PESTAÑA CARGAR DATOS DE ETABS ────────────────────────────────────────────
function etabsCargaHTML(doc) {
  doc = doc || {};
  const tablas = (doc.tablas || []).map(t => `<tr>
    <td style="padding:4px 10px;font-weight:700;white-space:nowrap">${esc(t.tabla)}</td>
    <td style="padding:4px 10px;font-family:monospace;font-size:11px;color:var(--text-dim)">${esc(t.columnas)}</td>
    <td style="padding:4px 10px">${esc(t.lee)}</td>
  </tr>`).join("");
  const pasosProd = (doc.como_producirlo || []).map(x => `<li style="margin-bottom:3px">${esc(x)}</li>`).join("");

  return `
    <div style="font-size:11px;color:var(--text-dim);background:var(--surface2);border:1px solid var(--border);border-radius:4px;padding:9px 12px;margin-bottom:12px;line-height:1.55">
      ⬆ <b>Cargar datos de ETABS</b><br>${esc(doc.que_es || "")}
    </div>

    <div style="border:1px solid var(--border);border-radius:5px;padding:10px 12px;margin-bottom:12px;background:var(--surface)">
      <div style="font-size:11px;font-weight:700;color:var(--accent);margin-bottom:6px">¿Cómo producir el archivo en ETABS?</div>
      <ol style="margin:0;padding-left:20px;font-size:12px;line-height:1.5">${pasosProd}</ol>
    </div>

    <div style="border:1px solid var(--border);border-radius:5px;padding:10px 12px;margin-bottom:12px;background:var(--surface)">
      <div style="font-size:11px;font-weight:700;color:var(--accent);margin-bottom:6px">Tablas y columnas que el loader reconoce</div>
      <table style="border-collapse:collapse;font-size:12px;width:100%">
        <thead><tr style="color:var(--text-dim);font-size:10px;text-align:left">
          <th style="padding:3px 10px">Tabla ETABS</th><th style="padding:3px 10px">Columnas</th><th style="padding:3px 10px">Qué se lee</th>
        </tr></thead>
        <tbody>${tablas}</tbody>
      </table>
    </div>

    <div style="border:1px solid var(--accent);border-radius:5px;padding:12px;margin-bottom:12px;background:var(--surface)">
      <div style="font-size:11px;font-weight:700;color:var(--accent);margin-bottom:8px">Cargar export (.csv / .xlsx) o pegar la tabla</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:8px">
        <input type="file" id="et-file" accept=".csv,.tsv,.txt,.xlsx" style="font-size:12px"/>
        <button id="et-file-btn" class="btn-primary" style="font-size:12px;padding:5px 12px">Procesar archivo</button>
      </div>
      <div style="font-size:10px;color:var(--text-dim);margin-bottom:6px">…o pega aquí el texto copiado de las tablas de ETABS:</div>
      <textarea id="et-paste" rows="5" placeholder="OutputCase,FX,FY,FZ&#10;Dead,0,0,1206&#10;SH,540,510,0&#10;Mode,Period&#10;1,0.31&#10;Story,OutputCase,Direction,Drift&#10;L2,SH,X,0.0041" style="width:100%;box-sizing:border-box;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:3px;font-family:monospace;font-size:11px;padding:6px"></textarea>
      <div style="margin-top:8px"><button id="et-paste-btn" class="btn-primary" style="font-size:12px;padding:5px 12px">Procesar texto pegado</button></div>
      <div style="font-size:10px;color:var(--text-dim);margin-top:6px">Acepta <b>.xlsx</b> (multi-hoja: Base Reactions, Modal Periods, Story Drifts, Mass Summary), <b>.csv/.tsv</b> o texto pegado. El parser es tolerante con los nombres de hoja/columna: si falta una tabla, avisa y sigue.</div>
    </div>

    <div id="et-load-result"></div>`;
}

// Engancha los controles del loader.
function bindEtabsLoader() {
  const fileBtn  = document.getElementById("et-file-btn");
  const pasteBtn = document.getElementById("et-paste-btn");
  if (fileBtn) fileBtn.addEventListener("click", () => {
    const f = document.getElementById("et-file");
    if (!f || !f.files || !f.files[0]) { alert("Selecciona un archivo .csv/.xlsx primero."); return; }
    cargarExportEtabs({ file: f.files[0] });
  });
  if (pasteBtn) pasteBtn.addEventListener("click", () => {
    const ta = document.getElementById("et-paste");
    const txt = ta ? ta.value : "";
    if (!txt.trim()) { alert("Pega el texto de las tablas de ETABS primero."); return; }
    cargarExportEtabs({ texto: txt });
  });
}

// Envía el export al backend, autollena la hoja y muestra el resumen de lo leído.
async function cargarExportEtabs({ file, texto }) {
  const out = document.getElementById("et-load-result");
  if (out) out.innerHTML = `<div style="font-size:12px;color:var(--text-dim)">Procesando…</div>`;
  let res;
  // pid del presupuesto activo (para escalado/derivas contra el ContextoSismico
  // persistido); si no hay, el backend usa los params de la hoja / defaults.
  const sPid = etabsState.pid || null;
  const qs = sPid ? ("?pid=" + encodeURIComponent(sPid)) : "";
  try {
    if (file) {
      // .xlsx (multi-hoja) y .csv/.txt se envían como multipart; el backend
      // detecta el formato y elige el parser (openpyxl vs CSV tolerante).
      const fd = new FormData();
      fd.append("archivo", file, file.name);
      if (sPid) fd.append("pid", sPid);
      // params de la hoja por si no hay contexto persistido
      fd.append("zona", etabsState.zona); fd.append("suelo", etabsState.suelo);
      fd.append("I", etabsState.I); fd.append("Rw", etabsState.Rw);
      fd.append("hn_m", etabsState.hn_m); fd.append("regular", "true");
      const r = await fetch(API + "/diseno/sismo/import-etabs" + qs, { method: "POST", body: fd });
      if (!r.ok) throw new Error("HTTP " + r.status);
      res = await r.json();
    } else {
      res = await api("POST", "/diseno/sismo/import-etabs" + qs, {
        texto, pid: sPid, zona: etabsState.zona, suelo: etabsState.suelo,
        I: etabsState.I, Rw: etabsState.Rw, hn_m: etabsState.hn_m, regular: "true",
      });
    }
  } catch (err) {
    if (out) out.innerHTML = `<div style="color:#e74c3c;font-size:12px">Error al procesar: ${esc(err.message || String(err))}</div>`;
    return;
  }

  // Autollenar la hoja con lo leído.
  const s = etabsState;
  let cambios = [];
  if (res.W != null)      { s.W_t = res.W; cambios.push("W = " + res.W + " kgf"); etabsMarcarSucio(); }
  if (res.T != null)      { s.T_etabs = res.T; }
  if (res.V_din != null)  { s.Vdin_etabs = res.V_din; etabsMarcarSucio(); }
  if (res.deriva != null) { s.deriva_etabs = res.deriva; etabsMarcarSucio(); }

  const fmtMap = { xlsx: "Excel multi-hoja (.xlsx)", csv: "CSV/TSV", texto: "texto pegado" };
  const formatoTxt = res.formato ? (fmtMap[res.formato] || res.formato) : null;
  const hojasTxt = Array.isArray(res.hojas) && res.hojas.length
    ? res.hojas.map(h => `${esc(h.hoja)} → ${(h.leyo || []).join(", ")}`).join(" · ")
    : "";

  const leido = (res.leido || []).map(x => `<li>${esc(x)}</li>`).join("");
  const avisos = (res.avisos || []).map(x => `<li style="color:#e67e22">${esc(x)}</li>`).join("");
  if (out) out.innerHTML = `
    <div style="border:1px solid #27ae60;border-radius:5px;padding:10px 12px;background:var(--surface)">
      <div style="font-size:11px;font-weight:700;color:#27ae60;margin-bottom:5px">RESULTADO DE LA LECTURA${formatoTxt ? ` <span style="color:var(--text-dim);font-weight:400">· formato: ${esc(formatoTxt)}</span>` : ""}</div>
      ${hojasTxt ? `<div style="font-size:10.5px;color:var(--text-dim);margin-bottom:6px">Hojas leídas: ${hojasTxt}</div>` : ""}
      ${leido ? `<ul style="margin:0;padding-left:18px;font-size:12px;line-height:1.6">${leido}</ul>` : `<div style="font-size:12px;color:var(--text-dim)">No se leyó ningún valor.</div>`}
      ${avisos ? `<div style="font-size:10px;font-weight:700;color:#e67e22;margin-top:8px">AVISOS</div><ul style="margin:0;padding-left:18px;font-size:11px;line-height:1.5">${avisos}</ul>` : ""}
      ${cambios.length ? `<div style="font-size:11px;color:var(--accent);margin-top:8px">✔ Autollenado en la hoja: ${esc(cambios.join(" · "))}. Abre la pestaña «Hoja de cálculo» para ver el recálculo y la verificación.</div>` : ""}
    </div>
    ${etabsEscaladoHTML(res.escalado)}
    ${etabsDerivasPorPisoHTML(res.verificacion_derivas)}`;
}

// Tarjeta "Escalado del cortante" (CHOC-08 1.3.6.5.3). Verde si cumple, rojo si no.
function etabsEscaladoHTML(e) {
  if (!e) return "";
  const ok = !!e.cumple;
  const col = ok ? "#27ae60" : "#e74c3c";
  const veredicto = ok
    ? "✓ El cortante dinámico cumple — no requiere escalado."
    : "✗ El cortante dinámico está por debajo del mínimo — debe escalarse.";
  const factorTxt = (e.factor_escala != null) ? Number(e.factor_escala).toFixed(4) : "—";
  const accion = ok
    ? `El caso SH no necesita ajuste (Scale Factor de escalado = 1.0).`
    : `En ETABS: <b>Define ▸ Load Cases ▸ SH ▸ Modify</b> y multiplica el Scale Factor actual por <b>${factorTxt}</b>, luego <b>reanaliza (F5)</b> y vuelve a cargar el export.`;
  const pisoCRw = e.piso_c_rw
    ? `<div style="font-size:10px;color:#e67e22;margin-top:4px">⚠ C/Rw aplicó el piso 0.075 (CHOC 1.3.6.4): real ${Number(e.C_Rw).toFixed(4)} → usado ${Number(e.C_Rw_aplicado).toFixed(4)}.</div>`
    : "";
  const fila = (lbl, val, u) => `<tr>
    <td style="padding:3px 10px;color:var(--text-dim)">${lbl}</td>
    <td style="padding:3px 10px;font-family:monospace;text-align:right">${val}${u ? ` <span style="color:var(--text-dim)">${u}</span>` : ""}</td></tr>`;
  return `
    <div style="border:2px solid ${col};border-radius:5px;padding:12px;margin-top:12px;background:var(--surface)">
      <div style="font-size:11px;font-weight:700;color:${col};margin-bottom:8px">ESCALADO DEL CORTANTE · CHOC-08 1.3.6.5.3 (${e.regular ? "estructura regular ≥ 90%" : "estructura irregular ≥ 100%"})</div>
      <table style="border-collapse:collapse;font-size:12px;width:100%;margin-bottom:8px">
        ${fila("V estático (Z·I·C/Rw·W)", Number(e.V_est).toLocaleString(), "kgf")}
        ${fila("V dinámico (ETABS, caso SH)", Number(e.V_din).toLocaleString(), "kgf")}
        ${fila(`Objetivo (${e.objetivo_pct}% de V_est)`, Number(e.V_objetivo).toLocaleString(), "kgf")}
        ${fila("% alcanzado", e.V_est ? ((e.V_din / e.V_est) * 100).toFixed(1) : "—", "%")}
        ${fila("<b>Factor de escala a aplicar al caso SH</b>", `<b>${factorTxt}</b>`, "")}
        ${fila("C / T usado", `${Number(e.C).toFixed(4)} / ${Number(e.T_usado).toFixed(4)} s`, "")}
      </table>
      <div style="font-size:10px;color:var(--text-dim);margin-bottom:6px">T por: ${esc(e.metodo_T || "—")}</div>
      ${pisoCRw}
      <div style="font-size:12px;font-weight:700;color:${col};margin-bottom:5px">${veredicto}</div>
      <div style="font-size:11px;line-height:1.5">${accion}</div>
    </div>`;
}

// Tabla "Derivas por piso" (CHOC-08 1.3.5.8.2) con semáforo por fila.
function etabsDerivasPorPisoHTML(v) {
  if (!v || !Array.isArray(v.pisos) || !v.pisos.length) return "";
  const r = v.resumen || {};
  const filas = v.pisos.map(p => {
    const ok = !!p.cumple;
    const col = ok ? "#27ae60" : "#e74c3c";
    const bg = ok ? "transparent" : "rgba(231,76,60,0.10)";
    return `<tr style="background:${bg}">
      <td style="padding:4px 10px">${esc(p.story || "—")}</td>
      <td style="padding:4px 10px">${esc(p.dir || "—")}</td>
      <td style="padding:4px 10px;font-family:monospace;text-align:right">${Number(p.drift).toFixed(6)}</td>
      <td style="padding:4px 10px;font-family:monospace;text-align:right;color:var(--text-dim)">${p.limite != null ? Number(p.limite).toFixed(6) : "—"}</td>
      <td style="padding:4px 10px;text-align:center;color:${col};font-weight:700">${ok ? "✓ OK" : "✗ EXCEDE"}</td>
    </tr>`;
  }).join("");
  const okG = r.cumple_global === true;
  const colG = r.cumple_global == null ? "var(--text-dim)" : (okG ? "#27ae60" : "#e74c3c");
  const resumenTxt = r.cumple_global == null
    ? "Sin límite de deriva para comparar."
    : (okG
        ? `✓ Todas las derivas cumplen (máx ${Number(r.max).toFixed(6)} ≤ límite ${Number(r.limite).toFixed(6)}).`
        : `✗ Hay pisos que exceden el límite (máx ${Number(r.max).toFixed(6)} en ${esc(r.story_max || "?")}-${esc(r.dir_max || "?")} > ${Number(r.limite).toFixed(6)}). Rigidizar y reanalizar.`);
  return `
    <div style="border:2px solid ${colG};border-radius:5px;padding:12px;margin-top:12px;background:var(--surface)">
      <div style="font-size:11px;font-weight:700;color:${colG};margin-bottom:8px">DERIVAS POR PISO · CHOC-08 1.3.5.8.2</div>
      <table style="border-collapse:collapse;font-size:12px;width:100%;margin-bottom:8px">
        <thead><tr style="color:var(--text-dim);font-size:10px;text-align:left">
          <th style="padding:3px 10px">Piso</th><th style="padding:3px 10px">Dir</th>
          <th style="padding:3px 10px;text-align:right">Deriva</th>
          <th style="padding:3px 10px;text-align:right">Límite</th>
          <th style="padding:3px 10px;text-align:center">Estado</th>
        </tr></thead>
        <tbody>${filas}</tbody>
      </table>
      <div style="font-size:12px;font-weight:700;color:${colG}">${resumenTxt}</div>
    </div>`;
}

// ─── PUENTE ETABS → CONCRETO (Div 03) ─────────────────────────────────────────
// Botón + mini-form en el panel Elementos de #diseno-view.
// POST /diseno/{pid}/import-etabs-concreto → crea elementos + casos (sin partidas).

function _setImportMode(material) {
  disenoState.importMaterial = material;
  const recub = document.getElementById("diseno-import-recub-wrap");
  const grado = document.getElementById("diseno-import-grado-wrap");
  const isAcero = material === "ACERO";
  if (recub) recub.style.display = isAcero ? "none" : "flex";
  if (grado) grado.style.display = isAcero ? "flex" : "none";
}

function initDisenoImportEtabs() {
  const btn      = document.getElementById("btn-diseno-import-etabs");
  const btnAc    = document.getElementById("btn-diseno-import-acero");
  const form     = document.getElementById("diseno-import-form");
  const btnCanc  = document.getElementById("btn-diseno-import-cancelar");
  const btnSend  = document.getElementById("btn-diseno-import-enviar");
  const openForm = (material) => {
    if (!state.activeId) { alert("Abre un presupuesto primero."); return; }
    _setImportMode(material);
    if (form) form.style.display = "";
  };
  if (btn)   btn.addEventListener("click", () => openForm("CONCRETO"));
  if (btnAc) btnAc.addEventListener("click", () => openForm("ACERO"));
  if (btnCanc) btnCanc.addEventListener("click", () => { if (form) form.style.display = "none"; });
  if (btnSend) btnSend.addEventListener("click", importarEtabs);
}

async function importarEtabs() {
  const pid = state.activeId;
  if (!pid) { alert("Abre un presupuesto primero."); return; }
  const isAcero = (disenoState.importMaterial || "CONCRETO") === "ACERO";
  const out    = document.getElementById("diseno-import-result");
  const fileEl  = document.getElementById("diseno-import-file");
  const pasteEl = document.getElementById("diseno-import-paste");
  const unidad  = document.getElementById("diseno-import-unidad")?.value || "kgf";
  const recub   = parseFloat(document.getElementById("diseno-import-recub")?.value || 4);
  const acero   = document.getElementById("diseno-import-acero-grado")?.value || "A992";
  const file    = fileEl && fileEl.files && fileEl.files[0];
  const texto   = pasteEl ? pasteEl.value.trim() : "";
  if (!file && !texto) { alert("Sube un archivo .csv/.xlsx o pega la tabla de ETABS."); return; }
  if (out) out.innerHTML = `<div style="font-size:11px;color:var(--text-dim)">Procesando…</div>`;
  const endpoint = isAcero ? `/diseno/${pid}/import-etabs-acero-fuerzas`
                           : `/diseno/${pid}/import-etabs-concreto`;

  let res;
  try {
    if (file) {
      const fd = new FormData();
      fd.append("archivo", file, file.name);
      fd.append("unidad", unidad);
      if (isAcero) fd.append("acero", acero);
      else fd.append("recubrimiento_cm", String(recub));
      const r = await fetch(API + endpoint, { method: "POST", body: fd });
      if (!r.ok) {
        const e = await r.json().catch(() => null);
        throw new Error(e?.detail || ("HTTP " + r.status));
      }
      res = await r.json();
    } else {
      const body = isAcero ? { texto, unidad, acero }
                           : { texto, unidad, recubrimiento_cm: recub };
      res = await api("POST", endpoint, body);
    }
  } catch (err) {
    if (out) out.innerHTML = `<div style="color:#e74c3c;font-size:11px;padding:6px">Error: ${esc(err.message || String(err))}</div>`;
    return;
  }

  if (out) out.innerHTML = isAcero ? renderAceroLrfdResult(res) : renderConcretoResult(res);
  // Refrescar la lista de elementos del módulo Diseño tras la importación.
  await loadElementos(pid);
}

function renderConcretoResult(res) {
  const gob = Array.isArray(res.gobernantes) ? res.gobernantes : [];
  const map = Array.isArray(res.mapeos_aproximados) ? res.mapeos_aproximados : [];
  const avs = Array.isArray(res.avisos) ? res.avisos : [];

  const filasGob = gob.map(g => {
    const okS = g.ok_sismico;
    const sem = okS == null
      ? `<span style="color:var(--text-dim)">—</span>`
      : (okS ? `<span style="color:#27ae60;font-weight:700">●</span>`
             : `<span style="color:#e74c3c;font-weight:700">●</span>`);
    const as = g.as_cm2 != null ? fmt(g.as_cm2, 2)
             : (g.as_col_cm2 != null ? fmt(g.as_col_cm2, 2) : "—");
    return `<tr>
      <td style="padding:3px 7px;font-family:monospace;font-size:11px">${esc(g.csi || "—")}</td>
      <td style="padding:3px 7px;font-size:11px">${esc(g.type_mark || "—")}</td>
      <td style="padding:3px 7px;font-size:11px;color:var(--text-dim)">${esc(g.combo || "—")}</td>
      <td style="padding:3px 7px;text-align:right;font-family:monospace;font-size:11px">${as}</td>
      <td style="padding:3px 7px;text-align:center">${sem}</td>
    </tr>`;
  }).join("");

  const tablaGob = gob.length ? `
    <div style="font-size:10px;font-weight:700;color:var(--accent);margin:8px 0 4px">CASOS GOBERNANTES</div>
    <table style="border-collapse:collapse;width:100%;font-size:11px">
      <thead><tr style="color:var(--text-dim);font-size:9px;text-align:left">
        <th style="padding:2px 7px">CSI</th><th style="padding:2px 7px">Type Mark</th>
        <th style="padding:2px 7px">Combo</th><th style="padding:2px 7px;text-align:right">As cm²</th>
        <th style="padding:2px 7px;text-align:center">Sísmico</th>
      </tr></thead><tbody>${filasGob}</tbody>
    </table>` : "";

  const mapHtml = map.length ? `
    <div style="border:1px solid #e67e22;background:rgba(230,126,34,.10);border-radius:4px;padding:7px 9px;margin-top:8px">
      <div style="font-size:10px;font-weight:700;color:#e67e22;margin-bottom:3px">⚠ MAPEOS APROXIMADOS (${map.length})</div>
      <ul style="margin:0;padding-left:16px;font-size:10px;line-height:1.5;color:var(--text-dim)">
        ${map.map(m => `<li>${esc(typeof m === "string" ? m : JSON.stringify(m))}</li>`).join("")}
      </ul>
    </div>` : "";

  const avsHtml = avs.length ? `
    <ul style="margin:8px 0 0;padding-left:16px;font-size:10px;line-height:1.5;color:#e67e22">
      ${avs.map(a => `<li>${esc(a)}</li>`).join("")}
    </ul>` : "";

  return `
    <div style="border:1px solid #27ae60;border-radius:4px;padding:8px 10px;background:var(--surface)">
      <div style="font-size:11px;font-weight:700;color:#27ae60;margin-bottom:4px">✔ IMPORTADO DE ETABS</div>
      <div style="font-size:11px">Elementos creados: <b>${res.elementos_creados ?? 0}</b> · Casos: <b>${res.casos_creados ?? 0}</b></div>
      <div style="font-size:9.5px;color:var(--text-dim);margin-top:2px">Unidad: ${esc(res.unidad_entrada || "—")} · Recub: ${res.recubrimiento_cm ?? "—"} cm</div>
      ${tablaGob}
      ${mapHtml}
      ${avsHtml}
    </div>`;
}

function renderAceroLrfdResult(res) {
  const gob   = Array.isArray(res.gobernantes) ? res.gobernantes : [];
  const nomap = Array.isArray(res.perfiles_no_mapeados) ? res.perfiles_no_mapeados : [];
  const avs   = Array.isArray(res.avisos) ? res.avisos : [];

  const filas = gob.map(g => {
    const sem = g.cumple ? `<span style="color:#27ae60;font-weight:700">●</span>`
                         : `<span style="color:#e74c3c;font-weight:700">●</span>`;
    return `<tr>
      <td style="padding:3px 7px;font-family:monospace;font-size:11px">${esc(g.csi || "—")}</td>
      <td style="padding:3px 7px;font-size:11px">${esc(g.perfil || "—")}</td>
      <td style="padding:3px 7px;font-size:11px;color:var(--text-dim)">${esc(g.combo || "—")}</td>
      <td style="padding:3px 7px;font-size:11px">${esc(g.estado_gob || "—")}</td>
      <td style="padding:3px 7px;text-align:right;font-family:monospace;font-size:11px">${fmt(g.dc, 3)}</td>
      <td style="padding:3px 7px;text-align:center">${sem}</td>
    </tr>`;
  }).join("");

  const tabla = gob.length ? `
    <div style="font-size:10px;font-weight:700;color:var(--accent);margin:8px 0 4px">CASOS GOBERNANTES (LRFD §D–H)</div>
    <table style="border-collapse:collapse;width:100%;font-size:11px">
      <thead><tr style="color:var(--text-dim);font-size:9px;text-align:left">
        <th style="padding:2px 7px">CSI</th><th style="padding:2px 7px">Perfil</th>
        <th style="padding:2px 7px">Combo</th><th style="padding:2px 7px">Estado</th>
        <th style="padding:2px 7px;text-align:right">DC</th><th style="padding:2px 7px;text-align:center">OK</th>
      </tr></thead><tbody>${filas}</tbody>
    </table>` : "";

  const nomapHtml = nomap.length ? `
    <div style="border:1px solid #e67e22;background:rgba(230,126,34,.10);border-radius:4px;padding:7px 9px;margin-top:8px">
      <div style="font-size:10px;font-weight:700;color:#e67e22;margin-bottom:3px">⚠ PERFILES NO MAPEADOS (${nomap.length})</div>
      <ul style="margin:0;padding-left:16px;font-size:10px;line-height:1.5;color:var(--text-dim)">
        ${nomap.map(m => `<li>${esc(m.member || "")}: ${esc(m.section || "")}</li>`).join("")}
      </ul>
    </div>` : "";

  const avsHtml = avs.length ? `
    <ul style="margin:8px 0 0;padding-left:16px;font-size:10px;line-height:1.5;color:#e67e22">
      ${avs.map(a => `<li>${esc(a)}</li>`).join("")}
    </ul>` : "";

  return `
    <div style="border:1px solid #5b6bbf;border-radius:4px;padding:8px 10px;background:var(--surface)">
      <div style="font-size:11px;font-weight:700;color:#5b6bbf;margin-bottom:4px">✔ IMPORTADO DE ETABS — ACERO LRFD</div>
      <div style="font-size:11px">Elementos: <b>${res.elementos_creados ?? 0}</b> · Casos: <b>${res.casos_creados ?? 0}</b> · Acero: <b>${esc(res.acero_grado || "A992")}</b></div>
      <div style="font-size:9.5px;color:var(--text-dim);margin-top:2px">Unidad: ${esc(res.unidad_entrada || "—")} · Verificación §D–H propia (chequeo cruzado de ETABS)</div>
      ${tabla}
      ${nomapHtml}
      ${avsHtml}
    </div>`;
}

// ─── PUENTE ETABS → ACERO (Div 05) — vista #acero-view ────────────────────────
// POST /diseno/{pid}/import-etabs-acero (?generar=true opcional).

function initAceroView() {
  const btnClose = document.getElementById("btn-cerrar-acero-view");
  if (btnClose) btnClose.addEventListener("click", () => {
    document.getElementById("acero-view").style.display = "none";
    const s = document.getElementById("sel-modulo"); if (s) s.value = "";
  });
}

// ─── MÓDULO MIEMBRO ACERO — AISC 360-16 §D/E/F/G/H (LRFD, estilo Mathcad) ─────
// Aditivo, STATELESS. Verificación INDEPENDIENTE: calcula φRn propio por estado
// límite y compara contra demanda Pu/Mu/Vu (chequeo cruzado de ETABS).
// Catálogo de perfiles pedido a /miembro-acero/catalogo (NO se hardcodean).
// Reemplaza la vista del puente ETABS→Div05 (importarAceroEtabs sigue en backend).

const miembroState = {
  perfil: "W310X73", acero: "A992",
  L_cm: 400, K: 1.0, Lb_cm: 0, Cb: 1.0,
  pu_t: -50, mux_tm: 10, muy_tm: 0, vu_t: 20,
  catalogo: null, ultima: null, timer: null,
};

async function miembroCargarCatalogo() {
  if (miembroState.catalogo) return miembroState.catalogo;
  try { miembroState.catalogo = await api("GET", "/miembro-acero/catalogo"); }
  catch { miembroState.catalogo = { perfiles: [], aceros: [] }; }
  return miembroState.catalogo;
}

async function renderAcero() {
  const cont = document.getElementById("acero-content");
  if (!cont) return;
  const s = miembroState;
  if (!s.vista || s.vista === "import") s.vista = "calculo";
  // Split-view igual a Diseño: sidebar (import + elementos) | Hoja §D-H persistente + tabs.
  cont.innerHTML = `
    <div style="display:flex;height:100%;overflow:hidden">
      <div style="width:252px;min-width:210px;border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden">
        <div style="padding:8px 10px;border-bottom:1px solid var(--border)">
          <button id="acero-imp-toggle" class="btn-primary" style="width:100%;font-size:11px;padding:5px 8px">⬆ Importar de ETABS</button>
          <div id="acero-imp-form" style="display:none;margin-top:7px"></div>
          <button id="acero-genpart-btn2" class="btn-primary" style="width:100%;font-size:11px;padding:5px 8px;margin-top:6px" title="Genera partidas Div 05 (mL) por ficha desde los elementos de acero de la obra">📦 Generar partidas Div 05</button>
          <div id="acero-partidas-result" style="margin-top:6px"></div>
        </div>
        <div style="font-size:10px;font-weight:700;color:var(--text-dim);letter-spacing:.5px;padding:8px 10px 4px">ELEMENTOS DE ACERO</div>
        <div id="acero-elementos-list" style="overflow-y:auto;flex:1;padding:4px 8px">Cargando…</div>
      </div>
      <div style="flex:1;display:flex;flex-direction:column;overflow:hidden">
        <div style="display:flex;align-items:center;gap:8px;padding:9px 14px;border-bottom:1px solid var(--border);flex-wrap:wrap">
          <b style="font-size:14px">Acero Estructural</b>
          <span style="font-size:11px;color:var(--text-dim)">AISC 360-16 LRFD §D-H · Div 05</span>
          <span id="acero-elem-chip" style="font-size:11px;color:var(--accent)"></span>
          <div style="margin-left:auto;display:flex;gap:4px">
            <button class="tab-btn ${s.vista === 'calculo' ? 'active' : ''}" data-atab="calculo" style="font-size:11px">🧮 Hoja §D-H</button>
            <button class="tab-btn ${s.vista === 'ayuda' ? 'active' : ''}" data-atab="ayuda" style="font-size:11px">📖 Cómo se usa</button>
          </div>
        </div>
        <div id="acero-body" style="flex:1;overflow-y:auto"></div>
      </div>
    </div>`;
  cont.querySelectorAll("[data-atab]").forEach(b => b.addEventListener("click", () => {
    cont.querySelectorAll("[data-atab]").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    miembroState.vista = b.dataset.atab;
    renderAceroVista();
  }));
  const tg = document.getElementById("acero-imp-toggle");
  if (tg) tg.addEventListener("click", () => {
    const f = document.getElementById("acero-imp-form");
    if (!f) return;
    if (f.style.display === "none") { f.innerHTML = aceroImportFormHTML(); f.style.display = ""; bindAceroImport(); }
    else { f.style.display = "none"; }
  });
  const gp = document.getElementById("acero-genpart-btn2");
  if (gp) gp.addEventListener("click", aceroGenerarPartidas);
  loadAceroElementos();
  renderAceroVista();
}

function renderAceroVista() {
  const body = document.getElementById("acero-body");
  if (!body) return;
  if (miembroState.vista === "ayuda") { body.innerHTML = vistaAceroAyudaHTML(); return; }
  renderAceroCalculo(body);
}

async function renderAceroCalculo(body) {
  body.innerHTML = `<div style="padding:40px;text-align:center;color:var(--text-dim);font-size:13px">Cargando catálogo…</div>`;
  const cat = await miembroCargarCatalogo();
  const s = miembroState;
  const selStyle = "background:var(--surface2);border:1px solid var(--accent);color:var(--text);padding:3px 7px;border-radius:3px;font-weight:600;font-size:12px";
  const inpStyle = "width:90px;background:var(--bg);border:1px solid var(--accent);color:var(--text);padding:3px 6px;border-radius:3px;font-family:monospace;font-weight:600";

  const perfilOpts = (cat.perfiles || []).map(p =>
    `<option value="${escapeAttr(p.perfil)}" ${p.perfil === s.perfil ? "selected" : ""}>${esc(p.perfil)}${p.hss ? " (HSS §E3/F7/G4)" : ""}</option>`).join("");
  const aceroOpts = (cat.aceros || []).map(a =>
    `<option value="${escapeAttr(a.clave)}" ${a.clave === s.acero ? "selected" : ""}>${esc(a.clave)} · ${esc(a.desc)}</option>`).join("");

  const miRow = (key, sym, unit, val, step) =>
    `<div style="display:flex;align-items:center;gap:6px;padding:2px 0">
      <span style="min-width:34px;text-align:right">${kx(sym, sym)}</span>
      <span style="color:var(--accent);font-weight:700">:=</span>
      <input data-mi="${key}" type="number" step="${step || "any"}" value="${val}" style="${inpStyle}"/>
      <span style="font-size:10px;color:var(--text-dim)">${esc(unit)}</span>
    </div>`;

  body.innerHTML = `
   <div style="padding:14px 16px;max-width:1040px">
     <div style="font-size:11px;color:var(--text-dim);background:var(--surface2);border:1px solid var(--border);border-radius:4px;padding:8px 11px;margin-bottom:10px;line-height:1.5">
       🔩 <b>Miembro de acero LRFD (AISC 360-16 §D/E/F/G/H)</b> estilo Mathcad, métrico (kgf, cm, t). <b>Verificación independiente</b>: calcula φRn propio por estado límite (tracción §D, compresión §E, flexión §F, cortante §G, flexo-compresión §H) y lo compara contra la demanda — chequeo cruzado del Steel Frame Design de ETABS. Propiedades de sección (Z, S, r, r_ts) <b>derivadas de la geometría</b> y mostradas como fórmulas. <b>Sin persistencia</b> (cálculo).
     </div>

     <div style="border:1px solid var(--accent);border-radius:5px;padding:10px 12px;margin-bottom:10px;background:var(--surface)">
       <div style="font-size:10px;font-weight:700;color:var(--accent);letter-spacing:.5px;margin-bottom:8px">PERFIL Y MATERIAL</div>
       <div style="display:flex;gap:20px;flex-wrap:wrap;align-items:flex-end">
         <div><div style="font-size:10px;color:var(--text-dim);margin-bottom:2px">Perfil</div>
           <select id="mi-perfil" style="${selStyle};min-width:230px">${perfilOpts}</select></div>
         <div><div style="font-size:10px;color:var(--text-dim);margin-bottom:2px">Acero</div>
           <select id="mi-acero" style="${selStyle};min-width:200px">${aceroOpts}</select></div>
       </div>
       <div id="mi-rotulo" style="margin-top:10px;font-size:13px;font-weight:700;padding:7px 11px;border-radius:4px;background:var(--surface2);border:1px solid var(--border)">calculando…</div>
     </div>

     <div style="border:1px solid var(--accent);border-radius:5px;padding:10px 12px;margin-bottom:12px;background:var(--surface)">
       <div style="font-size:10px;font-weight:700;color:var(--accent);letter-spacing:.5px;margin-bottom:7px">VARIABLES EDITABLES — geometría · demanda (ETABS, combo LRFD)</div>
       <div style="display:flex;gap:30px;flex-wrap:wrap;align-items:flex-start">
         <div style="min-width:200px">
           <div style="font-size:10px;font-weight:700;color:var(--text-dim);margin-bottom:3px">Geometría / arriostramiento</div>
           ${miRow("L_cm", "L", "cm", s.L_cm, "1")}
           ${miRow("K", "K", "", s.K, "0.05")}
           ${miRow("Lb_cm", "L_b", "cm (0=L)", s.Lb_cm, "1")}
           ${miRow("Cb", "C_b", "", s.Cb, "0.05")}
         </div>
         <div style="min-width:200px">
           <div style="font-size:10px;font-weight:700;color:var(--text-dim);margin-bottom:3px">Demanda axial / cortante</div>
           ${miRow("pu_t", "P_u", "t (+T/−C)", s.pu_t, "1")}
           ${miRow("vu_t", "V_u", "t", s.vu_t, "1")}
         </div>
         <div style="min-width:200px">
           <div style="font-size:10px;font-weight:700;color:var(--text-dim);margin-bottom:3px">Demanda flexión</div>
           ${miRow("mux_tm", "M_{ux}", "t·m", s.mux_tm, "0.5")}
           ${miRow("muy_tm", "M_{uy}", "t·m", s.muy_tm, "0.5")}
         </div>
       </div>
     </div>

     <div style="font-size:11px;font-weight:700;color:var(--text-dim);letter-spacing:.5px;margin-bottom:6px">DESARROLLO — símbolo := fórmula = sustitución = resultado</div>
     <div id="mi-desarrollo" style="font-size:14px">cargando…</div>
     <div style="border:1px solid var(--border);border-radius:5px;padding:8px 11px;margin-top:14px;background:var(--surface)">
       <div style="font-size:10px;font-weight:700;color:var(--text-dim);letter-spacing:.5px;margin-bottom:5px">CONSTANTES (fijas)</div>
       <div id="mi-constantes" style="display:grid;grid-template-columns:repeat(3,1fr);gap:5px 20px;font-size:13px"></div>
     </div>
     <div id="mi-avisos" style="margin-top:10px"></div>
     <div style="font-size:10px;color:var(--text-dim);text-align:center;margin-top:14px;line-height:1.5">
       Miembros <b>AISC 360-16 §D/E/F/G/H</b>. Métrico kgf/cm/t. Perfiles I (props CISC/AISC) y <b>HSS cuadrado</b> (§E3 compresión · §F7 flexión sin LTB · §G4 cortante). Pendiente: pandeo local F3/E7 de paredes/alas esbeltas.
     </div>
   </div>`;

  bindMiembroInputs();
  recalcMiembro();
}

function bindMiembroInputs() {
  const s = miembroState;
  const onSel = (id, key) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", () => { s[key] = el.value; recalcMiembro(); });
  };
  onSel("mi-perfil", "perfil");
  onSel("mi-acero", "acero");
  document.querySelectorAll("#acero-content input[data-mi]").forEach(inp => {
    inp.addEventListener("input", () => {
      const k = inp.dataset.mi;
      const v = parseFloat(inp.value);
      s[k] = isNaN(v) ? 0 : v;
      clearTimeout(s.timer);
      s.timer = setTimeout(recalcMiembro, 250);
    });
  });
}

// Descripción de cada sección de la Hoja (lógica del grupo de fórmulas).
const MIEMBRO_SEC = {
  "Material":       ["AISC Tabla 2-4 / §E",  "F_y rige fluencia (tracción, compresión, cortante); F_u rige rotura. E = módulo de elasticidad, gobierna el pandeo (Fe) y el LTB."],
  "Seccion":        ["Resist. de materiales", "Propiedades derivadas de la geometría d/bf/tf/tw: Z_x (→Mp), S_x (→LTB), r_x/r_y (→pandeo, el menor gobierna), r_ts (→LTB elástico)."],
  "Demanda":        ["AISC §B3.1 · LRFD",     "P_u (+tracción/−compresión), M_ux, M_uy, V_u del análisis (ETABS, combo gobernante). L/K/L_b/C_b definen pandeo y arriostramiento lateral."],
  "§D Traccion":    ["AISC 360-16 §D2",       "φP_n = menor entre fluencia del área bruta (0.90·F_y·A_g) y rotura del área neta (0.75·F_u·A_e). Para miembro sin agujeros A_e = A_g."],
  "§E Compresion":  ["AISC 360-16 §E3",       "Esbeltez KL/r (r menor gobierna) → Fe de Euler → Fcr: inelástico si KL/r ≤ 4.71√(E/F_y), si no elástico (0.877·Fe). φP_n = 0.90·Fcr·A_g."],
  "§F Flexion":     ["AISC 360-16 §F2",       "Mp = F_y·Z_x. L_p y L_r definen la zona: L_b ≤ L_p plástico (Mp); L_p<L_b≤L_r LTB inelástico; L_b>L_r LTB elástico. φM_n = 0.90·M_n."],
  "§G Cortante":    ["AISC 360-16 §G2",       "φV_n = φ·0.6·F_y·A_w·C_v1, A_w = d·t_w. Alma laminada compacta (h/t_w ≤ 2.24√(E/F_y)) → C_v1 = 1.0 y φ = 1.0."],
  "§H Interaccion": ["AISC 360-16 §H1",       "Flexo-compresión: combina axial + momento. Si P_r/P_c ≥ 0.2 usa H1-1a (factor 8/9); si < 0.2 usa H1-1b. Debe quedar ≤ 1.0."],
  "Verificacion":   ["AISC §B3.1",            "DC = demanda/φRn por estado; gobierna el de mayor DC. El miembro cumple si DC_gobernante ≤ 1.0 en todos los estados."],
};

async function recalcMiembro() {
  const dev = document.getElementById("mi-desarrollo");
  const con = document.getElementById("mi-constantes");
  const rot = document.getElementById("mi-rotulo");
  const avi = document.getElementById("mi-avisos");
  if (!dev) return;
  const s = miembroState;
  const body = {
    perfil: s.perfil, acero: s.acero,
    L_cm: s.L_cm, K: s.K, Lb_cm: s.Lb_cm, Cb: s.Cb,
    pu_t: s.pu_t, mux_tm: s.mux_tm, muy_tm: s.muy_tm, vu_t: s.vu_t,
  };
  let m;
  try { m = await api("POST", "/miembro-acero/memoria-rapida", body); }
  catch (err) { dev.innerHTML = `<div style="color:#e74c3c;font-size:12px">Error: ${esc(err.message)}</div>`; return; }
  miembroState.ultima = m;
  const meta = m.meta || {};

  // Rótulo de estado (verde/naranja/rojo según DC)
  if (rot) {
    const dc = meta.dc_gobernante;
    const cumple = meta.cumple;
    const col = dc == null ? "var(--text-dim)" : (!cumple ? "#e74c3c" : (dc >= 0.9 ? "#e67e22" : "#27ae60"));
    rot.style.borderColor = col; rot.style.color = col;
    const estado = cumple ? "✓ CUMPLE" : (dc == null ? "—" : "✗ NO CUMPLE");
    rot.innerHTML = `🔩 ${esc(meta.resumen || "—")} <span style="font-weight:700">· ${estado}</span>`;
  }

  if (con && Array.isArray(m.constantes))
    con.innerHTML = m.constantes.map(c => `<div title="${esc(c.desc || "")}">${kx(c.latex, c.simbolo)}</div>`).join("");

  // Avisos honestos del motor
  const avisos = Array.isArray(meta.avisos) ? meta.avisos : [];
  if (avi) avi.innerHTML = avisos.length ? `
    <div style="border:1px solid #e67e22;background:rgba(230,126,34,.08);border-radius:5px;padding:8px 11px">
      <div style="font-size:10px;font-weight:700;color:#e67e22;letter-spacing:.5px;margin-bottom:4px">AVISOS</div>
      <ul style="margin:0;padding-left:18px;font-size:11px;line-height:1.5;color:var(--text-dim)">
        ${avisos.map(a => `<li>${esc(a)}</li>`).join("")}
      </ul></div>` : "";

  // Desarrollo agrupado por sección
  const orden = [], grupos = {};
  (m.pasos || []).forEach(p => { if (!grupos[p.seccion]) { grupos[p.seccion] = []; orden.push(p.seccion); } grupos[p.seccion].push(p); });
  dev.innerHTML = orden.map((sec, i) => {
    const [ref, intro] = MIEMBRO_SEC[sec] || ["AISC 360-16", ""];
    return `<div style="margin-bottom:14px">
      <div style="display:flex;align-items:baseline;gap:8px;border-bottom:2px solid var(--accent);padding-bottom:3px;margin-bottom:6px">
        <span style="font-size:12px;font-weight:700">${i + 1}. ${esc(sec)}</span>
        <span style="font-size:9px;font-weight:700;color:var(--accent);border:1px solid var(--accent);border-radius:8px;padding:1px 7px">${esc(ref)}</span>
      </div>
      ${intro ? `<div style="font-size:11px;color:var(--text-dim);font-style:italic;margin-bottom:7px;line-height:1.45">${esc(intro)}</div>` : ""}
      ${grupos[sec].map(etabsDevLine).join("")}
    </div>`;
  }).join("");
}

// ── Form de Import (sidebar) — import-etabs-acero (Steel Frame Summary XLSX) ──
function aceroImportFormHTML() {
  return `
    <div style="border:1px solid var(--accent);border-radius:4px;padding:8px;background:var(--surface)">
      <div style="font-size:10px;color:var(--text-dim);margin-bottom:6px;line-height:1.4">Steel Frame Design Summary XLSX (ETABS: Display → Show Tables → Steel Frame Design → Export to Excel). Genera partidas Div 05 automáticamente.</div>
      <input type="file" id="acero-imp-file" accept=".xlsx,.csv,.tsv,.txt" style="font-size:10px;width:100%;margin-bottom:6px"/>
      <button id="acero-imp-btn" class="btn-primary" style="width:100%;font-size:11px;padding:4px">Importar y generar partidas</button>
      <div id="acero-import-result" style="margin-top:6px"></div>
    </div>`;
}

function bindAceroImport() {
  const btn = document.getElementById("acero-imp-btn");
  if (btn) btn.addEventListener("click", aceroImportSubmit);
}

async function aceroGenerarPartidas() {
  const pid = state.activeId;
  if (!pid) { alert("Abre un presupuesto primero."); return; }
  const out = document.getElementById("acero-partidas-result");
  if (out) out.innerHTML = `<div style="font-size:11px;color:var(--text-dim)">Generando…</div>`;
  let res;
  try { res = await api("POST", `/diseno/${pid}/acero-generar-partidas`, {}); }
  catch (err) { if (out) out.innerHTML = `<div style="color:#e74c3c;font-size:11px">Error: ${esc(err.message)}</div>`; return; }
  if (res.status === "sin_elementos") {
    if (out) out.innerHTML = `<div style="font-size:11px;color:#e67e22">${esc((res.avisos || []).join(" "))}</div>`;
    return;
  }
  const parts = res.partidas_generadas || [];
  const noMap = res.perfiles_no_mapeados || [];
  const filas = parts.map(p => `<li><b>${esc(p.clave)}</b> · ${esc(p.ficha)} · ${esc(p.perfil)} (${esc(p.rol)}) · ${fmt(p.cantidad, 2)} mL</li>`).join("");
  const noMapHtml = noMap.length ? `<div style="font-size:10px;color:#e67e22;margin-top:5px">⚠ No mapeados: ${noMap.map(m => esc(m.perfil || m.section || "?")).join(", ")}</div>` : "";
  if (out) out.innerHTML = `
    <div style="border:1px solid #27ae60;border-radius:5px;padding:8px 11px;background:var(--surface)">
      <div style="font-size:11px;font-weight:700;color:#27ae60;margin-bottom:4px">📦 ${parts.length} partidas Div 05 generadas (${res.n_elementos} elementos)</div>
      <ul style="margin:0;padding-left:18px;font-size:11px;line-height:1.5">${filas}</ul>
      ${noMapHtml}
      <div style="font-size:9.5px;color:var(--text-dim);margin-top:5px">Suministro mL · precio 0 (se inyecta por fichas). Las conexiones se costean en el módulo Conexión.</div>
    </div>`;
  if (typeof loadObra === "function") { try { loadObra(state.activeId); } catch (e) {} }
}

async function aceroImportSubmit() {
  const pid = state.activeId;
  if (!pid) { alert("Abre un presupuesto primero."); return; }
  const out = document.getElementById("acero-import-result");
  const fileEl = document.getElementById("acero-imp-file");
  const file = fileEl && fileEl.files && fileEl.files[0];
  if (!file) { alert("Sube un archivo .xlsx exportado de ETABS (Steel Frame Design Summary)."); return; }
  if (out) out.innerHTML = `<div style="font-size:11px;color:var(--text-dim)">Procesando…</div>`;
  const ep = `/diseno/${pid}/import-etabs-acero?generar=true`;
  let res;
  try {
    const fd = new FormData();
    fd.append("archivo", file, file.name);
    const r = await fetch(API + ep, { method: "POST", body: fd });
    if (!r.ok) { const e = await r.json().catch(() => null); throw new Error(e?.detail || ("HTTP " + r.status)); }
    res = await r.json();
  } catch (err) {
    if (out) out.innerHTML = `<div style="color:#e74c3c;font-size:11px;padding:6px">Error: ${esc(err.message || String(err))}</div>`;
    return;
  }
  if (out) out.innerHTML = renderAceroImportResult(res);
  loadAceroElementos();
}

function renderAceroImportResult(res) {
  if (!res) return `<div style="color:#e74c3c;font-size:11px">Sin respuesta del servidor.</div>`;
  const parts = res.partidas_generadas || [];
  const noMap = res.perfiles_no_mapeados || [];
  const miembros = res.miembros || [];
  const dcMax = miembros.length ? Math.max(...miembros.map(m => m.dc ?? 0)).toFixed(3) : "—";
  const sobre = miembros.filter(m => (m.dc ?? 0) > 1.0).length;
  const filas = parts.map(p => `<li><b>${esc(p.clave)}</b> · ${esc(p.ficha)} · ${esc(p.perfil)} (${esc(p.rol)}) · ${fmt(p.cantidad, 2)} mL</li>`).join("");
  const noMapHtml = noMap.length ? `<div style="font-size:10px;color:#e67e22;margin-top:5px">⚠ No mapeados: ${noMap.map(m => esc(m.perfil || m.section || "?")).join(", ")}</div>` : "";
  const overHtml = sobre ? `<div style="color:#e74c3c;font-size:10px;margin-top:4px">⚠ ${sobre} elemento(s) con D/C > 1.0</div>` : "";
  return `
    <div style="border:1px solid #27ae60;border-radius:5px;padding:8px 11px;background:var(--surface)">
      <div style="font-size:11px;font-weight:700;color:#27ae60;margin-bottom:4px">✅ ${miembros.length} elementos importados · D/C máx ${dcMax}</div>
      ${overHtml}
      <ul style="margin:4px 0;padding-left:18px;font-size:11px;line-height:1.5">${filas}</ul>
      ${noMapHtml}
    </div>`;

async function loadAceroElementos() {
  const cont = document.getElementById("acero-elementos-list");
  if (!cont) return;
  const pid = state.activeId;
  if (!pid) { cont.innerHTML = "Sin obra activa."; return; }
  let data;
  try { data = await api("GET", `/diseno/${pid}/elementos`); }
  catch { cont.innerHTML = "Error cargando elementos."; return; }
  const els = ((data && data.elementos) || []).filter(e => e.material_tipo === "ACERO");
  miembroState.elementos = els;
  if (!els.length) { cont.innerHTML = `<div style="font-size:11px;color:var(--text-dim);padding:4px">Sin elementos. Importa de ETABS ↑.</div>`; return; }
  cont.innerHTML = els.map(el => {
    const gob = (el.casos || []).find(c => c.gobierna) || (el.casos || [])[0];
    const r = gob && gob.resultado;
    const dc = r ? r.acero_dc : null;
    const cumple = r ? r.acero_cumple : null;
    const col = dc == null ? "var(--text-dim)" : (!cumple ? "#e74c3c" : (dc >= 0.9 ? "#e67e22" : "#27ae60"));
    const act = el.id === miembroState._elemId ? ";border-color:var(--accent);background:var(--surface2)" : "";
    return `<div class="acero-el-row" data-eid="${el.id}" title="Cargar en la Hoja §D-H" style="padding:5px 7px;border:1px solid var(--border);border-radius:4px;margin-bottom:3px;cursor:pointer;background:var(--surface)${act}">
      <div style="display:flex;align-items:center;gap:6px">
        <span style="font-family:monospace;font-size:11px;font-weight:600">${esc(el.perfil_acero || "—")}</span>
        <span style="margin-left:auto;font-size:11px;font-weight:700;color:${col}">${dc == null ? "—" : "DC " + fmt(dc, 2)}</span>
      </div>
      <div style="font-size:9px;color:var(--text-dim)">${esc(el.tipo || "")} · ${esc(el.csi || "")}</div>
    </div>`;
  }).join("");
  cont.querySelectorAll(".acero-el-row").forEach(d =>
    d.addEventListener("click", () => { const el = miembroState.elementos.find(x => x.id === d.dataset.eid); if (el) cargarElementoAcero(el); }));
}

function cargarElementoAcero(el) {
  const s = miembroState, num = (v, d) => { const n = parseFloat(v); return isNaN(n) ? d : n; };
  const gob = (el.casos || []).find(c => c.gobierna) || (el.casos || [])[0];
  s.perfil = el.perfil_acero || s.perfil;
  s.acero = el.acero_grado || "A992";
  s.L_cm = num(el.longitud_m, 0) * 100 || s.L_cm;
  const esCol = el.tipo === "COLUMNA";
  if (gob) {
    if (esCol) { s.pu_t = -Math.abs(num(gob.pu_t, 0)); s.mux_tm = num(gob.mu_xx_tm, 0); s.muy_tm = num(gob.mu_yy_tm, 0); s.vu_t = num(gob.vu_t, 0); }
    else { s.pu_t = num(gob.nu_t, 0); s.mux_tm = num(gob.mu_tm, 0); s.muy_tm = 0; s.vu_t = num(gob.vu_t, 0); }
    s.Lb_cm = num(gob.lu_cm, 0); s.K = num(gob.k_x, 1);
  }
  s._elemId = el.id;
  s._label = (el.perfil_acero || "") + " · " + (el.csi || "");
  s.vista = "calculo";
  const chip = document.getElementById("acero-elem-chip"); if (chip) chip.textContent = "📥 " + s._label;
  document.querySelectorAll("[data-atab]").forEach(x => x.classList.toggle("active", x.dataset.atab === "calculo"));
  loadAceroElementos();   // refresca highlight
  renderAceroVista();
}

function vistaAceroAyudaHTML() {
  const box = (t, body) => `<div style="border:1px solid var(--border);border-radius:5px;padding:10px 13px;margin-bottom:10px;background:var(--surface)"><div style="font-size:12px;font-weight:700;color:var(--accent);margin-bottom:5px">${t}</div><div style="font-size:12px;color:var(--text);line-height:1.6">${body}</div></div>`;
  return `<div style="padding:14px 16px;max-width:760px">
    <div style="font-size:14px;font-weight:700;margin-bottom:10px">📖 Cómo se usa — Acero Estructural</div>
    ${box("¿Qué es?", `Módulo de acero LRFD <b>AISC 360-16 §D-H</b>, métrico. Dropdown <b>Vista</b>: <b>Calculadora de miembro</b> (verificación en vivo de un miembro) e <b>Importar de ETABS</b> (masivo + persistente en la obra).`)}
    ${box("Calculadora de miembro", `Elige perfil + acero, teclea geometría (L, K, L_b, C_b) y demanda (P_u +tracc/−compr, M_ux, M_uy, V_u). La Hoja calcula φR_n por estado (§D tracción, §E compresión, §F flexión/LTB, §G cortante, §H interacción) y el DC gobernante. Verificación independiente = chequeo cruzado del Steel Frame Design de ETABS.`)}
    ${box("Importar de ETABS", `Pega/sube la tabla de fuerzas (Frame/Section/Combo/P/V2/M2/M3), elige unidad y grado → crea elementos + un caso por combo, corre §D-H, marca gobernante por DC. Los elementos quedan listados abajo; «cargar ▸» los abre en la Calculadora.`)}
    ${box("Resultados", `<b>φR_n</b> por estado · <b>DC = demanda/φR_n</b> · estado gobernante · cumple ✓/✗. Semáforo: verde &lt;0.9 · naranja 0.9–1.0 · rojo &gt;1.0. Sin carga → muestra las capacidades del perfil (DC=0).`)}
    ${box("Alcance / pendiente", `Perfil I compacto + <b>HSS cuadrado</b> (§E3 · §F7 · §G4). <b>Pendiente:</b> pandeo local F3/E7 (alas/paredes esbeltas), conexiones (módulo Conexión aparte). Sismo-acero AISC 341 y R_w del sistema = fase siguiente.`)}
  </div>`;
}

async function importarAceroEtabs() {
  const pid = state.activeId;
  if (!pid) { alert("Abre un presupuesto primero."); return; }
  const out     = document.getElementById("acero-result");
  const fileEl  = document.getElementById("acero-file");
  const pasteEl = document.getElementById("acero-paste");
  const generar = !!document.getElementById("acero-generar")?.checked;
  const file    = fileEl && fileEl.files && fileEl.files[0];
  const texto   = pasteEl ? pasteEl.value.trim() : "";
  if (!file && !texto) { alert("Sube un archivo .csv/.xlsx o pega la tabla de ETABS."); return; }
  if (out) out.innerHTML = `<div style="font-size:12px;color:var(--text-dim)">Procesando…</div>`;
  const qs = generar ? "?generar=true" : "";

  let res;
  try {
    if (file) {
      const fd = new FormData();
      fd.append("archivo", file, file.name);
      if (generar) fd.append("generar", "true");
      const r = await fetch(API + `/diseno/${pid}/import-etabs-acero` + qs, { method: "POST", body: fd });
      if (!r.ok) {
        const e = await r.json().catch(() => null);
        throw new Error(e?.detail || ("HTTP " + r.status));
      }
      res = await r.json();
    } else {
      res = await api("POST", `/diseno/${pid}/import-etabs-acero` + qs, { texto, generar });
    }
  } catch (err) {
    if (out) out.innerHTML = `<div style="color:#e74c3c;font-size:12px;padding:8px">Error: ${esc(err.message || String(err))}</div>`;
    return;
  }
  if (out) out.innerHTML = renderAceroResult(res);
}

function dcSemaforo(dc) {
  if (dc == null) return `<span style="color:var(--text-dim)">—</span>`;
  const col = dc > 1.0 ? "#e74c3c" : (dc >= 0.9 ? "#e67e22" : "#27ae60");
  return `<span style="color:${col};font-weight:700">${fmt(dc, 3)}</span>`;
}

function renderAceroResult(res) {
  if (res.status === "sin_datos") {
    const avs = (res.avisos || []).map(a => `<li>${esc(a)}</li>`).join("");
    return `<div style="border:1px solid #e67e22;background:rgba(230,126,34,.10);border-radius:5px;padding:10px 12px">
      <div style="font-size:12px;font-weight:700;color:#e67e22;margin-bottom:5px">Sin datos reconocidos</div>
      <ul style="margin:0;padding-left:18px;font-size:11px;line-height:1.5">${avs}</ul></div>`;
  }
  const porFicha = Array.isArray(res.por_ficha) ? res.por_ficha : [];
  const sobre    = Array.isArray(res.sobre_esforzados) ? res.sobre_esforzados : [];
  const noMap    = Array.isArray(res.perfiles_no_mapeados) ? res.perfiles_no_mapeados : [];
  const parts    = Array.isArray(res.partidas_generadas) ? res.partidas_generadas : [];
  const avs      = Array.isArray(res.avisos) ? res.avisos : [];

  const filasFicha = porFicha.map(f => `<tr>
    <td style="padding:4px 10px;font-family:monospace;font-weight:600">${esc(f.ficha || "—")}</td>
    <td style="padding:4px 10px;font-family:monospace;font-size:11px">${esc(f.perfil || "—")}</td>
    <td style="padding:4px 10px">${esc(f.rol || "—")}</td>
    <td style="padding:4px 10px;text-align:right;font-family:monospace">${fmt(f.longitud_total_mL, 2)}</td>
    <td style="padding:4px 10px;text-align:right">${f.n_miembros ?? "—"}</td>
    <td style="padding:4px 10px;text-align:right">${dcSemaforo(f.dc_max)}</td>
    <td style="padding:4px 10px;font-size:11px;color:var(--text-dim)">${esc(f.combo_gobernante || "—")}</td>
  </tr>`).join("");

  const tablaFicha = porFicha.length ? `
    <div style="border:1px solid var(--border);border-radius:5px;padding:10px 12px;margin-bottom:12px;background:var(--surface)">
      <div style="font-size:11px;font-weight:700;color:var(--accent);margin-bottom:8px">RESUMEN POR FICHA (${porFicha.length})</div>
      <table style="border-collapse:collapse;width:100%;font-size:12px">
        <thead><tr style="color:var(--text-dim);font-size:10px;text-align:left">
          <th style="padding:3px 10px">Ficha</th><th style="padding:3px 10px">Perfil</th>
          <th style="padding:3px 10px">Rol</th><th style="padding:3px 10px;text-align:right">Long. mL</th>
          <th style="padding:3px 10px;text-align:right">N</th>
          <th style="padding:3px 10px;text-align:right">D/C máx</th>
          <th style="padding:3px 10px">Combo gob.</th>
        </tr></thead><tbody>${filasFicha}</tbody>
      </table>
      <div style="font-size:9.5px;color:var(--text-dim);margin-top:6px">Semáforo D/C: <span style="color:#27ae60">●</span> &lt;0.9 · <span style="color:#e67e22">●</span> 0.9–1.0 · <span style="color:#e74c3c">●</span> &gt;1.0</div>
    </div>` : `<div style="font-size:12px;color:var(--text-dim);margin-bottom:12px">No se agregó ninguna ficha.</div>`;

  const filasSobre = sobre.map(s => `<tr>
    <td style="padding:4px 10px;font-family:monospace">${esc(s.frame || "—")}</td>
    <td style="padding:4px 10px;font-family:monospace;font-size:11px">${esc(s.perfil || "—")}</td>
    <td style="padding:4px 10px;text-align:right;font-weight:700;color:#e74c3c">${fmt(s.dc, 3)}</td>
    <td style="padding:4px 10px;font-size:11px;color:var(--text-dim)">${esc(s.combo || "—")}</td>
  </tr>`).join("");
  const tablaSobre = sobre.length ? `
    <div style="border:2px solid #e74c3c;border-radius:5px;padding:10px 12px;margin-bottom:12px;background:rgba(231,76,60,.08)">
      <div style="font-size:11px;font-weight:700;color:#e74c3c;margin-bottom:8px">✗ SOBRE-ESFORZADOS (D/C &gt; 1.0) — ${sobre.length}</div>
      <table style="border-collapse:collapse;width:100%;font-size:12px">
        <thead><tr style="color:var(--text-dim);font-size:10px;text-align:left">
          <th style="padding:3px 10px">Frame</th><th style="padding:3px 10px">Perfil</th>
          <th style="padding:3px 10px;text-align:right">D/C</th><th style="padding:3px 10px">Combo</th>
        </tr></thead><tbody>${filasSobre}</tbody>
      </table>
    </div>` : "";

  const noMapHtml = noMap.length ? `
    <div style="border:1px solid #e67e22;background:rgba(230,126,34,.10);border-radius:5px;padding:9px 12px;margin-bottom:12px">
      <div style="font-size:11px;font-weight:700;color:#e67e22;margin-bottom:5px">⚠ PERFILES NO MAPEADOS (${noMap.length})</div>
      <ul style="margin:0;padding-left:18px;font-size:11px;line-height:1.5;color:var(--text-dim)">
        ${noMap.map(m => `<li>${esc(m.frame || "?")} — perfil <b>${esc(m.perfil || "?")}</b>${m.rol ? " (" + esc(m.rol) + ")" : ""}</li>`).join("")}
      </ul>
    </div>` : "";

  const partsHtml = parts.length ? `
    <div style="border:1px solid #27ae60;border-radius:5px;padding:9px 12px;margin-bottom:12px;background:var(--surface)">
      <div style="font-size:11px;font-weight:700;color:#27ae60;margin-bottom:5px">📦 PARTIDAS GENERADAS Div 05 (${parts.length})</div>
      <ul style="margin:0;padding-left:18px;font-size:11px;line-height:1.5">
        ${parts.map(p => `<li><b>${esc(p.clave || "")}</b> · ${esc(p.ficha || "")} · ${fmt(p.cantidad, 2)} ${esc(p.unidad || "mL")}</li>`).join("")}
      </ul>
      <div style="font-size:9.5px;color:var(--text-dim);margin-top:5px">Precio unitario = 0 hasta inyectar fichas (igual que Div 03).</div>
    </div>` : (res.generado ? `<div style="font-size:11px;color:var(--text-dim);margin-bottom:12px">No se generaron partidas.</div>` : "");

  const avsHtml = avs.length ? `
    <ul style="margin:0 0 12px;padding-left:18px;font-size:10.5px;line-height:1.5;color:#e67e22">
      ${avs.map(a => `<li>${esc(a)}</li>`).join("")}
    </ul>` : "";

  return `
    <div style="border:1px solid #27ae60;border-radius:5px;padding:9px 12px;margin-bottom:12px;background:var(--surface)">
      <div style="font-size:12px;font-weight:700;color:#27ae60">✔ IMPORTADO — ${res.n_miembros ?? 0} miembros leídos${res.formato ? ` <span style="color:var(--text-dim);font-weight:400">· ${esc(res.formato)}</span>` : ""}</div>
    </div>
    ${tablaFicha}
    ${tablaSobre}
    ${noMapHtml}
    ${partsHtml}
    ${avsHtml}`;
}

// ─── MÓDULO CONEXIÓN ACERO — AISC 360-16 §J (LRFD, estilo Mathcad) ────────────
// Aditivo, STATELESS. Dropdowns Tipo/Viga/Columna pedidos a /conexion-acero/catalogo
// (NO se hardcodean perfiles). Hoja recalcula en vivo (debounce 250ms → /memoria-rapida).
// Persistencia + partidas Div 05 + placa base §J8 + fuerzas-nudo ETABS = fase siguiente.

const conexionState = {
  tipo: "VC_CORTANTE",
  perfil_viga: "", perfil_columna: "",
  acero: "A992",
  t_placa_cm: 0.95, perno_grado: "A325", perno_d_cm: 1.9,
  n_pernos: 3, roscas_en_corte: true,
  w_filete_cm: 0.794, L_soldadura_cm: 40,
  vu_t: 15, nu_t: 0, mu_tm: 0,
  // Placa base §J8 (vienen de ETABS pero quedan editables como variables)
  pu_t: 0, fc_kg_cm2: 210, B_placa_cm: 0, N_placa_cm: 0, A2_cm2: 0,
  catalogo: null, ultima: null, ficha: null, timer: null,
  vista: "calc",   // calc | info | lote | placas | guardadas
  // R4 — import masivo de fuerzas-nudo ETABS
  loteUnidad: "kgf", loteTexto: "", loteRes: null, loteBusy: false,
  // Placas base §J8 — pedestales P1..Pn (preseed BD + Joint Reactions ETABS)
  placasUnidad: "kgf", placasTexto: "", placasSpecs: null, placasRes: null,
  // R5 — conexiones guardadas (persistencia)
  guardadas: null,
};

const CONEXION_TIPOS = [
  { v: "VC_CORTANTE", t: "Viga-columna a cortante" },
  { v: "VC_MOMENTO",  t: "Viga-columna a momento" },
  { v: "VV",          t: "Viga-viga a cortante" },
  { v: "SOLDADA",     t: "Conexión soldada (filete)" },
  { v: "PLACA_BASE",  t: "Placa base §J8 (placa-concreto)" },
];

function initConexionView() {
  const btnClose = document.getElementById("btn-cerrar-conexion-view");
  if (btnClose) btnClose.addEventListener("click", () => {
    document.getElementById("conexion-view").style.display = "none";
    const s = document.getElementById("sel-modulo"); if (s) s.value = "";
  });
}

async function conexionCargarCatalogo() {
  if (conexionState.catalogo) return conexionState.catalogo;
  try { conexionState.catalogo = await api("GET", "/conexion-acero/catalogo"); }
  catch { conexionState.catalogo = { vigas: [], columnas: [], conexiones: [] }; }
  // default perfiles si vienen vacíos
  const c = conexionState.catalogo;
  if (!conexionState.perfil_viga && c.vigas && c.vigas.length) conexionState.perfil_viga = c.vigas[0].perfil;
  if (!conexionState.perfil_columna && c.columnas && c.columnas.length) conexionState.perfil_columna = c.columnas[0].perfil;
  return conexionState.catalogo;
}

function conexionBody() {
  const s = conexionState;
  return {
    tipo_conexion: s.tipo, perfil_viga: s.perfil_viga, perfil_columna: s.perfil_columna,
    acero: s.acero, t_placa_cm: s.t_placa_cm, perno_grado: s.perno_grado,
    perno_d_cm: s.perno_d_cm, n_pernos: s.n_pernos, roscas_en_corte: s.roscas_en_corte,
    w_filete_cm: s.w_filete_cm, L_soldadura_cm: s.L_soldadura_cm,
    vu_t: s.vu_t, nu_t: s.nu_t, mu_tm: s.mu_tm,
    pu_t: s.pu_t, fc_kg_cm2: s.fc_kg_cm2,
    B_placa_cm: s.B_placa_cm, N_placa_cm: s.N_placa_cm, A2_cm2: s.A2_cm2,
  };
}

async function renderConexion() {
  const cont = document.getElementById("conexion-content");
  if (!cont) return;
  cont.innerHTML = `<div style="padding:40px;text-align:center;color:var(--text-dim);font-size:13px">Cargando catálogo…</div>`;
  const cat = await conexionCargarCatalogo();
  const s = conexionState;
  const selStyle = "background:var(--surface2);border:1px solid var(--accent);color:var(--text);padding:3px 7px;border-radius:3px;font-weight:600;font-size:12px";
  const inpStyle = "width:90px;background:var(--bg);border:1px solid var(--accent);color:var(--text);padding:3px 6px;border-radius:3px;font-family:monospace;font-weight:600";

  const tipoOpts = CONEXION_TIPOS.map(o =>
    `<option value="${o.v}" ${o.v === s.tipo ? "selected" : ""}>${esc(o.t)}</option>`).join("");
  const vigaOpts = (cat.vigas || []).map(v =>
    `<option value="${escapeAttr(v.perfil)}" ${v.perfil === s.perfil_viga ? "selected" : ""}>${esc(v.ficha)} · ${esc(v.perfil)}</option>`).join("");
  // En VV el 2º dropdown es otra VIGA; en el resto es COLUMNA.
  const esVV = (s.tipo === "VV");
  const segundaLista = esVV ? (cat.vigas || []) : (cat.columnas || []);
  const segundaSel = esVV ? s.perfil_columna : s.perfil_columna;
  const colOpts = segundaLista.map(v =>
    `<option value="${escapeAttr(v.perfil)}" ${v.perfil === segundaSel ? "selected" : ""}>${esc(v.ficha)} · ${esc(v.perfil)}</option>`).join("");

  const vistaBtn = (id, label) =>
    `<button class="cx-vista" data-cxv="${id}" style="background:${s.vista === id ? "var(--accent)" : "transparent"};color:${s.vista === id ? "#fff" : "var(--text)"};border:1px solid var(--accent);padding:5px 14px;border-radius:4px;font-size:12px;font-weight:700;cursor:pointer">${label}</button>`;

  cont.innerHTML = `
   <div style="padding:14px 16px;max-width:1060px">
     <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
       ${vistaBtn("calc", "🧮 Cálculo en vivo")}
       ${vistaBtn("lote", "📥 Importar ETABS (lote)")}
       ${vistaBtn("placas", "🔩 Placas base (pedestales)")}
       ${vistaBtn("guardadas", "📂 Guardadas")}
       ${vistaBtn("info", "📖 Cómo usar")}
     </div>

     <!-- VISTA CÁLCULO -->
     <div id="cx-pane-calc" style="display:${s.vista === "calc" ? "block" : "none"}">
       <div style="font-size:11px;color:var(--text-dim);background:var(--surface2);border:1px solid var(--border);border-radius:4px;padding:8px 11px;margin-bottom:10px;line-height:1.5">
         🔗 <b>Conexión de acero LRFD (AISC 360-16 §J)</b> estilo Mathcad, métrico (kgf, cm, t). Elige tipo, viga y columna; la <b>ficha Div 05</b> se resuelve sola. Edita placa, pernos, soldadura y demanda — todo recalcula al instante en <b>símbolo := fórmula = sustitución = resultado</b>. Cubre §J2 soldadura + metal base, §J3 pernos, §J4 elementos, §J8 placa base. <b>Sin persistencia aún</b> (cálculo).
       </div>

       <!-- Selección de la conexión -->
       <div style="border:1px solid var(--accent);border-radius:5px;padding:10px 12px;margin-bottom:10px;background:var(--surface)">
         <div style="font-size:10px;font-weight:700;color:var(--accent);letter-spacing:.5px;margin-bottom:8px">SELECCIÓN DE LA CONEXIÓN — perfiles del acero disponible</div>
         <div style="display:flex;gap:20px;flex-wrap:wrap;align-items:flex-end">
           <div><div style="font-size:10px;color:var(--text-dim);margin-bottom:2px">Tipo de conexión</div>
             <select id="cx-tipo" style="${selStyle};min-width:230px">${tipoOpts}</select></div>
           <div><div style="font-size:10px;color:var(--text-dim);margin-bottom:2px">VIGA</div>
             <select id="cx-viga" style="${selStyle};min-width:190px">${vigaOpts}</select></div>
           <div><div style="font-size:10px;color:var(--text-dim);margin-bottom:2px">${esVV ? "VIGA (2ª)" : "COLUMNA"}</div>
             <select id="cx-col" style="${selStyle};min-width:190px">${colOpts}</select></div>
           <div><div style="font-size:10px;color:var(--text-dim);margin-bottom:2px">Acero placa/miembro</div>
             <select id="cx-acero" style="${selStyle}">
               <option value="A992" ${s.acero === "A992" ? "selected" : ""}>A992 (W)</option>
               <option value="A36" ${s.acero === "A36" ? "selected" : ""}>A36 (placa)</option>
               <option value="A500" ${s.acero === "A500" ? "selected" : ""}>A500 (HSS)</option>
             </select></div>
         </div>
         <div id="cx-rotulo" style="margin-top:10px;font-size:13px;font-weight:700;padding:7px 11px;border-radius:4px;background:var(--surface2);border:1px solid var(--border)">resolviendo ficha…</div>
       </div>

       <!-- Variables editables -->
       <div style="border:1px solid var(--accent);border-radius:5px;padding:10px 12px;margin-bottom:12px;background:var(--surface)">
         <div style="font-size:10px;font-weight:700;color:var(--accent);letter-spacing:.5px;margin-bottom:7px">VARIABLES EDITABLES — placa · pernos · soldadura · demanda</div>
         <div style="display:flex;gap:30px;flex-wrap:wrap;align-items:flex-start">
           <div style="min-width:200px">
             <div style="font-size:10px;font-weight:700;color:var(--text-dim);margin-bottom:3px">Placa / pernos §J3</div>
             ${cxInRow("t_placa_cm", "t_p", "cm", s.t_placa_cm, "0.05", inpStyle)}
             ${cxInRow("n_pernos", "n", "pernos", s.n_pernos, "1", inpStyle)}
             ${cxInRow("perno_d_cm", "d_b", "cm", s.perno_d_cm, "0.1", inpStyle)}
             <div style="display:flex;align-items:center;gap:6px;padding:2px 0">
               <span style="min-width:30px;text-align:right;font-size:12px">grado</span>
               <select id="cx-perno-grado" style="${selStyle}">
                 <option value="A325" ${s.perno_grado === "A325" ? "selected" : ""}>A325</option>
                 <option value="A490" ${s.perno_grado === "A490" ? "selected" : ""}>A490</option>
                 <option value="A307" ${s.perno_grado === "A307" ? "selected" : ""}>A307</option>
               </select>
             </div>
             <label style="display:flex;align-items:center;gap:5px;font-size:11px;cursor:pointer;padding:3px 0 0 32px">
               <input type="checkbox" id="cx-roscas" ${s.roscas_en_corte ? "checked" : ""}/> roscas en plano de corte (N)
             </label>
           </div>
           <div style="min-width:200px">
             <div style="font-size:10px;font-weight:700;color:var(--text-dim);margin-bottom:3px">Soldadura §J2</div>
             ${cxInRow("w_filete_cm", "w", "cm", s.w_filete_cm, "0.05", inpStyle)}
             ${cxInRow("L_soldadura_cm", "L", "cm", s.L_soldadura_cm, "1", inpStyle)}
           </div>
           <div style="min-width:200px">
             <div style="font-size:10px;font-weight:700;color:var(--text-dim);margin-bottom:3px">Demanda (ETABS, combo LRFD)</div>
             ${cxInRow("vu_t", "V_u", "t", s.vu_t, "0.5", inpStyle)}
             ${cxInRow("nu_t", "N_u", "t", s.nu_t, "0.5", inpStyle)}
             ${cxInRow("mu_tm", "M_u", "t·m", s.mu_tm, "0.5", inpStyle)}
           </div>
           ${s.tipo === "PLACA_BASE" ? `
           <div style="min-width:210px;border-left:2px solid var(--accent);padding-left:14px">
             <div style="font-size:10px;font-weight:700;color:var(--accent);margin-bottom:3px">Placa base §J8 (de ETABS, editable)</div>
             ${cxInRow("pu_t", "P_u", "t", s.pu_t, "1", inpStyle)}
             ${cxInRow("fc_kg_cm2", "f'_c", "kgf/cm²", s.fc_kg_cm2, "10", inpStyle)}
             ${cxInRow("B_placa_cm", "B", "cm", s.B_placa_cm, "1", inpStyle)}
             ${cxInRow("N_placa_cm", "N", "cm", s.N_placa_cm, "1", inpStyle)}
             ${cxInRow("A2_cm2", "A_2", "cm²", s.A2_cm2, "10", inpStyle)}
             <div style="font-size:9px;color:var(--text-dim);padding-left:32px;line-height:1.4">B,N,A₂ = 0 → deriva del perfil columna (b_f+10, d+10, A₂=A₁).</div>
           </div>` : ""}
         </div>
       </div>

       <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;gap:10px">
         <span style="font-size:11px;font-weight:700;color:var(--text-dim);letter-spacing:.5px">DESARROLLO — símbolo := fórmula = sustitución = resultado</span>
         <button id="cx-guardar-btn" title="Guardar esta conexión en el presupuesto (persistente)" style="background:transparent;color:var(--accent);border:1px solid var(--accent);padding:4px 12px;border-radius:4px;font-size:11px;font-weight:700;cursor:pointer;white-space:nowrap">💾 Guardar conexión</button>
       </div>
       <div id="cx-desarrollo" style="font-size:14px">cargando…</div>
       <div style="border:1px solid var(--border);border-radius:5px;padding:8px 11px;margin-top:14px;background:var(--surface)">
         <div style="font-size:10px;font-weight:700;color:var(--text-dim);letter-spacing:.5px;margin-bottom:5px">CONSTANTES (fijas)</div>
         <div id="cx-constantes" style="display:grid;grid-template-columns:repeat(3,1fr);gap:5px 20px;font-size:13px"></div>
       </div>
       <div style="font-size:10px;color:var(--text-dim);text-align:center;margin-top:14px;line-height:1.5">
         Conexiones <b>AISC 360-16 §J</b> (J2 soldadura+metal base · J3 pernos · J4 elementos · <b>J8 placa base</b>). Métrico kgf/cm/t. Persistencia, partidas Div 05 e import de fuerzas-nudo ETABS = <b>fase siguiente</b>.
       </div>
     </div>

     <!-- VISTA IMPORTAR ETABS (LOTE) -->
     <div id="cx-pane-lote" style="display:${s.vista === "lote" ? "block" : "none"}">
       ${vistaLoteHTML(s, cat, selStyle, inpStyle)}
     </div>

     <!-- VISTA PLACAS BASE (pedestales) -->
     <div id="cx-pane-placas" style="display:${s.vista === "placas" ? "block" : "none"}">
       <div id="cx-placas-body"><div style="color:var(--text-dim);font-size:12px;padding:8px">cargando…</div></div>
     </div>

     <!-- VISTA GUARDADAS (persistencia) -->
     <div id="cx-pane-guardadas" style="display:${s.vista === "guardadas" ? "block" : "none"}">
       <div id="cx-guardadas-body"><div style="color:var(--text-dim);font-size:12px;padding:8px">cargando…</div></div>
     </div>

     <!-- VISTA CÓMO USAR -->
     <div id="cx-pane-info" style="display:${s.vista === "info" ? "block" : "none"}">
       ${conexionInfoHTML()}
     </div>
   </div>`;

  bindConexionVistas();
  if (s.vista === "calc") { bindConexionInputs(); recalcConexion(); }
  if (s.vista === "lote") { bindConexionLote(); }
  if (s.vista === "placas") { renderPlacasBase(); }
  if (s.vista === "guardadas") { renderGuardadas(); }
}

// ── R4 — VISTA IMPORTAR ETABS (LOTE): fuerzas-nudo -> envolvente DC §J ────────
function vistaLoteHTML(s, cat, selStyle, inpStyle) {
  const vigaOpts = (cat.vigas || []).map(v =>
    `<option value="${escapeAttr(v.perfil)}">${esc(v.ficha)} · ${esc(v.perfil)}</option>`).join("");
  const colOpts = (cat.columnas || []).map(v =>
    `<option value="${escapeAttr(v.perfil)}">${esc(v.ficha)} · ${esc(v.perfil)}</option>`).join("");
  const uOpt = (v, l) => `<option value="${v}" ${s.loteUnidad === v ? "selected" : ""}>${l}</option>`;
  return `
   <div style="font-size:11px;color:var(--text-dim);background:var(--surface2);border:1px solid var(--border);border-radius:4px;padding:8px 11px;margin-bottom:10px;line-height:1.5">
     📥 <b>Import masivo de fuerzas-nudo ETABS → conexiones §J.</b> Pega la tabla de fuerzas de ETABS
     (<code>Element Forces - Frames</code>: <code>member · P · V2 · M2 · M3 · Combo</code>). Por cada nudo se toma la
     <b>envolvente</b> (mayor D/C entre todas las combinaciones). El tipo se auto-asigna por heurística
     (P domina → placa base · M significativo → momento · resto → cortante) usando los perfiles plantilla.
     <b>Stateless</b> — para costear cada conexión usa "Generar partida Div 05" del Cálculo en vivo.
   </div>
   <div style="border:1px solid var(--accent);border-radius:5px;padding:10px 12px;margin-bottom:10px;background:var(--surface)">
     <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-end;margin-bottom:8px">
       <div><div style="font-size:10px;color:var(--text-dim);margin-bottom:2px">Unidad fuerza ETABS</div>
         <select id="cx-lote-unidad" style="${selStyle}">${uOpt("kgf", "kgf · m")}${uOpt("t", "t · m")}${uOpt("kn", "kN · m")}</select></div>
       <div><div style="font-size:10px;color:var(--text-dim);margin-bottom:2px">Plantilla VIGA</div>
         <select id="cx-lote-viga" style="${selStyle};min-width:175px">${vigaOpts}</select></div>
       <div><div style="font-size:10px;color:var(--text-dim);margin-bottom:2px">Plantilla COLUMNA</div>
         <select id="cx-lote-col" style="${selStyle};min-width:175px">${colOpts}</select></div>
       <button id="cx-lote-calc" style="background:var(--accent);color:#fff;border:none;padding:7px 16px;border-radius:4px;font-size:12px;font-weight:700;cursor:pointer">Calcular lote §J</button>
     </div>
     <textarea id="cx-lote-texto" placeholder="member,P,V2,M2,M3,Combo&#10;B1,-2000,8000,0,3500,1.2D+1.6L&#10;B1,-1500,6000,0,5000,1.2D+1.0E&#10;C1,-80000,3000,0,0,1.2D+1.6L" style="width:100%;min-height:130px;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:4px;font-family:monospace;font-size:11px;padding:7px;box-sizing:border-box">${esc(s.loteTexto || "")}</textarea>
     <div style="font-size:9px;color:var(--text-dim);margin-top:4px">Separa columnas con <b>comas</b> o <b>tabuladores</b> (pega directo de Excel/ETABS). Una fila por combinación; el encabezado debe incluir <code>Combo</code> u <code>OutputCase</code>.</div>
   </div>
   <div id="cx-lote-result">${s.loteRes ? loteResultHTML(s.loteRes) : ""}</div>

   <div style="border:1px solid var(--accent);border-radius:5px;padding:10px 12px;margin-top:16px;background:var(--surface)">
     <div style="font-size:11px;color:var(--text-dim);margin-bottom:8px;line-height:1.5">
       🔩 <b>Importar conexiones desde pyRevit (CSV).</b> Sube <code>C10_connections_latest.csv</code>
       (botón <i>Export Steel Connections</i> de Revit). Genera fichas Div 05 con <b>insumos × cantidad</b>.
       Decide aquí si las viga-columna (VC) son <b>apernadas</b> o <b>soldadas</b>. Las VV van apernadas; la placa base ya está en el pedestal.
     </div>
     <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-bottom:8px">
       <input type="file" id="cx-pyr-file" accept=".csv,text/csv" style="font-size:11px">
       <label style="font-size:11px;cursor:pointer"><input type="radio" name="cx-pyr-modo" value="apernada" checked> VC apernada (CV)</label>
       <label style="font-size:11px;cursor:pointer"><input type="radio" name="cx-pyr-modo" value="soldada"> VC soldada (CX)</label>
       <button id="cx-pyr-import" style="background:var(--accent);color:#fff;border:none;padding:7px 16px;border-radius:4px;font-size:12px;font-weight:700;cursor:pointer">Importar CSV</button>
     </div>
     <div id="cx-pyr-result" style="font-size:12px"></div>
   </div>`;
}

function loteResultHTML(res) {
  if (!res || res.status === "sin_datos")
    return `<div style="color:#e67e22;font-size:12px">${esc(((res && res.avisos) || ["Sin datos."]).join(" "))}</div>`;
  const rows = res.conexiones || [];
  if (!rows.length)
    return `<div style="color:var(--text-dim);font-size:12px">Sin conexiones calculadas. ${esc((res.avisos || []).join(" "))}</div>`;
  const dcBadge = (dc, cumple) => {
    if (dc == null) return `<span style="color:var(--text-dim)">—</span>`;
    const col = cumple ? "#27ae60" : "#e74c3c";
    return `<span style="font-weight:700;color:${col}">${fmt(dc, 3)}</span>`;
  };
  const tr = rows.map(c => `<tr style="border-top:1px solid var(--border);background:${(c.dc != null && c.dc > 1) ? "rgba(231,76,60,.08)" : "transparent"}">
     <td style="padding:3px 6px;font-weight:600">${esc(c.member)}</td>
     <td style="padding:3px 6px;font-size:11px">${esc(c.tipo_conexion)}</td>
     <td style="padding:3px 6px;font-size:11px">${esc(c.ficha || "—")}${c.aproximado ? ' <span style="color:#e67e22" title="ficha aproximada">≈</span>' : ""}</td>
     <td style="padding:3px 6px;font-size:11px">${esc(c.estado_gob || "—")}</td>
     <td style="padding:3px 6px;text-align:right;font-size:11px">${c.demanda_t != null ? fmt(c.demanda_t, 2) : "—"}</td>
     <td style="padding:3px 6px;text-align:right;font-size:11px">${c.phi_rn != null ? fmt(c.phi_rn, 2) : "—"}</td>
     <td style="padding:3px 6px;text-align:center">${dcBadge(c.dc, c.cumple)}</td>
     <td style="padding:3px 6px;text-align:center">${c.cumple ? "✅" : (c.dc == null ? "—" : "❌")}</td>
     <td style="padding:3px 6px;font-size:10px;color:var(--text-dim)">${esc(c.combo || "")}</td>
   </tr>`).join("");
  return `
   <div style="font-size:12px;margin-bottom:6px">
     <b>${res.n_conexiones}</b> conexiones · <b style="color:${res.n_sobre_esforzadas ? "#e74c3c" : "#27ae60"}">${res.n_sobre_esforzadas}</b> sobre-esforzadas (D/C&gt;1)
     ${(res.sin_fuerzas && res.sin_fuerzas.length) ? ` · <span style="color:#e67e22">${res.sin_fuerzas.length} sin fuerzas</span>` : ""}
   </div>
   <table style="width:100%;border-collapse:collapse;font-size:12px;background:var(--surface);border:1px solid var(--border);border-radius:5px;overflow:hidden">
     <thead><tr style="background:var(--surface2);font-size:10px;color:var(--text-dim);text-align:left">
       <th style="padding:4px 6px">Nudo</th><th style="padding:4px 6px">Tipo</th><th style="padding:4px 6px">Ficha</th>
       <th style="padding:4px 6px">Estado gob.</th><th style="padding:4px 6px;text-align:right">Dem (t)</th>
       <th style="padding:4px 6px;text-align:right">φRn (t)</th><th style="padding:4px 6px;text-align:center">D/C</th>
       <th style="padding:4px 6px;text-align:center">✓</th><th style="padding:4px 6px">Combo gob.</th>
     </tr></thead><tbody>${tr}</tbody>
   </table>
   ${(res.avisos && res.avisos.length) ? `<div style="font-size:10px;color:var(--text-dim);margin-top:6px">⚠ ${esc(res.avisos.join(" "))}</div>` : ""}`;
}

function bindConexionLote() {
  const s = conexionState;
  const ta = document.getElementById("cx-lote-texto");
  if (ta) ta.addEventListener("input", () => { s.loteTexto = ta.value; });
  const u = document.getElementById("cx-lote-unidad");
  if (u) u.addEventListener("change", () => { s.loteUnidad = u.value; });
  const btn = document.getElementById("cx-lote-calc");
  if (btn) btn.addEventListener("click", conexionLoteCalcular);
  const pyr = document.getElementById("cx-pyr-import");
  if (pyr) pyr.addEventListener("click", conexionImportPyrevit);
}

// ── Import CSV pyRevit (conteo de conexiones) -> fichas Div 05 con insumos ────
async function conexionImportPyrevit() {
  const pid = state.activeId;
  const out = document.getElementById("cx-pyr-result");
  if (!pid) { if (out) out.innerHTML = `<span style="color:#e67e22">Selecciona un presupuesto.</span>`; return; }
  const fileEl = document.getElementById("cx-pyr-file");
  const file = fileEl && fileEl.files && fileEl.files[0];
  if (!file) { out.innerHTML = `<span style="color:#e67e22">Selecciona el CSV de pyRevit.</span>`; return; }
  const modo = (document.querySelector('input[name="cx-pyr-modo"]:checked') || {}).value || "apernada";
  out.innerHTML = `<span style="color:var(--text-dim)">Importando…</span>`;
  let text;
  try { text = await file.text(); }
  catch (e) { out.innerHTML = `<span style="color:#e74c3c">No se pudo leer el archivo.</span>`; return; }
  let res;
  try { res = await api("POST", `/diseno/${pid}/conexion-import-pyrevit-csv`, { csv_text: text, vc_modo: modo }); }
  catch (e) { out.innerHTML = `<span style="color:#e74c3c">Error: ${esc(e.message || String(e))}</span>`; return; }
  if (!res || res.status === "vacio") {
    out.innerHTML = `<span style="color:#e67e22">${esc(((res && res.avisos) || ["CSV vacío o inválido."]).join(" "))}</span>`;
    return;
  }
  const ok = (res.detalle || []).filter(d => d.status === "ok");
  const tr = ok.map(d => `<tr style="border-top:1px solid var(--border)">
     <td style="padding:3px 6px;font-weight:600">${esc(d.entrada.tipo)}</td>
     <td style="padding:3px 6px">${esc(d.ficha || "—")}${d.aproximado ? ' <span style="color:#e67e22" title="aproximada">≈</span>' : ""}</td>
     <td style="padding:3px 6px;font-size:11px;color:var(--text-dim)">${esc(d.csi || "")}</td>
     <td style="padding:3px 6px;font-size:11px">${esc(d.entrada.perfil_viga)}×${esc(d.entrada.perfil_columna)}</td>
     <td style="padding:3px 6px;text-align:center">${fmt(d.cantidad, 0)}</td>
     <td style="padding:3px 6px;text-align:right">${d.n_insumos}</td>
     <td style="padding:3px 6px;text-align:right">L ${fmt(d.total, 2)}</td>
   </tr>`).join("");
  const sf = res.sin_ficha || [];
  out.innerHTML = `
    <div style="margin-bottom:6px"><b style="color:#27ae60">${res.partidas_generadas}</b> partidas Div 05 generadas ·
      ${res.grupos} grupos · ${res.filas_csv} filas · VC: <b>${esc(res.modo_vc)}</b> ·
      total <b>L ${fmt(res.total, 2)}</b>${res.descartados ? ` · <span style="color:#e67e22">${res.descartados} descartadas</span>` : ""}</div>
    <table style="width:100%;border-collapse:collapse;font-size:12px;background:var(--surface);border:1px solid var(--border);border-radius:5px;overflow:hidden">
      <thead><tr style="background:var(--surface2);font-size:10px;color:var(--text-dim);text-align:left">
        <th style="padding:4px 6px">Tipo</th><th style="padding:4px 6px">Ficha</th><th style="padding:4px 6px">CSI</th>
        <th style="padding:4px 6px">Perfiles</th><th style="padding:4px 6px;text-align:center">Cant</th>
        <th style="padding:4px 6px;text-align:right">Insumos</th><th style="padding:4px 6px;text-align:right">Total</th>
      </tr></thead><tbody>${tr}</tbody>
    </table>
    ${sf.length ? `<div style="font-size:10px;color:#e67e22;margin-top:6px">⚠ ${sf.length} sin ficha en base curada: ${sf.map(x => esc(x.tipo + " " + x.perfil_viga + "×" + x.perfil_columna)).join(", ")}</div>` : ""}
    <div style="font-size:10px;color:var(--text-dim);margin-top:6px">Las partidas quedan en el capítulo 05 del presupuesto.</div>`;
}

function tipoHeuristicoLote(n) {
  if ((n.p_max_t || 0) >= 20 && (n.mu_max_tm || 0) < 0.5) return "PLACA_BASE";
  if ((n.mu_max_tm || 0) >= 1.0) return "VC_MOMENTO";
  return "VC_CORTANTE";
}

async function conexionLoteCalcular() {
  const s = conexionState;
  const out = document.getElementById("cx-lote-result");
  const texto = (document.getElementById("cx-lote-texto")?.value || "").trim();
  s.loteTexto = texto;
  s.loteUnidad = document.getElementById("cx-lote-unidad")?.value || "kgf";
  const pViga = document.getElementById("cx-lote-viga")?.value || "";
  const pCol = document.getElementById("cx-lote-col")?.value || "";
  if (!texto) { if (out) out.innerHTML = `<div style="color:#e67e22;font-size:12px">Pega la tabla de fuerzas de ETABS primero.</div>`; return; }
  if (out) out.innerHTML = `<div style="color:var(--text-dim);font-size:12px">Leyendo nudos…</div>`;
  // 1) envolvente de fuerzas por nudo (descubre miembros)
  let nodos;
  try { nodos = await api("POST", "/conexion-acero/import-etabs-fuerzas", { unidad: s.loteUnidad, texto }); }
  catch (err) { if (out) out.innerHTML = `<div style="color:#e74c3c;font-size:12px">Error: ${esc(err.message)}</div>`; return; }
  if (nodos.status === "sin_datos") { s.loteRes = nodos; if (out) out.innerHTML = loteResultHTML(nodos); return; }
  // 2) specs por nudo (tipo por heurística + perfiles plantilla) -> envolvente DC
  const specs = (nodos.demanda_por_nudo || []).map(n => {
    const tipo = tipoHeuristicoLote(n);
    return { member: n.member, tipo_conexion: tipo,
             perfil_viga: tipo === "PLACA_BASE" ? "" : pViga, perfil_columna: pCol };
  });
  if (out) out.innerHTML = `<div style="color:var(--text-dim);font-size:12px">Calculando §J de ${specs.length} nudos…</div>`;
  let res;
  try { res = await api("POST", "/conexion-acero/import-etabs-fuerzas", { unidad: s.loteUnidad, texto, conexiones: specs }); }
  catch (err) { if (out) out.innerHTML = `<div style="color:#e74c3c;font-size:12px">Error: ${esc(err.message)}</div>`; return; }
  s.loteRes = res;
  if (out) out.innerHTML = loteResultHTML(res);
}

// ── PLACAS BASE §J8 — pedestales P1..Pn (preseed BD + Joint Reactions ETABS) ──
async function renderPlacasBase() {
  const body = document.getElementById("cx-placas-body");
  if (!body) return;
  const s = conexionState;
  const pid = state.activeId;
  if (!pid) {
    body.innerHTML = `<div style="color:#e67e22;font-size:12px;padding:8px">Abre un presupuesto para cargar sus pedestales (P1…Pn).</div>`;
    return;
  }
  if (!s.placasSpecs) {
    body.innerHTML = `<div style="color:var(--text-dim);font-size:12px;padding:8px">Cargando pedestales de la obra…</div>`;
    try {
      const pre = await api("GET", `/diseno/${pid}/pedestales-base`);
      s.placasSpecs = (pre.pedestales || []).map(p => ({
        pedestal: p.pedestal, joint: p.pedestal, perfil_columna: p.perfil_columna || "",
        fc_kg_cm2: p.fc_kg_cm2 || 210, lado_cm: p.lado_cm || 0, A2_cm2: p.A2_cm2 || 0,
        t_placa_cm: p.t_placa_cm || 1.9, columnas: p.columnas || "",
      }));
    } catch (err) { body.innerHTML = `<div style="color:#e74c3c;font-size:12px;padding:8px">Error: ${esc(err.message)}</div>`; return; }
  }
  body.innerHTML = placasViewHTML(s);
  bindPlacasInputs();
}

function placasViewHTML(s) {
  const uOpt = (v, l) => `<option value="${v}" ${s.placasUnidad === v ? "selected" : ""}>${l}</option>`;
  return `
   <div style="font-size:11px;color:var(--text-dim);background:var(--surface2);border:1px solid var(--border);border-radius:4px;padding:8px 11px;margin-bottom:10px;line-height:1.5">
     🔩 <b>Placas base §J8 — pedestales de la obra.</b> Los pedestales (P1…Pn) se cargan solos desde el presupuesto (tamaño→A₂, perfil de columna si está en la ficha). Pega las <b>Joint Reactions</b> de ETABS
     (<code>Joint · OutputCase · FX · FY · FZ</code>) → por cada pedestal: <b>Pu = |FZ|</b>, Vu = √(FX²+FY²), A₂ = lado². Edita el <b>joint</b> de ETABS y el <b>perfil</b> faltante por fila. Stateless (verificación).
   </div>
   <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end;margin-bottom:8px">
     <div><div style="font-size:10px;color:var(--text-dim);margin-bottom:2px">Unidad fuerza ETABS</div>
       <select id="cx-placas-unidad" style="background:var(--surface2);border:1px solid var(--accent);color:var(--text);padding:3px 7px;border-radius:3px;font-weight:600;font-size:12px">${uOpt("kgf", "kgf · m")}${uOpt("t", "t · m")}${uOpt("kn", "kN · m")}</select></div>
     <button id="cx-placas-calc" style="background:var(--accent);color:#fff;border:none;padding:7px 16px;border-radius:4px;font-size:12px;font-weight:700;cursor:pointer">Calcular placas base §J8</button>
     ${s.placasRes ? placasSummaryHTML(s.placasRes) : `<span style="font-size:10px;color:var(--text-dim)">pega reacciones y calcula →</span>`}
   </div>
   <textarea id="cx-placas-texto" placeholder="Joint,OutputCase,FX,FY,FZ,MX,MY,MZ&#10;P1,1.2D+1.6L,1500,800,42000,0,0,0&#10;P6,1.2D+1.6L,500,300,18000,0,0,0" style="width:100%;min-height:90px;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:4px;font-family:monospace;font-size:11px;padding:7px;box-sizing:border-box;margin-bottom:10px">${esc(s.placasTexto || "")}</textarea>
   ${placasTablaHTML(s)}`;
}

function placasSummaryHTML(res) {
  if (res.status === "sin_datos")
    return `<span style="font-size:11px;color:#e67e22">${esc((res.avisos || []).join(" "))}</span>`;
  if (res.status === "solo_reacciones")
    return `<span style="font-size:11px;color:var(--text-dim)">${res.n_nudos} nudos leídos — mapea joints a pedestales</span>`;
  return `<span style="font-size:11px"><b>${res.n_placas}</b> placas · <b style="color:${res.n_sobre_esforzadas ? "#e74c3c" : "#27ae60"}">${res.n_sobre_esforzadas}</b> sobre-esforzadas</span>`;
}

function placasTablaHTML(s) {
  const resByPed = {};
  (s.placasRes && s.placasRes.placas || []).forEach(p => { resByPed[p.pedestal] = p; });
  const inp = (i, f, val, ph, num) =>
    `<input data-pb-i="${i}" data-pb-f="${f}" ${num ? 'type="number" step="any"' : 'type="text"'} value="${escapeAttr(String(val == null ? "" : val))}" ${ph ? `placeholder="${ph}"` : ""} style="width:${num ? "62" : "82"}px;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:2px 4px;border-radius:3px;font-family:monospace;font-size:11px"/>`;
  const rows = (s.placasSpecs || []).map((sp, i) => {
    const r = resByPed[sp.pedestal] || {};
    const dc = r.dc;
    const dcCol = dc == null ? "var(--text-dim)" : (r.cumple ? "#27ae60" : "#e74c3c");
    const ok = r.error ? `<span title="${esc(r.error)}" style="color:#e67e22">⚠</span>`
      : (r.cumple ? "✅" : (dc == null ? "—" : "❌"));
    return `<tr style="border-top:1px solid var(--border);background:${(dc != null && dc > 1) ? "rgba(231,76,60,.08)" : "transparent"}">
       <td style="padding:3px 6px;font-weight:700">${esc(sp.pedestal)}<div style="font-size:9px;color:var(--text-dim);font-weight:400">${esc(sp.columnas || "")}</div></td>
       <td style="padding:3px 5px">${inp(i, "joint", sp.joint, "joint", false)}</td>
       <td style="padding:3px 5px">${inp(i, "perfil_columna", sp.perfil_columna, "W…", false)}</td>
       <td style="padding:3px 5px">${inp(i, "fc_kg_cm2", sp.fc_kg_cm2, "", true)}</td>
       <td style="padding:3px 5px">${inp(i, "lado_cm", sp.lado_cm, "", true)}<div style="font-size:9px;color:var(--text-dim)">A₂=${fmt((sp.lado_cm || 0) * (sp.lado_cm || 0), 0)}</div></td>
       <td style="padding:3px 5px">${inp(i, "t_placa_cm", sp.t_placa_cm, "", true)}</td>
       <td style="padding:3px 6px;text-align:right;font-size:11px">${r.pu_t != null ? fmt(r.pu_t, 1) : "—"}</td>
       <td style="padding:3px 6px;text-align:right;font-size:11px">${r.phiPp_t != null ? fmt(r.phiPp_t, 1) : "—"}</td>
       <td style="padding:3px 6px;text-align:right;font-size:11px">${(r.B != null && r.N != null) ? `${fmt(r.B, 0)}×${fmt(r.N, 0)}` : "—"}</td>
       <td style="padding:3px 6px;text-align:right;font-size:11px">${r.tp_req != null ? fmt(r.tp_req, 2) : "—"}/${r.tp != null ? fmt(r.tp, 2) : "—"}</td>
       <td style="padding:3px 6px;text-align:center"><b style="color:${dcCol}">${dc != null ? fmt(dc, 3) : "—"}</b></td>
       <td style="padding:3px 6px;text-align:center">${ok}</td>
     </tr>`;
  }).join("");
  return `
   <table style="width:100%;border-collapse:collapse;font-size:12px;background:var(--surface);border:1px solid var(--border);border-radius:5px;overflow:hidden">
     <thead><tr style="background:var(--surface2);font-size:10px;color:var(--text-dim);text-align:left">
       <th style="padding:4px 6px">Pedestal</th><th style="padding:4px 5px">Joint ETABS</th><th style="padding:4px 5px">Perfil col.</th>
       <th style="padding:4px 5px">f'c</th><th style="padding:4px 5px">Lado (A₂)</th><th style="padding:4px 5px">t placa</th>
       <th style="padding:4px 6px;text-align:right">Pu (t)</th><th style="padding:4px 6px;text-align:right">φPp (t)</th>
       <th style="padding:4px 6px;text-align:right">B×N</th><th style="padding:4px 6px;text-align:right">tp req/prov</th>
       <th style="padding:4px 6px;text-align:center">D/C</th><th style="padding:4px 6px;text-align:center">✓</th>
     </tr></thead><tbody>${rows}</tbody>
   </table>
   ${(s.placasRes && s.placasRes.avisos && s.placasRes.avisos.length) ? `<div style="font-size:10px;color:var(--text-dim);margin-top:6px">⚠ ${esc(s.placasRes.avisos.join(" "))}</div>` : ""}
   <div style="font-size:10px;color:var(--text-dim);margin-top:8px;line-height:1.5">§J8: φPp = aplastamiento del concreto (0.65·0.85·f'c·A₁·√(A₂/A₁) ≤ 0.65·1.7·f'c·A₁) · tp = espesor por voladizo (DG-1). A₂ = área del pedestal; B×N = placa (deriva del perfil si no se fija). Pu de la reacción ETABS (FZ).</div>`;
}

function bindPlacasInputs() {
  const s = conexionState;
  document.querySelectorAll("#cx-placas-body input[data-pb-i]").forEach(inp => {
    inp.addEventListener("input", () => {
      const i = +inp.dataset.pbI, f = inp.dataset.pbF;
      const num = (f === "fc_kg_cm2" || f === "lado_cm" || f === "t_placa_cm");
      s.placasSpecs[i][f] = num ? (parseFloat(inp.value) || 0) : inp.value;
      if (f === "lado_cm") s.placasSpecs[i].A2_cm2 = (parseFloat(inp.value) || 0) ** 2;
    });
  });
  const ta = document.getElementById("cx-placas-texto");
  if (ta) ta.addEventListener("input", () => { s.placasTexto = ta.value; });
  const u = document.getElementById("cx-placas-unidad");
  if (u) u.addEventListener("change", () => { s.placasUnidad = u.value; });
  const btn = document.getElementById("cx-placas-calc");
  if (btn) btn.addEventListener("click", conexionPlacasCalcular);
}

async function conexionPlacasCalcular() {
  const s = conexionState;
  const pid = state.activeId;
  if (!pid) { alert("Abre un presupuesto primero."); return; }
  s.placasTexto = document.getElementById("cx-placas-texto")?.value || "";
  s.placasUnidad = document.getElementById("cx-placas-unidad")?.value || "kgf";
  if (!s.placasTexto.trim()) { alert("Pega las Joint Reactions de ETABS primero."); return; }
  const specs = (s.placasSpecs || []).map(sp => ({
    pedestal: sp.pedestal, joint: sp.joint, perfil_columna: sp.perfil_columna,
    acero: "A992", fc_kg_cm2: sp.fc_kg_cm2, lado_cm: sp.lado_cm,
    A2_cm2: (sp.lado_cm || 0) * (sp.lado_cm || 0), t_placa_cm: sp.t_placa_cm,
  }));
  let res;
  try { res = await api("POST", `/diseno/${pid}/placas-base-etabs`, { unidad: s.placasUnidad, texto: s.placasTexto, pedestales: specs }); }
  catch (err) { alert("Error: " + err.message); return; }
  s.placasRes = res;
  renderPlacasBase();
}

// ── R5 — CONEXIONES GUARDADAS (persistencia) ─────────────────────────────────
async function conexionGuardar() {
  const s = conexionState;
  const pid = state.activeId;
  if (!pid) { alert("Abre un presupuesto para guardar la conexión."); return; }
  const tm = prompt("Etiqueta de la conexión (type_mark):", s.tipo || "CX-1");
  if (tm === null) return;
  const body = {
    csi: "", type_mark: tm || "", tipo_conexion: s.tipo,
    perfil_viga: s.perfil_viga, perfil_columna: s.perfil_columna, acero: s.acero,
    t_placa_cm: s.t_placa_cm, perno_grado: s.perno_grado, perno_d_cm: s.perno_d_cm,
    n_pernos: s.n_pernos, roscas_en_corte: s.roscas_en_corte,
    w_filete_cm: s.w_filete_cm, L_soldadura_cm: s.L_soldadura_cm,
    fc_kg_cm2: s.fc_kg_cm2, B_placa_cm: s.B_placa_cm, N_placa_cm: s.N_placa_cm, A2_cm2: s.A2_cm2,
    casos: [{ nombre: "D+L", origen: "MANUAL", combo_etabs: "",
              vu_t: s.vu_t, nu_t: s.nu_t, mu_tm: s.mu_tm, pu_t: s.pu_t }],
  };
  let res;
  try { res = await api("POST", `/conexion-acero/${pid}/conexiones`, body); }
  catch (err) { alert("Error: " + err.message); return; }
  s.guardadas = null;
  const g = res.gobernante;
  alert(`Guardada: ${res.type_mark || "(sin etiqueta)"} · DC=${g ? fmt(g.dc, 3) : "—"} · ${g && g.cumple ? "cumple ✅" : "REVISAR ❌"}`);
}

async function renderGuardadas() {
  const body = document.getElementById("cx-guardadas-body");
  if (!body) return;
  const pid = state.activeId;
  if (!pid) { body.innerHTML = `<div style="color:#e67e22;font-size:12px;padding:8px">Abre un presupuesto para ver sus conexiones guardadas.</div>`; return; }
  body.innerHTML = `<div style="color:var(--text-dim);font-size:12px;padding:8px">Cargando…</div>`;
  let res;
  try { res = await api("GET", `/conexion-acero/${pid}/conexiones`); }
  catch (err) { body.innerHTML = `<div style="color:#e74c3c;font-size:12px;padding:8px">Error: ${esc(err.message)}</div>`; return; }
  conexionState.guardadas = res;
  body.innerHTML = guardadasTablaHTML(res);
  bindGuardadas();
}

function guardadasTablaHTML(res) {
  const rows = res.conexiones || [];
  if (!rows.length)
    return `<div style="color:var(--text-dim);font-size:12px;padding:8px;line-height:1.5">No hay conexiones guardadas. Usa <b>💾 Guardar conexión</b> en el Cálculo en vivo para persistir una.</div>`;
  const dcBadge = g => {
    if (!g || g.dc == null) return `<span style="color:var(--text-dim)">—</span>`;
    return `<b style="color:${g.cumple ? "#27ae60" : "#e74c3c"}">${fmt(g.dc, 3)}</b>`;
  };
  const tr = rows.map(c => {
    const g = c.gobernante;
    return `<tr style="border-top:1px solid var(--border);background:${(g && g.dc != null && g.dc > 1) ? "rgba(231,76,60,.08)" : "transparent"}">
       <td style="padding:3px 6px;font-weight:600">${esc(c.type_mark || c.csi || "—")}</td>
       <td style="padding:3px 6px;font-size:11px">${esc(c.tipo_conexion)}</td>
       <td style="padding:3px 6px;font-size:11px">${esc(c.perfil_viga || "")}${c.perfil_columna ? ` / ${esc(c.perfil_columna)}` : ""}</td>
       <td style="padding:3px 6px;font-size:11px">${esc(g ? (g.estado_gob || "—") : "—")}</td>
       <td style="padding:3px 6px;text-align:right;font-size:11px">${g && g.demanda_t != null ? fmt(g.demanda_t, 2) : "—"}</td>
       <td style="padding:3px 6px;text-align:center">${dcBadge(g)}</td>
       <td style="padding:3px 6px;text-align:center">${g ? (g.cumple ? "✅" : "❌") : "—"}</td>
       <td style="padding:3px 6px;text-align:center;font-size:10px;color:var(--text-dim)">${c.n_casos}</td>
       <td style="padding:3px 6px;text-align:center"><button data-del-cx="${c.id}" title="Borrar" style="background:transparent;border:1px solid #e74c3c;color:#e74c3c;border-radius:3px;font-size:10px;padding:2px 7px;cursor:pointer">🗑</button></td>
     </tr>`;
  }).join("");
  return `
   <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
     <span style="font-size:12px"><b>${res.n}</b> conexiones guardadas en el presupuesto</span>
     <button id="cx-guardadas-refresh" style="background:transparent;color:var(--accent);border:1px solid var(--accent);padding:3px 10px;border-radius:4px;font-size:11px;font-weight:700;cursor:pointer">↻ Refrescar</button>
   </div>
   <table style="width:100%;border-collapse:collapse;font-size:12px;background:var(--surface);border:1px solid var(--border);border-radius:5px;overflow:hidden">
     <thead><tr style="background:var(--surface2);font-size:10px;color:var(--text-dim);text-align:left">
       <th style="padding:4px 6px">Etiqueta</th><th style="padding:4px 6px">Tipo</th><th style="padding:4px 6px">Perfiles</th>
       <th style="padding:4px 6px">Estado gob.</th><th style="padding:4px 6px;text-align:right">Dem (t)</th>
       <th style="padding:4px 6px;text-align:center">D/C</th><th style="padding:4px 6px;text-align:center">✓</th>
       <th style="padding:4px 6px;text-align:center">casos</th><th style="padding:4px 6px;text-align:center"></th>
     </tr></thead><tbody>${tr}</tbody>
   </table>`;
}

function bindGuardadas() {
  document.querySelectorAll("#cx-guardadas-body button[data-del-cx]").forEach(b => {
    b.addEventListener("click", () => conexionEliminarGuardada(b.dataset.delCx));
  });
  const rf = document.getElementById("cx-guardadas-refresh");
  if (rf) rf.addEventListener("click", () => { conexionState.guardadas = null; renderGuardadas(); });
}

async function conexionEliminarGuardada(cid) {
  if (!confirm("¿Borrar esta conexión guardada? (no se puede deshacer)")) return;
  try { await api("DELETE", `/conexion-acero/conexiones/${cid}`); }
  catch (err) { alert("Error: " + err.message); return; }
  conexionState.guardadas = null;
  renderGuardadas();
}

function cxInRow(key, sym, unit, val, step, inpStyle) {
  return `<div style="display:flex;align-items:center;gap:6px;padding:2px 0">
      <span style="min-width:30px;text-align:right">${kx(sym, sym)}</span>
      <span style="color:var(--accent);font-weight:700">:=</span>
      <input data-cx="${key}" type="number" step="${step || "any"}" value="${val}" style="${inpStyle}"/>
      <span style="font-size:10px;color:var(--text-dim)">${esc(unit)}</span>
    </div>`;
}

function bindConexionVistas() {
  document.querySelectorAll("#conexion-content .cx-vista").forEach(b => {
    b.addEventListener("click", () => { conexionState.vista = b.dataset.cxv; renderConexion(); });
  });
}

function bindConexionInputs() {
  const s = conexionState;
  const onSel = (id, key, rerender) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", () => {
      s[key] = el.value;
      if (rerender) renderConexion(); else recalcConexion();
    });
  };
  // Tipo cambia qué es el 2º dropdown (VV → viga) → re-render
  onSel("cx-tipo", "tipo", true);
  onSel("cx-viga", "perfil_viga", false);
  onSel("cx-col", "perfil_columna", false);
  onSel("cx-acero", "acero", false);
  onSel("cx-perno-grado", "perno_grado", false);
  const rosca = document.getElementById("cx-roscas");
  if (rosca) rosca.addEventListener("change", () => { s.roscas_en_corte = rosca.checked; recalcConexion(); });
  document.querySelectorAll("#conexion-content input[data-cx]").forEach(inp => {
    inp.addEventListener("input", () => {
      const k = inp.dataset.cx;
      const v = (k === "n_pernos") ? parseInt(inp.value, 10) : parseFloat(inp.value);
      s[k] = isNaN(v) ? 0 : v;
      clearTimeout(s.timer);
      s.timer = setTimeout(recalcConexion, 250);
    });
  });
  const gbtn = document.getElementById("cx-guardar-btn");
  if (gbtn) gbtn.addEventListener("click", conexionGuardar);
}

async function recalcConexion() {
  const dev = document.getElementById("cx-desarrollo");
  const con = document.getElementById("cx-constantes");
  const rot = document.getElementById("cx-rotulo");
  const badge = document.getElementById("conexion-status-badge");
  if (!dev) return;
  let m;
  try { m = await api("POST", "/conexion-acero/memoria-rapida", conexionBody()); }
  catch (err) { dev.innerHTML = `<div style="color:#e74c3c;font-size:12px">Error: ${esc(err.message)}</div>`; return; }
  conexionState.ultima = m;
  const meta = m.meta || {};

  // Rótulo de la ficha resuelta (arriba de la hoja)
  if (rot) {
    const aprox = meta.aproximado;
    const col = aprox ? "#e67e22" : "#27ae60";
    rot.style.borderColor = col; rot.style.color = col;
    rot.innerHTML = `🏷️ ${esc(meta.rotulo || "—")}${meta.descripcion ? ` <span style="font-weight:400;color:var(--text-dim);font-size:11px">— ${esc(meta.descripcion)}</span>` : ""}`;
  }
  if (badge) badge.textContent = meta.resumen || "";

  if (con && Array.isArray(m.constantes))
    con.innerHTML = m.constantes.map(c => `<div title="${esc(c.desc || "")}">${kx(c.latex, c.simbolo)}</div>`).join("");

  // Desarrollo agrupado por sección (orden de aparición)
  const orden = [], grupos = {};
  (m.pasos || []).forEach(p => { if (!grupos[p.seccion]) { grupos[p.seccion] = []; orden.push(p.seccion); } grupos[p.seccion].push(p); });
  const CX_SEC = {
    "Materiales":    ["AISC Tabla 2-4 / J2.5 / J3.2", "Fy y Fu del acero de la placa (A992/A36). F_EXX del electrodo. Fnv y Fnt del perno. Definen todos los topes de resistencia."],
    "Geometria":     ["AISC §J3.3 / §J3.4",            "Perfiles de viga y columna (d, tf, Ag). Placa: h_p, Ag, Agv, Anv. Pernos: Ab, paso s, borde Le, distancia libre l_c (gobierna tearout)."],
    "Demanda":       ["AISC §J1.1 · LRFD",             "Vu, Nu, Mu del análisis (ETABS, combo LRFD gobernante). Para VC momento: Fuf = Mu/(d−tf) convierte el momento en par de fuerzas de ala."],
    "Pernos §J3":    ["AISC §J3.6 / §J3.7 / §J3.10",  "Cortante (Fnv·Ab·n), tracción (Fnt·Ab·n, reducido por J3-3a si actúa Vu), aplastamiento y tearout dependen de Fu de la PLACA, no del perno."],
    "Soldadura §J2": ["AISC §J2.2a / §J2.4",           "t_e = 0.707·w. Fnw = 0.6·F_EXX (θ=0, conservador). La junta vale min(φRn_soldadura, φRn_metal_base) — la placa puede fallar antes que el cordón."],
    "Elementos §J4": ["AISC §J4.1–§J4.3",              "Fy rige fluencia (φ=0.90 tracción, φ=1.00 cortante); Fu rige rotura (φ=0.75). Block shear combina corte + tracción — governa en placas con pocos pernos."],
    "Placa base §J8":["AISC §J8 · DG-1 · ACI 318 §14", "Aplastamiento del concreto φPp=0.65·0.85·f'c·A1·√(A2/A1)≤0.65·1.7·f'c·A1. Espesor por flexión del voladizo l=max(m,n,n'): tp=l·√(2·fp/(0.90·Fy)). P_u y geometría vienen de ETABS pero quedan editables."],
    "Verificacion":  ["AISC §J / §B3.1",               "φRn_gob = min(todos los estados). DC = Demanda / φRn_gob ≤ 1.0. El estado gobernante es el punto débil real de la conexión."],
  };
  dev.innerHTML = insumosFichaConexionHTML(m.ficha) + orden.map((sec, i) => {
    const [ref, intro] = CX_SEC[sec] || ["AISC §J", ""];
    return `<div style="margin-bottom:14px">
      <div style="display:flex;align-items:baseline;gap:8px;border-bottom:2px solid var(--accent);padding-bottom:3px;margin-bottom:6px">
        <span style="font-size:12px;font-weight:700">${i + 1}. ${esc(sec)}</span>
        ${ref ? `<span style="font-size:9px;font-weight:700;color:var(--accent);border:1px solid var(--accent);border-radius:8px;padding:1px 7px">${esc(ref)}</span>` : ""}
      </div>
      ${intro ? `<div style="font-size:11px;color:var(--text-dim);font-style:italic;margin-bottom:7px;line-height:1.45">${esc(intro)}</div>` : ""}
      ${grupos[sec].map(etabsDevLine).join("")}
    </div>`;
  }).join("");
  bindConexionPartida();
}

function bindConexionPartida() {
  const btn = document.getElementById("cx-genpart-btn");
  if (btn) btn.addEventListener("click", conexionGenerarPartida);
}

async function conexionGenerarPartida() {
  const pid = state.activeId;
  if (!pid) { alert("Abre un presupuesto primero."); return; }
  const out = document.getElementById("cx-partida-result");
  const n = parseFloat(document.getElementById("cx-part-n")?.value) || 1;
  const s = conexionState;
  if (out) out.innerHTML = `<span style="color:var(--text-dim)">Generando…</span>`;
  let res;
  try {
    res = await api("POST", `/diseno/${pid}/conexion-generar-partida`, {
      perfil_viga: s.perfil_viga, perfil_columna: s.perfil_columna,
      tipo_conexion: s.tipo, n_conexiones: n,
    });
  } catch (err) { if (out) out.innerHTML = `<span style="color:#e74c3c">Error: ${esc(err.message)}</span>`; return; }
  if (res.status === "sin_ficha") {
    if (out) out.innerHTML = `<span style="color:#e67e22">${esc((res.avisos || []).join(" "))}</span>`;
    return;
  }
  if (out) out.innerHTML = `<span style="color:#27ae60;font-weight:700">✓ ${esc(res.csi)} · ${res.cantidad} pza · L ${fmt(res.total, 2)}</span>`;
  if (typeof loadObra === "function") { try { loadObra(state.activeId); } catch (e) {} }
}

function conexionInfoHTML() {
  return `<div style="max-width:840px;font-size:12.5px;line-height:1.6">
    <div style="border:1px solid var(--accent);border-radius:5px;padding:12px 14px;margin-bottom:12px;background:var(--surface)">
      <div style="font-weight:700;color:var(--accent);margin-bottom:6px">¿Qué hace este módulo?</div>
      Verifica conexiones de acero por <b>LRFD (AISC 360-16 §J)</b>, en métrico (kgf, cm, t). Calcula la resistencia de diseño φRn de cada estado límite, toma el <b>gobernante = mínimo</b>, y compara contra la demanda (D/C ≤ 1.0).
    </div>
    <div style="border:1px solid var(--border);border-radius:5px;padding:12px 14px;margin-bottom:12px;background:var(--surface)">
      <div style="font-weight:700;margin-bottom:6px">De dónde viene cada dato</div>
      <ul style="margin:0;padding-left:18px">
        <li><b>Tipo / Viga / Columna:</b> de las fichas Div 05 del proyecto. La ficha de conexión (CV/VV/CX) se resuelve sola.</li>
        <li><b>Placa, pernos, soldadura:</b> del detalle/planos de taller. Defaults razonables editables.</li>
        <li><b>Demanda V_u / N_u / M_u:</b> del análisis ETABS, combinación LRFD gobernante (hoy se teclea; import de fuerzas-nudo = fase siguiente).</li>
      </ul>
    </div>
    <div style="border:1px solid var(--border);border-radius:5px;padding:12px 14px;margin-bottom:12px;background:var(--surface)">
      <div style="font-weight:700;margin-bottom:6px">Estados límite por tipo</div>
      <table style="border-collapse:collapse;font-size:11.5px;width:100%">
        <thead><tr style="color:var(--text-dim);text-align:left"><th style="padding:3px 8px">Tipo</th><th style="padding:3px 8px">Estados que se chequean</th></tr></thead>
        <tbody>
          <tr><td style="padding:3px 8px;font-weight:600">VC cortante</td><td style="padding:3px 8px">pernos (corte/aplast./tearout) + soldadura placa-columna + §J4 + block shear</td></tr>
          <tr><td style="padding:3px 8px;font-weight:600">VC momento</td><td style="padding:3px 8px">lo anterior + pernos a tracción + combinado J3-3a (par de ala M_u/(d−t_f))</td></tr>
          <tr><td style="padding:3px 8px;font-weight:600">Viga-viga</td><td style="padding:3px 8px">pernos + §J4 + block shear</td></tr>
          <tr><td style="padding:3px 8px;font-weight:600">Soldada</td><td style="padding:3px 8px">soldadura §J2 (filete) + metal base J2-2 → min</td></tr>
        </tbody>
      </table>
    </div>
    <div style="border:1px solid #e67e22;border-radius:5px;padding:11px 14px;background:rgba(230,126,34,.08)">
      <div style="font-weight:700;color:#e67e22;margin-bottom:5px">Alcance y límites honestos (esta fase)</div>
      <ul style="margin:0;padding-left:18px">
        <li><b>Stateless:</b> no guarda en BD, no genera partidas Div 05 todavía (fase siguiente, requiere confirmar 3 tablas nuevas).</li>
        <li><b>Placa base §J8</b> (aplastamiento concreto + espesor) = fase siguiente.</li>
        <li><b>Geometría de placa</b> derivada con convenciones estándar (s=3·d_b, borde=1.5·d_b). El detalle real afina tearout/block shear.</li>
        <li>El módulo de Soldadura viejo (kips/ksi) fue <b>eliminado (R7)</b>: este lo subsume en métrico + metal base + límites §J2.</li>
      </ul>
    </div>
  </div>`;
}

// Tabla de INSUMOS de la ficha de conexión (Div 05) — la ficha SIEMPRE se
// respalda con insumos de la base curada (fichas_v1.2.json).
function insumosFichaConexionHTML(ficha) {
  if (!ficha) return "";
  const ins = ficha.insumos || [];
  const okIns = ficha.insumos_ok && ins.length > 0;
  const rows = ins.map(i => `
    <tr>
      <td style="padding:2px 7px;font-family:monospace;font-size:10px">${esc(i.codigo || "")}</td>
      <td style="padding:2px 7px;font-size:10px">${esc(i.descripcion || "")}</td>
      <td style="padding:2px 7px;font-size:10px;color:var(--text-dim)">${esc(i.tipo || "")}</td>
      <td style="padding:2px 7px;text-align:right;font-size:10px">${fmt(i.cantidad, 3)} ${esc(i.unidad || "")}</td>
      <td style="padding:2px 7px;text-align:right;font-size:10px">${fmt(i.precio_unit, 2)}</td>
      <td style="padding:2px 7px;text-align:right;font-size:10px;font-weight:600">${fmt(i.total, 2)}</td>
    </tr>`).join("");
  const tabla = okIns ? `
    <table style="border-collapse:collapse;width:100%">
      <thead><tr style="color:var(--text-dim);font-size:9px;text-align:left">
        <th style="padding:2px 7px">Código</th><th style="padding:2px 7px">Insumo</th><th style="padding:2px 7px">Tipo</th>
        <th style="padding:2px 7px;text-align:right">Cant.</th><th style="padding:2px 7px;text-align:right">P.Unit</th><th style="padding:2px 7px;text-align:right">Total</th>
      </tr></thead><tbody>${rows}</tbody>
      <tfoot><tr style="border-top:1px solid var(--accent)">
        <td colspan="5" style="padding:3px 7px;text-align:right;font-weight:700;font-size:11px">Costo directo (Σ insumos)</td>
        <td style="padding:3px 7px;text-align:right;font-weight:700;font-size:11px">L ${fmt(ficha.costo_directo, 2)}</td>
      </tr></tfoot>
    </table>` : `<div style="color:#e74c3c;font-size:11px">⚠ Ficha sin insumos en la base curada — NO cumple la regla "ficha basada en insumos". Revisar fichas_v1.2.json.</div>`;
  return `
    <div style="border:1px solid var(--accent);border-radius:6px;margin-bottom:14px;background:var(--surface)">
      <div style="background:var(--surface2);padding:7px 11px;border-bottom:1px solid var(--border);display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">
        <b style="font-size:12px">🧾 Ficha Div 05 · ${esc(ficha.ficha || "—")}</b>
        <span style="font-family:monospace;font-size:11px;color:var(--accent)">${esc(ficha.csi || "")}</span>
        <span style="font-size:11px;color:var(--text-dim)">${ins.length} insumos · ${esc(ficha.unidad || "pza")}${ficha.aproximado ? " · (aprox.)" : ""}</span>
        <span style="margin-left:auto;font-size:12px;font-weight:700">Costo directo: L ${fmt(ficha.costo_directo, 2)}</span>
      </div>
      <div style="padding:8px 11px;overflow-x:auto">
        ${tabla}
        ${okIns ? `<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:8px;padding-top:8px;border-top:1px dashed var(--border)">
          <span style="font-size:11px;color:var(--text-dim)">Generar partida:</span>
          <input id="cx-part-n" type="number" min="1" step="1" value="1" style="width:62px;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:3px;padding:2px 5px;font-size:11px" title="Número de conexiones (pza)"/>
          <span style="font-size:11px;color:var(--text-dim)">pza</span>
          <button id="cx-genpart-btn" class="btn-primary" style="font-size:11px;padding:3px 10px" title="Crea/actualiza la partida Div 05 de esta conexión con sus insumos en la obra activa">📦 Generar partida Div 05</button>
          <span id="cx-partida-result" style="font-size:11px"></span>
        </div>` : ""}
        <div style="font-size:9.5px;color:var(--text-dim);margin-top:5px">Insumos de la base curada v1.2 · PU base ficha: L ${fmt(ficha.precio_unitario, 2)}. La ficha de conexión se respalda SIEMPRE con estos insumos (placa, pernos, electrodo, mano de obra, flete, herramienta).</div>
      </div>
    </div>`;
}
