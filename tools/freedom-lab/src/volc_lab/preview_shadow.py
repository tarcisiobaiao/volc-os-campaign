"""Gera um preview HTML estático da recomendação shadow a partir do MESMO resultado.json
que um endpoint GET de leitura devolveria. Não tem botão de ação: shadow não executa.

    PYTHONPATH=tools/freedom-lab/src .venv-lab/bin/python -m volc_lab.preview_shadow <dir>
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path


def brl(v):
    return "—" if v is None else f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gerar(d: Path) -> Path:
    r = json.loads((d / "resultado.json").read_text())
    rec, m, q = r["recomendacao"], r["janela_madura"], r["janela_madura_recente"]
    linhas = "".join(f"<li>{html.escape(x)}</li>" for x in rec["motivos"])
    lac = "".join(f"<li>{html.escape(x)}</li>" for x in rec["lacunas"])
    def bloco(t, j):
        if not j["dias"]:
            return f"<section><h3>{t}</h3><p>Nenhum dia reconciliado nesta janela (ausente, não zero).</p></section>"
        return (f"<section><h3>{t}</h3><dl><dt>Dias reconciliados</dt><dd>{j['dias']}</dd>"
                f"<dt>Custo (Google Ads)</dt><dd>{brl(j['custo_brl'])}</dd><dt>Receita bruta (JoinAds)</dt><dd>{brl(j['receita_brl'])}</dd>"
                f"<dt>Contribuição bruta</dt><dd>{brl(j['contribuicao_bruta'])}</dd><dt>ROAS</dt><dd>{j['roas']}</dd>"
                f"<dt>Cliques</dt><dd>{j['cliques']}</dd><dt>CPC / receita por clique</dt><dd>{brl(j['cpc'])} / {brl(j['rpc'])}</dd></dl></section>")
    pagina = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Recomendação em sombra</title><style>
:root{{--bg:#0f1115;--fg:#e8e8ea;--mut:#9aa0a6;--card:#181b21;--warn:#f2b84b;--bad:#ef6b6b}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0;padding:24px 16px;max-width:960px;margin:auto}}
.selo{{display:inline-block;border:1px solid var(--warn);color:var(--warn);border-radius:6px;padding:2px 8px;font-size:12px}}
.dir{{font-size:28px;font-weight:700;color:var(--bad);text-transform:uppercase}} section{{background:var(--card);border-radius:10px;padding:12px 16px;margin:12px 0}}
dl{{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;margin:0}} dt{{color:var(--mut)}} dd{{margin:0}} small{{color:var(--mut)}}
.grade{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}}
</style></head><body>
<span class="selo">SOMBRA · não executada · sem botão de ação</span>
<h1>Campanha {html.escape(rec['campanha'])}</h1>
<p>Direção sugerida: <span class="dir">{html.escape(rec['direcao'])}</span> &nbsp; <small>executada = {str(rec['executada']).lower()} · valor sugerido = {rec['valor_sugerido'] or 'nenhum'}</small></p>
<section><h3>Por quê</h3><ul>{linhas}</ul></section>
<div class="grade">{bloco('Janela madura (até ' + r['corte_maturidade'] + ', exclusive)', m)}{bloco('Últimos 5 dias maduros', q)}</div>
<section><h3>Lacunas declaradas</h3><ul>{lac}</ul></section>
<section><small>Valor de conversão do Google no período: {brl(r['valor_conversao_google_total'])} (valor configurado na conversão, não receita; não entra na decisão).
As-of {r['as_of']}. Contrato: volc_lab.prova_vertical → resultado.json. Parâmetros do laboratório, não política do dono.</small></section>
</body></html>"""
    destino = d / "preview.html"
    destino.write_text(pagina, encoding="utf-8")
    return destino


if __name__ == "__main__":
    print(gerar(Path(sys.argv[1])))
