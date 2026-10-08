"""N ações de gestão num só `MutateGoogleAdsRequest`, com `partial_failure=True`.

## Por que partial failure aqui, e só aqui

O nascimento (`gads.client.mutar`) é atômico: campanha meio criada é pior que
campanha nenhuma. A gestão é o contrário. Num lote de 40 negativas, 1 recusada
por política não pode segurar as outras 39; numa rodada que pausa 6 grupos e
sobe 2 orçamentos, um orçamento abaixo do piso não pode deixar os 6 grupos
gastando. Cada ação tem a sua proposta e a sua aprovação no ledger — o
desfecho tem de ser por ação também.

## Como a falha volta para a ação

Com `partial_failure`, a API não levanta: devolve `partial_failure_error`
(um `google.rpc.Status`) cujos `details` carregam um `GoogleAdsFailure`. Cada
erro tem `location.field_path_elements[0] = mutate_operations[i]`, e `i` é o
índice da OPERAÇÃO, não da ação. Uma ação pode montar várias operações
(lista compartilhada = 1 + itens + vínculos), então o plano guarda a faixa
[início, fim) de cada ação, e o índice volta para a ação pela faixa.

Uma ação com algumas operações aceitas e outras não fica `parcial` — e os
resource names das aceitas vêm junto, porque é com eles que o reverso limpa.

## Por que este arquivo tem o próprio envio (e não usa `client.mutar`)

`client.mutar()` fixa `partial_failure=False` — e deve continuar fixando, é o
contrato do nascimento. `enviar()` aqui reproduz a MESMA trava
(`modo.exigir_leitura_apenas` antes de montar a requisição real) e o mesmo
retry tipado (`client.executar`). Sugestão registrada: mover para
`gads.client` um `mutar_em_lote(..., partial_failure=True)` irmão de `mutar`,
para que a porta de escrita continue sendo um arquivo só.

## Recomendações

`RecommendationService.ApplyRecommendation/DismissRecommendation` não é
`GoogleAdsService.Mutate` e NÃO tem `validate_only` na v25. No ensaio, essas
ações saem `nao_validavel` sem chamada nenhuma; a aplicação real tem função
própria (`aplicar_recomendacoes`), atrás da mesma trava.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import count
from typing import Any, Sequence

from volc_ads.gads import modo
from volc_ads.gads.errors import ErroGads, FalhaGads, classificar

from .acoes import Acao, AcaoRecusada

DESFECHOS = ("ok", "parcial", "falhou", "nao_validavel")


class LoteRecusado(ValueError):
    """O lote não sai: duas ações brigam pelo mesmo campo, ou ação fora do mutate."""


# ── plano: função pura ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Plano:
    customer_id: str
    acoes: tuple[Acao, ...]
    operacoes: tuple[Any, ...]
    faixas: tuple[tuple[int, int], ...]

    def acao_da_operacao(self, indice: int) -> int | None:
        for i, (ini, fim) in enumerate(self.faixas):
            if ini <= indice < fim:
                return i
        return None


def _conferir_conflitos(acoes: Sequence[Acao], customer_id: str) -> None:
    """Dois `(recurso, campo)` iguais no mesmo lote = a segunda sobrescreve a
    primeira e o ledger registra dois sucessos. "*" (remoção) conflita com
    qualquer campo do mesmo recurso."""
    dono: dict[str, dict[str, int]] = {}
    for i, a in enumerate(acoes):
        for rn, campo in a.campos_alterados(customer_id):
            campos = dono.setdefault(rn, {})
            colide = [j for c, j in campos.items() if c == campo or "*" in (c, campo)]
            if colide:
                raise LoteRecusado(
                    f"ações {colide[0]} e {i} alteram {rn} ({campo}) no mesmo lote")
            campos[campo] = i


def montar(acoes: Sequence[Acao], get_type: Any, customer_id: str) -> Plano:
    """As operações do lote, na ordem das ações, com a faixa de cada uma.

    Os ids temporários são do LOTE (−1, −2, …): duas listas criadas no mesmo
    lote não podem disputar o −1.
    """
    cid = str(customer_id)
    acoes = tuple(acoes)
    if not acoes:
        raise LoteRecusado("lote vazio")
    fora = [a.tipo for a in acoes if a.fora_do_mutate]
    if fora:
        raise LoteRecusado(f"{fora} não são GoogleAdsService.Mutate; use aplicar_recomendacoes")
    _conferir_conflitos(acoes, cid)
    temp = count(-1, -1)
    ops: list[Any] = []
    faixas: list[tuple[int, int]] = []
    for a in acoes:
        novas = a.operacoes(get_type, cid, lambda: next(temp))
        if not novas:
            raise AcaoRecusada(f"{a.tipo} não montou operação nenhuma")
        faixas.append((len(ops), len(ops) + len(novas)))
        ops.extend(novas)
    return Plano(cid, acoes, tuple(ops), tuple(faixas))


# ── leitura da resposta: função pura ────────────────────────────────────────


class _ExcecaoComFalha:
    """O mínimo que `errors.classificar` lê de uma GoogleAdsException."""

    def __init__(self, failure: Any, request_id: str = ""):
        self.failure = failure
        self.request_id = request_id


def falhas_parciais(resposta: Any, request_id: str = "") -> tuple[ErroGads, ...]:
    """Os erros de `partial_failure_error`, já classificados e com o índice.

    `partial_failure_error` é um `google.rpc.Status` cru (pb2, não proto-plus);
    o `GoogleAdsFailure` vem serializado dentro de `details` como `Any`.
    """
    from google.ads.googleads.v25.errors.types.errors import GoogleAdsFailure  # noqa: PLC0415

    pb = getattr(resposta, "_pb", resposta)
    try:
        if not pb.HasField("partial_failure_error"):
            return ()
    except ValueError:
        return ()
    status = pb.partial_failure_error
    erros: list[ErroGads] = []
    for detalhe in status.details:
        if not detalhe.type_url.endswith("GoogleAdsFailure"):
            continue
        falha = GoogleAdsFailure.deserialize(detalhe.value)
        erros.extend(classificar(_ExcecaoComFalha(falha, request_id)).erros)
    if not erros and status.code:
        # Status sem GoogleAdsFailure legível: não é "sem erro".
        erros.append(ErroGads(campo_codigo="request_error", valor_codigo=str(status.code),
                              mensagem=status.message or "partial_failure_error ilegível"))
    return tuple(erros)


def _recurso_da_resposta(resposta_op: Any) -> str:
    pb = getattr(resposta_op, "_pb", resposta_op)
    qual = pb.WhichOneof("response")
    return getattr(getattr(pb, qual), "resource_name", "") if qual else ""


@dataclass(frozen=True)
class ResultadoAcao:
    acao: Acao
    desfecho: str
    erros: tuple[ErroGads, ...] = ()
    #: resource names devolvidos pelas operações aceitas (vazio no ensaio).
    recursos: tuple[str, ...] = ()
    faixa: tuple[int, int] | None = None
    motivo: str = ""

    def resumo(self) -> str:
        cab = f"[{self.desfecho}] {self.acao.descrever()}"
        if self.motivo:
            cab += f" — {self.motivo}"
        return "\n".join([cab, *(f"    {e.resumo()}" for e in self.erros)])


@dataclass(frozen=True)
class ResultadoLote:
    customer_id: str
    validate_only: bool
    acoes: tuple[ResultadoAcao, ...]
    #: erros sem índice de operação (requisição recusada inteira).
    erros_gerais: tuple[ErroGads, ...] = ()
    request_id: str = ""

    @property
    def tudo_ok(self) -> bool:
        return all(r.desfecho == "ok" for r in self.acoes)

    def por_desfecho(self, desfecho: str) -> tuple[ResultadoAcao, ...]:
        return tuple(r for r in self.acoes if r.desfecho == desfecho)

    def resumo(self) -> str:
        modo_ = "validate_only" if self.validate_only else "REAL"
        linhas = [f"lote {modo_} em {self.customer_id}: "
                  + ", ".join(f"{d}={len(self.por_desfecho(d))}" for d in DESFECHOS)]
        linhas += [f"  geral: {e.resumo()}" for e in self.erros_gerais]
        linhas += ["  " + r.resumo() for r in self.acoes]
        return "\n".join(linhas)


def mapear(plano: Plano, *, validate_only: bool, resposta: Any = None,
           falha: FalhaGads | None = None) -> ResultadoLote:
    """Distribui erros e resource names pelas ações do plano.

    `falha` é a exceção da requisição inteira (quando a API levantou em vez de
    devolver partial failure). Erro com índice cai na ação dona do índice; erro
    sem índice derruba TODAS — não dá para dizer qual ação ele poupou.
    """
    erros = list(falha.erros) if falha else []
    request_id = falha.request_id if falha else ""
    if resposta is not None:
        erros += falhas_parciais(resposta, request_id)

    por_acao: dict[int, list[ErroGads]] = {}
    gerais: list[ErroGads] = []
    for e in erros:
        dono = plano.acao_da_operacao(e.indice_operacao) if e.indice_operacao is not None else None
        (por_acao.setdefault(dono, []) if dono is not None else gerais).append(e)

    respostas = list(getattr(resposta, "mutate_operation_responses", []) or [])
    resultados = []
    for i, (acao, (ini, fim)) in enumerate(zip(plano.acoes, plano.faixas)):
        meus = tuple(por_acao.get(i, ()))
        ops_ruins = {e.indice_operacao for e in meus}
        if gerais or len(ops_ruins) >= fim - ini:
            desfecho = "falhou"
        elif ops_ruins:
            desfecho = "parcial"
        else:
            desfecho = "ok"
        recursos = tuple(
            r for j in range(ini, fim)
            if j < len(respostas) and j not in ops_ruins
            and (r := _recurso_da_resposta(respostas[j])))
        resultados.append(ResultadoAcao(acao, desfecho, meus + tuple(gerais),
                                        recursos, (ini, fim)))
    return ResultadoLote(plano.customer_id, validate_only, tuple(resultados),
                         tuple(gerais), request_id)


# ── envio ───────────────────────────────────────────────────────────────────


def _cliente(login_customer_id: str, cliente: Any) -> Any:
    if cliente is not None:
        return cliente
    from volc_ads.gads.client import cliente as fabrica  # noqa: PLC0415

    return fabrica(login_customer_id)


def enviar(plano: Plano, *, login_customer_id: str, validate_only: bool,
           cliente: Any = None, politica: Any = None) -> ResultadoLote:
    """`GoogleAdsService.Mutate` com `partial_failure=True`.

    Escrita real (`validate_only=False`) passa pela trava ANTES de montar a
    requisição — o mesmo ponto em que `client.mutar` a confere. O retry é o de
    `client.executar` (o mesmo de `mutar`): TERMINAL nunca retenta.

    ⚠️ Um DEADLINE_EXCEEDED de escrita pode ter sido aplicado do lado do Google.
    Updates (status, orçamento, lance, ajuste) são idempotentes; criação de
    critério reenviada pode duplicar ou ser recusada como duplicata. Por isso
    quem registra no ledger não confia no desfecho sozinho: a verificação
    (`trafego_acompanhamento`, momento='verificacao') relê o estado.
    """
    from volc_ads.gads.client import ErroEsgotado, ErroTerminal, executar  # noqa: PLC0415

    if not validate_only:
        modo.exigir_leitura_apenas(
            f"gestao.lote.enviar({plano.customer_id}, {len(plano.operacoes)} operações)")

    c = _cliente(login_customer_id, cliente)
    servico = c.get_service("GoogleAdsService")
    req = c.get_type("MutateGoogleAdsRequest")
    req.customer_id = plano.customer_id
    req.mutate_operations.extend(plano.operacoes)
    req.partial_failure = True
    req.validate_only = validate_only

    try:
        resposta = executar(lambda: servico.mutate(request=req), politica=politica,
                            rotulo=f"gestao:{plano.customer_id}")
    except (ErroTerminal, ErroEsgotado) as exc:
        return mapear(plano, validate_only=validate_only, falha=exc.falha)
    return mapear(plano, validate_only=validate_only, resposta=resposta)


def _juntar(customer_id: str, validate_only: bool, acoes: Sequence[Acao],
            parciais: dict[int, ResultadoAcao], lote: ResultadoLote | None) -> ResultadoLote:
    """Recompõe a ordem original das ações depois de separar as fora do mutate."""
    fila = list(lote.acoes) if lote else []
    out = [parciais[i] if i in parciais else fila.pop(0) for i in range(len(acoes))]
    return ResultadoLote(str(customer_id), validate_only, tuple(out),
                         lote.erros_gerais if lote else (),
                         lote.request_id if lote else "")


def validar(customer_id: str, acoes: Sequence[Acao], *, login_customer_id: str,
            cliente: Any = None) -> ResultadoLote:
    """O ensaio: `validate_only=True` + `partial_failure=True`. Não exige trava."""
    acoes = tuple(acoes)
    fora = {i: ResultadoAcao(a, "nao_validavel",
                             motivo="RecommendationService não tem validate_only na v25")
            for i, a in enumerate(acoes) if a.fora_do_mutate}
    dentro = [a for a in acoes if not a.fora_do_mutate]
    lote = None
    if dentro:
        c = _cliente(login_customer_id, cliente)
        plano = montar(dentro, c.get_type, customer_id)
        lote = enviar(plano, login_customer_id=login_customer_id, validate_only=True, cliente=c)
    return _juntar(customer_id, True, acoes, fora, lote)


def aplicar(customer_id: str, acoes: Sequence[Acao], *, login_customer_id: str,
            motivo: str, cliente: Any = None) -> tuple[ResultadoLote, ResultadoLote | None]:
    """Ensaia, e manda de verdade SÓ as ações que o ensaio aceitou inteiras.

    Ação `parcial` no ensaio não vai: o humano aprovou a ação inteira, e mandar
    metade dela é aplicar outra coisa. A escrita real abre a trava de dois
    fatores (`modo.destravar(motivo)` + FORGE_PERMITIR_ESCRITA=1); sem os dois,
    `EscritaBloqueada` sobe e nada sai.
    """
    acoes = tuple(acoes)
    if any(a.fora_do_mutate for a in acoes):
        raise LoteRecusado("recomendação vai por aplicar_recomendacoes, não por aplicar")
    c = _cliente(login_customer_id, cliente)
    ensaio = validar(customer_id, acoes, login_customer_id=login_customer_id, cliente=c)
    aceitas = [r.acao for r in ensaio.acoes if r.desfecho == "ok"]
    if not aceitas:
        return ensaio, None
    plano = montar(aceitas, c.get_type, customer_id)
    with modo.destravar(motivo):
        real = enviar(plano, login_customer_id=login_customer_id, validate_only=False, cliente=c)
    return ensaio, real


# ── recomendações ───────────────────────────────────────────────────────────


def _plano_de_recomendacoes(acoes: Sequence[Acao], customer_id: str) -> Plano:
    """Plano com uma operação por ação — a faixa vale para `operations[i]`."""
    return Plano(str(customer_id), tuple(acoes), tuple(None for _ in acoes),
                 tuple((i, i + 1) for i in range(len(acoes))))


def montar_pedidos_de_recomendacao(acoes: Sequence[Acao], get_type: Any,
                                   customer_id: str) -> dict[str, tuple[Any, Plano]]:
    """`{"aplicar": (ApplyRecommendationRequest, plano), "dispensar": (...)}` — puro."""
    from .acoes import AplicarRecomendacao, DispensarRecomendacao  # noqa: PLC0415

    pedidos: dict[str, tuple[Any, Plano]] = {}
    for nome, classe, tipo_req in (
            ("aplicar", AplicarRecomendacao, "ApplyRecommendationRequest"),
            ("dispensar", DispensarRecomendacao, "DismissRecommendationRequest")):
        grupo = [a for a in acoes if isinstance(a, classe)]
        if not grupo:
            continue
        req = get_type(tipo_req)
        req.customer_id = str(customer_id)
        req.partial_failure = True
        req.operations.extend(a.operacao_de_recomendacao(get_type) for a in grupo)
        pedidos[nome] = (req, _plano_de_recomendacoes(grupo, customer_id))
    outras = [a.tipo for a in acoes if not a.fora_do_mutate]
    if outras:
        raise LoteRecusado(f"{outras} não são recomendação")
    return pedidos


def mapear_recomendacoes(plano: Plano, *, resposta: Any = None,
                         falha: FalhaGads | None = None) -> ResultadoLote:
    """Igual a `mapear`, mas a resposta traz `results[i].resource_name`."""
    erros = list(falha.erros) if falha else []
    if resposta is not None:
        erros += falhas_parciais(resposta)
    gerais = [e for e in erros if e.indice_operacao is None]
    resultados = []
    resultados_api = list(getattr(resposta, "results", []) or [])
    for i, acao in enumerate(plano.acoes):
        meus = tuple(e for e in erros if e.indice_operacao == i)
        desfecho = "falhou" if (meus or gerais) else "ok"
        rn = resultados_api[i].resource_name if i < len(resultados_api) and not meus else ""
        resultados.append(ResultadoAcao(acao, desfecho, meus + tuple(gerais),
                                        (rn,) if rn else (), (i, i + 1)))
    return ResultadoLote(plano.customer_id, False, tuple(resultados), tuple(gerais),
                         falha.request_id if falha else "")


def aplicar_recomendacoes(customer_id: str, acoes: Sequence[Acao], *, login_customer_id: str,
                          motivo: str, cliente: Any = None) -> dict[str, ResultadoLote]:
    """Aplica/dispensa DE VERDADE. Não há ensaio possível — ver docstring do módulo.

    Mesma trava de `enviar`: `destravar(motivo)` aqui + `exigir_leitura_apenas`
    antes de cada chamada.
    """
    from volc_ads.gads.client import ErroEsgotado, ErroTerminal, executar  # noqa: PLC0415

    c = _cliente(login_customer_id, cliente)
    pedidos = montar_pedidos_de_recomendacao(acoes, c.get_type, customer_id)
    servico = c.get_service("RecommendationService")
    saida: dict[str, ResultadoLote] = {}
    with modo.destravar(motivo):
        for nome, (req, plano) in pedidos.items():
            modo.exigir_leitura_apenas(f"recomendacao.{nome}({customer_id}, {len(plano.acoes)})")
            chamada = (servico.apply_recommendation if nome == "aplicar"
                       else servico.dismiss_recommendation)
            try:
                resp = executar(lambda: chamada(request=req), rotulo=f"recomendacao:{nome}")
            except (ErroTerminal, ErroEsgotado) as exc:
                saida[nome] = mapear_recomendacoes(plano, falha=exc.falha)
                continue
            saida[nome] = mapear_recomendacoes(plano, resposta=resp)
    return saida
