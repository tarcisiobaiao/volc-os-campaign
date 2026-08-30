"""
Portão de LEITURA — o segundo eixo da descoberta, irmão de `scoring.py`.

    arbitrage_score   volume × eCPM ÷ concorrência          →  O MERCADO PAGA?
    reading gate      ignorância · engajamento · opacidade  →  A PESSOA LÊ?

Os dois NÃO se substituem. Medidos nas mesmas 20 entidades de finanças/Brasil, a
correlação de Spearman entre os ranqueamentos foi −0,092: não medem a mesma
coisa, e é por isso que o segundo acrescenta. Onde discordam é onde há decisão a
tomar.

## Por que só três eixos, e por que agora

O motor (`app.motor_pautas.espaco`) mede em 10 eixos. Sete deles — volume,
spread, vácuo, densidade… — são ESTIMATIVA DE QUANTIDADE, e na descoberta toda
quantidade é palpite: o próprio prompt pede "melhor estimativa de volume de
busca mensal". A mineração real só acontece quando o card é arrastado no Kanban.

Os três que usamos aqui não estimam quantidade — CLASSIFICAM A FORMA DA
PERGUNTA. O modelo erra ao adivinhar "1,8 milhão de buscas"; não erra ao dizer
que "qual o desconto da cota única do IPVA" é uma resposta que cabe num número.
Misturar os sete palpites com as três classificações diluiria as boas nas ruins.

## ⚠️ ISTO NÃO BARRA NADA. É SUGESTÃO. (rebaixado por medição, não por opinião)

Nasceu como PORTÃO ANTES DE MINERAR. **A justificativa econômica era falsa**, e
isso bastava para matá-lo sem teste nenhum: a sondagem custa ~US$ 0,25 por ciclo
(`motor_pautas/sensores/dataforseo.py`: US$ 0,06/tarefa, até 1000 keywords),
enquanto um falso negativo custa uma oportunidade inteira. Economia legítima fica
ENTRE a sondagem e os quinze dias de produção — nunca antes da sondagem.

O teste veio depois e concordou. Duas rodadas idênticas (mesmo prompt, país,
nicho e contagem, ambas dry), medindo se a MESMA entidade recebe o MESMO rótulo.
O acaso aqui não é 1/5: é a chance de dois sorteios coincidirem dadas as
marginais de cada rodada, `Σ p_A(i)·p_B(i)`.

    1 frase por entidade   2 de  6 = 33,3%   acaso 23,5%   p = 0,43
    3 frases + moda        6 de 12 = 50,0%   acaso 29,8%   p = 0,11
    critério declarado ANTES do teste: >= 83%    P(6 de 12 | 83%) = 0,0088

Ou seja: a moda de três subiu, mas **nem a 6 de 12 se distingue do acaso** (p =
0,11, n = 12) — e as duas medições são fortemente INCOMPATÍVEIS com o limiar
declarado. Não é "sinal fraco": é ausência de evidência de sinal, com evidência
contra o limiar.

⚠️ Uma medida que NÃO é evidência disto, e que eu cheguei a citar como se fosse:
só 2 das 43 entidades tiveram as três frases concordando entre si. Parece
dramático, mas o acaso para três iguais, dadas as mesmas marginais, é 12,5% — o
medido (4,7%) está ABAIXO do acaso, e por desenho: o prompt manda escrever três
perguntas DIFERENTES. Diversidade interna é o pedido sendo atendido, não ruído.
A evidência real é só a instabilidade do rótulo ENTRE rodadas.

O que NÃO está errado: o mapeamento frase->rótulo, apertado por quatro rodadas,
segurou (a classe de erro "quem age é a instituição" morreu, 0 casos em 8). O que
não existe é a unidade de análise: "o engajamento do CDB" não é uma quantidade —
o CDB tem uma pergunta comparativa, uma condicional e uma de dado único, e as
três estão certas. Não há amostragem que faça uma distribuição multimodal
convergir, e mais prompt não alcança isso.

Um portão errado metade das vezes é PIOR que portão nenhum: bloqueia tema bom em
silêncio e ainda cria confiança falsa. Então `bloqueado` sai sempre `False`, e o
que sobra é `motivo` — texto para um humano ler e decidir.

Isto é ponto de parada declarado, não pendência. A condição de retomada — quatro
itens, nenhum deles satisfeito por outra rodada de prompt — está no comentário
logo abaixo de `BARRA_DE_VERDADE`.
"""
from __future__ import annotations

import unicodedata
from collections import Counter
from typing import Any, Dict, List, Optional

from app.motor_pautas.espaco import (ENGAJAMENTO, ENGAJAMENTO_LEGADO,
                                     IGNORANCIA, OPACIDADE, posicionar)

# Quem define portão é o MOTOR (`espaco.PORTOES`), não este módulo. `Eixo.e_portao`
# já resolve, nativamente, as três coisas de que precisamos: portão é o par
# (eixo, nível) e não o eixo inteiro; eixo não declarado nunca dispara o seu
# portão; e `spread`/`volume` se recusam a matar tema com palpite (`medidos`).
#
# Por isso NÃO passamos `medidos=` daqui: na descoberta volume e spread são
# estimativa do LLM, e o padrão do motor (ausente = estimativa) é justamente o
# que impede um número inventado de barrar uma pauta. Também não declaramos
# `formato_consumo` — ele precisa de dado por país que não existe nesta fase, e
# declarar portão no chute é pior que não declarar.

# O portão BARRA? Não. Rebaixado a sugestão por medição — ver o cabeçalho do
# módulo. Fica como constante, e não como código apagado, porque a pergunta
# "por que isto não barra?" tem de ter resposta no lugar onde alguém vai
# procurar.
BARRA_DE_VERDADE = False

# O que precisa existir para religar `BARRA_DE_VERDADE`. Está aqui, e não num
# README ou num ticket, porque quem for religar vai abrir ESTE arquivo — e porque
# "intenção de medir" não é condição, é lembrete.
#
# A unidade NÃO é a entidade nem a página isolada: é
# CLUSTER DE CONSULTA × PÁGINA × PAÍS × PERÍODO.
#
#   1. Registrar por unidade: consulta/cluster, página, clique pago, CPC,
#      pageviews, impressões VIEWABLE e receita.
#   2. EXPOSIÇÃO INICIAL COMUM — mesmo número de cliques por unidade, ou regra
#      sequencial fixada antes de olhar o resultado. Sem isso o `spend` codifica
#      a decisão de quem investiu, que foi exatamente como a versão ajustada do
#      motor se contaminou (AUC 0,971 só com spend — ver `motor_pautas/espaco`).
#   3. Avaliar RECEITA POR CLIQUE ÷ CUSTO POR CLIQUE e SEGUNDOS VIEWABLE POR
#      CLIQUE, em holdout de ENTIDADES (não de páginas — páginas da mesma
#      entidade vazam entre treino e teste). Nunca lucro absoluto: lucro embute
#      verba.
#   4. SÓ ENTÃO testar se a participação de `dado_unico` acrescenta algo ALÉM de
#      CPC, RPM e volume. Se não acrescentar, o portão morre de vez em vez de
#      ficar esperando.
#
# Outra rodada de prompt NÃO satisfaz nenhum destes quatro itens.


def _canon(valor: Any, escala: Dict[str, Any]) -> Optional[str]:
    """Rótulo do LLM -> nível canônico do motor, ou None.

    Dobra acento e separador (`diagnóstico` -> `diagnostico`, `dado único` ->
    `dado_unico`) pelo mesmo motivo que `scoring._norm` dobra "Muito alto" em
    `very_high`: o vocabulário é fechado, mas a grafia do modelo não é, e
    descartar `ilegível` como "fora do vocabulário" apagaria um portão por causa
    de um til. O que NÃO existe aqui é aproximação semântica: rótulo que não cai
    exatamente num nível vira dado ausente, nunca no nível "mais parecido".
    """
    if not isinstance(valor, str):
        return None
    t = unicodedata.normalize("NFD", valor.strip().lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = "_".join(t.replace("-", " ").split())
    if t in escala:
        return t
    # ── a ponte do vocabulário aposentado ───────────────────────────────────
    #
    # `engajamento` colapsou de cinco níveis para dois porque os cinco não
    # discriminaram (concordância teste-reteste de 45% com input fixo, contra
    # 67% do binário). `espaco.ENGAJAMENTO_LEGADO` foi escrito NA MESMA HORA
    # para ler linha já gravada — e não foi ligado aqui.
    #
    # O custo do esquecimento: todo card cujo `engajamento_level` fosse um dos
    # cinco antigos virava dado ausente, e `posicionar()` levantava
    # `ValueError: nível 'condicional' não existe`. Nove testes caíram numa
    # suíte que eu não estava rodando.
    #
    # A ponte vale só para LER o que já existe. `posicionar()` continua
    # recusando o vocabulário antigo na ENTRADA, que é o que deixa claro que a
    # escala mudou em vez de conviverem duas.
    if escala is ENGAJAMENTO:
        return ENGAJAMENTO_LEGADO.get(t)
    return None


def respostas_validas(opp: Dict[str, Any]) -> List[Dict[str, str]]:
    """As frases do campo `respostas`, com rótulo canônico. Descarta as tortas.

    Cada item é `{"frase": str, "engajamento_level": <canônico>}`.

    ⚠️ MUDARAM DE FUNÇÃO. Nasceram como três VOTOS para um rótulo; como votos não
    servem (a distribuição é multimodal e não há para onde convergir — ver o
    cabeçalho). O que elas são de fato é melhor: **três perguntas legítimas e
    distintas sobre a mesma entidade**, que é matéria-prima de arquitetura de
    funil — uma página de solução por pergunta. Na UI chamam-se PERGUNTAS
    CANDIDATAS, e um humano escolhe quais viram página.

    ⚠️ E por isso NÃO alimentam score nenhum. O mesmo LLM que inventa as
    perguntas pontuando as próprias invenções é circuito fechado de opinião, não
    medição. Não derive `funnel_score` nem nada parecido daqui.
    """
    bruto = opp.get("respostas")
    if not isinstance(bruto, list):   # jsonb NULL, string, número: nada de válido
        return []
    out: List[Dict[str, str]] = []
    for r in bruto:
        if not isinstance(r, dict):
            continue
        nivel = _canon(r.get("engajamento_level"), ENGAJAMENTO)
        frase = r.get("frase")
        if nivel and isinstance(frase, str) and frase.strip():
            item = {"frase": frase.strip(), "engajamento_level": nivel}
            # `ignorancia` POR PERGUNTA (v7_17): o buraco de conhecimento de quem
            # faz AQUELA pergunta. É o eixo com a melhor evidência (+0,194) e no
            # nível da pergunta ele é bem definido — no nível da entidade não era.
            # Opcional: ausente não descarta a pergunta, só não acompanha ela.
            ign = _canon(r.get("ignorancia_level"), IGNORANCIA)
            if ign:
                item["ignorancia_level"] = ign
            out.append(item)
    return out


def moda_engajamento(respostas: List[Dict[str, str]]) -> Optional[str]:
    """A moda dos rótulos das frases; empate triplo -> o do MEIO da escala.

    Calculada aqui, em Python, e não pedida pronta ao modelo: pedir a moda é
    pedir aritmética a quem já erra a classificação, e o valor perderia a
    auditoria contra as três frases persistidas. O campo que o modelo declara
    fica como fallback quando `respostas` não vem.

    O desempate pelo meio da escala tem uma consequência que interessa ao
    portão: `dado_unico` é o MENOR valor da escala, então nunca é o do meio de
    três distintos. Logo `moda == dado_unico` implica que pelo menos duas das
    três frases disseram `dado_unico` — que é exatamente a regra "o portão só
    fecha se a MAIORIA disser dado_unico", sem precisar de um segundo teste.
    """
    niveis = [r["engajamento_level"] for r in respostas]
    if not niveis:
        return None
    contagem = Counter(niveis)
    topo = max(contagem.values())
    empatados = [n for n, c in contagem.items() if c == topo]
    if len(empatados) == 1:
        return empatados[0]
    # empate: ordena pela força do eixo e pega o do meio (ímpar) ou o mais baixo
    # da metade superior (par) — sempre um valor que ALGUÉM declarou.
    ordenados = sorted(empatados, key=lambda n: ENGAJAMENTO[n][0])
    return ordenados[len(ordenados) // 2]


def canonical_levels(opp: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Os três níveis já canonizados (ou None). Público porque quem PERSISTE
    quer gravar o rótulo limpo, e quem depura quer saber qual dos três faltou.

    `engajamento` sai da MODA das três frases quando elas existem; o campo solto
    do modelo é só o fallback. Uma frase só é uma amostra de tamanho 1 de um
    espaço que o modelo sorteia a cada rodada — medido: a mesma entidade mudou
    de rótulo em 4 de 6 casos entre duas rodadas idênticas.
    """
    respostas = respostas_validas(opp)
    return {
        "ignorancia": _canon(opp.get("ignorancia_level"), IGNORANCIA),
        "engajamento": moda_engajamento(respostas) or _canon(opp.get("engajamento_level"), ENGAJAMENTO),
        "opacidade": _canon(opp.get("opacidade_level"), OPACIDADE),
    }


def frase_representativa(opp: Dict[str, Any], nivel: Optional[str]) -> Optional[str]:
    """A frase que sustenta o rótulo vencedor — é ela que o card mostra.

    Derivada, não pedida: pedir uma quarta frase "resumo" ao lado das três seria
    dar ao modelo a chance de escrever uma que não corresponde a rótulo nenhum.
    """
    for r in respostas_validas(opp):
        if r["engajamento_level"] == nivel:
            return r["frase"]
    bruto = opp.get("resposta_em_uma_frase")
    return bruto.strip() if isinstance(bruto, str) and bruto.strip() else None


_NEUTRO: Dict[str, Any] = {
    "bloqueado": False,
    "motivo": None,
    "forca": None,
    "quadrante": None,
}


def compute_reading_gate(
    opp: Dict[str, Any], *, termo: str = "", country_code: Optional[str] = None
) -> Dict[str, Any]:
    """Portão de LEITURA. Irmão de `compute_entity_score`.

    O score diz se o mercado paga. Este diz se a pessoa fica na página o
    suficiente para o anúncio ser visto.

    Devolve ``{"bloqueado": bool, "motivo": str|None, "forca": float|None,
    "quadrante": str|None}``. Campos ausentes -> não bloqueia (bloquear por
    falta de dado seria pior que não opinar).

    **`bloqueado` sai sempre `False`** — ver `BARRA_DE_VERDADE` e o cabeçalho do
    módulo. `motivo` continua saindo quando os portões do motor disparam: é a
    SUGESTÃO que um humano lê antes de arrastar o card.

    `termo` e `country_code` são só rótulos da posição — não entram em conta
    nenhuma. Existem para que o motor e os logs digam de QUEM é o veredito.

    Sobre `forca` (persistida como `reading_strength`): média geométrica de
    ignorancia × engajamento × opacidade.

    **NUNCA ordene o board por ela.** Ela é derivada dos MESMOS rótulos cuja
    estabilidade entre rodadas foi medida em 33% (1 frase) e 50% (3 frases),
    contra 24-30% de acaso — média de três rótulos instáveis é ruído com quatro
    casas decimais, e quatro casas decimais parecem precisão. Serve para leitura
    humana do caso, ao lado das perguntas candidatas. Ordenação do board é por
    `score` (arbitragem), que é o que ela é hoje.

    **NÃO é o índice de 10 eixos do motor; não comparar com valores de
    `motor_pautas.Posicao.indice`.** São contas
    diferentes e a diferença é grande: com um portão disparado o índice do motor
    é **exatamente 0,0** (portão é decisão binária: não construa), enquanto aqui
    o mesmo `dado_unico` entra diluído na média e devolve ~0,37. Fora do portão,
    o índice do motor exige DUAS famílias e sai `None` nesta fase — os nossos
    três eixos são todos `demanda_humana`. O nome é a única defesa contra alguém
    somar os dois daqui a três meses. Também não se compara com
    `arbitrage_score` — esse responde outra pergunta.
    """
    niveis = canonical_levels(opp)
    ign, eng, opa = niveis["ignorancia"], niveis["engajamento"], niveis["opacidade"]

    try:
        p = posicionar(
            termo or (opp.get("canonical_name") or "?"),
            pais=(country_code or "??"),
            ignorancia=ign,
            engajamento=eng,
            opacidade=opa,
        )
    except ValueError:
        # o motor recusou um nível que passou por `_canon` — só acontece se as
        # escalas mudarem debaixo daqui. Não opinar é a resposta certa.
        return dict(_NEUTRO)

    # Cada portão depende SÓ do eixo que o define — e quem garante isso é o
    # motor, não uma cópia da regra aqui:
    #   engajamento ausente -> o portão de engajamento não pode disparar
    #   ignorancia ausente  -> o portão de ignorância não pode disparar
    #   opacidade ausente   -> afeta SÓ a `forca`, nunca um portão (ela não
    #                          participa de portão nenhum)
    # Deixar `opacidade` derrubar o portão em silêncio era o pior tipo de falha:
    # a que parece funcionamento normal.
    disparou = bool(p.portoes_disparados())
    # ...e o portão INFORMA, não barra: reprovou o critério de estabilidade
    # declarado antes do teste (6/12 contra >=83%). Ver o cabeçalho do módulo.
    bloqueado = disparou and BARRA_DE_VERDADE
    motivo = None
    if disparou:
        # a frase legível é a que o próprio motor emite — reescrevê-la aqui seria
        # deixar as duas versões divergirem na primeira revisão do motor.
        motivo = " ".join(a for a in p.alertas if a.startswith("PORTÃO")) or None

    forca = p.familia("demanda_humana")
    return {
        "bloqueado": bloqueado,
        "motivo": motivo,
        "forca": round(forca, 4) if forca is not None else None,
        # "descartar" quando um portão dispara (o motor põe o portão ANTES do
        # quadrante, então ele não contradiz mais o `bloqueado`); "indefinido"
        # no resto desta fase, porque o quadrante cruza LEITURA × MERCADO e a
        # família ECONOMIA só existe depois da mineração.
        "quadrante": p.perfil(),
    }
