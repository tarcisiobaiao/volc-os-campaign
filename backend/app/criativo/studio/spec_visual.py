"""Spec visual versionada; uma decisão estratégica, uma composição por formato.

As medidas são direção de arte, não uma alegação de precisão do provider.
Não há chamada LLM aqui e a copy externa nunca entra no prompt de pixels.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.criativo import dominio
from app.criativo.agente.contrato import CopyCompartilhada, PecaCriativa
from services.creative_engine.envelope_openai import canvas_para


class CreativeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Missing version remains legacy. Only a newly proposed, explicitly versioned
    # art direction opts into the new renderer instructions.
    schema_version: Literal["volc.creative-spec/1", "volc.creative-spec/2"] = "volc.creative-spec/1"
    creative_ref: str
    conceito: str
    angulo: str
    intencao: str
    fato_refs: list[str]
    texto_exato: dict[str, str]
    copy_externa: dict[str, str]
    direcao_visual: str
    # `checklist` é lista, então o valor deixou de ser sempre `str`. O tipo
    # aberto é o que permite a direção de arte crescer sem que uma spec antiga
    # deixe de reler — e a validação de cada campo mora em `DirecaoDeArte`.
    direcao_de_arte: dict[str, object] = Field(default_factory=dict)
    formato: str
    largura_final: int
    altura_final: int
    canvas_provider: str
    margem_segura: dict[str, int]
    composicao: str
    hierarquia: str
    contraste: str
    papel_referencia: str
    #: A família cromática do assunto. Vazia em specs históricas, e é assim que
    #: o replay de uma aprovação antiga continua produzindo o mesmo prompt.
    familia_cromatica: list[str] = Field(default_factory=list)
    #: O plano de composição resolvido para esta peça, quando a tipografia vem
    #: por código. Vazio nas specs históricas e no caminho 'modelo'.
    plano_de_composicao: dict[str, object] = Field(default_factory=dict)
    proibidos: list[str]
    revisao_visual: Literal["humana_pendente"] = "humana_pendente"

    @model_validator(mode="after")
    def blueprint_v2_completo(self):
        if self.schema_version == "volc.creative-spec/2":
            if self.direcao_de_arte.get("blueprint_version") != "volc.art-direction/2":
                raise ValueError("Spec v2 exige direção de arte v2 explicitamente aprovada.")
            campos = ("cena", "tratamento", "composicao", "tipografia", "paleta_e_contraste")
            if any(not str(self.direcao_de_arte.get(campo) or "").strip() for campo in campos):
                raise ValueError("Spec v2 exige os cinco campos do blueprint aprovado.")
        return self


def especificar(peca: PecaCriativa, copy: CopyCompartilhada, slot: str, modo: str,
                familia_cromatica: list[str] | None = None,
                semente_do_plano: int = 0,
                tipografia_por_codigo: bool = False) -> CreativeSpec:
    formato = dominio.formato_de(slot)
    w, h = formato.largura, formato.altura
    # ⚠️ `vertical` governa APENAS `margem_segura`, e o limiar está errado de
    # propósito preservado: 1080x1350 dá h/w = 1,25 e NÃO é "vertical" aqui.
    # Corrigir o limiar mudaria a margem de toda peça 4x5 já planejada, que é
    # uma alteração visual que ninguém pediu nesta frente. O que o limiar NÃO
    # governa mais é a composição — ver abaixo.
    vertical = h / w > 1.6
    paisagem = w / h > 1.5
    margem = round(w * .07)
    direcao = getattr(peca, "direcao_de_arte", None)
    versao = (
        "volc.creative-spec/2"
        if direcao and direcao.blueprint_version == "volc.art-direction/2"
        else "volc.creative-spec/1"
    )

    if versao == "volc.creative-spec/2":
        # O layout é do blueprint daquela peça. Esta camada contribui com a
        # única coisa que sabe e o blueprint não: a geometria da entrega.
        #
        # Até 10/09/2026 ela contribuía com muito mais, e era o problema. As
        # três frases eram função só de (largura, altura), então as quatro peças
        # 1080x1350 de um lote recebiam a MESMA sentença byte a byte — e a
        # sentença que o 4x5 recebia (ramo `else`, porque 1,25 não passa de 1,6)
        # era "bloco de headline dominante separado da cena e CTA em área limpa".
        # Somada a `contraste`, que mandava "usar área sólida/scrim quando houver
        # fotografia" e PROIBIA letra encostar na cena, ela desenhava o panfleto
        # antes de o agente abrir a boca: faixa chapada no topo, foto embaixo,
        # pílula de CTA. Diversidade de lote não tinha por onde existir.
        composicao = f"Entrega {w}x{h}. Componha para esta proporção."
        hierarquia = "A headline é o maior elemento tipográfico da peça."
        contraste = (
            "Piso de legibilidade: o texto precisa ser lido em miniatura de 150 px "
            "de largura. Como obter esse contraste é decisão do blueprint — "
            "tipografia integrada à cena, contorno, sombra ou campo de cor são "
            "todos aceitáveis; nenhum é obrigatório."
        )
    else:
        # Caminho legado, preservado literalmente: um lote v1 é replay de uma
        # aprovação antiga, não uma aprovação criativa nova.
        composicao = (
            "Composição vertical: headline no terço superior útil; uma cena central; CTA acima da área inferior protegida."
            if vertical else
            "Composição horizontal: texto ocupa uma coluna larga e a cena a outra, sem comprimir a headline."
            if paisagem else
            "Composição editorial: um único foco visual; bloco de headline dominante separado da cena e CTA em área limpa."
        )
        hierarquia = "Headline de alto impacto, maior que complemento; CTA distinto e legível. Até duas famílias tipográficas, sem texto decorativo aleatório."
        contraste = "Texto escuro sobre superfície clara ou claro sobre escura; use área sólida/scrim quando houver fotografia. Não sobreponha letras a detalhes da cena."

    if modo == "hibrido":
        # A região reservada é uma RESTRIÇÃO geométrica somada ao blueprint, não
        # um layout que o substitui. Substituir era jogar fora a direção da peça
        # para impor uma de três frases fixas ("Foto no topo, texto na faixa
        # inferior."), que é o mesmo template por outro caminho.
        from .composicao import REGIOES
        composicao = (
            f"{composicao} REGIÃO RESERVADA: {REGIOES[slot].descricao} "
            "Todo texto fica exclusivamente na região de texto; a fotografia será colada depois."
        )
    return CreativeSpec(
        schema_version=versao,
        creative_ref=peca.ref, conceito=peca.hook, angulo=peca.angulo, intencao=peca.hipotese,
        fato_refs=list(peca.fato_refs),
        texto_exato={"headline": peca.headline_interna, "complemento": peca.complemento_interno or "", "cta": peca.cta_visual or ""},
        copy_externa={"texto_principal": copy.texto_principal, "titulo": copy.titulo, "descricao": copy.descricao, "cta": copy.cta_nativa},
        direcao_visual=peca.direcao_visual,
        direcao_de_arte=direcao.model_dump() if direcao else {},
        formato=slot, largura_final=w, altura_final=h, canvas_provider=canvas_para(w, h).size,
        margem_segura={"esquerda": margem, "direita": margem, "topo": round(h * .14) if vertical else margem, "base": round(h * .18) if vertical else margem},
        composicao=composicao,
        hierarquia=hierarquia,
        contraste=contraste,
        papel_referencia=modo,
        familia_cromatica=list(familia_cromatica or []),
        plano_de_composicao=(
            _plano_da_peca(direcao, semente_do_plano) if tipografia_por_codigo else {}
        ),
        # ⚠️ Esta lista NÃO muda: ela é campo persistido e entra no prompt v1, que
        # é byte-idêntico por contrato (replay não é aprovação criativa nova).
        # Quem filtra "selo oficial inventado" é o compilador v2 — ver `_SEM_EFEITO_V2`.
        proibidos=["alegações não sustentadas", "logos e marcas não solicitados", "selo oficial inventado", "texto externo da copy na arte", "IDs ou metadados operacionais"],
    )


def compilar_prompt(spec: CreativeSpec) -> str:
    if spec.schema_version == "volc.creative-spec/2":
        return _compilar_blueprint_v2(spec)
    # Keep this v1 output unchanged: replay is not a new creative approval.
    # JSON quotes are delimiters, not typography to reproduce. Preserve the
    # actual string without uppercasing, shortening, summarizing or translating.
    textos = "\n".join(f"{papel}: {json.dumps(texto, ensure_ascii=False)}" for papel, texto in spec.texto_exato.items() if texto)
    return (
        "Crie UMA arte publicitária final, pronta para revisão humana, não um mockup nem uma fotografia sem diagramação.\n"
        f"CONCEITO: {spec.conceito}\nÂNGULO: {spec.angulo}\nINTENÇÃO: {spec.intencao}\n"
        f"DIREÇÃO VISUAL APROVADA: {spec.direcao_visual}\n"
        f"DIREÇÃO DE ARTE: {json.dumps(spec.direcao_de_arte, ensure_ascii=False)}\n"
        f"COMPOSIÇÃO {spec.formato}: {spec.composicao}\n{spec.hierarquia}\n{spec.contraste}\n"
        f"Margens mínimas orientativas no arquivo final {spec.largura_final}x{spec.altura_final}: {json.dumps(spec.margem_segura)} px. "
        "Ajuste quebras de linha sem alterar palavras. Não corte headline, complemento ou CTA.\n"
        "TEXTO EXATO OBRIGATÓRIO DENTRO DA IMAGEM (aspas delimitam, não devem aparecer):\n"
        f"{textos}\n"
        "Renderize TODOS os textos acima em português, com acentos e ortografia preservados. Não os substitua por placeholders. "
        "O resultado precisa conter texto legível, não apenas espaço vazio reservado. Não invente outras frases.\n"
        f"PAPEL DA REFERÊNCIA: {spec.papel_referencia}.\n"
        f"NÃO INCLUIR: {', '.join(spec.proibidos)}."
    )


def _plano_da_peca(direcao, semente: int) -> dict:
    """Resolve o plano de composição quando a peça compõe o texto por código.

    ⚠️ Quem decide isto é a ROTA, não o modelo — e a diferença custou um lote.
    Numa run real eu pedi ao estrategista que declarasse `fonte_do_texto` junto
    com os outros eixos; ele declarou certo, mas a instrução extra roubou
    atenção da tarefa editorial e três das quatro peças voltaram sem a âncora
    do assunto. Escolher a rota é decisão criativa; QUEM DESENHA A LETRA é
    consequência mecânica dela — `campo_cromatico` e `rodape_limpo` reservam
    zona, logo compõem por código, e não há julgamento nisso.

    O campo continua no contrato como OVERRIDE explícito: `modelo` numa rota que
    reserva zona desliga a prensa, e é assim que se compara os dois caminhos
    lado a lado sem tocar em código.

    ⚠️ Nada disto liga sozinho. A prensa é opt-in da OPERAÇÃO
    (`especificar(..., tipografia_por_codigo=True)`), e dentro dela a rota
    decide quais peças ganham plano. Derivar direto da rota, sem o opt-in,
    trocaria o caminho de render de todo fluxo existente em silêncio — inclusive
    o de quem só queria uma peça com faixa de cor.
    """
    if direcao is None:
        return {}
    from .planos import escolher

    override = getattr(direcao, "fonte_do_texto", None)
    if override == "modelo":
        return {}
    escolhido = escolher(direcao.rota_de_texto, semente)
    if escolhido is None:
        return {}
    nome, plano = escolhido
    return {"nome": nome, "pedido": plano["pedido"], "zona": list(plano["zona"])}


#: A receita de layout de cada rota, escrita em positivo.
#:
#: Estas frases substituem a instrução única e incondicional que existia antes
#: ("use área sólida/scrim quando houver fotografia. Não sobreponha letras a
#: detalhes da cena"), que era a lei de layout de TODA peça de TODO lote — e a
#: razão de as quatro peças reclamadas terem a mesma tarja chapada no topo.
#:
#: Só `campo_cromatico` autoriza a tarja. As outras três a proíbem, cada uma
#: propondo o que fazer no lugar, porque proibição sem alternativa devolve o
#: modelo ao comportamento de menor risco, que é justamente a tarja.
_RECEITA_DE_ROTA = {
    "integrado_na_cena": (
        "O texto encosta na cena e pertence a ela: assentado sobre superfície, parede, "
        "papel ou área de foco suave, com peso, contorno ou sombra suficientes para ser "
        "lido. NÃO crie retângulo, faixa, cartela ou barra de cor dedicada ao texto."
    ),
    "campo_cromatico": (
        "Um campo de cor chapado e contínuo sustenta o texto e ocupa parte generosa do "
        "quadro — não uma tarja fina no topo. A cena divide o quadro com esse campo em "
        "vez de ficar atrás dele."
    ),
    "tipografia_protagonista": (
        "A tipografia É a imagem: a headline ocupa a maior parte do quadro, em display "
        "pesada, podendo sangrar pelas bordas. A cena entra como textura, recorte dentro "
        "das letras ou um único objeto encostado na base. Sem fotografia dominante."
    ),
    "rodape_limpo": (
        "O assunto ocupa o quadro inteiro, de borda a borda, e o texto vive numa faixa "
        "estreita no rodapé, sem competir com o ponto focal. Nada de bloco no topo."
    ),
}


#: Proibições persistidas que o compilador v2 NÃO repassa ao modelo de imagem.
#:
#: "selo oficial inventado" é larga demais para o efeito que tem. O risco real —
#: emblema, brasão e assinatura de órgão público — já está na linha principal,
#: nomeado com precisão. O que a frase larga acrescentava era proibir carimbo
#: genérico de cenário, que é adereço de materialidade e não afirma vínculo com
#: instituição nenhuma; e, pior, colocava "selo" no espaço de saída do modelo.
#: O campo continua na spec porque ele é persistido e o prompt v1 é byte-idêntico.
_SEM_EFEITO_V2 = frozenset({"selo oficial inventado"})


def _compilar_blueprint_v2(spec: CreativeSpec) -> str:
    """Compile decisions, not a second open-ended strategy request.

    Do not infer a different style, invent a scene, shorten copy, or send the
    article/external ad copy. The five approved fields are the render blueprint.

    ## Ordem e orçamento, e por que os dois são a regra deste arquivo

    A versão anterior emitia 4.334 caracteres, dos quais 440 (10,2%) eram a
    direção DESTA peça e o resto era literal fixo, idêntico em todo lote. Um
    modelo de imagem lê isso como uma especificação de peça genérica com um
    tempero por cima — que é exatamente o que ele devolvia.

    Duas invariantes agora governam esta função:

    1. **A direção da peça abre o prompt.** O que diferencia vem primeiro,
       porque aderência cai com o comprimento e o começo é o que sobrevive.
    2. **Proibição não é vocabulário.** Cada substantivo visual citado numa
       negativa entra no espaço de saída do modelo — dizer "sem pílula de CTA"
       é uma forma cara de dizer "pílula de CTA". As proibições que sobraram
       aqui são as de POLÍTICA, que precisam viajar com os pixels; as de gosto
       viraram contraprova determinística em `agente/validacao.py`, onde o erro
       é medido em vez de pedido.
    """
    direcao = spec.direcao_de_arte
    blocos = [f"Imagem de anúncio, entrega {spec.largura_final}x{spec.altura_final}."]
    # Com plano ativo o modelo é fotógrafo, não diagramador: dos cinco campos do
    # blueprint só os três que descrevem a FOTOGRAFIA viajam. `tipografia` e
    # `composicao` falam de headline, CTA e ordem de leitura — mandar isso junto
    # com "não escreva texto" é pedir duas coisas incompatíveis.
    campos_do_blueprint = (
        (("cena", "CENA"), ("tratamento", "LUZ E MATERIALIDADE"),
         ("paleta_e_contraste", "PALETA E CONTRASTE"))
        if spec.plano_de_composicao else
        (("cena", "CENA"), ("tratamento", "LUZ E MATERIALIDADE"),
         ("composicao", "COMPOSIÇÃO E PONTO FOCAL"), ("tipografia", "TIPOGRAFIA"),
         ("paleta_e_contraste", "PALETA E CONTRASTE"))
    )
    for chave, rotulo in campos_do_blueprint:
        blocos.append(f"{rotulo}: {direcao.get(chave, '')}")
    if spec.familia_cromatica:
        # Posição de abertura e linguagem de ÁREA. Dizer "use azul e amarelo" no
        # meio do prompt produz um botão amarelo; dizer que a cor ocupa superfície
        # grande é o que muda o campo visual — que é o que faz alguém reconhecer
        # o assunto antes de ler.
        blocos.append(
            "UNIDADE CROMÁTICA OBRIGATÓRIA — a peça precisa ser reconhecida como sendo "
            f"deste assunto antes de qualquer leitura. Use esta família: {', '.join(spec.familia_cromatica)}. "
            "Pelo menos duas dessas cores ocupam SUPERFÍCIE GRANDE e contínua do quadro "
            "(fundo, parede, papel, campo chapado, vestuário ou objeto principal), somando "
            "no mínimo metade do campo visual. Cor confinada a botão, pílula ou filete não conta. "
            "São cores do universo temático, aplicadas com liberdade de composição — não são "
            "logotipo, marca nem assinatura de ninguém."
        )
    blocos.append(f"IDEIA: {spec.conceito} — {spec.angulo}")
    if spec.direcao_visual:
        blocos.append(f"DIREÇÃO APROVADA: {spec.direcao_visual}")
    if spec.plano_de_composicao:
        # ⚠️ Corte seco: quando a tipografia é do código, o modelo recebe CENA e
        # nada mais. Nada de arquitetura de texto, checklist, selo, hierarquia
        # ou piso de legibilidade — esses blocos viram ordem contraditória
        # ("componha o texto assim" + "não escreva texto") e o modelo obedece a
        # um dos dois ao acaso.
        #
        # E o pedido de composição NÃO nomeia área reservada: nomear devolve ao
        # modelo o pixel que o código controla, e costuma voltar desenhado como
        # tarja. Pede-se a queda de luz que ABRE a zona; a obediência é
        # conferida depois, por contenção da zona medida.
        blocos.append(f"COMPOSIÇÃO: {spec.plano_de_composicao['pedido']}")
        blocos.append(
            "Não escreva NENHUM texto, letra, número, legenda, marca d'água ou "
            "assinatura na imagem. Entregue apenas a cena fotográfica."
        )
        blocos.append(
            "Quando a direção for fotográfica: luz motivada, pele e materiais com textura, "
            "gesto convincente. A cena é ilustrativa e não prova nada."
        )
        blocos.append(
            "NÃO INCLUIR: logotipo, brasão, emblema ou assinatura de órgão público, "
            "de banco ou de terceiro; reprodução de tela de sistema oficial; saldo, "
            "extrato ou comprovante com valor legível."
        )
        return "\n".join(blocos)

    if direcao.get("registro") == "cartaz_beneficio":
        blocos.append(
            "REGISTRO — CARTAZ DE BENEFÍCIO: vernáculo brasileiro de anúncio de programa "
            "social. Campo de cor saturado ocupando o quadro; objeto-herói recortado com "
            "sombra projetada, grande e nítido; tipografia sem serifa MUITO pesada em caixa "
            "alta, assentada sobre faixas irregulares de cor com borda de pincel; barra de "
            "CTA larga e contrastante com seta. Alta densidade e alto contraste são "
            "corretos aqui — não suavize para parecer peça de marca."
        )
    if direcao.get("selo_de_valor"):
        blocos.append(
            f"SELO DE VALOR (texto exato, em bloco destacado de cor contrastante, "
            f"canto superior ou lateral, com o algarismo em corpo muito maior): "
            f"{json.dumps(direcao['selo_de_valor'], ensure_ascii=False)}"
        )
    if direcao.get("qualificador"):
        blocos.append(
            f"RESSALVA (texto exato, corpo pequeno, logo abaixo do selo, iniciando com "
            f"asterisco): {json.dumps(direcao['qualificador'], ensure_ascii=False)}"
        )
    if direcao.get("checklist"):
        itens = " | ".join(direcao["checklist"])
        blocos.append(
            "CHECKLIST (textos exatos, um por linha, cada um precedido de um ícone de "
            f"marca de seleção, sobre cartão ou papel claro): {itens}"
        )
    receita = _RECEITA_DE_ROTA.get(direcao.get("rota_de_texto") or "")
    if receita:
        blocos.append(f"ARQUITETURA DE TEXTO: {receita}")
    if direcao.get("presenca_humana") == "ausente":
        # Dizer "sem pessoa" no meio da prosa não sobrevive; o modelo tem um
        # prior forte de colocar gente segurando celular em qualquer briefing.
        blocos.append("SEM FIGURA HUMANA nesta peça: o assunto é carregado por objeto, documento ou tipografia.")
    blocos.append(f"FORMATO: {spec.composicao} {spec.hierarquia}")
    blocos.append(spec.contraste)
    blocos.append("TEXTO EXATO NA IMAGEM (as aspas delimitam, não aparecem):")
    blocos.extend(
        f"{papel}: {json.dumps(texto, ensure_ascii=False)}"
        for papel, texto in spec.texto_exato.items() if texto
    )
    blocos.append(
        "Preserve palavras, acentos e qualificadores; ajuste só as quebras de linha. "
        "Campo ausente é elemento ausente, nunca placeholder."
    )
    # A condicional é a garantia, e ela mora na frase de propósito: uma técnica
    # que o operador aprovou (aquarela, colagem, 3D) não pode virar fotografia
    # porque o renderizador prefere fotografia. Trocar isto por uma afirmação
    # incondicional de fotorrealismo apagaria uma aprovação explícita.
    blocos.append(
        "Quando a direção for fotográfica: luz motivada, pele e materiais com textura, "
        "gesto convincente. Não converta uma ilustração explicitamente aprovada em fotografia, "
        "e não invente pessoa ou telefone por faltar referência humana. "
        "A cena é ilustrativa e não prova nada."
    )
    if spec.papel_referencia == "hibrido":
        blocos.append(
            "Deixe intacta a região reservada: a foto real entra depois, por composição "
            "determinística, sem passar por você. Não desenhe pessoa nessa área."
        )
    # ⚠️ Lista curta de propósito, e cada item é uma linha jurídica — não estética.
    #
    # A versão anterior misturava marca registrada com adereço de cenário
    # ("notificação", "prazo", "selo de aprovação"), e o efeito de listar
    # substantivo visual numa negativa é colocá-lo no espaço de saída do modelo:
    # proibir "pílula de CTA" é uma forma cara de pedir uma. O que sobra aqui é
    # o que quebra conta de anunciante ou infringe marca; o resto do bom gosto
    # mora na direção de arte, que é onde ele funciona.
    blocos.append(
        "NÃO INCLUIR: logotipo, brasão, emblema ou assinatura de órgão público, "
        "de banco ou de terceiro; reprodução de tela de sistema oficial; saldo, "
        "extrato ou comprovante com valor legível. "
        f"{', '.join(p for p in spec.proibidos if p not in _SEM_EFEITO_V2)}."
    )
    return "\n".join(blocos)
