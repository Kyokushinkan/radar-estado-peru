"""Adaptador V2.5.4: normalizacion de observaciones oficiales."""

import re
from urllib.parse import urlparse


def normalizar_observacion(registro):
    if not isinstance(registro, dict):
        raise ValueError("Registro invalido")

    if registro.get("resultado") != "ok":
        raise ValueError("Consulta oficial no valida")

    identificador = str(registro.get("id_funcionario") or "").strip()
    cargo = str(registro.get("cargo_publicado") or "").strip()
    entidad = str(registro.get("entidad_publica") or "").strip()
    url = str(
        registro.get("url_oficial") or registro.get("perfil") or ""
    ).strip()

    if not identificador or not cargo or not entidad:
        raise ValueError("Campos obligatorios incompletos")

    parsed = urlparse(url)

    patron = (
        r"^/institucion/[^/]+/funcionarios/"
        + re.escape(identificador)
        + r"(?:-[a-z0-9-]+)?/?$"
    )

    if (
        parsed.scheme != "https"
        or parsed.hostname not in ("gob.pe", "www.gob.pe")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(patron, parsed.path, re.IGNORECASE)
    ):
        raise ValueError("URL oficial no coincide con funcionario")

    return {
        "id_funcionario": identificador,
        "resultado": "ok",
        "cargo": cargo,
        "entidad": entidad,
        "url_oficial": url,
        "fecha_consulta": registro.get("fecha_consulta"),
        "http_status": registro.get("http_status"),
        "evidencia": registro.get("evidencia") or {},
    }