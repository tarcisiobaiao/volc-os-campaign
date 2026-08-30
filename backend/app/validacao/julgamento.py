"""O lado que nenhuma API mede — e agora ele CONTA em vez de rotular.

## Um prompt no lugar de dois

Antes eram duas chamadas com dois documentos: um classificador de 648 linhas
pedindo cinco rótulos ordinais, e um portão dedicado de 155 linhas perguntando
um booleano. O portão foi extraído porque, enterrado no item 2 de nove eixos,
ele perdia o verdadeiro positivo em 4 de 5 execuções.

Com a ficha, o portão **é derivado das contagens** — `ramos_de_acao <= 1` e
`condicoes_pessoais == 0` e nada a decidir depois. Então os dois documentos
viram um: `ficha_de_resposta.md`, 8 observáveis e a resposta literal.

O que sobra para o LLM é o que só ele faz: ler a situação e escrever a resposta
que a pessoa veio buscar. O que era julgamento ordinal virou aritmética em
`ficha.py`, onde não oscila.

## Duas passadas, comparando CONTAGEM

A régua assimétrica continua (`2/2 → portão`, `1/2 → limítrofe`, `0/2 → sem
portão`) e continua medindo desacordo em vez de votar. O que mudou é o objeto
comparado: antes eram dois vereditos, agora são duas fichas de oito números.

Isso responde a crítica que as duas auditorias fizeram ao meu teste anterior. Eu
tinha concluído que "a evidência acompanha o veredito, logo mover o teste para
código não ajuda" — mas o modelo inventava a evidência na mesma respiração em
que a julgava. Com a consulta congelada pelo PAA e a contagem separada da
derivação, a evidência passa a ser comparável de verdade.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any, Dict, List, Optional, Sequence

from app.config import Settings
from app.llm import get_engine
from app.llm.json_defensivo import extract_json
from app.validacao.ficha import (Ficha, agregar, campos_do_widget, derivar,
                                 formato_da_pergunta, formatos_da_entidade,
                                 veredito_do_portao)

log = logging.getLogger("pautador.validacao.ficha")

PROMPT = (pathlib.Path(__file__).resolve().parents[1]
          / "motor_pautas" / "prompts" / "ficha_de_resposta.md")

# Os três eixos que saem da ficha, por derivação. Nenhum é declarado pelo LLM.
DERIVADOS_DA_FICHA = ("ignorancia", "engajamento", "opacidade")
# O PAA devolve tipicamente 4, e o teto é 4 — não 5.
#
# A cauda do bloco não é mais do mesmo objeto. A partir da quinta ou sexta, o
# PAA costuma derivar para suporte operacional ("qual o telefone do órgão?",
# "como recuperar a senha do Gov.br?"), exceção local ou entidade correlata.
# Misturar isso com as perguntas de cabeça contamina o share numa direção que
# não dá para prever: pergunta de telefone esgota e empurra para o portão;
# pergunta correlata ramifica e resgata o tema por fora do próprio assunto.
#
# Não é que a cauda seja ruidosa — é que ela é OUTRO OBJETO. E a unidade deste
# motor é a entidade lida pelas perguntas que as pessoas fazem SOBRE ELA.
MAX_PERGUNTAS = 4


def carregar_prompt() -> str:
    return PROMPT.read_text(encoding="utf-8")


def _perguntas(c: Any) -> List[str]:
    """As perguntas do PAA. Lista VAZIA quando não há PAA — sem fallback.

    ## O fallback que fabricava o objeto, e por que ele saiu

    Isto terminava em `or [c.termo]`: sem bloco de perguntas do Google, o código
    injetava UMA pseudo-pergunta que era a própria string de busca. Aí o modelo
    recebia `"consultar CPF situação cadastral"` — que não é pergunta — escrevia
    a resposta seca óbvia para um keyword nu, e os TRÊS eixos julgados da
    entidade saíam desse item fabricado.

    Foi medido custando um achado: `consultar CPF` apareceu em dois lotes com
    100% das perguntas se esgotando, e foi reportado como o extremo limpo do
    motor. O cache mostra `[]` nas duas rodadas. O 1,00 era n=1 sobre uma
    não-pergunta, e a conclusão inteira era circular.

    O piso de N em `ficha.py` limita o ESTRAGO (n=1 não dispara portão), mas não
    resolve a origem: o item continuava sendo inventado e continuava produzindo
    nível de eixo. Sem PAA, a resposta honesta é não ler a entidade. Os eixos
    ficam `ausente` com motivo `paa_ausente`, que é diferente de `ficha_invalida`
    — um é o Google que não devolveu, o outro é o modelo que errou o formato.
    """
    prova = getattr(c, "prova_cabecas", None) or {}
    perguntas = [q for q in (prova.get("paa_perguntas") or []) if isinstance(q, str)]
    cabeca = getattr(c, "cabeca_editorial", None)
    if cabeca and cabeca not in perguntas:
        perguntas.insert(0, cabeca)
    return perguntas[:MAX_PERGUNTAS]


def _entrada(cards: Sequence[Any]) -> Dict[str, Any]:
    """O bloco `temas`, com a consulta CONGELADA e as medições como fato.

    `consulta_fixa` é o que tira do modelo a escolha do objeto. Ela vem do bloco
    "As pessoas também perguntam" do Google, e é a mudança que separa "o modelo
    oscila julgando" de "o modelo oscila escolhendo o que julgar" — a confusão
    que as duas auditorias apontaram no meu experimento anterior.
    """
    temas = []
    for c in cards:
        if not _perguntas(c):
            continue        # sem objeto para ler, a entidade não vai ao modelo
        medido = {nome: c.eixos[nome].nivel
                  for nome in ("volume", "reposicao", "vacuo", "formato_consumo", "densidade")
                  if c.eixos.get(nome) and c.eixos[nome].nivel}
        temas.append({
            "id": f"opp{c.opportunity_id}",
            "termo": c.termo,
            "pais": c.country_code or "??",
            "descricao": (getattr(c, "descricao", "") or "")[:400],
            # TODAS as perguntas do PAA, não uma. A entidade não tem uma
            # pergunta: `DIRPF` tem "quando libera" (data), "quem precisa
            # declarar" (três condições) e "simplificada ou completa" (uma
            # decisão). Congelar a primeira matou o tema mais rico do lote.
            "perguntas": _perguntas(c),
            "medido_pela_api": medido or None,
        })
    return {"temas": temas}


async def _uma_passada(cards: Sequence[Any], *, settings: Settings,
                       engine: Optional[str], model: Optional[str]
                       ) -> Dict[str, Dict[str, Ficha]]:
    motor = get_engine(settings, engine, model)
    cliente = getattr(motor, "client", None)
    if cliente is None:
        log.warning("engine sem cliente de texto — nenhuma ficha")
        return {}
    bruto = await cliente.complete(
        carregar_prompt(),
        json.dumps(_entrada(cards), ensure_ascii=False, indent=1))
    dados = extract_json(bruto)

    fora: Dict[str, Dict[str, Ficha]] = {}
    for item in (dados.get("temas") or []):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        por_pergunta: Dict[str, Ficha] = {}
        for bruta in (item.get("fichas") or []):
            if not isinstance(bruta, dict):
                continue
            f = Ficha.de_json(bruta)
            pergunta = str(bruta.get("pergunta") or "").strip()
            if f is None or not pergunta:
                # Ficha meia não vira eixo: contagem faltante entraria na conta
                # com cara de medida.
                log.info("ficha recusada em %s / %r", item.get("id"), pergunta[:60])
                continue
            por_pergunta[pergunta] = f
        fora[str(item["id"])] = por_pergunta
    return fora


async def ler_fichas(cards: Sequence[Any], *, settings: Settings,
                     engine: Optional[str] = None, model: Optional[str] = None,
                     passadas: int = 3) -> Dict[int, Dict[str, Any]]:
    """`{opportunity_id: {"niveis", "ficha", "comparacao", "porques", "fonte"}}`.

    ## Três passadas, e a regra é UNANIMIDADE

    Eram duas. Virou três porque a confiabilidade do instrumento foi medida com
    input fixo (mesmas entidades, mesmo PAA em cache, mesmo prompt, 3 execuções,
    42 perguntas), pelo AC1 de Gwet — que é a métrica correta aqui, porque kappa
    castiga escala enviesada e um portão é enviesado por desenho:

        ignorancia   0,81      tensao      0,76
        opacidade    0,64      engajamento 0,64

    É bom o bastante para decidir e longe de perfeito. Com 3 passadas, o
    orquestrador só aceita o veredito quando as três concordam; qualquer
    divergência vira `limitrofe`, que é o estado que manda o humano olhar.

    Isso troca COBERTURA por CONFIABILIDADE de propósito. O operador publica 2 a
    3 funis por mês: cobrir menos candidatos com veredito firme vale mais que
    cobrir todos com veredito que muda na re-execução.

    Custo: uma chamada a mais por LOTE, não por card. US$ 0,01.
    """
    if not cards:
        return {}

    rodadas: List[Dict[str, Optional[Ficha]]] = []
    for _ in range(max(1, passadas)):
        rodadas.append(await _uma_passada(cards, settings=settings,
                                          engine=engine, model=model))

    motor = get_engine(settings, engine, model)
    fonte = f"{getattr(motor, 'name', '?')}:{getattr(motor, 'model', '?')}"

    fora: Dict[int, Dict[str, Any]] = {}
    for c in cards:
        ident = f"opp{c.opportunity_id}"
        if not _perguntas(c):
            fora[c.opportunity_id] = {
                "niveis": {}, "entidade": None, "fonte": fonte,
                "motivo": "paa_ausente",
                "comparacao": {"comparavel": False,
                               "motivo": "SERP sem bloco de perguntas — "
                                         "entidade não lida, e não reprovada"}}
            continue
        por_passada = [r.get(ident) or {} for r in rodadas]
        entidades = [agregar(p) for p in por_passada if p]
        vivas = [e for e in entidades if e is not None]
        if not vivas:
            fora[c.opportunity_id] = {"niveis": {}, "entidade": None, "fonte": fonte,
                                      "comparacao": {"comparavel": False,
                                                     "motivo": "nenhuma ficha válida"}}
            continue

        primeira = vivas[0]
        shares = [e.share_dado_unico for e in vivas]
        # As passadas são comparadas pelo SHARE, que é o que decide o portão —
        # não pelos oito números de cada pergunta. Divergir em `fontes_oficiais`
        # de uma pergunta sem mover o share é ruído; mover o share é a entidade
        # sendo lida de outro jeito.
        vereditos = [veredito_do_portao(e.share_dado_unico, len(e.fichas))
                     for e in vivas]

        # ── concordância POR PERGUNTA, que é a confiabilidade de verdade ────
        #
        # O veredito da entidade pode bater por compensação: duas perguntas
        # trocando de lado mantêm o share e escondem que o instrumento derrapou.
        # Isto mede o que de fato aconteceu, pergunta a pergunta, e vai gravado
        # em toda evidência — é o número que dá para acompanhar ao longo do
        # tempo sem repetir o experimento de calibração.
        por_q: Dict[str, set] = {}
        for e in vivas:
            for q, f in e.fichas:
                por_q.setdefault(q, set()).add(derivar(f)["engajamento"])
        estaveis = [q for q, niveis in por_q.items() if len(niveis) == 1]
        concordancia = (round(len(estaveis) / len(por_q), 3) if por_q else None)
        fora[c.opportunity_id] = {
            "niveis": primeira.niveis,
            "entidade": {
                "share_dado_unico": primeira.share_dado_unico,
                "distribuicao": primeira.distribuicao,
                "pergunta_mais_rica": primeira.pergunta_mais_rica,
                "n_perguntas": len(primeira.fichas),
                "tensao_dominante": primeira.tensao_dominante,
                "distribuicao_de_tensao": primeira.distribuicao_de_tensao,
                "share_com_tensao": primeira.share_com_tensao,
                "intensidade": primeira.intensidade,
                "citacoes_conferidas": primeira.citacoes_conferidas,
                "n_citacoes": primeira.n_citacoes,
                "stake_sem_prova": primeira.stake_sem_prova,
                # A prescrição de formato: propriedade da PÁGINA, não da
                # entidade. Não entra em `posicionar()` e não move índice.
                "formatos": formatos_da_entidade(dict(primeira.fichas)),
                "perguntas": [
                    {"pergunta": q, "resposta_literal": f.resposta_literal,
                     "engajamento": derivar(f)["engajamento"], "tensao": f.tensao,
                     "ramos": f.ramos_de_acao, "condicoes": f.condicoes_pessoais,
                     "decide_depois": f.decisao_apos_resposta,
                     # ⚠️ SEM ESTA LINHA O ROTEADOR DE FORMATO NÃO EXISTE.
                     # `oficial_fecha_sozinho` é o VETO do roteador — é ele que
                     # separa "dá para fazer a ferramenta" de "o balcão oficial
                     # já faz e o seu widget não adiciona nada". Ele era contado
                     # e jogado fora; nenhum dos desenhos do painel notou.
                     "oficial_fecha_sozinho": f.oficial_fecha_sozinho,
                     "formato": formato_da_pergunta(f),
                     "campos_do_widget": campos_do_widget(f),
                     "trechos_citados": dict(f.trechos_citados),
                     "citacoes_conferem": f.citacoes_conferem(),
                     # a pergunta sobreviveu às N passadas com o mesmo nível?
                     "estavel": q in estaveis}
                    for q, f in primeira.fichas
                ],
            },
            "porques": dict(primeira.fichas[0][1].porques) if primeira.fichas else {},
            "comparacao": {
                "comparavel": len(vivas) > 1,
                "n_passadas": len(vivas),
                "shares": shares,
                "vereditos": vereditos,
                # UNANIMIDADE: com 3 passadas, `estavel` só é verdadeiro quando
                # as três dão o mesmo veredito. É o que o orquestrador exige
                # antes de aceitar a decisão.
                "estavel": len(set(vereditos)) == 1,
                "concordancia_por_pergunta": concordancia,
                "perguntas_instaveis": [q for q in por_q if q not in estaveis],
            },
            "fonte": fonte,
        }
    return fora
