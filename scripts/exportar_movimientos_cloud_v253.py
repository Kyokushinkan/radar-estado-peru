"""Exportacion controlada de movimientos observados a JSON publico."""
import json
import sqlite3
import sys
from pathlib import Path

CAMPOS = (
    "id", "id_funcionario", "campo", "valor_anterior",
    "valor_nuevo", "fecha_deteccion", "fuente", "run_id",
    "verificacion_oficial"
)

def exportar(db, destino):
    db = Path(db).resolve()
    destino = Path(destino).resolve()
    if not db.is_file():
        raise FileNotFoundError(db)

    con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLITE_INTEGRIDAD_BLOCK")

        existe = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='movimientos'"
        ).fetchone()

        if not existe:
            raise ValueError("TABLA_MOVIMIENTOS_AUSENTE")

        registros = [
            dict(fila) for fila in con.execute(
                "SELECT " + ",".join(CAMPOS)
                + " FROM movimientos ORDER BY fecha_deteccion DESC, id DESC"
            )
        ]
    finally:
        con.close()

    # El JSON es una fuente de presentacion, no un acto oficial.
    salida = {
        "version": "2.5.3",
        "tipo": "movimientos_observados",
        "total": len(registros),
        "movimientos": registros,
    }

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(destino.suffix + ".tmp")
    temporal.write_text(
        json.dumps(salida, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    temporal.replace(destino)
    print("MOVIMIENTOS_EXPORTADOS=" + str(len(registros)))
    print("JSON_PUBLICO=" + str(destino))

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Uso: exportador.py HISTORIAL.sqlite3 DESTINO.json")
    exportar(sys.argv[1], sys.argv[2])