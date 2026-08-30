"""A prescrição — de "célula vazia" para "faz isso, neste país, agora".

O grafo mostra 404 células vazias. Isso é diagnóstico, não instrução. Este
módulo faz a travessia: escolhe quais valem trabalho, diz por quê, e nomeia o
que falta descobrir.

## Os dois tipos de prescrição, e a diferença importa

**TRANSPOR** — a célula está vazia e o arquétipo se provou em outros países.
Sabemos a tensão, sabemos o spread do mercado; **não sabemos o nome local**. A
prescrição não é "escreve sobre isso" — é *"descubra como se chama o
`fundo_verba_trabalhista` no Canadá francófono"*. É uma pergunta fechada, com
resposta verificável, e é exatamente o que uma LLM com busca faz bem.

**ATIVAR** — a entidade já é conhecida e um evento a está tocando agora. Aqui a
prescrição é direta, porque não falta descobrir nada: falta escrever.

Misturar os dois seria o erro que faz painel virar ruído. Uma pede pesquisa, a
outra pede produção, e quem lê precisa saber qual é qual antes de abrir a lista.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from .. import espaco as E
from .. import psique as P
from .modelo import VAZIO, Grafo

# Tensão → nível de ignorância. A ponte entre a biblioteca de padrões e o eixo
# do espaço. Vem do achado do teste cego: o que faz virar página é o buraco de
# conhecimento, não a força da pressão.
TENSAO_IGNORANCIA = {
    "dinheiro_esquecido": "nao_sei_se_existe",
    "protecao_familiar":  "nao_sei_se_sirvo",
    "ascensao":           "nao_sei_se_sirvo",
    "acesso_negado":      "nao_sei_por_que_falhou",
    "medo_de_perder":     "so_falta_um_dado",
    "obrigacao_legal":    "sei_o_que_fazer",
    "urgencia_de_renda":  "nao_sei_se_sirvo",
}

# ⚠️ O PRIOR DE `engajamento` FOI REMOVIDO, E NÃO É UM ESQUECIMENTO.
#
# Ele mapeava tensão → ramificação típica: `medo_de_perder` -> `dado_unico`,
# `ascensao` -> `sequencial`, e assim por diante. Duas coisas o derrubaram.
#
# A primeira: a escala colapsou de cinco níveis para dois. Medida em dois lotes
# de 4 perguntas por entidade, ela nunca separou o meio — o nível dominante
# trocou de `diagnostico` (62,5%) para `condicional` (76,2%) só mudando a
# amostra. Sobraram `sustenta` e `dado_unico`, e um prior de sete tensões para
# dois estados não carrega informação que valha o risco.
#
# A segunda, mais grave: `dado_unico` é PORTÃO — zera o índice do tema. E
# `engajamento` não está em `PORTOES_EXIGEM_MEDICAO`, então esse prior matava
# tema por ARQUÉTIPO, sem ninguém ter lido uma resposta. Um portão disparado por
# analogia é exatamente o que a validação existe para não fazer.
#
# Fica em branco, como o docstring desta função já manda para o que não foi
# observado. Quem preenche é `validacao/ficha.py`, contando sobre a resposta que
# escreveu. `cobertura` denuncia a ausência, que é o comportamento correto.


@dataclass
class Prescricao:
    acao: str                    # transpor | ativar
    arquetipo: str
    pais: str
    tensao: str | None
    indice: float | None
    perfil: str
    entidade: str | None = None
    pergunta: str = ""           # o que descobrir, quando a ação é transpor
    porque: list[str] = field(default_factory=list)
    falta_descobrir: list[str] = field(default_factory=list)
    evento: dict | None = None

    def __str__(self) -> str:
        alvo = self.entidade or f"({self.arquetipo})"
        i = f"{self.indice:.3f}" if self.indice is not None else "  s/base"
        return f"{self.acao:<8} {i}  {self.pais:<5} {alvo[:34]:<34} {self.perfil}"


def _posicao_da_celula(g: Grafo, arquetipo: str, pais: str, *,
                       entidade=None) -> E.Posicao:
    """Monta a posição com o que o grafo sabe, e só com isso.

    Os eixos que dependem da entidade local — vácuo, volume, produção — ficam
    em branco de propósito quando ela ainda não existe. Preenchê-los com um
    meio-termo transformaria ignorância em número, que é a forma mais cara de
    mentir num motor de decisão.
    """
    arq = g.nos[f"a:{arquetipo}"]
    p = g.nos[f"p:{pais}"]
    tensoes = g.vizinhos(f"a:{arquetipo}", "aciona")
    tensao = tensoes[0].rotulo if tensoes else None

    niveis: dict[str, str | None] = {
        "ignorancia": TENSAO_IGNORANCIA.get(tensao or ""),
        "spread": p.atributos.get("spread"),
        "formato_consumo": p.atributos.get("formato_consumo"),
        # densidade sai do bairro IAB: quem paga para falar com esse estado
        # mental é propriedade do arquétipo, não do país
        "densidade": _densidade_iab(arq.atributos.get("iab_caminho", "")),
    }
    if entidade is not None:
        saz = (entidade.atributos.get("sazonalidade") or "").lower()
        niveis["reposicao"] = {
            "evergreen": "continua", "sazonal_anual": "anual",
            "sazonal_mensal": "mesma_gente", "evento_unico": "unica",
        }.get(saz)
    return E.posicionar(termo=(entidade.rotulo if entidade else arquetipo),
                        pais=pais, **{k: v for k, v in niveis.items() if v})


_DENSIDADE_POR_BAIRRO = {
    "Personal Finance": "densa", "Real Estate": "densa",
    "Careers": "media", "Education": "media", "Medical Health": "media",
    "Shopping": "media", "Home & Garden": "media",
    "Automotive": "rala", "Entertainment": "rala",
    "Politics": "nenhuma", "Crime": "nenhuma",
}


def _densidade_iab(caminho: str) -> str | None:
    return _DENSIDADE_POR_BAIRRO.get(caminho.split(" > ")[0]) if caminho else None


def transpor(g: Grafo, *, forca_minima: int = 2,
             limite: int | None = None) -> list[Prescricao]:
    """Células vazias em arquétipos que já atravessaram fronteira."""
    out: list[Prescricao] = []
    for arquetipo, pais in g.celulas_vazias(forca_minima=forca_minima):
        arq = g.nos[f"a:{arquetipo}"]
        tensoes = g.vizinhos(f"a:{arquetipo}", "aciona")
        tensao = tensoes[0].rotulo if tensoes else None
        pos = _posicao_da_celula(g, arquetipo, pais)

        provado_em = [p.rotulo for p in g.por_tipo("pais")
                      if g.celula(f"a:{arquetipo}", p.id) == "forte"]
        exemplos = []
        for cc in provado_em[:3]:
            ents = g.entidades_de(f"a:{arquetipo}", cc)
            if ents:
                exemplos.append(f"{cc}:{ents[0].rotulo}")

        porque = [f"arquétipo provado em {len(provado_em)} países: {', '.join(provado_em)}"]
        if exemplos:
            porque.append("nomes locais já conhecidos: " + " · ".join(exemplos))
        if tensao:
            d = P.TENSOES.get(tensao, {})
            porque.append(f'tensão «{tensao}»: "{d.get("pergunta", "")}"')
        if arq.atributos.get("orfao_iab"):
            porque.append("sem nó na taxonomia IAB — ninguém mira esse inventário")
        sp = g.nos[f"p:{pais}"].atributos
        if sp.get("spread_natureza") != "observado":
            porque.append(f"spread do país é {sp.get('spread_natureza')}, não medido")

        out.append(Prescricao(
            acao="transpor", arquetipo=arquetipo, pais=pais, tensao=tensao,
            indice=pos.indice, perfil=pos.perfil(),
            pergunta=f"Qual é o nome local de «{arquetipo}» em {pais}? "
                     f"Equivalentes conhecidos: {', '.join(exemplos) or '—'}",
            porque=porque, falta_descobrir=pos.faltando(),
        ))

    out.sort(key=lambda p: -(p.indice or 0))
    return out[:limite] if limite else out


def ativar(g: Grafo, hoje: datetime.date, *,
           janela_dias: int = 90, lead_minimo: int = 7) -> list[Prescricao]:
    """Entidades conhecidas que um evento está tocando dentro da janela útil."""
    out: list[Prescricao] = []
    for ev in g.eventos_ativos(hoje, janela_dias=janela_dias):
        alvos = g.vizinhos(ev.id, "ativa")
        if not alvos:
            continue
        ent = alvos[0]
        arquetipo = ent.atributos.get("arquetipo")
        pais = ent.atributos.get("pais")
        if not arquetipo or not pais or f"a:{arquetipo}" not in g.nos:
            continue

        dias = (datetime.date.fromisoformat(ev.atributos["data"]) - hoje).days
        pos = _posicao_da_celula(g, arquetipo, pais, entidade=ent)
        tensoes = g.vizinhos(f"a:{arquetipo}", "aciona")

        porque = [f"{ev.atributos.get('tipo_evento','evento')} em "
                  f"{ev.atributos['data']} ({dias:+d} dias) · {ev.atributos.get('orgao','')}"]
        if dias < lead_minimo:
            porque.append(f"⚠ faltam {dias}d — abaixo do lead time para escrever, "
                          f"publicar e passar por revisão de política")
        if ent.atributos.get("gancho"):
            porque.append(f'gancho: "{ent.atributos["gancho"][:80]}"')

        out.append(Prescricao(
            acao="ativar", arquetipo=arquetipo, pais=pais,
            tensao=(tensoes[0].rotulo if tensoes else None),
            indice=pos.indice, perfil=pos.perfil(), entidade=ent.rotulo,
            porque=porque, falta_descobrir=pos.faltando(),
            evento={"data": ev.atributos["data"], "dias": dias,
                    "tipo": ev.atributos.get("tipo_evento", ""),
                    "fonte": ev.atributos.get("fonte", "")},
        ))
    out.sort(key=lambda p: -(p.indice or 0))
    return out


def _diversificar(ps: list[Prescricao], *, teto: int,
                  max_por_arquetipo: int = 2,
                  max_por_entidade: int = 1) -> list[Prescricao]:
    """Corta repetição antes de aplicar o teto.

    Sem isto o topo do dia era um arquétipo em cinco países, todos com índice
    idêntico — porque células vazias do mesmo arquétipo herdam exatamente os
    mesmos priores de tensão, e países com o mesmo spread empatam. Uma lista de
    cinco linhas que na prática é uma linha.

    O mesmo vale para evento: `calendario inss` aparecia três vezes, com as
    datas de agosto, setembro e outubro. Só a mais próxima interessa; as outras
    voltam sozinhas no mês que vem.
    """
    vistos_arq: dict[str, int] = {}
    vistos_ent: dict[str, int] = {}
    out: list[Prescricao] = []
    for p in ps:
        chave_ent = (p.entidade or "").lower()
        if chave_ent and vistos_ent.get(chave_ent, 0) >= max_por_entidade:
            continue
        if vistos_arq.get(p.arquetipo, 0) >= max_por_arquetipo:
            continue
        vistos_arq[p.arquetipo] = vistos_arq.get(p.arquetipo, 0) + 1
        if chave_ent:
            vistos_ent[chave_ent] = vistos_ent.get(chave_ent, 0) + 1
        out.append(p)
        if len(out) >= teto:
            break
    return out


def prescrever(g: Grafo, hoje: datetime.date, *, teto_por_acao: int = 5) -> dict:
    """A saída do dia. Teto por ação, e silêncio é resposta válida.

    Melhor três excelentes que quarenta medianos — todo sentinela morre virando
    feed que ninguém lê, e o teto é o que impede isso.
    """
    t, a = transpor(g), ativar(g, hoje)
    t_dia = _diversificar(t, teto=teto_por_acao)
    a_dia = _diversificar(a, teto=teto_por_acao)
    return {
        "data": hoje.isoformat(),
        "transpor": t_dia,
        "ativar": a_dia,
        "retidos": {"transpor": max(0, len(t) - len(t_dia)),
                    "ativar": max(0, len(a) - len(a_dia))},
        "celulas_vazias_total": len(g.celulas_vazias()),
    }
