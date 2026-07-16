import os

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.db import engine
from backend.models import Base
from backend.routers import presupuestos, partidas, recursos, calculos, export, insumos, scripts as scripts_router, bases, updater, diagnostics, memory, diseno_estructural, sismo, conexion_acero, miembro_acero, acero_diseno, portal_publish, cronograma as cronograma_router, export_pdf, preview_pdf
from backend.error_handler import register_exception_handlers
from backend.silent_notifier import notifier, notify_file


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    notifier.subscribe(notify_file(os.path.join(os.path.dirname(__file__), "notifications.log")))
    notifier.start_monitoring()
    yield
    notifier.stop_monitoring()


app = FastAPI(title="Estimacion API", version="1.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5000", "http://127.0.0.1:5000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(presupuestos.router)
app.include_router(partidas.router)
app.include_router(recursos.router)
app.include_router(calculos.router)
app.include_router(export.router)
app.include_router(insumos.router)
app.include_router(scripts_router.router)
app.include_router(bases.router)
app.include_router(updater.router)
app.include_router(diagnostics.router)
app.include_router(memory.router)
app.include_router(diseno_estructural.router)
app.include_router(sismo.router)
app.include_router(acero_diseno.router)   # R3: endpoints acero stateful (mismo prefix /diseno)
app.include_router(conexion_acero.router)
app.include_router(miembro_acero.router)
app.include_router(portal_publish.router)   # POST /presupuestos/{id}/publish-supabase
app.include_router(cronograma_router.router)   # GET cronograma + export-cronograma (Gantt)
app.include_router(export_pdf.router)   # GET export-pdf (membrete ConsuConstruct)
app.include_router(preview_pdf.router)   # GET preview-pdf (HTML) + export-pdf-html (Chromium)


@app.get("/")
def root():
    return {"status": "ok", "app": "Estimacion API v1.0"}

@app.get("/health")
def health():
    return {"status": "healthy"}
