"""Soma de linhas que a RPC enxergaria como o MESMO fato.

`volc_registrar_gads_fatos` identifica o fato por (campanha, dia, hash das
dimensões), e o hash só usa algumas colunas da família. Algumas views da API
têm grão mais fino que essa identidade:

- `detail_placement_view` e `group_placement_view` são por GRUPO de anúncios,
  e a família `placement` não tem `ad_group_id` (a CHECK `_grupo` proíbe);
- `ad_group_ad_asset_view` é por ANÚNCIO, e o contexto `ad_group` guarda o grupo.

Duas linhas com a mesma identidade no mesmo documento não somam no banco: a
segunda empata em precedência e `colhida_em`, cai no `WHERE` do ON CONFLICT e
vira "preterida" — perda silenciosa. Por isso a soma acontece aqui, antes do lote.
"""
from __future__ import annotations

from ._metricas_nucleo import NUCLEO

# As colunas que a RPC põe no hash (v17_01, `v_dims`), mais as da chave única.
IDENTIDADE = (
    "campaign_id", "metric_date",
    "hora", "dispositivo", "rede", "url", "url_tipo", "geo_constant", "local_tipo",
    "placement", "placement_view", "ad_group_id", "termo", "termo_match", "criterion_id",
    "asset_id", "asset_campo", "asset_contexto", "asset_contexto_id",
)


def _somar(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return a + b


def consolidar(linhas: list[dict]) -> list[dict]:
    """Uma linha por identidade, na ordem da primeira ocorrência (o sha do lote
    tem que ser determinístico). Métrica soma (ausente + ausente = ausente);
    atributo fora da identidade só sobrevive se todas as linhas concordam."""
    grupos: dict[tuple, list[dict]] = {}
    for linha in linhas:
        grupos.setdefault(tuple(linha.get(c) for c in IDENTIDADE), []).append(linha)
    saida = []
    for juntas in grupos.values():
        if len(juntas) == 1:
            saida.append(juntas[0])
            continue
        base = dict(juntas[0])
        for outra in juntas[1:]:
            for coluna, valor in outra.items():
                if coluna in NUCLEO:
                    base[coluna] = _somar(base.get(coluna), valor)
                elif coluna == "metricas_extras" or coluna in IDENTIDADE:
                    continue
                elif base.get(coluna) != valor:
                    base[coluna] = None
        base["metricas_extras"] = {**base.get("metricas_extras", {}), "linhas_somadas": len(juntas)}
        saida.append(base)
    return saida
