"""Provas do manifesto n8n sanitizado.

Motivo: o grafo dependia de ``inventario-n8n/flows/*.meta.json``, diretório
gitignored e ausente de qualquer worktree limpa. O manifesto rastreado substitui
essa dependência; estas provas garantem que ele seja determinístico e que a
sanitização falhe fechado em vez de vazar por omissão.
"""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "scripts"))

from gerar_inventario_n8n_sanitizado import (  # noqa: E402
    CAMPOS_PERMITIDOS, ManifestoInvalido, construir, sanitizar,
)

MANIFESTO = RAIZ / "docs" / "volc-os-graph" / "inventario-n8n-sanitizado.json"
CURADORIA = RAIZ / "docs" / "volc-os-graph" / "curadoria-operacional.json"

BASE = {
    "id": "AaBb0011CcDd2233",  # formato de ID n8n, valor sintetico
    "nome": "Apply Bidding - Webhook v2",
    "slug": "atuacao-apply-bidding-webhook-v2",
    "camada": "atuacao",
    "ativo": True,
    "nos": 10,
    "atualizado_em": "2025-12-23T13:03:21.000Z",
    "gatilhos": ["webhook:00000000-0000-4000-8000-000000000000"],  # UUID sintetico, nunca o real
    "tipos_de_no": ["code", "httpRequest", "if", "webhook"],
    "nos_com_codigo": {"Build Mutate Payload": {"linguagem": "js", "linhas": 80}},
    "linhas_de_codigo": 146,
}


def _dir_com(*metas: dict) -> TemporaryDirectory:
    tmp = TemporaryDirectory()
    for i, m in enumerate(metas):
        (Path(tmp.name) / f"{i:02d}-{m['slug']}.meta.json").write_text(json.dumps(m))
    return tmp


class SanitizacaoTest(unittest.TestCase):
    def test_1_geracao_determinista(self):
        with _dir_com(BASE) as d:
            a = construir(Path(d)); b = construir(Path(d))
            self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_2_ordem_independe_da_ordem_dos_arquivos(self):
        z = {**BASE, "slug": "zzz-ultimo", "nome": "Z"}
        a = {**BASE, "slug": "aaa-primeiro", "nome": "A"}
        with _dir_com(z, a) as d1, _dir_com(a, z) as d2:
            s1 = [w["slug"] for w in construir(Path(d1))["workflows"]]
            s2 = [w["slug"] for w in construir(Path(d2))["workflows"]]
            self.assertEqual(s1, s2)
            self.assertEqual(s1, sorted(s1))

    def test_3_mesmo_input_mesmo_sha(self):
        with _dir_com(BASE) as d:
            def sha():
                return hashlib.sha256(
                    json.dumps(construir(Path(d)), ensure_ascii=False, indent=2).encode()
                ).hexdigest()
            self.assertEqual(sha(), sha())

    def test_4_campo_desconhecido_recusado(self):
        with self.assertRaises(ManifestoInvalido) as e:
            sanitizar({**BASE, "campo_novo_do_futuro": "x"}, origem=MANIFESTO)
        self.assertIn("fora do schema", str(e.exception))

    def test_5_slug_duplicado_recusado(self):
        with _dir_com(BASE, {**BASE, "nome": "outro"}) as d:
            with self.assertRaises(ManifestoInvalido) as e:
                construir(Path(d))
            self.assertIn("duplicado", str(e.exception))

    def test_6_manifesto_explica_todo_no_n8n_da_curadoria(self):
        import re
        slugs_curados = set(re.findall(r'"n8n:([a-z0-9-]+)"', CURADORIA.read_text()))
        no_manifesto = {w["slug"] for w in json.loads(MANIFESTO.read_text())["workflows"]}
        self.assertTrue(slugs_curados, "a curadoria deveria referenciar nós n8n")
        self.assertEqual(slugs_curados - no_manifesto, set(),
                         "há nó n8n curado sem registro no manifesto")

    def test_7_segredo_faz_geracao_ser_recusada(self):
        for veneno in (
            {"nome": "Bearer token=abc123 secret"},
            {"nome": "https://n8n.interno.exemplo/webhook/abc"},
            {"nome": "contato@empresa.com"},
            {"nome": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9xxxxx"},
            {"nome": "00000000-0000-4000-8000-000000000000"},
        ):
            with self.subTest(veneno=list(veneno.values())[0][:28]):
                with self.assertRaises(ManifestoInvalido):
                    r = sanitizar({**BASE, **veneno}, origem=MANIFESTO)
                    from gerar_inventario_n8n_sanitizado import auditar_segredos
                    auditar_segredos(r)

    def test_8_caminho_absoluto_nunca_serializado(self):
        texto = MANIFESTO.read_text()
        for prefixo in ("/Users/", "/home/", "/root/", "/private/"):
            self.assertNotIn(prefixo, texto, f"caminho absoluto {prefixo} vazou")

    def test_9_id_real_do_workflow_nao_vaza(self):
        registro = sanitizar(BASE, origem=MANIFESTO)
        self.assertNotIn("id", registro)
        self.assertNotIn(BASE["id"], json.dumps(registro))
        for w in json.loads(MANIFESTO.read_text())["workflows"]:
            self.assertNotIn("id", w)

    def test_10_codigo_de_no_nao_entra(self):
        registro = sanitizar(BASE, origem=MANIFESTO)
        self.assertNotIn("nos_com_codigo", registro)
        self.assertNotIn("Build Mutate Payload", json.dumps(registro, ensure_ascii=False))
        for w in json.loads(MANIFESTO.read_text())["workflows"]:
            self.assertNotIn("nos_com_codigo", w)
            self.assertEqual(set(w) - CAMPOS_PERMITIDOS, set())

    def test_11_gatilho_preserva_tipo_e_descarta_caminho(self):
        registro = sanitizar(BASE, origem=MANIFESTO)
        self.assertEqual(registro["gatilhos_tipos"], ["webhook"])
        self.assertNotIn("00000000-0000", json.dumps(registro))

    def test_12_manifesto_no_disco_bate_com_o_schema(self):
        d = json.loads(MANIFESTO.read_text())
        self.assertEqual(d["total"], len(d["workflows"]))
        self.assertEqual(d["source_kind"], "n8n_legacy_metadata")
        self.assertEqual(len({w["slug"] for w in d["workflows"]}), d["total"],
                         "slug duplicado no manifesto versionado")
        for w in d["workflows"]:
            self.assertEqual(len(w["source_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
