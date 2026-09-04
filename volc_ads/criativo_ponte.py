"""A fronteira entre o motor de criativo e o construtor de campanha.

## Por que este arquivo não mora nem em `criativo/` nem em `campanha/`

Os dois lados recusaram explicitamente conhecer o outro, e os dois tinham razão:

  `criativo/__init__.py`  "Nada aqui fala com o Google Ads. Subir asset é do
                          domínio de campanha." E `criativo/requisitos.py` chega
                          a ler `campanha/limites.yaml` **como arquivo**,
                          tolerando ausência, só para não importar `campanha/`.

  `campanha/brief.py`     "Esta classe não importa `volc_ads/criativo/`. (…) O
                          construtor de campanha não deve depender do pacote de
                          criativo para montar um payload — são donos
                          diferentes, e o acoplamento tornaria impossível testar
                          um sem o outro."

Logo, quem conhece os dois não pode ser nenhum dos dois. Este é o mesmo lugar
que `volc_ads/pautador_ponte.py` ocupa do lado da mineração: importa
`campanha.brief` (nunca `campanha.display`), não é importado por ninguém dentro
dos dois pacotes, e devolve estrutura pronta. É a camada de aplicação.

Sem ciclo: `criativo_ponte` → {`criativo.*`, `campanha.brief`}. Nada em
`criativo/` nem em `campanha/` importa daqui.

## O que esta ponte resolve, e que não era de formato

O `Asset` do criativo **não carrega bytes** — só `conteudo_hash`,
`bytes_totais`, `mime` e dimensão. Os bytes existem em `porta.ArquivoGerado.
conteudo` e são descartados por `catalogo.assets_da_resposta()`. Já
`ImagemParaSubir` **exige** `dados: bytes`.

Um `asset_para_imagem(asset)` é, portanto, impossível de escrever: falta a
metade que importa. Por isso a assinatura pede o conteúdo separado — e, tendo
os dois em mãos, a ponte faz a única coisa honesta possível: **recomputa o
sha256 dos bytes e compara com o hash que o asset declara**. Sem essa
conferência, a procedência seria um rótulo colado num arquivo que ninguém provou
ser aquele — e um rastro que não se confere não é rastro, é decoração.

## A ordem dos passos não é arbitrária

  1. resolver a exigência do canal (só a parte de ARQUIVO)
  2. `validar_lote()`  ← a validação acontece ANTES de existir qualquer payload
  3. reprovou? devolve sem `ImagensDisplay`. Não há o que passar adiante.
  4. só então, para cada APROVADO: papel, bytes, hash conferido, linhagem
  5. papel obrigatório que esvaziou por falta de bytes derruba a entrega

O requisito "lote inválido não avança silenciosamente" fica cumprido
**estruturalmente**, não por disciplina: quando o lote reprova, o
`ImagensDisplay` não existe.

O passo 5 não é redundância do 2. `validar_lote` julga assets; ele não sabe se
temos os bytes em mãos. Um lote perfeitamente válido cujo `marketing` ficou sem
conteúdo produziria um `ImagensDisplay` incompleto, e o operador leria uma
recusa sobre o payload em vez da recusa verdadeira — "faltam os bytes".
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Mapping

from .campanha import validacao as _validacao_de_campanha
from .campanha.brief import (
    AssetRemotoDemandGen,
    ImagemParaSubir,
    ImagensDemandGen,
    ImagensDisplay,
    ImagensPMax,
    Linhagem,
    ReciboAssetAprovado,
    _emitir_recibo_asset_aprovado,
)
from .criativo import requisitos, validacao
from .criativo.adaptadores import medir_imagem
from .criativo.contrato import (
    Asset,
    ExigenciaDeCanal,
    Falha,
    LoteDeAssets,
    NaturezaDaProcedencia,
    Origem,
    Procedencia,
    TipoDeAsset,
    Violacao,
    hash_de_conteudo,
)
from .criativo.validacao import ResultadoDeValidacao

CANAL_DISPLAY = "DISPLAY"
CANAL_DEMAND_GEN = "DEMAND_GEN"
CANAL_PMAX = "PERFORMANCE_MAX"


# ── a tabela de papéis, e a armadilha que ela desarma ───────────────────────
#
# ⚠️ LEIA ANTES DE "CORRIGIR": `ImagensDisplay.logo` é o campo **4:1**
# (`logo_images` no proto), e `logo_quadrado` é o **1:1**. O pareamento que a
# intuição sugere — `logo` ↔ `LOGO_QUADRADO`, porque os dois nomes são curtos —
# está ERRADO, e o erro é caro: as duas imagens entrariam nos campos trocados,
# a API recusaria o mutate inteiro por proporção, e a mensagem apontaria para o
# ANÚNCIO. Ninguém suspeitaria desta tabela.
#
# Há teste que confere cada linha contra a proporção declarada em
# `criativo/requisitos.yaml` — a tabela é conferida contra a fonte, não revisada
# a olho.

PAPEL_POR_TIPO: dict[TipoDeAsset, str] = {
    TipoDeAsset.IMAGEM_MARKETING: "marketing",                    # 1.91:1
    TipoDeAsset.IMAGEM_MARKETING_QUADRADA: "marketing_quadrada",  # 1:1
    TipoDeAsset.LOGO_PAISAGEM: "logo",                            # 4:1
    TipoDeAsset.LOGO_QUADRADO: "logo_quadrado",                   # 1:1
}

PAPEL_POR_TIPO_DEMAND_GEN: dict[TipoDeAsset, str] = {
    TipoDeAsset.IMAGEM_MARKETING: "marketing",
    TipoDeAsset.IMAGEM_MARKETING_QUADRADA: "marketing_quadrada",
    TipoDeAsset.IMAGEM_MARKETING_RETRATO: "marketing_retrato",
    TipoDeAsset.IMAGEM_MARKETING_RETRATO_ALTO: "marketing_retrato_alto",
    TipoDeAsset.LOGO_QUADRADO: "logo_quadrado",
}

PAPEL_POR_TIPO_PMAX: dict[TipoDeAsset, str] = {
    TipoDeAsset.IMAGEM_MARKETING: "marketing",
    TipoDeAsset.IMAGEM_MARKETING_QUADRADA: "marketing_quadrada",
    TipoDeAsset.IMAGEM_MARKETING_RETRATO: "marketing_retrato",
    TipoDeAsset.LOGO_QUADRADO: "logo",
    TipoDeAsset.LOGO_PAISAGEM: "logo_paisagem",
}


class Destino(Enum):
    """Para onde este payload vai — e é isso que decide quem pode entrar nele.

    ## Por que a fronteira é AQUI, e não no validador

    `validacao.py` responde "este arquivo serve para o canal?" — geometria, peso,
    formato, contagem. A natureza da procedência não é uma propriedade do
    arquivo: um PNG de ensaio 1200×628 é geometricamente idêntico ao banner que a
    agência pagou. A pergunta "pode subir para uma conta real?" só existe no
    instante em que o payload é montado, e este módulo é esse instante.

    ## Por que `PRODUCAO` é o padrão

    Porque o padrão é o que acontece com quem não pensou no assunto, e o erro
    caro tem uma direção só: subir ensaio achando que é produção. O contrário —
    recusar um asset de produção porque alguém esqueceu de declarar o destino —
    custa uma mensagem de recusa nomeada, que é barato e visível.

    `ENSAIO` não é "modo relaxado": ele não afrouxa geometria, peso nem contagem.
    Ele afrouxa exatamente uma coisa, a natureza, e carimba isso na `Entrega`
    para que ninguém leia o payload sem ver o rótulo.
    """

    PRODUCAO = "producao"
    ENSAIO = "ensaio"


#: As naturezas que cada destino aceita. Tabela, e não `if`, porque um destino
#: novo (homologação, conta de sandbox) precisa declarar sua política em vez de
#: herdá-la de um `else`.
NATUREZAS_ACEITAS: dict[Destino, frozenset[NaturezaDaProcedencia]] = {
    Destino.PRODUCAO: frozenset({
        NaturezaDaProcedencia.PRODUCAO,
        # ⚠️ `NAO_DECLARADA` entra, e isso é uma DÍVIDA declarada, não um
        # descuido. Todo `Asset` construído antes deste campo existir — o
        # caminho de pasta do operador, as fixtures dos testes de campanha, os
        # adaptadores de motor pago — nasce sem natureza. Recusá-los aqui
        # quebraria o único caminho que hoje monta payload de verdade, para
        # ganhar uma garantia que a ausência não dá de qualquer modo.
        #
        # O que ELA ganha em troca é visibilidade: cada asset sem natureza sai
        # nomeado em `Entrega.avisos`. Quando os produtores declararem, esta
        # linha sai e o aviso vira recusa.
        NaturezaDaProcedencia.NAO_DECLARADA,
    }),
    Destino.ENSAIO: frozenset(NaturezaDaProcedencia),
}


class PonteIncompleta(RuntimeError):
    """Erro de programador: o pedido não faz sentido para esta fronteira.

    Reservado ao que nenhum dado de entrada pode causar — canal sem exigência
    de arquivo, por exemplo. Problema de LOTE nunca levanta: vira veredito.
    """


@dataclass(frozen=True)
class Entrega:
    """O que a fronteira devolve: o veredito, e o payload quando houver.

    ## Por que não é exceção

    `criativo/validacao.py` já decidiu isto para este domínio, e a razão é
    dinheiro: "devolve tudo, não a primeira" e "um asset ruim não derruba o
    lote". Levantar jogaria fora justamente o veredito, que é o que diz qual é
    o remédio mais barato — regerar é chamada paga, recortar é local.

    ## Por que não é um par `(imagens, veredito)`

    Porque tupla se desempacota e o segundo elemento se ignora. Com `Entrega`,
    o único caminho até as imagens passa por `imagens`, que é `Optional` — o
    caso "reprovou" é obrigatório de tratar para chegar ao payload.

    ## Como os DOIS `Resultado` da casa convivem sem virar um terceiro

    `veredito` é o `ResultadoDeValidacao` do criativo, **sem tradução**. Quem já
    tem um `campanha.validacao.Resultado` na mão usa `anexar()`, que é uma
    projeção de MÃO ÚNICA. É o mesmo desenho de `campanha/conteudo.registrar`,
    que já faz exatamente isso com o terceiro tipo de violação da casa
    (`policy.Violacao`): um tradutor por tipo estrangeiro, sempre na mesma
    direção, nunca de volta.
    """

    veredito: ResultadoDeValidacao
    imagens: ImagensDisplay | ImagensDemandGen | ImagensPMax | None = None
    linhagem: tuple[Linhagem, ...] = ()
    #: O que a ponte descartou e por quê — bytes ausentes, hash divergente,
    #: asset já na conta, tipo sem papel neste canal, natureza não publicável.
    #: Uma linha por descarte.
    recusas: tuple[str, ...] = ()
    #: Para onde este payload ia quando foi montado. Viaja junto porque um
    #: `ImagensDisplay` no meio de um log não diz sozinho se nasceu de um ensaio.
    destino: Destino = Destino.PRODUCAO
    #: `Asset.identidade` -> valor de `NaturezaDaProcedencia`, para **cada**
    #: asset do lote — inclusive os que a ponte depois recusou. Quem lê a
    #: entrega precisa saber o que havia no lote, não só o que sobrou.
    naturezas: dict[str, str] = field(default_factory=dict)
    #: O que passou mas merece ser dito. Hoje: asset sem natureza declarada num
    #: destino de produção. Aviso e não recusa — ver `NATUREZAS_ACEITAS`.
    avisos: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Há payload montável? Nunca derive isto de `veredito.ok` sozinho.

        Um lote aprovado cujos bytes não estavam em mãos tem `veredito.ok` True
        e `imagens` None. As duas perguntas são diferentes: uma é sobre os
        arquivos serem bons, a outra é sobre eles estarem disponíveis.
        """
        return self.imagens is not None

    def resumo(self) -> str:
        linhas = [self.veredito.resumo()]
        linhas.append(f"  destino: {self.destino.value}")
        nao_publicaveis = sorted(
            i for i, n in self.naturezas.items()
            if n != NaturezaDaProcedencia.PRODUCAO.value
        )
        if nao_publicaveis:
            linhas.append(
                f"  ⚠️ {len(nao_publicaveis)} asset(s) de natureza não "
                f"publicável no lote: "
                + ", ".join(f"{i}={self.naturezas[i]}" for i in nao_publicaveis)
            )
        if self.avisos:
            linhas.extend(f"  ⚠️ {m}" for m in self.avisos)
        if self.recusas:
            linhas.append(f"  descartados pela ponte: {len(self.recusas)}")
            linhas.extend(f"    {m}" for m in self.recusas)
        if self.imagens is None:
            linhas.append("  → nenhum payload montado")
        else:
            confirmadas = sum(1 for ln in self.linhagem if ln.confirmada)
            linhas.append(
                f"  → {len(self.linhagem)} imagens, "
                f"{confirmadas} com procedência confirmada")
        return "\n".join(linhas)


# ── projeção de Asset para Linhagem ─────────────────────────────────────────


def _quando_iso(quando: datetime | None) -> str | None:
    """`datetime` → ISO-8601, preservando o que se sabe do fuso.

    ⚠️ Um `datetime` ingênuo (sem tzinfo) sai SEM offset, de propósito. As duas
    alternativas seriam piores:

      assumir UTC        inventaria informação que ninguém apurou, e o erro
                         ficaria invisível — um horário errado parece um
                         horário certo;
      recusar o ingênuo  inventaria uma exigência que `Procedencia` nunca fez.
                         O contrato não diz se `quando` é aware ou naive, e as
                         fixtures da casa usam naive.

    A ausência de offset na string É a resposta honesta: sabemos o instante
    local, não o fuso.
    """
    if quando is None:
        return None
    return quando.isoformat()


def linhagem_de(
    asset: Asset, papel: str, exigencia: ExigenciaDeCanal, *, nome: str
) -> Linhagem:
    """Projeta um `Asset` medido na `Linhagem` que viaja até o recibo.

    Projetar é copiar, nunca completar. Todo campo que o `Asset` não sabe sai
    `None` — em particular `custo_usd`, que é `None` quando o motor não reportou
    e jamais `0.0`. Um relatório de COGS que soma zeros inventados fecha bonito
    e está errado.
    """
    p = asset.procedencia
    return Linhagem(
        nome=nome,
        papel=papel,
        identidade=asset.identidade,
        conteudo_hash=asset.conteudo_hash,
        motor=p.motor or None,
        versao_do_motor=p.versao_do_motor,
        insumo=p.insumo or None,
        insumo_hash=p.insumo_hash,
        pedido=p.pedido or None,
        quando=_quando_iso(p.quando),
        origem=asset.origem.value,
        mime=asset.mime,
        largura=asset.largura,
        altura=asset.altura,
        bytes_totais=asset.bytes_totais,
        custo_usd=p.custo_usd,
        derivado_de=asset.derivado_de,
        id_externo=asset.id_externo,
        exigencia_fonte=exigencia.fonte or None,
        exigencia_provisoria=exigencia.provisorio,
    )


def _recibo_de(
    asset: Asset,
    papel: str,
    exigencia: ExigenciaDeCanal,
    *,
    nome: str,
    linhagem: Linhagem,
) -> ReciboAssetAprovado:
    """Emite o recibo só depois do veredito e da conferência dos bytes."""
    return _emitir_recibo_asset_aprovado(
        catalogo_id=asset.identidade,
        canal=exigencia.canal,
        nome=nome,
        papel=papel,
        conteudo_hash=asset.conteudo_hash,
        mime=asset.mime,
        largura=asset.largura,
        altura=asset.altura,
        bytes_totais=asset.bytes_totais,
        resource_name=asset.id_externo,
        exigencia_fonte=exigencia.fonte or None,
        exigencia_provisoria=exigencia.provisorio,
        medidor_id="volc_ads.criativo.adaptadores.medir_imagem:v1",
        reconferidor=_reconferir_medidas,
        linhagem=linhagem,
    )


def _reconferir_medidas(
    dados: bytes,
) -> tuple[str | None, int | None, int | None, int]:
    """Adapta o medidor autoritativo para o contrato opaco do recibo."""
    medida = medir_imagem.medir(dados)
    return medida.mime, medida.largura, medida.altura, medida.bytes_totais


# ── a fronteira ─────────────────────────────────────────────────────────────


def imagens_de_display(
    lote: LoteDeAssets,
    conteudo_por_identidade: Mapping[str, bytes],
    *,
    exigencia: ExigenciaDeCanal | None = None,
    destino: Destino = Destino.PRODUCAO,
) -> Entrega:
    """Valida o lote e, se ele servir, monta o `ImagensDisplay` com linhagem.

    `conteudo_por_identidade` mapeia `Asset.identidade` → bytes. Ele é
    obrigatório porque o `Asset` não carrega conteúdo (ver o cabeçalho). Uma
    identidade ausente do mapa **não** vira imagem: o asset é descartado com
    recusa nomeada. "Asset não persistido" não é "asset disponível".

    ## A ordem das duas recusas de canal, que não é arbitrária

    Primeiro a régua, depois a porta. Um lote `SEARCH` ou `TIKTOK` morre no
    `exigencia_binaria_de`, com a mensagem que nomeia o dono daquele canal — é a
    informação que o operador precisa, e ela se perderia atrás de um "esta ponte
    é de Display". Um lote `DEMAND_GEN` passa da régua (ele TEM régua de arquivo)
    e é aí que a porta o barra: sem esta guarda ele seria validado contra a régua
    do Demand Gen e mapeado com a tabela de papéis do DISPLAY — `logo` é 4:1 num
    lado e nem existe no outro —, montando um payload que a API recusaria por
    proporção, com o erro apontando para o anúncio.
    """
    if exigencia is None:
        exigencia = requisitos.exigencia_binaria_de(lote.canal)
    if lote.canal != CANAL_DISPLAY:
        raise PonteIncompleta(
            f"imagens_de_display recebeu lote {lote.canal!r}; esperado "
            f"{CANAL_DISPLAY!r}"
        )
    return _imagens_de(
        lote,
        conteudo_por_identidade,
        exigencia=exigencia,
        classe_imagens=ImagensDisplay,
        papel_por_tipo=PAPEL_POR_TIPO,
        destino=destino,
    )


def imagens_de_demand_gen(
    lote: LoteDeAssets,
    conteudo_por_identidade: Mapping[str, bytes],
    *,
    exigencia: ExigenciaDeCanal | None = None,
    destino: Destino = Destino.PRODUCAO,
) -> Entrega:
    """Valida pelo contrato do Estúdio e monta ``ImagensDemandGen``.

    Nenhum número ou geometria é recalculado aqui: a autoridade continua em
    ``criativo/requisitos.py`` + ``validacao.py``. Esta função só traduz cada
    papel aprovado para o contrato do builder.
    """
    if lote.canal != CANAL_DEMAND_GEN:
        raise PonteIncompleta(
            f"imagens_de_demand_gen recebeu lote {lote.canal!r}; esperado "
            f"{CANAL_DEMAND_GEN!r}"
        )
    entrega = _imagens_de(
        lote,
        conteudo_por_identidade,
        exigencia=exigencia,
        classe_imagens=ImagensDemandGen,
        papel_por_tipo=PAPEL_POR_TIPO_DEMAND_GEN,
        destino=destino,
    )
    # Demand Gen não aceita uma entrega que descartou parte do pedido. O caller
    # não tem como distinguir "a primeira duplicata venceu" de "tudo entrou"
    # olhando só para ImagensDemandGen, e esta rodada exige recusa explícita.
    if entrega.imagens is not None and entrega.recusas:
        return Entrega(
            veredito=entrega.veredito,
            imagens=None,
            linhagem=(),
            recusas=entrega.recusas,
            destino=entrega.destino,
            naturezas=entrega.naturezas,
            avisos=entrega.avisos,
        )
    return entrega


def imagens_de_pmax(
    lote: LoteDeAssets,
    conteudo_por_identidade: Mapping[str, bytes],
    *,
    exigencia: ExigenciaDeCanal | None = None,
    destino: Destino = Destino.PRODUCAO,
) -> Entrega:
    """Valida e projeta os cinco papéis visuais do Asset Group PMax."""
    if lote.canal != CANAL_PMAX:
        raise PonteIncompleta(
            f"imagens_de_pmax recebeu lote {lote.canal!r}; esperado "
            f"{CANAL_PMAX!r}"
        )
    entrega = _imagens_de(
        lote,
        conteudo_por_identidade,
        exigencia=exigencia,
        classe_imagens=ImagensPMax,
        papel_por_tipo=PAPEL_POR_TIPO_PMAX,
        destino=destino,
    )
    if entrega.imagens is not None and entrega.recusas:
        return Entrega(
            veredito=entrega.veredito,
            imagens=None,
            linhagem=(),
            recusas=entrega.recusas,
            destino=entrega.destino,
            naturezas=entrega.naturezas,
            avisos=entrega.avisos,
        )
    return entrega


def _imagens_de(
    lote: LoteDeAssets,
    conteudo_por_identidade: Mapping[str, bytes],
    *,
    exigencia: ExigenciaDeCanal | None,
    classe_imagens,
    papel_por_tipo: Mapping[TipoDeAsset, str],
    destino: Destino = Destino.PRODUCAO,
) -> Entrega:
    """Implementação única da fronteira Asset → imagens por papel."""
    exigencia = exigencia or requisitos.exigencia_binaria_de(lote.canal)
    veredito = validacao.validar_lote(lote, exigencia)
    recusas: list[str] = []
    avisos: list[str] = []
    aceitas = NATUREZAS_ACEITAS[destino]
    # ⚠️ Registrado sobre o lote INTEIRO, não só sobre os aprovados.
    # Quem lê a entrega para decidir se pode publicar precisa saber que havia um
    # asset de ensaio ali dentro mesmo quando ele foi reprovado por outro motivo
    # — senão a mesma peça, com a geometria corrigida, entra na rodada seguinte
    # sem que ninguém lembre de onde ela veio.
    naturezas = {a.identidade: a.procedencia.natureza.value for a in lote.assets}

    if not veredito.ok:
        # Nada é montado. Não é uma escolha de estilo: um payload parcial
        # construído a partir de um lote reprovado é exatamente o objeto que
        # atravessaria o resto do sistema sem que ninguém soubesse que ele
        # nasceu de um veredito negativo.
        return Entrega(
            veredito=veredito, imagens=None, recusas=tuple(recusas),
            destino=destino, naturezas=naturezas, avisos=tuple(avisos),
        )

    imagens = classe_imagens()
    # Deduplicação POR PAPEL, não global: o catálogo já declara que o mesmo
    # arquivo servindo dois papéis não é conflito (uma imagem 1:1 é logo
    # quadrada e imagem de marketing quadrada ao mesmo tempo). Deduplicar
    # globalmente descartaria o segundo uso legítimo.
    vistos_por_papel: dict[str, set[str]] = {
        p: set() for p in classe_imagens.PAPEIS
    }

    for asset in veredito.aprovados:
        # ── a guarda de natureza, e por que ela vem ANTES do papel ──────────
        #
        # Se ela viesse depois, um asset de ensaio sem papel neste canal sairia
        # com a recusa errada ("não tem papel de imagem em DISPLAY"), e quem
        # lesse o relatório concluiria que o problema era de tipo. A recusa mais
        # grave é a que precisa aparecer, e esta é a que impede dinheiro de ser
        # gasto sobre uma peça que ninguém aprovou para publicar.
        natureza = asset.procedencia.natureza
        if natureza not in aceitas:
            recusas.append(
                f"{asset.identidade}: procedência de natureza "
                f"{natureza.value!r} não pode ser apresentada como "
                f"{destino.value} — este payload vai para uma conta real e "
                f"peça de ensaio/fixture não sobe. Se a intenção era provar o "
                f"caminho, peça `destino=Destino.ENSAIO`")
            continue
        if (
            destino is Destino.PRODUCAO
            and natureza is NaturezaDaProcedencia.NAO_DECLARADA
        ):
            avisos.append(
                f"{asset.identidade}: natureza da procedência não declarada. "
                f"Passou porque ausência de declaração ainda não é recusa "
                f"(ver NATUREZAS_ACEITAS), mas ninguém afirmou que este "
                f"arquivo é de produção")

        papel = papel_por_tipo.get(asset.tipo)
        if papel is None:
            # VIDEO cai aqui: o responsive display ad referencia vídeo por
            # `youtube_videos`, que é resource name de asset já na conta — outro
            # caminho, com outro dono. Silenciar seria perder o arquivo sem dizer.
            destino = (
                "as quatro famílias do responsive display ad, e vídeo entra "
                "por `brief.videos`"
                if lote.canal == CANAL_DISPLAY
                else "somente as famílias de imagem declaradas pelo contrato "
                "do canal"
            )
            recusas.append(
                f"{asset.identidade}: {asset.tipo.value} não tem papel de imagem "
                f"em {lote.canal} — este caminho monta {destino}")
            continue

        if asset.id_externo and classe_imagens is not ImagensDemandGen:
            # Asset que já existe na conta. Rebaixá-lo em silêncio para um `str`
            # na lista perderia a linhagem — e preservá-la exigiria uma terceira
            # forma em `ImagensDisplay`, o que muda o `isinstance` do construtor.
            # Recusa nomeada agora; reuso com linhagem é outra fatia.
            recusas.append(
                f"{asset.identidade}: já existe na conta ({asset.id_externo}) e "
                f"esta ponte só emite assets que nascem no mutate. Passe o "
                f"resource name direto em `{classe_imagens.__name__}.{papel}`, ciente de "
                f"que a linhagem não acompanha esse caminho")
            continue

        dados = conteudo_por_identidade.get(asset.identidade)
        if not dados:
            recusas.append(
                f"{asset.identidade}: sem bytes em mãos. O asset foi medido e "
                f"aprovado, mas o conteúdo não veio no mapa — asset não "
                f"persistido não é asset disponível")
            continue

        recomputado = hash_de_conteudo(dados)
        if recomputado != asset.conteudo_hash:
            # A conferência que dá sentido a tudo o mais. Sem ela, a linhagem
            # descreveria um arquivo e o payload carregaria outro.
            recusas.append(
                f"{asset.identidade}: os bytes não são os do asset — declarado "
                f"{asset.conteudo_hash[:19]}…, recomputado {recomputado[:19]}…. "
                f"A procedência descreveria um arquivo e o mutate levaria outro")
            continue

        if asset.conteudo_hash in vistos_por_papel[papel]:
            recusas.append(
                f"{asset.identidade}: conteúdo idêntico a outro já incluído em "
                f"`{papel}` — a primeira ocorrência fica. Duas cópias do mesmo "
                f"arquivo no mesmo papel gastam duas vagas do teto do canal")
            continue
        vistos_por_papel[papel].add(asset.conteudo_hash)

        nome = asset.rotulo.strip() or asset.identidade
        linhagem = linhagem_de(asset, papel, exigencia, nome=nome)

        # ── o recibo, agora nos DOIS canais ────────────────────────────────
        #
        # ⚠️ Até 01/09/2026 o recibo tipado saía só no Demand Gen, e o
        # comentário dizia "Display preserva o contrato anterior". O contrato
        # anterior era só o que já existia — não uma razão. E a diferença ficou
        # cara no dia em que a rota HTTP de Display passou a chamar esta ponte:
        # o mesmo asset atravessava com recibo por uma porta e sem recibo pela
        # outra, e quem lesse os dois payloads não teria como afirmar a mesma
        # coisa sobre eles.
        #
        # O recibo é reconferência dos bytes contra a linhagem. Emiti-lo é a
        # parte barata; descobrir depois que o payload do Display não tinha como
        # provar de onde veio é a parte cara.
        try:
            recibo = _recibo_de(
                asset, papel, exigencia, nome=nome, linhagem=linhagem
            )
        except (TypeError, ValueError) as exc:
            # ⚠️ Recusa, e não recibo `None`. Um asset que não consegue provar
            # a própria procedência não é um asset com um campo a menos: é um
            # asset que não deveria subir. Silenciar aqui devolveria ao payload
            # exatamente a peça sem prova que o recibo existe para barrar.
            recusas.append(
                f"{asset.identidade}: não foi possível emitir recibo "
                f"tipado: {exc}"
            )
            continue

        if classe_imagens is ImagensDemandGen:
            if asset.id_externo:
                item = AssetRemotoDemandGen(
                    resource_name=asset.id_externo,
                    dados=dados,
                    recibo=recibo,
                )
            else:
                item = ImagemParaSubir(
                    nome=nome,
                    dados=dados,
                    linhagem=linhagem,
                    mime=asset.mime,
                    largura=asset.largura,
                    altura=asset.altura,
                    recibo_aprovacao=recibo,
                )
        else:
            item = ImagemParaSubir(
                nome=nome,
                dados=dados,
                linhagem=linhagem,
                mime=asset.mime,
                largura=asset.largura,
                altura=asset.altura,
                recibo_aprovacao=recibo,
            )
        getattr(imagens, papel).append(item)

    # ── passo 5: o papel obrigatório que esvaziou depois da validação ───────
    #
    # `validar_lote` contou os APROVADOS; esta lista conta os que de fato têm
    # bytes conferidos. Quando um descarte esvazia um papel obrigatório, o lote
    # deixa de ser montável — e o motivo verdadeiro é a falta do arquivo, não
    # uma contagem do payload.
    faltando = [
        papel_por_tipo[tipo]
        for tipo in exigencia.obrigatorios
        if tipo in papel_por_tipo and not getattr(imagens, papel_por_tipo[tipo])
    ]
    faltando_combinado = []
    for teto in exigencia.combinados:
        if teto.minimo <= 0:
            continue
        quantidade = sum(
            len(getattr(imagens, papel_por_tipo[tipo]))
            for tipo in teto.tipos
            if tipo in papel_por_tipo
        )
        if quantidade < teto.minimo:
            faltando_combinado.append(
                f"{teto.rotulo}: {quantidade}/{teto.minimo}"
            )
    if faltando:
        recusas.append(
            f"papéis obrigatórios sem nenhuma imagem utilizável após os "
            f"descartes acima: {', '.join(faltando)}. O lote foi APROVADO na "
            f"validação — o que faltou foi o conteúdo, não a qualidade")
        return Entrega(
            veredito=veredito, imagens=None, recusas=tuple(recusas),
            destino=destino, naturezas=naturezas, avisos=tuple(avisos),
        )
    if faltando_combinado:
        recusas.append(
            "mínimos combinados sem conteúdo utilizável após os descartes: "
            + ", ".join(faltando_combinado)
        )
        return Entrega(
            veredito=veredito, imagens=None, recusas=tuple(recusas),
            destino=destino, naturezas=naturezas, avisos=tuple(avisos),
        )

    return Entrega(
        veredito=veredito,
        imagens=imagens,
        # ⚠️ DERIVADA, nunca acumulada. A primeira versão deste arquivo montava
        # a lista dentro do laço acima — e o laço percorre `veredito.aprovados`,
        # que está na ordem do LOTE, enquanto `linhagens()` percorre a ordem
        # canônica dos PAPÉIS. As duas divergiam sempre que o lote não chegasse
        # já ordenado por papel, e o sintoma seria a procedência da logo
        # carimbada no banner. Um teste pegou; a correção é não ter a segunda
        # lista, e não sincronizá-la.
        linhagem=imagens.linhagens(),
        recusas=tuple(recusas),
        destino=destino,
        naturezas=naturezas,
        avisos=tuple(avisos),
    )


# ── projeção de mão única para o diário do construtor ───────────────────────


def anexar(entrega: Entrega, r: _validacao_de_campanha.Resultado, *,
           campo: str = "imagens_display") -> _validacao_de_campanha.Resultado:
    """Escreve as violações do criativo no `Resultado` de campanha.

    Mão única, e por dois motivos. Primeiro, `Violacao` carrega `classe` — o
    remédio — e `Achado` não tem onde guardá-la; a volta perderia informação.
    Segundo, os dois vocabulários têm donos diferentes, e um tradutor
    bidirecional convida os dois a convergirem até virarem um só tipo mal
    definido.

    A severidade é preservada tal como veio. Promover aviso a erro aqui faria o
    construtor recusar localmente o que a API aceita — e portão com falso
    positivo é portão desligado.
    """
    for v in entrega.veredito.violacoes:
        alvo = f"{campo}.{v.alvo}" if v.alvo else campo
        escrever = r.erro if v.severidade == "erro" else r.aviso
        escrever(alvo, v.codigo, f"[{v.classe.value}] {v.detalhe}")
    for motivo in entrega.recusas:
        r.aviso(campo, "descartado pela ponte", motivo)
    return r


def violacoes_por_codigo(entrega: Entrega) -> dict[str, tuple[Violacao, ...]]:
    """Agrupa o veredito por código — atalho de leitura para relatório e teste."""
    saida: dict[str, list[Violacao]] = {}
    for v in entrega.veredito.violacoes:
        saida.setdefault(v.codigo, []).append(v)
    return {codigo: tuple(itens) for codigo, itens in saida.items()}


# ── o consumidor: uma pasta de arquivos vira um lote validado ───────────────
#
# Esta é a razão de a ponte não ser um ponto de extensão sem consumidor. A
# revisão adversarial de 27/08/2026 acertou ao apontar que, sem ela,
# `validar_lote()` continuaria sem rodar em lugar nenhum: `pautador_ponte.
# montar_brief` nunca preenche `imagens_display`, então o caminho HTTP não
# alcança este código — e isso continua verdade, e está declarado no relatório.
#
# O que existe agora é o caminho do OPERADOR: quatro arquivos numa pasta, uma
# linha de comando, e um `ImagensDisplay` medido, validado e com procedência.
# É o mesmo tipo de porta que `volc_ads/subir.py` já oferece com o `main()`
# dele. Nada aqui fala com o Google, e não há como falar: este módulo não
# importa `gads`.

#: Subpasta por papel. O papel é DECLARADO pela estrutura de diretórios, e não
#: adivinhado pela proporção do arquivo: uma imagem 1:1 é logo quadrada OU
#: imagem de marketing quadrada, e só quem encomendou sabe qual.
_TIPO_POR_PASTA: dict[str, TipoDeAsset] = {
    papel: tipo for tipo, papel in PAPEL_POR_TIPO.items()
}

# ⚠️ A inversão de um dicionário só é segura enquanto os VALORES forem únicos.
# Se um `TipoDeAsset` novo mapear para um papel já usado, a inversão descarta um
# dos dois em silêncio e os arquivos daquela pasta viram o tipo errado — sem
# erro, sem aviso. A checagem custa uma linha e roda no import.
if len(_TIPO_POR_PASTA) != len(PAPEL_POR_TIPO):
    raise RuntimeError(
        "PAPEL_POR_TIPO tem papéis repetidos: a inversão perderia um tipo em "
        f"silêncio. {PAPEL_POR_TIPO}")


def lote_de_pasta(
    raiz: pathlib.Path,
    *,
    motor: str,
    insumo: str,
    versao_do_motor: str = "",
    origem: Origem = Origem.HUMANO,
    canal: str = CANAL_DISPLAY,
) -> tuple[LoteDeAssets, dict[str, bytes], tuple[str, ...]]:
    """Lê `raiz/<papel>/*` e devolve (lote, bytes por identidade, avisos).

    ## O instante que temos, e o que ele significa

    `Procedencia.quando` é obrigatório, e para um arquivo em disco o único
    instante que EXISTE é o `mtime`. Ele não é o instante da geração — é o da
    última escrita. Está registrado assim no `nota` da procedência, porque um
    campo que parece ser uma coisa e é outra é pior que um campo vazio.

    Nenhum relógio é lido: `mtime` é metadado do arquivo, não `now()`.

    ## Arquivo que não vira asset vira `Falha`, e o lote segue

    Mesma regra de `catalogo.assets_da_resposta`: um arquivo ilegível não pode
    derrubar os outros três. E medida ausente NÃO é contornada aqui — ela vira
    `Falha` ou `Asset` sem medida, e `validar_lote` decide.
    """
    from datetime import datetime as _datetime, timezone as _timezone

    raiz = pathlib.Path(raiz)
    if not raiz.is_dir():
        raise PonteIncompleta(f"{raiz} não é uma pasta")

    assets: list[Asset] = []
    falhas: list[Falha] = []
    conteudo: dict[str, bytes] = {}
    avisos: list[str] = []

    # ── nada some em silêncio ──────────────────────────────────────────────
    #
    # ⚠️ A primeira versão só olhava as quatro pastas conhecidas e descartava
    # subpastas com um `is_file()` mudo. Medido pela revisão adversarial: uma
    # pasta com `logos/` (typo) e `marketing/aprovados/` perdia CINCO arquivos,
    # sem aviso, sem falha, e o comando saía com 0. O único sinal na tela
    # apontava para o papel errado.
    #
    # Este módulo escreveu a doutrina contrária algumas linhas acima, para o
    # caso do vídeo: "Silenciar seria perder o arquivo sem dizer".
    # ⚠️ A COMPARAÇÃO É INSENSÍVEL À CAIXA, e não por gentileza. `raiz / papel`
    # resolve `Marketing/` em APFS (macOS) e NÃO resolve em ext4 (Linux). Com a
    # comparação sensível, o aviso dizia "pasta 'Marketing/' ignorada" enquanto
    # a leitura, vinte linhas abaixo, JÁ TINHA LIDO os arquivos dela — o
    # operador via uma perda que não houve e reenviava. Pior: o mesmo diretório
    # aprovado no macOS reprovava no Linux por falta de `marketing`.
    #
    # Casar por caixa insensível aqui alinha o aviso com o que a leitura faz na
    # plataforma em que ela roda, e o aviso de divergência de caixa é emitido
    # explicitamente — porque no Linux aquele arquivo REALMENTE não entra.
    conhecidas = set(_TIPO_POR_PASTA)
    por_caixa = {p.lower(): p for p in conhecidas}
    for entrada in sorted(raiz.iterdir()):
        if entrada.name.startswith("."):
            continue
        canonico = por_caixa.get(entrada.name.lower())
        if entrada.is_dir() and canonico is not None and entrada.name != canonico:
            avisos.append(
                f"pasta '{entrada.name}/' difere do papel '{canonico}' apenas na "
                f"caixa. Em macOS ela É lida; em Linux NÃO seria. Renomeie para "
                f"'{canonico}' antes de mover o lote de máquina")
            continue
        if entrada.is_dir() and canonico is None:
            quantos = sum(1 for _ in entrada.rglob("*") if _.is_file())
            avisos.append(
                f"pasta '{entrada.name}/' ignorada ({quantos} arquivo(s)): "
                f"não é um papel do canal. Papéis: {', '.join(sorted(conhecidas))}")
        elif entrada.is_file():
            avisos.append(
                f"'{entrada.name}' ignorado: arquivo solto na raiz, sem papel "
                f"declarado. Mova para uma das pastas: "
                f"{', '.join(sorted(conhecidas))}")

    achou_alguma_pasta = False
    for papel in sorted(_TIPO_POR_PASTA):
        pasta = raiz / papel
        if not pasta.is_dir():
            continue
        achou_alguma_pasta = True
        tipo = _TIPO_POR_PASTA[papel]
        for sub in sorted(p for p in pasta.iterdir() if p.is_dir()):
            if sub.name.startswith("."):
                continue
            quantos = sum(1 for _ in sub.rglob("*") if _.is_file())
            avisos.append(
                f"subpasta '{papel}/{sub.name}/' ignorada ({quantos} arquivo(s)): "
                f"a leitura não desce um nível — o papel é a pasta de cima")
        for arquivo in sorted(p for p in pasta.iterdir() if p.is_file()):
            if arquivo.name.startswith("."):
                continue
            try:
                dados = arquivo.read_bytes()
            except OSError as exc:
                # ⚠️ O docstring desta função promete que "um arquivo ilegível
                # não pode derrubar os outros três" — e sem este `except` a
                # promessa era falsa: `PermissionError` matava o lote inteiro.
                # O teste que dizia prová-la usava um arquivo VAZIO, que é
                # outro caso.
                falhas.append(Falha(
                    referencia=str(arquivo.relative_to(raiz)),
                    motivo=f"não deu para ler: {exc.__class__.__name__}",
                    codigo="F4.ilegivel", tipo=tipo, permanente=False))
                continue
            if not dados:
                falhas.append(Falha(
                    referencia=str(arquivo.relative_to(raiz)),
                    motivo="arquivo vazio", codigo="F3.arquivo_vazio",
                    tipo=tipo, permanente=True))
                continue
            medida = medir_imagem.medir(dados)
            mtime = _datetime.fromtimestamp(
                arquivo.stat().st_mtime, tz=_timezone.utc)
            try:
                asset = Asset(
                    tipo=tipo,
                    procedencia=Procedencia(
                        motor=motor, versao_do_motor=versao_do_motor,
                        insumo=insumo, quando=mtime,
                        pedido=f"pasta:{raiz.name}",
                        nota="`quando` é o mtime do arquivo, não o instante "
                             "de geração — é o único que a pasta conhece",
                    ),
                    conteudo_hash=hash_de_conteudo(dados),
                    origem=origem,
                    bytes_totais=medida.bytes_totais,
                    mime=medida.mime,
                    largura=medida.largura,
                    altura=medida.altura,
                    rotulo=arquivo.stem,
                )
            except ValueError as exc:
                falhas.append(Falha(
                    referencia=str(arquivo.relative_to(raiz)),
                    motivo=f"arquivo não virou asset: {exc}",
                    codigo="F1.arquivo_invalido", tipo=tipo, permanente=True))
                continue
            if not medida.dimensionada:
                # Não é falha: é um asset sem medida, e `validar_lote` vai
                # cobrá-lo com `M1.sem_medida`. Dizer aqui poupa o operador de
                # descobrir só no veredito.
                avisos.append(
                    f"{arquivo.name}: não deu para medir "
                    f"({medida.mime or 'formato não reconhecido'})")
            assets.append(asset)
            conteudo[asset.identidade] = dados

    if not achou_alguma_pasta:
        # ⚠️ Os avisos de caixa VAO NA MENSAGEM. Em sistema case-sensitive
        # (Linux), uma raiz que só tem `Marketing/` cai aqui — e sem isto o
        # operador leria "não tem nenhuma subpasta de papel" sem saber que a
        # pasta certa está ali com a caixa errada. O aviso tinha acabado de ser
        # montado e era descartado junto com o retorno.
        de_caixa = [a for a in avisos if "apenas na caixa" in a]
        detalhe = ("\n  " + "\n  ".join(de_caixa)) if de_caixa else ""
        raise PonteIncompleta(
            f"{raiz} não tem nenhuma subpasta de papel. Esperadas: "
            f"{', '.join(sorted(_TIPO_POR_PASTA))}{detalhe}")

    return (
        LoteDeAssets(canal=canal, assets=tuple(assets), falhas=tuple(falhas),
                     intencao=raiz.name),
        conteudo,
        tuple(avisos),
    )


def main(argv: list[str] | None = None) -> int:
    """Monta um `ImagensDisplay` validado a partir de uma pasta. Não escreve nada.

        python -m volc_ads.criativo_ponte --pasta ./criativos \\
            --motor "humano:tarcisio" --insumo "banners do FGTS de setembro"

    Devolve 0 quando o lote serve, 1 quando não serve. Nenhuma conta é tocada:
    este módulo não importa `gads` e não tem como falar com o Google.
    """
    import argparse
    import json  # noqa: F401 — usado no envelope, inclusive no caminho de falha

    p = argparse.ArgumentParser(
        prog="volc_ads.criativo_ponte",
        description="Valida uma pasta de criativos contra a régua do canal e "
                    "monta o ImagensDisplay com procedência. Offline.")
    p.add_argument("--pasta", required=True,
                   help="raiz com subpastas por papel: "
                        + ", ".join(sorted(_TIPO_POR_PASTA)))
    p.add_argument("--motor", required=True,
                   help="quem produziu os arquivos: 'humano:tarcisio', "
                        "'openai:gpt-image-2', 'veo-3.1'…")
    p.add_argument("--insumo", required=True,
                   help="o prompt ou briefing que originou os arquivos")
    p.add_argument("--versao", default="", help="versão do motor, quando houver")
    p.add_argument("--origem", default=Origem.HUMANO.value,
                   choices=[o.value for o in Origem])
    p.add_argument("--json", dest="saida_json", default="",
                   help="grava a linhagem em JSON neste caminho")

    a = p.parse_args(argv)

    # ⚠️ O ARQUIVO DE SAÍDA É INVALIDADO ANTES DE QUALQUER TRABALHO.
    #
    # `lote_de_pasta` levanta antes de o envelope ser escrito. Com `--json`
    # apontando para um caminho que já existe, o leitor que consome o ARQUIVO
    # em vez do código de saída — o leitor cujo nome o comentário do envelope
    # invoca — lia `ok: true` de uma rodada que nunca aconteceu, com a linhagem
    # de OUTRO lote. Um relatório obsoleto é pior que relatório nenhum.
    if a.saida_json:
        pathlib.Path(a.saida_json).write_text(
            json.dumps({"ok": False, "estado": "em execução",
                        "nota": "esta rodada não terminou; se este texto "
                                "sobreviveu, o comando falhou antes do "
                                "veredito"},
                       ensure_ascii=False, indent=2),
            encoding="utf-8")

    try:
        lote, conteudo, avisos = lote_de_pasta(
            pathlib.Path(a.pasta), motor=a.motor, insumo=a.insumo,
            versao_do_motor=a.versao, origem=Origem(a.origem))
    except PonteIncompleta as exc:
        print(f"⊘  {exc}")
        if a.saida_json:
            pathlib.Path(a.saida_json).write_text(
                json.dumps({"ok": False, "estado": "leitura falhou",
                            "erro": str(exc)}, ensure_ascii=False, indent=2),
                encoding="utf-8")
            print(f"relatório gravado em {a.saida_json} — SEM payload "
                  f"(a pasta não pôde ser lida)")
        return 1

    for aviso in avisos:
        print(f"⚠️  {aviso}")
    for falha in lote.falhas:
        print(f"⊘  {falha}")

    entrega = imagens_de_display(lote, conteudo)
    print(entrega.resumo())

    if a.saida_json:
        # ⚠️ Um `[]` num lote reprovado é indistinguível de "zero imagens" para
        # quem lê o arquivo em vez do código de saída — ausência tratada como
        # zero, no consumidor escrito pelo commit que argumenta contra isso.
        # O envelope diz o que aconteceu.
        # ⚠️ `avisos` e `falhas` VÃO JUNTO. Sem eles o artefato dizia "lote
        # perfeito" enquanto o stdout mostrava três arquivos perdidos por typo
        # de pasta e um ilegível — e o argumento do próprio envelope é que
        # existe um leitor que consome o ARQUIVO, não o código de saída. As
        # duas correções do mesmo commit não se falavam.
        envelope = {
            "ok": entrega.ok,
            "canal": entrega.veredito.canal,
            "exigencia_fonte": entrega.veredito.fonte or None,
            "linhagem": [ln.para_json() for ln in entrega.linhagem],
            "recusas": list(entrega.recusas),
            "violacoes": [str(v) for v in entrega.veredito.violacoes],
            "avisos_de_leitura": list(avisos),
            "falhas_de_leitura": [str(f) for f in lote.falhas],
        }
        pathlib.Path(a.saida_json).write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
        estado = "com payload" if entrega.ok else "SEM payload (lote reprovado)"
        print(f"relatório gravado em {a.saida_json} — {estado}")

    if not entrega.ok:
        print("\n→ o lote NÃO serve para montar a campanha. "
              "Nada foi enviado a lugar nenhum.")
        return 1

    print(f"\n→ {len(entrega.linhagem)} imagens prontas para "
          f"`brief.imagens_display`. Nada foi enviado: a trava de escrita "
          f"continua fechada e este módulo não fala com o Google.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
