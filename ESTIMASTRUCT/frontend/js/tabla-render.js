// tabla-render.js — Render de la tabla de partidas/capitulos + handlers.
// Cargado DESPUES de app.js. Scope global: usa state/esc/fmt/api (core); showPanelPartida vive en app.js.

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
  const audit = isDev && state.auditMode;
  const moMode = isDev && state.moMode;
  const savedWidths = loadTableWidths();
  // Header conditional
  const resizableTh = (key, label, cls = "", width = null) => {
    const saved = savedWidths[key];
    const finalWidth = Number.isFinite(saved) ? saved : width;
    const widthStyle = finalWidth ? `style="width:${finalWidth}px;min-width:${finalWidth}px"` : "";
    return `<th class="resizable-th ${cls}" data-col="${key}" ${widthStyle}><span class="th-label">${label}</span><span class="col-resizer" data-col="${key}" title="Arrastrar para ajustar"></span></th>`;
  };
  const tmHeader = showTm ? resizableTh("tm", "Type Mark", "", 90) : "";
  let headerCells;
  if (!isDev) {
    headerCells = `${resizableTh("csi", "CSI", "", 120)}${resizableTh("desc", "Descripción", "", 360)}${resizableTh("qty", "Cantidad", "num", 95)}${resizableTh("pu", "PRECIO UNITARIO", "num", 120)}${resizableTh("tot", "Total", "num", 120)}`;
  } else if (moMode) {
    headerCells = `${resizableTh("csi", "CSI", "", 120)}${tmHeader}${resizableTh("desc", "Descripción", "", 300)}${resizableTh("ud", "Ud", "", 60)}${resizableTh("qty", "Cantidad", "num", 95)}${resizableTh("mo", "Mano de Obra", "num", 110)}${resizableTh("cd", "TOTAL MANO DE OBRA", "num", 150)}`;
  } else {
    headerCells = `${resizableTh("csi", "CSI", "", 120)}${tmHeader}${resizableTh("desc", "Descripción", "", 300)}${resizableTh("ud", "Ud", "", 60)}${resizableTh("qty", "Cantidad", "num", 95)}${resizableTh("mo", "Mano de Obra", "num", 90)}${resizableTh("ma", "INSUMOS", "num", 90)}${audit ? resizableTh("cd", "TOTAL MANO DE OBRA", "num", 140) : resizableTh("cd", "COSTO DIRECTO", "num", 110)}${audit ? resizableTh("pu", "TOTAL INSUMOS", "num", 130) : resizableTh("pu", "PRECIO UNITARIO", "num", 110)}${resizableTh("tot", "Total", "num", 110)}`;
  }
  const totalCols = isDev ? (moMode ? (showTm ? 7 : 6) : (showTm ? 10 : 9)) : 5;

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
    // En modo Mano de Obra, el total del capítulo suma SOLO mano de obra (Cant × costo_mo)
    // de sus partidas, no el total de obra (cap.total).
    const capTotalDisplay = moMode
      ? cap.partidas.reduce((s, p) => s + (parseFloat(p.cantidad) || 0) * (parseFloat(p.costo_mo) || 0), 0)
      : cap.total;
    rows += `
      <tr class="capitulo-row" data-cap="${cap.id}">
        ${capDesc}
        ${capEmpty}
        <td class="num"><b>${fmt(capTotalDisplay)}</b></td>
      </tr>
    `;
    for (const p of cap.partidas) {
      const colorClass = `row-${p.color_tipo || 'blanco'}`;
      const isSelected = p.id === state.selectedPartida?.id;
      const tmCell = showTm
        ? `<td class="tm-cell" data-pid="${p.id}" data-tm="${esc(p.type_mark || "")}" style="font-size:11px;color:var(--text-dim);cursor:pointer" title="Doble-clic para editar">${esc(p.type_mark || "—")}</td>`
        : "";
      // INSUMOS = MATERIAL (costo_ma) + resto de non-MO (SUBCONTRATO/HERRAMIENTA/EQUIPO/FLETE/DISEÑO,
      // que el backend acumula en unitario_matriz). Antes solo se mostraba costo_ma → columna
      // y costo directo SUBVALUADOS; costo_base backend YA sumaba unitario_matriz (PU/total correctos).
      const insumosNonMo = (parseFloat(p.costo_ma) || 0) + (parseFloat(p.unitario_matriz) || 0);
      const costoDirecto = (parseFloat(p.costo_mo) || 0) + insumosNonMo;
      const qtyNum = parseFloat(p.cantidad) || 0;
      const totalInsumos = qtyNum * insumosNonMo;   // Cant × Insumos (MA + non-MO)
      const totalManoObra = qtyNum * (parseFloat(p.costo_mo) || 0);  // Cant × Mano de Obra
      const colorDot = isDev
        ? `<span class="color-dot ${p.color_tipo||'blanco'}" data-pid="${p.id}" title="Cambiar color"></span>`
        : "";
      const descCell = `<td class="desc-cell" data-pid="${p.id}" data-desc="${esc(p.descripcion || "")}" title="Doble-clic para editar">${esc(p.descripcion)}</td>`;
      const udCell = `<td class="ud-cell" data-pid="${p.id}" data-ud="${esc(p.unidad || "")}" style="color:var(--text-dim);cursor:pointer" title="Doble-clic para editar">${esc(p.unidad)}</td>`;
      const qtyCell = `<td class="qty-cell ${p.cantidad > 0 ? 'qty-filled' : ''}" data-pid="${p.id}">${p.cantidad > 0 ? fmt(p.cantidad) : "—"}</td>`;
      const csiCell = `<td style="font-size:11px;color:var(--text-dim)">${colorDot}${esc(p.clave_csi)}</td>`;
      let cells;
      if (!isDev) {
        cells = `
          <td style="font-size:11px;color:var(--text-dim)">${esc(p.clave_csi)}</td>
          <td style="max-width:380px;overflow:hidden;text-overflow:ellipsis">${esc(p.descripcion)}</td>
          <td class="num ${p.cantidad > 0 ? 'qty-filled' : ''}">${p.cantidad > 0 ? fmt(p.cantidad) : "—"}</td>
          <td class="num pu-cell">${fmt(p.precio_unitario)}</td>
          <td class="num tot-cell ${p.total > 0 ? 'total-filled' : ''}">${p.total > 0 ? fmt(p.total) : "—"}</td>
        `;
      } else if (moMode) {
        cells = `
          ${csiCell}
          ${tmCell}
          ${descCell}
          ${udCell}
          ${qtyCell}
          <td class="num">${fmt(p.costo_mo)}</td>
          <td class="num cd-cell">${fmt(totalManoObra)}</td>
        `;
      } else {
        cells = `
          ${csiCell}
          ${tmCell}
          ${descCell}
          ${udCell}
          ${qtyCell}
          <td class="num">${fmt(p.costo_mo)}</td>
          <td class="num">${fmt(insumosNonMo)}</td>
          <td class="num cd-cell">${audit ? fmt(totalManoObra) : fmt(costoDirecto)}</td>
          <td class="num pu-cell">${audit ? fmt(totalInsumos) : fmt(p.precio_unitario)}</td>
          <td class="num tot-cell ${p.total > 0 ? 'total-filled' : ''}">${p.total > 0 ? fmt(p.total) : "—"}</td>
        `;
      }
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
  attachTableResizeHandlers(area);
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
          // En auditoría/MO, los cells CD/PU muestran Cant × valor → recalcular
          if (state.auditMode || state.moMode) {
            const q = result.cantidad;
            const insumosNonMoEdit = (parseFloat(partida.costo_ma) || 0) + (parseFloat(partida.unitario_matriz) || 0);
            const cdCell = row.querySelector(".cd-cell");
            if (cdCell) cdCell.textContent = fmt(q * (parseFloat(partida.costo_mo) || 0));  // Total Mano de Obra
            if (puCell) puCell.textContent = fmt(q * insumosNonMoEdit);  // Total Insumos (MA + non-MO)
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

function attachTableResizeHandlers(area) {
  const table = area.querySelector("table");
  if (!table) return;
  const handles = table.querySelectorAll(".col-resizer");
  if (!handles.length) return;

  handles.forEach(handle => {
    handle.addEventListener("mousedown", e => {
      e.preventDefault();
      e.stopPropagation();
      const th = handle.closest("th");
      if (!th) return;
      const col = th.dataset.col;
      const startX = e.clientX;
      const startWidth = th.getBoundingClientRect().width;
      const widths = loadTableWidths();

      const onMove = ev => {
        const nextWidth = Math.max(48, Math.round(startWidth + (ev.clientX - startX)));
        th.style.width = `${nextWidth}px`;
        th.style.minWidth = `${nextWidth}px`;
      };

      const onUp = ev => {
        const nextWidth = Math.max(48, Math.round(startWidth + (ev.clientX - startX)));
        widths[col] = nextWidth;
        saveTableWidths(widths);
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      };

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  });
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

