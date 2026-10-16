"""Integridade: schema drift, source substitution e cobertura de identidade (sensor × campanha).

Equivalentes SQL: `dq_esquema_joinads` (por `schema_fingerprint`), `dq_substituicao_fonte`,
`dq_cobertura_atribuicao_sensor` (só agregados; nenhum `sid`/`pid` sai da view).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from .agenda import LIMIARES_PADRAO
from .modelo import Achado, CoberturaSensorDia, ObservacaoDQ, RunDQ, Severidade, iso

# --------------------------------------------------------------------------- schema drift


def campos_de_payload(payload) -> frozenset[str]:
    """Mesma regra do gatilho `joinads_hash_raw_batch` (192bc065:…20261015163704…:161-198):
    chaves do documento ∪ chaves de cada objeto de `payload` (se array) ou `payload.data`."""
    docs = [payload]
    if isinstance(payload, list):
        docs += payload
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        docs += payload["data"]
    campos: set[str] = set()
    for d in docs:
        if isinstance(d, dict):
            campos.update(d.keys())
    return frozenset(campos)


def checar_deriva_esquema(
    observacoes: Iterable[ObservacaoDQ],
    contrato: Mapping[tuple[str, str, str], frozenset[str]] | None = None,
) -> list[Achado]:
    """Por (fonte, grão, versão do coletor): campos novos (aviso) e ausentes (alto) frente ao
    contrato declarado, ou — sem contrato — frente à primeira leitura daquela versão.
    Mudança de esquema SEM troca de versão é o caso que importa; troca com versão é `info`."""
    grupos: dict[tuple[str, str, str], list[ObservacaoDQ]] = defaultdict(list)
    for o in observacoes:
        if o.campos_payload is None:
            continue
        grupos[(o.fonte, o.grao, str(o.versao_coletor))].append(o)
    achados: list[Achado] = []
    referencia_por_fonte: dict[tuple[str, str], tuple[str, frozenset[str]]] = {}
    for chave in sorted(grupos):
        fonte, grao, versao = chave
        obs = sorted(grupos[chave], key=lambda o: (o.observed_at is None, o.observed_at, o.chave))
        ref = (contrato or {}).get(chave, obs[0].campos_payload)
        novos: set[str] = set()
        ausentes: set[str] = set()
        for o in obs:
            novos |= set(o.campos_payload - ref)
            ausentes |= set(ref - o.campos_payload)
        janela = (iso(obs[0].observed_at), iso(obs[-1].observed_at))
        if ausentes:
            achados.append(Achado("esquema_campo_ausente", Severidade.ALTO, fonte, grao, janela,
                                  {"versao_coletor": versao, "campos": sorted(ausentes)},
                                  f"{fonte}/{grao} v{versao}: campos ausentes {sorted(ausentes)}", chave=versao))
        if novos:
            achados.append(Achado("esquema_campo_novo", Severidade.AVISO, fonte, grao, janela,
                                  {"versao_coletor": versao, "campos": sorted(novos)},
                                  f"{fonte}/{grao} v{versao}: campos novos {sorted(novos)}", chave=versao))
        anterior = referencia_por_fonte.get((fonte, grao))
        if anterior is not None and anterior[1] != ref:
            achados.append(Achado("esquema_mudou_com_versao", Severidade.INFO, fonte, grao, janela,
                                  {"de_versao": anterior[0], "para_versao": versao,
                                   "adicionados": sorted(ref - anterior[1]),
                                   "removidos": sorted(anterior[1] - ref)},
                                  f"{fonte}/{grao}: esquema mudou de v{anterior[0]} para v{versao}", chave=versao))
        referencia_por_fonte[(fonte, grao)] = (versao, ref)
    return achados


# --------------------------------------------------------------------------- source substitution


def checar_substituicao_fonte(
    observacoes: Iterable[ObservacaoDQ],
    runs: Iterable[RunDQ] = (),
    moeda_esperada: Mapping[str, str] | None = None,
) -> list[Achado]:
    """A fonte devolveu outra coisa que não a pedida:
    - `custom_key` devolvido ≠ pedido (observação) ou aviso `custom_key_substituted` do run (a JoinAds v2
      descarta a linha e registra o aviso no recibo do run — 192bc065:n8n/joinads_v2_normalize.js);
    - moeda trocada (mais de uma moeda por fonte × conta, ou diferente da esperada);
    - campanha que aparece em mais de uma conta."""
    obs = list(observacoes)
    achados: list[Achado] = []
    trocas: dict[tuple[str, str, str, str], int] = defaultdict(int)
    for o in obs:
        pedido = o.atributos.get("custom_key_pedido")
        devolvido = o.atributos.get("custom_key")
        if pedido and devolvido and pedido != devolvido:
            trocas[(o.fonte, o.grao, str(pedido), str(devolvido))] += 1
    for (fonte, grao, pedido, devolvido), n in sorted(trocas.items()):
        achados.append(Achado("substituicao_custom_key", Severidade.ALTO, fonte, grao, (None, None),
                              {"pedido": pedido, "devolvido": devolvido, "n": n},
                              f"{fonte}/{grao}: pediu custom_key={pedido}, recebeu {devolvido} ({n}×)",
                              chave=f"{pedido}->{devolvido}"))
    for r in sorted(runs, key=lambda x: x.run_id):
        n = sum(1 for a in r.avisos if a.get("code") == "custom_key_substituted")
        if n:
            achados.append(Achado("substituicao_custom_key_run", Severidade.ALTO, r.fonte, "run",
                                  (iso(r.started_at), iso(r.finished_at)), {"avisos": n, "coletor": r.coletor},
                                  f"run {r.run_id}: {n} linha(s) descartada(s) por custom_key substituída",
                                  chave=r.run_id))
    moedas: dict[tuple[str, str | None], set[str]] = defaultdict(set)
    contas_por_campanha: dict[tuple[str, str], set[str]] = defaultdict(set)
    for o in obs:
        if o.moeda:
            moedas[(o.fonte, o.conta)].add(o.moeda)
        if o.entidade and o.conta:
            contas_por_campanha[(o.fonte, o.entidade)].add(o.conta)
    for (fonte, conta), ms in sorted(moedas.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        esperada = (moeda_esperada or {}).get(fonte)
        fora = sorted(m for m in ms if esperada and m != esperada)
        if len(ms) > 1 or fora:
            achados.append(Achado("substituicao_moeda", Severidade.ALTO, fonte, "conta", (None, None),
                                  {"conta": conta, "moedas": sorted(ms), "esperada": esperada},
                                  f"{fonte} conta {conta}: moedas {sorted(ms)} (esperada {esperada})",
                                  chave=conta))
    for (fonte, campanha), contas in sorted(contas_por_campanha.items()):
        if len(contas) > 1:
            achados.append(Achado("substituicao_campanha_mudou_de_conta", Severidade.ALTO, fonte, "campanha",
                                  (None, None), {"contas": sorted(contas)},
                                  f"{fonte}: campanha {campanha} vista em {len(contas)} contas", chave=campanha))
    return achados


# --------------------------------------------------------------------------- identidade / atribuição


def avaliar_cobertura_atribuicao(
    linhas: Iterable[CoberturaSensorDia],
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
) -> list[tuple[CoberturaSensorDia, float | None, str, str]]:
    """(linha, cobertura, estado, severidade). Cobertura = pagas com utm_campaign / pagas.
    Pagas = 0 ou desconhecido -> cobertura None (não 0); amostra pequena -> `amostra_insuficiente`."""
    lo, alto, amostra = (float(limiares[k]) for k in
                         ("sensor_cobertura_min", "sensor_cobertura_alto", "sensor_amostra_min"))
    saida = []
    for ln in sorted(linhas, key=lambda x: x.dia):
        if not ln.sessoes_pagas or ln.pagas_com_campanha is None:
            saida.append((ln, None, "sem_base", "ok"))
            continue
        cob = round(ln.pagas_com_campanha / ln.sessoes_pagas, 4)
        if ln.sessoes_pagas < amostra:
            estado, sev = "amostra_insuficiente", "info"
        elif cob < alto:
            estado, sev = "cobertura_baixa", "alto"
        elif cob < lo:
            estado, sev = "cobertura_baixa", "aviso"
        else:
            estado, sev = "ok", "ok"
        saida.append((ln, cob, estado, sev))
    return saida


def checar_cobertura_atribuicao(
    linhas: Iterable[CoberturaSensorDia],
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
) -> list[Achado]:
    achados = []
    for ln, cob, estado, sev in avaliar_cobertura_atribuicao(linhas, limiares):
        if sev == "ok":
            continue
        dia = iso(ln.dia)
        achados.append(
            Achado(
                regra=f"atribuicao_sensor_{estado}",
                severidade=Severidade(sev),
                fonte="volc_sensor",
                grao="sessao_dia",
                janela=(dia, dia),
                evidencia={"sessoes_pagas": ln.sessoes_pagas, "pagas_com_campanha": ln.pagas_com_campanha,
                           "pagas_com_source": ln.pagas_com_source, "cobertura": cob},
                mensagem=(f"{dia}: {ln.pagas_com_campanha}/{ln.sessoes_pagas} sessões pagas com utm_campaign"
                          f" (cobertura {cob}) — navegação não junta com campanha"),
            )
        )
    return achados
