# 🔧 Troubleshooting — Menú Opciones no aparece

**Fecha:** 26 abril 2026  
**Problema:** La opción "⚙ Opciones" no aparece en el menú "⚙ Pasos"

---

## ✅ VERIFICACIÓN CHECKLIST

### 1️⃣ Verificar que estés en MODO DESARROLLADOR
- [ ] Arriba a la derecha dice: 🛠 **Desarrollador** (NO 👤 Cliente)
- [ ] Si dice "👤 Cliente", haz clic para cambiar
- [ ] Si no aparece el botón modo, carga una obra primero

**Ubicación del botón:**
```
[ESTIMASTRUCT] [Obra activa] [Totales] [Actualizar] [👤 Cliente / 🛠 Desarrollador] [⚙ Pasos ▾] [⬇ Exportar ▾]
```

---

### 2️⃣ Verificar que el menú "Pasos" esté visible
- [ ] Haz clic en: **⚙ Pasos ▾**
- [ ] Debería mostrar 3 opciones:
  1. **⚙ Opciones** ← NUEVA (debería estar aquí)
  2. Paso 2 — Generar Keynotes
  3. Paso 4 — Actualizar Cantidades (RevitQ)

---

### 3️⃣ Limpiar Cache del Navegador

**Si el menú NO aparece, el problema es casi seguramente CACHE:**

#### Chrome/Edge:
1. Presiona: `Ctrl + Shift + Delete`
2. Selecciona:
   - ✓ Cookies y datos de sitios web
   - ✓ Imágenes y archivos en caché
3. Rango: "Todo el tiempo"
4. Haz clic: "Borrar datos"
5. Recarga: `Ctrl + F5` (hard refresh)

#### Firefox:
1. Presiona: `Ctrl + Shift + Delete`
2. Selecciona: "Todo"
3. Haz clic: "Limpiar ahora"
4. Recarga: `Ctrl + Shift + R`

#### Safari:
1. Menú: Desarrollador → Vaciar cachés
2. Recarga: `Cmd + Shift + R`

---

### 4️⃣ Verificar en Consola del Navegador

1. Presiona: `F12` (abre Developer Tools)
2. Ve a: **Console** tab
3. Busca errores en rojo (debería estar limpia)
4. Ejecuta este comando:
```javascript
console.log("state.templateVersion:", state.templateVersion);
console.log("Modal:", document.getElementById("modal-template-version"));
console.log("Botón opciones:", document.querySelector('[data-step="opciones"]'));
```

**Resultado esperado:**
```
state.templateVersion: v1.0
Modal: <div id="modal-template-version" class="modal-overlay hidden">...</div>
Botón opciones: <button class="dev-menu-item" data-step="opciones">⚙ Opciones</button>
```

Si alguno dice `null`, hay un problema en el HTML.

---

### 5️⃣ Verificar archivos modificados

**Archivo:** `frontend/index.html`
- Búsqueda: `<button class="dev-menu-item" data-step="opciones">`
- Debería encontrarse en línea ~32

**Archivo:** `frontend/js/app.js`
- Búsqueda: `function initModalTemplateVersion()`
- Debería encontrarse en línea ~1140

Si no están, los cambios no se guardaron.

---

### 6️⃣ Verificar con Comandos

```bash
# Verificar que el botón está en HTML
grep -n 'data-step="opciones"' frontend/index.html

# Resultado esperado:
# 32:      <button class="dev-menu-item" data-step="opciones">⚙ Opciones</button>

# Verificar que la función está en JS
grep -n 'initModalTemplateVersion' frontend/js/app.js

# Resultado esperado:
# 71:  initModalTemplateVersion();
# 1140:function initModalTemplateVersion() {
```

---

## 🐛 SI EL PROBLEMA PERSISTE

### Opción A: Revertir y Rehacer
```bash
# Ir a carpeta frontend
cd D:\OneDrive\Bots\Estimacion\frontend

# Ver cambios recientes
git diff index.html
git diff js/app.js

# Si quieres revertir y empezar de nuevo:
git checkout -- index.html js/app.js
```

Luego seguir las instrucciones de IMPLEMENTACIÓN nuevamente.

### Opción B: Verificación Manual

Abre `index.html` en editor de texto y busca:
1. ¿Existe `<div id="modal-template-version"`? (línea ~261)
2. ¿Existe `<button class="dev-menu-item" data-step="opciones">`? (línea ~32)

Abre `app.js` en editor de texto y busca:
1. ¿Existe `function initModalTemplateVersion()`? (línea ~1140)
2. ¿Existe `openModalTemplateVersionDialog()`? (línea ~1179)
3. ¿Existe `initModalTemplateVersion();` en DOMContentLoaded? (línea ~71)
4. ¿Existe `if (step === "opciones")` en initDevMenu? (línea ~319)

Si alguno NO existe, los cambios no se guardaron correctamente.

---

## ✨ VERIFICACIÓN FINAL

Después de hacer Ctrl+F5 (hard refresh), el menú debería verse así:

```
⚙ Pasos ▾
├─ ⚙ Opciones ← NUEVA (aquí)
├─ ─────────────────── (línea divisoria)
├─ Paso 2 — Generar Keynotes
└─ Paso 4 — Actualizar Cantidades (RevitQ)
```

Si ves esto, ¡todo está funcionando! 🎉

---

## 📋 RESUMEN DE CAMBIOS (para verificación manual)

### En `index.html`:

**Línea ~32 (en dev-menu):**
```html
<button class="dev-menu-item" data-step="opciones">⚙ Opciones</button>
<hr style="margin:4px 0;border:none;border-top:1px solid var(--border)"/>
```

**Línea ~261 (nuevo modal):**
```html
<!-- MODAL: SELECCIONAR VERSION TEMPLATE -->
<div id="modal-template-version" class="modal-overlay hidden">
  <!-- ... contenido del modal ... -->
</div>
```

### En `app.js`:

**Línea ~71 (en DOMContentLoaded):**
```javascript
initModalTemplateVersion();
```

**Línea ~319 (en initDevMenu):**
```javascript
if (step === "opciones") openModalTemplateVersionDialog();
```

**Línea ~1140 (nuevas funciones):**
```javascript
function initModalTemplateVersion() { ... }

function openModalTemplateVersionDialog() { ... }

function updateTemplateDesc() { ... }
```

---

**Si después de Ctrl+F5 sigue sin aparecer, reporta en console:**
- ¿Qué dice `console.log("Modal:", document.getElementById("modal-template-version"))`?
- ¿Qué dice `console.log("Botón:", document.querySelector('[data-step="opciones"]'))`?

Eso nos dirá dónde está el problema exacto.
