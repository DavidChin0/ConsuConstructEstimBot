> [!CONTEXT]
> Entrada viva de EstimaStruct fuera del vault. El punto de navegacion canonico es `index.md` en esta carpeta.

# EstimaStruct

EstimaStruct es una plataforma open source de estimación para ingeniería y arquitectura.  
Sirve como puente entre Revit 2027 y el análisis de precios, con foco en trazabilidad, detalle técnico y control de costos.

By ConsuConstruct.com, dentro del ecosistema Estimbot.

## What it does

- Estimación por partidas, capítulos CSI e insumos
- Administración de bases de fichas por versión
- Importación de cantidades desde schedules exportados desde Revit
- Recalculo de costos y exportación de presupuesto real
- Exportación de insumos necesarios por obra activa, separados por actividad, usando `rendimiento` por insumo y una hoja global con consolidado, `cantidad de insumos` y ROUNDUP
- Soporte para análisis estructural y detalle técnico

## Stack

- Backend: FastAPI
- Database: SQLite
- Frontend: Vanilla JavaScript, HTML, CSS
- Integración: Revit 2027 + pyRevit

## Live flow

1. Se crea o selecciona una obra en EstimaStruct.
2. Revit exporta schedules desde pyRevit.
3. EstimaStruct importa cantidades desde CSV.
4. La base recalcula costos y totales.
5. El presupuesto queda listo para exportación, incluyendo el reporte de insumos necesarios, o para etapas posteriores de propuesta.

## Run locally

- Raíz viva: `D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT`
- Backend: `backend\` (FastAPI :8002) — BD viva en `C:\EstimaStruct\data\estimacion.db`
- Frontend: `ESTIMASTRUCT\` (Flask :5000) + `frontend\` (JS/CSS/vendor)

Lanzador único (backend 8002 + frontend 5000 en una ventana):

- `START_UNICA.ps1`

## Project layout

- `index.md` - entrada canonica de la carpeta.
- `backend/` - API, modelos, routers y scripts de importación/exportación
- `frontend/` - interfaz principal
- `development/Template2_Updated/` - bases de fichas versionadas
- `ESTIMASTRUCT/` - app Flask que sirve la UI (templates + static)

## Notes

- El flujo operativo está pensado para que Revit alimente cantidades y EstimaStruct consolide presupuesto.
- Los nombres de las actividades en `v1.1` se consideran la referencia estable.
- El proyecto forma parte del módulo de automatización de Estimbot.
- El `sobrecosto` es el único margen aplicado sobre el costo directo; el IVA ya viene absorbido dentro de los costos de insumos y no se suma aparte.
- El `Costo Directo` del front end debe coincidir con `Total general` de la fila 5 de la hoja `global` del export de insumos.
- En los insumos, el precio unitario es fijo por código y el rendimiento es el valor que cambia por matriz.
- Si el mismo código aparece varias veces, la limpieza conserva el insumo con precio unitario válido y descarta el duplicado débil.
- En el export de insumos, `Consolidado global de insumos` incluye materiales, mano de obra, equipo y subcontrato; `Cantidad de insumos` solo incluye materiales.
- En modo cliente la cabecera solo muestra `Total`; `Costo Directo` y `Sobrecosto` quedan reservados para modo desarrollador.
- `Bases de Datos` se audita desde un panel full en modo desarrollador y se activa/desactiva desde la barra lateral.
- En modo desarrollador la tabla de actividades permite ajustar tamaño de letra y redimensionar columnas arrastrando sus encabezados.
- El precio unitario canónico de un código es el precio no-cero más repetido; si un código aparece varias veces, todas sus matrices heredan ese precio sin cambiar su código.
- La descripción canónica de un código también se normaliza por frecuencia; si el mismo código aparece con nombres distintos, la base conserva un nombre estándar por código.
- `HER-00` es una excepción operativa: su valor se calcula como porcentaje de la mano de obra total de la ficha y no entra en la normalización de precio.
- La auditoría XLSX solo considera insumos reales: `MA`, `MO`, `SC`, `EQ`, `HER`, `DIS` y `FL`. No usa `Type Mark` ni `CSI` como llave de auditoría.
