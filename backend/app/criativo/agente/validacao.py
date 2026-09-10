"""Contraprovas determinísticas aplicadas depois da resposta do modelo."""

from __future__ import annotations

from collections import Counter
import json
import re
import unicodedata
from typing import Any

from .caminhos import CaminhoInvalido, resolver as resolver_caminho
from .conhecimento import carregar_regras
from .contrato import (
    TETO_DE_BLOCOS, PedidoDoAgente, PecaCriativa, SaidaDoAgente,
    contem_metadado_operacional,
)


#: Um selo que dispara a exigência de ressalva. Dinheiro, gratuidade ou
#: quantidade — os três jeitos de o selo virar promessa.
_AFIRMA_VALOR = re.compile(
    r"R\$|\d|gr[aá]tis|gratuit|100\s*%|isen|sem\s+custo", re.IGNORECASE
)

_ID_OU_SEGREDO_EXTERNO = re.compile(
    r"(?:\bEAA[A-Za-z0-9]+|\bact_\d+|\bcustomers/\d+|/Users/|/home/|https?://)",
    re.IGNORECASE,
)


class SaidaCriativaInvalida(ValueError):
    def __init__(self, erros: list[str]):
        self.erros = erros
        super().__init__("; ".join(erros))


def _distancia(a: PecaCriativa, b: PecaCriativa) -> int:
    campos = (
        "estado_mental_ref",
        "angulo",
        "hipotese",
        "mecanismo_de_interrupcao",
        "formato",
    )
    return sum(getattr(a, c).casefold() != getattr(b, c).casefold() for c in campos)


def _palavras(texto: str) -> str:
    sem_acentos = "".join(c for c in unicodedata.normalize("NFKD", texto.casefold())
                         if not unicodedata.combining(c))
    return " ".join(re.findall(r"[^\W_]+", sem_acentos, flags=re.UNICODE))


def direcao_da_peca(peca: PecaCriativa):
    """A direção de arte quando ela declara densidade; None caso contrário."""
    direcao = peca.direcao_de_arte
    return direcao if direcao is not None and direcao.densidade else None


def densidade_derivada(peca: PecaCriativa) -> str:
    """A faixa de densidade da peça, CONTADA a partir do que vai aos pixels.

    ⚠️ Derivada e não declarada, e a lição custou dois lotes. Pedir ao modelo
    que declare `densidade` e depois recusar quando a contagem não bate com o
    rótulo transforma um desacordo de contabilidade em recusa de lote inteiro —
    exatamente o que aconteceu com `fonte_do_texto` antes. O modelo decide
    QUANTO colocar; quem conta é o código, e a contagem não erra.

    O campo `DirecaoDeArte.densidade` sobrevive como INTENÇÃO declarada, útil
    para ler o raciocínio da peça, e nunca como algo a ser conferido.
    """
    blocos = _blocos_de_texto(peca)
    if blocos <= TETO_DE_BLOCOS["minima"]:
        return "minima"
    if blocos <= TETO_DE_BLOCOS["media"]:
        return "media"
    return "alta"


def _blocos_de_texto(peca: PecaCriativa) -> int:
    """Quantos elementos textuais o olho precisa processar nesta peça.

    Conta o que VAI AOS PIXELS, não o que existe no contrato: headline sempre;
    complemento, CTA, selo e ressalva quando preenchidos; e cada item de
    checklist conta um, porque três marcadores são três leituras e não uma.
    """
    direcao = peca.direcao_de_arte
    total = 1  # headline_interna é obrigatória
    total += 1 if peca.complemento_interno else 0
    total += 1 if peca.cta_visual else 0
    if direcao is not None:
        total += 1 if direcao.selo_de_valor else 0
        total += 1 if direcao.qualificador else 0
        total += len(direcao.checklist)
    return total


def _nucleo_da_cor(declarada: str) -> str:
    """O nome da cor, sem o hex e sem o qualificador de tom.

    O operador declara "azul cobalto #1B3FCC" e o modelo escreve "azul cobalto
    saturado no campo de fundo". Comparar a string inteira nunca casaria, e
    comparar só a primeira palavra casaria "azul-marinho" com "azul cobalto" —
    que é justamente a confusão que este portão existe para impedir. O núcleo
    são as duas primeiras palavras alfabéticas: "azul cobalto", "amarelo ovo".
    Uma cor de palavra única ("branco", "verde") vale por si.
    """
    tokens = [t for t in _palavras(declarada).split() if not t.isdigit()]
    tokens = [t for t in tokens if not all(c in "0123456789abcdef" for c in t) or len(t) < 3]
    return " ".join(tokens[:2])


def _cobertura_visual(
    pedido: PedidoDoAgente, saida: SaidaDoAgente, congelados: dict[str, str]
) -> list[str]:
    """O portão que faltava: um lote precisa cobrir território VISUAL.

    `_distancia` mede cinco campos de prosa estratégica. Quatro peças podem ter
    ângulos, hipóteses e mecanismos distintos — passando com folga — e ainda
    assim serem a mesma arte com a foto trocada. Foi o que aconteceu em
    09/09/2026: mesma paleta, mesma tarja no topo, mesmo adolescente de perfil
    com celular, nas quatro. O recibo carimbou BATCH_DIVERSITY_VALID por cima.

    As regras aqui escalam com o tamanho do lote de propósito. Um lote de duas
    peças não tem espaço para cobrir três registros, e exigir isso transformaria
    uma restrição útil numa recusa impossível de satisfazer.

    Peças congeladas ficam de fora da exigência mas CONTAM na cobertura: elas
    ocupam território visual de verdade, e ignorá-las faria o portão pedir
    variação que o lote já tem.
    """
    novas = [p for p in saida.pecas if not _visual_congelado(congelados, p.ref)]
    if not novas:
        return []

    erros: list[str] = []
    sem_eixos = [
        p.ref for p in novas
        if p.direcao_de_arte is not None
        and p.direcao_de_arte.blueprint_version == "volc.art-direction/2"
        and not all((
            p.direcao_de_arte.rota_de_texto,
            p.direcao_de_arte.registro,
            p.direcao_de_arte.presenca_humana,
        ))
    ]
    if sem_eixos:
        erros.append(
            "peças sem os eixos visuais do blueprint v2 "
            f"({', '.join(sorted(sem_eixos))}): declare rota_de_texto, registro e "
            "presenca_humana em cada peça nova"
        )
        return erros

    eixos = [
        (p.ref, p.direcao_de_arte.rota_de_texto, p.direcao_de_arte.registro,
         p.direcao_de_arte.presenca_humana)
        for p in saida.pecas
        if p.direcao_de_arte is not None and p.direcao_de_arte.rota_de_texto
    ]
    if len(eixos) < 2:
        return erros

    vistos: dict[tuple[str, str, str], str] = {}
    for ref, rota, registro, presenca in eixos:
        chave = (rota, registro, presenca)
        if chave in vistos:
            erros.append(
                f"{vistos[chave]} e {ref} têm a mesma rota visual "
                f"({rota} / {registro} / {presenca}): mude a arquitetura de texto, "
                "o registro ou a presença humana de uma delas"
            )
        else:
            vistos[chave] = ref

    total = len(eixos)
    tarjas = sum(1 for _, rota, _, _ in eixos if rota == "campo_cromatico")
    teto = (total + 1) // 2
    if tarjas > teto:
        erros.append(
            f"{tarjas} de {total} peças usam campo_cromatico (teto {teto}): uma faixa "
            "chapada de texto não pode ser a arquitetura de quase todo o lote"
        )
    if total >= 3:
        if not any(presenca == "ausente" for _, _, _, presenca in eixos):
            erros.append(
                "nenhuma peça do lote tem presenca_humana='ausente': falta o eixo "
                "objeto/documento/número, e um lote só de gente testa uma coisa só"
            )
        # Densidade CONTADA, não declarada: o rótulo do modelo não entra aqui.
        densidades = {densidade_derivada(p) for p in saida.pecas}
        if len(densidades) < 2:
            unica = densidades.pop()
            erros.append(
                f"todas as peças do lote têm densidade {unica!r} pela contagem de blocos de "
                "texto. Densidade é variável de teste, não constante: deixe uma peça bem mais "
                "limpa (headline e CTA, sem mais nada) ou uma bem mais densa que as outras."
            )
        distintos = {registro for _, _, registro, _ in eixos}
        if len(distintos) < min(3, total):
            erros.append(
                f"o lote cobre só {len(distintos)} registro(s) ({', '.join(sorted(distintos))}): "
                f"use ao menos {min(3, total)} registros diferentes"
            )
    return erros


def _visual_congelado(caminhos: dict[str, str], ref: str) -> bool:
    """Uma peça cuja direção de arte foi aprovada não é redesenhada por um portão."""
    raiz = f"/pecas/{ref}"
    return (
        "/pecas" in caminhos
        or raiz in caminhos
        or f"{raiz}/direcao_de_arte" in caminhos
    )


def _ancoras_da_arte(pedido: PedidoDoAgente) -> list[str]:
    """As formas aceitáveis de nomear o assunto DENTRO da imagem.

    Precedência deliberada: quando o operador declara `ancora_de_desejo`, é ela
    que a arte precisa dizer, e `assunto_principal` sai da exigência de pixel —
    continua governando congruência, que é outra checagem. Sem âncora declarada,
    `assunto_principal` continua sendo a exigência, exatamente como antes: um
    pedido histórico não muda de significado por causa de um campo novo.
    """
    principal = (pedido.ancora_de_desejo or pedido.assunto_principal or "").strip()
    if not principal:
        return []
    aceitas = [principal]
    for variante in pedido.ancoras_aceitas:
        limpa = variante.strip()
        if limpa and _palavras(limpa) not in {_palavras(a) for a in aceitas}:
            aceitas.append(limpa)
    return aceitas


def _texto_congelado(caminhos: dict[str, str], ref: str) -> bool:
    raiz = f"/pecas/{ref}"
    return ("/pecas" in caminhos or raiz in caminhos or
            all(f"{raiz}/{campo}" in caminhos
                for campo in ("headline_interna", "complemento_interno")))


def validar_saida(pedido: PedidoDoAgente, saida: SaidaDoAgente) -> None:
    erros: list[str] = []
    if saida.project_ref != pedido.project_ref:
        erros.append("project_ref diverge do pedido")
    if saida.fase_concluida != pedido.fase:
        erros.append("fase_concluida diverge da fase pedida")
    if len(saida.pecas) != pedido.quantidade_de_pecas:
        erros.append(
            f"lote contém {len(saida.pecas)} peças; esperado {pedido.quantidade_de_pecas}"
        )

    fatos = {f.ref for f in pedido.fatos_da_oferta}
    regras = {r["id"] for r in carregar_regras()["rules"]}
    estados = {e.ref for e in saida.jornada}
    grupos = {g.ref for g in saida.grupos}
    grupo_por_ref = {g.ref: g for g in saida.grupos}
    copies = {c.ref: c for c in saida.copies_compartilhadas}
    texto_da_saida = saida.model_dump_json().casefold()
    if _ID_OU_SEGREDO_EXTERNO.search(saida.model_dump_json()):
        erros.append("saída contém URL, caminho privado ou identificador bruto de provedor")
    for restricao in pedido.restricoes:
        for termo in restricao.termos_bloqueados:
            if termo.casefold() in texto_da_saida:
                erros.append(f"termo bloqueado por {restricao.ref} apareceu na saída")

    colecoes = {
        "estados": [e.ref for e in saida.jornada],
        "grupos": [g.ref for g in saida.grupos],
        "copies": list(copies),
        "pecas": [p.ref for p in saida.pecas],
    }
    for nome, ids in colecoes.items():
        repetidos = [ref for ref, n in Counter(ids).items() if n > 1]
        if repetidos:
            erros.append(f"{nome} contém refs duplicadas: {', '.join(repetidos)}")

    for ref in saida.diagnostico.fato_refs:
        if ref not in fatos:
            erros.append(f"diagnóstico cita fato inexistente: {ref}")
    for grupo in saida.grupos:
        ausentes = set(grupo.estado_mental_refs) - estados
        if ausentes:
            erros.append(f"{grupo.ref} cita estados inexistentes: {sorted(ausentes)}")
        if not any(peca.group_ref == grupo.ref for peca in saida.pecas):
            erros.append(f"{grupo.ref} não possui nenhuma peça no lote")
    for copy in saida.copies_compartilhadas:
        if copy.group_ref not in grupos:
            erros.append(f"{copy.ref} cita grupo inexistente")
        ausentes = set(copy.fato_refs) - fatos
        if ausentes:
            erros.append(f"{copy.ref} cita fatos inexistentes: {sorted(ausentes)}")

    congelados = {e.caminho: e.valor for e in pedido.elementos_congelados}
    documento = saida.model_dump(mode="json")
    for caminho, valor in congelados.items():
        try:
            atual = resolver_caminho(documento, caminho)
        except CaminhoInvalido:
            erros.append(f"elemento congelado ausente da saída: {caminho}")
            continue
        canonico = json.dumps(atual, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if canonico != valor:
            erros.append(f"elemento congelado foi alterado: {caminho}")

    for peca in saida.pecas:
        motivacoes = getattr(pedido.contexto_da_pagina, "motivacoes_sugeridas", [])
        contexto_motivacional = any(set(m.fato_refs) <= fatos for m in motivacoes)
        raiz = f"/pecas/{peca.ref}"
        peca_congelada = "/pecas" in congelados or raiz in congelados
        if contexto_motivacional and not peca_congelada and peca.big_idea is None:
            erros.append(f"{peca.ref}: falta big_idea; explicite ideia, pergunta, promessa do clique e cena antes de gerar")
        # A arte precisa dizer sobre o que é. O que ela precisa DIZER, porém, é a
        # âncora de desejo quando o operador declarou uma — e não o nome
        # institucional do canal. Ver `PedidoDoAgente.ancora_de_desejo`.
        #
        # Aceitar variantes não afrouxa a contraprova: quem declara o conjunto é
        # o operador, no pedido, antes da resposta. O modelo continua sem poder
        # inventar o sinônimo que o valida.
        aceitas = _ancoras_da_arte(pedido)
        if aceitas and not _texto_congelado(congelados, peca.ref):
            textos_visiveis = (peca.headline_interna, peca.complemento_interno or "")
            palavras_visiveis = [f" {_palavras(texto)} " for texto in textos_visiveis]
            if not any(
                f" {_palavras(ancora)} " in visivel
                for ancora in aceitas
                for visivel in palavras_visiveis
            ):
                esperadas = ", ".join(repr(a) for a in aceitas)
                erros.append(
                    f"{peca.ref}: a imagem não diz sobre o que é. Escreva o assunto na "
                    f"headline_interna ou no complemento_interno usando UMA destas formas: "
                    f"{esperadas}. Escolha a que couber melhor na frase; não empilhe todas "
                    "e não altere elementos congelados."
                )
        # Orçamento de pixel-texto. `contrato.py` permite 160+300+60 = 520
        # caracteres dentro de uma imagem que será lida com ~150 px de largura no
        # feed, e o lote de 09/09/2026 gastou a headline inteira com o nome
        # institucional do canal ("Login no App Jornada do Estudante").
        #
        # ⚠️ Isto é validador e NÃO `max_length` no contrato, de propósito: das 35
        # peças históricas medidas, 49% têm headline acima de 45 caracteres.
        # Apertar o campo recusaria replay de metade do acervo aprovado. Aqui a
        # régua só alcança peça nova e não congelada, que é onde ela deve doer.
        # ⚠️ Este portão NÃO teria pego o lote de 09/09/2026: aquelas quatro
        # headlines tinham 33 a 43 caracteres e 6 a 8 palavras, todas dentro de
        # qualquer orçamento razoável. O defeito delas era EM QUE as palavras
        # foram gastas — o nome do canal — e quem conserta isso é a âncora de
        # desejo, não a régua. O limite aqui existe para outra falha, real e
        # medida no acervo: headlines de até 58 caracteres que viram parágrafo
        # em miniatura de feed.
        # ⚠️ UMA régua, não duas. A primeira versão contava caracteres E palavras,
        # e num lote real a peça "Pé-de-Meia: consulta no app, saque na Caixa" —
        # 47 caracteres, dentro do teto — foi recusada por ter 9 palavras. As duas
        # contagens medem a mesma coisa, então a segunda só cria dupla penalidade
        # sobre uma preferência de estilo. E como o orquestrador tenta duas vezes
        # e falha o LOTE inteiro, uma régua estreita demais não deixa a peça pior:
        # deixa o operador sem peça nenhuma.
        if not _texto_congelado(congelados, peca.ref):
            if len(peca.headline_interna) > 52:
                erros.append(
                    f"{peca.ref}: headline de {len(peca.headline_interna)} caracteres não é "
                    "lida em miniatura de feed. Escreva até cerca de 45; detalhe e ressalva "
                    "vão para a copy externa, não para dentro da imagem."
                )
            if peca.cta_visual and len(peca.cta_visual) > 24:
                erros.append(
                    f"{peca.ref}: cta_visual de {len(peca.cta_visual)} caracteres; "
                    "um CTA de imagem cabe em 2 a 4 palavras."
                )
        # Unidade cromática do assunto. Sem isto, o modelo converge para o azul
        # corporativo mesmo com o prompt mandando o contrário — medido em lote
        # real. Duas cores da família, não uma: uma só vira acento decorativo.
        if pedido.familia_cromatica and not _visual_congelado(congelados, peca.ref):
            direcao = peca.direcao_de_arte
            texto_da_paleta = _palavras(
                f"{direcao.paleta_e_contraste} {direcao.cena} {direcao.tratamento}"
                if direcao else ""
            )
            presentes = [
                cor for cor in pedido.familia_cromatica
                if _nucleo_da_cor(cor) and _nucleo_da_cor(cor) in texto_da_paleta
            ]
            if len(presentes) < 2:
                erros.append(
                    f"{peca.ref}: a peça não usa a família cromática do assunto "
                    f"({', '.join(pedido.familia_cromatica)}). Escreva pelo menos DUAS "
                    "dessas cores em paleta_e_contraste, dizendo em que superfície de "
                    "área grande cada uma aparece — não num botão pequeno."
                )
        # Teto duro de densidade. A FAIXA (minima/media/alta) é DERIVADA da
        # contagem, não conferida contra o que o modelo declarou — ver
        # `densidade_derivada`. O que sobra aqui é o teto: acima de 8 blocos a
        # peça deixa de ser anúncio e vira folheto, em qualquer registro.
        if not _texto_congelado(congelados, peca.ref):
            blocos = _blocos_de_texto(peca)
            if blocos > TETO_DE_BLOCOS["alta"]:
                erros.append(
                    f"{peca.ref}: {blocos} blocos de texto numa peça de feed. Acima de "
                    f"{TETO_DE_BLOCOS['alta']} ninguém lê em miniatura — corte complemento, "
                    "itens de checklist ou selo."
                )

        # Um selo que afirma gratuidade ou valor sem ressalva é propaganda
        # enganosa por omissão (CDC art. 37 §1º) — e, em benefício social, é
        # também o padrão que derruba conta de anunciante. A referência de
        # mercado que motivou este campo traz sempre o par: "100% GRATUITO*" e,
        # logo abaixo, "*conforme critérios do programa". O par é a regra.
        direcao = peca.direcao_de_arte
        if direcao and direcao.selo_de_valor and not _texto_congelado(congelados, peca.ref):
            afirma_valor = _AFIRMA_VALOR.search(direcao.selo_de_valor)
            if afirma_valor and not direcao.qualificador:
                erros.append(
                    f"{peca.ref}: o selo {direcao.selo_de_valor!r} afirma valor ou gratuidade "
                    "sem ressalva. Preencha qualificador com a condição real "
                    "(ex.: 'conforme critérios do programa'); ela vai impressa na arte."
                )
        if peca.group_ref not in grupos:
            erros.append(f"{peca.ref} cita grupo inexistente")
        if peca.estado_mental_ref not in estados:
            erros.append(f"{peca.ref} cita estado mental inexistente")
        else:
            # Existir na jornada não basta: a peça precisa falar com um estado
            # DO SEU grupo. Sem esta contraprova o modelo podia montar uma peça
            # do grupo "quem já conhece" endereçando a dúvida de "quem nunca
            # ouviu falar" — as duas refs são válidas isoladamente, e a
            # incoerência só apareceria depois, na leitura humana do lote.
            grupo_da_peca = grupo_por_ref.get(peca.group_ref)
            if (
                grupo_da_peca is not None
                and peca.estado_mental_ref not in grupo_da_peca.estado_mental_refs
            ):
                erros.append(
                    f"{peca.ref} usa estado mental {peca.estado_mental_ref} "
                    f"que não pertence a {peca.group_ref}"
                )
        copy = copies.get(peca.shared_copy_ref)
        if copy is None:
            erros.append(f"{peca.ref} cita copy compartilhada inexistente")
        elif copy.group_ref != peca.group_ref:
            erros.append(f"{peca.ref} usa copy de outro grupo")
        if peca.formato not in pedido.formatos_permitidos:
            erros.append(f"{peca.ref} usa formato não permitido: {peca.formato}")
        fatos_ausentes = set(peca.fato_refs) - fatos
        if fatos_ausentes:
            erros.append(f"{peca.ref} cita fatos inexistentes: {sorted(fatos_ausentes)}")
        regras_ausentes = set(peca.rule_refs) - regras
        if regras_ausentes:
            erros.append(f"{peca.ref} cita regras inexistentes: {sorted(regras_ausentes)}")
        if contem_metadado_operacional(peca):
            erros.append(f"{peca.ref} vazou metadado operacional na peça")

    # Toda dupla precisa diferir em três dimensões estratégicas. O corpus chama
    # distâncias 1–2 de cosméticas e recomenda concentrar exploração em 3–5.
    for i, atual in enumerate(saida.pecas):
        for outra in saida.pecas[i + 1 :]:
            if _distancia(atual, outra) < 3:
                erros.append(f"{atual.ref} e {outra.ref} são variações cosméticas")

    erros.extend(_cobertura_visual(pedido, saida, congelados))

    if erros:
        raise SaidaCriativaInvalida(erros[:30])
