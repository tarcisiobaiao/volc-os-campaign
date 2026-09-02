"""Valida assets contra a especificação do canal — TODAS as violações, sempre.

## As duas decisões que moldam este arquivo

**1. Devolve tudo, não a primeira.** Parar na primeira violação transforma a
correção num jogo de tentativa e erro: conserta a proporção, roda de novo,
descobre que o peso também estoura, roda de novo. Cada rodada dessas, num
motor pago, é dinheiro. O operador (ou a cascata) precisa da lista inteira de
uma vez para escolher o remédio mais barato que resolve o conjunto.

**2. Um asset ruim não derruba o lote.** A validação separa aprovados de
reprovados e continua. É a mesma escolha de `contrato.Falha`: 20 imagens com 1
recusada são 19 imagens boas e 1 problema, não um lote perdido.

## A sutileza da contagem

A quantidade mínima é conferida sobre os APROVADOS, não sobre os entregues.
Cinco imagens das quais duas estão fora de proporção são três imagens
utilizáveis — e se o canal exige quatro, o lote está incompleto mesmo tendo
cinco arquivos. Contar entregues esconderia exatamente o buraco que a validação
existe para achar.

É por isso que `ResultadoDeValidacao.ok` olha só as violações DO LOTE: o asset
reprovado é perda conhecida e já saiu; o que decide se dá para subir é o que
sobrou cumprir o canal. Se a perda deixou um buraco, ele reaparece como
`Q1.faltam` — e aí sim o lote não está `ok`.

## O que este módulo não sabe

Não abre arquivo, não mede pixel e não fala com o Google. Ele julga o que já
foi medido; medir é trabalho do adaptador, que é quem tem os bytes. Um asset
sem medida vira violação da classe MEDIR_ANTES — nunca aprovação por omissão.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .contrato import (
    Asset,
    Classe,
    EspecificacaoDeAsset,
    ExigenciaDeCanal,
    LoteDeAssets,
    TipoDeAsset,
    Violacao,
    e_binario,
)


def _caracteres(texto: str) -> int:
    """Comprimento como o Google conta nos canais desta camada.

    Sem resolução de DKI de propósito: `{KeyWord:...}` é recurso de Search, e
    Search não passa por aqui. Se um dia passar, o medidor tem de ser o de
    `campanha/contrato.comprimento_efetivo` — importado, não reescrito. Dois
    medidores de caractere no mesmo sistema medem a divergência entre si.
    """
    return len(texto)


# ── um asset contra uma especificação ───────────────────────────────────────


def validar_asset(asset: Asset, spec: EspecificacaoDeAsset) -> tuple[Violacao, ...]:
    """Todas as regras que este asset não cumpre. Lista vazia = aprovado."""
    achados: list[Violacao] = []
    alvo = asset.identidade

    def erro(codigo: str, classe: Classe, detalhe: str) -> None:
        achados.append(Violacao(codigo, classe, detalhe, "erro", alvo))

    def aviso(codigo: str, classe: Classe, detalhe: str) -> None:
        achados.append(Violacao(codigo, classe, detalhe, "aviso", alvo))

    if asset.tipo is not spec.tipo:
        erro("E1.tipo_divergente", Classe.ESTRUTURA,
             f"asset é {asset.tipo.value}, a especificação é de {spec.tipo.value}")
        return tuple(achados)

    if not e_binario(asset.tipo):
        texto = (asset.texto or "").strip()
        if not texto:
            erro("X2.texto_vazio", Classe.REESCREVER_TEXTO, "texto vazio")
        elif spec.caracteres_maximos is not None:
            n = _caracteres(texto)
            if n > spec.caracteres_maximos:
                erro("X1.caracteres", Classe.REESCREVER_TEXTO,
                     f"{n} caracteres > limite {spec.caracteres_maximos}")
        return tuple(achados)

    # ── daqui para baixo é binário ──
    if asset.mime is None:
        erro("M1.sem_medida", Classe.MEDIR_ANTES, "mime desconhecido")
    elif spec.mimes_aceitos and asset.mime not in spec.mimes_aceitos:
        erro("F1.mime", Classe.SANEAVEL_EM_CODIGO,
             f"{asset.mime} fora de {list(spec.mimes_aceitos)}")

    if spec.bytes_maximos is not None:
        if asset.bytes_totais is None:
            erro("M1.sem_medida", Classe.MEDIR_ANTES, "tamanho em bytes desconhecido")
        elif asset.bytes_totais > spec.bytes_maximos:
            erro("P1.peso", Classe.SANEAVEL_EM_CODIGO,
                 f"{asset.bytes_totais} bytes > limite {spec.bytes_maximos}")

    if asset.tipo is TipoDeAsset.VIDEO:
        if asset.duracao_s is None:
            erro("M1.sem_medida", Classe.MEDIR_ANTES, "duração desconhecida")
        else:
            if spec.duracao_minima_s is not None and asset.duracao_s < spec.duracao_minima_s:
                erro("T1.duracao_curta", Classe.REGERAR_ASSET,
                     f"{asset.duracao_s:.1f}s < mínimo {spec.duracao_minima_s:.1f}s")
            if spec.duracao_maxima_s is not None and asset.duracao_s > spec.duracao_maxima_s:
                # Cortar o fim é local e barato; regerar é chamada paga.
                erro("T2.duracao_longa", Classe.SANEAVEL_EM_CODIGO,
                     f"{asset.duracao_s:.1f}s > máximo {spec.duracao_maxima_s:.1f}s")
        # ⚠️ ACHADO ADVERSARIAL (02/09/2026). Aqui havia um `return`, e ele fazia
        # o vídeo sair da função ANTES do bloco de geometria: um vídeo de
        # 100×100 num envelope 1080×1920 não recebia achado nenhum. Duração era
        # tudo que se julgava de vídeo, e a proporção — que é o que decide se a
        # peça serve a Reels ou Shorts — não era julgada.
        #
        # O bloco abaixo já trata medida ausente (`M1.sem_medida`) e já é
        # condicional à spec pedir dimensão, então cair nele é correto para
        # vídeo pelo mesmo motivo que é correto para imagem.

    exige_dimensao = (
        spec.largura_minima is not None
        or spec.altura_minima is not None
        or spec.proporcao_alvo is not None
    )
    if asset.largura is None or asset.altura is None:
        if exige_dimensao:
            erro("M1.sem_medida", Classe.MEDIR_ANTES,
                 "largura/altura desconhecidas — não dá para julgar dimensão nem proporção")
        return tuple(achados)

    if spec.largura_minima is not None and asset.largura < spec.largura_minima:
        # Ampliar por interpolação não cria pixel; só uma geração nova resolve.
        erro("D1.dimensao_minima", Classe.REGERAR_ASSET,
             f"largura {asset.largura} < mínimo {spec.largura_minima}")
    if spec.altura_minima is not None and asset.altura < spec.altura_minima:
        erro("D1.dimensao_minima", Classe.REGERAR_ASSET,
             f"altura {asset.altura} < mínimo {spec.altura_minima}")

    esperada = spec.proporcao_esperada
    if esperada is not None:
        atual = asset.proporcao
        assert atual is not None  # garantido pelo teste de largura/altura acima
        if abs(atual - esperada) / esperada > spec.tolerancia_proporcao:
            # Recorte determinístico é local e é o que o próprio Google oferece
            # ao anunciante; regerar seria pagar de novo pelo mesmo enquadramento.
            erro("D3.proporcao", Classe.SANEAVEL_EM_CODIGO,
                 f"{asset.largura}x{asset.altura} = {atual:.3f}, "
                 f"esperado {spec.proporcao_alvo[0]}:{spec.proporcao_alvo[1]} = {esperada:.3f}")

    # Abaixo do recomendado passa, mas custa Ad Strength — por isso aviso, e
    # por isso só depois de a dimensão mínima ter sido conferida.
    if (
        spec.largura_recomendada is not None
        and asset.largura >= (spec.largura_minima or 0)
        and asset.largura < spec.largura_recomendada
    ):
        aviso("D2.abaixo_do_recomendado", Classe.REGERAR_ASSET,
              f"largura {asset.largura} < recomendada {spec.largura_recomendada}")

    return tuple(achados)


# ── o lote contra o canal ───────────────────────────────────────────────────


@dataclass
class ResultadoDeValidacao:
    """O veredito do lote, separando o que serve do que não serve."""

    canal: str
    aprovados: tuple[Asset, ...] = ()
    reprovados: tuple[Asset, ...] = ()
    por_asset: dict[str, tuple[Violacao, ...]] = field(default_factory=dict)
    do_lote: tuple[Violacao, ...] = ()
    provisorio: bool = True
    fonte: str = ""

    @property
    def violacoes(self) -> tuple[Violacao, ...]:
        soltas = [v for lista in self.por_asset.values() for v in lista]
        return tuple(soltas) + tuple(self.do_lote)

    @property
    def erros(self) -> tuple[Violacao, ...]:
        return tuple(v for v in self.violacoes if v.severidade == "erro")

    @property
    def erros_do_lote(self) -> tuple[Violacao, ...]:
        return tuple(v for v in self.do_lote if v.severidade == "erro")

    @property
    def ok(self) -> bool:
        """O lote pode subir com o que sobrou?

        Erro de asset INDIVIDUAL não entra nesta conta, e a distinção é a razão
        de ser deste módulo: aquele asset já foi para `reprovados`, é perda
        conhecida, e ninguém vai tentar subi-lo. Dezenove imagens boas e uma
        ruim são um lote publicável — chamá-lo de reprovado devolveria ao
        operador exatamente o "tudo ou nada" que a separação existe para evitar.

        Quando a perda torna o lote incompleto, isso NÃO passa despercebido: a
        contagem mínima é feita sobre os aprovados e vira `Q1.faltam`, que é
        erro DO LOTE e derruba o `ok` aqui.
        """
        return not self.erros_do_lote

    def por_classe(self, classe: Classe) -> tuple[Violacao, ...]:
        """O que a cascata consulta para escolher o remédio."""
        return tuple(v for v in self.violacoes if v.classe is classe)

    def resumo(self) -> str:
        linhas = [
            f"validação {self.canal}: {len(self.aprovados)} aprovados, "
            f"{len(self.reprovados)} reprovados, {len(self.erros)} erros"
        ]
        if self.provisorio:
            linhas.append(f"  ⚠️ requisitos deste canal são provisórios — {self.fonte}")
        for identidade, achados in self.por_asset.items():
            for v in achados:
                linhas.append(f"  {v}")
        for v in self.do_lote:
            linhas.append(f"  {v}")
        return "\n".join(linhas)


def validar_lote(lote: LoteDeAssets, exigencia: ExigenciaDeCanal) -> ResultadoDeValidacao:
    """Valida asset por asset e depois confere a contagem sobre os APROVADOS."""
    resultado = ResultadoDeValidacao(
        canal=exigencia.canal, provisorio=exigencia.provisorio, fonte=exigencia.fonte
    )

    aprovados: list[Asset] = []
    reprovados: list[Asset] = []
    do_lote: list[Violacao] = []

    for asset in lote.assets:
        spec = exigencia.de(asset.tipo)
        if spec is None:
            # Não é erro: é um asset que este canal não usa. Ele não vai subir,
            # e dizer isso é mais útil do que reprová-lo ou ignorá-lo.
            do_lote.append(Violacao(
                "E2.sem_slot", Classe.ESTRUTURA,
                f"{exigencia.canal} não tem slot para {asset.tipo.value}",
                "aviso", asset.identidade,
            ))
            reprovados.append(asset)
            continue
        achados = validar_asset(asset, spec)
        if achados:
            resultado.por_asset[asset.identidade] = achados
        if any(v.severidade == "erro" for v in achados):
            reprovados.append(asset)
        else:
            aprovados.append(asset)

    contagem: dict[TipoDeAsset, int] = {}
    for asset in aprovados:
        contagem[asset.tipo] = contagem.get(asset.tipo, 0) + 1

    for spec in exigencia.especificacoes:
        n = contagem.get(spec.tipo, 0)
        if n < spec.quantidade_minima:
            do_lote.append(Violacao(
                "Q1.faltam", Classe.GERAR_MAIS,
                f"{n} de {spec.quantidade_minima} exigidos "
                f"(entregues {len(lote.do_tipo(spec.tipo))}, aprovados {n})",
                "erro", spec.tipo.value,
            ))
        elif spec.quantidade_maxima is not None and n > spec.quantidade_maxima:
            # Excesso não impede publicar: corta-se localmente, de graça.
            do_lote.append(Violacao(
                "Q2.excedem", Classe.CORTAR_EXCEDENTE,
                f"{n} acima do máximo {spec.quantidade_maxima}",
                "aviso", spec.tipo.value,
            ))
        if (
            spec.quantidade_recomendada is not None
            and n >= spec.quantidade_minima
            and n < spec.quantidade_recomendada
        ):
            # Recomendado sem ser exigido: o payload sobe, a peça fica pior.
            # Reprovar aqui seria recusar localmente o que a API aceita — e
            # portão que dá falso positivo é portão que alguém desliga.
            do_lote.append(Violacao(
                "Q3.abaixo_do_recomendado", Classe.GERAR_MAIS,
                f"{n} de {spec.quantidade_recomendada} recomendados",
                "aviso", spec.tipo.value,
            ))

    # Exigências que são do CONJUNTO e não de cada item. A descrição curta de
    # Performance Max é o caso: cinco descrições de 90 caracteres passam uma a
    # uma e o asset group é recusado com SHORT_DESCRIPTION_REQUIRED.
    for spec in exigencia.especificacoes:
        if spec.caracteres_de_pelo_menos_um is None:
            continue
        do_tipo = [a for a in aprovados if a.tipo is spec.tipo]
        if not do_tipo:
            continue  # a ausência já é Q1.faltam; não vale contar duas vezes
        if not any(
            _caracteres((a.texto or "").strip()) <= spec.caracteres_de_pelo_menos_um
            for a in do_tipo
        ):
            do_lote.append(Violacao(
                "X3.falta_a_curta", Classe.REESCREVER_TEXTO,
                f"nenhuma de {len(do_tipo)} tem {spec.caracteres_de_pelo_menos_um} "
                f"caracteres ou menos",
                "erro", spec.tipo.value,
            ))

    # Tetos que valem para vários tipos somados. É ERRO, não aviso: a API recusa
    # o payload inteiro, e cortar o excedente aqui exigiria escolher QUAL
    # imagem sai — decisão de quem encomendou o lote, não do validador.
    for teto in exigencia.combinados:
        somados = sum(contagem.get(tipo, 0) for tipo in teto.tipos)
        if teto.maximo is not None and somados > teto.maximo:
            do_lote.append(Violacao(
                "Q4.teto_combinado", Classe.CORTAR_EXCEDENTE,
                f"{teto.rotulo}: {somados} acima do teto conjunto {teto.maximo}",
                "erro", "+".join(t.value for t in teto.tipos),
            ))
        if somados < teto.minimo:
            do_lote.append(Violacao(
                "Q5.teto_combinado_falta", Classe.GERAR_MAIS,
                f"{teto.rotulo}: {somados} de {teto.minimo} exigidos no conjunto",
                "erro", "+".join(t.value for t in teto.tipos),
            ))

    resultado.aprovados = tuple(aprovados)
    resultado.reprovados = tuple(reprovados)
    resultado.do_lote = tuple(do_lote)
    return resultado
