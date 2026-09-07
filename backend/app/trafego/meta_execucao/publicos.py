"""Resolve referências opacas de público e mensuração para IDs do provedor.

## Por que resolver é LISTAR, e não decifrar

`dominio.referencia_opaca_objeto` é um sha256 truncado de
`meta_ads:<conta>:<tipo>:<id>` (dominio.py:170-181). Ele é de MÃO ÚNICA: não
existe função que devolva o id a partir da referência, e é assim de propósito —
o navegador nunca segura um identificador real da conta.

Então resolver uma referência é: LISTAR o catálogo daquela conta, recalcular a
referência opaca de cada item e procurar a que bate.

⚠️ E é exatamente isso que dá o isolamento de graça (`A13`, `F12`). Um público
que pertence a OUTRA conta nunca aparece na listagem desta, então a referência
dele nunca bate — a recusa não depende de um `if` que alguém possa esquecer,
ela é uma consequência de onde a lista veio.

## Por que nada é lido quando nada foi escolhido

O preflight desta lane já custa nove requisições paginadas por clique. Um plano
de público amplo, sem conversão e sem idioma não precisa de NENHUMA leitura
extra — e disparar quatro edges "por via das dúvidas" transformaria compilar,
que é um ato local e barato, num ato caro com efeito de rede. A função sai cedo
quando o plano não pede nada.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Protocol

import httpx

from app.trafego.meta import dominio as dom
from app.trafego.meta.adaptador import AdaptadorMetaSomenteLeitura
from app.trafego.meta.credenciais import SegredoEfemero

from .contrato import ErroDeNascimentoMeta
from .contrato_v2 import PlanoMetaV2, ReferenciasDePublicoResolvidas


#: Os tipos com que `referencia_opaca_objeto` foi chamada quando a referência
#: foi EMITIDA. Recalcular com outro tipo produz outro digest e nada bate — por
#: isso eles são constantes num lugar só, e não literais espalhados.
TIPO_PUBLICO = "custom_audience"
TIPO_PIXEL = "pixel"
TIPO_CONVERSAO = "custom_conversion"


class CatalogoDaConta(Protocol):
    """O mínimo que o resolvedor precisa do adaptador.

    Existe como Protocol para que o teste hermético possa entregar um catálogo
    de memória sem abrir socket nenhum — e para que trocar a pilha de leitura
    Graph não obrigue a reescrever a resolução.

    ⚠️ `resolver_ids_por_referencia` é SERVER-ONLY: o que ela devolve são ids
    reais do provedor, e eles nunca podem atravessar uma resposta HTTP. É a
    mesma regra de `ReferenciasMetaResolvidas`, que fecha o `__repr__` pelo
    mesmo motivo.
    """

    async def descobrir_contas(self, segredo: SegredoEfemero) -> tuple[Any, ...]: ...

    async def resolver_ids_por_referencia(
        self,
        conta_externa: str,
        tipo: str,
        referencias: list[str],
        segredo: SegredoEfemero,
    ) -> Mapping[str, str]: ...


def _exigir_leitor(catalogo: Any, metodo: str, o_que: str) -> Any:
    """Recusa com nome próprio quando a pilha de leitura não sabe ler isto.

    ⚠️ Sem esta guarda, um catálogo incompleto devolveria zero itens e a
    resolução falharia como "público não encontrado" — mandando o operador
    procurar um defeito na conta dele por causa de um método que não existe
    aqui. Os dois casos são reais e precisam de mensagens diferentes.
    """
    funcao = getattr(catalogo, metodo, None)
    if not callable(funcao):
        raise ErroDeNascimentoMeta(
            "META_CATALOG_READER_UNAVAILABLE",
            f"este servidor ainda não sabe listar {o_que} desta conta",
        )
    return funcao


def _resolver(
    leitor: Any,
    conta: str,
    tipo: str,
    referencias: Iterable[str],
    segredo: SegredoEfemero,
    o_que: str,
) -> Any:
    """Delega a listagem ao adaptador e cobra AQUI o que ele não achou.

    ⚠️ A divisão é deliberada. O adaptador sabe LISTAR — ele devolve o que
    encontrou e não opina. Quem transforma ausência em recusa é este módulo,
    porque só ele sabe que a referência era obrigatória para o payload. Juntar
    as duas responsabilidades faria "não sei ler este catálogo" e "este público
    não é seu" virarem o mesmo erro, e são causas opostas.
    """
    return _exigir_leitor(leitor, "resolver_ids_por_referencia", o_que)(
        conta, tipo, list(referencias), segredo)


def _cobrar(
    pedidas: Iterable[str], indice: Mapping[str, str], o_que: str,
) -> dict[str, str]:
    resolvidas: dict[str, str] = {}
    faltando: list[str] = []
    for referencia in dict.fromkeys(pedidas):
        if referencia in indice:
            resolvidas[referencia] = indice[referencia]
        else:
            faltando.append(referencia)
    if faltando:
        # A mensagem não cita a referência: ela não diz nada ao operador e
        # citá-la num log ligaria o handle do navegador ao incidente.
        raise ErroDeNascimentoMeta(
            "META_AUDIENCE_REFERENCE_UNRESOLVED",
            f"{len(faltando)} {o_que} não pertence(m) a esta conta ou não existe(m) mais",
        )
    return resolvidas


def _refs_de_publico(plano: PlanoMetaV2) -> tuple[str, ...]:
    refs: list[str] = []
    for conjunto in plano.conjuntos:
        publico = conjunto.publico
        refs.extend(publico.incluir_custom_refs)
        refs.extend(publico.lookalike_refs)
        refs.extend(publico.excluir_custom_refs)
    return tuple(dict.fromkeys(refs))


def _refs_de_fonte(plano: PlanoMetaV2) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        conjunto.mensuracao.source_ref
        for conjunto in plano.conjuntos
        # ⚠️ Só o que MUDA o payload é resolvido. Uma fonte escolhida para
        # RELATAR não vira `promoted_object`, então resolvê-la seria pagar uma
        # leitura de rede por um id que nenhum payload vai carregar.
        if conjunto.mensuracao.altera_payload and conjunto.mensuracao.source_ref
    ))


def _refs_de_conversao(plano: PlanoMetaV2) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        conjunto.mensuracao.custom_conversion_ref
        for conjunto in plano.conjuntos
        if conjunto.mensuracao.altera_payload and conjunto.mensuracao.custom_conversion_ref
    ))


def _refs_de_interesse(plano: PlanoMetaV2) -> tuple[str, ...]:
    refs: list[str] = []
    for conjunto in plano.conjuntos:
        refs.extend(conjunto.publico.interesse_refs)
    return tuple(dict.fromkeys(refs))


def _refs_de_locale(plano: PlanoMetaV2) -> tuple[str, ...]:
    refs: list[str] = []
    for conjunto in plano.conjuntos:
        refs.extend(conjunto.publico.locale_refs)
    return tuple(dict.fromkeys(refs))


async def resolver_referencias_de_publico(
    cliente: httpx.AsyncClient,
    *,
    plano: PlanoMetaV2,
    account_ref: str,
    segredo: SegredoEfemero,
    catalogo: CatalogoDaConta | None = None,
) -> ReferenciasDePublicoResolvidas:
    """Troca as referências opacas do plano pelos ids reais DESTA conta."""
    publicos_pedidos = _refs_de_publico(plano)
    fontes_pedidas = _refs_de_fonte(plano)
    conversoes_pedidas = _refs_de_conversao(plano)
    interesses_pedidos = _refs_de_interesse(plano)
    locales_pedidos = _refs_de_locale(plano)

    if not any((publicos_pedidos, fontes_pedidas, conversoes_pedidas,
                interesses_pedidos, locales_pedidos)):
        # Nada escolhido, nada lido. Compilar continua sendo um ato local.
        return ReferenciasDePublicoResolvidas()

    if interesses_pedidos or locales_pedidos:
        # ⚠️ Recusa HONESTA, e é uma lacuna nomeada, não um bug escondido.
        # Interesses e idiomas vêm do endpoint de busca (`/search`), que não é
        # uma edge da conta: a referência opaca deles não é escopável por conta
        # do mesmo jeito, e resolvê-la exige um contrato próprio que esta
        # missão não provou. Emitir um id adivinhado aqui seria segmentação
        # inventada com cara de escolha do operador.
        raise ErroDeNascimentoMeta(
            "META_AUDIENCE_CATALOG_NOT_PROVEN",
            "segmentação detalhada e idiomas ainda não têm catálogo provado neste "
            "servidor; remova a seleção ou peça a prova desse catálogo",
        )

    leitor = catalogo if catalogo is not None else AdaptadorMetaSomenteLeitura(cliente)
    conta = await _conta_externa(leitor, account_ref, segredo)

    resolvidos_publicos: dict[str, str] = {}
    if publicos_pedidos:
        resolvidos_publicos = _cobrar(
            publicos_pedidos,
            await _resolver(
                leitor, conta, TIPO_PUBLICO, publicos_pedidos, segredo,
                "os públicos personalizados"),
            "público(s)",
        )

    resolvidas_fontes: dict[str, str] = {}
    if fontes_pedidas:
        resolvidas_fontes = _cobrar(
            fontes_pedidas,
            await _resolver(
                leitor, conta, TIPO_PIXEL, fontes_pedidas, segredo,
                "os pixels e datasets"),
            "fonte(s) de mensuração",
        )

    resolvidas_conversoes: dict[str, str] = {}
    if conversoes_pedidas:
        resolvidas_conversoes = _cobrar(
            conversoes_pedidas,
            await _resolver(
                leitor, conta, TIPO_CONVERSAO, conversoes_pedidas, segredo,
                "as conversões personalizadas"),
            "conversão(ões) personalizada(s)",
        )

    return ReferenciasDePublicoResolvidas(
        custom_audience_ids=resolvidos_publicos,
        measurement_source_ids=resolvidas_fontes,
        custom_conversion_ids=resolvidas_conversoes,
    )


async def _conta_externa(
    leitor: Any, account_ref: str, segredo: SegredoEfemero,
) -> str:
    """A conta REAL por trás da referência opaca, descoberta pela credencial.

    ⚠️ A descoberta é a segunda metade do isolamento: a conta só é resolvida se
    ela estiver entre as que ESTA credencial alcança. Uma referência forjada
    para a conta de outro ator não encontra par aqui.

    ⚠️ Reusa `AdaptadorMetaSomenteLeitura.resolver_referencia_opaca`
    (adaptador.py:109) em vez de repetir a comparação. Duas cópias da mesma
    regra de posse é como uma delas fica para trás.
    """
    descobrir = _exigir_leitor(leitor, "descobrir_contas", "as contas desta credencial")
    contas = await descobrir(segredo)
    try:
        conta = AdaptadorMetaSomenteLeitura.resolver_referencia_opaca(
            tuple(contas), account_ref)
    except Exception:
        conta = None
    if conta is None:
        raise ErroDeNascimentoMeta(
            "META_ACCOUNT_REFERENCE_UNRESOLVED",
            "esta conta não pertence à credencial usada nesta sessão",
        )
    return str(conta.id_externo)
