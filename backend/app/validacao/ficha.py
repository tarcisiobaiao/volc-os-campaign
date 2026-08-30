"""A ficha da resposta: o LLM CONTA, o Python DERIVA.

## O que muda, e por que era necessário

Antes, o modelo recebia uma entidade e devolvia `ignorancia: nao_sei_se_sirvo`.
Um julgamento ordinal, numa escala cujos números foram inventados, com 67% de
estabilidade entre execuções idênticas. E `ignorancia` e `engajamento` se
sobrepunham tanto que o prompt precisava de uma trava proibindo a combinação
contraditória entre os dois.

Duas auditorias externas convergiram no mesmo diagnóstico: pedir rótulo onde se
deveria pedir contagem. Aqui o modelo responde oito coisas **contáveis e
verificáveis contra o texto que ele mesmo acabou de escrever**, e os três eixos
psicológicos saem de aritmética em Python, onde não oscilam.

    quantas condições pessoais preciso saber para responder?     0 1 2 3+
    quantos ramos levam a ações DIFERENTES?                      1 2 3+
    quantas fontes oficiais distintas a resposta exige?          1 2 3+
    sobra decisão DEPOIS da resposta?                            sim/não
    o canal oficial fecha a pergunta sozinho?                    sim/não
    a regra mudou há pouco?                                      sim/não
    há algo concreto em jogo?                                    sim/não
    ela descobre AQUI que isso existe para ela?                  sim/não

Isso resolve três coisas de uma vez: mata a sobreposição entre eixos (cada um
sai de observáveis distintos), torna a evidência independente do veredito (o
teste que eu fiz antes era inválido porque o modelo inventava a evidência na
mesma respiração em que a julgava), e transforma o portão `dado_unico` numa
consequência aritmética em vez de um julgamento.

## O nome do nível é vocabulário legado, a derivação é a definição

`nao_sei_por_que_falhou` não significa literalmente "não sabe por que falhou":
significa **uma condição pessoal por resolver**. Os nomes ficam porque
`espaco.py` os exige e porque trocá-los quebraria a comparação com o histórico.
A regra que vale é a que está no código abaixo, não o que o nome sugere.

## O que NÃO é derivado aqui

`volume`, `reposicao`, `vacuo`, `formato_consumo` e `densidade` são medidos pela
API. `producao` saiu do escopo: é restrição de capacidade da equipe, não sinal
de mercado, e nenhuma ferramenta de keyword a tem porque ela não é do mercado.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.motor_pautas.psique import TENSOES

# Os oito observáveis. Contagens são saturadas em 3 de propósito: a diferença
# entre 3 e 7 condições não muda decisão nenhuma, e pedir precisão onde ela não
# decide é convidar o modelo a inventar.
TETO_CONTAGEM = 3

# A trava de citação só liga acima disto. Abaixo, o ruído de formatação domina e
# a trava reprovaria mais medição boa do que fabricação.
LIMIAR_TRAVA_CITACAO = 0.90

# `stake_qual` que não nomeia nada. Comparados já normalizados.
_STAKE_VAZIO = frozenset({
    "nenhum", "nenhuma", "n a", "na", "nao se aplica", "nada", "-", "sem stake",
    "indefinido", "generico", "varios", "diversos", "curiosidade",
})


def _normalizar(texto: str) -> str:
    """Dobra acento, caixa e pontuação para a citação ser conferível.

    A conferência é `substring`, e substring é implacável com detalhe que não
    muda sentido: `"saque-aniversário"` contra `"saque aniversario"` reprovaria
    citação honesta. Dobrar acento (NFD, joga fora as marcas), caixa e
    pontuação deixa passar a variação de forma e continua pegando o que
    importa — trecho que simplesmente não está no texto.

    O que NÃO se dobra: ordem de palavras. Reordenar frase é reescrever, e
    reescrita é exatamente a paráfrase que esta conferência existe para pegar.
    """
    if not texto:
        return ""
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", str(texto))
                         if unicodedata.category(c) != "Mn")
    limpo = "".join(c if c.isalnum() or c.isspace() else " " for c in sem_acento)
    return " ".join(limpo.lower().split())


@dataclass(frozen=True)
class Ficha:
    """O que o modelo observou. Nada aqui é nível de eixo."""

    resposta_literal: str = ""
    consulta_dominante: str = ""
    condicoes_pessoais: int = 0
    ramos_de_acao: int = 1
    fontes_oficiais: int = 1
    decisao_apos_resposta: bool = False
    oficial_fecha_sozinho: bool = False
    regra_mudou_recentemente: bool = False
    stake: bool = True
    stake_qual: str = ""
    descobre_que_existe: bool = False
    # A CARGA com que ela chega, contra a FORMA da resposta que os oito acima
    # descrevem. Vocabulário fechado das 7 tensões + `nenhuma`. O LLM reconhece
    # QUAL é; a intensidade vem da tabela, fora dele.
    tensao: str = "nenhuma"
    porques: Dict[str, str] = field(default_factory=dict)
    # O trecho da PRÓPRIA `resposta_literal` que justifica cada observável.
    # Veio da segunda rodada da auditoria externa e é a melhor ideia que ela
    # produziu: transforma contagem em coisa conferível. `porques` é prosa sobre
    # a contagem; `trechos_citados` tem de ser recorte do texto, e recorte se
    # confere com `in`.
    trechos_citados: Dict[str, str] = field(default_factory=dict)

    def citacoes_conferem(self) -> Dict[str, bool]:
        """Quais citações de fato aparecem na resposta que o modelo escreveu.

        ⚠️ HOJE ISTO MEDE, NÃO BARRA — e a ordem importa.

        Citação que não está no texto é fabricação, e detectá-la é o ganho
        inteiro da ideia. Mas normalização produz falso negativo, e uma trava
        ligada antes de medir a taxa de falso negativo reprovaria ficha boa em
        silêncio — que é a classe de defeito que este arquivo já cometeu duas
        vezes. Primeiro se mede a taxa; depois se decide se ela barra.

        O limiar para ligar a trava, herdado da auditoria externa: **90% de
        acerto observado**. Abaixo disso o ruído de formatação domina e a trava
        reprovaria mais medição boa do que fabricação.
        """
        alvo = _normalizar(self.resposta_literal)
        fora: Dict[str, bool] = {}
        for campo, trecho in (self.trechos_citados or {}).items():
            t = _normalizar(trecho)
            fora[campo] = bool(t) and t in alvo
        return fora

    @property
    def stake_validado(self) -> bool:
        """`stake=True` sustentado por evidência, ou apenas afirmado.

        A brecha é da auditoria externa e é real: como `stake` NÃO cai por falta
        de citação (rebaixar por ausência de prova dispararia o portão), uma
        curiosidade pura marcada `stake=True` com `stake_qual` vazio ou genérico
        passaria limpa para a fila de produção.

        O conserto não é rebaixar — é RECUSAR O AUTOMÁTICO. Quando o stake é
        afirmado e não sustentado, o orquestrador força `limitrofe` e um humano
        olha. Nenhum tema morre por formatação de string; nenhum tema sem stake
        real entra na fila sem alguém ver.
        """
        if not self.stake:
            return True                    # negar stake não precisa de prova
        qual = _normalizar(self.stake_qual)
        if not qual or qual in _STAKE_VAZIO:
            return False
        citada = self.citacoes_conferem().get("stake")
        return citada is not False         # None (não citou) ainda passa

    @property
    def assinatura(self) -> tuple:
        """Só os observáveis. É o que se compara entre duas passadas.

        A `resposta_literal` fica de fora: duas passadas podem escrever a mesma
        resposta com palavras diferentes, e comparar prosa produziria desacordo
        onde não há. O que precisa bater são os números.
        """
        return (self.condicoes_pessoais, self.ramos_de_acao, self.fontes_oficiais,
                self.decisao_apos_resposta, self.oficial_fecha_sozinho,
                self.regra_mudou_recentemente, self.stake, self.descobre_que_existe)

    @classmethod
    def de_json(cls, d: Dict[str, Any]) -> Optional["Ficha"]:
        """Constrói a partir da resposta do modelo. Recusa o que não é observável.

        Contagem que não vem inteira, ou booleano que vem como string, devolve
        `None` — a ficha inteira. Meia ficha derivaria eixo com metade da base,
        e um eixo derivado de contagem faltante é pior que eixo ausente: ele
        entra na média com cara de medido.
        """
        if not isinstance(d, dict):
            return None
        try:
            contagens = {
                k: max(0, min(TETO_CONTAGEM, int(d[k])))
                for k in ("condicoes_pessoais", "ramos_de_acao", "fontes_oficiais")
            }
        except (KeyError, TypeError, ValueError):
            return None

        booleanos = {}
        for k in ("decisao_apos_resposta", "oficial_fecha_sozinho",
                  "regra_mudou_recentemente", "stake", "descobre_que_existe"):
            v = d.get(k)
            if not isinstance(v, bool):
                return None       # `"true"` entre aspas é verdadeiro em Python
            booleanos[k] = v

        # Tensão fora do vocabulário vira `nenhuma` — nunca a "mais parecida".
        # Aproximação semântica aqui é o mesmo erro da blocklist de palavras:
        # parece robustez e é invenção.
        tensao = str(d.get("tensao") or "nenhuma").strip().lower()
        if tensao not in TENSOES:
            tensao = "nenhuma"

        trechos = {k: str(v)[:400] for k, v in (d.get("trechos_citados") or {}).items()
                   if isinstance(v, str) and str(v).strip()}

        # ── a regra da citação, e ela é ASSIMÉTRICA de propósito ────────────
        #
        # A auditoria externa reprovou `regra_mudou_recentemente` e `stake` por
        # exigirem conhecimento de fora do texto. O diagnóstico é bom; a receita
        # dela (apagar os dois) não é, porque apagar tira o topo de `opacidade`
        # da escala. O conserto é exigir âncora textual — mas os dois não podem
        # receber o mesmo tratamento, e é aqui que a simetria mataria tema:
        #
        #   `regra_mudou_recentemente` é o TOPO de `opacidade` (1,00). Sem
        #   citação, rebaixar para False é CONSERVADOR: deixa de inflar.
        #
        #   `stake=False` é o PORTÃO `nao_preciso_de_nada`, que zera o índice.
        #   Rebaixar `stake` por falta de citação MATARIA o tema por ausência de
        #   prova, e ausência de prova não é prova. Então `stake` só cai quando
        #   o modelo diz False explicitamente — a falta de citação fica gravada
        #   e não decide nada.
        if booleanos["regra_mudou_recentemente"] and not trechos.get("regra_mudou"):
            booleanos["regra_mudou_recentemente"] = False

        return cls(
            tensao=tensao,
            resposta_literal=str(d.get("resposta_literal") or "").strip(),
            consulta_dominante=str(d.get("consulta_dominante") or "").strip(),
            stake_qual=str(d.get("stake_qual") or "").strip(),
            porques={k: str(v)[:300] for k, v in (d.get("porques") or {}).items()
                     if isinstance(v, str)},
            trechos_citados=trechos,
            **contagens, **booleanos,
        )


# ── as três derivações ─────────────────────────────────────────────────────
#
# Cada eixo sai de observáveis DISTINTOS. Era a sobreposição entre eles que
# obrigava o prompt antigo a carregar uma trava de coerência: `engajamento` alto
# com `ignorancia` baixa era proibido por regra, porque os dois estavam lendo a
# mesma coisa com nomes diferentes.
#
#     engajamento  <- forma da RESPOSTA      (ramos, condições, decisão que sobra)
#     ignorancia   <- o que ELA não sabe     (condições, stake, descoberta)
#     opacidade    <- o que a INSTITUIÇÃO    (fontes, canal oficial, mudança)
#                     esconde


def nivel_engajamento(f: Ficha) -> str:
    """Quanto tempo de atenção a resposta EXIGE.

    A primeira linha é o portão. Ela é a definição operacional de
    `dado_unico`: um caminho só, nada da situação dela para resolver, e nada a
    decidir depois. A resposta se esgota, o leitor sai antes do anúncio ficar
    visível, e a viewability do domínio cai.

    ⚠️ Evidência forte e NÃO replicada fora dos nove temas originais, que são
    todos o mesmo arquétipo (consulta de registro pessoal). Ver
    `portao.NOTA_DE_REPLICACAO`.
    """
    # ⚠️ A CONDIÇÃO PESSOAL SAIU DAQUI, e a medição mandou.
    #
    # A regra exigia `condicoes_pessoais == 0`. Medido contra `Registrato` — o
    # arquétipo de consulta em base própria — a ficha contou UMA condição:
    # "faça login com sua conta Gov.br nível prata ou ouro". A contagem está
    # certa pela definição do prompt (é um fato da situação dela), e mesmo
    # assim o portão não disparava.
    #
    # Ter conta Gov.br é PRÉ-REQUISITO DE ACESSO, não ramificação da resposta.
    # A resposta continua se esgotando em segundos, que é o mecanismo inteiro:
    # o leitor sai antes do anúncio ficar visível. O que ramifica é `ramos` e o
    # que sobra é `decisao_apos_resposta`. Pré-requisito não faz nem uma coisa
    # nem outra.
    if f.ramos_de_acao <= 1 and not f.decisao_apos_resposta:
        return "dado_unico"
    # Dois estados, não cinco. Os três do meio foram medidos em dois lotes e não
    # discriminaram: o nível dominante trocou de `diagnostico` (62,5%) para
    # `condicional` (76,2%) só mudando a amostra. QUANTO sustenta continua
    # descrito pelas contagens cruas, que não fingem ordinalidade.
    return "sustenta"


def nivel_ignorancia(f: Ficha) -> str:
    """O tamanho do que ela não sabe ao chegar.

    Ordem de precedência deliberada: o portão de stake vem primeiro porque
    hiato de conhecimento sem nada em jogo não paga — quem busca uma novela tem
    hiato máximo e não lê nada além do capítulo.

    ⚠️ `nao_sei_por_que_falhou` é vocabulário legado. A derivação é UMA condição
    pessoal por resolver, não "não sabe por que falhou". O nome fica porque
    `espaco.ESCALAS` o exige; a regra é esta função.
    """
    if not f.stake:
        return "nao_preciso_de_nada"      # PORTÃO
    if f.descobre_que_existe:
        return "nao_sei_se_existe"
    if f.condicoes_pessoais >= 2:
        return "nao_sei_se_sirvo"
    if f.condicoes_pessoais == 1:
        return "nao_sei_por_que_falhou"
    if f.oficial_fecha_sozinho:
        return "sei_o_que_fazer"
    return "so_falta_um_dado"


def nivel_opacidade(f: Ficha) -> str:
    """O quanto a instituição esconde.

    Universal a qualquer burocracia: se o canal oficial resolvesse, ninguém
    leria uma explicação dele. `clara` vem por último entre as positivas porque
    regra recém-mudada e resposta espalhada vencem a clareza do canal: o site
    oficial pode estar límpido e desatualizado.
    """
    if f.regra_mudou_recentemente:
        return "regra_mudou"
    if f.fontes_oficiais >= 2:
        return "fragmentada"
    if f.oficial_fecha_sozinho:
        return "clara"
    return "ilegivel"


DERIVADOS = {
    "engajamento": nivel_engajamento,
    "ignorancia": nivel_ignorancia,
    "opacidade": nivel_opacidade,
}


def derivar(f: Ficha) -> Dict[str, str]:
    return {eixo: fn(f) for eixo, fn in DERIVADOS.items()}


# ── duas passadas: comparar CONTAGEM, não rótulo ───────────────────────────


def comparar(a: Optional[Ficha], b: Optional[Ficha]) -> Dict[str, Any]:
    """O que duas passadas viram diferente.

    Comparar as contagens, e não os níveis derivados, é o ponto: dois modelos
    podem discordar em `fontes_oficiais` sem mudar nenhum eixo, e concordar nas
    oito contagens produzindo o mesmo eixo por construção. A instabilidade que
    interessa é a do OBSERVÁVEL, porque é ela que a formulação pode consertar.
    """
    if a is None or b is None:
        return {"comparavel": False, "motivo": "ficha ausente numa das passadas"}
    campos = ("condicoes_pessoais", "ramos_de_acao", "fontes_oficiais",
              "decisao_apos_resposta", "oficial_fecha_sozinho",
              "regra_mudou_recentemente", "stake", "descobre_que_existe")
    divergem = {c: [getattr(a, c), getattr(b, c)]
                for c in campos if getattr(a, c) != getattr(b, c)}
    da, db = derivar(a), derivar(b)
    return {
        "comparavel": True,
        "contagens_iguais": not divergem,
        "divergencias": divergem,
        "eixos_iguais": da == db,
        "eixos": {"passada_1": da, "passada_2": db},
        # É o que decide o veredito do portão, e é derivado, não votado.
        "portao_passada_1": da["engajamento"] == "dado_unico",
        "portao_passada_2": db["engajamento"] == "dado_unico",
    }


# ── a entidade não tem UMA pergunta ────────────────────────────────────────
#
# `leitura.py` mediu e escreveu: "o CDB tem uma pergunta comparativa, uma
# condicional e uma de dado único, e as três estão certas. Não há amostragem
# que faça uma distribuição multimodal convergir."
#
# Congelar UMA pergunta do PAA e julgar a entidade por ela reproduz o erro do
# outro lado — medido: `DIRPF` congelado em "Quando libera a declaração de 2026?"
# devolve uma DATA, dispara `dado_unico`, e mata a entidade mais rica do lote.
# A contagem estava certa; o objeto é que era outro.
#
# Então a ficha roda em TODAS as perguntas do PAA, e a entidade carrega a
# DISTRIBUIÇÃO. `share_dado_unico` — o mesmo nome que a regra de retomada do
# `DECISOES.md` já usava sem que existisse — é o que decide o portão.

PORTAO, LIMITROFE, SEM_PORTAO = "portao", "limitrofe", "sem_portao"

LIMIAR_PORTAO_ENTIDADE = 1.0    # todas as perguntas precisam esgotar
LIMIAR_LIMITROFE = 0.5          # metade já pede humano

# ⚠️ PISO DE N, E ELE FOI MEDIDO CUSTANDO UMA ENTIDADE.
#
# "Todas as perguntas esgotam" é uma regra VAZIA quando existe uma pergunta só:
# 1/1 = 1,0 satisfaz qualquer exigência de unanimidade. E n=1 acontece de
# verdade — `consultar CPF situação cadastral` voltou com PAA vazio numa rodada
# (tinha 2 na anterior), caiu no fallback do próprio termo, e uma SERP sem bloco
# de perguntas matou a entidade com aparência de medição.
#
# Abaixo do piso o portão não dispara. O máximo que a entidade recebe é
# `limitrofe`, que é o estado que já significa "humano olha" — porque é
# exatamente isso: ninguém sabe ainda, e a diferença entre não saber e ter
# medido é a coisa que este motor inteiro existe para não borrar.
N_MINIMO_PARA_PORTAO = 3


@dataclass(frozen=True)
class Entidade:
    """O que a entidade é, somando as perguntas que as pessoas fazem sobre ela."""

    fichas: tuple                       # (pergunta, Ficha)
    share_dado_unico: float = 0.0
    niveis: Dict[str, str] = field(default_factory=dict)
    pergunta_mais_rica: str = ""
    distribuicao: Dict[str, int] = field(default_factory=dict)
    # A carga: qual aflição a entidade aciona, e em quantas das perguntas.
    tensao_dominante: Optional[str] = None
    distribuicao_de_tensao: Dict[str, int] = field(default_factory=dict)
    intensidade: Optional[float] = None
    share_com_tensao: float = 0.0
    # Das citações que o modelo deu, quantas de fato estão na resposta que ele
    # escreveu. `None` quando ele não citou nada — que é diferente de citar e
    # errar, e as duas coisas precisam de nomes diferentes na hora de decidir
    # se a exigência de citação vira trava.
    citacoes_conferidas: Optional[float] = None
    n_citacoes: int = 0
    # Perguntas em que o stake foi AFIRMADO e não sustentado. Não rebaixa nada
    # — força revisão humana, que é o único jeito de fechar a brecha sem
    # reintroduzir o risco de matar tema por formatação de string.
    stake_sem_prova: int = 0


def carga_de_leitura(f: Ficha) -> int:
    """Quanto esta resposta exige, em contagem crua. Só para ESCOLHER a pergunta
    representativa da entidade — nunca como valor de eixo.

    É soma de coisas contadas, não escala: `2 ramos + 3 condições + decisão` dá
    7 e `1 ramo + 1 condição` dá 2, e a única afirmação é que a primeira exige
    mais. Chamar isso de nível seria reintroduzir a ordinalidade que a medição
    acabou de derrubar.
    """
    return (f.ramos_de_acao + f.condicoes_pessoais
            + (2 if f.decisao_apos_resposta else 0))


# Os eixos que carregam PORTÃO. Nível que mata não pode sair de uma pergunta
# eleita: tem de sair da distribuição inteira. `espaco.PORTOES` é a fonte da
# verdade, e ler dela evita que um portão novo lá apareça aqui sem ninguém ver.
def _eixos_com_portao() -> Dict[str, tuple]:
    from app.motor_pautas.espaco import PORTOES
    return {e: n for e, n in PORTOES.items() if e in ("engajamento", "ignorancia")}


def niveis_da_entidade(derivados: Dict[str, Dict[str, str]], mais_rica: str,
                       share_dado_unico: float, n_perguntas: int) -> Dict[str, str]:
    """Os eixos da ENTIDADE. Nível que mata vem da DISTRIBUIÇÃO.

    ## O defeito que isto conserta, medido no código vivo

    Isto era `derivados[mais_rica]` — os três eixos da entidade saíam de UMA
    pergunta, eleita por `carga_de_leitura`. E `carga_de_leitura` SOMA
    `condicoes_pessoais`. Consequência:

        entidade que ramifica em 3 das 4 perguntas, com uma pergunta
        de forma calculadora (1 ramo, 3 condições):

            share_dado_unico ..... 0,25      1 de 4 esgota
            veredito_do_portao ... sem_portao
            pergunta eleita ...... "Como calculo o valor?"
            eixo engajamento ..... dado_unico     <- da eleita
            índice ............... 0,0
            perfil ............... descartar

    **Dois portões no mesmo card, discordando.** O veredito que foi blindado com
    três passadas e unanimidade governava uma string na tela; quem zerava o
    índice era este eixo, tirado de uma pergunta, de uma passada, num eixo de
    AC1 0,64 e sem réplica.

    Pior: a eleição é enviesada CONTRA a pergunta em forma de calculadora.
    Quanto mais condições pessoais ela tem, mais provável vencer a eleição e
    carimbar a entidade inteira. Em 200 mil entidades sintéticas de 4 perguntas,
    93% dos disparos do eixo acontecem com share < 1,00 — invisíveis ao veredito
    — e em metade deles a eleita é justamente a pergunta que seria a ferramenta.

    É o `DIRPF` morrendo de novo, uma camada abaixo de onde foi consertado.

    ## A regra

    ENGAJAMENTO vem do share, exatamente como `veredito_do_portao`. Os dois
    passam a concordar POR CONSTRUÇÃO, e não por coincidência.

    IGNORANCIA: só o PORTÃO vem da distribuição — a entidade é curiosidade pura
    quando NENHUMA pergunta tem stake, não quando a eleita não tem. Os outros
    cinco níveis graduam e continuam vindo da representativa.

    OPACIDADE não tem portão: continua saindo da representativa, e uma escolha
    infeliz ali custa graduação, nunca a vida do tema.

    ## O piso de N vale aqui também

    Abaixo do piso, `dado_unico` não é declarado — a entidade já sai `limitrofe`
    no veredito e está fora da fila de qualquer jeito. Declarar o portão com
    n=1 seria a mesma regra vazia que o piso existe para impedir, só que num
    lugar onde ela zera a nota em vez de mudar um rótulo.
    """
    niveis = dict(derivados[mais_rica])

    esgota_tudo = (share_dado_unico >= LIMIAR_PORTAO_ENTIDADE
                   and n_perguntas >= N_MINIMO_PARA_PORTAO)
    niveis["engajamento"] = "dado_unico" if esgota_tudo else "sustenta"

    sem_stake_em_nenhuma = all(d.get("ignorancia") == "nao_preciso_de_nada"
                               for d in derivados.values())
    if sem_stake_em_nenhuma:
        niveis["ignorancia"] = "nao_preciso_de_nada"
    elif niveis.get("ignorancia") == "nao_preciso_de_nada":
        # A eleita não tem stake, mas a entidade tem. Herdar o portão dela
        # mataria o tema por uma pergunta. Pega a graduação da pergunta com
        # stake mais rica que existir.
        com_stake = [d for d in derivados.values()
                     if d.get("ignorancia") != "nao_preciso_de_nada"]
        if com_stake:
            niveis["ignorancia"] = com_stake[0]["ignorancia"]
    return niveis


# ── o roteador de FORMATO ──────────────────────────────────────────────────
#
# O portão `dado_unico` e o perfil `mercado_rico_sem_leitura` assumiam em
# silêncio que a página é um ARTIGO DE TEXTO. A premissa nunca foi declarada e é
# falsa nesta operação: o agente redator já põe widget HTML nas páginas de
# solução. Então o portão pode não estar detectando ASSUNTO RUIM — pode estar
# detectando FORMATO ERRADO PARA A INTENÇÃO.
#
# ## Dois formatos, e o terceiro estado não é formato
#
# O painel voltou dividido (2, 3 e 5), e a arbitragem foi por PRODUÇÃO: só
# existem dois envelopes técnicos que o operador publica — texto puro, ou o
# template injetando um componente interativo. Checklist, tabela consultável e
# comparador são O MESMO ARTEFATO (2-3 campos + função + painel de saída); o que
# os distingue é o rótulo da saída, que é uma frase no prompt do redator, não um
# formato no banco. Multiplicar enum aqui é poluir schema pelo mesmo envelope.
#
#     o MOTOR decide      a página precisa de entrada manipulável?  (booleano)
#     o REDATOR decide    calculadora, filtro ou checklist          (preset)
#
# ## O que este roteador NÃO faz
#
# Não entra em `posicionar()`, não muda `indice`, `perfil`, `apto`, nem nível de
# eixo nenhum. É propriedade da PERGUNTA; o veredito é da ENTIDADE. Medido pelos
# críticos: suspender o eixo quando roteia daria 0,799 contra 0,824 de um artigo
# perfeito, com cobertura caindo só de 1,00 para 0,88 — o card-ferramenta subiria
# na fila por ter APAGADO o eixo em que falhou, e a cobertura não denunciaria.
#
# ## O invariante
#
#     formato_da_pergunta(f) == ARTIGO  <=>  nivel_engajamento(f) == "sustenta"
#
# As duas leem a mesma condição. Logo o roteador não pode matar o que hoje vive
# nem ressuscitar nada sozinho: ele só NOMEIA o que já morreu. O teste varre o
# espaço inteiro e falha se essa equivalência quebrar.

ARTIGO = "artigo"
FERRAMENTA = "artigo_com_ferramenta"
NAO_PRODUZIR = "nao_produzir"          # não é formato: é o portão, com nome

FORMATOS = (ARTIGO, FERRAMENTA)        # o que o redator precisa saber produzir

# Quantos fatos DELA a resposta exige para a página virar máquina. Dois, e não
# um, por duas razões independentes:
#
# MEDIÇÃO — `condicoes_pessoais == 1` está contaminado por PRÉ-REQUISITO DE
# ACESSO. `nivel_engajamento` já carrega o caso que custou a regra: o Registrato
# conta 1 condição ("faça login com conta Gov.br nível prata ou ouro"), que é
# porta de entrada e não variável. Campo que não varia não é campo.
#
# MECANISMO — formulário de UM campo se preenche em três segundos e devolve um
# número; não cruza o limiar de refresh (30s in-view) nem produz o refazer que
# gera a segunda impressão. Dois campos produzem COMPARAÇÃO — ela muda um valor
# e roda de novo — e é aí que a interação passa de segundos para dezenas.
MINIMO_DE_ENTRADAS = 2


def formato_da_pergunta(f: Ficha) -> str:
    """Que envelope esta pergunta pede. Puro, sem medição nova.

    ⚠️ SOBRE O VAZAMENTO DO `IPVA`, e por que ele NÃO é fechado aqui.

    `condicoes_pessoais` conta DIMENSÃO DE SELEÇÃO, não entrada de cálculo — o
    exemplo é do próprio prompt: "o valor do IPVA depende do estado e do ano do
    veículo" conta 2. Um crítico chamou isso de vazamento: a regra rotearia
    "consultar IPVA pela placa" para ferramenta, sendo consulta de tabela.

    Duas coisas respondem, e nenhuma é um nono observável:

    1. `oficial_fecha_sozinho` já barra o caso, quando o portal do estado de
       fato resolve. O veto está antes do discriminador, de propósito.

    2. E quando não barra, dois dropdowns (estado × ano) que devolvem a alíquota
       SÃO um widget: mesma interface manipulável, mesmo tempo de tela, mesma
       impressão viewable. Calculadora e filtro são o mesmo envelope — a
       distinção vive no preset do redator, não aqui.

    O que NÃO se faz é inventar um nono observável `exige_calculo_aritmetico`.
    Ele pediria ao modelo separar "4% para carros de passeio" (tabela) de uma
    instrução de cálculo, que é exatamente o tipo de juízo que já mediu mal neste
    motor. Discriminador instável no lugar de um vazamento declarado é troca
    ruim.

    ⚠️ ISTO CARREGA A CONFIABILIDADE DE `oficial_fecha_sozinho`, que é o veto e
    hoje alimenta `opacidade` (AC1 0,64). O roteador não é mais confiável que
    esse booleano, e é honesto dizer onde ele apoia o peso.
    """
    if f.ramos_de_acao >= 2 or f.decisao_apos_resposta:
        return ARTIGO                  # <=> nivel_engajamento == "sustenta"
    if f.oficial_fecha_sozinho:
        return NAO_PRODUZIR            # o balcão resolve: nenhum formato salva
    if f.condicoes_pessoais >= MINIMO_DE_ENTRADAS:
        return FERRAMENTA
    return NAO_PRODUZIR                # resposta igual para todos: lookup puro


def campos_do_widget(f: Ficha) -> str:
    """A especificação da entrada, de graça.

    `trechos_citados["condicoes_pessoais"]` é RECORTE LITERAL da resposta que o
    modelo escreveu — "se optou pelo saque-aniversário e se já passou a
    carência" — e já NOMEIA os campos. O redator recebe a especificação sem uma
    segunda chamada de LLM.
    """
    return (f.trechos_citados or {}).get("condicoes_pessoais", "")


def formatos_da_entidade(por_pergunta: Dict[str, Ficha]) -> Dict[str, Any]:
    """A prescrição da entidade: por pergunta, mais o resumo.

    Não devolve UM formato para a entidade, porque formato é propriedade da
    PÁGINA. O funil tem 5 páginas e cada uma responde a sua pergunta.
    """
    por_q = {q: formato_da_pergunta(f) for q, f in por_pergunta.items() if f}
    ferramentas = [q for q, fmt in por_q.items() if fmt == FERRAMENTA]
    return {
        "por_pergunta": por_q,
        "n_ferramenta": len(ferramentas),
        "n_artigo": sum(1 for v in por_q.values() if v == ARTIGO),
        "n_nao_produzir": sum(1 for v in por_q.values() if v == NAO_PRODUZIR),
        "prescricao": [
            {"pergunta": q,
             "campos": campos_do_widget(por_pergunta[q]),
             "n_campos": por_pergunta[q].condicoes_pessoais}
            for q in ferramentas
        ],
    }


def agregar(por_pergunta: Dict[str, Ficha]) -> Optional[Entidade]:
    """De N perguntas para uma posição de entidade."""
    validas = {q: f for q, f in por_pergunta.items() if f is not None}
    if not validas:
        return None

    derivados = {q: derivar(f) for q, f in validas.items()}
    engajamentos = [d["engajamento"] for d in derivados.values()]
    n_dado_unico = sum(1 for e in engajamentos if e == "dado_unico")

    # A pergunta representativa é a que EXIGE MAIS leitura, por contagem crua —
    # é essa a página que se escreveria. Perguntas que esgotam ficam por último
    # por construção: elas têm 1 ramo, 0 ou poucas condições e nada depois.
    mais_rica = max(validas, key=lambda q: carga_de_leitura(validas[q]))
    dist: Dict[str, int] = {}
    for e in engajamentos:
        dist[e] = dist.get(e, 0) + 1

    # ── a carga ───────────────────────────────────────────────────────────
    #
    # A tensão dominante é a MODA entre as perguntas, e `share_com_tensao` diz
    # em quantas delas alguma tensão foi reconhecida. Entidade cuja maioria das
    # perguntas sai `nenhuma` chega fria — e isso é informação, não falha.
    tensoes: Dict[str, int] = {}
    for f in validas.values():
        if f.tensao and f.tensao != "nenhuma":
            tensoes[f.tensao] = tensoes.get(f.tensao, 0) + 1
    dominante = max(tensoes, key=lambda k: tensoes[k]) if tensoes else None
    com_tensao = sum(tensoes.values())

    # ── a conferência das citações ────────────────────────────────────────
    #
    # Some as citações de todas as perguntas e mede quantas estão mesmo no
    # texto. É o número que decide, mais para a frente, se a exigência de
    # citação pode virar trava — hoje ela só mede.
    conferencias = [ok for f in validas.values()
                    for ok in f.citacoes_conferem().values()]
    taxa = round(sum(conferencias) / len(conferencias), 3) if conferencias else None
    sem_prova = sum(1 for f in validas.values() if not f.stake_validado)

    share = round(n_dado_unico / len(validas), 3)

    return Entidade(
        citacoes_conferidas=taxa,
        n_citacoes=len(conferencias),
        stake_sem_prova=sem_prova,
        fichas=tuple(validas.items()),
        share_dado_unico=share,
        niveis=niveis_da_entidade(derivados, mais_rica, share, len(validas)),
        pergunta_mais_rica=mais_rica,
        distribuicao=dist,
        tensao_dominante=dominante,
        distribuicao_de_tensao=tensoes,
        # ⚠️ PRIOR COM DÍVIDA. As intensidades da tabela (0,64 a 0,84) vieram do
        # desfecho `lucro`, que `spend` prevê com AUC 0,971 — a mesma régua
        # contaminada que aposentou a regressão. O número vai gravado para o dia
        # em que houver desfecho limpo; ele NÃO entra em conta nenhuma hoje.
        intensidade=(TENSOES[dominante]["intensidade"] if dominante else None),
        share_com_tensao=round(com_tensao / len(validas), 3),
    )


def veredito_de_passadas(shares: list, n_perguntas: int) -> str:
    """O veredito sobre TODAS as passadas, com a unanimidade no SHARE.

    ## Por que o rótulo por passada foi aposentado

    Rodada real, 4 entidades, 3 passadas cada:

        Registrato   shares 0,75 · 1,00 · 1,00   rótulos: limitrofe, portao, portao
        FGTS         shares 0,50 · 0,25 · 0,50   limitrofe, sem_portao, limitrofe
        Cesantías    shares 0,25 · 0,50 · 0,50   sem_portao, limitrofe, limitrofe

    A MEDIÇÃO é estável — as três passadas ficam dentro de UMA pergunta de
    diferença em todos os casos. O RÓTULO é que pula, e a razão é aritmética:
    com 4 perguntas do PAA o share só assume 5 valores, uma pergunta virando o
    move 0,25, e os limiares (0,5 e 1,0) caem dentro dessa banda. Metade dos
    movimentos de UMA pergunta troca o rótulo.

    O veredito de três estados por passada é frágil por construção, não por
    instabilidade do modelo — a mesma classe de defeito que já aposentou a
    escala de cinco níveis de `engajamento`: distinção que a medição não paga.

    ## A regra que sobrou

    Os dois desfechos AUTOMÁTICOS exigem unanimidade, e cada um a exige do lado
    que o protege contra o próprio erro:

        min(shares) >= 1,0   ->  portao      esgotou tudo em TODA passada
        max(shares) <  0,5   ->  sem_portao  nem na pior passada chegou à metade
        qualquer outra coisa ->  limitrofe   o humano lê o share e decide

    Note que `sem_portao` NÃO exige share zero. Toda entidade rica tem uma
    pergunta de lookup no PAA — foi o `DIRPF` que ensinou isso — e exigir zero
    mandaria toda entidade boa para revisão, que é o mesmo erro na direção
    contrária.

    O que a tela mostra não é este rótulo: é o share com a dispersão.
    `0,75 · 1,00 · 1,00` diz tudo que o rótulo dizia, sem inventar uma fronteira
    que a aritmética não sustenta.
    """
    if not shares:
        return LIMITROFE
    if n_perguntas < N_MINIMO_PARA_PORTAO:
        # Poucas perguntas: nenhum automático, nem para matar nem para aprovar.
        return LIMITROFE
    if min(shares) >= LIMIAR_PORTAO_ENTIDADE:
        return PORTAO
    if max(shares) < LIMIAR_LIMITROFE:
        return SEM_PORTAO
    return LIMITROFE


def veredito_do_portao(share: float, n_perguntas: int) -> str:
    """A régua assimétrica, agora sobre a distribuição da entidade.

    A assimetria inverteu de lado, e o motivo é o custo. Sobre UMA pergunta,
    qualquer disparo isolado rebaixava: deixar passar um `dado_unico` era o erro
    caro. Sobre a ENTIDADE, matar por uma pergunta de lookup é que é caro —
    toda entidade rica tem uma pergunta de lookup no PAA, e o `DIRPF` provou
    isso na primeira rodada.

        todas as perguntas esgotam   ->  portao       a entidade é um lookup
        metade ou mais               ->  limitrofe    o humano olha
        minoria                      ->  sem_portao   há o que escrever
    """
    if share >= LIMIAR_PORTAO_ENTIDADE and n_perguntas >= N_MINIMO_PARA_PORTAO:
        return "portao"
    if share >= LIMIAR_PORTAO_ENTIDADE:
        # Esgotou tudo o que foi perguntado — e foi perguntado pouco demais para
        # isso significar alguma coisa sobre a entidade.
        return "limitrofe"
    if share >= LIMIAR_LIMITROFE:
        return "limitrofe"
    return "sem_portao"
