"""JSON ↔ ação do motor, nos dois sentidos — e o segundo é o que importa.

## Ida: o pedido HTTP vira `volc_ads.gestao.acoes.Acao`

O vocabulário é o do motor (`acao.tipo` = `trafego_proposta.operacao`), e a
validação também: este módulo não repete nenhuma regra de `acoes.py`, só
converte tipos JSON em tipos Python e deixa o `__post_init__` da ação recusar.

Dois tipos aceitam um campo a menos e o completam pela LEITURA da conta:
`orcamento.diario` sem `budget_id` e `lance.alvo` sem `estrategia`. O motor já
tem `do_estado()` para isso, e é o certo: o orçamento que vale é o que a
campanha usa HOJE, não o que a tela lembrava.

## Volta: a linha de `trafego_proposta` vira a MESMA ação

`acao_da_proposta()` reconstrói a ação a partir de `operacao`, `alvo_*`,
`valor_atual` e `valor_proposto` — as colunas que o gatilho
`trafego_proposta_diff_imutavel` congela. O que se aplica sai, portanto, do diff
que o humano aprovou, e não de um payload guardado ao lado que ninguém viu.
`testes` provam ida e volta para todos os tipos: `acao_da_proposta(proposta(a))
== a`.

## Verba e lance dizem de onde vieram (`ValorMonetario`)

`orcamento.diario`, `lance.alvo` (tCPA/teto de CPC) e `lance.estrategia` com
alvo em dinheiro exigem `origem` no pedido, e a origem é ESCRITA AQUI, não pela
tela:

· `operador`: só uma identidade de SESSÃO (humano) — serviço não é operador. A
  evidência `operador:<sub>/<papel>@<agora>` sai da identidade autenticada, e
  a justificativa é o `motivo` obrigatório da proposta. Evidência mandada pelo
  cliente é ignorada.
· `medido_na_conta`: só com `medicao = {proposta_id, campo, as_of, sha256}`,
  apontando o "antes" que o próprio backend leu e gravou numa proposta. Aqui se
  confere a forma; o caso de uso confere o registro guardado (hash, as_of,
  valor, mesma campanha) antes de ler a conta. Texto livre não é medição.
· qualquer outra origem (serp, keyword_planner, dataforseo, ferramenta_externa,
  estimativa_modelo): 422 `valor_sem_autoridade`, antes de ler a conta. No tROAS
  (razão, sem origem obrigatória) uma origem que não autoriza também é recusada,
  em vez de descartada em silêncio.

A origem vai gravada em `valor_proposto.origem_valor` e volta com a proposta;
proposta antiga sem ela volta como `nao_informada`: verifica e reverte, mas não
é aprovada nem aplicada, e não segura a chave de idempotência.

`reverso.remover_criados` não entra pela ida: ele só existe como reverso de
outra ação, montado por `ledger.reversao` a partir do que a aplicação criou.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from volc_ads.gestao import acoes as A
from volc_ads.gestao.acoes import AcaoRecusada
from volc_ads.gestao import valor as V
from volc_ads.gestao.valor import ORIGENS_QUE_AUTORIZAM, ValorMonetario, ValorSemAutoridade

from .erros import AcaoInvalida

#: Os 15 tipos que a API aceita, nos 9 grupos do motor. A ordem é a do contrato.
GRUPOS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("1. status", ("status",)),
    ("2. orçamento diário", ("orcamento.diario",)),
    ("3. alvo de lance", ("lance.alvo",)),
    ("4. troca de estratégia", ("lance.estrategia",)),
    ("5. negativas e listas", ("negativa.keyword", "lista.criar", "lista.adicionar",
                               "lista.anexar")),
    ("6. exclusão de placement", ("exclusao.placement",)),
    ("7. exclusão de IP", ("exclusao.ip",)),
    ("8. programação e ajustes", ("programacao.anuncios", "ajuste.dispositivo",
                                  "ajuste.horario")),
    ("9. recomendações", ("recomendacao.aplicar", "recomendacao.dispensar")),
)
TIPOS: Tuple[str, ...] = tuple(t for _, ts in GRUPOS for t in ts)

#: Para a sonda de leitura de `lance.alvo` sem estratégia: a variante MAIS
#: permissiva de cada alvo (todas aceitam 0). Ela só serve para LER; a ação
#: final sai de `AlterarAlvoDeLance.do_estado`, que valida de novo.
_SONDA_DO_ALVO = {"teto_cpc": "TARGET_SPEND", "tcpa": "MAXIMIZE_CONVERSIONS",
                  "troas": "MAXIMIZE_CONVERSION_VALUE"}


@dataclass(frozen=True)
class Pedido:
    """A ação pedida. Se `completar` existe, `acao` é só a SONDA de leitura.

    `completar(antes_dados)` devolve a ação definitiva montada do estado lido.
    """

    acao: Any
    completar: Optional[Callable[[Dict[str, Any]], Any]] = None


def _obrig(d: Mapping[str, Any], campo: str, tipo: str) -> Any:
    if campo not in d or d[campo] is None:
        raise AcaoInvalida(f"{tipo}: falta `{campo}`", detalhe={"campo": campo})
    return d[campo]


def _lista(d: Mapping[str, Any], campo: str, tipo: str, *, obrigatoria: bool = True) -> list:
    v = d.get(campo)
    if v is None and not obrigatoria:
        return []
    if not isinstance(v, list):
        raise AcaoInvalida(f"{tipo}: `{campo}` tem de ser lista", detalhe={"campo": campo})
    return v


def _termo(x: Any) -> A.Termo:
    if not isinstance(x, Mapping):
        raise AcaoInvalida(f"termo tem de ser objeto {{texto, correspondencia}}: {x!r}")
    return A.Termo(x.get("texto"), x.get("correspondencia") or "PHRASE")


def _placement(x: Any) -> A.Placement:
    if not isinstance(x, Mapping):
        raise AcaoInvalida(f"placement tem de ser objeto {{tipo, valor}}: {x!r}")
    return A.Placement(x.get("tipo"), x.get("valor"))


def _janela(x: Any) -> A.Janela:
    if not isinstance(x, Mapping):
        raise AcaoInvalida(f"janela tem de ser objeto {{dia, inicio, fim, modificador}}: {x!r}")
    return A.Janela(x.get("dia"), x.get("inicio"), x.get("fim"), x.get("modificador"))


def _itens_de_lista(tipo_lista: str, itens: list) -> tuple:
    if tipo_lista == "NEGATIVE_KEYWORDS":
        return tuple(_termo(i) for i in itens)
    if tipo_lista == "NEGATIVE_PLACEMENTS":
        return tuple(_placement(i) for i in itens)
    raise AcaoInvalida(f"tipo_lista desconhecido: {tipo_lista!r}",
                       detalhe={"validos": sorted(A.TIPOS_LISTA)})


def _int(v: Any, rotulo: str) -> int:
    """Inteiro JSON. `true` não é 1, e 1.5 não é 1 — o motor recusaria tarde."""
    if isinstance(v, bool) or not isinstance(v, int):
        raise AcaoInvalida(f"{rotulo} tem de ser inteiro: {v!r}")
    return v


@dataclass(frozen=True)
class Ator:
    """Quem pede, como a borda autenticou (`Identidade`). Nunca vem do corpo."""

    sub: str
    papel: str
    origem: str  # "sessao" (humano) ou "servico"


@dataclass(frozen=True)
class Contexto:
    ator: Optional[Ator] = None
    quando: str = ""
    justificativa: str = ""


def _sem_autoridade(tipo: str, campo: str, porque: str, **detalhe: Any) -> AcaoInvalida:
    return AcaoInvalida(f"{tipo}: {porque}", codigo="valor_sem_autoridade",
                        detalhe={"campo": campo, **detalhe})


def _dinheiro(d: Mapping[str, Any], campo: str, tipo: str, ctx: Contexto) -> ValorMonetario:
    """O número do pedido com a origem que o SERVIDOR escreve — e só se ela autoriza."""
    micros = _int(_obrig(d, campo, tipo), campo)
    origem = d.get("origem")
    if not origem:
        raise AcaoInvalida(
            f"{tipo}: `{campo}` sem `origem`. Verba e lance dizem de onde vieram "
            "(operador ou medido_na_conta)", codigo="valor_sem_origem",
            detalhe={"campo": campo})
    try:
        if origem == "operador":
            a = ctx.ator
            if a is None or not a.sub or not ctx.quando:
                raise _sem_autoridade(tipo, campo, "origem operador exige identidade "
                                      "autenticada", origem=origem)
            if a.origem != "sessao":
                raise _sem_autoridade(tipo, campo, "identidade de serviço não é operador: "
                                      "só um humano em sessão autoriza verba ou lance",
                                      origem=origem)
            valor = V.operador(micros, "_".join(a.sub.split()), "_".join(a.papel.split()) or "-",
                               ctx.quando, ctx.justificativa)
        elif origem == "medido_na_conta":
            m = d.get("medicao")
            if not isinstance(m, Mapping) or not all(m.get(k) for k in
                                                     ("proposta_id", "campo", "as_of", "sha256")):
                raise _sem_autoridade(
                    tipo, campo, "medido_na_conta exige `medicao` {proposta_id, campo, as_of, "
                    "sha256} de uma leitura guardada pelo backend; texto livre não é medição",
                    origem=origem)
            valor = ValorMonetario(
                micros, "medido_na_conta",
                f"medicao:trafego_proposta.valor_atual/{m['proposta_id']}#{m['campo']}"
                f"@{m['as_of']} sha256={m['sha256']}")
        else:
            valor = ValorMonetario(micros, str(origem), str(d.get("evidencia") or origem))
        valor.autoriza()
    except ValorSemAutoridade as exc:
        raise _sem_autoridade(tipo, campo, str(exc), origem=origem) from exc
    return valor


def _sem_origem_que_desautoriza(d: Mapping[str, Any], campo: str, tipo: str) -> None:
    """tROAS não exige origem; mas uma origem declarada que não autoriza não some."""
    origem = d.get("origem")
    if origem and origem not in ORIGENS_QUE_AUTORIZAM:
        raise _sem_autoridade(tipo, campo, f"origem {origem!r} não autoriza lance; "
                              "a declaração não é descartada", origem=origem)


def _montar(tipo: str, d: Mapping[str, Any], ctx: Contexto) -> Pedido:
    if tipo == "status":
        return Pedido(A.AlterarStatus(_obrig(d, "nivel", tipo), str(_obrig(d, "ident", tipo)),
                                      _obrig(d, "status", tipo)))
    if tipo == "orcamento.diario":
        cid = _obrig(d, "campaign_id", tipo)
        valor = _dinheiro(d, "amount_micros", tipo, ctx)
        ciente = bool(d.get("compartilhado_ciente", False))
        if d.get("budget_id") is not None:
            return Pedido(A.AlterarOrcamento(cid, d["budget_id"], valor, ciente))
        sonda = A.AlterarOrcamento(cid, 1, valor, ciente)
        return Pedido(sonda, lambda antes: A.AlterarOrcamento.do_estado(
            antes, valor, compartilhado_ciente=ciente))
    if tipo == "lance.alvo":
        cid = _obrig(d, "campaign_id", tipo)
        alvo = _obrig(d, "alvo", tipo)
        # tROAS é razão, não dinheiro: segue sem origem obrigatória (lacuna
        # declarada no W5), mas origem que não autoriza é recusada.
        if alvo == "troas":
            _sem_origem_que_desautoriza(d, "valor", tipo)
            valor = _obrig(d, "valor", tipo)
        else:
            valor = _dinheiro(d, "valor", tipo, ctx)
        if d.get("estrategia"):
            return Pedido(A.AlterarAlvoDeLance(cid, d["estrategia"], alvo, valor))
        if alvo not in _SONDA_DO_ALVO:
            raise AcaoInvalida(f"alvo desconhecido: {alvo!r}",
                               detalhe={"validos": sorted(_SONDA_DO_ALVO)})
        sonda = A.AlterarAlvoDeLance(cid, _SONDA_DO_ALVO[alvo], alvo, valor)
        return Pedido(sonda, lambda antes: A.AlterarAlvoDeLance.do_estado(antes, alvo, valor))
    if tipo == "lance.estrategia":
        _sem_origem_que_desautoriza(d, "troas/alvo", tipo)

        def alvo_em_dinheiro(campo: str) -> Optional[ValorMonetario]:
            # 0/ausente = estratégia sem alvo: não é número que autorize verba.
            if not _int(d.get(campo, 0) or 0, campo):
                return None
            return _dinheiro(d, campo, tipo, ctx)

        return Pedido(A.TrocarEstrategia(
            _obrig(d, "campaign_id", tipo), _obrig(d, "nova", tipo),
            tcpa=alvo_em_dinheiro("tcpa_micros"),
            troas=float(d.get("troas", 0.0) or 0.0),
            teto_cpc=alvo_em_dinheiro("teto_cpc_micros"),
            portfolio=str(d.get("portfolio") or "")))
    if tipo == "negativa.keyword":
        return Pedido(A.AdicionarNegativas(
            _obrig(d, "escopo", tipo), _obrig(d, "alvo", tipo),
            tuple(_termo(t) for t in _lista(d, "termos", tipo))))
    if tipo == "lista.criar":
        tl = _obrig(d, "tipo_lista", tipo)
        return Pedido(A.CriarListaCompartilhada(
            tl, _obrig(d, "nome", tipo), _itens_de_lista(tl, _lista(d, "itens", tipo)),
            tuple(_lista(d, "campanhas", tipo, obrigatoria=False))))
    if tipo == "lista.adicionar":
        tl = _obrig(d, "tipo_lista", tipo)
        return Pedido(A.AdicionarNaLista(_obrig(d, "shared_set_id", tipo), tl,
                                         _itens_de_lista(tl, _lista(d, "itens", tipo))))
    if tipo == "lista.anexar":
        return Pedido(A.AnexarLista(_obrig(d, "shared_set_id", tipo),
                                    tuple(_lista(d, "campanhas", tipo))))
    if tipo == "exclusao.placement":
        return Pedido(A.ExcluirPlacements(
            _obrig(d, "escopo", tipo), tuple(_placement(p) for p in _lista(d, "itens", tipo)),
            d.get("campaign_id")))
    if tipo == "exclusao.ip":
        return Pedido(A.ExcluirIps(_obrig(d, "escopo", tipo),
                                   tuple(str(i) for i in _lista(d, "ips", tipo)),
                                   d.get("campaign_id")))
    if tipo == "programacao.anuncios":
        cid = _obrig(d, "campaign_id", tipo)
        janelas = tuple(_janela(j) for j in _lista(d, "janelas", tipo, obrigatoria=False))
        if d.get("substituir"):
            # "Substituir" = remover TODAS as janelas lidas agora + criar as novas,
            # na mesma ação — para o reverso saber recriar exatamente as removidas.
            sonda = A.ProgramarAnuncios(cid, janelas or (A.Janela("MONDAY", "00:00", "00:15"),))
            return Pedido(sonda, lambda antes: A.ProgramarAnuncios.substituindo(
                antes, cid, janelas))
        return Pedido(A.ProgramarAnuncios(cid, janelas,
                                          tuple(_lista(d, "remover", tipo, obrigatoria=False))))
    if tipo == "ajuste.dispositivo":
        return Pedido(A.AjustarDispositivo.de(_obrig(d, "campaign_id", tipo),
                                              _obrig(d, "dispositivo", tipo),
                                              _obrig(d, "modificador", tipo)))
    if tipo == "ajuste.horario":
        return Pedido(A.AjustarHorario(_obrig(d, "campaign_id", tipo),
                                       _obrig(d, "criterion_id", tipo),
                                       _obrig(d, "modificador", tipo)))
    if tipo == "recomendacao.aplicar":
        return Pedido(A.AplicarRecomendacao(_obrig(d, "recurso", tipo)))
    if tipo == "recomendacao.dispensar":
        return Pedido(A.DispensarRecomendacao(_obrig(d, "recurso", tipo)))
    raise AcaoInvalida(f"tipo de ação desconhecido: {tipo!r}", detalhe={"validos": list(TIPOS)})


def pedido_do_payload(payload: Mapping[str, Any], *, ator: Optional[Ator] = None,
                      quando: str = "", justificativa: str = "") -> Pedido:
    """`{"tipo": ..., <campos do tipo>}` → `Pedido`. 422 em qualquer recusa local.

    `ator`/`quando`/`justificativa` escrevem a origem `operador` (ver o topo).
    """
    if not isinstance(payload, Mapping):
        raise AcaoInvalida("`acao` tem de ser objeto com `tipo`")
    tipo = str(payload.get("tipo") or "")
    try:
        return _montar(tipo, payload, Contexto(ator, quando, justificativa))
    except AcaoInvalida:
        raise
    except ValorSemAutoridade as exc:
        raise AcaoInvalida(f"{tipo}: {exc}", codigo="valor_sem_autoridade") from exc
    except (AcaoRecusada, TypeError, ValueError) as exc:
        raise AcaoInvalida(f"{tipo}: {exc}") from exc


# ── volta: a proposta gravada vira a mesma ação ─────────────────────────────


def _cid_do_alvo(linha: Mapping[str, Any]) -> int:
    return int(str(linha["alvo_id_externo"]))


def _dinheiro_gravado(linha: Mapping[str, Any], vp: Mapping[str, Any],
                     micros: Any) -> ValorMonetario:
    """O número gravado com a origem gravada. Sem `origem_valor` (proposta de
    antes do W5), `nao_informada`: reconstrói, verifica e reverte, mas não aplica."""
    o = vp.get("origem_valor")
    if isinstance(o, Mapping) and o.get("origem"):
        return ValorMonetario(micros, str(o["origem"]), str(o.get("evidencia") or ""),
                              str(o.get("justificativa") or ""))
    return ValorMonetario(micros, "nao_informada",
                          f"proposta {linha.get('proposta_id')} gravada sem origem_valor")


def acao_da_proposta(linha: Mapping[str, Any]) -> Any:
    """A ação que esta linha de `trafego_proposta` descreve. Determinística.

    ⚠️ `compartilhado_ciente` do orçamento não é coluna — e não precisa ser: a
    proposta sobre orçamento compartilhado SÓ pôde nascer com ciência (o
    `conferir` da proposta recusaria). Logo, ela é derivada do `valor_atual`
    congelado, e não de um booleano que a tela poderia mandar diferente.
    """
    op = str(linha.get("operacao") or "")
    vp: Mapping[str, Any] = linha.get("valor_proposto") or {}
    va: Mapping[str, Any] = linha.get("valor_atual") or {}
    nivel = str(linha.get("alvo_nivel") or "")
    alvo = str(linha.get("alvo_id_externo") or "")
    try:
        if op == "status":
            return A.AlterarStatus(nivel, alvo, vp["status"])
        if op == "orcamento.diario":
            ciente = bool(va.get("compartilhado")) or int(va.get("campanhas_no_orcamento") or 1) > 1
            return A.AlterarOrcamento(_cid_do_alvo(linha), vp["budget_id"],
                                      _dinheiro_gravado(linha, vp, vp["verba_diaria_micros"]),
                                      ciente)
        if op == "lance.alvo":
            qual = next(k for k in ("teto_cpc", "tcpa", "troas") if k in vp)
            lance = vp[qual] if qual == "troas" else _dinheiro_gravado(linha, vp, vp[qual])
            return A.AlterarAlvoDeLance(_cid_do_alvo(linha), vp["estrategia"], qual, lance)
        if op == "lance.estrategia":
            def gravado(campo: str) -> Optional[ValorMonetario]:
                return _dinheiro_gravado(linha, vp, vp[campo]) if vp.get(campo) else None

            return A.TrocarEstrategia(_cid_do_alvo(linha), vp["estrategia"],
                                      tcpa=gravado("tcpa_micros"),
                                      troas=float(vp.get("troas", 0.0)),
                                      teto_cpc=gravado("teto_cpc_micros"),
                                      portfolio=vp.get("portfolio", ""))
        if op == "negativa.keyword":
            return A.AdicionarNegativas(vp["escopo"], alvo,
                                        tuple(_termo(t) for t in vp["adicionar"]))
        if op == "lista.criar":
            return A.CriarListaCompartilhada(vp["tipo"], vp["lista"],
                                             _itens_de_lista(vp["tipo"], list(vp["itens"])),
                                             tuple(vp.get("campanhas") or ()))
        if op == "lista.adicionar":
            itens = list(vp["adicionar"])
            tl = va.get("tipo") or ("NEGATIVE_KEYWORDS" if itens and "texto" in itens[0]
                                    else "NEGATIVE_PLACEMENTS")
            return A.AdicionarNaLista(vp["lista"], tl, _itens_de_lista(tl, itens))
        if op == "lista.anexar":
            return A.AnexarLista(vp["lista"], tuple(vp["anexar"]))
        if op == "exclusao.placement":
            return A.ExcluirPlacements(vp["escopo"], tuple(_placement(p) for p in vp["excluir"]),
                                       int(alvo) if vp["escopo"] == "campanha" else None)
        if op == "exclusao.ip":
            return A.ExcluirIps(vp["escopo"], tuple(vp["excluir_ips"]),
                                int(alvo) if vp["escopo"] == "campanha" else None)
        if op == "programacao.anuncios":
            return A.ProgramarAnuncios(_cid_do_alvo(linha),
                                       tuple(_janela(j) for j in vp.get("criar") or ()),
                                       tuple(vp.get("remover") or ()))
        if op == "ajuste.dispositivo":
            return A.AjustarDispositivo.de(_cid_do_alvo(linha), vp["dispositivo"],
                                           vp["modificador"])
        if op == "ajuste.horario":
            return A.AjustarHorario(_cid_do_alvo(linha), vp["criterion_id"], vp["modificador"])
        if op == "recomendacao.aplicar":
            return A.AplicarRecomendacao(vp["aplicar"])
        if op == "recomendacao.dispensar":
            return A.DispensarRecomendacao(vp["dispensar"])
    except (KeyError, StopIteration, AcaoRecusada, TypeError, ValueError) as exc:
        raise AcaoInvalida(
            f"a proposta {linha.get('proposta_id')} ({op}) não reconstrói uma ação: {exc}",
            codigo="proposta_ilegivel") from exc
    raise AcaoInvalida(f"operação {op!r} não é da gestão", codigo="proposta_ilegivel")


def customer_id_da_proposta(linha: Mapping[str, Any]) -> str:
    """`alvo_chave` é `google_ads:<customer>:<nivel>:<alvo>` (ledger.alvo_chave).

    `maxsplit` porque o alvo pode ter `:` (`lista:<nome>`).
    """
    partes = str(linha.get("alvo_chave") or "").split(":", 3)
    if len(partes) != 4 or partes[0] != "google_ads" or not partes[1].isdigit():
        raise AcaoInvalida(f"alvo_chave fora do formato da gestão: {linha.get('alvo_chave')!r}",
                           codigo="proposta_ilegivel")
    return partes[1]
