# 🛠️ Scripts Utilidades — ESTIMASTRUCT

**Ubicación:** `D:\OneDrive\Bots\Estimacion\scripts_utils\`  
**Propósito:** Scripts reutilizables para operaciones comunes de mantenimiento y procesamiento de datos  
**Crear:** 26 abril 2026

---

## 📋 SCRIPTS DISPONIBLES

### 1. `migrate_all_dbs.py` — Migración Base de Datos

**Propósito:** Agregar nueva columna a tabla `config_presupuesto`

**Uso:**
```powershell
D:\LLM\python\python.exe scripts_utils/migrate_all_dbs.py
```

**Qué hace:**
- Busca todas las BDs en `backend/`
- Verifica si tabla `config_presupuesto` existe
- Agrega columna `template_version` si no existe
- Default: `'v1.0'`

**Cuándo usar:**
- Al agregar nuevo campo a `ConfigPresupuesto` en `models.py`
- Cuando actualizas modelos y necesitas sincronizar BD existentes

**Resultado:**
```
[OK] Connected: estimacion.db
[OK] template_version already exists
[ADD] Adding template_version column...
[OK] Column added successfully
```

---

### 2. `merge_v11.py` — Merge V1.1 con V1.0

**Propósito:** Combinar fichas actualizadas (V1.1) con fichas base (V1.0)

**Uso:**
```powershell
D:\LLM\python\python.exe scripts_utils/merge_v11.py
```

**Qué hace:**
- Lee `fichas_v1.0.json` (277 fichas)
- Lee `fichas_v1.1.json` (40 fichas actualizadas)
- Crea V1.1 merged: 40 actualizadas + fichas de V1.0 que no están en V1.1
- Guarda en `v1.1/fichas/fichas_v1.1.json`

**Cuándo usar:**
- Cuando actualices "Fichas revisadas" y solo tengas algunas fichas nuevas
- Para asegurar que V1.1 sea completo (no vacío)

**Antes/Después:**
```
ANTES:
  V1.0: 277 fichas
  V1.1: 40 fichas (vacío en frontend)

DESPUÉS:
  V1.0: 277 fichas
  V1.1: 268 fichas (completo)
```

---

### 3. `clean_unk_fichas.py` — Limpiar Fichas Inválidas

**Propósito:** Remover fichas con códigos inválidos (UNK-*)

**Uso:**
```powershell
D:\LLM\python\python.exe scripts_utils/clean_unk_fichas.py
```

**Qué hace:**
- Lee `fichas_v1.1.json`
- Identifica fichas con código `UNK-*` (errores de importación)
- Remueve fichas inválidas
- Regenera insumos desde fichas limpias
- Guarda versión limpia

**Cuándo usar:**
- Después de importar Excel con errores
- Cuando ves fichas con código "UNK-87", "UNK-109", etc.

**Antes/Después:**
```
ANTES:
  V1.1: 275 fichas (7 inválidas)

DESPUÉS:
  V1.1: 268 fichas (limpias)
```

---

### 4. `regenerate_v11_insumos.py` — Regenerar Insumos V1.1

**Propósito:** Extraer insumos únicos de todas las fichas V1.1

**Uso:**
```powershell
D:\LLM\python\python.exe scripts_utils/regenerate_v11_insumos.py
```

**Qué hace:**
- Lee `fichas_v1.1.json`
- Extrae todos los insumos de cada ficha
- Elimina duplicados (por código)
- Guarda en `v1.1/insumos/insumos_v1.1.json`

**Cuándo usar:**
- Después de merge de V1.1
- Después de limpiar fichas inválidas
- Cuando agregas/modificas insumos en fichas

**Resultado:**
```
V1.1: 268 fichas
Total insumos: 95 únicos
Saved: insumos_v1.1.json
```

---

### 5. `generate_csvs.py` — Generar CSVs de Referencia

**Propósito:** Crear archivos CSV legibles de fichas e insumos

**Uso:**
```powershell
D:\LLM\python\python.exe scripts_utils/generate_csvs.py
```

**Qué hace:**
- Lee JSON de fichas (V1.0 y V1.1)
- Lee JSON de insumos (V1.0 y V1.1)
- Genera CSVs con formato tabla
- Útil para revisar en Excel o editor de texto

**Cuándo usar:**
- Después de cualquier cambio en fichas/insumos
- Para verificar datos en formato legible
- Para comparar versiones

**Genera:**
```
✓ fichas_v1.0.csv (277 fichas)
✓ fichas_v1.1.csv (33 fichas)
✓ insumos_v1.0.csv (146 insumos)
✓ insumos_v1.1.csv (95 insumos)
```

---

### 6. `fix_v11_only_updated.py` — Restaurar V1.1 a Fichas Actualizadas

**Propósito:** Restaurar V1.1 a SOLO las fichas actualizadas (no merged con V1.0)

**Uso:**
```powershell
D:\LLM\python\python.exe scripts_utils/fix_v11_only_updated.py
```

**Qué hace:**
- Lee V1.1 actual (posiblemente merged con V1.0)
- Filtra SOLO los códigos que fueron actualizados
- Elimina todas las demás (fichas duplicadas de V1.0)
- Regenera insumos desde las fichas filtradas
- Guarda V1.1 "limpio"

**Cuándo usar:**
- Cuando V1.1 accidentalmente tiene las mismas fichas que V1.0
- Después de un merge fallido
- Para asegurar que V1.1 sea diferente (solo actualizadas)

**Resultado esperado:**
```
V1.0: 277 fichas (original)
V1.1: 33 fichas (solo actualizadas)
```

---

## 🔄 FLUJO TÍPICO DE USO

**Escenario:** Importar nuevas fichas actualizadas

```
1. Obtener "Fichas revisadas DDMMYY.xlsx"
   ↓
2. Ejecutar: clean_unk_fichas.py
   → Limpiar fichas inválidas (UNK-*)
   ↓
3. Ejecutar: fix_v11_only_updated.py
   → Filtrar SOLO fichas actualizadas
   → Eliminar fichas duplicadas de V1.0
   ↓
4. Ejecutar: generate_csvs.py
   → Generar CSVs para verificar
   ↓
5. Revisar CSVs en Excel
   → V1.0 debe tener 277 fichas
   → V1.1 debe tener ~33 fichas (solo actualizadas)
   ↓
6. Si todo OK → Desplegar (reiniciar backend)
   Si hay problemas → Ajustar y repetir
```

**Notas:**
- NO hacer `merge_v11.py` si quieres V1.1 diferente a V1.0
- `fix_v11_only_updated.py` es el que restaura V1.1 correctamente

---

## 🛠️ CONFIGURACIÓN

### Python Version
```powershell
D:\LLM\python\python.exe --version
# Debe mostrar: Python 3.x.x
```

### Paths Hardcodeados
Algunos scripts asumen rutas específicas:

```python
base_path = r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT"
db_path = r"D:\OneDrive\Bots\Estimacion\backend\estimacion.db"
```

Si cambias carpetas, actualizar en scripts.

---

## 🧪 TESTING

### Antes de ejecutar cualquier script:

```powershell
# 1. Verificar Python
D:\LLM\python\python.exe --version

# 2. Verificar rutas existen
Test-Path "D:\OneDrive\Bots\Estimacion\backend\"
Test-Path "D:\OneDrive\Bots\Estimacion\development\Template2_Updated\"

# 3. Backup de datos
Copy-Item "fichas_v1.0.json" "fichas_v1.0.json.backup"
Copy-Item "fichas_v1.1.json" "fichas_v1.1.json.backup"

# 4. Ejecutar script
D:\LLM\python\python.exe scripts_utils/tu_script.py

# 5. Verificar resultados
Get-ChildItem "fichas_v1.1.json" | Select-Object LastWriteTime
```

---

## 📝 NOTAS IMPORTANTES

1. **Siempre hacer backup** antes de ejecutar scripts que modifiquen datos
2. **Usar `D:\LLM\python\python.exe`** - evita problemas de codificación
3. **Ejecutar desde carpeta raíz** de Estimacion (o usar rutas absolutas)
4. **Verificar resultados** - revisar CSVs después de cambios

---

## 🚀 AGREGAR NUEVOS SCRIPTS

Cuando crees nuevos scripts reutilizables:

1. Guardar en `scripts_utils/`
2. Nombre descriptivo: `accion_recurso.py`
3. Agregar docstring al inicio:
   ```python
   """
   Descripción corta
   
   Uso: python scripts_utils/my_script.py
   """
   ```
4. Actualizar este README

---

**Última actualización:** 26 abril 2026  
**Mantener actualizado cuando haya cambios en estructura de datos**
