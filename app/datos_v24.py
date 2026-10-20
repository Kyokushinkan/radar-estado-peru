"""Adaptador V2.4: contrato compartido y enlaces validados en una lectura."""
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlparse
from app.datos import normalizar_registros, enriquecer, leer_instantanea
from app.declaraciones_v24 import evaluar

ETIQUETAS = {
    "enlace_registrado": "Enlace registrado", "inconsistente": "Requiere revisión",
    "no_encontrada": "Sin enlace encontrado", "sin_resultado": "Sin resultado registrado",
    "error_http_perfil": "Error HTTP del perfil", "sin_control": "Sin control en la instantánea",
}


def oficial(url):
    try:
        p = urlparse(url)
        host = p.hostname or ""
        return (p.scheme == "https" and (host == "gob.pe" or host.endswith(".gob.pe"))
                and p.port in (None, 443) and not p.username and not p.password)
    except (ValueError, TypeError):
        return False


def cargar_datos(modo, ruta, referencia):
    if modo == "snapshot":
        df = leer_instantanea(ruta)
        df["estado_declaracion"] = "sin_control"
        df["declaracion_jurada"] = ""
    else:
        c = sqlite3.connect(Path(ruta).resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        inicio = time.monotonic()
        try:
            c.set_progress_handler(lambda: int(time.monotonic() - inicio > 10), 1000)
            c.execute("BEGIN")
            rows = c.execute("SELECT url,result,payload FROM profiles").fetchall()
            existe = c.execute("SELECT 1 FROM sqlite_master WHERE name='declaraciones_control' AND type='table'").fetchone()
            controles = {str(fid): (estado, url) for fid, estado, url in c.execute(
                "SELECT id_funcionario,estado,url FROM declaraciones_control")} if existe else {}
        finally:
            c.close()
        df = normalizar_registros([(r, p) for _, r, p in rows])
        estados, enlaces = [], []
        for url, resultado, raw in rows:
            try:
                p = json.loads(raw)
                dato = evaluar(url, resultado, p, controles.get(str(p.get("id_funcionario"))))
            except (ValueError, TypeError, AttributeError):
                dato = {"estado": "inconsistente", "url": ""}
            estados.append(dato["estado"])
            enlaces.append(dato["url"])
        df["estado_declaracion"] = estados
        df["declaracion_jurada"] = enlaces
    for campo in ("perfil", "norma"):
        df[campo] = df[campo].where(df[campo].map(oficial), "")
    df["declaraciones"] = df.estado_declaracion.map(ETIQUETAS).fillna("Requiere revisión")
    return enriquecer(df, referencia)
