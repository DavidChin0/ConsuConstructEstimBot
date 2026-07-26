# Features Page — EstimaStruct

## Deliverable Summary

**File:** `ESTIMASTRUCT/templates/features.html`  
**Route:** `http://localhost:5000/features`  
**Status:** Ready for staging

### Completed

✅ **Module Descriptions** (real, not marketing):
- Presupuesto: Budget by CSI, quantity takeoff, pricing pipeline
- Viewer 3D: Babylon.js renderer for BIM models
- Base de Datos: Postgres/SQLite architecture, ACID, migration
- Diseño Estructural: Concreto CHOC-08 + Acero LRFD 360-16
- Cronograma: Gantt + Overrides MO diario + prorrateo valor
- RAG Retrieval: Semantic search on fichas + docs

✅ **MCP Integrations** (real endpoints + use cases):
- **Revit MCP :8100** — IronPython injection, quantity import, keynote generation
  - Endpoints: /start, /status, /import-quantities, /generate-keynotes
  - Use case: auto-extract quantities from Revit models → batch import to presupuesto
  
- **ETABS Integration** — CSV parser for seismic analysis
  - Endpoints: /import-results, /parse-csv, /spectrum-export
  - Use case: ETABS Concrete Frame Design → auto-generate CSI 03/05 partidas + refuerzo

✅ **Brand Consistency**:
- Amber #F8BE16 as accent
- Charcoal #2c2c2c as primary text
- Cinzel serif typeface for headings
- Technical tone (no fluff, code examples, real specs)

✅ **Tech Stack Transparency**:
- Backend: FastAPI 0.111 + Uvicorn :8002
- Database: PostgreSQL 16 primario, SQLite legacy compat
- Frontend: Flask 3.1 + Vanilla JS + KaTeX
- Rendering: Babylon.js (3D), ReportLab (PDF), openpyxl (XLSX)
- Integrations: Revit MCP HTTP, ETABS CSV, Supabase REST

✅ **Workflow Visualization**:
- Pipeline: Cargar → Instanciar CSI → Bucketing → Costo Base → Takeoff → Recalcular → Overhead → Export
- Deployment: PowerShell launcher (START_POSTGRES_UNICA.ps1 → FastAPI + Flask + PG)

### Screenshot Situation

❌ **Missing:** Module screenshots (app UI, Viewer 3D, design calculator)

**Next Steps:**
1. Run EstimaStruct locally (START_POSTGRES_UNICA.ps1)
2. Capture key views:
   - Main presupuesto grid (partidas by CSI)
   - Viewer 3D (Babylon rendering of model)
   - Diseño Estructural panel (KaTeX fórmulas)
   - Revit MCP control panel
3. Place in `/media/features/` with refs in HTML:
   ```html
   <img src="/media/features/presupuesto-grid.png" alt="Presupuesto grid" />
   ```
4. Or: delegate to Sonnet agent to generate mockups (if actual screenshots unavailable)

### Integration Points

**Features page now lives at:**
- Public URL: `http://localhost:5000/features`
- Route handler: `ESTIMASTRUCT/app.py` line ~150

**Ready for:**
- Static hosting (GitHub Pages, S3, CDN) — minify CSS inline
- PDF export (include as technical spec sheet)
- Portal integration (Supabase link → direct to features)
- Marketing site (update ConsuConstruct.com homepage)

### Accessibility Notes

- Full semantic HTML (h1–h3, nav structure)
- Color contrast: 7:1+ (charcoal #2c2c2c on white)
- Responsive: mobile-first grid (360px+)
- No JavaScript required (pure HTML/CSS)
- Keyboard navigable (native link focus)

### Technical Debt / Future

- Add embedded video (demo: Revit → import quantities → presupuesto) [P1]
- Add comparison table (EstimaStruct vs Excel / competitor X) [P2]
- Add FAQ section (troubleshooting, common workflows) [P3]
- Internationalization: es/en toggle at header level [P4]
- Implement screenshot carousel with Viewer 3D live embed [P5]

---

**Created:** 2026-07-26  
**By:** Fable Agent (ESTIMASTRUCT Portfolio Refresh)  
**Status:** Ready for review + screenshot capture
