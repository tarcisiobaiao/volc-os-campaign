"""Inventário SOMENTE LEITURA das LPs já montadas, contra o template atual.

Uso (de `funnelforge-migracao/engine`):

    python scripts/inventario_lps_historicas.py runs [outro_dir ...]

Para cada run com `p1.elementor.json`, diz se a LP foi montada com o template
e o render atuais (`p1.template.json` = `assinatura_do_template()`). Não
renderiza, não reconstrói, não publica e não lê segredo: só compara a
assinatura gravada no build. LP com assinatura diferente, ou sem registro
(build anterior a 15/10/2026), reprova no portão final como
`lp_template_desatualizado` e só volta a publicar depois de
`funnelforge reconstruir-lp <run_id>`, decidido run a run pelo operador.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from funnelforge.pipeline.lp_template import assinatura_do_template


def classificar(run_dir: Path, atual: str) -> dict:
    registro = run_dir / "p1.template.json"
    construida = ""
    if registro.exists():
        try:
            construida = str(json.loads(registro.read_text(encoding="utf-8")).get("assinatura")
                             or "")
        except (OSError, ValueError, AttributeError):
            construida = ""
    publicadas: list[str] = []
    estado = run_dir / "state.json"
    if estado.exists():
        try:
            publicadas = sorted((json.loads(estado.read_text(encoding="utf-8"))
                                 .get("published") or {}).keys())
        except (OSError, ValueError, AttributeError):
            publicadas = []
    if construida == atual:
        situacao = "atual"
    elif construida:
        situacao = "template_diferente: rebuild antes de publicar"
    else:
        situacao = "sem_registro (build anterior a 15/10/2026): rebuild antes de publicar"
    return {"run": run_dir.name, "situacao": situacao,
            "assinatura": construida[:12] or None, "paginas_publicadas_no_estado": publicadas}


def main(argv: list[str]) -> int:
    atual = assinatura_do_template()
    linhas = []
    for base in (Path(a) for a in (argv or ["runs"])):
        for elementor in sorted(base.glob("*/p1.elementor.json")):
            linhas.append(classificar(elementor.parent, atual))
    print(json.dumps({"template_atual": atual[:12], "lps": linhas},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
