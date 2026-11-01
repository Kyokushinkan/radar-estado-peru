"""Entrada aislada Radar Estado Peru V2.5.3."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Priorizar la raiz del proyecto para resolver app como paquete.
# No incorporar rutas de laboratorio ni anteponer ROOT/app.
APP_DIR = ROOT / "app"

for ruta in (str(ROOT), str(APP_DIR)):
    while ruta in sys.path:
        sys.path.remove(ruta)

sys.path.insert(0, str(ROOT))

import streamlit as st

from app.interfaz_v253 import main

st.navigation(
    [st.Page(main, title="Radar Estado Peru V2.5.3")],
    position="hidden"
).run()