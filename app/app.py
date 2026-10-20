"""Entrada publica de Radar Estado Peru V2.4."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

while str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))

sys.path.insert(0, str(ROOT))

import streamlit as st
from app.interfaz_v24 import main

st.navigation(
    [st.Page(main, title="Radar Estado Peru V2.4")],
    position="hidden"
).run()
