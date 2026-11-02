
import hashlib
import json
import sqlite3
from datetime import datetime, timezone


def canonical(registro):
    return json.dumps(
        registro,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def fecha_utc(valor):
    if not isinstance(valor, str):
        raise ValueError("FECHA_INVALIDA")
    fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    if fecha.tzinfo is None:
        raise ValueError("FECHA_SIN_ZONA")
    return fecha.astimezone(timezone.utc)


def normalizar(valor):
    import re
    import unicodedata

    texto = unicodedata.normalize("NFKD", str(valor or "").strip())
    texto = "".join(
        c for c in texto if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", texto).casefold()


def esquema(con):
    con.executescript("""
        CREATE TABLE observaciones (
            id INTEGER PRIMARY KEY,
            run_id TEXT NOT NULL,
            id_funcionario TEXT NOT NULL,
            fecha_observacion TEXT NOT NULL,
            fecha_utc TEXT NOT NULL,
            fuente TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            huella_integral TEXT NOT NULL,
            UNIQUE(run_id, id_funcionario)
        );

        CREATE TABLE movimientos (
            id INTEGER PRIMARY KEY,
            clave TEXT NOT NULL UNIQUE,
            observacion_anterior_id INTEGER NOT NULL,
            observacion_nueva_id INTEGER NOT NULL,
            id_funcionario TEXT NOT NULL,
            campo TEXT NOT NULL,
            valor_anterior TEXT NOT NULL,
            valor_nuevo TEXT NOT NULL,
            fecha_deteccion TEXT NOT NULL,
            fuente TEXT NOT NULL,
            run_id TEXT NOT NULL,
            verificacion_oficial TEXT NOT NULL DEFAULT 'pendiente',
            FOREIGN KEY(observacion_anterior_id)
                REFERENCES observaciones(id),
            FOREIGN KEY(observacion_nueva_id)
                REFERENCES observaciones(id)
        );
    """)


def registrar(con, run_id, fecha, registro, fuente):
    if not isinstance(registro, dict):
        raise ValueError("REGISTRO_INVALIDO")

    ident = str(registro.get("id_funcionario") or "").strip()

    if not all((run_id, fuente, ident)):
        raise ValueError("METADATOS_INCOMPLETOS")

    if registro.get("resultado") != "ok":
        return "IGNORADO_ERROR"

    if not all(
        str(registro.get(campo) or "").strip()
        for campo in ("cargo", "entidad")
    ):
        return "IGNORADO_INCOMPLETO"

    momento = fecha_utc(fecha)
    instante = momento.isoformat()
    payload = canonical(registro)
    huella = sha(payload)

    with con:
        existente = con.execute(
            """SELECT huella_integral, fecha_utc, fuente
               FROM observaciones
               WHERE run_id=? AND id_funcionario=?""",
            (run_id, ident),
        ).fetchone()

        if existente:
            if existente != (huella, instante, fuente):
                raise ValueError("REPLAY_CONFLICTIVO")
            return "REPLAY_IDENTICO"

        previo = con.execute(
            """SELECT id, payload_json, huella_integral, fecha_utc
               FROM observaciones
               WHERE id_funcionario=?
               ORDER BY fecha_utc DESC, id DESC
               LIMIT 1""",
            (ident,),
        ).fetchone()

        if previo and momento <= datetime.fromisoformat(previo[3]):
            raise ValueError("OBSERVACION_NO_POSTERIOR")

        cursor = con.execute(
            """INSERT INTO observaciones
               (run_id, id_funcionario, fecha_observacion,
                fecha_utc, fuente, payload_json, huella_integral)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, ident, fecha, instante, fuente, payload, huella),
        )

        nueva_id = cursor.lastrowid

        if not previo:
            return "BASELINE"

        anterior = json.loads(previo[1])
        cambios = 0

        for campo in ("cargo", "entidad"):
            viejo = str(anterior.get(campo) or "").strip()
            nuevo = str(registro.get(campo) or "").strip()

            if normalizar(viejo) == normalizar(nuevo):
                continue

            clave = sha(canonical({
                "anterior": previo[0],
                "nueva": nueva_id,
                "campo": campo,
            }))

            con.execute(
                """INSERT INTO movimientos
                   (clave, observacion_anterior_id,
                    observacion_nueva_id, id_funcionario,
                    campo, valor_anterior, valor_nuevo,
                    fecha_deteccion, fuente, run_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    clave, previo[0], nueva_id, ident,
                    campo, viejo, nuevo, instante, fuente, run_id,
                ),
            )
            cambios += 1

        return "CAMBIOS=" + str(cambios)


def verificar_integridad(con):
    errores = []

    for ident, payload, huella in con.execute(
        "SELECT id, payload_json, huella_integral FROM observaciones"
    ):
        if sha(payload) != huella:
            errores.append(ident)

    return errores
