// db-backup.js — Copia de seguridad de la BD viva: botones "📦 Exportar copia BD (ZIP)"
// y "📥 Importar BD (ZIP)" en la zona "Bases de Datos" (solo modo desarrollador,
// la zona entera ya esta gateada por applyModoUI()).
// Cargado DESPUES de core.js/app.js/bases-drawer.js. Usa API/esc/bus de core.js
// (scope global clasico compartido entre <script>, mismo patron que el resto).
//
// Backend: backend/routers/db_backup.py — GET /db/export-zip, POST /db/import-zip.
// Doc completa del flujo (schema, PRAGMAs, requisitos de import, advertencias):
// docs/mapa_sql_inyeccion_bd.md.

let dbImportState = { file: null };

function initDbBackup() {
  document.getElementById("btn-db-export-zip")?.addEventListener("click", downloadDbExportZip);

  const fileInput = document.getElementById("db-import-zip-input");
  document.getElementById("btn-db-import-zip")?.addEventListener("click", () => {
    if (fileInput) fileInput.value = "";
    fileInput?.click();
  });
  fileInput?.addEventListener("change", () => {
    const f = fileInput.files && fileInput.files[0];
    if (f) openModalDbImport(f);
  });

  const modal = document.getElementById("modal-db-import");
  const chk = document.getElementById("db-import-confirm-check");
  const btnOk = document.getElementById("modal-db-import-ok");

  document.getElementById("modal-db-import-cancel")?.addEventListener("click", () => {
    closeModalDbImport();
  });
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) closeModalDbImport();
  });
  chk?.addEventListener("change", () => { btnOk.disabled = !chk.checked; });
  btnOk?.addEventListener("click", runDbImportZip);
}

// --- EXPORT ---
function downloadDbExportZip() {
  // Mismo patron que el resto de descargas del app (export-pdf, export-db, etc.)
  window.open(`${API}/db/export-zip`, "_blank");
}

// --- IMPORT (doble confirmacion: checkbox + boton) ---
function openModalDbImport(file) {
  dbImportState.file = file;
  const modal = document.getElementById("modal-db-import");
  document.getElementById("modal-db-import-file").textContent =
    `Archivo seleccionado: ${file.name} (${(file.size / 1024).toFixed(0)} KB)`;

  const result = document.getElementById("modal-db-import-result");
  result.classList.add("hidden");
  result.textContent = "";
  result.style.color = "";

  const chk = document.getElementById("db-import-confirm-check");
  chk.checked = false;
  chk.disabled = false;

  const btnOk = document.getElementById("modal-db-import-ok");
  btnOk.disabled = true;
  btnOk.textContent = "Importar y reemplazar";

  modal.classList.remove("hidden");
}

function closeModalDbImport() {
  document.getElementById("modal-db-import").classList.add("hidden");
  const fileInput = document.getElementById("db-import-zip-input");
  if (fileInput) fileInput.value = "";
  dbImportState.file = null;
}

async function runDbImportZip() {
  const file = dbImportState.file;
  if (!file) return;

  const chk = document.getElementById("db-import-confirm-check");
  const btnOk = document.getElementById("modal-db-import-ok");
  const resultBox = document.getElementById("modal-db-import-result");

  btnOk.disabled = true;
  chk.disabled = true;
  btnOk.textContent = "Importando...";
  resultBox.classList.add("hidden");
  resultBox.style.color = "";

  const fd = new FormData();
  fd.append("file", file, file.name);

  try {
    const res = await fetch(`${API}/db/import-zip?confirm=true`, { method: "POST", body: fd });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error(data?.message || data?.detail || res.statusText);
    }

    const tablas = Object.keys(data.counts_after || {});
    const filas = tablas.map(t => {
      const antes = data.counts_before?.[t];
      const despues = data.counts_after[t];
      return `  ${t.padEnd(22)} ${String(antes ?? "—").padStart(6)} -> ${String(despues).padStart(6)}`;
    }).join("\n");

    resultBox.classList.remove("hidden");
    resultBox.textContent =
      `Importación OK — BD reemplazada.\n` +
      `Backup previo: ${data.backup_pre_import}\n` +
      `Alembic: ${data.alembic_version || "—"}\n\n` +
      `Tabla                     antes -> después\n${filas}`;

    btnOk.textContent = "Hecho";
    if (typeof logChange === "function") {
      logChange("BD", "Import ZIP", { archivo: file.name, backup: data.backup_pre_import });
    }
    setTimeout(closeModalDbImport, 5000);
  } catch (err) {
    resultBox.classList.remove("hidden");
    resultBox.style.color = "#e74c3c";
    resultBox.textContent = "Error: " + (err.message || err);
    btnOk.disabled = false;
    chk.disabled = false;
    btnOk.textContent = "Importar y reemplazar";
  }
}
