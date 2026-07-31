// auditoria-formulas.js — Hoja de Auditoría de Fórmulas.
// Consolida en un solo lugar: (a) las 4 memorias ya narradas (concreto/sismo/
// acero/conexiones) vía links directos al módulo correspondiente, (b) las 2
// memorias nuevas (pricing + indirectos de presupuesto), (c) el índice de los
// 8 módulos que siguen ciegos. Mismo patrón visual DATO/CÁLC/RESULT/CHECK que
// la Hoja de Diseño Estructural (kx/esc/fmt/api vienen de core.js + calculo-estructural.js).
// Carga DESPUÉS de calculo-estructural.js (usa su kx()).

const auditoriaState = {
  vista: "resumen",          // resumen | pricing | calculos | mamposteria
  pricingSub: "calc",        // calc | partida
  pricing: { costo_mo: 100, costo_ma: 200, unitario_matriz: 0, sobrecosto_pct: 20, cantidad: 1 },
  // Defaults = TMS 402-16 §7.3.2.6 (ver backend/services/mamposteria_memoria.py)
  mampo: {
    longitud_m: 5, altura_m: 3, espesor_cm: 20,
    s_vertical_m: 0.60, s_horizontal_m: 0.60, celda_largo_cm: 15,
    barra_vertical: "#4", barra_horizontal: "#4",
    con_refuerzo_horizontal: true, s_celda_m: null, celda_ancho_cm: null,
  },
  partidaId: null,
  resumenCache: null,
  calculosCache: null,       // { pid, memoria }
};
let auditoriaTimer = null;

// ── Renderer genérico de memoria {meta, pasos, constantes} — mismo look que
// la Hoja de Diseño Estructural (cardHtml/seccionHtml de calculo-estructural.js),
// pero sin acoplarse a secciones estructurales fijas. ──────────────────────
const AUD_TIPO_COLOR = { input: "#56ccf2", intermedio: "#8a94a6", resultado: "#27ae60", check: "#f2c94c", takeoff: "#bb6bd9" };
const AUD_TIPO_BADGE = { input: "DATO", intermedio: "CÁLC", resultado: "RESULT", check: "CHECK", takeoff: "TAKEOFF" };

const AUD_SEC_INTRO = {
  "Bucketing 3-vías": "Cada insumo de la partida cae en uno de 3 buckets según su tipo. Fuente única: services/pricing.rebucket_insumos (ADR-003).",
  "Costo base":       "costo_base = MO + MA + sub-matrices OPUS. Ningún router debe recalcular esto en paralelo.",
  "Precio unitario":  "El sobrecosto es el único markup que hoy mueve el precio — administración/utilidad/imprevistos/IVA de config_presupuesto son campos muertos (no los lee ningún cálculo).",
  "Total":            "cantidad × PU = lo que aparece en la fila de la partida.",
  "Cuantización":     "ADR-004: toda cifra monetaria pasa por Decimal(str(x)), nunca Decimal(float), cuantizada ROUND_HALF_UP a 4 decimales.",
  "Verificación vs BD": "Compara el recálculo en vivo (desde los insumos actuales) contra lo persistido en la partida. Una discrepancia no es necesariamente un error — puede ser edición manual posterior al último /calcular — pero debe verse.",
  "Vista A — /calcular": "Reproduce exactamente la aritmética de POST /presupuestos/{pid}/calcular sobre este presupuesto, sin escribir nada.",
  "Vista B — /reporte":  "Reproduce exactamente la aritmética de GET /presupuestos/{pid}/reporte sobre este presupuesto, sin escribir nada.",
  "⚠ Hallazgo": "Esta auditoría expone el comportamiento actual del código. No lo corrige.",
  "Geometría": "Dimensiones del paño. El área de muro (L×h) es la base de TODO el takeoff: los coeficientes de acero y de relleno son por m² de muro.",
  "Acero de refuerzo": "El peso lineal de la varilla NO está tabulado: se deriva de π/4·db² · 10⁻⁴ · γs con la misma densidad (7850 kg/m³) que usan los takeoffs de viga y columna. Antes de 2026-07-27 aquí había una constante fija de 3.5 kg/m² sin fórmula ni norma.",
  "Concreto de relleno": "Volumen de grout = área de celda ÷ espaciamiento de celdas. La constante vieja (0.023 m³/m²) era el ÁREA de una sola celda usada como si fuera volumen por m² — le faltaba dividir por el espaciamiento.",
  "Verificación TMS 402": "ACI 318 no cubre mampostería. El código aplicable es TMS 402 (hasta la ed. 2013 se publicaba como el conjunto TMS 402/ACI 530/ASCE 5; desde 2016, TMS 402 a secas). §7.3.2.6 fija los mínimos sísmicos de muro de cortante de mampostería especial reforzada.",
  // ── Tanda 2026-07-31 ──────────────────────────────────────────────────────
  "Base de la obra": "Los dos números de los que cuelga todo el prorrateo: lo que vale la obra hoy (Σ partida.total, con sobrecosto) y el piso por debajo del cual se pierde plata (Σ cantidad × costo_base, sin markup).",
  "Factor de prorrateo": "Un solo número multiplica TODOS los precios unitarios del PDF bancario. Hasta 2026-07-31 no aparecía en ninguna parte del documento ni de la UI.",
  "Cuadre del documento": "La fila TOTAL del PDF se FUERZA a valor_banco, no a la suma de las filas ya redondeadas a 2 decimales. La diferencia existe siempre; aquí se cuantifica en Lempiras.",
  "Margen del documento": "Lo que realmente importa del prorrateo: qué margen queda sobre el costo directo DESPUÉS de escalar. Si es negativo, el papel que va al banco documenta una obra a pérdida.",
  "Gantt bancario": "El buffer de contratiempos es una constante fija (26 días activos = 1 mes laboral), no un cálculo. El banco lo ve como una actividad más.",
  "Cantidad de Revit": "La cantidad medida en el modelo se redondea SIEMPRE hacia arriba antes de aplicar factores. El salto no se muestra en la tabla de partidas.",
  "Factores de ajuste": "_safe_factor (routers/partidas.py:70) convierte un 0 en 1.0 sin avisar y deja pasar los negativos. Quien teclea 0 esperando anular la partida obtiene la cantidad completa.",
  "Cantidad facturable": "El resultado del takeoff: lo que se factura y lo que ve el cliente en la fila del presupuesto.",
  "Actividad": "Toda la duración y la fase salen de la clave CSI. Una CSI mal asignada no produce un error: produce un plazo distinto.",
  "Fuente del rendimiento": "Cascada de 4 niveles: TIEMPOS_FIJOS > MANUAL_SPLIT > catálogo V1.2 > SIN_TIEMPO. El último asigna 1 día por defecto — una actividad de tres semanas se dibuja como una barra de un día.",
  "Jornadas-hombre": "Trabajo total que exige la actividad, antes de repartirlo entre personas. Especialista y ayudante se cuentan por separado.",
  "Duración": "Gobierna el oficio más cargado, con redondeo hacia arriba: media jornada sobrante cuesta un día entero de calendario.",
  "Secuenciación": "Los offsets de fase (0, 3, 8, 22, 29, 50, 80, 120 días) están codificados a mano por división CSI, sin justificación escrita. El plazo total del Gantt sale en buena medida de esas constantes.",
  "Identificación": "Tres rutas posibles para resolver las propiedades de un perfil: tabla AISC/CISC exacta, derivación de 3 rectángulos (~3% conservadora) o sección cerrada HSS. Hasta 2026-07-31 la memoria de acero no decía cuál se usó.",
  "Geometría": "Dimensiones del paño o de la sección. Cuando la fuente es 'derivada', estos valores vienen de PERFILES_ACERO, cuya tf/tw es imprecisa por admisión del propio repo.",
  "Propiedades derivadas": "⚠ El perfil NO está tabulado: todo se deriva tratando la sección como dos alas + un alma. El φMn que se narra aguas abajo hereda esta incertidumbre sin declararla.",
  "Propiedades (tabla AISC/CISC)": "Valores de norma. Sólo se convierten de unidad SI a cm. Ésta es la vía confiable.",
  "Propiedades HSS": "Sección cerrada: Ix = Iy, sin pandeo lateral-torsional, torsión de Bredt. Las fórmulas de perfil I no aplican.",
  "Esbelteces": "Clasifican ala y alma en compacta / no compacta / esbelta. Deciden qué sección del AISC gobierna la flexión y el cortante.",
  "Impacto aguas abajo": "Aquí se cierra el círculo: Mp = Fy·Zx es el número que la memoria de miembro de acero muestra perfectamente narrado. Su calidad es exactamente la calidad del Zx de arriba.",
  "Entrada": "Lo que el usuario declara al pegar la tabla de ETABS. Nada en el texto pegado dice en qué unidad están los números — la declaración es la única señal que tiene el sistema.",
  "Factores": "Fuerza y momento comparten factor porque ETABS reporta el brazo en metros en ambos flujos. Es correcto, pero no estaba escrito en ninguna parte.",
  "Aplicación": "El motor de diseño trabaja SIEMPRE en t y t·m. Éste es el número que realmente entra a §J8, §H1 y a las memorias de acero.",
  "Sensibilidad": "Elegir la unidad equivocada no produce un resultado que 'se vea mal': escala todo el diseño de forma uniforme por ~101.97× (kgf ↔ kN). Es el error más difícil de detectar del sistema.",
  "Columna": "Regla de pulgar del despacho: 8 cm de lado por nivel. ACI 318-19 no predimensiona, verifica — esto sirve para arrancar el modelo, no para defenderlo.",
  "Viga": "Lectura del criterio clásico L/10 aplicado a la luz LIBRE (cara a cara de apoyo, no entre ejes). Más conservador que el L/12–L/16 habitual para vigas continuas.",
  "Peralte efectivo": "d = h − recubrimiento es una aproximación: el d riguroso descuenta también el estribo y medio diámetro de barra. Para predimensionar alcanza; el motor de diseño usa el d real.",
  "Mapeo perfil → ficha": "Tres puntos donde la cadena descarta información: el rol asumido en perfiles duales, la agrupación por triple clave y los perfiles fuera del catálogo, cuya longitud no llega a ninguna partida.",
  "Agrupación": "Se agrupa por (ficha, perfil normalizado, rol), no sólo por ficha: dos perfiles distintos que mapean a la misma ficha producen filas separadas.",
  "Envolvente D/C por ficha": "Cada ficha reporta UN D/C: el del miembro peor. Los otros N−1 miembros y sus combos desaparecen del reporte.",
  "Verificación": "Los checks que hasta 2026-07-31 no existían en ninguna parte. No verifican que el cálculo esté bien — verifican que no haya decisiones tomadas en silencio.",
};

function audValorHtml(p) {
  if (typeof p.valor === "boolean")
    return p.valor ? `<span style="color:#27ae60;font-weight:700">✓ OK</span>`
                   : `<span style="color:#e74c3c;font-weight:700">✗</span>`;
  if (typeof p.valor === "number") {
    const n = p.valor.toLocaleString("es-HN", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
    const u = p.unidad ? ` <span style="color:var(--text-dim);font-weight:400;font-size:12px">${esc(p.unidad)}</span>` : "";
    return `<span style="font-weight:700">${n}</span>${u}`;
  }
  const u = p.unidad ? ` <span style="color:var(--text-dim);font-weight:400;font-size:12px">${esc(p.unidad)}</span>` : "";
  return `<span style="font-weight:700">${esc(String(p.valor))}</span>${u}`;
}

// Bloque "dónde exactamente" — UNA entrada de `p.hallazgos` (contrato genérico,
// ver services/calculos_memoria.py). `h` apunta a un paso YA narrado en otro
// lugar de la memoria (h.simbolo_ref) y trae su fórmula/sustitución REAL con
// el término culpable ya envuelto en \textcolor por el backend
// (_resaltar_termino) — el frontend solo llama a kx(), nunca reimplementa el
// resaltado. Reusable por cualquier hallazgo futuro (export_pdf, cronograma,
// partidas, acero_ficha, etc.), no solo el bug de sobrecosto.
function audHallazgoItemHtml(h) {
  return `
    <div style="border-left:3px solid #e74c3c;padding:7px 10px;margin-top:7px;background:#e74c3c14;border-radius:0 4px 4px 0">
      <div style="font-size:9px;font-weight:700;color:#e74c3c;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">
        Dónde exactamente — paso <span style="font-family:monospace">${esc(h.simbolo_ref || "")}</span>${h.etiqueta_ref ? ` · ${esc(h.etiqueta_ref)}` : ""}
      </div>
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:4px;padding:6px 9px;margin-bottom:5px;overflow-x:auto;font-size:1.05em">
        ${kx(h.latex_formula_marcada, h.formula_ref)}
      </div>
      ${h.latex_sub_marcada || h.sustitucion_ref ? `
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:4px;padding:6px 9px;margin-bottom:5px;overflow-x:auto;font-size:.95em;color:#bb6bd9">
        ${kx(h.latex_sub_marcada, h.sustitucion_ref)}
      </div>` : ""}
      ${h.nota ? `<div style="font-size:11px;color:var(--text);line-height:1.5">${esc(h.nota)}</div>` : ""}
    </div>`;
}

function audCardHtml(p) {
  const col = AUD_TIPO_COLOR[p.tipo] || "var(--text-dim)";
  const badge = AUD_TIPO_BADGE[p.tipo] || "";
  const isInput = p.tipo === "input";
  const hasF = !isInput && !!p.latex;
  const hasS = !isInput && !!p.latex_sub && p.formula !== "—";
  const hasHallazgos = Array.isArray(p.hallazgos) && p.hallazgos.length > 0;
  const kxRow = (tag, latex, fallback, color) => `
    <div style="display:flex;gap:8px;align-items:center;background:var(--surface2);border:1px solid var(--border);border-radius:4px;padding:6px 9px;margin-bottom:5px;overflow-x:auto">
      <span style="flex:0 0 auto;width:74px;font-size:8px;font-weight:700;letter-spacing:.5px;color:var(--text-dim);text-transform:uppercase">${tag}</span>
      <span style="flex:1 1 auto;font-size:1.02em;color:${color || 'var(--text)'};min-width:0">${kx(latex, fallback)}</span>
    </div>`;
  return `
    <div style="border:1px solid ${col}44;border-left:3px solid ${col};border-radius:5px;padding:9px 11px;margin-bottom:8px;background:var(--surface)">
      <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:7px">
        <span style="font-family:monospace;font-weight:700;font-size:17px;color:${col}">${esc(p.simbolo || "")}</span>
        <span style="font-size:12px;color:var(--text)">${esc(p.etiqueta || "")}</span>
        <span style="margin-left:auto;display:flex;gap:6px;align-items:center">
          ${p.referencia && p.referencia !== "—" ? `<span style="font-size:9px;font-weight:700;color:var(--accent);border:1px solid var(--accent);border-radius:8px;padding:1px 7px;white-space:nowrap">${esc(p.referencia)}</span>` : ""}
          <span style="font-size:8px;font-weight:700;letter-spacing:.5px;padding:1px 5px;border-radius:8px;background:${col}22;color:${col};border:1px solid ${col}55">${badge}</span>
        </span>
      </div>
      ${hasF ? kxRow("Fórmula", p.latex, p.formula) : ""}
      ${hasS ? kxRow("Sustitución", p.latex_sub, p.sustitucion, "#bb6bd9") : ""}
      <div style="display:flex;align-items:baseline;gap:8px;margin-top:6px">
        <span style="flex:0 0 auto;width:74px;font-size:8px;font-weight:700;letter-spacing:.5px;color:var(--text-dim);text-transform:uppercase">Resultado</span>
        <span style="font-size:17px">= ${audValorHtml(p)}</span>
      </div>
      ${p.descripcion ? `<div style="font-size:11px;color:var(--text-dim);line-height:1.45;margin-top:6px">${esc(p.descripcion)}</div>` : ""}
      ${hasHallazgos ? p.hallazgos.map(audHallazgoItemHtml).join("") : ""}
    </div>`;
}

function audLegendHtml() {
  return `
    <div style="font-size:10px;color:var(--text-dim);line-height:1.6;padding:7px 10px;background:var(--surface2);border:1px solid var(--border);border-radius:5px;margin-bottom:12px">
      Cada tarjeta narra un paso REAL del motor (nunca recalculado por la auditoría): <b>símbolo</b> · <b>Fórmula</b> · <b>Sustitución</b> numérica · <b>Resultado</b> · <b>Referencia</b>.<br>
      <span style="color:#56ccf2;font-weight:700">DATO</span> entrada ·
      <span style="color:#8a94a6;font-weight:700">CÁLC</span> intermedio ·
      <span style="color:#27ae60;font-weight:700">RESULT</span> resultado ·
      <span style="color:#f2c94c;font-weight:700">CHECK</span> verificación/hallazgo.
    </div>`;
}

// Pinta {meta, pasos, constantes} dentro de containerEl. `opts.titulo` es un
// encabezado libre (HTML permitido, ya escapado por el caller).
function renderMemoriaGenerica(containerEl, m, opts) {
  opts = opts || {};
  if (!containerEl) return;
  if (!m || !Array.isArray(m.pasos) || !m.pasos.length) {
    containerEl.innerHTML = `<div style="color:var(--text-dim);font-size:12px;padding:8px">Sin pasos que mostrar.</div>`;
    return;
  }
  const orden = [], grupos = {};
  m.pasos.forEach(p => { if (!grupos[p.seccion]) { grupos[p.seccion] = []; orden.push(p.seccion); } grupos[p.seccion].push(p); });

  const constHtml = (Array.isArray(m.constantes) && m.constantes.length)
    ? `<div style="border:1px solid var(--border);border-radius:5px;padding:8px 11px;margin-bottom:12px;background:var(--surface)">
         <div style="font-size:10px;font-weight:700;color:var(--text-dim);letter-spacing:.5px;margin-bottom:5px">CONSTANTES</div>
         <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:5px 16px;font-size:12px">
           ${m.constantes.map(c => `<div title="${esc(c.desc || "")}">${kx(c.latex, c.simbolo)} <span style="color:var(--text-dim);font-size:10px">${esc(c.unidad || "")}</span></div>`).join("")}
         </div>
       </div>` : "";

  const seccionHtml = (sec, i) => `
    <div style="margin-bottom:16px">
      <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:6px;border-bottom:2px solid var(--accent);padding-bottom:4px">
        <span style="font-size:13px;font-weight:700;color:var(--text)">${i + 1}. ${esc(sec)}</span>
      </div>
      ${AUD_SEC_INTRO[sec] ? `<div style="font-size:11px;color:var(--text-dim);font-style:italic;margin-bottom:9px;line-height:1.45">${esc(AUD_SEC_INTRO[sec])}</div>` : ""}
      ${grupos[sec].map(audCardHtml).join("")}
    </div>`;

  containerEl.innerHTML = `
    ${opts.titulo ? `<div style="font-size:13px;margin-bottom:10px">${opts.titulo}</div>` : ""}
    ${constHtml}
    ${audLegendHtml()}
    ${orden.map(seccionHtml).join("")}
  `;
}

// ── VISTA: Resumen / índice de cobertura ────────────────────────────────────
async function audRenderResumen() {
  const c = document.getElementById("auditoria-content");
  if (!c) return;
  c.innerHTML = `<div style="padding:14px;color:var(--text-dim);font-size:12px">Cargando índice…</div>`;
  try {
    if (!auditoriaState.resumenCache) auditoriaState.resumenCache = await api("GET", "/auditoria/resumen");
  } catch (err) {
    c.innerHTML = `<div style="padding:14px;color:#e74c3c;font-size:12px">Error: ${esc(err.message)}</div>`;
    return;
  }
  const r = auditoriaState.resumenCache;
  const rowNarrado = (x) => `
    <tr>
      <td style="padding:6px 10px;font-weight:700">${esc(x.nombre)}${x.nuevo_2026_07_31 ? ' <span style="font-size:9px;color:#27ae60;border:1px solid #27ae60;border-radius:8px;padding:1px 6px">NUEVO 07-31</span>' : x.nuevo_2026_07_27 ? ' <span style="font-size:9px;color:#27ae60;border:1px solid #27ae60;border-radius:8px;padding:1px 6px">NUEVO</span>' : ""}</td>
      <td style="padding:6px 10px;font-family:monospace;font-size:11px;color:var(--text-dim)">${esc(x.archivo)}</td>
      <td style="padding:6px 10px;font-size:11px;color:var(--text-dim)">${esc(x.endpoint)}</td>
      <td style="padding:6px 10px;text-align:center">${x.pasos}</td>
      <td style="padding:6px 10px">
        ${x.modulo === "auditoria"
          ? `<button class="btn-primary aud-goto-vista" data-vista="${esc(x.id)}" style="font-size:11px;padding:3px 9px">Ver aquí →</button>`
          : `<button class="btn-primary aud-goto-modulo" data-modulo="${x.modulo}" style="font-size:11px;padding:3px 9px">Abrir módulo →</button>`}
      </td>
    </tr>${x.flag ? `<tr><td colspan="5" style="padding:2px 10px 8px;font-size:11px;color:${String(x.flag).startsWith("✔") ? "#27ae60" : String(x.flag).charAt(0) === "⚠" ? "#e74c3c" : "#f2c94c"}">${esc(x.flag)}</td></tr>` : ""}`;

  const rowCiego = (x) => `
    <tr>
      <td style="padding:5px 10px;font-family:monospace;font-size:11px">${esc(x.archivo)}</td>
      <td style="padding:5px 10px;font-size:11px;color:var(--text-dim)">${esc(x.dominio)}</td>
      <td style="padding:5px 10px;text-align:center">
        <span style="font-size:9px;font-weight:700;padding:1px 7px;border-radius:8px;
          background:${x.riesgo === 'alto' ? '#e74c3c22' : x.riesgo === 'medio' ? '#f2c94c22' : '#8a94a622'};
          color:${x.riesgo === 'alto' ? '#e74c3c' : x.riesgo === 'medio' ? '#f2c94c' : '#8a94a6'};
          border:1px solid currentColor">${esc(x.riesgo.toUpperCase())}</span>
      </td>
    </tr>`;

  c.innerHTML = `
    <div style="padding:14px 16px;max-width:1080px">
      <div style="border:1px solid var(--border);border-radius:5px;padding:10px 13px;margin-bottom:14px;background:var(--surface);font-size:12px;color:var(--text);line-height:1.6">
        Consolida TODAS las fórmulas de cálculo del backend en un solo lugar. Todo lo que es <b>ingeniería estructural</b> ya se narraba (4 motores); esta auditoría agrega <b>pricing</b> e <b>indirectos de presupuesto</b> — el lado del dinero, que corría ciego. Read-only: nada de lo que ves aquí recalcula por su cuenta; lee y narra lo que el motor real produce (ADR-003).
      </div>

      <div style="font-size:12px;font-weight:700;color:var(--accent);margin-bottom:6px">✓ Narrado (${r.narrados.length})</div>
      <div style="overflow-x:auto;margin-bottom:18px">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead><tr style="text-align:left;border-bottom:1px solid var(--border);color:var(--text-dim);font-size:10px;text-transform:uppercase">
            <th style="padding:4px 10px">Dominio</th><th style="padding:4px 10px">Archivo</th><th style="padding:4px 10px">Endpoint</th><th style="padding:4px 10px;text-align:center">Pasos</th><th></th>
          </tr></thead>
          <tbody>${r.narrados.map(rowNarrado).join("")}</tbody>
        </table>
      </div>

      <div style="font-size:12px;font-weight:700;color:#e67e22;margin-bottom:6px">○ Ciego — pendiente (${r.ciegos_pendientes.length})</div>
      <div style="overflow-x:auto;margin-bottom:10px">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead><tr style="text-align:left;border-bottom:1px solid var(--border);color:var(--text-dim);font-size:10px;text-transform:uppercase">
            <th style="padding:4px 10px">Archivo</th><th style="padding:4px 10px">Dominio</th><th style="padding:4px 10px;text-align:center">Riesgo</th>
          </tr></thead>
          <tbody>${r.ciegos_pendientes.map(rowCiego).join("")}</tbody>
        </table>
      </div>
      <div style="font-size:10px;color:var(--text-dim)">Fuente: ${esc(r.fuente)}. Fuera de scope de esta sesión — no tocado.</div>
    </div>`;

  c.querySelectorAll(".aud-goto-vista").forEach(b => b.addEventListener("click", () => {
    auditoriaState.vista = b.dataset.vista; renderAuditoria();
  }));
  c.querySelectorAll(".aud-goto-modulo").forEach(b => b.addEventListener("click", () => {
    setModuloActivo(b.dataset.modulo);
  }));
}

// ── VISTA: Pricing ───────────────────────────────────────────────────────────
function audPricingInputRow(key, label, unit) {
  const v = auditoriaState.pricing[key];
  return `<div style="display:flex;align-items:center;gap:6px;padding:3px 0">
    <span style="min-width:110px;font-size:11px;color:var(--text-dim)">${esc(label)}</span>
    <input data-audp="${key}" type="number" step="any" value="${v}"
      style="width:110px;background:var(--bg);border:1px solid var(--accent);color:var(--text);padding:3px 6px;border-radius:3px;font-family:monospace;font-weight:600"/>
    <span style="font-size:10px;color:var(--text-dim)">${esc(unit)}</span>
  </div>`;
}

async function audRecalcPricingCalc() {
  const dev = document.getElementById("aud-pricing-dev");
  if (!dev) return;
  const b = auditoriaState.pricing;
  let m;
  try {
    m = await api("POST", "/auditoria/pricing/memoria-rapida", {
      costo_mo: b.costo_mo, costo_ma: b.costo_ma, unitario_matriz: b.unitario_matriz,
      sobrecosto_pct: b.sobrecosto_pct, cantidad: b.cantidad,
    });
  } catch (err) { dev.innerHTML = `<div style="color:#e74c3c;font-size:12px">Error: ${esc(err.message)}</div>`; return; }
  renderMemoriaGenerica(dev, m);
}

function audBindPricingCalcInputs() {
  document.querySelectorAll("#aud-pricing-calc-form input[data-audp]").forEach(inp => {
    inp.addEventListener("input", () => {
      const k = inp.dataset.audp, v = parseFloat(inp.value);
      auditoriaState.pricing[k] = isNaN(v) ? 0 : v;
      clearTimeout(auditoriaTimer);
      auditoriaTimer = setTimeout(audRecalcPricingCalc, 250);
    });
  });
}

function audPartidasDisponibles() {
  if (typeof state === "undefined" || !state.activeData || !Array.isArray(state.activeData.capitulos)) return [];
  const out = [];
  state.activeData.capitulos.forEach(cap => (cap.partidas || []).forEach(p => out.push({
    id: p.id, clave_csi: p.clave_csi, descripcion: p.descripcion, capitulo: cap.nombre,
  })));
  return out;
}

async function audRenderPricingPartida() {
  const wrap = document.getElementById("aud-pricing-partida-wrap");
  if (!wrap) return;
  const partidas = audPartidasDisponibles();
  if (!partidas.length) {
    wrap.innerHTML = `<div style="color:#e67e22;font-size:12px;padding:10px">No hay presupuesto activo (o no tiene partidas). Abre un presupuesto en la pantalla principal y vuelve aquí.</div>`;
    return;
  }
  const opts = partidas.map(p => `<option value="${esc(p.id)}" ${p.id === auditoriaState.partidaId ? "selected" : ""}>${esc(p.clave_csi)} — ${esc(p.descripcion)} (${esc(p.capitulo)})</option>`).join("");
  wrap.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
      <span style="font-size:11px;color:var(--text-dim)">Partida real:</span>
      <select id="aud-partida-sel" style="flex:1;max-width:520px;background:var(--surface2);border:1px solid var(--accent);color:var(--text);padding:4px 8px;border-radius:3px;font-size:12px">
        <option value="">— elige una partida —</option>${opts}
      </select>
    </div>
    <div id="aud-pricing-partida-dev" style="font-size:14px"></div>`;
  const sel = document.getElementById("aud-partida-sel");
  sel.addEventListener("change", async () => {
    auditoriaState.partidaId = sel.value || null;
    const dev = document.getElementById("aud-pricing-partida-dev");
    if (!auditoriaState.partidaId) { dev.innerHTML = ""; return; }
    dev.innerHTML = `<div style="color:var(--text-dim);font-size:12px">Cargando…</div>`;
    try {
      const m = await api("GET", `/auditoria/pricing/partida/${auditoriaState.partidaId}/memoria`);
      const meta = m.meta || {};
      const titulo = `<span style="font-family:monospace;color:var(--accent)">${esc(meta.clave_csi || "")}</span> — ${esc(meta.descripcion || "")} <span style="color:var(--text-dim);font-size:11px">(${esc(meta.presupuesto_nombre || "")})</span>`;
      renderMemoriaGenerica(dev, m, { titulo });
    } catch (err) {
      dev.innerHTML = `<div style="color:#e74c3c;font-size:12px">Error: ${esc(err.message)}</div>`;
    }
  });
  if (auditoriaState.partidaId) sel.dispatchEvent(new Event("change"));
}

function audRenderPricing() {
  const c = document.getElementById("auditoria-content");
  if (!c) return;
  const sub = auditoriaState.pricingSub;
  c.innerHTML = `
    <div style="padding:14px 16px;max-width:980px">
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <button class="aud-sub-btn" data-sub="calc" style="font-size:12px;padding:5px 12px;border-radius:14px;cursor:pointer;border:1px solid ${sub === 'calc' ? 'var(--accent)' : 'var(--border)'};background:${sub === 'calc' ? 'var(--accent)' : 'var(--surface2)'};color:${sub === 'calc' ? '#1a1a1a' : 'var(--text)'};font-weight:700">🧮 Calculadora libre</button>
        <button class="aud-sub-btn" data-sub="partida" style="font-size:12px;padding:5px 12px;border-radius:14px;cursor:pointer;border:1px solid ${sub === 'partida' ? 'var(--accent)' : 'var(--border)'};background:${sub === 'partida' ? 'var(--accent)' : 'var(--surface2)'};color:${sub === 'partida' ? '#1a1a1a' : 'var(--text)'};font-weight:700">📥 Partida real (BD)</button>
      </div>
      <div style="font-size:11px;color:var(--text-dim);margin-bottom:12px;line-height:1.5">
        Narra <code>services/pricing.py</code> (ADR-003, fuente única de costeo) paso a paso: bucketing 3-vías → costo_base → precio unitario → total. Nunca reimplementa la aritmética — llama a las funciones puras reales.
      </div>
      ${sub === "calc" ? `
        <div id="aud-pricing-calc-form" style="border:1px solid var(--accent);border-radius:5px;padding:9px 12px;margin-bottom:12px;background:var(--surface)">
          <div style="font-size:10px;font-weight:700;color:var(--accent);letter-spacing:.5px;margin-bottom:6px">VARIABLES DE ENTRADA — edita aquí</div>
          <div style="display:flex;gap:26px;flex-wrap:wrap">
            <div>${audPricingInputRow("costo_mo", "costo_mo (MO)", "HNL")}${audPricingInputRow("costo_ma", "costo_ma (Material)", "HNL")}${audPricingInputRow("unitario_matriz", "unitario_matriz", "HNL")}</div>
            <div>${audPricingInputRow("sobrecosto_pct", "sobrecosto", "%")}${audPricingInputRow("cantidad", "cantidad", "unidad")}</div>
          </div>
        </div>
        <div id="aud-pricing-dev" style="font-size:14px">cargando…</div>
      ` : `<div id="aud-pricing-partida-wrap"></div>`}
    </div>`;

  c.querySelectorAll(".aud-sub-btn").forEach(b => b.addEventListener("click", () => {
    auditoriaState.pricingSub = b.dataset.sub; audRenderPricing();
  }));

  if (sub === "calc") { audBindPricingCalcInputs(); audRecalcPricingCalc(); }
  else audRenderPricingPartida();
}

// ── VISTA: Mampostería reforzada (TMS 402-16) ───────────────────────────────
// Reemplaza el módulo ciego routers/diseno_estructural.py::crear_mamposteria,
// que hasta 2026-07-27 usaba 3.5 kg/m² y 0.023 m³/m² como constantes mágicas.
function audMampoNumRow(key, label, unit, step) {
  const v = auditoriaState.mampo[key];
  return `<div style="display:flex;align-items:center;gap:6px;padding:3px 0">
    <span style="min-width:150px;font-size:11px;color:var(--text-dim)">${esc(label)}</span>
    <input data-audm="${key}" type="number" step="${step || "any"}" value="${v === null ? "" : v}"
      style="width:100px;background:var(--bg);border:1px solid var(--accent);color:var(--text);padding:3px 6px;border-radius:3px;font-family:monospace;font-weight:600"/>
    <span style="font-size:10px;color:var(--text-dim)">${esc(unit)}</span>
  </div>`;
}

function audMampoBarraRow(key, label) {
  const v = auditoriaState.mampo[key];
  const opts = ["#3", "#4", "#5", "#6", "#7", "#8"]
    .map(b => `<option value="${b}" ${b === v ? "selected" : ""}>${b}</option>`).join("");
  return `<div style="display:flex;align-items:center;gap:6px;padding:3px 0">
    <span style="min-width:150px;font-size:11px;color:var(--text-dim)">${esc(label)}</span>
    <select data-audm-sel="${key}" style="width:100px;background:var(--bg);border:1px solid var(--accent);color:var(--text);padding:3px 6px;border-radius:3px;font-family:monospace;font-weight:600">${opts}</select>
    <span style="font-size:10px;color:var(--text-dim)">ASTM A615</span>
  </div>`;
}

async function audRecalcMampo() {
  const dev = document.getElementById("aud-mampo-dev");
  if (!dev) return;
  let m;
  try {
    m = await api("POST", "/auditoria/mamposteria/memoria-rapida", {
      ...auditoriaState.mampo, con_refuerzo: true, con_relleno: true,
    });
  } catch (err) { dev.innerHTML = `<div style="color:#e74c3c;font-size:12px">Error: ${esc(err.message)}</div>`; return; }

  const meta = m.meta || {};
  const advs = Array.isArray(meta.advertencias) ? meta.advertencias : [];
  const banner = `
    <div style="border:1px solid ${meta.cumple_normativa ? "#27ae60" : "#e74c3c"};background:${meta.cumple_normativa ? "#27ae6014" : "#e74c3c14"};border-radius:5px;padding:9px 12px;margin-bottom:12px">
      <div style="font-size:12px;font-weight:700;color:${meta.cumple_normativa ? "#27ae60" : "#e74c3c"}">
        ${meta.cumple_normativa ? "✓ Cumple los mínimos de" : "✗ NO cumple"} ${esc(meta.norma || "")}
      </div>
      ${advs.map(a => `<div style="font-size:11px;color:#e74c3c;margin-top:5px;line-height:1.45">⚠ ${esc(a)}</div>`).join("")}
    </div>`;

  const dev2 = document.createElement("div");
  renderMemoriaGenerica(dev2, m);
  dev.innerHTML = banner;
  dev.appendChild(dev2);
}

function audBindMampoInputs() {
  document.querySelectorAll("#aud-mampo-form input[data-audm]").forEach(inp => {
    inp.addEventListener("input", () => {
      const k = inp.dataset.audm;
      auditoriaState.mampo[k] = inp.value === "" ? null : (isNaN(parseFloat(inp.value)) ? null : parseFloat(inp.value));
      clearTimeout(auditoriaTimer);
      auditoriaTimer = setTimeout(audRecalcMampo, 250);
    });
  });
  document.querySelectorAll("#aud-mampo-form select[data-audm-sel]").forEach(sel => {
    sel.addEventListener("change", () => {
      auditoriaState.mampo[sel.dataset.audmSel] = sel.value;
      audRecalcMampo();
    });
  });
  const chk = document.getElementById("aud-mampo-horiz");
  if (chk) chk.addEventListener("change", () => {
    auditoriaState.mampo.con_refuerzo_horizontal = chk.checked;
    audRecalcMampo();
  });
}

function audRenderMamposteria() {
  const c = document.getElementById("auditoria-content");
  if (!c) return;
  c.innerHTML = `
    <div style="padding:14px 16px;max-width:980px">
      <div style="font-size:11px;color:var(--text-dim);margin-bottom:12px;line-height:1.55">
        Narra <code>services/mamposteria_memoria.py</code> — el takeoff de muro de mampostería reforzada que alimenta
        <code>POST /diseno/{pid}/mamposteria</code> (partidas CSI 04 20 00 · 03 20 00 · 03 30 00).
        <b>Hasta 2026-07-27 este módulo corría ciego</b> con dos constantes mágicas inline sin fórmula ni norma:
        <code>3.5 kg/m²</code> de acero (era <b>+111%</b> respecto de lo que decía su propio comentario, "#4 vertical @0.60") y
        <code>0.023 m³/m²</code> de relleno (el <b>área</b> de una celda usada como volumen por m², sin dividir por el espaciamiento).
        Ahora ambos coeficientes se derivan de geometría real y se verifican contra TMS 402-16 §7.3.2.6.
        <br><b>Nota de norma:</b> ACI 318 no cubre mampostería — el código hermano es TMS 402
        (hasta la ed. 2013 se publicaba como TMS 402/ACI 530/ASCE 5; desde 2016, TMS 402 a secas).
      </div>
      <div id="aud-mampo-form" style="border:1px solid var(--accent);border-radius:5px;padding:9px 12px;margin-bottom:12px;background:var(--surface)">
        <div style="font-size:10px;font-weight:700;color:var(--accent);letter-spacing:.5px;margin-bottom:6px">VARIABLES DE ENTRADA — edita aquí</div>
        <div style="display:flex;gap:26px;flex-wrap:wrap">
          <div>
            ${audMampoNumRow("longitud_m", "Longitud del muro", "m")}
            ${audMampoNumRow("altura_m", "Altura del muro", "m")}
            ${audMampoNumRow("espesor_cm", "Espesor del bloque", "cm")}
          </div>
          <div>
            ${audMampoBarraRow("barra_vertical", "Varilla vertical")}
            ${audMampoNumRow("s_vertical_m", "Espaciamiento vert.", "m", "0.05")}
            ${audMampoBarraRow("barra_horizontal", "Varilla horizontal")}
            ${audMampoNumRow("s_horizontal_m", "Espaciamiento horiz.", "m", "0.05")}
          </div>
          <div>
            ${audMampoNumRow("celda_ancho_cm", "Ancho de celda (vacío = t−5)", "cm")}
            ${audMampoNumRow("celda_largo_cm", "Largo de celda", "cm")}
            ${audMampoNumRow("s_celda_m", "Celdas rellenas (vacío = s_v)", "m", "0.05")}
            <div style="display:flex;align-items:center;gap:6px;padding:3px 0">
              <span style="min-width:150px;font-size:11px;color:var(--text-dim)">Refuerzo horizontal</span>
              <input id="aud-mampo-horiz" type="checkbox" ${auditoriaState.mampo.con_refuerzo_horizontal ? "checked" : ""}/>
              <span style="font-size:10px;color:var(--text-dim)">TMS §7.3.2.6 lo exige</span>
            </div>
          </div>
        </div>
      </div>
      <div id="aud-mampo-dev" style="font-size:14px">cargando…</div>
    </div>`;
  audBindMampoInputs();
  audRecalcMampo();
}

// ── VISTA: Calculos (indirectos de presupuesto) ─────────────────────────────
async function audRenderCalculos() {
  const c = document.getElementById("auditoria-content");
  if (!c) return;
  if (typeof state === "undefined" || !state.activeId) {
    c.innerHTML = `<div style="padding:14px;color:#e67e22;font-size:12px">No hay presupuesto activo. Abre un presupuesto en la pantalla principal y vuelve aquí.</div>`;
    return;
  }
  c.innerHTML = `<div style="padding:14px;color:var(--text-dim);font-size:12px">Cargando…</div>`;
  let m;
  try {
    if (auditoriaState.calculosCache && auditoriaState.calculosCache.pid === state.activeId) {
      m = auditoriaState.calculosCache.memoria;
    } else {
      m = await api("GET", `/auditoria/calculos/${state.activeId}/memoria`);
      auditoriaState.calculosCache = { pid: state.activeId, memoria: m };
    }
  } catch (err) {
    c.innerHTML = `<div style="padding:14px;color:#e74c3c;font-size:12px">Error: ${esc(err.message)}</div>`;
    return;
  }
  const meta = m.meta || {};

  // Banner interactivo GENÉRICO: cualquier paso tipo "check" que traiga
  // `hallazgos` (contrato en services/calculos_memoria.py) se lista aquí como
  // un "problema" clickeable. No es exclusivo del bug de sobrecosto — cuando
  // los 8 módulos ciegos se auditen y narren su propio "⚠ Hallazgo" con
  // `hallazgos`, aparecen aquí solos, sin tocar este JS.
  const problemas = (m.pasos || []).filter(p => p.tipo === "check" && Array.isArray(p.hallazgos) && p.hallazgos.length);
  const problemaItemHtml = (p) => `
    <details style="border:1px solid #f2c94c55;border-radius:4px;background:var(--surface);margin-bottom:6px">
      <summary style="cursor:pointer;padding:7px 10px;font-size:12px;font-weight:700;color:var(--text);display:flex;align-items:center;gap:7px;flex-wrap:wrap">
        <span style="color:#f2c94c">⚠</span> ${esc(p.etiqueta || "")}
        ${typeof p.valor === "number" ? `<span style="margin-left:auto;font-family:monospace;font-size:11px;color:#e74c3c">Δ ${p.valor.toLocaleString("es-HN", { minimumFractionDigits: 2 })} ${esc(p.unidad || "")}</span>` : ""}
      </summary>
      <div style="padding:2px 10px 10px">${audCardHtml(p)}</div>
    </details>`;

  const banner = problemas.length ? `
    <div style="border:1px solid #f2c94c;background:#f2c94c14;border-radius:5px;padding:10px 13px;margin-bottom:14px">
      <div style="font-size:12px;font-weight:700;color:#f2c94c;margin-bottom:8px">
        ⚠ ${problemas.length} problema${problemas.length > 1 ? "s" : ""} detectado${problemas.length > 1 ? "s" : ""} — click para ver la fórmula real y el término exacto que falla
      </div>
      ${problemas.map(problemaItemHtml).join("")}
      <div style="font-size:10px;color:var(--text-dim);margin-top:2px">Esta auditoría <b>expone</b> el comportamiento actual del código — no lo corrige.</div>
    </div>` : "";

  const dev = document.createElement("div");
  const titulo = `<b>${esc(meta.nombre || "")}</b> <span style="color:var(--text-dim);font-size:11px">· ${meta.n_partidas || 0} partidas · ${meta.n_capitulos || 0} capítulos</span>`;
  renderMemoriaGenerica(dev, m, { titulo });

  c.innerHTML = `<div style="padding:14px 16px;max-width:980px">
    <div style="font-size:11px;color:var(--text-dim);margin-bottom:12px;line-height:1.5">
      Narra <code>routers/calculos.py</code> read-only: reproduce la aritmética de <code>/calcular</code> (Vista A) y de <code>/reporte</code> (Vista B) sobre este presupuesto SIN escribir nada en la BD.
    </div>
    ${banner}
  </div>`;
  c.querySelector("div[style*='max-width:980px']").appendChild(dev);
}

// ═══════════════════════════════════════════════════════════════════════════
// TANDA 2026-07-31 — los 7 módulos ciegos restantes.
// Motor GENÉRICO de vistas: cada módulo se declara como data (endpoint +
// campos + intro) y se pinta con renderMemoriaGenerica(). No se duplica el
// renderer, no se reimplementa audCardHtml ni kx().
// ═══════════════════════════════════════════════════════════════════════════
const AUD_CALCS = {
  banco: {
    titulo: "Prorrateo bancario",
    riesgo: "alto",
    intro: `Narra <code>routers/export_pdf.py::_export_pdf_banco</code> — el factor que multiplica
      TODOS los precios unitarios del PDF que sale al banco. <b>Riesgo ALTO:</b> es el único cálculo
      del sistema cuyo resultado sale del taller y llega a un tercero como documento formal, y el
      factor no aparece en ninguna parte del PDF. Expone además el <b>residuo de redondeo</b> (la
      fila TOTAL se fuerza a <code>valor_banco</code>, no a la suma de las filas) y el
      <b>margen implícito</b> sobre el costo directo.
      <br><span style="color:#e74c3c;font-weight:700">⚠ PENDIENTE DE APROBACIÓN DEL DIRECTOR.</span>
      El código es aditivo (no cambia ningún número del PDF), pero por su riesgo no se da por cerrado
      sin revisión humana del diff.`,
    endpoint: "/auditoria/banco/memoria-rapida",
    fields: [
      { k: "total_real",          l: "total_real (Σ partida.total)", u: "L" },
      { k: "valor_banco",         l: "valor_banco exigido",          u: "L" },
      { k: "costo_directo",       l: "costo_directo (sin markup)",   u: "L" },
      { k: "fin_cronograma_dias", l: "fin del cronograma",           u: "días activos" },
      { k: "buffer_dias",         l: "buffer contratiempos",         u: "días activos" },
    ],
    def: { total_real: 1097110.30, valor_banco: 1009341.48, costo_directo: 877688.24,
           fin_cronograma_dias: 120, buffer_dias: 26, moneda: "L" },
    real: { label: "🏦 Presupuesto real (BD)", tipo: "presupuesto",
            url: (id, st) => `/auditoria/banco/${id}/memoria?valor_banco=${encodeURIComponent(st.valor_banco || 0)}`,
            extraNum: { k: "valor_banco", l: "valor_banco exigido por el banco", u: "L" } },
  },
  cantidad: {
    titulo: "Factores de cantidad (takeoff Revit)",
    riesgo: "alto",
    intro: `Narra <code>cantidad = ceil(revit_q) × factor_e × factor_f</code> de
      <code>routers/partidas.py</code>. <b>Riesgo ALTO:</b> define la cantidad que se factura y tiene
      tres comportamientos silenciosos — un <code>factor = 0</code> se convierte en <code>1.0</code>
      (quien teclea 0 esperando anular la partida obtiene la cantidad completa), un factor
      <b>negativo</b> pasa y produce un total que RESTA del presupuesto, y el <code>ceil()</code>
      mueve la cantidad sin mostrarlo. Desde 2026-07-31 <code>PATCH /revit-q</code> y
      <code>/factores</code> devuelven <code>advertencias[]</code> con estos casos.`,
    endpoint: "/auditoria/cantidad/memoria-rapida",
    fields: [
      { k: "revit_q",         l: "revit_q (bruto del modelo)", u: "unidad" },
      { k: "factor_e",        l: "factor_e",                   u: "—" },
      { k: "factor_f",        l: "factor_f",                   u: "—" },
      { k: "precio_unitario", l: "precio unitario",            u: "L" },
    ],
    texts: [{ k: "unidad", l: "unidad", u: "" }],
    def: { revit_q: 12.4, factor_e: 0, factor_f: 1.05, precio_unitario: 850, unidad: "m2" },
    real: { label: "📥 Partida real (BD)", tipo: "partida",
            url: (id) => `/auditoria/cantidad/partida/${id}/memoria` },
  },
  cronograma: {
    titulo: "Cronograma — duración y fase",
    riesgo: "medio",
    intro: `Narra <code>backend/cronograma.py</code>: jornadas-hombre, duración y fase constructiva.
      Lo que corría ciego es la <b>cascada de 4 fuentes</b>
      (<code>TIEMPOS_FIJOS &gt; MANUAL_SPLIT &gt; catálogo V1.2 &gt; SIN_TIEMPO</code>) — una actividad
      que no está en ninguna recibe <b>1 día</b> por defecto y el Gantt la dibuja igual que cualquier
      otra — y los <b>offsets de fase mágicos</b> (0, 3, 8, 22, 29, 50, 80, 120 días) codificados a
      mano por división CSI sin justificación escrita. Los "días" son días ACTIVOS (6/semana), no
      calendario.`,
    endpoint: "/auditoria/cronograma/memoria-rapida",
    fields: [
      { k: "cantidad", l: "cantidad de obra",     u: "unidad" },
      { k: "n_esp",    l: "especialistas (N_esp)", u: "personas", step: "1" },
      { k: "n_ay",     l: "ayudantes (N_ay)",      u: "personas", step: "1" },
    ],
    texts: [
      { k: "clave_csi",      l: "clave CSI", u: "" },
      { k: "unidad",         l: "unidad",    u: "" },
      { k: "capitulo_clave", l: "capítulo (2 díg.)", u: "" },
    ],
    def: { clave_csi: "03 31 13.2", cantidad: 20, unidad: "m3", n_esp: 3, n_ay: 3,
           capitulo_clave: "", descripcion: "" },
    real: { label: "📥 Partida real (BD)", tipo: "partida",
            url: (id) => `/auditoria/cronograma/partida/${id}/memoria` },
  },
  perfil: {
    titulo: "Propiedades de sección de acero",
    riesgo: "medio",
    intro: `Narra <code>perfiles_acero.props_seccion()</code>. Es <b>el gap más traicionero</b>: no
      produce un número visiblemente malo, invalida en silencio memorias que SÍ se ven perfectas.
      <code>calculo_miembro_acero</code> muestra φMn = φ·Fy·Zx paso a paso con LaTeX y referencia
      AISC — impecable — pero ese <code>Zx</code> puede venir de la <b>tabla AISC/CISC exacta</b>, de
      una <b>derivación de 3 rectángulos ~3% conservadora</b> (con geometría de tf/tw imprecisa, que
      el propio repo advierte que da Zx/ry 25-34% bajos) o de la rama <b>HSS</b>. Hasta 2026-07-31 la
      memoria no decía cuál.`,
    endpoint: "/auditoria/perfil/memoria-rapida",
    fields: [{ k: "fy_kgcm2", l: "Fy del acero", u: "kgf/cm²" }],
    selects: [{ k: "perfil", l: "perfil", opts: [] }],   // se llena desde /auditoria/perfil/catalogo
    def: { perfil: "W250X33", fy_kgcm2: 3515 },
  },
  unidades: {
    titulo: "Conversión de unidades ETABS",
    riesgo: "medio",
    intro: `Narra <code>seccion_ficha.factores_unidad()</code>, que aplica un factor a <b>cada</b>
      número de fuerza y momento que entra desde ETABS. Riesgo MEDIO en probabilidad, ALTO en
      consecuencia: una unidad no reconocida (<code>kip</code>, <code>lb</code>, <code>N</code>, un
      typo) cae en <b>kgf sin avisar</b>, y si los datos venían en kN todo el diseño queda
      <b>101.97× fuera de escala</b> de forma uniforme — el tipo de error que se ve consistente y por
      eso no se detecta revisando un resultado suelto.`,
    endpoint: "/auditoria/unidades/memoria-rapida",
    fields: [
      { k: "p_entrada", l: "fuerza de ejemplo",  u: "unidad declarada" },
      { k: "m_entrada", l: "momento de ejemplo", u: "unidad·m" },
    ],
    texts: [{ k: "unidad", l: "unidad declarada", u: "kgf · kg · t · ton · kn" }],
    def: { unidad: "kip", p_entrada: 50000, m_entrada: 12000 },
  },
  predim: {
    titulo: "Predimensionamiento de secciones",
    riesgo: "bajo",
    intro: `Narra <code>calculo_estructural.predimensionar()</code>. El resultado numérico nunca
      estuvo en duda — lo que faltaba era dejar escrito que las dos reglas
      (<code>lado = niveles·10·0.8</code> para columna, <code>h = (L−2b)/10</code> para viga) son
      <b>heurística del despacho, NO ACI 318-19</b>: la norma no predimensiona, verifica. La memoria
      agrega los checks de mínimos sísmicos (§18.6.2.1 viga 25 cm · §18.7.2.1 columna 30 cm) y de
      relación L/h que las reglas no conocen.`,
    endpoint: "/auditoria/predimensionar/memoria-rapida",
    fields: [
      { k: "niveles",          l: "niveles (columna)",  u: "niveles", step: "1" },
      { k: "luz_libre_cm",     l: "luz libre (viga)",   u: "cm" },
      { k: "b_apoyo_cm",       l: "ancho de apoyo",     u: "cm" },
      { k: "recubrimiento_cm", l: "recubrimiento",      u: "cm" },
    ],
    selects: [{ k: "tipo", l: "elemento", opts: ["VIGA", "COLUMNA"] }],
    def: { tipo: "VIGA", niveles: 2, luz_libre_cm: 500, b_apoyo_cm: 30, recubrimiento_cm: 4 },
  },
};

// Vista aceroficha: entrada tabular, no un formulario de escalares → propia.
const AUD_ACERO_DEMO = [
  { frame: "C1", perfil: "W200X36", rol: "",       longitud_mL: 3.5, dc: 0.72, combo: "ENV-2" },
  { frame: "C2", perfil: "W200X36", rol: "Column", longitud_mL: 3.5, dc: 0.88, combo: "ENV-3" },
  { frame: "B1", perfil: "W200X36", rol: "Beam",   longitud_mL: 6.0, dc: 0.91, combo: "ENV-1" },
  { frame: "B2", perfil: "W150X18", rol: "Beam",   longitud_mL: 4.2, dc: 1.14, combo: "ENV-4" },
  { frame: "X9", perfil: "W44X335", rol: "Beam",   longitud_mL: 8.0, dc: 0.40, combo: "ENV-1" },
];

// Estado por módulo (se siembra con `def` la primera vez que se abre).
auditoriaState.calc = {};
auditoriaState.calcSub = {};       // vista -> "calc" | "real"
auditoriaState.calcRealId = {};    // vista -> id de presupuesto/partida elegido
auditoriaState.aceroTexto = JSON.stringify(AUD_ACERO_DEMO, null, 1);
auditoriaState.perfilCatalogo = null;

function audCalcState(v) {
  if (!auditoriaState.calc[v]) auditoriaState.calc[v] = { ...(AUD_CALCS[v].def || {}) };
  return auditoriaState.calc[v];
}

// Banner de advertencias — mismo contrato `meta.advertencias` que mampostería.
function audBannerHtml(meta) {
  const advs = Array.isArray(meta.advertencias) ? meta.advertencias : [];
  const ok = !!meta.cumple_normativa;
  const pend = meta.pendiente_aprobacion_director;
  return `
    <div style="border:1px solid ${ok ? "#27ae60" : "#e74c3c"};background:${ok ? "#27ae6014" : "#e74c3c14"};border-radius:5px;padding:9px 12px;margin-bottom:12px">
      <div style="font-size:12px;font-weight:700;color:${ok ? "#27ae60" : "#e74c3c"}">
        ${ok ? "✓ Sin banderas" : `✗ ${advs.length} bandera${advs.length === 1 ? "" : "s"}`}${meta.norma ? ` · ${esc(meta.norma)}` : ""}
      </div>
      ${advs.map(a => `<div style="font-size:11px;color:#e74c3c;margin-top:5px;line-height:1.45">⚠ ${esc(a)}</div>`).join("")}
      ${pend ? `<div style="font-size:11px;color:#f2c94c;margin-top:7px;font-weight:700;line-height:1.45">⏳ Módulo PENDIENTE DE APROBACIÓN DEL DIRECTOR — implementado y verificado, no cerrado.</div>` : ""}
      ${meta.nota_norma ? `<div style="font-size:10px;color:var(--text-dim);margin-top:7px;line-height:1.5;font-style:italic">${esc(meta.nota_norma)}</div>` : ""}
    </div>`;
}

function audNumRow(v, f) {
  const val = audCalcState(v)[f.k];
  return `<div style="display:flex;align-items:center;gap:6px;padding:3px 0">
    <span style="min-width:170px;font-size:11px;color:var(--text-dim)">${esc(f.l)}</span>
    <input data-audc="${f.k}" type="number" step="${f.step || "any"}" value="${val === null || val === undefined ? "" : val}"
      style="width:120px;background:var(--bg);border:1px solid var(--accent);color:var(--text);padding:3px 6px;border-radius:3px;font-family:monospace;font-weight:600"/>
    <span style="font-size:10px;color:var(--text-dim)">${esc(f.u || "")}</span>
  </div>`;
}

function audTextRow(v, f) {
  const val = audCalcState(v)[f.k];
  return `<div style="display:flex;align-items:center;gap:6px;padding:3px 0">
    <span style="min-width:170px;font-size:11px;color:var(--text-dim)">${esc(f.l)}</span>
    <input data-audct="${f.k}" type="text" value="${esc(String(val === null || val === undefined ? "" : val))}"
      style="width:120px;background:var(--bg);border:1px solid var(--accent);color:var(--text);padding:3px 6px;border-radius:3px;font-family:monospace;font-weight:600"/>
    <span style="font-size:10px;color:var(--text-dim)">${esc(f.u || "")}</span>
  </div>`;
}

function audSelRow(v, f) {
  const val = audCalcState(v)[f.k];
  const opts = (f.opts || []).map(o => {
    const val_ = typeof o === "string" ? o : o.v;
    const lab = typeof o === "string" ? o : o.l;
    return `<option value="${esc(val_)}" ${val_ === val ? "selected" : ""}>${esc(lab)}</option>`;
  }).join("");
  return `<div style="display:flex;align-items:center;gap:6px;padding:3px 0">
    <span style="min-width:170px;font-size:11px;color:var(--text-dim)">${esc(f.l)}</span>
    <select data-audcs="${f.k}" style="width:210px;background:var(--bg);border:1px solid var(--accent);color:var(--text);padding:3px 6px;border-radius:3px;font-family:monospace;font-weight:600">${opts}</select>
  </div>`;
}

async function audRecalcCalc(v) {
  const dev = document.getElementById("aud-calc-dev");
  if (!dev) return;
  const spec = AUD_CALCS[v];
  let m;
  try {
    m = await api("POST", spec.endpoint, { ...audCalcState(v) });
  } catch (err) { dev.innerHTML = `<div style="color:#e74c3c;font-size:12px">Error: ${esc(err.message)}</div>`; return; }
  const sub = document.createElement("div");
  renderMemoriaGenerica(sub, m);
  dev.innerHTML = audBannerHtml(m.meta || {});
  dev.appendChild(sub);
}

function audBindCalcInputs(v) {
  document.querySelectorAll("#aud-calc-form input[data-audc]").forEach(inp => {
    inp.addEventListener("input", () => {
      const n = parseFloat(inp.value);
      audCalcState(v)[inp.dataset.audc] = inp.value === "" ? null : (isNaN(n) ? null : n);
      clearTimeout(auditoriaTimer);
      auditoriaTimer = setTimeout(() => audRecalcCalc(v), 250);
    });
  });
  document.querySelectorAll("#aud-calc-form input[data-audct]").forEach(inp => {
    inp.addEventListener("input", () => {
      audCalcState(v)[inp.dataset.audct] = inp.value;
      clearTimeout(auditoriaTimer);
      auditoriaTimer = setTimeout(() => audRecalcCalc(v), 350);
    });
  });
  document.querySelectorAll("#aud-calc-form select[data-audcs]").forEach(sel => {
    sel.addEventListener("change", () => {
      audCalcState(v)[sel.dataset.audcs] = sel.value;
      audRecalcCalc(v);
    });
  });
}

// ── Sub-vista "real (BD)": presupuesto activo o partida del presupuesto activo
function audPresupuestosDisponibles() {
  if (typeof state === "undefined" || !state.activeId) return [];
  return [{ id: state.activeId, label: (state.activeData && state.activeData.nombre) || state.activeId }];
}

async function audRenderCalcReal(v) {
  const wrap = document.getElementById("aud-calc-real-wrap");
  if (!wrap) return;
  const spec = AUD_CALCS[v], real = spec.real;
  const items = real.tipo === "partida"
    ? audPartidasDisponibles().map(p => ({ id: p.id, label: `${p.clave_csi} — ${p.descripcion} (${p.capitulo})` }))
    : audPresupuestosDisponibles();
  if (!items.length) {
    wrap.innerHTML = `<div style="color:#e67e22;font-size:12px;padding:10px">No hay presupuesto activo${real.tipo === "partida" ? " (o no tiene partidas)" : ""}. Abre un presupuesto en la pantalla principal y vuelve aquí.</div>`;
    return;
  }
  const sel0 = auditoriaState.calcRealId[v] || "";
  const opts = items.map(i => `<option value="${esc(i.id)}" ${i.id === sel0 ? "selected" : ""}>${esc(i.label)}</option>`).join("");
  wrap.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap">
      <span style="font-size:11px;color:var(--text-dim)">${real.tipo === "partida" ? "Partida real:" : "Presupuesto activo:"}</span>
      <select id="aud-calc-real-sel" style="flex:1;min-width:280px;max-width:520px;background:var(--surface2);border:1px solid var(--accent);color:var(--text);padding:4px 8px;border-radius:3px;font-size:12px">
        <option value="">— elige —</option>${opts}
      </select>
      ${real.extraNum ? `<span style="font-size:11px;color:var(--text-dim)">${esc(real.extraNum.l)}</span>
        <input id="aud-calc-real-extra" type="number" step="any" value="${audCalcState(v)[real.extraNum.k]}"
          style="width:140px;background:var(--bg);border:1px solid var(--accent);color:var(--text);padding:3px 6px;border-radius:3px;font-family:monospace;font-weight:600"/>
        <span style="font-size:10px;color:var(--text-dim)">${esc(real.extraNum.u || "")}</span>` : ""}
    </div>
    <div id="aud-calc-real-dev" style="font-size:14px"></div>`;

  const sel = document.getElementById("aud-calc-real-sel");
  const load = async () => {
    auditoriaState.calcRealId[v] = sel.value || null;
    const dev = document.getElementById("aud-calc-real-dev");
    if (!sel.value) { dev.innerHTML = ""; return; }
    dev.innerHTML = `<div style="color:var(--text-dim);font-size:12px">Cargando…</div>`;
    try {
      const m = await api("GET", real.url(sel.value, audCalcState(v)));
      const meta = m.meta || {};
      const titulo = meta.clave_csi
        ? `<span style="font-family:monospace;color:var(--accent)">${esc(meta.clave_csi)}</span> — ${esc(meta.descripcion || "")}`
        : `<b>${esc(meta.presupuesto_nombre || "")}</b>${meta.n_partidas ? ` <span style="color:var(--text-dim);font-size:11px">· ${meta.n_partidas} partidas</span>` : ""}`;
      const sub = document.createElement("div");
      renderMemoriaGenerica(sub, m, { titulo });
      dev.innerHTML = audBannerHtml(meta);
      dev.appendChild(sub);
    } catch (err) {
      dev.innerHTML = `<div style="color:#e74c3c;font-size:12px">Error: ${esc(err.message)}</div>`;
    }
  };
  sel.addEventListener("change", load);
  const extra = document.getElementById("aud-calc-real-extra");
  if (extra) extra.addEventListener("input", () => {
    const n = parseFloat(extra.value);
    audCalcState(v)[real.extraNum.k] = isNaN(n) ? 0 : n;
    clearTimeout(auditoriaTimer);
    auditoriaTimer = setTimeout(load, 350);
  });
  if (sel.value) load();
}

async function audRenderCalc(v) {
  const c = document.getElementById("auditoria-content");
  if (!c) return;
  const spec = AUD_CALCS[v];
  if (!spec) return audRenderResumen();

  // El catálogo de perfiles se pide una vez y llena el <select> del módulo perfil.
  if (v === "perfil" && !auditoriaState.perfilCatalogo) {
    try {
      const cat = await api("GET", "/auditoria/perfil/catalogo");
      auditoriaState.perfilCatalogo = cat;
      spec.selects[0].opts = (cat.perfiles || []).map(p => ({ v: p.perfil, l: `${p.perfil}  ·  ${p.fuente}` }));
    } catch (err) { spec.selects[0].opts = [{ v: "W200X36", l: "W200X36" }]; }
  }

  const st = audCalcState(v);
  const sub = auditoriaState.calcSub[v] || "calc";
  const RIESGO_COL = { alto: "#e74c3c", medio: "#f2c94c", bajo: "#8a94a6" };
  const col = RIESGO_COL[spec.riesgo] || "#8a94a6";

  c.innerHTML = `
    <div style="padding:14px 16px;max-width:1000px">
      <div style="display:flex;align-items:baseline;gap:9px;margin-bottom:9px;flex-wrap:wrap">
        <span style="font-size:14px;font-weight:700;color:var(--text)">${esc(spec.titulo)}</span>
        <span style="font-size:9px;font-weight:700;padding:1px 8px;border-radius:8px;background:${col}22;color:${col};border:1px solid ${col}">RIESGO ${esc(spec.riesgo.toUpperCase())}</span>
      </div>
      <div style="font-size:11px;color:var(--text-dim);margin-bottom:12px;line-height:1.55">${spec.intro}</div>
      ${spec.real ? `<div style="display:flex;gap:8px;margin-bottom:12px">
        <button class="aud-calc-sub" data-sub="calc" style="font-size:12px;padding:5px 12px;border-radius:14px;cursor:pointer;border:1px solid ${sub === "calc" ? "var(--accent)" : "var(--border)"};background:${sub === "calc" ? "var(--accent)" : "var(--surface2)"};color:${sub === "calc" ? "#1a1a1a" : "var(--text)"};font-weight:700">🧮 Calculadora libre</button>
        <button class="aud-calc-sub" data-sub="real" style="font-size:12px;padding:5px 12px;border-radius:14px;cursor:pointer;border:1px solid ${sub === "real" ? "var(--accent)" : "var(--border)"};background:${sub === "real" ? "var(--accent)" : "var(--surface2)"};color:${sub === "real" ? "#1a1a1a" : "var(--text)"};font-weight:700">${esc(spec.real.label)}</button>
      </div>` : ""}
      ${sub === "calc" ? `
        <div id="aud-calc-form" style="border:1px solid var(--accent);border-radius:5px;padding:9px 12px;margin-bottom:12px;background:var(--surface)">
          <div style="font-size:10px;font-weight:700;color:var(--accent);letter-spacing:.5px;margin-bottom:6px">VARIABLES DE ENTRADA — edita aquí</div>
          <div style="display:flex;gap:26px;flex-wrap:wrap">
            <div>${(spec.selects || []).map(f => audSelRow(v, f)).join("")}${(spec.texts || []).map(f => audTextRow(v, f)).join("")}</div>
            <div>${(spec.fields || []).map(f => audNumRow(v, f)).join("")}</div>
          </div>
        </div>
        <div id="aud-calc-dev" style="font-size:14px">cargando…</div>
      ` : `<div id="aud-calc-real-wrap"></div>`}
    </div>`;

  c.querySelectorAll(".aud-calc-sub").forEach(b => b.addEventListener("click", () => {
    auditoriaState.calcSub[v] = b.dataset.sub; audRenderCalc(v);
  }));
  if (sub === "calc") { audBindCalcInputs(v); audRecalcCalc(v); }
  else audRenderCalcReal(v);
}

// ── VISTA: Acero por ficha Div 05 (entrada tabular) ──────────────────────────
async function audRecalcAceroFicha() {
  const dev = document.getElementById("aud-acero-dev");
  if (!dev) return;
  let miembros;
  try {
    miembros = JSON.parse(auditoriaState.aceroTexto);
    if (!Array.isArray(miembros)) throw new Error("Se espera una lista de miembros.");
  } catch (err) {
    dev.innerHTML = `<div style="color:#e74c3c;font-size:12px">JSON inválido: ${esc(err.message)}</div>`;
    return;
  }
  let m;
  try {
    m = await api("POST", "/auditoria/acero-ficha/memoria-rapida", { miembros });
  } catch (err) { dev.innerHTML = `<div style="color:#e74c3c;font-size:12px">Error: ${esc(err.message)}</div>`; return; }
  const sub = document.createElement("div");
  renderMemoriaGenerica(sub, m);
  const r = m.resultado || {};
  const tabla = (r.por_ficha || []).length ? `
    <div style="overflow-x:auto;margin-bottom:12px">
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="text-align:left;border-bottom:1px solid var(--border);color:var(--text-dim);font-size:10px;text-transform:uppercase">
          <th style="padding:4px 10px">Ficha</th><th style="padding:4px 10px">Perfil</th><th style="padding:4px 10px">Rol</th>
          <th style="padding:4px 10px;text-align:right">Miembros</th><th style="padding:4px 10px;text-align:right">Longitud mL</th>
          <th style="padding:4px 10px;text-align:right">D/C máx</th><th style="padding:4px 10px">Combo</th>
        </tr></thead>
        <tbody>${r.por_ficha.map(f => `<tr>
          <td style="padding:5px 10px;font-family:monospace;font-weight:700">${esc(f.ficha)}</td>
          <td style="padding:5px 10px;font-family:monospace">${esc(f.perfil)}</td>
          <td style="padding:5px 10px">${esc(f.rol)}</td>
          <td style="padding:5px 10px;text-align:right">${f.n_miembros}</td>
          <td style="padding:5px 10px;text-align:right">${f.longitud_total_mL}</td>
          <td style="padding:5px 10px;text-align:right;color:${f.dc_max > 1 ? "#e74c3c" : "var(--text)"};font-weight:700">${f.dc_max === null ? "—" : f.dc_max}</td>
          <td style="padding:5px 10px;font-size:11px;color:var(--text-dim)">${esc(f.combo_gobernante || "—")}</td>
        </tr>`).join("")}</tbody>
      </table>
    </div>` : "";
  dev.innerHTML = audBannerHtml(m.meta || {}) + tabla;
  dev.appendChild(sub);
}

function audRenderAceroFicha() {
  const c = document.getElementById("auditoria-content");
  if (!c) return;
  c.innerHTML = `
    <div style="padding:14px 16px;max-width:1000px">
      <div style="display:flex;align-items:baseline;gap:9px;margin-bottom:9px;flex-wrap:wrap">
        <span style="font-size:14px;font-weight:700;color:var(--text)">Agregación de acero por ficha Div 05</span>
        <span style="font-size:9px;font-weight:700;padding:1px 8px;border-radius:8px;background:#8a94a622;color:#8a94a6;border:1px solid #8a94a6">RIESGO BAJO · ALTA COMPLEJIDAD</span>
      </div>
      <div style="font-size:11px;color:var(--text-dim);margin-bottom:12px;line-height:1.55">
        Narra <code>acero_ficha.agregar_por_ficha()</code>. No es una fórmula: es una cadena de decisiones
        donde cada paso descarta información y ninguno se ve. <b>(1)</b> perfil dual sin rol ⇒ se asume
        <b>COLUMNA</b> — mapea a otra ficha, con otros insumos y otro costo (el motor genera el aviso desde
        siempre, pero <code>avisos[]</code> no se renderizaba en ningún lado). <b>(2)</b> la envolvente D/C
        reporta el peor miembro y descarta los otros N−1 y sus combos. <b>(3)</b> los perfiles fuera de
        <code>FICHAS_ACERO</code> no entran a ninguna partida: acero real del modelo que no se presupuesta.
      </div>
      <div style="border:1px solid var(--accent);border-radius:5px;padding:9px 12px;margin-bottom:12px;background:var(--surface)">
        <div style="font-size:10px;font-weight:700;color:var(--accent);letter-spacing:.5px;margin-bottom:6px">MIEMBROS (JSON — igual que la salida del parser de ETABS)</div>
        <textarea id="aud-acero-txt" spellcheck="false" style="width:100%;height:190px;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:7px 9px;border-radius:3px;font-family:monospace;font-size:11px;line-height:1.5">${esc(auditoriaState.aceroTexto)}</textarea>
        <div style="font-size:10px;color:var(--text-dim);margin-top:5px">Campos: <code>frame · perfil · rol · longitud_mL · dc · combo</code>. Dejá <code>rol</code> vacío en un perfil dual para ver la regla silenciosa en acción.</div>
      </div>
      <div id="aud-acero-dev" style="font-size:14px">cargando…</div>
    </div>`;
  const ta = document.getElementById("aud-acero-txt");
  ta.addEventListener("input", () => {
    auditoriaState.aceroTexto = ta.value;
    clearTimeout(auditoriaTimer);
    auditoriaTimer = setTimeout(audRecalcAceroFicha, 400);
  });
  audRecalcAceroFicha();
}

// ── Shell / router de vistas ─────────────────────────────────────────────────
function renderAuditoria() {
  const panel = document.getElementById("auditoria-view");
  if (!panel) return;
  const bar = document.getElementById("auditoria-vista-sel");
  if (bar) bar.value = auditoriaState.vista;
  const v = auditoriaState.vista;
  if (v === "pricing") audRenderPricing();
  else if (v === "calculos") audRenderCalculos();
  else if (v === "mamposteria") audRenderMamposteria();
  else if (v === "aceroficha") audRenderAceroFicha();
  else if (AUD_CALCS[v]) audRenderCalc(v);          // banco · cantidad · cronograma · perfil · unidades · predim
  else audRenderResumen();
}

function initAuditoriaDropdown() {
  const sel = document.getElementById("auditoria-vista-sel");
  if (!sel) return;
  sel.addEventListener("change", () => { auditoriaState.vista = sel.value; renderAuditoria(); });
}

document.addEventListener("DOMContentLoaded", initAuditoriaDropdown);
