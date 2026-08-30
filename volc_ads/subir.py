"""Caminho de ESCRITA — cria a campanha de verdade, pausada, e registra o que nasceu.

## Por que existe

`copy/provar.py` termina no veredito do `validate_only`: o payload é aceitável.
Isso é preflight, não revisão. O veredito de política que decide se o anúncio
serve só existe sobre recurso PERSISTIDO (`ad_group_ad.policy_summary`), e para
haver recurso persistido alguém precisa escrever.

Este módulo é o `provar.py` com uma troca: sai `validar_mutacoes`, entra
`mutar()` dentro de um `destravar()`. Todo o resto do arquivo existe por causa
dessa troca — as duas travas de segurança antes, e o recibo depois.

## Por que nascer PAUSED não é meia-medida

`campanha/comum.py` já cria a campanha `PAUSED`, e isso não é cautela: é o que
torna o lançamento BARATO. Campanha pausada não entra em leilão e não gasta —
e mesmo assim o Google revisa os anúncios dela como revisaria os de qualquer
outra. Ou seja: o quarto juiz custa zero e devolve a única coisa que o
`validate_only` não sabe dizer, que é o veredito sobre o texto real, na conta
real, com a landing page real do outro lado. Despausar continua sendo uma
decisão separada, tomada depois de ler esse veredito.

## Por que os resource names são gravados no ato

O mutate atômico devolve `mutate_operation_responses`, e é a ÚNICA vez que os
resource names aparecem. Perdidos ali, uma campanha recém-criada só é
localizável por busca textual pelo nome — e o nome carrega um carimbo de
segundo (`comum.carimbo()`), o que faz da busca um exercício de adivinhação.
Com os resource names guardados, a consulta ao `policy_summary` é direta.

## O que ele NÃO faz

Não despausa. Não pede isenção de política — isso é `isencao.py`, e a decisão é
humana. Não consulta `policy_summary`: a revisão do Google leva tempo e essa
leitura é de outro momento. O que este módulo garante é que ela seja POSSÍVEL.

Uso:
    backend/.venv/bin/python -m volc_ads.subir --dry
    backend/.venv/bin/python -m volc_ads.subir --subir --conta 8017851692 \
        --mcc 6016739364 --motivo "canário do FGTS na Crédito Up"
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from . import isencao, politica_auto
from .campanha import perfil, search
from .campanha.brief import Brief, Linhagem
from .campanha.criterio import chave as _chave_criterio
from .criativo.adaptadores import medir_imagem
from .gads import modo
from .gads.client import (
    ErroEsgotado,
    cliente,
    ErroTerminal,
    PoliticaRetry,
    mutar,
    validar_mutacoes,
)
from .gads.errors import FalhaGads

# Onde os recibos ficam. Arquivo, e não banco, de propósito: o recibo tem de
# sobreviver a um processo que morreu no meio da chamada, e nesse instante o
# que existe de mais confiável é um `write()` já retornado.
PASTA_RECIBOS = Path(__file__).resolve().parent / "dados" / "recibos"

# Estados possíveis de um recibo. São quatro porque a pergunta do operador não
# é "deu erro?", é "o que sobrou na conta?".
TENTANDO = "TENTANDO"            # a requisição saiu e ainda não voltou
ACEITO = "ACEITO"                # respondeu criando; os resource names estão aqui
RECUSADO = "RECUSADO"            # respondeu recusando; atômico ⇒ nada foi criado
INDETERMINADO = "INDETERMINADO"  # não respondeu; pode ter criado. Vá conferir.

# ⚠️ UMA tentativa, e isso é decisão, não descuido. `client.executar()` retenta
# TRANSIENT com backoff, o que é certo para leitura e PERIGOSO aqui: um
# DEADLINE_EXCEEDED pode chegar depois de o servidor ter aplicado o mutate, e a
# segunda tentativa criaria a campanha inteira de novo. A API não oferece chave
# de idempotência em `mutate` (procurado em google_ads_api/: "idempot" tem zero
# ocorrências), então a única proteção é não repetir. Custo: uma falha de infra
# vira INDETERMINADO em vez de ser reabsorvida. É o lado barato de errar.
SEM_RETENTATIVA = PoliticaRetry(tentativas=1)


class TravaAberta(RuntimeError):
    """A trava de escrita já estava aberta quando `subir()` foi chamado."""


class PayloadNaoValidado(RuntimeError):
    """O grafo não passou por `validate_only`, ou mudou depois de passar."""


class CanalSemMutacaoReal(RuntimeError):
    """O canal pode ser provado, mas esta onda proíbe criação remota."""


#: A recusa de canal sem construtor. Definida em `campanha/perfil.py`, que é
#: quem conhece os canais, e reexportada aqui porque `subir.CanalSemConstrutor`
#: é o nome público que a porta do Hub e os testes já usam. Continua sendo
#: `ValueError`, então o router segue traduzindo para 422.
CanalSemConstrutor = perfil.CanalSemConstrutor

# Registro explícito de escrita. Reconhecer um canal no inventário não autoriza
# montá-lo: cada entrada daqui precisa ser um construtor completo, testado e
# capaz de provar exatamente o payload que depois será enviado.
#
# ⚠️ Isto é uma VISTA, não uma segunda declaração. Os construtores vêm de
# `campanha/perfil.py` — o dicionário existe literal aqui porque é este arquivo
# que `backend/tests/test_trafego_plataforma.py` lê por árvore sintática para
# comparar o engine com o manifesto do Hub, sem importar o SDK do Google. A
# guarda logo abaixo derruba o import se as duas listas divergirem, então
# esquecer um canal aqui é um erro que aparece na hora, não na tela.
CONSTRUTORES_POR_CANAL = {
    "SEARCH": perfil.SEARCH.construtor,
    "DISPLAY": perfil.DISPLAY.construtor,
}

# Vista separada da porta de prova. Demand Gen aparece aqui porque possui
# builder + validate_only, e não aparece acima porque não pode alcançar mutar.
PROVADORES_POR_CANAL = {
    "SEARCH": perfil.SEARCH.validador,
    "DISPLAY": perfil.DISPLAY.validador,
    "DEMAND_GEN": perfil.DEMAND_GEN.validador,
}

_esperado = set(perfil.canais_que_criam())
if set(CONSTRUTORES_POR_CANAL) != _esperado:
    raise RuntimeError(
        f"CONSTRUTORES_POR_CANAL lista {sorted(CONSTRUTORES_POR_CANAL)} e "
        f"campanha/perfil.py declara {sorted(_esperado)} sabendo criar. A vista "
        f"em subir.py precisa acompanhar o perfil — é ela que o Hub lê para "
        f"saber o que oferecer na tela."
    )

_provadores_esperados = set(perfil.canais_que_provam())
if set(PROVADORES_POR_CANAL) != _provadores_esperados:
    raise RuntimeError(
        f"PROVADORES_POR_CANAL lista {sorted(PROVADORES_POR_CANAL)} e o perfil "
        f"declara {sorted(_provadores_esperados)}. Prova e mutação são portas "
        "diferentes e ambas precisam acompanhar o perfil."
    )

APELIDOS_DE_CANAL = perfil.APELIDOS


def resolver_construtor(canal: str) -> tuple[str, Any]:
    """Devolve canal canônico + builder ou recusa antes de tocar no Google."""
    p = perfil.exigir(canal)
    return p.canal, p.construtor


def resolver_provador(canal: str) -> tuple[str, Any]:
    """Devolve canal + validador para montagem/validate_only, sem autorizar mutate."""
    p = perfil.exigir_prova(canal)
    return p.canal, p.validador


# ── o que a prova produz, e o que a escrita exige ──────────────────────────


@dataclass(frozen=True)
class Selo:
    """Prova de que ESTE grafo, nesta conta, passou por `validate_only`.

    Um booleano `validado=True` não serviria: ele sobrevive à edição do payload
    logo depois. O selo carrega a impressão digital das operações, então mexer
    numa headline entre a prova e a escrita invalida o selo em vez de passar
    despercebido — que é exatamente o furo pelo qual um texto não provado
    chegaria à conta.
    """

    customer_id: str
    login_customer_id: str
    canal: str
    #: Um item por MutateOperation, incluindo o verbo do oneof
    #: (``campaign_operation.create``). O tipo não fica implícito no hash.
    tipos_operacoes: tuple[str, ...]
    #: sha256 individual de cada operação serializada deterministicamente.
    hashes_operacoes: tuple[str, ...]
    impressao: str
    n_operacoes: int
    carimbo: str


@dataclass(frozen=True)
class AutoridadeDasOperacoes:
    """Fatos derivados do payload, nunca do rótulo mutável de ``Preparo``."""

    canal: str
    tipos: tuple[str, ...]
    hashes: tuple[str, ...]
    impressao: str


@dataclass(frozen=True)
class Preparo:
    """O grafo montado e o veredito da prova. Sem selo, não sobe."""

    customer_id: str
    login_customer_id: str
    operacoes: tuple[Any, ...]
    nome_campanha: str
    canal: str = "SEARCH"
    selo: Selo | None = None
    recusa_local: str = ""
    falha_validacao: FalhaGads | None = None
    #: O que a autocorreção de política fez — uma linha por decisão. Vazio
    #: quando não houve recusa de política ou quando ela não era acionável.
    #: É o que a tela mostra para o operador saber o que saiu e o que foi
    #: isentado SEM ter de comparar dois payloads.
    autocorrecao: tuple[str, ...] = ()
    #: Os AVISOS da validação local — os achados que não barram.
    #:
    #: ⚠️ Vai SEMPRE, inclusive quando a prova PASSA, pela mesma razão que
    #: `autocorrecao` vai: é justamente no sucesso que a mudança silenciosa
    #: engana. Até aqui o `Resultado` só sobrevivia pelo `recusa_local`, que só
    #: é preenchido quando `r.ok` é falso — então "keyword duplicada entre ad
    #: groups, mantida só na primeira", "negativa duplicada removida" e
    #: "negativa anula esta keyword" desapareciam exatamente no caminho feliz,
    #: que é o caminho em que o operador aprova e gasta.
    #:
    #: Fica FORA do `Selo`, como a linhagem: o selo é a impressão digital do
    #: PAYLOAD, e um aviso não é payload. Acrescentá-lo não invalida prova feita.
    avisos_locais: tuple[str, ...] = ()
    #: De onde veio cada imagem que este payload manda criar, na ordem em que
    #: as `asset_operation` aparecem no mutate. Vazio para canais sem imagem
    #: nova — Search inclusive, e sem nenhum `if canal ==` para isso.
    #:
    #: Fica FORA do `Selo` de propósito: o selo é a impressão digital do
    #: PAYLOAD, e a linhagem não é payload. Um campo a mais aqui não invalida
    #: uma prova já feita.
    linhagem: tuple[Linhagem, ...] = ()

    @property
    def provado(self) -> bool:
        return self.selo is not None

    def porque_nao(self) -> str:
        if self.provado:
            return ""
        if self.recusa_local:
            return f"validação local do forge: {self.recusa_local}"
        if self.falha_validacao is not None:
            return f"validate_only recusou: {self.falha_validacao.resumo()}"
        return "sem selo e sem motivo registrado"


@dataclass(frozen=True)
class Criado:
    """Um recurso que a API confirmou ter criado."""

    posicao: int      # posição na LISTA DE RESPOSTA, não índice da operação
    tipo: str         # ex.: "campaign_result"
    resource_name: str


@dataclass(frozen=True)
class Recibo:
    """O relatório de uma tentativa de escrita — gravado antes e depois.

    Gravado duas vezes de propósito. A primeira, `TENTANDO`, sai antes de a
    requisição partir; se o processo morrer no meio da chamada, é ela que conta
    ao operador que alguma coisa saiu daqui e nunca foi confirmada. A segunda
    sobrescreve a primeira com o veredito. Recibo parado em `TENTANDO` = vá
    conferir a conta.
    """

    estado: str
    carimbo: str
    customer_id: str
    login_customer_id: str
    nome_campanha: str
    n_operacoes: int
    impressao: str
    motivo: str
    criados: tuple[Criado, ...] = ()
    request_id: str = ""
    falha: FalhaGads | None = None
    explicacao: str = ""
    #: A procedência das imagens que ESTA tentativa mandou criar.
    #:
    #: Ela é gravada já no pré-recibo (`TENTANDO`), antes de a requisição
    #: partir, e é aí que ela vale mais: se a chamada morrer sem veredito, o
    #: arquivo em disco ainda sabe quais bytes, com qual hash e de qual insumo
    #: saíram daqui. Sem isso, conferir a conta depois de um INDETERMINADO
    #: seria comparar imagens a olho.
    linhagem: tuple[Linhagem, ...] = ()

    @property
    def nada_foi_criado(self) -> bool | None:
        """Três respostas, e a terceira é `None` de propósito.

        O mutate é atômico: ou entrou tudo ou não entrou nada. Mas isso só vale
        quando a API RESPONDEU. Devolver `True` num INDETERMINADO seria mentir
        com cara de garantia; `None` obriga quem lê a tratar o terceiro caso.
        """
        if self.estado == ACEITO:
            return False
        if self.estado == RECUSADO:
            return True
        return None

    def recurso(self, tipo: str) -> str:
        """O primeiro resource_name de um tipo — `campaign_result`, etc."""
        for c in self.criados:
            if c.tipo == tipo:
                return c.resource_name
        return ""

    @property
    def arquivo(self) -> str:
        """Nome do arquivo do recibo. Determinístico: a 2ª gravação sobrescreve."""
        return f"{self.carimbo}_{self.customer_id}_{self.impressao[:8]}.json"

    def para_json(self) -> dict:
        d = dataclasses.asdict(self)
        d["nada_foi_criado"] = self.nada_foi_criado
        # ⚠️ `asdict` recursa nas `Linhagem` e produz dicts SEM `confirmada`,
        # porque `confirmada` é property e `asdict` só enxerga campos. Sem esta
        # linha, o recibo gravaria toda a procedência e omitiria justamente o
        # veredito sobre ela — e quem lesse o arquivo teria de recalcular a
        # regra por conta própria, que é como duas regras nascem.
        d["linhagem"] = [ln.para_json() for ln in self.linhagem]
        return d

    def resumo(self) -> str:
        linhas = [
            f"{self.estado}  {self.nome_campanha or '(campanha sem nome no payload)'}",
            (f"  conta {self.customer_id} sob MCC {self.login_customer_id}"
             f" · {self.n_operacoes} operações · impressão {self.impressao[:12]}"),
            f"  motivo declarado: {self.motivo}",
        ]
        if self.explicacao:
            linhas.append(f"  estado da conta: {self.explicacao}")
        for c in self.criados:
            linhas.append(f"  criado  {c.tipo:28} {c.resource_name}")
        if self.falha is not None:
            linhas.append("  falha:")
            linhas.extend(f"    {ln}" for ln in self.falha.detalhe().splitlines())
        return "\n".join(linhas)


# ── preparo: montar e provar, sem escrever nada ────────────────────────────


def _com_isencoes(operacoes: tuple[Any, ...], chaves: tuple[Any, ...],
                  *, login_customer_id: str) -> tuple[Any, ...]:
    """Escreve as chaves de isenção nas operações que carregam o texto violado.

    ⚠️ A isenção vai na OPERAÇÃO CERTA, e descobrir qual é o trabalho todo. O
    `violating_text` da chave é a keyword em si, então basta achar a operação
    de critério cujo texto casa — e é assim que a isenção sobrevive a uma
    remontagem: os índices mudam quando uma keyword sai, o texto não.
    """
    if not chaves:
        return operacoes
    # ⚠️ O cliente é NECESSÁRIO: `isencao.aplicar` monta o proto
    # `PolicyViolationKey` com `c.get_type(...)`, e sem ele não há como
    # construir a chave. Passar `None` estoura com `AttributeError` — que foi
    # exatamente o que aconteceu na primeira tentativa.
    # ⚠️ `gads` e não `c`: a primeira versão chamava o cliente de `c` e logo
    # abaixo usava `c` como variável do laço sobre as chaves. O laço
    # sobrescrevia o cliente, e `aplicar` recebia uma `ChavePolitica` no lugar
    # dele — `AttributeError: 'ChavePolitica' object has no attribute
    # 'get_type'`. Sombra de nome em Python não avisa.
    gads = cliente(login_customer_id)
    por_texto: dict[str, list[Any]] = {}
    for chave in chaves:
        por_texto.setdefault((chave.violating_text or "").strip().lower(), []).append(chave)

    for i, op in enumerate(operacoes):
        sub = getattr(op, "ad_group_criterion_operation", None)
        texto = ""
        try:
            texto = (sub.create.keyword.text or "").strip().lower() if sub else ""
        except Exception:  # noqa: BLE001 — operação de outro tipo; segue
            texto = ""
        alvo = por_texto.get(texto)
        if not alvo:
            continue
        pedido = isencao.Pedido(
            alvo=isencao.ALVO_CRITERIO, formato="violacao",
            indice_operacao=i, chaves=tuple(alvo),
        )
        isencao.aplicar(gads, op, pedido)
    return operacoes


#: Papel declarado quando o payload cria uma imagem que o brief não explica.
#: Não é rótulo de exibição: é o sinal de que a correspondência entre brief e
#: payload se quebrou, e de que aquela posição não tem procedência apurada.
PAPEL_NAO_APURADO = "?"


def _imagens_criadas(operacoes) -> list[tuple[str, bytes]]:
    """(nome, bytes) de cada imagem que ESTE payload cria, na ordem do mutate.

    Os BYTES vêm junto, e é isso que permite conferir a procedencia contra o
    que de fato vai sair — ver `_linhagem_do_payload`.

    Discrimina por `image_asset.data`: um `asset_operation` de sitelink ou
    callout (Search) não tem bytes de imagem, e contá-lo aqui atribuiria
    procedência de imagem a um asset de texto.
    """
    saida: list[tuple[str, bytes]] = []
    for op in operacoes:
        if _qual_oneof(op, "operation") != "asset_operation":
            continue
        try:
            cria = op.asset_operation.create
            dados = cria.image_asset.data
        except AttributeError:
            continue
        if dados:
            saida.append((str(cria.name or ""), bytes(dados)))
    return saida


def _linhagem_do_brief(brief: Brief) -> tuple[Linhagem, ...]:
    """A procedência das imagens novas que este brief DECLARA.

    Canal-agnóstico DE PROPÓSITO. Um brief sem `imagens_display` devolve vazio,
    e por isso `preparar()` não ganha um segundo `if canal ==` — o único que
    existe hoje é `p.autocorrige_keywords`, e ele é do perfil, que existe
    justamente para comer esses ifs.
    """
    saida: list[Linhagem] = []
    for campo in ("imagens_display", "imagens_demand_gen"):
        imagens = getattr(brief, campo, None)
        if imagens is not None:
            saida.extend(imagens.linhagens())
    return tuple(saida)


#: `image/jpg` nao existe no registro da IANA, mas e escrito o tempo todo.
#: Normalizar aqui e o oposto de aceitar: e impedir que a escolha da GRAFIA
#: decida se a conferencia acontece.
_MIME_CANONICO = {"image/jpg": "image/jpeg", "image/pjpeg": "image/jpeg"}


def _mime_normalizado(mime: str | None) -> str | None:
    """Reduz a grafia ao tipo, para a ESCRITA nao decidir se ha conferencia.

    ⚠️ Parametro RFC (`image/png; charset=binary`) e string vazia sao tratados
    aqui e nao mais adiante. Sem isto, os dois derrubavam a linhagem INTEIRA de
    um arquivo legitimo — falso positivo, que neste ponto e pior que falso
    negativo: rebaixar procedencia verdadeira ensina a desconfiar do portao.
    Nao e alcancavel pelos produtores de hoje (`medir_imagem`), mas seria no dia
    em que alguem plugasse `python-magic` ou copiasse um `Content-Type`.
    """
    if mime is None:
        return None
    limpo = mime.split(";")[0].strip().lower()
    if not limpo:
        return None            # declarado vazio e ausencia, nao contradicao
    return _MIME_CANONICO.get(limpo, limpo)


def _medidas_batem(candidata: Linhagem, dados: bytes) -> bool:
    """A linhagem descreve o FORMATO e o TAMANHO destes bytes?

    `Linhagem.confere` prova que os bytes sao os que o hash aponta — e so isso.
    `mime`, `largura` e `altura` sao afirmacoes INDEPENDENTES sobre o mesmo
    arquivo, e o docstring de `Linhagem.confirmada` promete saber "o que
    exatamente e o arquivo".

    ## A invariante, e as duas versoes erradas que vieram antes dela

    A regra e: **`confirmada` significa CORROBORADO.** O que nao se consegue
    corroborar nao e confirmado — nem por benevolencia, nem por ausencia.

    A primeira versao nao conferia medida nenhuma: bastava computar o sha256
    certo de 42 bytes de texto e declarar `image/png 1200x628`.

    A segunda so refutava quando o mime declarado estava entre os tres
    reconhecidos — e **quem declara escolhe a string**. Medido em 27/08/2026,
    sobre os MESMOS 42 bytes de texto:

        mime="image/png"   -> refutado  (o unico caso que a v2 fechava)
        mime="image/webp"  -> PASSAVA
        mime="IMAGE/PNG"   -> PASSAVA   (so a caixa mudou)
        mime="image/jpg"   -> PASSAVA   (so a grafia mudou)

    Agora ha dois ramos, e o segundo e o que fecha a familia inteira:

      ASSINATURA RECONHECIDA  o mime declarado tem de bater com o medido, e a
                              dimensao declarada tem de bater com a medida. Se
                              a dimensao foi declarada e NAO foi possivel
                              medi-la, tambem nao ha corroboracao — e o caso
                              real disso e o PNG de assinatura valida com IHDR
                              zerado, que declara 1200x628.

      ASSINATURA DESCONHECIDA nao da para corroborar NADA. Uma linhagem que
                              afirma formato ou dimensao sobre bytes que nao
                              sabemos ler esta afirmando o que ninguem apurou.

    ⚠️ O segundo ramo NAO reprova o payload — so nega a confirmacao. E ele nao
    prejudica formato legitimo novo: a API v25 aceita apenas PNG, JPEG e GIF
    (`criativo/requisitos.yaml: padroes.imagem.mimes`), e um WebP ja seria
    barrado por `F1.mime` na validacao, antes de chegar aqui.
    """
    medida = medir_imagem.medir(dados)
    declarado = _mime_normalizado(candidata.mime)

    # O tamanho vem PRIMEIRO porque e o unico que sempre da para conferir: ele
    # nao depende de reconhecer formato nenhum. Deixa-lo depois do desvio abaixo
    # fazia uma mentira de tamanho passar sempre que a assinatura fosse
    # desconhecida — achado do proprio teste desta guarda.
    if candidata.bytes_totais is not None and candidata.bytes_totais != len(dados):
        return False

    if medida.mime is None:
        # Nao reconhecemos a assinatura. Qualquer afirmacao sobre formato ou
        # dimensao e incorroboravel — e incorroboravel nao e confirmado.
        return not (declarado is not None
                    or candidata.largura is not None
                    or candidata.altura is not None)

    if declarado is not None and declarado != medida.mime:
        return False

    for declarada, medido in ((candidata.largura, medida.largura),
                              (candidata.altura, medida.altura)):
        if declarada is None:
            continue
        if medido is None or declarada != medido:
            # `medido is None` com formato reconhecido = cabecalho nao trouxe
            # dimensao utilizavel. Declarar uma assim mesmo e inventar.
            return False

    return True


def _linhagem_do_payload(brief: Brief, operacoes) -> tuple[Linhagem, ...]:
    """A procedência das imagens que o PAYLOAD realmente cria.

    ## Por que não basta ler o brief

    Porque o brief declara intenção e o payload declara o que vai acontecer, e
    eles podem divergir. O caso concreto, reproduzido antes de existir esta
    função: um brief de SEARCH com `imagens_display` preenchido devolve
    linhagem, e `search.construir` ignora esse campo por completo — o payload
    cria ZERO assets de imagem. O recibo gravaria a procedência de uma imagem
    que nunca foi criada.

    Um rastro que não corresponde ao que saiu é pior que rastro nenhum: ele
    parece um rastro, e ninguém vai conferir.

    `campos_operados` do perfil já diz que `imagens_display` não é de Search,
    mas é declaração, não guarda — nada o aplica. Esta função aplica.

    ## A doutrina que ela segue

    A mesma de `_nome_campanha`: **leia do payload, não re-derive**. O payload é
    a autoridade sobre QUAIS imagens nascem; o brief é a autoridade sobre a
    procedência delas. A lista devolvida tem sempre exatamente o comprimento do
    que o mutate cria — nunca mais, nunca menos.

    Quando a posição não casa pelo nome, aquela imagem entra como
    `desconhecida`: preferir o silêncio encurtaria a lista e deslocaria a
    procedência das seguintes.
    """
    criadas = _imagens_criadas(operacoes)
    if not criadas:
        # Nenhuma imagem nasce aqui. Search cai neste ramo sem uma linha
        # dedicada a ele, e um brief de Search com `imagens_display` preenchido
        # deixa de contaminar o recibo.
        return ()

    declaradas = _linhagem_do_brief(brief)
    saida: list[Linhagem] = []
    for i, (nome, dados) in enumerate(criadas):
        candidata = declaradas[i] if i < len(declaradas) else None
        if candidata is None:
            saida.append(Linhagem.desconhecida(nome or f"asset[{i}]",
                                               PAPEL_NAO_APURADO))
        elif candidata.confere(dados) and _medidas_batem(candidata, dados):
            # ⚠️ CONFERIDA CONTRA OS BYTES QUE VÃO SAIR, e não contra o nome.
            #
            # A primeira versão reconciliava por `candidata.nome == nome`. Isso
            # aceitava uma linhagem inteiramente fabricada: uma
            # `ImagemParaSubir` montada à mão, com 42 bytes de texto e uma
            # `Linhagem` declarando `sha256:dddd…`, motor e dimensão, chegava ao
            # recibo com `confirmada: true` e sem um único aviso. Medido em
            # 27/08/2026.
            #
            # A ponte já reconfere o hash, mas essa conferência é propriedade
            # DELA — e quem não passa por ela não era conferido por ninguém.
            # Aqui os bytes e o hash declarado estão os dois no mesmo escopo, e
            # é o último ponto antes de o payload virar requisição.
            saida.append(candidata)
        elif not candidata.conteudo_hash and candidata.nome == nome:
            # ⚠️ Linhagem que NÃO AFIRMA hash. A primeira versão preservava o
            # registro inteiro aqui — e isso invertia o incentivo, como a
            # revisão adversarial mostrou: quem DECLARA um hash falso perde
            # tudo, e quem OMITE o campo levava motor, insumo, `insumo_hash`,
            # dimensão inventada e `custo_usd: 99.0` para dentro do recibo.
            #
            # Sem hash não há como atribuir estes bytes a esta procedência.
            # Sobrevive só o que é verificável fora dela: o `nome`, que é o
            # que a conta vai mostrar, e o `papel`, que veio da estrutura do
            # brief e não de uma afirmação sobre o arquivo.
            saida.append(Linhagem.desconhecida(nome, candidata.papel))
        else:
            # Afirmou um hash e os bytes são outros. A procedência não descreve
            # este arquivo, então ela não acompanha este arquivo: o que se sabe
            # é o nome, e mais nada.
            saida.append(Linhagem.desconhecida(nome or f"asset[{i}]",
                                               PAPEL_NAO_APURADO))
    return tuple(saida)


def preparar(
    customer_id: str,
    brief: Brief,
    *,
    login_customer_id: str,
    canal: str = "SEARCH",
    ai_max: bool = False,
    autocorrigir: bool = True,
) -> Preparo:
    """Monta o grafo, valida local e roda `validate_only`. NADA é criado.

    É o mesmo caminho do `copy/provar.py`, com um acréscimo: quando tudo passa,
    emite o `Selo`. Sem esse selo `subir()` recusa — a prova deixa de ser uma
    etapa que alguém lembra de rodar e passa a ser pré-requisito estrutural.
    """
    p = perfil.exigir_prova(canal)
    canal_resolvido = p.canal

    try:
        # ⚠️ `montar()` e não `construir()` direto: quem decide se `ai_max`
        # chega ao construtor é o PERFIL do canal, não um `if` aqui. Search tem
        # a opção; Display não a tem e RECUSA em vez de ignorar — marcar uma
        # caixa que não faz nada é pior que não poder marcá-la.
        ops, r = perfil.montar(
            canal_resolvido, customer_id, brief,
            login_customer_id=login_customer_id, ai_max=ai_max,
        )
    except Exception as exc:  # noqa: BLE001 — construir() levanta ValueError de marcação
        return Preparo(
            customer_id=str(customer_id),
            login_customer_id=str(login_customer_id),
            operacoes=(),
            nome_campanha="",
            canal=canal_resolvido,
            recusa_local=f"construir() falhou: {exc}",
            # Sem `linhagem`: `construir()` levantou, nenhum payload existe, e
            # nenhuma imagem seria criada. Declarar procedência aqui
            # descreveria assets que não chegaram nem a ser montados.
        )

    operacoes = tuple(ops)
    nome = _nome_campanha(operacoes)

    # Os avisos viajam nos QUATRO desfechos abaixo, e não só na recusa. Ver o
    # campo `Preparo.avisos_locais` para a razão — é a mesma de `autocorrecao`.
    avisos_locais = tuple(
        f"{a.campo}: {a.motivo}" for a in r.achados if a.severidade == "aviso"
    )

    if not r.ok:
        return Preparo(
            customer_id=str(customer_id),
            login_customer_id=str(login_customer_id),
            operacoes=operacoes,
            nome_campanha=nome,
            canal=canal_resolvido,
            recusa_local=r.resumo(),
            avisos_locais=avisos_locais,
            linhagem=_linhagem_do_payload(brief, operacoes),
        )

    try:
        autoridade = _autoridade_das_operacoes(
            operacoes, canal_esperado=canal_resolvido
        )
    except ValueError as exc:
        # O builder declarou um canal, mas são as operações que vão ao Google.
        # Divergência para aqui, antes de validate_only e antes de qualquer
        # cliente de mutação, sem emitir selo parcial.
        return Preparo(
            customer_id=str(customer_id),
            login_customer_id=str(login_customer_id),
            operacoes=operacoes,
            nome_campanha=nome,
            canal=canal_resolvido,
            recusa_local=f"autoridade das operações: {exc}",
            avisos_locais=avisos_locais,
            linhagem=_linhagem_do_payload(brief, operacoes),
        )

    falha = validar_mutacoes(
        customer_id, list(operacoes), login_customer_id=login_customer_id
    )

    # ── AUTOCORREÇÃO DE POLÍTICA — UMA passada, e só de política ──────────
    #
    # Medido no card 65 em 19/08/2026: duas keywords derrubaram um mutate de
    # 114 operações. Os 15 títulos, as 4 descrições, os sitelinks e os callouts
    # tinham passado. O operador via "A policy was violated" duas vezes e não
    # tinha caminho de volta pela tela — só apagar keyword na mão e provar de
    # novo, sem saber qual.
    #
    # `politica_auto.decidir` separa o que é ruído de classificador (pede
    # isenção) do que é a política nomeando a categoria do texto (remove). O
    # padrão é REMOVER: pedir isenção do que se é troca "barrado agora" por
    # "reprovado depois de veicular", que é a mesma doutrina do portão.
    #
    # ⚠️ UMA passada, nunca um laço. Se a segunda validação também reprovar por
    # política, o Preparo volta com essa falha e a decisão fica no diário. Um
    # laço aqui gastaria quota contra uma parede e esconderia o padrão de quem
    # precisa lê-lo.
    #
    # ⚠️ `p.autocorrige_keywords` é o segundo `if canal ==` que o perfil come.
    # A poda mexe em `brief.keywords`, e keyword só vira critério em Search: em
    # Display a remontagem devolveria um payload IDÊNTICO e o diário registraria
    # uma decisão que não teve efeito nenhum — pior que não autocorrigir, porque
    # afirma ter feito algo.
    autocorrecao: tuple[str, ...] = ()
    if (falha is not None and falha.de_politica and autocorrigir
            and p.autocorrige_keywords):
        decisao = politica_auto.decidir(falha)
        if decisao.acionavel:
            ficaram, sairam = politica_auto.podar(list(brief.keywords), decisao.remover)
            # ⚠️ A PODA TEM DE ATRAVESSAR OS DOIS CONTRATOS.
            #
            # `replace()` reexecuta `Brief.__post_init__`, que reresolve os
            # critérios. Podar só `keywords` deixava a positiva podada dentro de
            # `criterios`, e daí dois desfechos, ambos ruins: ou o `Brief`
            # levanta ("positiva que não está na estrutura") e o ValueError
            # escapa de `preparar()` inteiro virando um 500 no meio de uma
            # recusa de política; ou, sem essa guarda, `_grupos` remontava a
            # keyword A PARTIR de `criterios` e o diário afirmava tê-la
            # removido — a "pior forma de sucesso" que o comentário lá embaixo
            # descreve, com outra roupa.
            novo_brief = brief
            if sairam:
                fora = {_chave_criterio(k) for k in sairam}
                sobreviventes = [
                    c for c in brief.criterios
                    if c.negativa or c.chave not in fora
                ]
                novo_brief = replace(
                    brief, keywords=ficaram, criterios=sobreviventes
                )
            try:
                ops2, r2 = perfil.montar(
                    canal_resolvido, customer_id, novo_brief,
                    login_customer_id=login_customer_id, ai_max=ai_max,
                )
            except Exception as exc:  # noqa: BLE001
                ops2, r2 = None, None
                autocorrecao = (*decisao.diario,
                                f"⊘ remontar falhou: {exc}")
            if ops2 is not None and r2 is not None and r2.ok:
                operacoes2 = tuple(ops2)
                if decisao.isentar:
                    operacoes2 = _com_isencoes(
                        operacoes2, decisao.isentar,
                        login_customer_id=str(login_customer_id))
                try:
                    autoridade2 = _autoridade_das_operacoes(
                        operacoes2, canal_esperado=canal_resolvido
                    )
                except ValueError as exc:
                    autocorrecao = (
                        *decisao.diario,
                        f"⊘ operações remontadas divergiram do canal: {exc}",
                    )
                else:
                    falha2 = validar_mutacoes(
                        customer_id, list(operacoes2),
                        login_customer_id=login_customer_id,
                    )
                    veredito = (
                        "passou" if falha2 is None else "reprovou de novo"
                    )
                    autocorrecao = (
                        *decisao.diario,
                        f"→ revalidado: {veredito}",
                    )
                    operacoes, falha, nome = (
                        operacoes2,
                        falha2,
                        _nome_campanha(operacoes2),
                    )
                    autoridade = autoridade2

    if falha is not None:
        return Preparo(
            customer_id=str(customer_id),
            login_customer_id=str(login_customer_id),
            operacoes=operacoes,
            nome_campanha=nome,
            canal=canal_resolvido,
            falha_validacao=falha,
            autocorrecao=autocorrecao,
            avisos_locais=avisos_locais,
            linhagem=_linhagem_do_payload(brief, operacoes),
        )

    # ⚠️ `autocorrecao` VAI TAMBÉM NO SUCESSO — e não ia.
    #
    # Medido na primeira execução real: a autocorreção tirou uma keyword, o
    # payload passou de 114 para 113 operações e o selo saiu. E o diário voltou
    # VAZIO, porque só o retorno de FALHA o carregava. Ou seja: o motor mudou o
    # que vai para a conta e não contou a ninguém.
    #
    # É a pior forma de sucesso — a que não deixa rastro. O operador aprovaria
    # uma campanha sem saber que uma keyword foi removida e outra isentada.
    return Preparo(
        customer_id=str(customer_id),
        login_customer_id=str(login_customer_id),
        operacoes=operacoes,
        nome_campanha=nome,
        canal=canal_resolvido,
        autocorrecao=autocorrecao,
        avisos_locais=avisos_locais,
        linhagem=_linhagem_do_payload(brief, operacoes),
        selo=Selo(
            customer_id=str(customer_id),
            login_customer_id=str(login_customer_id),
            canal=autoridade.canal,
            tipos_operacoes=autoridade.tipos,
            hashes_operacoes=autoridade.hashes,
            impressao=autoridade.impressao,
            n_operacoes=len(operacoes),
            carimbo=_carimbo(),
        ),
    )


# ── escrita ────────────────────────────────────────────────────────────────


def subir(
    preparo: Preparo,
    *,
    motivo: str,
    pasta_recibos: Path | str = PASTA_RECIBOS,
) -> Recibo:
    """Cria a campanha de verdade. Único caminho de escrita deste módulo.

    A ordem das portas é deliberada:

      1. selo, MCC, canal, tipos e hashes — o conteúdo das operações decide;
      2. política de mutação real do canal — Demand Gen para aqui;
      3. motivo descritivo;
      4. trava ambiente.

    Só depois das quatro é que `destravar()` abre, o pré-recibo é gravado e o
    mutate parte. Assim relabeling ou payload divergente não chegam nem a
    consultar a trava, criar recibo ou construir o cliente de mutação.

    Devolve `Recibo`. As quatro portas levantam exceção em vez de devolver recibo:
    elas descrevem o estado de QUEM CHAMOU, não o da conta — e nada saiu da
    máquina, então não há o que relatar. Recibo é para o que já aconteceu lá.
    """
    selo = _exigir_selo(preparo)
    # Selo/operações vêm primeiro: relabeling, troca de MCC, tipo ou hash morrem
    # antes de consultar a trava. Depois, a política de canal usa o canal selado,
    # que já foi reconciliado com campaign_operation.create — nunca o rótulo.
    _recusar_canal_sem_mutacao(selo.canal)
    _exigir_motivo(motivo)
    _recusar_trava_ambiente()

    pasta = Path(pasta_recibos)
    recibo = Recibo(
        estado=TENTANDO,
        carimbo=_carimbo(),
        customer_id=preparo.customer_id,
        login_customer_id=preparo.login_customer_id,
        nome_campanha=preparo.nome_campanha,
        n_operacoes=len(preparo.operacoes),
        impressao=selo.impressao,
        motivo=motivo.strip(),
        explicacao="requisição enviada; veredito ainda não recebido",
        linhagem=preparo.linhagem,
    )

    # ⚠️ NUNCA execute este bloco com a trava aberta durante desenvolvimento.
    # Com `FORGE_PERMITIR_ESCRITA` ausente, `destravar()` levanta
    # `EscritaBloqueada` na ENTRADA do `with` — antes do pré-recibo e antes de
    # qualquer byte sair. É por isso que a gravação mora dentro do bloco.
    with modo.destravar(motivo):
        _gravar(recibo, pasta)
        try:
            resposta = mutar(
                preparo.customer_id,
                list(preparo.operacoes),
                login_customer_id=preparo.login_customer_id,
                politica=SEM_RETENTATIVA,
            )
        except ErroTerminal as exc:
            recibo = _com_falha(recibo, exc.falha, bruta=exc.__cause__)
        except ErroEsgotado as exc:
            # ⚠️ `client.executar()` não encadeia a exceção original em
            # `ErroEsgotado` (`raise ErroEsgotado(...)` sem `from exc`), então
            # aqui não dá para saber se houve `GoogleAdsFailure`. Sem esse
            # sinal o único veredito honesto é INDETERMINADO. Consequência
            # concreta: uma recusa por cota, que não cria nada, manda o
            # operador conferir a conta à toa. O inverso — dizer "nada foi
            # criado" sobre uma resposta que nunca chegou — custa uma campanha
            # duplicada, e por isso o default é este.
            recibo = _com_falha(recibo, exc.falha, bruta=None)
        else:
            recibo = _com_sucesso(recibo, resposta)
        _gravar(recibo, pasta)

    return recibo


def _recusar_canal_sem_mutacao(canal: str) -> None:
    """Demand Gen nunca alcança trava, recibo ou ``mutar`` nesta onda."""
    p = perfil.perfil(canal)
    if p is None or not p.sabe_criar:
        disponiveis = ", ".join(perfil.canais_que_criam())
        raise CanalSemMutacaoReal(
            f"{canal}: o builder pode montar/provar, mas criação real "
            "está proibida nesta onda. /subir aceita somente "
            f"{disponiveis}; nada foi enviado."
        )


def _exigir_motivo(motivo: str) -> None:
    if not motivo or len(motivo.strip()) < 10:
        raise ValueError(
            "subir() exige um motivo descritivo (≥10 caracteres). Ele vai para "
            "o recibo e é a única explicação que sobra quando alguém pergunta, "
            "semanas depois, por que essa campanha existe."
        )


def _recusar_trava_ambiente() -> None:
    """Recusa quando a trava JÁ está aberta ao entrar em `subir()`.

    O valor dos dois fatores de `modo.py` está em a autorização ser declarada
    no ponto que escreve. Se um frame de fora já abriu o `destravar()`, esta
    função escreveria sob a justificativa de outra pessoa — e o recibo
    registraria um motivo que não foi o que autorizou. Pior: um `destravar()`
    largado aberto num script transforma toda chamada seguinte em escrita
    autorizada por acidente.

    Não há suavização aqui de propósito. Portão é decisão binária: quem chama
    fecha o `destravar()` dele e deixa `subir()` abrir o próprio.
    """
    estado = modo.estado()
    if estado["destravado_no_codigo"]:
        raise TravaAberta(
            "a trava de escrita JÁ estava aberta quando subir() foi chamado — "
            f"motivo herdado: {estado['motivo']!r}.\n"
            "subir() abre a própria trava com o próprio motivo, e recusa "
            "escrever sob autorização de terceiros. Feche o destravar() de "
            "fora e chame de novo. Nada foi enviado."
        )


def _exigir_selo(preparo: Preparo) -> Selo:
    """Recusa payload que não passou por `validate_only` — ou que mudou depois."""
    selo = preparo.selo
    if selo is None:
        raise PayloadNaoValidado(
            "este grafo não tem selo de validate_only. "
            f"{preparo.porque_nao()}\n"
            "Rode preparar() e só suba o Preparo que ele devolver. Nada foi "
            "enviado."
        )

    if selo.customer_id != preparo.customer_id:
        raise PayloadNaoValidado(
            f"o selo é da conta {selo.customer_id} e o preparo aponta para "
            f"{preparo.customer_id}. Um payload provado numa conta não "
            "autoriza escrita em outra. Nada foi enviado."
        )

    if selo.login_customer_id != preparo.login_customer_id:
        raise PayloadNaoValidado(
            f"o selo foi provado sob MCC {selo.login_customer_id} e o preparo "
            f"aponta para {preparo.login_customer_id}. Trocar login_customer_id "
            "troca o escopo de autorização. Nada foi enviado."
        )

    if selo.canal != preparo.canal:
        raise PayloadNaoValidado(
            f"o selo é do canal {selo.canal} e o rótulo do preparo foi trocado "
            f"para {preparo.canal}. O canal das operações é a autoridade; "
            "relabeling não autoriza outro executor. Nada foi enviado."
        )

    if len(preparo.operacoes) != selo.n_operacoes:
        raise PayloadNaoValidado(
            f"o grafo tinha {selo.n_operacoes} operações quando foi provado e "
            f"tem {len(preparo.operacoes)} agora. Nada foi enviado."
        )

    try:
        atual = _autoridade_das_operacoes(preparo.operacoes)
    except ValueError as exc:
        raise PayloadNaoValidado(
            f"as operações não têm autoridade estrutural válida: {exc}. "
            "Nada foi enviado."
        ) from exc

    if atual.canal != selo.canal:
        raise PayloadNaoValidado(
            f"o selo declara canal {selo.canal}, mas campaign_operation.create "
            f"declara {atual.canal}. O conteúdo das operações é a autoridade. "
            "Nada foi enviado."
        )
    if atual.tipos != selo.tipos_operacoes:
        raise PayloadNaoValidado(
            "o tipo/verbo das operações divergiu depois do validate_only: "
            f"provado {selo.tipos_operacoes}, atual {atual.tipos}. Nada foi "
            "enviado."
        )
    if atual.hashes != selo.hashes_operacoes:
        posicoes = [
            i
            for i, (antes, depois) in enumerate(
                zip(selo.hashes_operacoes, atual.hashes)
            )
            if antes != depois
        ]
        raise PayloadNaoValidado(
            "o hash individual das operações divergiu depois do validate_only "
            f"nas posições {posicoes or ['comprimento']}. Nada foi enviado."
        )
    if atual.impressao != selo.impressao:
        raise PayloadNaoValidado(
            "o grafo mudou depois do validate_only: impressão provada "
            f"{selo.impressao[:12]}, impressão atual "
            f"{atual.impressao[:12]}. O que seria enviado não é o que o "
            "Google aceitou. Nada foi enviado."
        )
    return selo


def _com_sucesso(recibo: Recibo, resposta: Any) -> Recibo:
    return dataclasses.replace(
        recibo,
        estado=ACEITO,
        criados=_colher_criados(resposta),
        request_id=str(getattr(resposta, "request_id", "") or ""),
        explicacao=(
            "a API confirmou a criação do grafo inteiro. A campanha está "
            "PAUSED: não entra em leilão e não gasta, mas os anúncios entram "
            "na fila de revisão do Google — o veredito de política sai em "
            "ad_group_ad.policy_summary, pelos resource names abaixo."
        ),
    )


def _com_falha(recibo: Recibo, falha: FalhaGads, *, bruta: BaseException | None) -> Recibo:
    estado, explicacao = _estado_da_conta(bruta)
    return dataclasses.replace(
        recibo,
        estado=estado,
        falha=falha,
        request_id=falha.request_id,
        explicacao=explicacao,
    )


def _estado_da_conta(bruta: BaseException | None) -> tuple[str, str]:
    """Traduz a exceção em ESTADO DA CONTA, que é outra pergunta que a classe.

    `Classe` responde "vale retentar?". Aqui a pergunta é "sobrou alguma coisa
    lá?", e ela tem uma resposta a mais: não sei.

    O sinal que separa os casos é a presença de um `GoogleAdsFailure` na
    exceção original. Ele existe quando o servidor processou a requisição e a
    recusou — e num mutate atômico recusa significa zero recursos criados.
    Quando ele não existe, a chamada morreu sem veredito e o servidor pode ter
    aplicado tudo antes de a conexão cair.
    """
    if bruta is not None and getattr(bruta, "failure", None) is not None:
        return RECUSADO, (
            "a API respondeu recusando o grafo inteiro. O mutate é atômico e "
            "partial_failure=False, então NADA foi criado — não há budget "
            "órfão nem campanha pela metade para limpar."
        )
    return INDETERMINADO, (
        "a chamada terminou sem veredito da API. O mutate pode ter sido "
        "aplicado antes de a resposta se perder. CONFIRA A CONTA antes de "
        "tentar de novo: procure a campanha pelo nome registrado neste recibo. "
        "Uma segunda tentativa sem conferir cria a campanha duplicada."
    )


# ── leitura do payload e da resposta ───────────────────────────────────────


def _nome_campanha(operacoes) -> str:
    """Lê o nome da campanha DO PAYLOAD que vai ser enviado.

    Re-derivar com `comum.carimbo()` daria outro segundo e portanto outro nome,
    e o nome é o único identificador que sobra quando a resposta não volta.
    """
    for op in operacoes:
        criar = getattr(getattr(op, "campaign_operation", None), "create", None)
        nome = str(getattr(criar, "name", "") or "") if criar is not None else ""
        if nome:
            return nome
    return ""


def _colher_criados(resposta: Any) -> tuple[Criado, ...]:
    """Extrai os resource names de `mutate_operation_responses`.

    Cada entrada é um oneof `response` com um `*_result` dentro, e o nome do
    campo preenchido é o que diz de que tipo é o recurso — `campaign_result`,
    `ad_group_ad_result`. A posição registrada é a da LISTA DE RESPOSTA: o
    proto documenta `mutate_operation_responses` como "all responses for the
    mutate" e não promete paridade de índice com as operações enviadas, então
    quem identifica o recurso aqui é o tipo, não a posição.
    """
    saida: list[Criado] = []
    for i, item in enumerate(getattr(resposta, "mutate_operation_responses", None) or []):
        campo = _qual_oneof(item, "response")
        if not campo:
            continue
        resultado = getattr(item, campo, None)
        rn = str(getattr(resultado, "resource_name", "") or "")
        if rn:
            saida.append(Criado(posicao=i, tipo=campo, resource_name=rn))
    return tuple(saida)


def _qual_oneof(mensagem: Any, nome: str) -> str:
    """`WhichOneof` mora no pb2; proto-plus o esconde atrás de `_pb`.

    As duas formas aparecem de verdade: o objeto devolvido por
    `client.get_type()` responde direto, e o que sai de dentro de um campo
    repetido às vezes vem embrulhado. Tentar as duas custa nada e evita um
    `AttributeError` no meio do único caminho que escreve.
    """
    for alvo in (mensagem, getattr(mensagem, "_pb", None)):
        which = getattr(alvo, "WhichOneof", None)
        if which is None:
            continue
        try:
            campo = which(nome)
        except Exception:  # noqa: BLE001 — objeto sem esse oneof
            continue
        if campo:
            return str(campo)
    return ""


def _tipo_da_operacao(op: Any) -> str:
    """Tipo externo + verbo interno, ambos vindos dos oneofs do proto."""
    externo = _qual_oneof(op, "operation")
    if not externo:
        raise ValueError("MutateOperation sem ramo do oneof `operation`")
    interna = getattr(op, externo, None)
    verbo = _qual_oneof(interna, "operation") if interna is not None else ""
    if not verbo:
        raise ValueError(f"{externo} sem create/update/remove selecionado")
    return f"{externo}.{verbo}"


def _hash_da_operacao(op: Any) -> str:
    return hashlib.sha256(_bytes_da_operacao(op)).hexdigest()


def _assinaturas_das_operacoes(
    operacoes,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    tipos: list[str] = []
    hashes: list[str] = []
    for op in operacoes:
        tipos.append(_tipo_da_operacao(op))
        hashes.append(_hash_da_operacao(op))
    return tuple(tipos), tuple(hashes)


def _impressao_das_assinaturas(
    tipos: tuple[str, ...], hashes: tuple[str, ...]
) -> str:
    if len(tipos) != len(hashes):
        raise ValueError("tipos e hashes de operação têm comprimentos diferentes")
    material = {
        "versao": "volc.google_ads.operacoes.v2",
        "operacoes": [
            {"indice": i, "tipo": tipo, "sha256": resumo}
            for i, (tipo, resumo) in enumerate(zip(tipos, hashes))
        ],
    }
    bruto = json.dumps(
        material, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(bruto).hexdigest()


def _canal_das_operacoes(operacoes, tipos: tuple[str, ...]) -> str:
    canais: list[str] = []
    for op, tipo in zip(operacoes, tipos):
        if tipo != "campaign_operation.create":
            continue
        campanha = op.campaign_operation.create
        valor = getattr(campanha, "advertising_channel_type", None)
        nome = str(getattr(valor, "name", "") or "").strip().upper()
        if not nome:
            # Com ``use_proto_plus=True`` o campo costuma voltar como Enum;
            # com o cliente real usado pelo harness v25 ele pode voltar como
            # inteiro. O descriptor do próprio proto é a autoridade para a
            # tradução — não uma tabela copiada nem o rótulo de ``Preparo``.
            pb = getattr(campanha, "_pb", campanha)
            descritor = getattr(pb, "DESCRIPTOR", None)
            campo = (
                descritor.fields_by_name.get("advertising_channel_type")
                if descritor is not None
                else None
            )
            enum_descritor = getattr(campo, "enum_type", None)
            try:
                numero = int(getattr(pb, "advertising_channel_type"))
            except (AttributeError, TypeError, ValueError):
                numero = -1
            item = (
                enum_descritor.values_by_number.get(numero)
                if enum_descritor is not None
                else None
            )
            nome = str(getattr(item, "name", "") or "").strip().upper()
        if not nome or nome in {"UNSPECIFIED", "UNKNOWN"}:
            raise ValueError(
                "campaign_operation.create sem advertising_channel_type legível"
            )
        canais.append(nome)
    if len(canais) != 1:
        raise ValueError(
            "o grafo precisa de exatamente uma campaign_operation.create com "
            f"canal explícito; encontrou {len(canais)}"
        )
    return canais[0]


def _autoridade_das_operacoes(
    operacoes, *, canal_esperado: str | None = None
) -> AutoridadeDasOperacoes:
    """Deriva canal, tipos e conteúdo do lote que realmente seria enviado."""
    ops = tuple(operacoes)
    if not ops:
        raise ValueError("grafo sem operações não tem canal nem conteúdo prováveis")
    tipos, hashes = _assinaturas_das_operacoes(ops)
    canal = _canal_das_operacoes(ops, tipos)
    if canal_esperado is not None and canal != str(canal_esperado):
        raise ValueError(
            f"perfil declarou {canal_esperado!r}, operações declaram {canal!r}"
        )
    return AutoridadeDasOperacoes(
        canal=canal,
        tipos=tipos,
        hashes=hashes,
        impressao=_impressao_das_assinaturas(tipos, hashes),
    )


def _impressao(operacoes) -> str:
    """sha256 canônico do tipo + conteúdo de cada operação, em ordem."""
    tipos, hashes = _assinaturas_das_operacoes(tuple(operacoes))
    return _impressao_das_assinaturas(tipos, hashes)


def _bytes_da_operacao(op: Any) -> bytes:
    alvo = getattr(op, "_pb", op)
    serializar = getattr(alvo, "SerializeToString", None)
    if serializar is not None:
        try:
            return serializar(deterministic=True)
        except TypeError:
            return serializar()
    # Sem proto (dublê de teste): `repr` de dataclass frozen é estável.
    return repr(op).encode("utf-8", "replace")


def _carimbo() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _gravar(recibo: Recibo, pasta: Path) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / recibo.arquivo
    caminho.write_text(
        json.dumps(recibo.para_json(), ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return caminho


# ── CLI ────────────────────────────────────────────────────────────────────

# Conta de prova, a mesma do `copy/provar.py`: zero campanhas, zero histórico.
# Serve de default para `--dry`, que não escreve. Para `--subir` a conta é
# obrigatória na linha de comando — escrever no default de alguém é como o
# `destravar()` esquecido, só que com fatura.
CONTA_PROVA = "8017851692"        # Crédito Up
MCC_PROVA = "6016739364"          # MCC VOLC Negócios Digitais


def main() -> int:
    ap = argparse.ArgumentParser(description="prova e (com trava aberta) sobe a campanha")
    ap.add_argument("--dry", action="store_true",
                    help="monta e roda validate_only; não escreve nada")
    ap.add_argument("--subir", action="store_true",
                    help="escreve de verdade; exige trava aberta e --motivo")
    ap.add_argument("--conta", default="")
    ap.add_argument("--mcc", default="")
    ap.add_argument("--motivo", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.subir and not args.conta:
        ap.error("--subir exige --conta explícita")
    if args.subir == args.dry:
        ap.error("escolha exatamente um: --dry ou --subir")

    from .briefs.fgts_saque_aniversario import BRIEF

    conta = args.conta or CONTA_PROVA
    mcc = args.mcc or MCC_PROVA

    preparo = preparar(conta, BRIEF, login_customer_id=mcc)
    if not preparo.provado:
        print(f"NÃO PROVADO — {preparo.porque_nao()}")
        return 1

    if args.dry:
        saida = {
            "provado": True,
            "conta": conta,
            "campanha": preparo.nome_campanha,
            "n_operacoes": preparo.selo.n_operacoes,
            "impressao": preparo.selo.impressao,
            "trava": "fechada" if not modo.escrita_permitida() else "ABERTA",
        }
        print(json.dumps(saida, ensure_ascii=False, indent=1) if args.json
              else "\n".join(f"{k:14} {v}" for k, v in saida.items()))
        return 0

    recibo = subir(preparo, motivo=args.motivo)
    print(json.dumps(recibo.para_json(), ensure_ascii=False, indent=1)
          if args.json else recibo.resumo())
    return 0 if recibo.estado == ACEITO else 1


if __name__ == "__main__":
    raise SystemExit(main())
