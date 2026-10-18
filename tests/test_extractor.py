"""Fixtures sintéticos: no representan HTML real validado de Gob.pe."""
import csv
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from scripts.extract_funcionarios_detalle import (
    Client, StopRun, arguments, connect, export_csv, load_source,
    parse_profile, profile_id, retry_after, save_record, run,
)

ROW = {"pagina": "1", "id_funcionario": "123", "nombre": "Ana María Pérez",
       "entidad_url": "prueba", "perfil": "https://www.gob.pe/institucion/prueba/funcionarios/123-ana-maria-perez"}


def response(status=200, body="", headers=None):
    result = requests.Response()
    result.status_code = status
    result._content = body.encode("utf-8")
    result.encoding = "utf-8"
    result.headers.update(headers or {"Content-Type": "text/html"})
    return result


class ParsingTests(unittest.TestCase):
    def parse(self, html, row=None):
        return parse_profile(html, row or ROW, ROW["perfil"])

    def test_definition_lists_and_originals(self):
        result = self.parse('''<main><h1>Ana María Pérez</h1><dl>
          <dt>Cargo</dt><dd>Directora de Administración</dd>
          <dt>Entidad pública</dt><dd>Instituto de Prueba</dd>
          <dt>Denominación completa</dt><dd>Instituto Nacional de Prueba</dd>
          <dt>Fecha de actualización</dt><dd>15 de octubre de 2026</dd></dl>
          <h2>Funciones</h2><p>Administración institucional.</p></main>''')
        self.assertEqual(result["cargo_publicado"], "Directora de Administración")
        self.assertEqual(result["fecha_actualizacion"], "15 de octubre de 2026")
        self.assertEqual(result["denominacion_completa"], "Instituto Nacional de Prueba")
        self.assertEqual(result["informacion_adicional"]["Funciones"], "Administración institucional.")
        self.assertEqual(result["resultado"], "ok")
        for key, value in ROW.items():
            self.assertEqual(result[key], value)

    def test_jsonld_graph(self):
        node = {"@graph": [{"@type": "Person", "name": "Ana María Pérez",
                 "jobTitle": "Jefa", "worksFor": {"name": "INP", "legalName": "Instituto Nacional de Prueba"}}]}
        result = self.parse('<script type="application/ld+json">' + json.dumps(node) + '</script>')
        self.assertEqual(result["cargo_publicado"], "Jefa")
        self.assertEqual(result["entidad_publica"], "INP")

    def test_observed_gobpe_card_structure(self):
        # Estructura observada el 16/10/2026; valores sintéticos.
        result = self.parse('''<title>Ana María Pérez - Directora - Funcionarios - Instituto de Prueba</title>
          <main><div class="officials__card-links"><h1>Ana María Pérez</h1><div>Directora</div>
          <div aria-describedby="institution-description"><h2><a href="/prueba">Instituto de Prueba</a></h2></div>
          <div><span>Fecha de inicio:</span><span>27 ene 2026</span></div>
          <a href="https://cdn.www.gob.pe/norma.pdf">Norma de nombramiento</a></div>
          <h3>Resumen</h3><div>Trayectoria publicada.</div></main>
          <div class="last-modification">Último cambio&nbsp;05 febrero 2026</div>''')
        self.assertEqual(result["cargo_publicado"], "Directora")
        self.assertEqual(result["denominacion_completa"], "Instituto de Prueba")
        self.assertEqual(result["fecha_actualizacion"], "05 febrero 2026")
        self.assertEqual(result["informacion_adicional"]["Fecha de inicio"], "27 ene 2026")
        self.assertEqual(result["informacion_adicional"]["Resumen"], "Trayectoria publicada.")
        self.assertEqual(result["informacion_adicional"]["norma_nombramiento_url"], "https://cdn.www.gob.pe/norma.pdf")

    def test_microdata_and_dates(self):
        result = self.parse('''<main><h1>Ana María Pérez</h1><div itemprop="jobTitle">Directora</div>
          <time itemprop="dateModified" datetime="2026-10-15">Ayer</time></main>
          <meta property="article:published_time" content="2025-01-01">''')
        self.assertEqual(result["fecha_actualizacion"], "2026-10-15")
        self.assertEqual(result["fecha_publicacion"], "2025-01-01")

    def test_labels_and_entity_link(self):
        result = self.parse('''<main><h1>Ana Maria Perez</h1><p>Cargo: Jefa</p>
          <a href="/institucion/prueba">Instituto de Prueba (INP)</a></main>''')
        self.assertEqual(result["cargo_publicado"], "Jefa")
        self.assertEqual(result["entidad_publica"], "Instituto de Prueba (INP)")
        self.assertEqual(result["denominacion_completa"], "")

    def test_missing_preserves_existing(self):
        row = {**ROW, "cargo_publicado": "Valor previo"}
        result = self.parse('<h1>Ana María Pérez</h1>', row)
        self.assertEqual(result["cargo_publicado"], "Valor previo")
        self.assertEqual(result["resultado"], "parcial")
        self.assertNotIn("cargo_publicado", result["campos_extraidos"])

    def test_unknown_heading_not_invented_as_job(self):
        result = self.parse('<h1>Ana María Pérez</h1><h2>Noticias</h2><p>Una noticia</p>')
        self.assertEqual(result["cargo_publicado"], "")

    def test_no_name_match(self):
        result = self.parse('<h1>Directorio de funcionarios</h1><p>Cargo: Jefa</p>')
        self.assertEqual(result["resultado"], "estructura_no_reconocida")
        self.assertEqual(result["nombre_completo"], ROW["nombre"])

    def test_block_page_with_200(self):
        self.assertEqual(self.parse('<h1>Acceso restringido</h1>')["resultado"], "bloqueado")

    def test_bad_json_and_other_person(self):
        result = self.parse('''<script type="application/ld+json">invalid</script>
          <script type="application/ld+json">{"@type":"Person","name":"Otra Persona","jobTitle":"Ministro"}</script>
          <h1>Ana María Pérez</h1>''')
        self.assertEqual(result["cargo_publicado"], "")
        self.assertTrue(result["advertencias"])

    def test_mismatched_redirect(self):
        result = parse_profile('<h1>Ana María Pérez</h1>', ROW, 'https://www.gob.pe/')
        self.assertEqual(result["resultado"], "perfil_no_coincide")


class NetworkTests(unittest.TestCase):
    def client(self, responses, **overrides):
        args = arguments([])
        for key, value in overrides.items():
            setattr(args, key, value)
        session = Mock()
        session.get.side_effect = responses
        self.events, self.sleeps = [], []
        self.session = session
        return Client(args, self.events.append, session=session, sleep=self.sleeps.append, clock=lambda: 0)

    def test_403_and_418_no_retry(self):
        for status in (403, 418):
            client = self.client([response(status)])
            self.assertEqual(client.get(ROW["perfil"]).status_code, status)
            self.assertEqual(self.session.get.call_count, 1)

    def test_429_retry_after(self):
        client = self.client([response(429, headers={"Retry-After": "30"}), response()])
        self.assertEqual(client.get(ROW["perfil"]).status_code, 200)
        self.assertIn(30, self.sleeps)
        self.assertEqual(len(self.events), 2)

    def test_long_retry_after_stops(self):
        client = self.client([response(429, headers={"Retry-After": "900"})])
        with self.assertRaises(StopRun):
            client.get(ROW["perfil"])
        self.assertEqual(self.session.get.call_count, 1)

    def test_network_failures_bounded(self):
        client = self.client([requests.Timeout("test")] * 3)
        with self.assertRaises(StopRun):
            client.get(ROW["perfil"])
        self.assertEqual(len(self.events), 3)
        self.assertTrue(all(e["error"] for e in self.events))

    def test_robots_blocks_before_profile(self):
        client = self.client([response(403)])
        with self.assertRaises(StopRun):
            client.check_robots()
        self.assertEqual(self.session.get.call_count, 1)

    def test_robots_disallow(self):
        client = self.client([response(200, "User-agent: *\nDisallow: /institucion/", {"Content-Type": "text/plain"})])
        client.check_robots()
        with self.assertRaises(StopRun):
            client.profile(ROW)
        self.assertEqual(self.session.get.call_count, 1)

    def test_robots_crawl_delay(self):
        client = self.client([response(200, "User-agent: *\nCrawl-delay: 8\nAllow: /", {"Content-Type": "text/plain"})])
        client.check_robots()
        self.assertEqual(client.delay, 8)

    def test_external_redirect_not_followed(self):
        client = self.client([response(404), response(302, headers={"Location": "https://example.org"})])
        client.check_robots()
        self.assertEqual(client.profile(ROW)["resultado"], "redireccion_no_permitida")
        self.assertEqual(self.session.get.call_count, 2)

    def test_404_does_not_retry(self):
        client = self.client([response(404), response(404)])
        client.check_robots()
        self.assertEqual(client.profile(ROW)["resultado"], "error_http")
        self.assertEqual(self.session.get.call_count, 2)

    def test_retry_http_date(self):
        date = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=60))
        self.assertGreater(retry_after(date), 58)
        self.assertEqual(retry_after("invalid"), 0)


class PersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (Path(__file__).resolve().parents[1] / "data/enriched").mkdir(parents=True, exist_ok=True)

    def test_resume_does_not_make_network_calls_for_success(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root / "data/enriched") as folder, \
                tempfile.TemporaryDirectory(prefix="extraccion_tests_", dir=root / "reports") as reports:
            path = Path(folder)
            source = path / "source.csv"
            with source.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, ROW.keys(), delimiter=";")
                writer.writeheader()
                writer.writerow(ROW)
            args = arguments(["--input", str(source), "--output-dir", str(path),
                              "--reports-dir", reports, "--resume"])
            with patch('scripts.extract_funcionarios_detalle.Client') as client_type:
                client = client_type.return_value
                client.delay = 3
                client.profile.return_value = parse_profile('<h1>Ana María Pérez</h1><p>Cargo: Jefa</p>', ROW, ROW["perfil"])
                self.assertEqual(run(args), 0)
                self.assertEqual(client.profile.call_count, 1)
                client.reset_mock()
                self.assertEqual(run(args), 0)
                client.profile.assert_not_called()
                client.check_robots.assert_not_called()

    def test_checkpoint_resume_and_export(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "data/enriched") as folder:
            path = Path(folder)
            db = connect(path / "test.sqlite3", "hash")
            record = parse_profile('<h1>Ana María Pérez</h1><p>Cargo: Jefa</p>', ROW, ROW["perfil"])
            save_record(db, record)
            db.close()
            db = connect(path / "test.sqlite3", "hash")
            self.assertEqual(db.execute("SELECT url FROM profiles WHERE result='ok'").fetchall(), [(ROW["perfil"],)])
            export_csv(db, path / "test.csv")
            with (path / "test.csv").open(encoding="utf-8-sig", newline="") as f:
                exported = list(csv.DictReader(f, delimiter=";"))
            self.assertEqual(exported[0]["nombre"], ROW["nombre"])
            self.assertEqual(exported[0]["cargo_publicado"], "Jefa")
            db.close()
            with self.assertRaises(ValueError):
                connect(path / "test.sqlite3", "different")

    def test_source_validation(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "data/enriched") as folder:
            path = Path(folder) / "source.csv"
            with path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, ROW.keys(), delimiter=";")
                writer.writeheader()
                writer.writerow(ROW)
                writer.writerow(ROW)
            with self.assertRaisesRegex(ValueError, "duplicada"):
                load_source(path)

    def test_official_url_validation(self):
        self.assertIsNone(profile_id('http://www.gob.pe/institucion/a/funcionarios/123'))
        self.assertIsNone(profile_id('https://www.gob.pe.evil.com/institucion/a/funcionarios/123'))
        self.assertEqual(profile_id(ROW["perfil"]), "123")


if __name__ == "__main__":
    unittest.main()
