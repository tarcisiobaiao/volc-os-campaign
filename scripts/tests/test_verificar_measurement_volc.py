from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path
import unittest


RAIZ = Path(__file__).resolve().parents[2]
CAMINHO = RAIZ / "scripts" / "verificar_measurement_volc.py"
SPEC = importlib.util.spec_from_file_location("verificar_measurement_volc", CAMINHO)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class MeasurementContractTest(unittest.TestCase):
    def test_normalizacao_ignora_so_bordas_e_quebra_windows(self) -> None:
        self.assertEqual(MOD._normalizar_html("\r\n<script>ok</script>\r\n"), "<script>ok</script>")
        self.assertEqual(MOD._normalizar_html("<script>\n \n</script>"), "<script>\n\n</script>")
        self.assertNotEqual(MOD._normalizar_html("<script> a </script>"), MOD._normalizar_html("<script>a</script>"))

    def test_sha_do_manifesto_bate_com_as_fontes(self) -> None:
        manifesto = json.loads((RAIZ / "measurement" / "gtm" / "manifest.json").read_text())
        fontes = {item["name"]: RAIZ / item["source"] for item in manifesto["tags"]}
        self.assertEqual(set(fontes), {"VOLC Sensor v3.3", "WEBS Wrapper v2"})
        self.assertTrue(all(caminho.is_file() for caminho in fontes.values()))
        self.assertTrue(all(len(MOD._sha256_texto(caminho.read_text())) == 64 for caminho in fontes.values()))

    def test_contratos_de_seguranca_ficam_versionados(self) -> None:
        sensor = (RAIZ / "measurement" / "gtm" / "volc-sensor-v3.html").read_text()
        edge = (RAIZ / "supabase" / "functions" / "volc-ingest" / "index.ts").read_text()
        migration = (RAIZ / "supabase" / "migrations" / "20261015153301_harden_volc_measurement.sql").read_text()
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", sensor)
        self.assertIn("database.agenciavolc.com.br/functions/v1/volc-ingest", sensor)
        self.assertIn("EVENT_FIELDS", edge)
        self.assertIn("origin_not_allowed", edge)
        self.assertIn("MAX_BODY_BYTES", edge)
        self.assertIn("force row level security", migration.lower())
        self.assertIn("revoke all privileges on table public.raw_events from anon", migration.lower())

    def test_v31_tem_sequencia_idempotente(self) -> None:
        sensor = (RAIZ / "measurement" / "gtm" / "volc-sensor-v3.html").read_text()
        edge = (RAIZ / "supabase" / "functions" / "volc-ingest" / "index.ts").read_text()
        migration = (RAIZ / "supabase" / "migrations" / "20261016155958_measurement_event_id_v31.sql").read_text()
        self.assertIn("v: '3.1'", sensor)
        self.assertIn("seq: ++eventSeq", sensor)
        self.assertIn("event_seq: eventSeq ?? 0", edge)
        self.assertIn('onConflict: "sid,pid,event_name,ts_sec,event_seq"', edge)
        self.assertIn("sid, pid, event_name, ts_sec, event_seq", migration)

    def test_parse_data_converte_para_utc(self) -> None:
        data = MOD._parse_data("2026-10-16T12:32:32.236-03:00")
        self.assertEqual(data.tzinfo, dt.timezone.utc)
        self.assertEqual(data.hour, 15)


if __name__ == "__main__":
    unittest.main()
