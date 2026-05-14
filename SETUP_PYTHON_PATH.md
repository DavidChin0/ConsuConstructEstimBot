# 🐍 CONFIGURACIÓN PYTHON — Path y Versión

**Importante:** Usar `D:\LLM\python\python.exe` de ahora en adelante  
**Razón:** Mejor compatibilidad y menos problemas de codificación

---

## ⚙️ AGREGAR AL PATH

### Opción 1: Temporal (Sesión Actual)
```powershell
$env:Path = "D:\LLM\python;" + $env:Path
python --version
# Debe mostrar: Python 3.x.x
```

### Opción 2: Permanente (Variables de Entorno)

**Windows 11:**
1. Abrir: `Configuración` → `Sistema` → `Información del sistema`
2. Click: `Configuración avanzada del sistema`
3. Tab: `Avanzado` → `Variables de entorno...`
4. Click: `Nueva...` (en "Variables del sistema")
5. `Nombre de variable:` **Path**
6. `Valor:` Agregar **`D:\LLM\python`** (separado con `;` de otros valores)
7. Aceptar y reiniciar terminal/IDE

---

## ✅ VERIFICACIÓN

Después de agregar al PATH:

```powershell
python --version
python -c "import sys; print(sys.executable)"
```

Debe mostrar:
```
Python 3.x.x
D:\LLM\python\python.exe
```

---

## 📋 COMANDOS A USAR

### Backend — Desarrollo
```powershell
# Instalar dependencias
python -m pip install -r backend/requirements.txt

# Ejecutar servidor
python backend/main.py
```

### Backend — Seed BD
```powershell
python backend/seed_bd.py
```

### Scripts — Migración
```powershell
# Migración actual (template_version)
python C:\temp\migrate_all_dbs.py

# Scripts personalizados
python scripts/mi_script.py
```

---

## 🔧 PROBLEMAS COMUNES

### "python: command not found"
→ Agregar al PATH (ver arriba) y reiniciar terminal

### "UnicodeEncodeError"
→ Usar `D:\LLM\python\python.exe` (ya incluye UTF-8)

### "ModuleNotFoundError"
→ Verificar: `python -m pip list` (debe mostrar sqlalchemy, fastapi, etc.)

---

## 📍 UBICACIÓN PYTHON ALTERNATIVA

Si `D:\LLM\python` no existe, buscar:
```powershell
# Buscar Python instalado
Get-Command python | Select-Object Source
gcm py | Select-Object Source
gcm python.exe | Select-Object Source
```

Luego reemplazar ruta en comandos.

---

## 🚀 USAR SIEMPRE ESTE PYTHON

De ahora en adelante, en todos los scripts y comandos:

```powershell
# MAL (puede dar errores):
python script.py

# BIEN (usar siempre):
D:\LLM\python\python.exe script.py

# O si está en PATH:
python script.py  # (funciona después de agregar a PATH)
```

---

**Estado:** ✅ CONFIGURADO  
**Última actualización:** 26 abril 2026
