import os
os.chdir(os.path.dirname(__file__))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db import engine
from models import Base
from routers import presupuestos, partidas, recursos, calculos, export, insumos, scripts as scripts_router, bases, updater, diagnostics, memory, soldadura_estructural
from error_handler import register_exception_handlers
from silent_notifier import notifier, notify_file

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Estimacion API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
notifier.subscribe(notify_file("notifications.log"))
notifier.start_monitoring()


@app.on_event("shutdown")
def shutdown():
    notifier.stop_monitoring()

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
app.include_router(soldadura_estructural.router)


@app.get("/")
def root():
    return {"status": "ok", "app": "Estimacion API v1.0"}

@app.get("/health")
def health():
    return {"status": "healthy"}
