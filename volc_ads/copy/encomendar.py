"""A ponte entre o cockpit do Hub de Tráfego e a cascata de copy.

## O que ela liga

`pautador_ponte.Cockpit` já carrega tudo que o `PROMPT.md` pede — nicho, URL,
país, idioma, vertical, keywords triadas e os fatos verificados do funil. O
`render.Encomenda` pede exatamente essas coisas. Faltava o tradutor, e o próprio
`pautador_ponte.Fato` declarava isso no comentário: "quem os injetar será o
Estágio 3". É este arquivo.

## ⚠️ O tipo de fato do Pautador NÃO é o tipo de fato do prompt — era

Medido em 18/08/2026 no card 73: dos 6 fatos que o cockpit devolve, **4 têm
`tipo: "afirmacao"`** — e a seção 2 do `PROMPT.md` não conhece esse tipo.
`Encomenda` recusa o desconhecido com `ErroDeRender`, e faz bem: o tipo é o que
liga a seção 2 às mecânicas da seção 5, então um tipo inventado desabilitaria
mecânica em silêncio.

Desde 30/09/2026 (contrato entre as trilhas) a ponte copia o tipo DECLARADO
pela pesquisa e, em estado antigo, aplica a regra de legado declarada
(`dados_validados` → `[contexto]`, marcado `regra_legado`). `[contexto]` entrou
na seção 2 com a semântica escrita: sustenta relevância e nomeação, nunca
número, prazo ou condição — e o contrato confere isso em código, sempre.

Continua valendo: o fato de tipo DESCONHECIDO é **descartado e RELATADO**,
nunca remapeado. E o fato marcado `citavel=False` (contraditório na pesquisa)
também cai, com o motivo: ele não ancora anúncio.

## Esta ponte não chama o Google, e isso é escolha

`ciclo.gerar()` aceita um `Juiz` — em `copy/provar.py` ele é `validate_only`
contra a conta real. Aqui ele é o juiz nulo, por dois motivos:

1. **O Google já julga esta copy, uma linha depois.** `/provar` monta a campanha
   inteira com a copy dentro e submete o payload real. Julgar a copy isolada
   antes disso seria julgar duas vezes o mesmo texto — e a segunda vez é a que
   vale, porque é a que reflete a campanha que vai ser criada.
2. **A cascata roda até 8 rodadas** (`ciclo.TETO_RODADAS`). Com o juiz do Google
   ligado, cada rodada é uma chamada `validate_only` — a mais lenta do fluxo,
   segundo o cabeçalho de `routers/trafego.py`. Oito delas para escrever um
   texto que ainda vai ser julgado inteiro depois.

O contrato local (`contrato.checar`, 5 classes) continua rodando em toda rodada.
Ele é determinístico, independente de idioma e de graça — é ele que pega
comprimento, contagem, ancoragem, duplicata e mecânica.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from . import ciclo, render
from .contrato import Achado
from .render import Encomenda, Fato

log = logging.getLogger("volc.copy.encomendar")


def _sem_google(_dados: dict) -> None:
    """O juiz nulo. Ver o cabeçalho: o Google julga o payload inteiro em
    `/provar`, e julgar a copy isolada antes seria julgar duas vezes."""
    return None


@dataclass
class Escrita:
    """O que a cascata produziu, com a medição colada.

    ⚠️ `custo` pode ser `None` — `cliente.py` não inventa preço. Sem
    `preco_entrada_mi`/`preco_saida_mi` configurados, a tela mostra "preço não
    configurado" em vez de um número plausível. Tokens e latência são sempre
    medidos de verdade.
    """

    aceita: bool
    copy: dict
    # ⚠️ Cada pendência é um DICIONÁRIO, não uma frase.
    #
    # `classe` separa duas coisas que a tela não pode misturar:
    # `ancoragem_mentiu` é o modelo errando a própria contabilidade (o anúncio
    # está certo) e `forma_reescrever` é o anúncio errado — como uma descrição
    # de 91 caracteres num teto de 90, que o Google recusa. Enquanto as duas
    # viajaram como texto solto, a tela mostrou as seis primeiras e escondeu
    # justamente as quatro que impediam a campanha de subir.
    pendentes: tuple[dict, ...] = ()
    diario: tuple[str, ...] = ()
    geracoes_conjunto: int = 0
    geracoes_asset: int = 0
    # Fatos que o cockpit trouxe e o PROMPT.md não conhece. Ver o cabeçalho.
    fatos_descartados: tuple[str, ...] = ()
    fatos_usados: int = 0
    medicao: dict[str, Any] = field(default_factory=dict)
    segundos: float = 0.0


def encomendar(
    cockpit: Any,
    *,
    keywords: Sequence[str],
    certificacoes: Sequence[str] = (),
    match_type: str = "PHRASE",
    url_final: str | None = None,
    # ⚠️ `None` herda a vertical da ENTIDADE. Preenchido, vence — porque a
    # vertical é decisão de fato sobre o negócio, e desde 19/08/2026 quem a
    # responde é o operador, no portão de política do cockpit.
    #
    # Sem este parâmetro a copy era escrita com as regras de uma vertical e o
    # payload provado com as de outra: o operador marcava `informativo` no
    # portão e recebia texto restrito de `financeiro`.
    vertical: str | None = None,
    # O que o leitor DIGITOU, em três estados (`inteligencia_google.modelo.
    # TermosDeBusca`): de `coletor.coletar_termos_de_busca` (search_term_view)
    # ou de `coletor.carregar_termos_de_arquivo` (export do integrador).
    # `None` NÃO é lista vazia: vira `ausente`, com o motivo escrito no prompt.
    termos_de_busca: Any = None,
) -> tuple[Encomenda, list[str]]:
    """Cockpit + keywords escolhidas → `Encomenda`, e o que caiu no caminho.

    `certificacoes` é o que a CONTA comprovadamente tem, e o padrão é vazio de
    propósito: sem certificação declarada, `render._habilitacao` restringe mais.
    Errar para o lado restritivo produz copy mais pobre; errar para o outro
    produz anúncio reprovado por política numa vertical regulada.
    """
    o = cockpit.origem

    aceitos = render.tipos_de_fato()
    fatos: list[Fato] = []
    descartados: list[str] = []
    for f in (o.fatos or ()):
        if f.tipo not in aceitos:
            descartados.append(
                f"{f.id} (tipo '{f.tipo}' não existe na seção 2 do PROMPT.md)")
            continue
        if getattr(f, "citavel", None) is False:
            descartados.append(
                f"{f.id} (marcado não citável na pesquisa: não ancora anúncio)")
            continue
        fatos.append(Fato(id=f.id, tipo=f.tipo, texto=f.texto, fonte=f.fonte,
                          escopo=str(getattr(f, "escopo", None) or "")))

    if termos_de_busca is None:
        from ..inteligencia_google.modelo import termos_ausentes  # noqa: PLC0415

        termos_de_busca = termos_ausentes(
            "nenhuma coleta de termos de busca (search_term_view ou arquivo) foi "
            "entregue a esta encomenda")

    # A amostra do corpus é o que ancora o TOM na operação real — 6.651
    # headlines aprovados e servindo. Ausência dela não impede escrever, então
    # a falha vira aviso e não exceção.
    amostra: tuple[str, ...] = ()
    origem_amostra = ""
    try:
        amostra, origem_amostra = render.amostra_do_corpus(o.idioma or "pt")
    except Exception as exc:  # noqa: BLE001
        descartados.append(f"amostra do corpus indisponível ({str(exc)[:80]})")

    enc = Encomenda(
        nicho=o.nicho,
        url=url_final or o.url_final,
        keywords=tuple(dict.fromkeys(k for k in keywords if k)),
        fatos=tuple(fatos),
        # Três estados, nunca `()` fixo: até 30/09/2026 aqui ia uma tupla vazia
        # e o prompt dizia "nenhum termo colhido" de uma campanha que NUNCA foi
        # consultada — ausência apresentada como medição.
        termos_de_busca=termos_de_busca,
        pais=o.pais or "BR",
        idioma=o.idioma or "",
        vertical=vertical or o.vertical or "informativo",
        certificacoes=tuple(certificacoes),
        match_type=match_type,
        amostra=amostra,
        origem_amostra=origem_amostra,
    )
    return enc, descartados


def escrever(
    cockpit: Any,
    *,
    keywords: Sequence[str],
    cliente: ciclo.Cliente | None = None,
    certificacoes: Sequence[str] = (),
    match_type: str = "PHRASE",
    url_final: str | None = None,
    # Repassado a `encomendar()`. `None` herda a vertical da entidade; ver o
    # porquê lá. Esta função é a porta que o backend chama — acrescentar o
    # parâmetro só em `encomendar()` fez a rota estourar com
    # `escrever() got an unexpected keyword argument 'vertical'`.
    vertical: str | None = None,
    # Repassado a `encomendar()`: um `TermosDeBusca` (presente |
    # vazio_confirmado | ausente). `None` = não coletado, e o prompt diz isso.
    termos_de_busca: Any = None,
    # ⚠️ O modelo é escolhível para PODER COMPARAR. Não existe modelo medido
    # para copy nesta operação — declarar um como "o certo" seria inventar
    # benchmark. `None` usa o do ambiente (`VOLC_ADS_COPY_MODELO` ou o do
    # backend). Passar um nome permite rodar o mesmo card em modelos diferentes
    # e olhar o resultado lado a lado, que é a única forma honesta de escolher.
    modelo: str | None = None,
    # O juiz de sentido. Ligado, desliga a C7 heurística e a C8 — ver
    # `contrato.checar` e `juiz_semantico.py`. O lastro TIPADO (existência do
    # fato e tipo compatível) roda sempre; e se o juiz cair, a copy não é
    # aceita (pendência `JS.indisponivel`).
    com_juiz_semantico: bool = True,
) -> Escrita:
    """Roda a cascata inteira e devolve a copy com a medição colada.

    `cliente=None` monta o real a partir do ambiente. Passar um dublê é como os
    testes rodam sem chave e sem rede.
    """
    from .cliente import criar

    enc, descartados = encomendar(
        cockpit, keywords=keywords, certificacoes=certificacoes,
        match_type=match_type, url_final=url_final, vertical=vertical,
        termos_de_busca=termos_de_busca)

    c = cliente if cliente is not None else criar(modelo=modelo)

    # O juiz de sentido usa o MESMO cliente: mesma chave, mesmo modelo, mesma
    # medição de token. Um juiz noutro modelo introduziria uma variável a mais
    # justamente na hora de comparar modelos.
    juiz_sem = None
    if com_juiz_semantico:
        from . import juiz_semantico as _js

        # O juiz é EDITOR (B6, 30/09/2026): recebe os fatos POR EXTENSO e
        # tipados (ver `_fatos_para_juiz`), os termos de busca com o estado da
        # coleta, o destino do clique e os trechos que as listas de palavras
        # marcaram — que não reprovam sozinhos.
        juiz_sem = _js.montar_juiz(
            c, fatos_texto=_fatos_para_juiz(enc),
            nicho=getattr(getattr(cockpit, "origem", None), "nicho", "") or "",
            termos_texto=render._bloco_termos(enc.termos_de_busca),
            destino=_destino_para_juiz(enc),
            # O que a LP promete (título, subtítulo, CTA), da ponte. Sem ela, o
            # bloco diz AUSENTE com o motivo, ou "não entregue".
            promessa_lp=_js.bloco_promessa_da_lp(getattr(
                getattr(cockpit, "origem", None), "promessa_da_lp", None)),
            pais=enc.pais, idioma=enc.idioma or "pt", vertical=enc.vertical)
    t0 = time.monotonic()
    r = ciclo.gerar(
        cliente=c,
        juiz=_sem_google,
        pedido=enc.pedido(),
        prompt_usuario=render.montar(enc),
        fatos_texto=_fatos_texto(enc),
        juiz_semantico=juiz_sem,
    )
    segundos = time.monotonic() - t0

    return Escrita(
        aceita=r.ok,
        copy=r.dados,
        pendentes=tuple(_texto_do_achado(a) for a in r.pendentes),
        diario=tuple(r.estado.diario),
        geracoes_conjunto=r.geracoes_conjunto,
        geracoes_asset=r.geracoes_asset,
        fatos_descartados=tuple(descartados),
        fatos_usados=len(enc.fatos),
        medicao=(c.resumo() if hasattr(c, "resumo") else {}),
        segundos=round(segundos, 2),
    )


def _fatos_texto(enc: Encomenda) -> str:
    """A linha curta que a regeneração de asset carrega junto.

    `ciclo._prompt_asset` reinjeta isto quando refaz UM título — sem ela, o
    modelo perderia o lastro e devolveria um título sem fato para ancorar.
    """
    if not enc.fatos:
        return ""
    return "FATOS: " + " · ".join(f"{f.id} {f.tipo}" for f in enc.fatos)


def _fatos_para_juiz(enc: Encomenda) -> str:
    """Os fatos POR EXTENSO — id, tipo, texto e fonte.

    ## ⚠️ Não confunda com `_fatos_texto`, e o custo de confundir foi medido

    `_fatos_texto` devolve `"FATOS: n1 numero · n2 numero · …"` — só id e tipo.
    Ela existe para a regeneração de UM asset, onde o modelo já viu os fatos na
    passada anterior e só precisa da referência.

    Em 19/08/2026 eu passei essa linha ao juiz semântico. Ele recebeu dez ids
    sem um único valor e concluiu, corretamente, que nada sustentava `0,58%`.
    Reprovou as oito alegações da copy — todas ancoradas, todas com fonte. O
    juiz acertou; a entrada é que era lixo.

    Um juiz que confere valor precisa VER o valor. É essa a diferença.
    """
    if not enc.fatos:
        return ""
    linhas = []
    for f in enc.fatos:
        fonte = f" (fonte: {f.fonte})" if getattr(f, "fonte", "") else ""
        escopo = getattr(f, "escopo", "") or ""
        escopo = f" · escopo: {escopo}" if escopo else ""
        linhas.append(f"  {f.id} [{f.tipo}] {f.texto}{fonte}{escopo}")
    return "\n".join(linhas)


def _destino_para_juiz(enc: Encomenda) -> str:
    """Para onde o clique leva. Todo sitelink aponta para a URL final do anúncio
    (`campanha/search.py`: uma landing page só), e é isso que se declara."""
    if not enc.url:
        return ""
    return (f"  anúncio → {enc.url}\n"
            f"  sitelink[*] → {enc.url} (todo sitelink desta campanha aponta para a "
            f"URL final do anúncio)")


def _texto_do_achado(a: Achado) -> dict:
    return {
        "classe": a.classe.value,
        "codigo": a.codigo,
        "alvo": str(a.alvo) if a.alvo else None,
        "detalhe": a.detalhe,
        "texto": str(a),
    }
