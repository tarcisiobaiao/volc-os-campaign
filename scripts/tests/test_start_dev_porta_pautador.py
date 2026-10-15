"""Prova hermetica: o front sobe apontando para o backend que o start-dev.sh sobe.

Medido em 15/10/2026: `.env.local` (symlink para o env local do operador)
trazia `VITE_PAUTADOR_API_URL=http://localhost:8011`, sobra de uma sessao que
rodava o FastAPI na 8011. O Vite da a `.env.local` precedencia sobre `.env`,
entao o front chamava a 8011 enquanto o `start-dev.sh` subia o backend na 8010:
Pautador, Redator, Criativos, Trafego, Integracoes, Cofre e QG abriam com
status 0, sem quebrar nenhum /health.

O teste roda o `start-dev.sh` de verdade numa copia, com `node`, `npm`,
`python3`, `lsof` e `uvicorn` trocados por dubles que so registram o que
receberam. Nada sobe, nenhuma porta e liberada, nenhum segredo e lido.
"""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "start-dev.sh"


def _executavel(caminho: Path, corpo: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("#!/usr/bin/env bash\n" + corpo + "\n")
    caminho.chmod(caminho.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class StartDevPortaPautadorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name) / "repo"
        self.raiz.mkdir()
        shutil.copy2(SCRIPT, self.raiz / "start-dev.sh")
        (self.raiz / ".env.server").write_text("# duble, sem chaves\n")
        (self.raiz / "node_modules").mkdir()
        (self.raiz / "backend").mkdir()
        self.registro = Path(tmp.name) / "registro"
        self.registro.mkdir()
        _executavel(
            self.raiz / "backend/.venv/bin/uvicorn",
            f'echo "$@" > "{self.registro}/uvicorn"',
        )
        self.bin = Path(tmp.name) / "bin"
        _executavel(
            self.bin / "npm",
            f'printf "%s" "${{VITE_PAUTADOR_API_URL-<ausente>}}" > "{self.registro}/vite_url"',
        )
        for nome in ("node", "python3", "lsof"):
            _executavel(self.bin / nome, "exit 0")

    def rodar(self, *args, env_local=None, extra_env=None):
        if env_local is not None:
            (self.raiz / ".env.local").write_text(env_local)
        env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.raiz),
            "PAUTADOR_PORT": "18010",
            **(extra_env or {}),
        }
        return subprocess.run(
            ["bash", str(self.raiz / "start-dev.sh"), *args],
            env=env, capture_output=True, text=True, timeout=30,
        )

    def url_do_front(self) -> str:
        return (self.registro / "vite_url").read_text()

    def test_front_aponta_para_a_porta_do_backend_que_subiu(self):
        r = self.rodar(env_local="VITE_PAUTADOR_API_URL=http://localhost:8011\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--port 18010", (self.registro / "uvicorn").read_text())
        self.assertEqual(self.url_do_front(), "http://localhost:18010")

    def test_divergencia_do_env_local_e_avisada(self):
        r = self.rodar(env_local="VITE_PAUTADOR_API_URL=http://localhost:8011\n")
        self.assertIn("http://localhost:8011", r.stdout)
        self.assertIn("http://localhost:18010", r.stdout)

    def test_env_local_sem_a_chave_cai_para_o_env(self):
        (self.raiz / ".env").write_text("VITE_PAUTADOR_API_URL=http://localhost:8011\n")
        r = self.rodar(env_local="OUTRA=1\n")
        self.assertIn(".env define VITE_PAUTADOR_API_URL=http://localhost:8011", r.stdout)
        self.assertEqual(self.url_do_front(), "http://localhost:18010")

    def test_sem_backend_nao_sobrescreve_a_url_configurada(self):
        r = self.rodar(
            "--skip-backend",
            env_local="VITE_PAUTADOR_API_URL=https://remoto.example\n",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.registro / "uvicorn").exists())
        # O Vite le o .env.local sozinho; o script nao injeta nada.
        self.assertEqual(self.url_do_front(), "<ausente>")


if __name__ == "__main__":
    unittest.main()
