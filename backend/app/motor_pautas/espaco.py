"""O espaço multidimensional de oportunidade — sem amarras de operação nenhuma.

## Por que este módulo existe e o que ele aposenta

A versão anterior do motor era uma regressão logística ajustada em 237 temas de
uma operação, com alvo `lucro > R$ 3.000`. Uma revisão externa mediu o que eu
não tinha medido: **`spend` sozinho prevê esse alvo com AUC 0,971**, e a mediana
de gasto é R$ 12.430 nos "vencedores" contra R$ 483 nos "perdedores".

O modelo não aprendeu o que é um bom tema. Aprendeu **em que aquela equipe
decidiu investir**. Os perdedores em sua maioria não perderam — foram
descartados antes de serem testados.

Para um motor que existe para SUGERIR pautas, isso é fatal: um sniper que
recomenda o que você já faz não vale nada. O valor inteiro está em apontar o
que ninguém tentou.

Então a camada ajustada saiu. Junto com ela saíram `rpm_arquetipo_loo` (derivado
do lucro daquela carteira) e `sigla_estado` (uma lista fixa de siglas
latino-americanas que valia −0,128 de AUC e não é princípio nenhum — é um
lookup regional).

## O que ficou, e por quê

Ficaram as dimensões **derivadas de princípio**, que não dependem de nenhuma
operação existir. Cada uma responde a uma pergunta sobre o mundo, não sobre uma
planilha:

    A · DEMANDA HUMANA      por que essa pessoa busca, e por que ela LÊ
    B · ECONOMIA DO MERCADO quanto a atenção dela vale e quanto custa comprá-la
    C · POSIÇÃO             dá para entrar, e a que custo de produção

Os pesos vêm de raciocínio sobre a mecânica do negócio, declarados como
**priores**. Não são medições e o código não finge que são. Há um lugar reservado
para calibrá-los contra desfecho — vazio de propósito, porque calibrar contra a
operação-exemplo foi exatamente o erro que este módulo corrige.

## O que o motor devolve

Não devolve só um número. Devolve a **posição do tema no espaço** — porque uma
nota escalar esconde a decisão. `alto volume × spread ruim` e `baixo volume ×
spread ótimo` podem dar a mesma nota e pedem ações opostas.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

# ═══════════════════════════════════════════════════════════════════════════
# FAMÍLIA A — DEMANDA HUMANA
# por que a pessoa busca, e sobretudo por que ela LÊ mais de uma página
# ═══════════════════════════════════════════════════════════════════════════

# A1 · IGNORÂNCIA — o buraco de conhecimento que ela carrega ao chegar.
# Não é a força da pressão: é o tamanho do que ela não sabe. Compulsão máxima
# com ignorância zero não pagina — quem precisa renovar a CNH sabe exatamente
# o que fazer e só quer executar.
# Medido em duas rodadas cegas independentes sobre 237 temas, e o pico está no
# hiato MÁXIMO nas duas:
#
#     nao_sei_se_existe    1,68x · 1,52x   ← pico
#     nao_sei_se_sirvo     0,99x · 1,26x
#     so_falta_um_dado     0,52x · 0,53x
#     sei_o_que_fazer      0,58x · 0,99x
#
# Isso REFUTA a teoria do hiato de informação de Loewenstein, que prevê U
# invertido com pico no hiato moderado. Aqui é monotônico decrescente.
#
# E refuta a transferência de Kahneman: agrupando as tensões por enquadramento
# de perda vs ganho, a razão medida foi 1,06x numa rodada e 0,69x na outra,
# contra os ~2,0x que a Teoria da Perspectiva prevê. O motivo é conceitual —
# Prospect Theory descreve ESCOLHA SOB RISCO, e aqui se mede LEITURA.
# ⚠️ OS DOIS ÚLTIMOS NÍVEIS ESTAVAM CONTRA A PRÓPRIA MEDIÇÃO. A tabela acima diz
# que `sei_o_que_fazer` (0,58 · 0,99) ganhou de `so_falta_um_dado` (0,52 · 0,53)
# NAS DUAS rodadas, e o código codificava o inverso (0,25 contra 0,35) — uma
# revisão externa pegou. A direção medida é consistente, mas a magnitude não é
# (a diferença some na rodada 1 e aparece na 2), e o erro padrão desta base é
# 0,065: qualquer diferença abaixo de ~0,13 é indistinguível de ruído.
#
# Inverter seria trocar um sobreajuste por outro. **Empatados em 0,30** é a
# leitura honesta: medimos que são indistinguíveis, com leve vantagem para o
# lado oposto ao que supúnhamos. Quem quiser separá-los precisa de dado novo.
IGNORANCIA = {
    "nao_sei_se_existe":   (1.00, "não sei nem se isso existe para mim"),
    "nao_sei_se_sirvo":    (0.75, "sei que existe, não sei se me encaixo"),
    "nao_sei_por_que_falhou": (0.65, "sei o que quero, não sei por que não deu"),
    "so_falta_um_dado":    (0.30, "sei tudo, só preciso da data/número"),
    "sei_o_que_fazer":     (0.30, "sei exatamente o passo, quero executar"),
    # PORTÃO, não nível — ver SEM_STAKE abaixo.
    "nao_preciso_de_nada": (0.02, "curiosidade pura — não há nada em jogo"),
}

# A1b · O PORTÃO QUE A ESCALA DE IGNORÂNCIA ESCONDIA.
#
# `curiosidade pura` deu **0% de vitória nas duas rodadas cegas** — zero em 4 e
# zero em 7. É a célula mais limpa de toda a base, e ela expôs um erro de
# desenho: eu tinha colapsado dois conceitos num eixo só.
#
# Quem busca uma novela tem hiato de conhecimento MÁXIMO — não sabe nada sobre
# o capítulo — e não paga, porque **não há nada em jogo**. Hiato e interesse são
# ortogonais, e sem stake nenhum hiato compensa.
SEM_STAKE = "nao_preciso_de_nada"

# A2 · ENGAJAMENTO EXIGIDO — quanto tempo de atenção a resposta EXIGE.
#
# Antes eu chamava isto de "ramificação" e media em páginas. Uma crítica externa
# apontou o erro, e ela procede: a unidade de valor do programático moderno não
# é o pageview, é **tempo de atenção com anúncio visível**. Um artigo único de
# oito minutos com refresh in-view monetiza como quatro pageviews; forçar
# paginação para multiplicar impressões é anti-padrão de UX que ainda por cima
# encarece o CPC pelo Quality Score.
#
# O eixo sobrevive porque o mecanismo sobrevive — muda a unidade. O que mata
# não é a falta de páginas, é a resposta que se esgota em dez segundos: o leitor
# sai antes do anúncio ficar visível, e a viewability do domínio despenca, o que
# rebaixa o inventário nos leilões seguintes.
#
# Medido: 9 temas de "consulta de registro" consumiram R$ 138.814 e devolveram
# prejuízo líquido, contra +48,6% de ROI do resto.
# ⚠️ A ESCALA COLAPSOU DE CINCO NÍVEIS PARA DOIS, E A MEDIÇÃO MANDOU.
#
# Os cinco níveis foram medidos em dois lotes de 4 perguntas por entidade, com
# a forma derivada de contagem em vez de rótulo:
#
#     6 entidades fiscais BR    `diagnostico`  62,5%
#     6 entidades heterogêneas  `condicional`  76,2%
#
# O nível dominante TROCOU entre os lotes e a concentração AUMENTOU. Não é
# sobre qual nível: é que sempre existe um nível para carimbar quase tudo.
# `comparativo` e `sequencial` sumiram do segundo lote inteiro.
#
# Na prática a escala operava com dois estados, e os três do meio eram ruído
# com nome. A regra de auditoria deste próprio repositório diz que um nível
# acima de 40% manda reaplicar o teste; 76,2% não é para ser afinado, é para
# ser aposentado.
#
# O que discrimina, e discrimina limpo: `consultar CPF` deu 1,00 de
# `share_dado_unico` e `aposentadoria por invalidez` deu 0,00. Os extremos se
# separam. O meio nunca se separou.
#
# QUANTO uma resposta sustenta continua descrito — pelas CONTAGENS CRUAS
# (`2 ramos · 3 condições · sobra decisão`), que é o dado honesto e já está
# gravado. O que saiu foi a pretensão de ordená-las.
ENGAJAMENTO = {
    "sustenta":   (1.00, "ramifica, condiciona ou deixa decisão — há o que ler"),
    "dado_unico": (0.05, "esgota em segundos: o leitor sai antes do anúncio "
                          "ficar visível e a viewability do domínio cai"),
}

# Os cinco níveis antigos, para LER linha já gravada sem quebrar. Não são
# válidos como entrada: `posicionar()` recusa, e é assim que fica claro que a
# escala mudou em vez de conviverem duas.
ENGAJAMENTO_LEGADO = {
    "diagnostico": "sustenta", "condicional": "sustenta",
    "sequencial": "sustenta", "comparativo": "sustenta",
    "dado_unico": "dado_unico",
}
RAMIFICACAO = ENGAJAMENTO   # nome antigo, mantido para não quebrar chamadas

# A3 · OPACIDADE — o quanto a instituição esconde. Universal a qualquer
# burocracia: se o canal oficial resolvesse, ninguém leria uma explicação dele.
OPACIDADE = {
    "regra_mudou":       (1.00, "mudou há pouco, ninguém explicou ainda"),
    "fragmentada":       (0.85, "resposta espalhada entre órgãos ou varia por região"),
    "ilegivel":          (0.60, "existe num só lugar, mas em linguagem de decreto"),
    "clara":             (0.10, "o site oficial resolve em um clique"),
}

# A4 · REPOSIÇÃO — entra gente NOVA na condição, ou é sempre a mesma voltando?
# A distinção decide se o funil é anuidade ou assinatura: reposição significa
# público que nunca viu aquilo, todo dia.
REPOSICAO = {
    "continua":     (1.00, "gente nova entra na condição o tempo todo"),
    "anual":        (0.70, "uma coorte nova por ano"),
    "mesma_gente":  (0.55, "os mesmos voltando periodicamente"),
    "unica":        (0.20, "aconteceu e acabou"),
}

# ═══════════════════════════════════════════════════════════════════════════
# FAMÍLIA B — ECONOMIA DO MERCADO
# quanto a atenção dessa pessoa vale, e quanto custa comprá-la
# ═══════════════════════════════════════════════════════════════════════════

# B1 · VOLUME — quantas pessoas por mês. Faixas largas de propósito: precisão
# de volume é ilusória em termo que ninguém comprou ainda, e faixa honesta
# decide tão bem quanto número falso.
VOLUME = {
    "massivo":   (1.00, "acima de 100 mil buscas/mês no país"),
    "alto":      (0.80, "10 mil a 100 mil"),
    "medio":     (0.55, "1 mil a 10 mil"),
    "baixo":     (0.30, "100 a 1 mil"),
    "residual":  (0.10, "abaixo de 100 — não sustenta funil"),
}

# B2 · SPREAD — RPM ÷ CPC, e a unidade é ARQUÉTIPO × PAÍS, não país.
#
# Duas correções acumuladas aqui.
#
# A primeira, que já estava certa: Tier 1 tem eCPM alto E CPC alto, e arbitragem
# vive da RAZÃO, não do eCPM absoluto. Um mercado com metade do eCPM e um quinto
# do CPC é melhor.
#
# A segunda veio de crítica externa e derruba a forma como eu media. Eu usava
# **média nacional**, e testei contra os cinco mercados com resultado medido:
# **Pearson −0,266** — não previu nada. O motivo: média de país dilui o nicho no
# run-of-network. O RPM de uma página de subsídio habitacional e o de uma página
# de multa de trânsito não são o mesmo número, e o CPC de "cesantias" não é o
# CPC médio da Colômbia.
#
# A unidade correta é `RPM do arquétipo naquele país ÷ CPC da keyword naquele
# país`. Valor de país entra só como fallback declarado, e o campo `cobertura`
# denuncia quando foi isso que aconteceu.
SPREAD = {
    "excelente": (1.00, "RPM/CPC acima de 2,0"),
    "bom":       (0.75, "1,4 a 2,0"),
    "neutro":    (0.50, "1,0 a 1,4"),
    "ruim":      (0.25, "abaixo de 1,0: o clique custou mais que a sessão rendeu"),
}

# B4 · FORMATO DE CONSUMO DOMINANTE — o funil pressupõe busca em texto.
#
# O eixo que faltava, e a crítica que o revelou é a mais forte que recebi sobre
# a tese de transposição: na Índia, Nigéria e Filipinas, "como fazer" de
# burocracia não acontece em artigo indexado. Acontece em WhatsApp, em tutorial
# no YouTube, em busca por voz, e via intermediário humano.
#
# A tensão psicológica atravessa fronteira — isso continua valendo. O que não
# atravessa é o **canal**. Um arquétipo perfeito num país onde ninguém lê artigo
# longo é um funil que não fecha, e nenhuma outra dimensão avisa isso.
FORMATO_CONSUMO = {
    "texto_busca":  (1.00, "buscar no Google e ler artigo é o padrão"),
    "misto":        (0.65, "texto convive com vídeo e mensageria"),
    "video_social": (0.30, "YouTube, WhatsApp e grupos dominam o 'como fazer'"),
    "voz_ou_humano": (0.15, "busca por voz ou intermediário físico — o funil não fecha"),
}

# B3 · DENSIDADE DE COMPRADOR — quantos setores pagariam para falar com essa
# pessoa NESTE estado mental. É o lado da venda e é onde a taxonomia IAB serve.
# Quem pesquisa subsídio habitacional está in-market para crédito, seguro e
# material; quem pesquisa multa de trânsito não está in-market para nada.
DENSIDADE = {
    "densa":   (1.00, "três ou mais setores nomeáveis"),
    "media":   (0.60, "um ou dois"),
    "rala":    (0.25, "difícil nomear um"),
    "nenhuma": (0.05, "estado mental sem comprador"),
}

# ═══════════════════════════════════════════════════════════════════════════
# FAMÍLIA C — POSIÇÃO
# dá para entrar, e quanto custa produzir
# ═══════════════════════════════════════════════════════════════════════════

# C1 · VÁCUO — quantos já explicaram bem.
VACUO = {
    "virgem":    (1.00, "entidade nomeada que ninguém explicou"),
    "raso":      (0.70, "poucos explicaram, e mal"),
    "disputado": (0.35, "vários portais cobrem"),
    "saturado":  (0.10, "commodity, inclusive grandes portais"),
}

# C2 · CUSTO DE PRODUÇÃO — invertido: barato de produzir vale mais.
# Um tema que exige acompanhar mudança legislativa toda semana consome equipe;
# um que se escreve uma vez e envelhece devagar é ativo.
PRODUCAO = {
    "escreve_uma_vez": (1.00, "escreve e envelhece devagar"),
    "revisao_anual":   (0.75, "precisa de uma atualização por ano"),
    "revisao_mensal":  (0.45, "muda com frequência"),
    "acompanhamento":  (0.20, "exige monitorar mudança o tempo todo"),
}


FAMILIAS = {
    "demanda_humana": {
        "ignorancia": IGNORANCIA, "engajamento": ENGAJAMENTO,
        "opacidade": OPACIDADE, "reposicao": REPOSICAO,
    },
    "economia": {
        "volume": VOLUME, "spread": SPREAD, "densidade": DENSIDADE,
        "formato_consumo": FORMATO_CONSUMO,
    },
    "posicao": {
        "vacuo": VACUO, "producao": PRODUCAO,
    },
}

# ── PORTÕES ─────────────────────────────────────────────────────────────────
# Um portão é um PAR (eixo, nível), binário. Ou o par ocorre e o tema morre, ou
# não ocorre e o eixo entra na média como qualquer outro.
#
# A versão anterior tratava o EIXO INTEIRO como portão (`base *= g.valor` em
# qualquer nível), e uma revisão externa reproduziu o estrago no próprio módulo:
#
#   diagnostico -> comparativo   x0,60    um passo banal na forma da pergunta
#   spread excelente -> ruim     x0,80    a margem de verdade do negócio
#
# Ou seja: o rótulo que um agente declara movia a nota MAIS que a margem. Pior,
# `spread=ruim` com todo o resto perfeito dava 0,802 e perfil "alvo" — prejuízo
# estrutural saindo como "lê e paga", que é exatamente a decisão que o modelo
# existe para não errar.
#
# EVIDÊNCIA DE CADA PAR — e ela é desigual, o que o código diz em voz alta:
#
#   (engajamento, dado_unico)     FORTE, e agora é o ÚNICO estado que o eixo
#                                 distingue. 9 temas somaram R$138.814, ~R$15k cada,
#                                 ACIMA da mediana dos vencedores: passaram pelo
#                                 filtro de verba e perderam assim mesmo. É o
#                                 único achado imune ao viés de seleção que
#                                 contamina o resto da base (ver DECISOES.md §1).
#   (ignorancia, nao_preciso...)  FRACA. 0 de 11, IC de Wilson até 0,26, p≈0,09
#                                 contra base de ~20%. Indício, não prova. Fica
#                                 como portão pela plausibilidade do mecanismo
#                                 (não há nada em jogo), não pela estatística.
#   (formato_consumo, ...)        Decisão de PAÍS, não de tema. Dentro de um
#                                 mesmo país o Spearman com e sem é 1,0 — ele
#                                 não reordena nada, só elimina o mercado.
#   (spread, ruim)                ARITMÉTICA. Razão < 1,0 é prejuízo por
#                                 construção; nenhuma leitura compensa.
#   (volume, residual)            O próprio rótulo diz "não sustenta funil".
#
# ⚠️ PROVENIÊNCIA: `spread` e `volume` só disparam o portão quando foram
# MEDIDOS. Na fase de descoberta os dois são palpite de LLM, e deixar um número
# inventado matar um tema é o mesmo erro, do outro lado. Ver `posicionar(...,
# medidos=...)`.
PORTOES: dict[str, tuple[str, ...]] = {
    "engajamento":     ("dado_unico",),
    "ignorancia":      (SEM_STAKE,),
    "formato_consumo": ("video_social", "voz_ou_humano"),
    "spread":          ("ruim",),
    "volume":          ("residual",),
}

# Portões que só valem com dado MEDIDO — nunca com estimativa.
PORTOES_EXIGEM_MEDICAO = frozenset({"spread", "volume"})

ESCALAS = {n: e for f in FAMILIAS.values() for n, e in f.items()}
TODOS_OS_EIXOS = tuple(ESCALAS)

# ── ESCOPO ──────────────────────────────────────────────────────────────────
# Nem toda etapa responde os dez eixos, e fingir que responde é o que trava a
# cobertura num teto que não significa nada.
#
# `spread` NÃO está no escopo do pautador, e isso é DECISÃO, não falta de dado.
# O pautador responde "vale a pena escrever sobre isso?" — demanda humana,
# opacidade institucional, espaço editorial, tamanho e renovação do público.
# `spread` é receita por sessão ÷ custo do clique: razão de COMPRA. Decisão de
# compra pertence a onde o dinheiro sai, no engine de Ads, e é lá que vivem as
# duas metades da razão — `ad_traffic_by_keywords` com lance real (6% de erro
# medido) e o RPM do GAM.
#
# O eixo continua definido acima de propósito: o engine de Ads vai usá-lo, e o
# docstring de `SPREAD` carrega o que a medição custou (o Pearson −0,266 da
# média nacional; a correção para a unidade arquétipo × país). Apagar o campo
# apagaria o aprendizado junto.
#
# Decisão se contesta; ausência se conserta por engano — por isso escopo, e não
# um eixo perpetuamente "ausente".
#
# `producao` também sai, e por outro motivo: ele não é sinal de MERCADO. "Quanto
# custa manter a página viva" é restrição de capacidade da equipe. Um tema que
# exige revisão semanal e imprime dinheiro deve ser escrito; um que se escreve
# uma vez e ninguém lê, não. Misturado na média, `escreve_uma_vez` puxava tema
# morto para cima. Nenhuma ferramenta de keyword tem esse dado porque ele não é
# do mercado — e o teste que este escopo aplica é exatamente esse: se a
# ferramenta padrão já dá, é chão; se não dá e não é do mercado, não é eixo.
#
# Ele continua definido acima: vira nota operacional no card, fora da conta.
FORA_DO_ESCOPO_PAUTADOR = ("spread", "producao")
ESCOPO_PAUTADOR = tuple(e for e in TODOS_OS_EIXOS if e not in FORA_DO_ESCOPO_PAUTADOR)

# ── priores ─────────────────────────────────────────────────────────────────
# Vindos de raciocínio sobre a mecânica, e o código diz isso em voz alta. NÃO
# são coeficientes ajustados.
#
# Com o portão virando PAR (eixo, nível), os eixos de portão passam a entrar na
# média nos níveis que NÃO são portão — `comparativo` é uma forma de pergunta
# perfeitamente normal e não pode custar x0,60. Isso obrigou a repesá-los, e a
# ordem aqui segue a FORÇA DA EVIDÊNCIA, não a intuição:
#
#   ignorancia   0,90  o único eixo com correlação medida contra desfecho
#                      (+0,194, contra +0,017 da hipótese que caiu). Ganha o
#                      maior peso porque é o único que ganhou no teste cego.
#   engajamento  0,75  tem evidência FORTE no extremo (`dado_unico`, imune ao
#                      viés de seleção) e NENHUMA nos níveis intermediários.
#                      Peso médio é a leitura honesta disso.
#   formato_consumo 0,35  vem de tabela escrita à mão por país, não de medição.
#                      Peso baixo, e o que ele tem de real é o portão.
#
# `_CALIBRACAO` está vazio de propósito. É onde entram fatores medidos quando
# houver desfecho próprio — e o alvo NÃO pode ser lucro. Uma revisão externa
# apontou o furo que sobreviveu à primeira limpeza: aposentamos a regressão
# porque `spend` previa `lucro > R$3.000` com AUC 0,971, mas continuamos medindo
# a escada de ignorância e as refutações de Kahneman/Loewenstein contra ESSE
# MESMO alvo. Régua contaminada contamina tudo que se mede com ela. O alvo certo
# é uma RAZÃO — segundos de anúncio visível por real de clique, ou RPC/CPC —
# porque `spend` não pode prever razão por construção.
PRIORES = {
    "ignorancia":      0.90,
    "opacidade":       0.85,
    "engajamento":     0.75,
    "densidade":       0.70,
    "spread":          0.70,
    "volume":          0.65,
    "reposicao":       0.60,
    "vacuo":           0.55,
    "formato_consumo": 0.35,
    "producao":        0.35,
}

_CALIBRACAO: dict[str, float] = {}


def peso(dimensao: str) -> float:
    return PRIORES[dimensao] * _CALIBRACAO.get(dimensao, 1.0)


# ── leitura e posição ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Eixo:
    nome: str
    nivel: str | None
    valor: float | None
    familia: str
    # De onde veio o nível. `False` = estimativa (o padrão: um agente declarou,
    # ou um LLM chutou na descoberta). `True` = medição (DataForSEO, GAM, o join
    # de placement). Só importa para os portões de `spread` e `volume`, que se
    # recusam a matar um tema com base em palpite.
    medido: bool = False

    @property
    def conhecido(self) -> bool:
        return self.nivel is not None

    @property
    def e_portao(self) -> bool:
        """O par (eixo, nível) deste eixo é um portão que DISPAROU?

        Binário por desenho. Um eixo de portão num nível que não é portão entra
        na média como qualquer outro — `comparativo` não é pré-condição de nada.
        """
        if not self.conhecido or self.nome not in PORTOES:
            return False
        if self.nivel not in PORTOES[self.nome]:
            return False
        if self.nome in PORTOES_EXIGEM_MEDICAO and not self.medido:
            return False        # palpite não mata tema
        return True


@dataclass
class Posicao:
    """A posição do tema no espaço. Escalar é o resumo, não o resultado."""
    termo: str
    pais: str
    eixos: dict[str, Eixo]
    alertas: list[str] = field(default_factory=list)
    # Os eixos que ESTA etapa responde. `cobertura` divide por ele, não pelos
    # dez — senão uma etapa de nove eixos fica presa em 90% para sempre, e o
    # número deixa de distinguir "faltou medir" de "não é da minha conta".
    escopo: tuple[str, ...] = TODOS_OS_EIXOS

    def conhecidos(self) -> list[Eixo]:
        return [e for e in self.eixos.values() if e.conhecido]

    def faltando(self) -> list[str]:
        return [n for n, e in self.eixos.items() if not e.conhecido]

    def familia(self, nome: str) -> float | None:
        """Índice de uma família isolada. Ver as três separadas é o ponto:
        `demanda humana alta` com `economia ruim` pede ação diferente do inverso."""
        eixos = [e for e in self.conhecidos() if e.familia == nome]
        if not eixos:
            return None
        ls = sum(peso(e.nome) * math.log(max(e.valor, 1e-6)) for e in eixos)
        pt = sum(peso(e.nome) for e in eixos)
        return math.exp(ls / pt) if pt else None

    def portoes_disparados(self) -> list[str]:
        """Os pares (eixo, nível) de portão que ocorreram. Vazio = nenhum."""
        return [e.nome for e in self.eixos.values() if e.e_portao]

    @property
    def indice(self) -> float | None:
        """Média geométrica ponderada de TODOS os eixos conhecidos — **zero** se
        qualquer portão disparou.

        Duas mudanças vindas de revisão externa, ambas reproduzidas no código
        antes de aceitas:

        1. PORTÃO É PAR, NÃO EIXO. Antes, `base *= g.valor` aplicava força de
           portão a QUALQUER nível dos três eixos: `comparativo` custava x0,60 e
           `nao_sei_se_sirvo` x0,75, sem nenhuma evidência de que fossem
           pré-condição. O rótulo declarado por um agente movia a nota mais que
           a margem real (`spread` excelente->ruim custava só x0,80). Agora um
           par de portão zera; qualquer outro nível entra na média.

        2. PORTÃO AUSENTE EXCLUI, não vale 0,70. O default anterior premiava o
           silêncio: não declarar `formato_consumo` dava 0,700 e declarar
           honestamente `misto` dava 0,650 — calar rendia 1,08x mais que dizer a
           verdade. Isso contradizia o princípio que este mesmo módulo enuncia:
           dimensão desconhecida fica FORA da conta, nunca vira meio-termo.

        Zero, e não um número pequeno, porque portão é decisão binária: não
        construa. Ordenar temas mortos entre si não informa nada.
        """
        if self.portoes_disparados():
            return 0.0
        eixos = self.conhecidos()
        if len(eixos) < 3:
            return None
        # ...e de pelo menos DUAS famílias. Média sobre uma família só não é
        # índice, é o que `familia()` já entrega com o nome certo. A regra
        # antiga (>=3 eixos NÃO-portão) impedia isso por acidente: com os três
        # eixos de julgamento declarados sobrava um não-portão e o índice saía
        # None. Ao tornar o portão um par, o acidente sumiu e o caso passou a
        # devolver número — uma nota de 0,90 sobre 30% de cobertura, toda ela
        # de `demanda_humana`, que diria "ótimo tema" sem saber nada da
        # economia nem da posição.
        if len({e.familia for e in eixos}) < 2:
            return None
        ls = sum(peso(e.nome) * math.log(max(e.valor, 1e-6)) for e in eixos)
        pt = sum(peso(e.nome) for e in eixos)
        return math.exp(ls / pt) if pt else None

    @property
    def cobertura(self) -> float:
        """Fração do ESCOPO que foi declarada. Card completo dá 1,0."""
        return len(self.conhecidos()) / max(1, len(self.escopo))

    def perfil(self) -> str:
        """Rótulo do quadrante — é o que orienta a ação, não a nota.

        O portão vem PRIMEIRO. Antes não vinha, e os dois lados do mesmo objeto
        se contradiziam: `dado_unico` com todo o resto perfeito dava índice 0,05
        e perfil `"alvo"`, e `spread=ruim` com todo o resto perfeito dava 0,802 e
        também `"alvo"` — prejuízo estrutural rotulado como "lê e paga". Se o
        quadrante é o que orienta a ação, ele não pode discordar da nota.
        """
        if self.portoes_disparados():
            return "descartar"
        h, ec = self.familia("demanda_humana"), self.familia("economia")
        if h is None or ec is None:
            return "indefinido"
        alto_h, alto_e = h >= 0.60, ec >= 0.60
        if alto_h and alto_e:
            return "alvo"                    # lê e paga
        if alto_h and not alto_e:
            return "audiencia_pobre"         # lê muito, mercado não paga
        if not alto_h and alto_e:
            return "mercado_rico_sem_leitura"  # paga bem, mas não pagina
        return "descartar"


def posicionar(termo: str, *, pais: str = "??",
               medidos: Iterable[str] = (),
               escopo: Iterable[str] | None = None, **niveis) -> Posicao:
    """Monta a posição a partir dos níveis declarados.

    Nenhum eixo é inferido de regex de idioma. Quem declara é quem julga — um
    agente, um humano — e o Python faz a aritmética. É isso que faz o motor
    valer para tailandês sem uma linha de tailandês no código.

    `medidos` nomeia os eixos cujo nível veio de MEDIÇÃO, não de estimativa. Só
    os portões de `spread` e `volume` consultam isso, e a razão é operacional:
    na fase de descoberta esses dois são palpite de LLM, e um número inventado
    não pode matar um tema. Depois da mineração de keywords eles viram medição e
    o portão passa a valer. Ausente = estimativa, que é o padrão seguro.

    Chave desconhecida em `**niveis` levanta `ValueError` em vez de ser engolida
    — um typo silencioso vira eixo não declarado, e eixo não declarado muda a
    conta sem avisar ninguém.
    """
    desconhecidas = set(niveis) - set(ESCALAS)
    if desconhecidas:
        raise ValueError(
            f"eixo(s) inexistente(s): {sorted(desconhecidas)}. "
            f"Válidos: {sorted(ESCALAS)}")
    escopo = tuple(escopo) if escopo is not None else TODOS_OS_EIXOS
    fora = set(escopo) - set(ESCALAS)
    if fora:
        raise ValueError(f"escopo com eixo inexistente: {sorted(fora)}")
    # Declarar nível de eixo fora do escopo é contrato violado, não descuido:
    # ou a etapa mudou de escopo, ou alguém mediu o que não devia.
    intrusos = set(niveis) - set(escopo)
    if intrusos:
        raise ValueError(
            f"eixo(s) fora do escopo desta etapa: {sorted(intrusos)}. "
            f"Escopo: {sorted(escopo)}")
    medidos = set(medidos)

    eixos: dict[str, Eixo] = {}
    for fam, dims in FAMILIAS.items():
        for nome, escala in dims.items():
            if nome not in escopo:
                continue          # fora do escopo não entra em conta nenhuma
            n = niveis.get(nome)
            if n in (None, "", "desconhecido"):
                eixos[nome] = Eixo(nome, None, None, fam)
            elif n not in escala:
                raise ValueError(
                    f"nível {n!r} não existe em {nome}. Válidos: {sorted(escala)}")
            else:
                eixos[nome] = Eixo(nome, n, escala[n][0], fam, nome in medidos)

    p = Posicao(termo=termo, pais=pais.upper(), eixos=eixos, escopo=escopo)

    if eixos.get("engajamento") and eixos["engajamento"].nivel == "dado_unico":
        p.alertas.append(
            "PORTÃO · ENGAJAMENTO NULO — a resposta esgota em segundos, o leitor sai "
            "antes do anúncio ficar visível e a viewability do domínio cai. "
            "Nenhuma outra dimensão compensa.")
    if eixos.get("ignorancia") and eixos["ignorancia"].nivel == SEM_STAKE:
        p.alertas.append(
            "PORTÃO · SEM STAKE — curiosidade pura deu 0% de vitória nas duas "
            "rodadas cegas. Hiato de conhecimento sem nada em jogo não paga.")
    elif eixos.get("ignorancia") and eixos["ignorancia"].nivel == "sei_o_que_fazer":
        p.alertas.append(
            "IGNORÂNCIA BAIXA — sabe exatamente o que fazer e quer executar. "
            "Pressão alta não implica leitura.")
    if eixos.get("volume") and eixos["volume"].nivel == "residual":
        p.alertas.append("VOLUME RESIDUAL — não sustenta funil mesmo com tudo o resto bom.")
    if eixos.get("spread") and eixos["spread"].nivel == "ruim":
        p.alertas.append("SPREAD RUIM — o clique come a receita neste nicho e mercado.")
    if eixos["formato_consumo"].nivel in ("video_social", "voz_ou_humano"):
        p.alertas.append(
            "FORMATO DE CONSUMO — neste país o 'como fazer' de burocracia acontece "
            "em vídeo, mensageria ou intermediário humano. A tensão atravessa "
            "fronteira; o canal não.")
    # Portão não declarado merece aviso PRÓPRIO. `portoes_disparados()` vazio é
    # ambíguo: pode significar "nenhum fechou" ou "ninguém olhou", e as duas
    # coisas orientam ações opostas. Excluir o eixo da média (o certo) ainda
    # deixa um resíduo de incentivo — não declarar um eixo fraco sobe a média,
    # o que vale para os 10 eixos e é o preço de nunca inventar meio-termo. A
    # defesa é `cobertura` + o mínimo do `ordenar`; este alerta é o que impede
    # que o silêncio passe por veredito.
    portoes_mudos = [n for n in PORTOES
                     if n in p.eixos and not p.eixos[n].conhecido]
    if portoes_mudos:
        p.alertas.append(
            f"PORTÃO NÃO VERIFICADO: {', '.join(portoes_mudos)} — o índice NÃO "
            f"afirma que nenhum portão fecha, só que ninguém olhou.")
    outros_mudos = [n for n in p.faltando() if n not in PORTOES]
    if outros_mudos:
        p.alertas.append(f"não declarados: {', '.join(outros_mudos)} — o índice sai "
                         f"só sobre os {len(p.conhecidos())} conhecidos.")
    return p


def ordenar(posicoes: list[Posicao], *, minimo_cobertura: float = 0.5) -> list[Posicao]:
    """Ordena por índice. Sai da lista — não vai para o fim, sai — quem:

      · não atinge a cobertura mínima  (item mal declarado no meio de um
        ranking parece avaliado, e isso é pior que ausente)
      · teve um PORTÃO disparado       (tema morto ordenado entre outros mortos
        não informa nada, e ocupar a 18ª posição sugere que existe uma 17ª
        melhor da mesma natureza — sugere gradiente onde há decisão binária)

    Quem foi barrado continua acessível pelo objeto, com `portoes_disparados()`
    e os alertas dizendo o motivo em frase. O que ele não faz é entrar na fila.
    """
    aptos = [p for p in posicoes
             if p.indice is not None
             and p.cobertura >= minimo_cobertura
             and not p.portoes_disparados()]
    return sorted(aptos, key=lambda p: -(p.indice or 0))
