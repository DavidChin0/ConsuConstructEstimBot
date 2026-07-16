// core.js — Nucleo EstimaStruct: config API, estado global, utilidades, bus pub/sub.
// Cargado por index.html ANTES de app.js (scope global clasico compartido entre <script>).

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
  auditMode: false,
  moMode: false,
  unidades: [],
  modo: localStorage.getItem("estimastruct.modo") || "cliente",
  templateVersion: (() => {
    const saved = localStorage.getItem("estimastruct.template-version");
    return saved && ["v1.0", "v1.1", "v1.2"].includes(saved) ? saved : "v1.2";
  })(),
};

let templateCatalog = {
  "v1.0": { fichas_total: null },
  "v1.1": { fichas_total: null },
  "v1.2": { fichas_total: null },
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
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#x27;");
}
async function api(method, path, body = null, { timeout = 15000 } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  const opts = { method, headers: { "Content-Type": "application/json" }, signal: ctrl.signal };
  if (body) opts.body = JSON.stringify(body);
  let res;
  try {
    res = await fetch(API + path, opts);
  } catch (err) {
    if (err.name === "AbortError") throw new Error(`Timeout (${timeout / 1000}s) sin respuesta del backend en ${path}`);
    throw new Error(`No se pudo conectar con el backend en ${API}${path}: ${err.message || err}`);
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    const detail = err?.detail || err?.message || res.statusText;
    throw new Error(`HTTP ${res.status} en ${path}: ${detail}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

// --- BUS pub/sub (prerequisito modularizacion) ---
const bus = {
  _h: {},
  on(ev, fn) { (this._h[ev] = this._h[ev] || []).push(fn); return () => this.off(ev, fn); },
  off(ev, fn) { this._h[ev] = (this._h[ev] || []).filter(f => f !== fn); },
  emit(ev, data) { (this._h[ev] || []).forEach(fn => { try { fn(data); } catch (e) { console.error('bus:' + ev, e); } }); },
};
