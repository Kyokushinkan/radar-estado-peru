"""Lectura conservadora de evidencia local; nunca modifica SQLite."""
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlparse


def url_dji_valida(url):
    try:
        p = urlparse(url)
        return (p.scheme == "https" and p.hostname == "appdji.contraloria.gob.pe"
                and p.port in (None, 443) and not p.username and not p.password
                and p.path == "/djic/ConsultaPublicaDJIC.aspx"
                and re.fullmatch(r"documento=\d+", p.query) is not None
                and not p.fragment)
    except (ValueError, TypeError):
        return False


def evaluar(url, resultado, perfil, control):
    fid = str(perfil.get("id_funcionario") or "")
    p = urlparse(url)
    match = re.fullmatch(r"/institucion/[^/]+/funcionarios/(\d+)(?:-[^/]+)?/?", p.path)
    if (p.scheme != "https" or p.hostname != "www.gob.pe" or not match
            or match[1] != fid or perfil.get("perfil") != url):
        return {"estado": "inconsistente", "url": ""}
    adicional = perfil.get("informacion_adicional") or {}
    enlace = adicional.get("declaracion_jurada_intereses_url", "") if isinstance(adicional, dict) else ""
    if enlace:
        if control != ("encontrada", enlace) or not url_dji_valida(enlace):
            return {"estado": "inconsistente", "url": ""}
        return {"estado": "enlace_registrado", "url": enlace}
    if control and control[0] == "sin_enlace" and not control[1]:
        return {"estado": "no_encontrada", "url": ""}
    if control:
        return {"estado": "inconsistente", "url": ""}
    if resultado == "error_http":
        return {"estado": "error_http_perfil", "url": "", "http": perfil.get("http_status")}
    return {"estado": "sin_resultado", "url": ""}


def consultar(ruta, perfil_url, fid):
    c = sqlite3.connect(Path(ruta).resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
    try:
        c.execute("BEGIN")
        row = c.execute("SELECT url,result,payload FROM profiles WHERE url=?", (perfil_url,)).fetchone()
        existe = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='declaraciones_control'").fetchone()
        control = c.execute("SELECT estado,url FROM declaraciones_control WHERE id_funcionario=?", (str(fid),)).fetchone() if existe else None
        if not row:
            return {"estado": "sin_resultado", "url": ""}
        payload = json.loads(row[2])
        if str(payload.get("id_funcionario")) != str(fid):
            return {"estado": "inconsistente", "url": ""}
        return evaluar(row[0], row[1], payload, control)
    finally:
        c.close()


def mostrar(persona, modo, ruta):
    import streamlit as st
    st.subheader("Declaraciones")
    if modo != "sqlite":
        st.info("Esta instantánea no incluye el control de extracción. Consulte la fuente SQLite local para verificar la vinculación.")
        return
    try:
        dato = consultar(ruta, persona["perfil"], persona["id_funcionario"])
    except (sqlite3.Error, ValueError, TypeError, AttributeError, OSError):
        st.error("No se pudo leer la evidencia local de declaraciones.")
        return
    estado = dato["estado"]
    if estado == "enlace_registrado":
        st.success("Enlace oficial registrado: declaración jurada de intereses.")
        st.link_button("Consultar en Contraloría", dato["url"])
        st.caption("El enlace coincide con el control de extracción de esta ficha. No se ha verificado el contenido, el titular, la fecha ni la disponibilidad actual del documento. Una persona puede aparecer en varias fichas.")
    elif estado == "no_encontrada":
        st.info("No se encontró un enlace en la consulta registrada de la ficha. Esto no demuestra que la persona carezca de declaraciones.")
    elif estado == "error_http_perfil":
        st.warning(f"Error HTTP {dato.get('http') or 'sin código'} en la extracción del perfil Gob.pe. No corresponde a una respuesta del documento de Contraloría.")
    elif estado == "inconsistente":
        st.warning("La vinculación requiere revisión. No se presenta un enlace como verificado.")
    else:
        st.info("Sin resultado registrado. Puede estar pendiente o haber fallado: el extractor anterior no guardaba los errores HTTP de declaraciones.")
    st.caption("No hay documentos descargados ni otros tipos de declaraciones acreditados en esta extracción.")
