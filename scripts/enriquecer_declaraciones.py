import argparse
import json
import sqlite3
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

DB = Path("data/enriched/funcionarios.sqlite3")

def normalizar(s):
    return "".join(
        c for c in unicodedata.normalize(
            "NFKD", str(s).casefold()
        )
        if not unicodedata.combining(c)
    )

def extraer(html, base):
    sopa = BeautifulSoup(html, "html.parser")
    for a in sopa.select("a[href]"):
        titulo = normalizar(a.get_text(" ", strip=True))
        if "declaracion jurada" in titulo and "interes" in titulo:
            url = urljoin(base, a["href"])
            host = urlparse(url).hostname or ""
            if url.startswith("https://") and (
                host == "contraloria.gob.pe"
                or host.endswith(".contraloria.gob.pe")
            ):
                return url
    return ""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit debe ser 0 o mayor")

    db = sqlite3.connect(DB, timeout=30)
    db.execute("""
        CREATE TABLE IF NOT EXISTS declaraciones_control (
            id_funcionario TEXT PRIMARY KEY,
            estado TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT ''
        )
    """)
    db.commit()

    filas = db.execute("""
        SELECT rowid, payload
        FROM profiles
        WHERE result = 'ok'
        ORDER BY rowid
    """).fetchall()

    sesion = requests.Session()
    sesion.headers.update({
        "User-Agent": "Mozilla/5.0"
    })

    procesados = 0

    try:
        for rowid, raw in filas:
            p = json.loads(raw)
            fid = str(p.get("id_funcionario") or "")
            url = p.get("url_oficial") or p.get("perfil")
            adicional = p.get("informacion_adicional") or {}

            if not isinstance(adicional, dict):
                adicional = {}

            if not fid or not url:
                continue

            if not url.startswith(
                "https://www.gob.pe/institucion/"
            ):
                continue

            if adicional.get("declaracion_jurada_intereses_url"):
                continue

            previo = db.execute(
                """SELECT estado FROM declaraciones_control
                   WHERE id_funcionario=?""",
                (fid,)
            ).fetchone()

            if previo and previo[0] in (
                "encontrada", "sin_enlace"
            ):
                continue

            if args.limit and procesados >= args.limit:
                break

            procesados += 1

            try:
                respuesta = sesion.get(url, timeout=45)
                respuesta.raise_for_status()
                enlace = extraer(respuesta.text, url)

                estado = "encontrada" if enlace else "sin_enlace"

                if enlace:
                    adicional[
                        "declaracion_jurada_intereses_url"
                    ] = enlace
                    p["informacion_adicional"] = adicional

                    db.execute(
                        "UPDATE profiles SET payload=? WHERE rowid=?",
                        (json.dumps(p, ensure_ascii=False), rowid)
                    )

                db.execute("""
                    INSERT INTO declaraciones_control
                    (id_funcionario, estado, url)
                    VALUES (?, ?, ?)
                    ON CONFLICT(id_funcionario)
                    DO UPDATE SET
                    estado=excluded.estado,
                    url=excluded.url
                """, (fid, estado, enlace))

                db.commit()
                print(
                    f"{procesados}: {fid}: {estado}",
                    flush=True
                )

            except requests.RequestException as error:
                print(
                    f"{procesados}: {fid}: error_http: {error}",
                    flush=True
                )

            time.sleep(3)

    except KeyboardInterrupt:
        print("Interrumpido; cambios guardados.")
    finally:
        db.close()

if __name__ == "__main__":
    main()
