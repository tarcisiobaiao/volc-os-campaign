"""A mudança entrou? — comparar o estado RELIDO com o que a ação pediu.

É a pergunta de `trafego_acompanhamento.momento = 'verificacao'`, e a mesma que
a reversão faz antes de desfazer: se o estado de agora não é o que a aplicação
deixou, alguém mexeu depois, e "restaurar o anterior" apagaria a mudança dessa
pessoa sem ninguém ter visto.

## Tri-estado, como a coluna

`True` confere, `False` não confere, `None` = não dá para dizer pela leitura
(recomendação aplicada: o Google não devolve o que ela mudou). `None` sempre
vem com motivo — a CHECK `trafego_acompanhamento_indeterminado_tem_motivo`
exige, e com razão: indeterminado mudo é indistinguível de "esqueci de olhar".

Lê os MESMOS dicionários que `acao.interpretar_antes` produz — nenhuma GAQL
nova, nenhuma interpretação paralela que possa discordar da do motor.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple

from volc_ads.gestao import acoes as A

Veredito = Tuple[Optional[bool], str]


def _todos(pedidos, existentes, rotulo: str) -> Veredito:
    faltam = [p for p in pedidos if p not in existentes]
    if faltam:
        return False, f"{rotulo} ausente(s) na releitura: {faltam}"
    return True, f"{len(pedidos)} {rotulo} presente(s)"


def conferir_efeito(acao: Any, obs: Mapping[str, Any]) -> Veredito:
    """`(confere, motivo)` para o estado `obs` relido depois da aplicação."""
    if isinstance(acao, A.AlterarStatus):
        if not obs.get("existe"):
            return False, f"{acao.nivel} {acao.ident} não existe mais"
        ok = obs.get("status") == acao.status
        return ok, f"status lido {obs.get('status')}, pedido {acao.status}"
    if isinstance(acao, A.AlterarOrcamento):
        if obs.get("budget_id") != acao.budget_id:
            return False, f"a campanha usa agora o orçamento {obs.get('budget_id')}"
        v = obs.get("verba_diaria_micros")
        return v == acao.amount_micros, f"verba lida {v}, pedida {acao.amount_micros}"
    if isinstance(acao, A.AlterarAlvoDeLance):
        if obs.get("estrategia") != acao.estrategia:
            return False, f"estratégia lida {obs.get('estrategia')}, proposta {acao.estrategia}"
        lido = {"teto_cpc": obs.get("teto_cpc_micros"), "tcpa": obs.get("tcpa_micros"),
                "troas": obs.get("troas")}[acao.alvo]
        return lido == acao.valor, f"{acao.alvo} lido {lido}, pedido {acao.valor}"
    if isinstance(acao, A.TrocarEstrategia):
        if acao.nova == "PORTFOLIO":
            ok = obs.get("portfolio") == acao.portfolio
            return ok, f"portfólio lido {obs.get('portfolio')}, pedido {acao.portfolio}"
        ok = obs.get("estrategia") == acao.nova and not obs.get("portfolio")
        return ok, f"estratégia lida {obs.get('estrategia')}, pedida {acao.nova}"
    if isinstance(acao, (A.AdicionarNegativas, A.ExcluirPlacements)):
        existentes = {tuple(k) for k in obs.get("chaves", [])}
        itens = acao.termos if isinstance(acao, A.AdicionarNegativas) else acao.itens
        return _todos([i.chave for i in itens], existentes, "item")
    if isinstance(acao, A.AdicionarNaLista):
        existentes = {tuple(k) for k in obs.get("chaves", [])}
        # A releitura da lista só enxerga keyword e placement de SITE
        # (`AdicionarNaLista.consultas_antes`). App/YouTube não aparecem nela —
        # dizer "não confere" por isso seria acusar uma ausência que a leitura
        # não sabe ver.
        visiveis = [i for i in acao.itens
                    if isinstance(i, A.Termo) or getattr(i, "tipo", "") == "site"]
        if not visiveis:
            return None, "a releitura da lista não enxerga placements de app/YouTube"
        return _todos([i.chave for i in visiveis], existentes, "item")
    if isinstance(acao, A.CriarListaCompartilhada):
        ids = obs.get("listas_com_mesmo_nome") or []
        return bool(ids), (f"lista {acao.nome!r} encontrada (ids {ids})" if ids
                           else f"lista {acao.nome!r} não encontrada")
    if isinstance(acao, A.AnexarLista):
        return _todos(list(acao.campanhas), set(obs.get("campanhas_vinculadas", [])), "vínculo")
    if isinstance(acao, A.ExcluirIps):
        return _todos(list(acao.ips), set(obs.get("ips_existentes", [])), "IP")
    if isinstance(acao, A.ProgramarAnuncios):
        janelas = obs.get("janelas", [])
        ids = {j["criterion_id"] for j in janelas}
        sobrou = [c for c in acao.remover if c in ids]
        if sobrou:
            return False, f"janela(s) que deviam sair continuam: {sobrou}"
        lidas = {(j["dia"], j["inicio"], j["fim"]) for j in janelas}
        return _todos([(j.dia, j.inicio, j.fim) for j in acao.janelas], lidas, "janela")
    if isinstance(acao, (A.AjustarDispositivo, A.AjustarHorario)):
        if not obs.get("existe"):
            return False, f"critério {acao.criterion_id} não existe mais"
        m = obs.get("modificador")
        m = 1.0 if m is None else m
        return m == acao.modificador, f"ajuste lido {m}, pedido {acao.modificador}"
    if isinstance(acao, A.DispensarRecomendacao):
        if not obs.get("existe"):
            return None, "a recomendação sumiu da conta (expira); não dá para ler a dispensa"
        return bool(obs.get("dispensada")), f"dispensada={obs.get('dispensada')}"
    if isinstance(acao, A.AplicarRecomendacao):
        return None, ("aplicar recomendação não devolve o que mudou; a releitura não "
                      "tem como dizer se o efeito está na conta")
    return None, f"{getattr(acao, 'tipo', acao)!s} sem comparação de efeito"
