"""Extracción conservadora Gob.pe. Ejecutar --help; no certifica vigencia del cargo."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import unicodedata
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/processed/funcionarios_gobpe_consolidado.csv"
ORIGINAL = ["pagina", "id_funcionario", "nombre", "entidad_url", "perfil"]
FIELDS = ["nombre_completo", "cargo_publicado", "entidad_publica",
          "denominacion_completa", "fecha_publicacion", "fecha_actualizacion"]
AGENT = "RadarEstadoPeruV2/0.1 (consulta de perfiles publicos; no acredita vigencia)"
ROBOTS = "https://www.gob.pe/robots.txt"


def now():
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    return " ".join(str(value or "").split())


def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFKD", clean(value).lower())
                   if not unicodedata.combining(c)).strip(" :")


def official(url):
    p = urlparse(url)
    return (p.scheme == "https" and p.hostname == "www.gob.pe"
            and p.port in (None, 443) and not p.username and not p.password)


def profile_id(url):
    if not official(url):
        return None
    match = re.fullmatch(r"/institucion/[^/]+/funcionarios/(\d+)(?:-[^/]+)?/?", urlparse(url).path)
    return match.group(1) if match else None


def load_source(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        if not set(ORIGINAL).issubset(reader.fieldnames or []):
            raise ValueError("Faltan columnas obligatorias en la fuente")
        rows = list(reader)
    seen = set()
    for number, row in enumerate(rows, 2):
        if any(not clean(row.get(k)) for k in ORIGINAL):
            raise ValueError(f"Fila {number}: campo obligatorio vacío")
        if profile_id(row["perfil"]) != row["id_funcionario"]:
            raise ValueError(f"Fila {number}: URL o identificador no válido")
        if row["perfil"] in seen:
            raise ValueError(f"Fila {number}: URL duplicada")
        seen.add(row["perfil"])
    return rows


def base_record(row):
    result = dict(row)
    result.update({k: row.get(k, "") for k in FIELDS})
    result["nombre_completo"] = row.get("nombre_completo") or row["nombre"]
    result.update(url_oficial=row["perfil"], informacion_adicional={}, evidencia={},
                  campos_extraidos=[], advertencias=[], resultado="sin_datos",
                  error="", http_status=None, fecha_consulta=now())
    return result


def parse_profile(html, row, final_url):
    """Detecta JSON-LD, microdatos y etiquetas semánticas, nunca deduce un cargo."""
    out = base_record(row)
    if profile_id(final_url) != row["id_funcionario"]:
        out.update(resultado="perfil_no_coincide", error="Redirección fuera del perfil esperado")
        return out
    out["url_oficial"] = final_url
    soup = BeautifulSoup(html, "html.parser")
    title_text = normalized(soup.get_text(" ", strip=True))
    if any(t in title_text for t in ("acceso restringido", "verify you are human",
                                     "verifica que eres humano", "no se pudo procesar la solicitud")):
        out.update(resultado="bloqueado", error="Página de restricción o desafío")
        return out

    def put(field, value, origin):
        value = clean(value)
        if value and field not in out["campos_extraidos"]:
            out[field] = value
            out["campos_extraidos"].append(field)
            out["evidencia"][field] = {"origen": origin, "texto": value}

    def same_name(value):
        a = set(re.findall(r"\w+", normalized(value)))
        b = set(re.findall(r"\w+", normalized(row["nombre"])))
        return bool(b) and len(a & b) / len(b) >= 0.6

    def walk(value):
        if isinstance(value, dict):
            yield value
            for v in value.values():
                yield from walk(v)
        elif isinstance(value, list):
            for v in value:
                yield from walk(v)

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            nodes = list(walk(json.loads(script.string or script.get_text())))
        except (ValueError, TypeError):
            out["advertencias"].append("JSON-LD inválido")
            continue
        for node in nodes:
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            name = node.get("name")
            if "Person" not in types or not isinstance(name, str) or not same_name(name):
                continue
            put("nombre_completo", name, "JSON-LD Person.name")
            for key, field in (("jobTitle", "cargo_publicado"), ("datePublished", "fecha_publicacion"),
                               ("dateModified", "fecha_actualizacion")):
                if isinstance(node.get(key), str):
                    put(field, node[key], f"JSON-LD Person.{key}")
            org = node.get("worksFor")
            if isinstance(org, dict):
                if isinstance(org.get("name"), str):
                    put("entidad_publica", org["name"], "JSON-LD worksFor.name")
                if isinstance(org.get("legalName"), str):
                    put("denominacion_completa", org["legalName"], "JSON-LD worksFor.legalName")

    main = soup.find("main") or soup.find("article") or soup.body or soup
    h1 = main.find("h1")
    if h1 and same_name(h1.get_text(" ", strip=True)):
        put("nombre_completo", h1.get_text(" ", strip=True), "h1 coincidente con nombre original")
    # No se atribuyen encabezados o datos de otras personas a esta ficha.
    if "nombre_completo" not in out["campos_extraidos"]:
        out.update(resultado="estructura_no_reconocida", error="No se identificó el titular de la ficha")
        return out

    # Plantilla observada en una ficha oficial: se exige tarjeta, entidad y
    # concordancia del cargo con el título, no sólo proximidad al h1.
    card = h1.find_parent(class_="officials__card-links") if h1 else None
    if card:
        entity = card.select_one('[aria-describedby="institution-description"] a')
        job = h1.find_next_sibling("div")
        page_title = clean(soup.title.get_text()) if soup.title else ""
        if entity:
            entity_name = clean(entity.get_text(" ", strip=True))
            entity_href = urljoin(final_url, entity.get("href", ""))
            if official(entity_href) and urlparse(entity_href).path.rstrip("/") in (
                    f"/{row['entidad_url']}", f"/institucion/{row['entidad_url']}"):
                put("entidad_publica", entity_name, "tarjeta oficial: institution-description")
                put("denominacion_completa", entity_name, "denominación publicada en la tarjeta oficial")
                job_text = clean(job.get_text(" ", strip=True)) if job else ""
                if job_text and f" - {job_text} - Funcionarios - " in page_title:
                    put("cargo_publicado", job_text, "tarjeta oficial, corroborado en title")
        for link in card.find_all("a", href=True):
            if normalized(link.get_text(" ", strip=True)) == "norma de nombramiento":
                out["informacion_adicional"]["norma_nombramiento_url"] = urljoin(final_url, link["href"])
    changed = soup.select_one(".last-modification")
    if changed:
        text = clean(changed.get_text(" ", strip=True))
        match = re.match(r"Último cambio\s*:?\s*(.+)", text, flags=re.IGNORECASE)
        if match:
            put("fecha_actualizacion", match.group(1), "last-modification: Último cambio")

    for prop, field in (("jobTitle", "cargo_publicado"), ("datePublished", "fecha_publicacion"),
                         ("dateModified", "fecha_actualizacion")):
        tag = main.find(attrs={"itemprop": prop})
        if tag:
            put(field, tag.get("content") or tag.get("datetime") or tag.get_text(" ", strip=True),
                f"itemprop={prop}")

    labels = {"cargo": "cargo_publicado", "cargo actual": "cargo_publicado",
              "cargo que ocupa": "cargo_publicado", "entidad": "entidad_publica",
              "institucion": "entidad_publica", "entidad publica": "entidad_publica",
              "denominacion completa": "denominacion_completa",
              "nombre completo de la entidad": "denominacion_completa",
              "fecha de publicacion": "fecha_publicacion", "publicado el": "fecha_publicacion",
              "ultima actualizacion": "fecha_actualizacion", "fecha de actualizacion": "fecha_actualizacion"}
    extras = {"resumen", "fecha de inicio", "fecha de fin", "biografia", "resena", "resena biografica", "trayectoria", "formacion academica",
              "experiencia profesional", "funciones", "unidad organica", "dependencia"}
    for tag in main.find_all(["dt", "th", "h2", "h3", "h4", "strong", "b", "p", "span", "label"]):
        text = clean(tag.get_text(" ", strip=True))
        key, sep, inline = text.partition(":")
        label = normalized(key)
        if label not in labels and label not in extras:
            continue
        value = clean(inline) if sep else ""
        if not value:
            sibling = tag.find_next_sibling()
            if sibling and sibling.name not in ("h1", "h2", "h3", "h4", "dt", "th"):
                value = clean(sibling.get_text(" ", strip=True))
        if value and len(value) <= (8000 if label in extras else 500):
            if label in labels:
                put(labels[label], value, f"etiqueta HTML: {key}")
            else:
                out["informacion_adicional"][key] = value

    institution = f"/institucion/{row['entidad_url']}"
    for link in soup.find_all("a", href=True):
        href = urljoin(final_url, link["href"])
        name = clean(link.get_text(" ", strip=True))
        if official(href) and urlparse(href).path.rstrip("/") == institution and name:
            if normalized(name) not in ("inicio", "ver mas", "portal institucional"):
                put("entidad_publica", name, "enlace a la entidad de la fuente")
    for key, field in (("article:published_time", "fecha_publicacion"),
                        ("article:modified_time", "fecha_actualizacion")):
        meta = soup.find("meta", attrs={"property": key})
        if meta:
            put(field, meta.get("content"), f"meta {key}")
    # Una sigla o un slug no se presentan como denominación legal completa.
    out["resultado"] = "ok" if "cargo_publicado" in out["campos_extraidos"] else "parcial"
    return out


class StopRun(Exception):
    pass


def retry_after(value):
    if not value:
        return 0.0
    try:
        seconds = float(value)
        return max(0.0, seconds) if math.isfinite(seconds) else 0.0
    except ValueError:
        try:
            return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0.0


class Client:
    def __init__(self, args, event, session=None, sleep=time.sleep, clock=time.monotonic):
        self.args, self.event = args, event
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": AGENT, "Accept": "text/html"})
        self.sleep, self.clock = sleep, clock
        self.last = None
        self.delay = args.delay
        self.policy = None

    def get(self, url):
        for attempt in range(self.args.retries + 1):
            if self.last is not None:
                self.sleep(max(0, self.delay - (self.clock() - self.last)))
            start = self.clock()
            response = None
            error = ""
            try:
                response = self.session.get(url, timeout=self.args.timeout, allow_redirects=False)
            except requests.RequestException as exc:
                error = str(exc)
            self.last = self.clock()
            status = response.status_code if response is not None else None
            self.event({"url": url, "intento": attempt + 1, "http_status": status,
                        "fecha_consulta": now(), "segundos": self.last - start, "error": error})
            if status in (401, 403, 418, 451):
                return response
            transient = response is None or status == 429 or status in (500, 502, 503, 504)
            if not transient or attempt == self.args.retries:
                if response is None:
                    raise StopRun(f"Error de red tras reintentos: {error}")
                return response
            pause = max(self.args.backoff * 2 ** attempt,
                        retry_after(response.headers.get("Retry-After")) if response is not None else 0)
            if pause > self.args.max_wait:
                raise StopRun(f"Pausa requerida {pause:.0f}s supera --max-wait; se detiene sin acortarla")
            self.sleep(pause)
        raise AssertionError("unreachable")

    def check_robots(self):
        response = self.get(ROBOTS)
        if response.status_code == 404:
            policy = RobotFileParser()
            policy.parse([])
        elif response.status_code == 200 and "<html" not in response.text.lower():
            policy = RobotFileParser()
            policy.parse(response.text.splitlines())
        else:
            raise StopRun(f"No se pudo verificar robots.txt: HTTP {response.status_code}; no se consultaron fichas")
        self.policy = policy
        self.delay = max(self.delay, policy.crawl_delay(AGENT) or 0)
        rate = policy.request_rate(AGENT)
        if rate:
            self.delay = max(self.delay, rate.seconds / rate.requests)

    def profile(self, row):
        url = row["perfil"]
        for _ in range(6):
            if not self.policy or not self.policy.can_fetch(AGENT, url):
                raise StopRun(f"robots.txt no permite consultar {url}")
            response = self.get(url)
            if response.status_code in (301, 302, 303, 307, 308):
                target = urljoin(url, response.headers.get("Location", ""))
                if target == url or profile_id(target) != row["id_funcionario"]:
                    record = base_record(row)
                    record.update(resultado="redireccion_no_permitida", http_status=response.status_code,
                                  error=f"Destino no reconocido: {target}")
                    return record
                url = target
                continue
            record = base_record(row)
            if response.status_code == 200:
                if "html" not in response.headers.get("Content-Type", "").lower():
                    record.update(resultado="contenido_no_html", error="Content-Type inesperado")
                else:
                    record = parse_profile(response.text, row, url)
                    if self.args.save_html:
                        sample_dir = self.args.output_dir / "html"
                        sample_dir.mkdir(parents=True, exist_ok=True)
                        (sample_dir / f"{row['id_funcionario']}.html").write_bytes(response.content)
            else:
                record.update(resultado="bloqueado" if response.status_code in (401, 403, 418, 429, 451)
                              else "error_http", error=f"HTTP {response.status_code}")
            record["http_status"] = response.status_code
            record["fecha_consulta"] = now()
            return record
        record = base_record(row)
        record.update(resultado="error_redireccion", error="Demasiadas redirecciones")
        return record


def connect(path, fingerprint):
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS profiles (url TEXT PRIMARY KEY, result TEXT, payload TEXT)")
    old = db.execute("SELECT value FROM metadata WHERE key='source_sha256'").fetchone()
    if old and old[0] != fingerprint:
        db.close()
        raise ValueError("La fuente cambió; use otro --output-dir para no mezclar bases")
    db.execute("INSERT OR IGNORE INTO metadata VALUES ('source_sha256', ?)", (fingerprint,))
    db.commit()
    return db


def save_record(db, record):
    db.execute("INSERT OR REPLACE INTO profiles VALUES (?, ?, ?)",
               (record["perfil"], record["resultado"], json.dumps(record, ensure_ascii=False)))
    db.commit()  # Checkpoint durable tras cada perfil, incluso antes de exportar CSV.


def export_csv(db, path):
    records = [json.loads(row[0]) for row in db.execute("SELECT payload FROM profiles ORDER BY url")]
    headers = list(dict.fromkeys(ORIGINAL + FIELDS + ["url_oficial", "informacion_adicional", "evidencia",
                "campos_extraidos", "advertencias", "resultado", "error", "http_status", "fecha_consulta"]
                + [k for record in records for k in record]))
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, headers, delimiter=";")
        writer.writeheader()
        for record in records:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                             for k, v in record.items()})
    temporary.replace(path)


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Debe ser un número finito mayor que cero")
    return number


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("Debe ser cero o mayor")
    return number


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SOURCE)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/enriched")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--limit", type=nonnegative, default=10, help="Perfiles nuevos/intentos por lote; 0=todos")
    parser.add_argument("--resume", action="store_true", help="Omitir perfiles con resultado ok")
    parser.add_argument("--save-html", action="store_true", help="Guardar HTML de muestras para validación local")
    parser.add_argument("--delay", type=positive, default=3.0, help="Pausa mínima entre solicitudes (s)")
    parser.add_argument("--retries", type=nonnegative, default=2)
    parser.add_argument("--backoff", type=positive, default=10.0)
    parser.add_argument("--timeout", type=positive, default=30.0)
    parser.add_argument("--max-wait", type=positive, default=300.0)
    parser.add_argument("--pause-every", type=nonnegative, default=100)
    parser.add_argument("--pause-seconds", type=positive, default=60.0)
    return parser.parse_args(argv)


def run(args):
    rows = load_source(args.input)
    fingerprint = hashlib.sha256(args.input.read_bytes()).hexdigest()
    # Impide seleccionar una carpeta que pueda sobrescribir entradas o código.
    output = args.output_dir.resolve()
    reports = args.reports_dir.resolve()
    if not output.is_relative_to((ROOT / "data/enriched").resolve()):
        raise ValueError("--output-dir debe estar dentro de data/enriched/")
    if not reports.is_relative_to((ROOT / "reports").resolve()):
        raise ValueError("--reports-dir debe estar dentro de reports/")
    output.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    db = connect(output / "funcionarios.sqlite3", fingerprint)
    if not args.resume and db.execute("SELECT count(*) FROM profiles").fetchone()[0]:
        db.close()
        raise ValueError("Ya existen resultados: use --resume u otra subcarpeta de salida")
    done = {r[0] for r in db.execute("SELECT url FROM profiles WHERE result='ok'")} if args.resume else set()
    pending = [row for row in rows if row["perfil"] not in done]
    batch = pending[:args.limit] if args.limit else pending
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    report = {"run_id": run_id, "inicio": now(), "fuente_sha256": fingerprint,
              "total_fuente": len(rows), "omitidos_ok": len(done), "seleccionados": len(batch),
              "perfiles_consultados": 0, "resultados": {}, "campos_extraidos": {},
              "estado": "completo", "motivo": "", "parametros": {k: str(v) if isinstance(v, Path) else v
                                                              for k, v in vars(args).items()}}
    counts, fields = Counter(), Counter()
    started = time.monotonic()
    requests_count = 0
    profile_started = None
    batch_pause_seconds = 0.0
    events_path = reports / f"extraccion_{run_id}.jsonl"
    with events_path.open("a", encoding="utf-8") as events:
        def event(value):
            nonlocal requests_count
            if "intento" in value:
                requests_count += 1
            events.write(json.dumps(value, ensure_ascii=False) + "\n")
            events.flush()
            os.fsync(events.fileno())

        client = Client(args, event)
        try:
            if batch:
                client.check_robots()
                profile_started = time.monotonic()
            for row in batch:
                try:
                    record = client.profile(row)
                except StopRun as exc:
                    record = base_record(row)
                    record.update(resultado="detenido", error=str(exc))
                    save_record(db, record)
                    event({"tipo": "resultado_perfil", **record})
                    counts["detenido"] += 1
                    raise
                save_record(db, record)
                event({"tipo": "resultado_perfil", **record})
                counts[record["resultado"]] += 1
                fields.update(record["campos_extraidos"])
                report["perfiles_consultados"] += 1
                print(f"{report['perfiles_consultados']}/{len(batch)} {row['id_funcionario']}: {record['resultado']}", flush=True)
                if record["resultado"] == "bloqueado":
                    raise StopRun(f"Servidor restringe el acceso al perfil: HTTP {record['http_status']}")
                # No continuar miles de solicitudes si la estructura ha cambiado.
                if record["resultado"] == "estructura_no_reconocida":
                    raise StopRun("Estructura no reconocida: revisar una ficha autorizada antes de continuar")
                if args.pause_every and report["perfiles_consultados"] % args.pause_every == 0:
                    if report["perfiles_consultados"] < len(batch):
                        time.sleep(args.pause_seconds)
                        batch_pause_seconds += args.pause_seconds
        except StopRun as exc:
            report.update(estado="detenido", motivo=str(exc))
        except KeyboardInterrupt:
            report.update(estado="interrumpido", motivo="Interrupción del usuario; checkpoint conservado")
        except Exception as exc:
            report.update(estado="error", motivo=f"{type(exc).__name__}: {exc}")
        finally:
            client.session.close()
            report.update(fin=now(), segundos=round(time.monotonic() - started, 3),
                          solicitudes_http=requests_count, resultados=dict(counts), campos_extraidos=dict(fields),
                          delay_efectivo=client.delay)
            report["lote_validado"] = bool(batch) and counts["ok"] == len(batch) and report["estado"] == "completo"
            n = report["perfiles_consultados"]
            report["pausas_programadas_segundos"] = batch_pause_seconds
            report["segundos_por_perfil"] = ((time.monotonic() - profile_started - batch_pause_seconds) / n
                                             if n and profile_started is not None else None)
            report["estimacion_horas_total"] = None
            if n and counts["ok"] == n and report["estado"] == "completo":
                seconds = max(report["segundos_por_perfil"], client.delay)
                pauses = ((len(rows) - 1) // args.pause_every * args.pause_seconds) if args.pause_every else 0
                report["estimacion_horas_total"] = (seconds * len(rows) + pauses) / 3600
            event({"tipo": "fin_ejecucion", **report})
            try:
                export_csv(db, output / "funcionarios_detalle.csv")
            finally:
                db.close()
                report_path = reports / f"extraccion_{run_id}.json"
                report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"Reporte: {report_path}", flush=True)
    return 0 if report["estado"] == "completo" else 2


if __name__ == "__main__":
    try:
        sys.exit(run(arguments()))
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
