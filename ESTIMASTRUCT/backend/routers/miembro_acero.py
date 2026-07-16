# -*- coding: utf-8 -*-
"""
Router — Miembros de Acero LRFD (AISC 360-16 §D/E/F/G/H)
========================================================
prefix /miembro-acero.  STATELESS: no toca BD, no crea tablas.
Verificacion independiente de miembros (calcula φRn propio).

Endpoints:
  GET  /miembro-acero/catalogo        -> perfiles + aceros para poblar menus
  POST /miembro-acero/memoria-rapida  -> Hoja en vivo (memoria_miembro)
"""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.calculo_miembro_acero import memoria_miembro
from backend.perfiles_acero import PERFILES_ACERO, ACEROS, _es_hss

router = APIRouter(prefix="/miembro-acero", tags=["miembro-acero"])


@router.get("/catalogo")
def get_catalogo():
    """Perfiles y aceros para poblar los menus. El frontend NO hardcodea
    perfiles; los pide aqui (fuente unica = perfiles_acero.py)."""
    perfiles = [
        {"perfil": k, "d": v["d"], "bf": v["bf"], "Ag": v["Ag"], "hss": _es_hss(k)}
        for k, v in PERFILES_ACERO.items()
    ]
    perfiles.sort(key=lambda p: (p["hss"], p["perfil"]))
    aceros = [{"clave": k, "Fy": v["Fy"], "Fu": v["Fu"], "desc": v["desc"]}
              for k, v in ACEROS.items()]
    return {"perfiles": perfiles, "aceros": aceros}


class MiembroRapido(BaseModel):
    perfil:  str   = "W310X73"
    acero:   str   = "A992"
    L_cm:    float = 400.0
    K:       float = 1.0
    Lb_cm:   float = 0.0     # 0 -> usa L_cm
    Cb:      float = 1.0
    pu_t:    float = 0.0     # + traccion / - compresion
    mux_tm:  float = 0.0
    muy_tm:  float = 0.0
    vu_t:    float = 0.0


@router.post("/memoria-rapida")
def memoria_rapida_miembro(body: MiembroRapido):
    """Calculadora en vivo de miembros: perfil + demanda -> memoria narrada
    (meta/pasos/constantes) con φRn por estado limite §D/E/F/G/H. NO toca BD."""
    elem = {
        "perfil": body.perfil, "acero": body.acero,
        "L_cm": body.L_cm, "K": body.K, "Lb_cm": body.Lb_cm, "Cb": body.Cb,
    }
    caso = {"pu_t": body.pu_t, "mux_tm": body.mux_tm,
            "muy_tm": body.muy_tm, "vu_t": body.vu_t}
    return memoria_miembro(elem, caso)
