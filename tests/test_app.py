"""Pruebas con la base real; no modifican archivos de datos."""
import hashlib
import io
from pathlib import Path
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

from app.app import DATA_PATH, COLUMNS, entity_counts, export_csv, filter_data, load_data


class RadarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = load_data(str(DATA_PATH), DATA_PATH.stat().st_mtime_ns)

    def test_verified_dataset_and_integrity(self):
        self.assertEqual(len(self.df), 41866)
        self.assertEqual(self.df.id_funcionario.nunique(), 41866)
        self.assertEqual(self.df.entidad_url.nunique(), 2829)
        self.assertEqual(set(self.df.pagina), set(range(1, 2095)))
        self.assertEqual(hashlib.sha256(DATA_PATH.read_bytes()).hexdigest(),
                         "730243e2cff29a04fee24c0a608d14ca9274e0efe4eeeac5c94d0977c787b757")

    def test_search_accents_case_order_and_entities(self):
        expected = filter_data(self.df, "José Alberto Valega Sáenz", [])
        actual = filter_data(self.df, "  SAENZ   jose VALEGA alberto ", ["acffaa"])
        self.assertGreater(len(actual), 0)
        self.assertEqual(set(actual.id_funcionario), set(expected.id_funcionario))
        self.assertEqual(set(actual.entidad_url), {"acffaa"})
        self.assertTrue(filter_data(self.df, "zzzzsincoincidenciazzzz", []).empty)
        self.assertTrue(filter_data(self.df, ".*", []).empty)
        self.assertEqual(len(filter_data(self.df, "   ", [])), 41866)
        selected = filter_data(self.df, "", ["acffaa", "pcm"])
        self.assertEqual(set(selected.entidad_url), {"acffaa", "pcm"})

    def test_export_and_counts(self):
        selected = filter_data(self.df, "jose", ["acffaa"])
        exported = export_csv(selected)
        self.assertTrue(exported.startswith(b"\xef\xbb\xbf"))
        recovered = pd.read_csv(io.BytesIO(exported), sep=";", dtype=str, keep_default_na=False)
        pd.testing.assert_frame_equal(recovered, selected[COLUMNS].astype(str).reset_index(drop=True))
        counts = entity_counts(self.df)
        self.assertEqual(len(counts), 2829)
        self.assertEqual(counts.perfiles.sum(), 41866)
        self.assertTrue(counts.perfiles.is_monotonic_decreasing)
        self.assertEqual(len(entity_counts(self.df.iloc[:0])), 0)

    def test_dashboard_interaction(self):
        at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/app.py"), default_timeout=30).run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual([m.value for m in at.metric], ["41,866", "2,829", "1 – 2,094"])
        self.assertEqual(len(at.dataframe[0].value), 41866)
        self.assertEqual(len(at.dataframe[1].value), 2829)
        at.text_input(key="query").set_value("SAENZ jose VALEGA alberto")
        at.multiselect(key="entities").set_value(["acffaa"]).run()
        self.assertEqual(len(at.exception), 0)
        self.assertGreater(len(at.dataframe[0].value), 0)
        self.assertEqual(set(at.dataframe[0].value.entidad_url), {"acffaa"})
        at.text_input(key="query").set_value("zzzzsincoincidenciazzzz").run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(at.dataframe[0].value.empty)
        self.assertTrue(at.get("download_button")[0].proto.disabled)
        at.text_input(key="query").set_value("")
        at.multiselect(key="entities").set_value([]).run()
        self.assertEqual(len(at.dataframe[0].value), 41866)


if __name__ == "__main__":
    unittest.main()
