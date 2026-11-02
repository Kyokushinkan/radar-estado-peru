"""Lector aislado de movimientos observados V2.5.3."""

import json
import sqlite3
from pathlib import Path
from urllib.parse import urlparse


CAMPOS = (
    "id", "perfil", "id_funcionario", "campo",
    "valor_anterior", "valor_nuevo", "fecha_deteccion",
    "fuente", "run_id", "clasificacion", "verificacion_oficial"
)


def enlace_oficial(valor):
    if not isinstance(valor, str):
        return False
    try:
        url = urlparse(valor.strip())
        host = (url.hostname or "").lower()
        return (
            url.scheme == "https"
            and (host == "gob.pe" or host.endswith(".gob.pe"))
            and url.port in (None, 443)
            and not url.username
            and not url.password
        )
    except (ValueError, TypeError):
        return False


def cargar_movimientos(ruta, limite=1000):
    """Devuelve movimientos observados, sin atribuir actos oficiales."""
    limite = int(limite)
    if not 1 <= limite <= 10000:
        raise ValueError("Limite fuera del rango permitido")

    archivo = Path(ruta).resolve()

    if not archivo.is_file():
        raise FileNotFoundError(str(archivo))

    conexion = sqlite3.connect(
        archivo.as_uri() + "?mode=ro",
        uri=True,
        timeout=3
    )
    conexion.row_factory = sqlite3.Row

    try:
        existe = conexion.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='movimientos_v25'"
        ).fetchone()

        if not existe:
            # Historial real V2.5.3: el motor conserva la tabla
            # movimientos. Sin registros, no hay cambios acreditados.
            historica = conexion.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='movimientos'"
            ).fetchone()

            if not historica:
                return []

            total = conexion.execute(
                "SELECT COUNT(*) FROM movimientos"
            ).fetchone()[0]

            if total == 0:
                return []

            raise ValueError(
                "El historial contiene movimientos en un esquema "
                "que requiere adaptación antes de presentarse."
            )

        consulta = (
            "SELECT " + ", ".join(CAMPOS)
            + " FROM movimientos_v25 "
            + "ORDER BY fecha_deteccion DESC, id DESC LIMIT ?"
        )

        registros = conexion.execute(consulta, (limite,)).fetchall()
        salida = []

        for fila in registros:
            item = dict(fila)

            item["perfil_oficial"] = (
                item["perfil"] if enlace_oficial(item["perfil"]) else ""
            )

            item["fuente_oficial"] = (
                item["fuente"] if enlace_oficial(item["fuente"]) else ""
            )

            item["estado_presentacion"] = (
                "Cambio observado; verificacion oficial pendiente"
                if item["clasificacion"] == "cambio_observado"
                and item["verificacion_oficial"] == "pendiente"
                else "Registro requiere revision"
            )

            salida.append(item)

        return salida

    finally:
        conexion.close()


def filtrar_movimientos(
    registros,
    funcionario="",
    campo="",
    verificacion="",
    fecha_desde=""
):
    funcionario = str(funcionario).strip().casefold()
    campo = str(campo).strip().casefold()
    verificacion = str(verificacion).strip().casefold()
    fecha_desde = str(fecha_desde).strip()

    return [
        item for item in registros
        if (not funcionario or funcionario in str(
            item.get("id_funcionario", "")
        ).casefold())
        and (not campo or campo == str(
            item.get("campo", "")
        ).casefold())
        and (not verificacion or verificacion == str(
            item.get("verificacion_oficial", "")
        ).casefold())
        and (not fecha_desde or str(
            item.get("fecha_deteccion", "")
        )[:10] >= fecha_desde)
    ]