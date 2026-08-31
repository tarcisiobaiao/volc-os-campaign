"""O ledger de lançamento — a única porta que grava intenção, aprovação e recibo.

## Por que este módulo existe, e por que ele é fino

A v10_01 modelou o ciclo inteiro (intenção → lote → item → validações →
aprovação → recibo → verificação) e a v10_03 fechou a fronteira atômica em
quatro funções no Postgres. **A regra mora no banco.** Este módulo não a
reimplementa: ele traduz chamada Python em `POST /rest/v1/rpc/...` e traduz a
recusa do banco em exceção tipada.

Reimplementar a regra aqui criaria duas fontes de verdade que divergem no
primeiro mês — e a de baixo é a que vale, porque é a que sobrevive a um cliente
novo, a um script de manutenção e a um `psql` às três da manhã.

## A ordem que importa

    abrir()      → intenção, blueprint, lote, item e provas persistidos
    (leitura remota de idempotência — não muta nada)
    despachar()  → aprovação vinculada + recibo `em_voo` COMMITADO
    ══════════ só agora a chamada que MUTA pode sair ══════════
    fechar()     → sucesso (com id externo) · erro · sem_resposta
    reconciliar()→ a leitura tardia fecha o MESMO recibo, sem reenviar

⚠️ **A leitura de pré-checagem acontece ANTES do recibo, de propósito.** A regra
que o recibo serve é "nenhuma MUTAÇÃO sem rastro local anterior"; uma leitura não
cria nada na conta. Abrir o recibo antes da leitura teria um custo real e
assimétrico: uma falha transitória de leitura deixaria um `em_voo` órfão, e a
camada 4 da v10_03 passaria a bloquear o item até alguém reconciliar uma chamada
que nunca saiu. O recibo cobre o mutate; a leitura é prova, e entra no ledger
como validação.

## Estados que este módulo se recusa a colapsar

`erro` é resposta: a plataforma disse que não criou, e o item vira `falhou`, que
é reentrável. `sem_resposta` é ignorância: ninguém disse nada, o item vira
`indeterminado`, e a saída de lá é verificar na conta — nunca reenviar. Quem
transforma um timeout em "falhou, tente de novo" cria a segunda campanha.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import httpx

from app.trafego import lote as dom
from app.trafego import sincronizador

log = logging.getLogger(__name__)

# Namespace fixo para derivar `intencao_id` do conteúdo da intenção. Ele não é
# segredo e não pode mudar: mudá-lo faria toda intenção já gravada deixar de ser
# reencontrada, e a chave de idempotência do item — que deriva do intencao_id —
# passaria a apontar para outro lugar.
NAMESPACE_INTENCAO = uuid.UUID("6f9b4a1e-1d3c-5f7a-9c2b-8e4d0a6b3f51")

OPERACAO_CRIAR = "criar_campanha"


class LedgerIndisponivel(RuntimeError):
    """Não deu para falar com o ledger. NÃO significa que algo falhou lá."""


class ErroDeIdentidade(ValueError):
    """A identidade da instância não pode ser derivada do que veio.

    Ela é interna à fachada: nenhum chamador a vê, porque todo caminho que
    deriva identidade a traduz para `LedgerRecusou` antes de sair daqui.
    """


class LedgerRecusou(RuntimeError):
    """Uma guarda do banco disparou. O pedido não aconteceu.

    `codigo` é o SQLSTATE. Ele separa recusa de regra (classe 23, 22023, P0001,
    P0002) de defeito de infraestrutura, e quem chama precisa dessa diferença
    para decidir entre "o operador errou" e "o sistema está quebrado".
    """

    def __init__(self, mensagem: str, *, codigo: str = "", detalhe: Any = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.detalhe = detalhe


# SQLSTATEs que significam "a regra recusou", e não "o ledger está quebrado".
# 22023 é argumento inválido (a função recusou o que recebeu); 22P02 NÃO entra —
# ele é literal malformado, ou seja, defeito de quem chamou o banco.
_RECUSA_DE_REGRA = ("P0001", "P0002", "22023", "23")


def _e_recusa_de_regra(codigo: str) -> bool:
    return bool(codigo) and (
        codigo in ("P0001", "P0002", "22023") or codigo.startswith("23")
    )


def intencao_determinista(
    *, plataforma: str, conta_externa: str, objetivo: str, rotulo: str,
    declarada_com_base_em: str,
) -> str:
    """O id da intenção derivado do que a intenção é.

    Precisa ser estável entre tentativas: a chave de idempotência do item deriva
    dele, e uma intenção com id novo produziria chave nova — que é o mesmo que
    não ter idempotência nenhuma no momento em que ela mais importa, a retomada.
    """
    materia = json.dumps(
        [plataforma, conta_externa, objetivo, rotulo, declarada_com_base_em],
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return str(uuid.uuid5(NAMESPACE_INTENCAO, materia))


def volc_campaign_id_de(*, plataforma: str, conta_externa: str, id_externo: str) -> str:
    """A identidade da instância (ADR-02), derivada e não sorteada.

    Duas leituras do mesmo recurso remoto têm de produzir o mesmo id local, ou a
    reconciliação criaria uma segunda identidade para a mesma campanha.

    ## Por que esta função DELEGA em vez de derivar

    Até 31/08/2026 ela derivava aqui — `volc_cmp_<sigla>_<sha256[:16]>` — enquanto
    `sincronizador.volc_campaign_id` já derivava `uuid5(gads:<conta>:<campanha>)`
    para o MESMO par externo. Duas derivações são duas identidades, e o banco
    tem um índice montado exatamente para descobrir isso da pior forma:

        trafego_campanha_identidade_externa_ux (customer_id, campaign_id)

    Esse índice NÃO é o alvo do `ON CONFLICT (volc_campaign_id) DO NOTHING` que
    `trafego_ledger_fechar` usa. Então, se a varredura já tinha declarado a
    identidade `uuid5` para o par, o INSERT do ledger com a forma `volc_cmp_`
    passava batido pelo `ON CONFLICT`, batia no índice do par externo com 23505
    e abortava a transação inteira de `fechar` — deixando o recibo `em_voo` com
    a campanha **já criada** na conta. O pior desfecho possível: existe lá,
    não existe aqui, e o rastro diz que ninguém sabe.

    A derivação vencedora é a do sincronizador porque é a que tem linhas
    gravadas. A do ledger nunca gravou nada em produção: `ProvarEntrada` declara
    `budget_diario: float`, e o `float` fazia `abrir()` levantar antes de existir
    recibo — o caminho inteiro estava morto. Não há registro anterior na forma
    `volc_cmp_` para migrar, e é por isso que esta convergência não precisa de
    adaptador de compatibilidade.
    """
    if plataforma != "GOOGLE_ADS":
        raise ErroDeIdentidade(
            f"a identidade de instância só tem derivação canônica para "
            f"GOOGLE_ADS; recebido {plataforma!r}. Inventar uma segunda forma "
            "aqui recriaria o defeito que esta delegação existe para fechar."
        )
    try:
        return sincronizador.volc_campaign_id(conta_externa, id_externo)
    except ValueError as exc:
        raise ErroDeIdentidade(str(exc)) from exc


def _identidade_ou_recusa(*, plataforma: str, conta_externa: str,
                          id_externo: str) -> str:
    """`volc_campaign_id_de`, com a recusa já na forma que a rota entende."""
    try:
        return volc_campaign_id_de(
            plataforma=plataforma, conta_externa=conta_externa,
            id_externo=id_externo)
    except ErroDeIdentidade as exc:
        raise LedgerRecusou(str(exc), codigo="22023") from exc


@dataclass(frozen=True)
class Despacho:
    """O que existe no banco no instante anterior à chamada que muta."""
    item_id: str
    lote_id: str
    recibo_id: str
    tentativa: int
    reentrada_apos: Optional[str] = None


class Ledger:
    """Fachada assíncrona sobre as quatro funções da v10_03."""

    def __init__(self, supa: Any):
        self._supa = supa

    @property
    def disponivel(self) -> bool:
        return bool(getattr(self._supa, "enabled", False))

    async def _rpc(self, funcao: str, argumentos: Mapping[str, Any]) -> Any:
        if not self.disponivel:
            raise LedgerIndisponivel(
                "O ledger de lançamento não está configurado neste processo "
                "(SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY ausentes). Nada foi "
                "registrado e nada foi enviado."
            )
        # `None` é diferente de ausente: mandar a chave com null faz o PostgREST
        # sobrescrever o DEFAULT da função com NULL, e alguns DEFAULTs aqui não
        # são NULL ('{}'::jsonb, 1, 'criar_campanha').
        corpo = {k: v for k, v in argumentos.items() if v is not None}
        try:
            return await self._supa.rpc(funcao, corpo)
        except httpx.HTTPStatusError as exc:
            codigo, mensagem, detalhe = _erro_do_postgrest(exc)
            if _e_recusa_de_regra(codigo):
                raise LedgerRecusou(mensagem, codigo=codigo, detalhe=detalhe) from exc
            raise LedgerIndisponivel(
                f"o ledger respondeu {exc.response.status_code}: {mensagem}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LedgerIndisponivel(f"o ledger não respondeu: {exc}") from exc

    async def abrir(
        self, *, plataforma: str, conta_externa: str, canal: str, objetivo: str,
        rotulo: str, plano: Mapping[str, Any], plano_impressao: str,
        declarada_por: str, declarada_com_base_em: str, blueprint_chave: str,
        blueprint_titulo: str, blueprint_corpo: Mapping[str, Any],
        destino_url: Optional[str] = None,
        verba_diaria_teto_micros: Optional[int] = None,
        moeda: Optional[str] = None,
        evidencia: Optional[Mapping[str, Any]] = None,
        validacoes: Sequence[Mapping[str, Any]] = (),
        ordem: int = 0,
    ) -> dict:
        """Persiste tudo o que existe antes da autorização humana."""
        intencao_id = intencao_determinista(
            plataforma=plataforma, conta_externa=conta_externa,
            objetivo=objetivo, rotulo=rotulo,
            declarada_com_base_em=declarada_com_base_em,
        )
        # A chave sai do domínio já testado (`lote.py`), não de uma segunda
        # derivação escrita aqui — duas derivações divergem, e a divergência
        # aparece justamente na retomada.
        #
        # ⚠️ `ErroDeLote` é `ValueError`, e um `ValueError` que atravessa esta
        # fachada vira 500 nu na rota — que captura só as duas exceções tipadas
        # daqui. Foi exatamente isso que deixou `/subir` inoperante: o plano
        # chegava com `budget_diario` float, `_sem_float` recusava (com razão),
        # e a recusa saía sem forma, sem status e sem recibo. A guarda não está
        # errada; o que faltava era ela chegar tipada a quem decide o HTTP.
        try:
            chave = dom.chave_de_idempotencia(
                intencao_id=intencao_id, plataforma=plataforma,
                conta_externa=conta_externa, canal=canal, ordem=ordem, plano=plano,
            )
        except dom.ErroDeLote as exc:
            raise LedgerRecusou(str(exc), codigo="22023") from exc
        resposta = await self._rpc("trafego_ledger_abrir_lancamento", {
            "p_idempotency_key": chave,
            "p_intencao_id": intencao_id,
            "p_plataforma": plataforma,
            "p_conta_externa": conta_externa,
            "p_canal": canal,
            "p_objetivo": objetivo,
            "p_rotulo": rotulo,
            "p_plano": dict(plano),
            "p_plano_impressao": plano_impressao,
            "p_declarada_por": declarada_por,
            "p_declarada_com_base_em": declarada_com_base_em,
            "p_blueprint_chave": blueprint_chave,
            "p_blueprint_titulo": blueprint_titulo,
            "p_blueprint_corpo": dict(blueprint_corpo or {}),
            "p_destino_url": destino_url,
            "p_verba_diaria_teto_micros": verba_diaria_teto_micros,
            "p_moeda": moeda,
            "p_evidencia": dict(evidencia or {}),
            "p_validacoes": [dict(v) for v in validacoes],
        })
        saida = dict(resposta or {})
        saida["idempotency_key"] = chave
        saida["intencao_id"] = saida.get("intencao_id") or intencao_id
        return saida

    async def despachar(
        self, *, idempotency_key: str, plataforma: str, conta_externa: str,
        canal: str, aprovacao_impressao: str, aprovado_por: str,
        aprovado_por_sub: str, operacao: str = OPERACAO_CRIAR,
        request_id: Optional[str] = None,
        aprovacao_observacao: Optional[str] = None,
    ) -> Despacho:
        """Autoriza e abre o recibo. Depois disto — e só depois — a chamada sai."""
        resposta = await self._rpc("trafego_ledger_despachar", {
            "p_idempotency_key": idempotency_key,
            "p_plataforma": plataforma,
            "p_conta_externa": conta_externa,
            "p_canal": canal,
            "p_aprovacao_impressao": aprovacao_impressao,
            "p_aprovado_por": aprovado_por,
            "p_aprovado_por_sub": aprovado_por_sub,
            "p_operacao": operacao,
            "p_request_id": request_id,
            "p_aprovacao_observacao": aprovacao_observacao,
        })
        d = dict(resposta or {})
        return Despacho(
            item_id=str(d.get("item_id") or ""),
            lote_id=str(d.get("lote_id") or ""),
            recibo_id=str(d.get("recibo_id") or ""),
            tentativa=int(d.get("tentativa") or 0),
            reentrada_apos=d.get("reentrada_apos"),
        )

    async def fechar_sucesso(
        self, *, recibo_id: str, id_externo: str, plataforma: str,
        conta_externa: str, resposta_bruta: Optional[Mapping[str, Any]] = None,
        operacoes_consumidas: Optional[int] = None, fechado_por: str = "volc_os",
    ) -> dict:
        return dict(await self._rpc("trafego_ledger_fechar", {
            "p_recibo_id": recibo_id,
            "p_desfecho": "sucesso",
            "p_id_externo": id_externo,
            "p_volc_campaign_id": _identidade_ou_recusa(
                plataforma=plataforma, conta_externa=conta_externa,
                id_externo=id_externo),
            "p_customer_id": conta_externa,
            "p_resposta_bruta": dict(resposta_bruta) if resposta_bruta else None,
            "p_operacoes_consumidas": operacoes_consumidas,
            "p_fechado_por": fechado_por,
        }) or {})

    async def fechar_erro(
        self, *, recibo_id: str, mensagem: str, codigo: Optional[str] = None,
        resposta_bruta: Optional[Mapping[str, Any]] = None,
        fechado_por: str = "volc_os",
    ) -> dict:
        """A plataforma RESPONDEU que não criou. O item fica reentrável."""
        return dict(await self._rpc("trafego_ledger_fechar", {
            "p_recibo_id": recibo_id,
            "p_desfecho": "erro",
            "p_erro_codigo": codigo,
            "p_erro_mensagem": (mensagem or "erro sem mensagem")[:2000],
            "p_resposta_bruta": dict(resposta_bruta) if resposta_bruta else None,
            "p_fechado_por": fechado_por,
        }) or {})

    async def fechar_sem_resposta(
        self, *, recibo_id: str, motivo: str, codigo: Optional[str] = None,
        fechado_por: str = "volc_os",
    ) -> dict:
        """⚠️ Ninguém respondeu. Isto NÃO é falha e NÃO autoriza reenvio.

        Note que aqui NÃO existe `resposta_bruta`: o ramo `sem_resposta` de
        `trafego_ledger_fechar` grava `erro_codigo` e `erro_mensagem` e ignora
        `p_resposta_bruta`. Aceitar o parâmetro daria a impressão de que a
        evidência ficou registrada quando ela seria descartada em silêncio.
        """
        return dict(await self._rpc("trafego_ledger_fechar", {
            "p_recibo_id": recibo_id,
            "p_desfecho": "sem_resposta",
            "p_erro_codigo": codigo,
            "p_erro_mensagem": (motivo or "sem resposta")[:2000],
            "p_fechado_por": fechado_por,
        }) or {})

    async def reconciliar(
        self, *, item_id: str, metodo: str, achou: Optional[bool],
        verificado_por: str, plataforma: str, conta_externa: str,
        id_externo: Optional[str] = None, quantidade: Optional[int] = None,
        motivo: Optional[str] = None, estado_externo: Optional[str] = None,
        divergencia: Optional[Mapping[str, Any]] = None,
    ) -> dict:
        """A leitura tardia. `achou=None` registra e não move nada.

        As duas guardas abaixo repetem CHECKs que o banco já impõe
        (`trafego_verificacao_achou_conta`, e a exigência de id externo dentro
        de `trafego_ledger_reconciliar`). Elas não existem por desconfiança do
        banco: existem porque a recusa do banco chega como `LedgerRecusou`
        genérico com SQLSTATE, e quem opera precisa saber que faltou a
        QUANTIDADE — não que "uma guarda disparou".
        """
        if achou is True:
            if (not isinstance(quantidade, int) or isinstance(quantidade, bool)
                    or quantidade < 1):
                raise LedgerRecusou(
                    "reconciliar: `achou=true` exige quantidade >= 1. Ausência "
                    f"de quantidade não vira zero, e {quantidade!r} não conta "
                    "uma campanha encontrada.",
                    codigo="22023")
            if not str(id_externo or "").strip():
                raise LedgerRecusou(
                    "reconciliar: `achou=true` exige o id externo da campanha "
                    "encontrada. \"Está lá\" sem saber qual não fecha recibo.",
                    codigo="22023")
        argumentos: dict[str, Any] = {
            "p_item_id": item_id,
            "p_metodo": metodo,
            "p_verificado_por": verificado_por,
            "p_id_externo": id_externo,
            "p_customer_id": conta_externa,
            "p_quantidade": quantidade,
            "p_motivo": motivo,
            "p_estado_externo": estado_externo,
            "p_divergencia": dict(divergencia) if divergencia else None,
        }
        # `achou` é tri-estado e NÃO pode ser podado como os outros: `None` aqui
        # é uma afirmação ("não consegui ler"), e o DEFAULT da função não é None.
        if achou is not None:
            argumentos["p_achou"] = achou
            if achou:
                argumentos["p_volc_campaign_id"] = _identidade_ou_recusa(
                    plataforma=plataforma, conta_externa=conta_externa,
                    id_externo=str(id_externo or ""))
        else:
            argumentos["p_achou"] = None
        corpo = {k: v for k, v in argumentos.items() if v is not None or k == "p_achou"}
        return dict(await self._rpc_cru("trafego_ledger_reconciliar", corpo) or {})

    async def conta_externa_do_item(self, item_id: str) -> Optional[str]:
        """A conta a que o item pertence, ou `None` se o item não existe.

        ⚠️ `None` aqui é "não existe", e é diferente de "não consegui ler" —
        que sai como `LedgerIndisponivel`. Quem chama usa a distinção para
        separar 404 de 503, e colapsá-la faria um banco fora do ar parecer um
        item inexistente, que é o convite a criar outro.

        Existe porque `trafego_ledger_reconciliar` acha o item só pelo id e não
        confere o lote: sem esta leitura, reconciliar aceitaria casar um item
        com a campanha de outra conta.
        """
        if not self.disponivel:
            raise LedgerIndisponivel(
                "O ledger de lançamento não está configurado neste processo.")
        try:
            itens = await self._supa.select(
                "trafego_lote_item",
                {"item_id": f"eq.{item_id}", "select": "item_id,lote_id", "limit": "1"})
            if not itens:
                return None
            lotes = await self._supa.select(
                "trafego_lote",
                {"lote_id": f"eq.{itens[0].get('lote_id')}",
                 "select": "lote_id,conta_externa", "limit": "1"})
            if not lotes:
                return None
            return str(lotes[0].get("conta_externa") or "") or None
        except httpx.HTTPError as exc:
            raise LedgerIndisponivel(
                f"não consegui ler o item {item_id}: {exc}") from exc

    async def _rpc_cru(self, funcao: str, corpo: Mapping[str, Any]) -> Any:
        """Como `_rpc`, mas sem podar `None` — para os campos tri-estado."""
        if not self.disponivel:
            raise LedgerIndisponivel(
                "O ledger de lançamento não está configurado neste processo."
            )
        try:
            return await self._supa.rpc(funcao, dict(corpo))
        except httpx.HTTPStatusError as exc:
            codigo, mensagem, detalhe = _erro_do_postgrest(exc)
            if _e_recusa_de_regra(codigo):
                raise LedgerRecusou(mensagem, codigo=codigo, detalhe=detalhe) from exc
            raise LedgerIndisponivel(
                f"o ledger respondeu {exc.response.status_code}: {mensagem}") from exc
        except httpx.HTTPError as exc:
            raise LedgerIndisponivel(f"o ledger não respondeu: {exc}") from exc


def _erro_do_postgrest(exc: httpx.HTTPStatusError) -> tuple[str, str, Any]:
    """Extrai SQLSTATE e mensagem do corpo do PostgREST.

    O corpo é `{"code": "23001", "message": "...", "details": ..., "hint": ...}`.
    Sem ler o `code`, uma recusa de regra e um banco fora do ar viram a mesma
    coisa para quem chama — e as duas exigem reações opostas.
    """
    try:
        corpo = exc.response.json()
    except Exception:  # noqa: BLE001
        return "", (exc.response.text or str(exc))[:500], None
    if not isinstance(corpo, Mapping):
        return "", str(corpo)[:500], corpo
    return (
        str(corpo.get("code") or ""),
        str(corpo.get("message") or exc.response.text or "")[:2000],
        corpo.get("details"),
    )
