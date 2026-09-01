"""O caminho mínimo: de uma receita a um lote medido, catalogado e conferível.

## O buraco que este módulo fecha

Até aqui a camada de criativo tinha todas as peças e nenhum caminho. `porta.py`
declarava o motor, `adaptadores/` o implementavam, `requisitos.py` sabia o que
cada canal exige, `validacao.py` sabia julgar e `catalogo.py` sabia deduplicar —
e **nada chamava tudo isso em ordem**. Quem quisesse um asset tinha de montar o
`PedidoDeGeracao` à mão, escolher o tamanho à mão, tratar os cinco erros da porta
à mão e lembrar de passar a procedência. Cada consumidor faria isso de um jeito,
e o primeiro que esquecesse um `try` transformaria um motor fora do ar em um
lote silenciosamente vazio.

Este módulo é essa ordem, escrita uma vez.

## Por que a receita é derivada da régua, e não uma lista

Uma `Receita` diz o CANAL e o insumo; ela **não lista tamanhos**. Os papéis a
produzir saem de `requisitos.exigencia_binaria_de(canal)` — os obrigatórios mais
o que os tetos combinados exigem no conjunto — e a dimensão de cada um sai da
especificação daquele papel.

A alternativa (uma tabela de slots aqui) seria a quinta cópia da mesma verdade,
ao lado de `requisitos.yaml`, `dominio.FORMATOS`, `criativos.ts` e das tabelas da
v11_02. Cópias não divergem no dia em que nascem; divergem seis meses depois, e
o sintoma é uma imagem gerada com o tamanho de ontem que a API recusa.

## Falha tem causa, e a causa tem código

Os cinco erros de `porta.py` viram cinco `Falha` distintas, cada uma com o
`permanente` que a cascata precisa para decidir se retentar tem sentido. Nenhum
deles vira `None`, lista vazia ou lote menor sem explicação:

    MotorIndisponivel   -> F5.motor_indisponivel     permanente=False
    PedidoRecusado      -> F6.pedido_recusado        permanente=True
    GeracaoPendente     -> F7.geracao_pendente       permanente=False
    GeracaoFracassada   -> F8.geracao_fracassada     permanente=True
    PedidoDesconhecido  -> F9.pedido_desconhecido    permanente=True

`F7` merece uma nota. Pendência **não é falha** — é "volte depois". Ela só vira
`Falha` quando o orçamento de tentativas acaba, e o motivo diz quantas foram.
Tratá-la como falha na primeira tentativa transformaria todo motor assíncrono em
motor quebrado; tratá-la como sucesso produziria um lote com menos arquivos do
que foi pedido, sem nenhum registro de que faltou.

## O que este módulo NÃO faz

Não fala com o Google, não escreve em disco, não lê relógio (o instante entra
injetado) e não monta payload de campanha. Montar payload é da ponte
(`volc_ads/criativo_ponte.py`), que é quem conhece os dois lados.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import requisitos
from .catalogo import Catalogo, assets_da_resposta
from .contrato import (
    Asset,
    ExigenciaDeCanal,
    Falha,
    LoteDeAssets,
    NaturezaDaProcedencia,
    Origem,
    TipoDeAsset,
)
from .porta import (
    ErroDoMotor,
    GeracaoFracassada,
    GeracaoPendente,
    MotorDeCriativo,
    MotorIndisponivel,
    PedidoDesconhecido,
    PedidoDeGeracao,
    PedidoRecusado,
    RespostaDoMotor,
)

CANAL_DISPLAY = "DISPLAY"
CANAL_DEMAND_GEN = "DEMAND_GEN"


# ── a receita ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Receita:
    """O que produzir, para qual canal, a partir de qual insumo.

    `papeis=None` significa "o mínimo que este canal aceita", derivado da régua.
    Passar a lista explicitamente é para quem quer mais do que o mínimo — nunca
    para contornar a régua, porque a validação continua sendo feita contra ela.
    """

    id: str
    canal: str
    rotulo: str = ""
    papeis: tuple[TipoDeAsset, ...] | None = None
    quantidade_por_papel: int = 1

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("receita sem id")
        if not self.canal.strip():
            raise ValueError(f"receita {self.id!r} sem canal")
        if self.quantidade_por_papel < 1:
            raise ValueError(
                f"receita {self.id!r}: quantidade_por_papel "
                f"{self.quantidade_por_papel} — pedir zero não é pedir"
            )


#: As receitas que esta camada conhece. Duas, e as duas são o MÍNIMO do canal:
#: o objetivo desta fatia é provar o caminho, não montar um catálogo de campanha.
RECEITAS: tuple[Receita, ...] = (
    Receita(
        id="display-minimo",
        canal=CANAL_DISPLAY,
        rotulo="Display — o mínimo que o canal aceita",
    ),
    Receita(
        id="demand-gen-minimo",
        canal=CANAL_DEMAND_GEN,
        rotulo="Demand Gen — o mínimo que o canal aceita",
    ),
)

_POR_ID: dict[str, Receita] = {r.id: r for r in RECEITAS}


class ReceitaDesconhecida(KeyError):
    """Erro próprio, e não `KeyError`, para que a rota distinga pedido inválido
    (culpa de quem chamou) de defeito nosso. É a mesma escolha que
    `dominio.SlotDesconhecido` já tinha feito do lado do Estúdio."""

    def __init__(self, receita_id: str) -> None:
        super().__init__(
            f"receita {receita_id!r} não existe. Conhecidas: "
            f"{', '.join(sorted(_POR_ID))}"
        )
        self.receita_id = receita_id


def receita_de(receita_id: str) -> Receita:
    try:
        return _POR_ID[receita_id]
    except KeyError:
        raise ReceitaDesconhecida(receita_id) from None


def papeis_da_receita(
    receita: Receita, exigencia: ExigenciaDeCanal
) -> tuple[TipoDeAsset, ...]:
    """Os papéis a produzir, derivados da régua quando a receita não os declara.

    São duas fontes de obrigação, e ignorar a segunda é o erro fácil:

      1. `quantidade_minima >= 1` numa especificação — "este canal exige N deste
         papel";
      2. `TetoCombinado.minimo >= 1` — "este canal exige N no CONJUNTO destes
         papéis, tanto faz qual".

    Demand Gen só é montável por causa da segunda: nenhuma imagem de marketing é
    individualmente obrigatória, e ainda assim o canal exige ao menos uma entre
    paisagem e quadrada (`imagem base`, mínimo 1). Uma derivação que olhasse só
    `obrigatorios` produziria um lote com o logo e mais nada, e o veredito
    devolveria `Q5.teto_combinado_falta` — correto, e inútil, porque o buraco
    estava na encomenda.
    """
    if receita.papeis is not None:
        return receita.papeis

    escolhidos: list[TipoDeAsset] = []
    for spec in exigencia.especificacoes:
        if spec.quantidade_minima >= 1 and spec.tipo is not TipoDeAsset.VIDEO:
            escolhidos.extend([spec.tipo] * spec.quantidade_minima)

    for teto in exigencia.combinados:
        if teto.minimo <= 0:
            continue
        ja = sum(1 for t in escolhidos if t in teto.tipos)
        candidatos = [t for t in teto.tipos if t is not TipoDeAsset.VIDEO]
        # Ordem estável: a do teto, que é a do YAML. Sorteio ou `set` fariam a
        # mesma receita produzir papéis diferentes entre duas execuções, e a
        # reprodutibilidade morreria antes do motor.
        i = 0
        while ja < teto.minimo and candidatos:
            escolhidos.append(candidatos[i % len(candidatos)])
            ja += 1
            i += 1

    return tuple(escolhidos)


# ── o resultado ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PedidoAtendido:
    """Um pedido feito ao motor e o que ele devolveu. Serve de rastro."""

    tipo: TipoDeAsset
    id_do_pedido: str | None      # `None` quando o motor recusou antes de emitir
    largura_pedida: int | None
    altura_pedida: int | None
    arquivos: int = 0
    falhas: int = 0


@dataclass(frozen=True)
class Producao:
    """O que uma receita produziu: o lote, os bytes e a procedência declarada.

    `conteudo` mapeia `Asset.identidade` → bytes, que é exatamente o que a ponte
    pede. Ele vive aqui e não dentro do `Asset` porque o `Asset` não carrega
    bytes de propósito (`contrato.py` explica), e porque um lote de vinte
    imagens em memória é diferente de vinte assets catalogados.
    """

    receita: Receita
    exigencia: ExigenciaDeCanal
    lote: LoteDeAssets
    conteudo: dict[str, bytes]
    catalogo: Catalogo
    natureza: NaturezaDaProcedencia
    motor: str
    versao_do_motor: str
    pedidos: tuple[PedidoAtendido, ...] = ()

    @property
    def publicavel(self) -> bool:
        """Esta produção pode ser apresentada como produção? Derivado."""
        return self.natureza.publicavel

    @property
    def assets(self) -> tuple[Asset, ...]:
        return self.lote.assets

    def resumo(self) -> str:
        linhas = [
            f"produção {self.receita.id} · {self.lote.canal} · "
            f"motor {self.motor}@{self.versao_do_motor} · "
            f"natureza {self.natureza.value}"
            + ("" if self.publicavel else " (NÃO publicável)")
        ]
        linhas.append("  " + self.lote.resumo().replace("\n", "\n  "))
        return "\n".join(linhas)


# ── a produção ──────────────────────────────────────────────────────────────


def _falha_de(
    erro: ErroDoMotor, tipo: TipoDeAsset, referencia: str
) -> Falha:
    """Traduz o erro tipado da porta na `Falha` que viaja dentro do lote.

    O mapa é explícito e não um `getattr(erro, 'codigo')` porque os códigos da
    porta (`MOTOR.*`) descrevem o MOTOR e os do lote (`F*`) descrevem o ARQUIVO
    que não existiu. Reaproveitar o primeiro como se fosse o segundo faria o
    relatório de um lote falar duas linguagens de código.
    """
    mapa: dict[type, tuple[str, bool]] = {
        MotorIndisponivel: ("F5.motor_indisponivel", False),
        PedidoRecusado: ("F6.pedido_recusado", True),
        GeracaoPendente: ("F7.geracao_pendente", False),
        GeracaoFracassada: ("F8.geracao_fracassada", True),
        PedidoDesconhecido: ("F9.pedido_desconhecido", True),
    }
    codigo, permanente = mapa.get(
        type(erro), ("F0.desconhecido", erro.permanente)
    )
    return Falha(
        referencia=referencia,
        motivo=erro.motivo,
        codigo=codigo,
        tipo=tipo,
        permanente=permanente,
    )


def produzir(
    receita: Receita,
    motor: MotorDeCriativo,
    *,
    insumo: str,
    quando: datetime,
    intencao: str = "",
    exigencia: ExigenciaDeCanal | None = None,
    tentativas_de_recebimento: int = 3,
) -> Producao:
    """Roda a receita contra o motor e devolve o lote com o que saiu e o que faltou.

    ## Por que `quando` é injetado

    Porque `Procedencia.quando` é obrigatório e um `datetime.now()` aqui dentro
    tornaria toda prova de reprodutibilidade dependente do relógio. O instante é
    um fato de quem encomendou, não deste laço. É a mesma escolha de
    `criativo_ponte.lote_de_pasta`, que usa o `mtime` do arquivo e diz isso na
    `nota` da procedência.

    ## Por que a natureza vem do MOTOR

    Porque quem sabe se um arquivo pode ser publicado é quem o produziu, e um
    parâmetro aqui permitiria a qualquer chamador declarar `PRODUCAO` sobre a
    saída de um motor de ensaio — que é exatamente o defeito que a natureza
    existe para fechar. Motor que não declara nada vale `NAO_DECLARADA`, nunca
    `PRODUCAO`: quem não respondeu não autorizou.
    """
    if not insumo.strip():
        raise ValueError(
            f"receita {receita.id!r} sem insumo: gerar a partir de quê?"
        )
    if tentativas_de_recebimento < 1:
        raise ValueError("tentativas_de_recebimento < 1 é não tentar")

    exigencia = exigencia or requisitos.exigencia_binaria_de(receita.canal)
    natureza = getattr(motor, "natureza", NaturezaDaProcedencia.NAO_DECLARADA)
    if not isinstance(natureza, NaturezaDaProcedencia):
        # Um motor que declara natureza numa string solta seria pior que um que
        # não declara nada: parece resposta e não é comparável.
        natureza = NaturezaDaProcedencia.NAO_DECLARADA

    catalogo = Catalogo()
    assets: list[Asset] = []
    falhas: list[Falha] = []
    conteudo: dict[str, bytes] = {}
    atendidos: list[PedidoAtendido] = []
    intencao = intencao or receita.id

    for ordem, tipo in enumerate(papeis_da_receita(receita, exigencia)):
        spec = exigencia.de(tipo)
        referencia = f"{receita.id}#{ordem}:{tipo.value}"
        pedido = PedidoDeGeracao(
            referencia=referencia,
            tipo=tipo,
            insumo=insumo,
            quantidade=receita.quantidade_por_papel,
            especificacao=spec,
            contexto={"receita": receita.id, "canal": exigencia.canal},
        )

        try:
            id_do_pedido = motor.solicitar_geracao(pedido)
        except ErroDoMotor as erro:
            falhas.append(_falha_de(erro, tipo, referencia))
            atendidos.append(PedidoAtendido(tipo, None, None, None, 0, 1))
            continue

        resposta, erro_ao_receber = _receber(
            motor, id_do_pedido, tentativas_de_recebimento
        )
        if resposta is None:
            assert erro_ao_receber is not None
            falhas.append(_falha_de(erro_ao_receber, tipo, referencia))
            atendidos.append(PedidoAtendido(tipo, id_do_pedido, None, None, 0, 1))
            continue

        novos, novas_falhas = assets_da_resposta(
            resposta,
            pedido,
            motor=motor.nome,
            versao=motor.versao,
            quando=quando,
            origem=Origem.GERADO,
            natureza=natureza,
        )
        for asset, arquivo in zip(novos, resposta.arquivos):
            bytes_do_arquivo = arquivo.conteudo
            if bytes_do_arquivo is None:
                # Asset textual: não tem bytes para a ponte conferir, e a ponte
                # é de imagem. Ele entra no lote e é a validação que decide.
                continue
            conteudo[asset.identidade] = bytes_do_arquivo

        assets.extend(novos)
        falhas.extend(novas_falhas)
        catalogo.absorver(novos, novas_falhas, intencao=intencao)
        atendidos.append(PedidoAtendido(
            tipo=tipo,
            id_do_pedido=id_do_pedido,
            largura_pedida=novos[0].largura if novos else None,
            altura_pedida=novos[0].altura if novos else None,
            arquivos=len(novos),
            falhas=len(novas_falhas),
        ))

    return Producao(
        receita=receita,
        exigencia=exigencia,
        lote=LoteDeAssets(
            canal=exigencia.canal,
            assets=tuple(assets),
            falhas=tuple(falhas),
            intencao=intencao,
        ),
        conteudo=conteudo,
        catalogo=catalogo,
        natureza=natureza,
        motor=motor.nome,
        versao_do_motor=motor.versao,
        pedidos=tuple(atendidos),
    )


def _receber(
    motor: MotorDeCriativo, id_do_pedido: str, tentativas: int
) -> tuple[RespostaDoMotor | None, ErroDoMotor | None]:
    """Insiste enquanto for pendência, desiste no primeiro erro definitivo.

    ⚠️ Sem `sleep`. Este módulo não decide política de espera — quem quiser
    espera com intervalo envolve `produzir` num laço próprio. Um `sleep` aqui
    tornaria o teste da pendência lento por construção, e "teste lento" é a
    primeira coisa que alguém desliga.
    """
    ultimo: ErroDoMotor | None = None
    for _ in range(tentativas):
        try:
            return motor.receber(id_do_pedido), None
        except GeracaoPendente as erro:
            ultimo = GeracaoPendente(
                f"{erro.motivo} — {tentativas} tentativa(s) de recebimento "
                f"esgotadas sem resultado",
                pedido=erro.pedido,
            )
            continue
        except ErroDoMotor as erro:
            return None, erro
    return None, ultimo
