"""Entrada principal de Radar Estado Perú V2.3."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Streamlit prepends the script directory; the repository must take priority.
while str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))
from app.interfaz import main

if __name__ == '__main__':
    main()
