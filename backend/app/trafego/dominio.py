"""O núcleo do inventário: as regras que decidem o que um número significa.

Este módulo é **domínio puro** — nenhum import de framework, nenhuma chamada de
rede, nenhum acesso a banco. Ele existe para que as três regras do inventário
tenham *um* lugar onde são decididas, e não uma cópia no backend, outra no
gatilho do Postgres e uma terceira na tela.

## As três regras, e por que elas vivem aqui

**A. Nenhum número sem frescor.** Toda medida sai acompanhada de quando foi
lida. Um custo sem data é indistinguível de um custo de ontem, e alguém decide
gasto olhando para ele. Por isso `Entrega` não existe sem `Leitura` e
`frescor_da_conta()` recusa calcular idade sem instante.

**B. Ausência é `None`, nunca zero.** Falha ao medir produz `None`; zero é um
fato medido. Foi o que a conta respondeu em 24/08: uma impressão numa campanha,
quatro na outra, **R$ 0,00 gastos** nas duas ([E-01]). Esses zeros só significam
alguma coisa enquanto não puderem ser confundidos com falha de leitura — e a
confusão é fácil de fazer, porque `0` e "não sei" imprimem parecido.

**C. Falha de uma conta não contamina as outras.** `frescor_do_conjunto()`
devolve `parcial` quando parte das contas respondeu, nunca `falhou` inteiro; e
`preservar_ultima_entrega()` mantém a última medida boa **junto do carimbo
dela**, para que dado velho não passe por novo.

## Uma regra, um lugar — e o defeito que isso fecha

Este módulo nasceu com **zero consumidores de produção**: só o próprio teste o
importava, e `inventario.py` mantinha uma segunda cópia das mesmas regras. As
duas cópias já discordavam em três pontos medidos — `{falhou, recente}` dava
`falhou` numa e `parcial` na outra; uma leitura vazia e antiga saía
`vazio_confirmado` numa e `velho` na outra; o teto de cliques aceitava
`MANUAL_CPM` numa e não na outra. Um sistema que responde diferente para a
mesma pergunta dependendo de quem perguntou não tem regra: tem duas opiniões.

Agora `inventario.py` **importa daqui**. Não há mais cópia: as funções de
frescor, teto, canal de leitura, presença projetada e atenção têm um endereço
só, e quem quiser mudar a regra muda num lugar.

## O que este módulo NÃO é

Não é camada de acesso a dados e não monta resposta HTTP. Não conhece
`keyword`, `asset_group`, `placement`, `audience` nem `match_type` — o gate de
acoplamento do SPEC §9.4 sobre este arquivo tem de dar **zero**, e há um teste
que o mede. Canal e subtipo são do núcleo (ADR-17); a semântica de cada canal,
não.

Não decide lance, orçamento nem graduação. ADR-11 continua valendo: nenhuma
regra de bidding, graduação ou automação está aprovada.

## Espelho do schema, de propósito

Os vocabulários abaixo são os mesmos das CHECK constraints de
`supabase/migrations/v9_01_trafego_inventario.sql`. A duplicação é deliberada —
o banco tem de recusar sozinho, sem depender de a aplicação lembrar — e existe
um teste que compara as duas listas. Foi exatamente uma divergência dessas,
espalhada por cinco lugares, que fez `PMAX` virar uma string que não existe em
lugar nenhum ([E-21]).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

# ---------------------------------------------------------------------------
# VOCABULÁRIOS — fechados, e iguais aos do banco
# ---------------------------------------------------------------------------

EstadoDePresenca = Literal[
    "removida",
    "nao_encontrada",
    "conta_nao_identificada",
    "fora_de_escopo",
    "sincronizacao_falhou",
    "legado_nao_reconciliado",
]

# ⚠️ Os seis nomeiam apenas EXCEÇÕES. Não há termo para "está lá, sem ressalva"
# — que é o estado da maioria das linhas. Enquanto o contrato não fechar essa
# lacuna, o caso normal é `None`, e é por isso que `presenca()` levanta quando
# não há leitura: sem essa trava, "esqueci de calcular" e "está tudo bem"
# ficariam iguais.
ESTADOS_DE_PRESENCA: frozenset[str] = frozenset(
    (
        "removida",
        "nao_encontrada",
        "conta_nao_identificada",
        "fora_de_escopo",
        "sincronizacao_falhou",
        "legado_nao_reconciliado",
    )
)

#: ⚠️ SÉTIMO VALOR, e ele é da API — não do banco.
#:
#: A CHECK `trafego_espelho_presenca_conhecida` aceita os seis acima **ou NULL**,
#: e NULL ali significa "a conta respondeu e a campanha estava lá, sem ressalva".
#: Os seis nomeiam apenas EXCEÇÕES; nenhum nomeia o caso normal, que é a maioria
#: das linhas. `presenca_projetada()` traduz esse NULL em `presente` na saída —
#: e é a ÚNICA tradução, para que "esqueci de calcular" e "está tudo bem" não
#: fiquem iguais em lugar nenhum.
PRESENTE = "presente"

#: O que a API pode emitir: os seis do banco mais `presente`. É este conjunto,
#: e não `ESTADOS_DE_PRESENCA`, que o filtro da rota valida.
PRESENCAS_NA_API: frozenset[str] = frozenset(ESTADOS_DE_PRESENCA | {PRESENTE})

Frescor = Literal[
    "recente", "velho", "parcial", "falhou", "nunca_lido", "vazio_confirmado"
]

# Os mesmos seis, como constantes nomeadas. Existem porque `inventario.py`
# endereça frescor por nome (`inv.RECENTE`) e a alternativa seria uma segunda
# lista de literais — que é exatamente a duplicação que este módulo fecha.
RECENTE = "recente"
VELHO = "velho"
PARCIAL = "parcial"
FALHOU = "falhou"
NUNCA_LIDO = "nunca_lido"
VAZIO_CONFIRMADO = "vazio_confirmado"

FRESCORES: tuple[str, ...] = (
    RECENTE, VELHO, PARCIAL, FALHOU, NUNCA_LIDO, VAZIO_CONFIRMADO,
)

PROCEDENCIAS: frozenset[str] = frozenset(
    ("volc_os", "descoberta", "legado", "desconhecida")
)

# O vocabulário canônico de canal (ADR-18): os nomes do enum do Google Ads, e
# não a lista do que sabemos construir. A distinção importa porque o ESPELHO
# tem de registrar honestamente o que a conta respondeu — inclusive um canal
# que o engine não monta. Recusar canal sem construtor é trabalho da porta de
# criação, não da leitura.
VOCABULARIO_DE_CANAL: frozenset[str] = frozenset(
    (
        "SEARCH",
        "DISPLAY",
        "DEMAND_GEN",
        "PERFORMANCE_MAX",
        "VIDEO",
        "SHOPPING",
        "DISCOVERY",
        "MULTI_CHANNEL",
        "LOCAL",
        "LOCAL_SERVICES",
        "SMART",
        "HOTEL",
        "TRAVEL",
        "UNSPECIFIED",
        "UNKNOWN",
    )
)

# Medido em 24/08 ([E-21]): existe UM construtor de grafo, `campanha/search.py`.
# Display e Demand Gen têm ajuste de campanha sem construtor; PERFORMANCE_MAX
# levanta `ValueError` no engine. Esta constante é o que permite a porta de
# criação recusar com uma mensagem que diz o que existe, em vez de deixar a
# exceção do engine vazar.
CANAIS_COM_CONSTRUTOR: frozenset[str] = frozenset(("SEARCH",))

# `PMAX` é apelido de tela e nunca valor de contrato (ADR-18). Ele não existe no
# enum do Google nem no engine: um pedido com essa string falharia tarde, no
# `getattr`, com uma mensagem que não ajuda ninguém.
APELIDOS_DE_CANAL: dict[str, str] = {"PMAX": "PERFORMANCE_MAX"}

# Estratégias que o produto usa hoje. NÃO é lista fechada de leitura, e a
# assimetria com o canal é proposital: a conta pode responder TARGET_SPEND,
# MAXIMIZE_CLICKS, TARGET_ROAS e mais meia dúzia. Só o teto de cliques depende
# de saber qual é a estratégia.
ESTRATEGIAS: frozenset[str] = frozenset(("MANUAL_CPC", "MAXIMIZE_CONVERSIONS"))

# ⚠️ SÓ `MANUAL_CPC`, e `MANUAL_CPM` saiu daqui.
#
# A lista tinha as duas ("estratégias de lance manual"), o que fazia sentido
# como categoria e nenhum como conta: `MANUAL_CPM` é lance por MIL IMPRESSÕES.
# Verba ÷ CPM não dá cliques, dá milhares de impressões — e o número saía num
# campo chamado `teto_de_cliques`, com aparência precisa e unidade errada.
#
# O critério não é "o lance é manual", é "verba ÷ lance tem a unidade CLIQUE".
ESTRATEGIAS_COM_TETO_DE_CLIQUES: frozenset[str] = frozenset(("MANUAL_CPC",))


class IdentidadeInvalida(ValueError):
    """A identidade externa não serve para endereçar uma campanha."""


class LeituraAusente(ValueError):
    """Pediram um estado que só uma leitura poderia sustentar."""


# ---------------------------------------------------------------------------
# IDENTIDADE
# ---------------------------------------------------------------------------


def normalizar_customer_id(valor: object) -> str | None:
    """Devolve a conta em dígitos, ou `None` quando ela não é conhecida.

    Aqui mora a distinção que `campaigns` perdeu. Medido em 24/08: as quatro
    linhas daquela tabela têm `customer_id = ''` — **string vazia, não nula**
    ([E-02], [E-10]) — e o filtro do INSERT que as produziu descartava apenas
    nulos, então o vazio atravessou.

    Vazio e nulo significam coisas diferentes: "não tem conta" e "não sei em que
    conta procurar" levam a ações opostas, e achatá-los apaga a diferença. Aqui
    o vazio **vira** `None`, uma vez só, na fronteira — e o banco recusa por
    CHECK qualquer coisa que não tenha passado por esta porta.

    O hífen é removido porque é como o painel do Google escreve a mesma conta
    (`801-785-1692`); mas só quando o que sobra é dígito, para que um valor
    corrompido não seja *promovido* a plausível por uma limpeza.
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    sem_hifen = texto.replace("-", "")
    if sem_hifen.isdigit() and 6 <= len(sem_hifen) <= 12:
        return sem_hifen
    raise IdentidadeInvalida(
        f"customer_id {texto!r} não é uma conta: esperados 6 a 12 dígitos. "
        "Se a conta é desconhecida, passe None — nunca string vazia."
    )


def normalizar_campaign_id(valor: object) -> str:
    """O id da campanha na conta. Sem ele não há identidade externa."""
    texto = "" if valor is None else str(valor).strip()
    if not texto.isdigit() or not 1 <= len(texto) <= 20:
        raise IdentidadeInvalida(
            f"campaign_id {texto!r} não é um id de campanha do Google Ads."
        )
    return texto


def canal_canonico(valor: object) -> str | None:
    """Traduz apelido de tela e recusa o que não existe no vocabulário.

    Devolve `None` quando a conta não informou o canal — que é diferente de
    informar um canal desconhecido, e por isso o desconhecido levanta.
    """
    if valor is None:
        return None
    texto = str(valor).strip().upper()
    if not texto:
        return None
    texto = APELIDOS_DE_CANAL.get(texto, texto)
    if texto not in VOCABULARIO_DE_CANAL:
        raise IdentidadeInvalida(
            f"canal {texto!r} está fora do vocabulário canônico. "
            f"Existem: {', '.join(sorted(VOCABULARIO_DE_CANAL))}."
        )
    return texto


#: Os canais que o CONTRATO de leitura declara (`Canal` em `src/types/trafego.ts`).
#: São seis — menos que os quinze do enum do Google, que o ESPELHO aceita.
#:
#: A assimetria é o ponto: o espelho registra honestamente o que a conta
#: respondeu, inclusive `TRAVEL`; a resposta da API só emite o que a tela sabe
#: renderizar. Emitir `TRAVEL` num campo tipado como `Canal` faria o front
#: desenhar um canal que o produto não opera.
CANAIS_DO_CONTRATO: tuple[str, ...] = (
    "SEARCH", "DISPLAY", "DEMAND_GEN", "PERFORMANCE_MAX", "VIDEO", "SHOPPING",
)

#: Apelidos aceitos na ENTRADA de filtro e traduzidos na porta (ADR-18). `PMAX`
#: chega de `src/types/trafego.ts`; `DISCOVERY` é o nome antigo de `DEMAND_GEN`
#: no enum do Google, e o espelho pode ter as duas grafias gravadas.
APELIDOS_DE_LEITURA: dict[str, str] = {
    "PMAX": "PERFORMANCE_MAX",
    "DISCOVERY": "DEMAND_GEN",
}


def canal_de_leitura(valor: object) -> str | None:
    """O canal que a RESPOSTA emite. Fora do contrato vira `None`, não levanta.

    Irmã de `canal_canonico()`, e a diferença entre as duas é a direção:

    · `canal_canonico` é a porta de ESCRITA — recusar cedo é o que impede um
      canal inventado de entrar no banco;
    · esta é a porta de LEITURA — levantar aqui derrubaria a página inteira por
      causa de uma linha que o espelho gravou legitimamente.

    O valor cru continua no espelho para a forense; o que não sai é um canal
    fora do vocabulário da tela.
    """
    texto = str(valor or "").strip().upper()
    if not texto:
        return None
    texto = APELIDOS_DE_LEITURA.get(texto, texto)
    return texto if texto in CANAIS_DO_CONTRATO else None


def canal_para_espelho(valor: object) -> str | None:
    """O canal como ele vai para `trafego_campanha_espelho`. Nunca levanta.

    ⚠️ A CHECK `trafego_espelho_canal_canonico` é FECHADA nos quinze nomes do
    enum do Google. Se a conta responder um décimo-sexto — o Google acrescenta
    valores ao enum sem avisar —, um INSERT com o valor cru seria recusado e a
    varredura INTEIRA daquela conta falharia. O sintoma apareceria como
    "sincronização falhou" numa conta que respondeu perfeitamente, que é
    exatamente o defeito que a migration evita em `estrategia` deixando a lista
    aberta.

    A saída é `UNKNOWN`, que já está no vocabulário e significa precisamente
    isto: a conta disse algo que não reconhecemos. O valor cru NÃO cabe no
    espelho — não há coluna para ele —, então quem chama declara a substituição
    em `faltou`, e a resposta da varredura diz o que foi trocado. Perder o rótulo
    é aceitável; perder a conta inteira não é.

    Nada de `PMAX` aqui: o apelido de tela não existe no enum do Google e a
    CHECK o recusaria (ADR-18).
    """
    texto = str(valor or "").strip().upper()
    if not texto:
        return None
    texto = APELIDOS_DE_CANAL.get(texto, texto)
    return texto if texto in VOCABULARIO_DE_CANAL else "UNKNOWN"


def texto_ou_nulo(valor: object) -> str | None:
    """String vazia vira `None`. É a mesma lição de `normalizar_customer_id`.

    Medido em `campaigns` ([E-02], [E-10]): quatro linhas com `customer_id = ''`
    porque o filtro do INSERT descartava apenas nulos. Vazio atravessa filtros
    de nulo, e as CHECKs `btrim(x) <> ''` do schema canônico existem para
    recusá-lo — recusa que vira varredura falhada se a fronteira não limpar.
    """
    texto = str(valor).strip() if valor is not None else ""
    return texto or None


def moeda_iso(valor: object) -> str | None:
    """Três letras maiúsculas, ou `None`. A CHECK do banco é `^[A-Z]{3}$`."""
    texto = str(valor or "").strip().upper()
    return texto if len(texto) == 3 and texto.isalpha() else None


def estrategia_de_leitura(valor: object) -> str | None:
    """A estratégia que a resposta emite. Fora do vocabulário vira `None`."""
    texto = str(valor or "").strip().upper()
    return texto if texto in ESTRATEGIAS else None


# ---------------------------------------------------------------------------
# FRESCOR — regra A
# ---------------------------------------------------------------------------

# Quanto tempo um dado continua "recente". Não é medição: é política, e por isso
# é um parâmetro com padrão declarado em vez de um número enterrado numa
# comparação. A varredura planejada roda a cada 15 minutos (SPEC §4.4), então
# dois ciclos é o limite a partir do qual a tela passa a destacar a idade.
JANELA_RECENTE_S: int = 30 * 60


@dataclass(frozen=True)
class Leitura:
    """Um instante medido, sempre acompanhado do que ele descreve."""

    lido_em: datetime
    idade_s: int

    def como_dicionario(self) -> dict[str, object]:
        return {"lido_em": _iso(self.lido_em), "idade_s": self.idade_s}


def leitura(quando: datetime | None, agora: datetime) -> Leitura | None:
    """Monta o par (instante, idade). `None` entra, `None` sai.

    A idade viaja calculada porque o consumidor que a recalcula é o consumidor
    que a esquece — e um número sem idade visível é o defeito que a regra A
    existe para impedir.
    """
    if quando is None:
        return None
    idade = int((_utc(agora) - _utc(quando)).total_seconds())
    return Leitura(lido_em=_utc(quando), idade_s=max(idade, 0))


def frescor_da_conta(
    *,
    resultado: str | None,
    lido_em: datetime | None,
    campanhas: int | None,
    agora: datetime,
    motivo: str | None = None,
    janela_recente_s: int = JANELA_RECENTE_S,
) -> Frescor:
    """Quão recente é o que a tela vai mostrar desta conta.

    `resultado is None` significa que **não houve tentativa** — no schema isso
    é a ausência de linha em `trafego_snapshot_conta`. `nunca_lido` e
    `vazio_confirmado` são fatos diferentes e a interface não pode achatá-los:
    "não perguntei" e "perguntei e não há nada" levam a ações opostas.

    ## Por que `parcial` sai de `motivo`, e não de um terceiro resultado

    `trafego_snapshot_conta` tem `CHECK (tentativa_resultado IN ('ok','falhou'))`
    — duas palavras, não três. Mas a varredura tem um terceiro desfecho real: a
    camada comum voltou e a entrega não. Guardá-lo exigiria ou uma coluna nova
    (mudar a migration da outra frente) ou um terceiro valor (quebrar a CHECK).

    A saída é que ele já está guardado: numa tentativa `ok`, `tentativa_motivo`
    preenchido só pode significar "deu certo, MENOS isto". Uma tentativa que deu
    certo inteira não tem o que explicar. Então `parcial` é **derivado**, e não
    existe uma segunda fonte da mesma verdade que possa divergir da primeira.

    ## Por que `velho` vence `vazio_confirmado`

    Uma leitura vazia de três dias atrás continua sendo de três dias atrás.
    `vazio_confirmado` responde "há campanha lá?"; `velho` responde "quando isso
    foi medido?" — e a segunda pergunta é a que decide se dá para confiar na
    primeira. Esta função respondia as duas na ordem inversa de `inventario.py`,
    o que fazia a mesma conta aparecer com frescores diferentes conforme quem
    projetava.
    """
    if resultado is None:
        return NUNCA_LIDO

    texto = str(resultado).strip()
    if texto == FALHOU:
        return FALHOU

    # ⚠️ FALHA FECHADA, e por omissão nunca para cima. Um `raise` aqui seria
    # pior: uma única linha corrompida derrubaria a projeção da resposta
    # inteira, e o operador ficaria sem inventário nenhum por causa de uma
    # conta. `velho` faz ele conferir; `recente` faria ele confiar.
    if texto not in ("ok", PARCIAL):
        return VELHO

    if lido_em is None:
        # 'ok' sem carimbo é a regra A violada na origem. Não dá para chamar de
        # recente um dado cuja data ninguém guardou.
        raise LeituraAusente(
            "leitura marcada como 'ok' sem instante de leitura: "
            "número sem frescor não sai do backend"
        )

    # ⚠️ A ORDEM ENTRE `parcial`, `velho` e `vazio_confirmado` é a MESMA de
    # `frescor_do_conjunto`, e ela precisa ser. As duas funções respondem à
    # mesma pergunta em escalas diferentes; se discordassem, uma conta sozinha
    # apareceria com um rótulo e o envelope de uma conta com outro — e o
    # operador veria o sistema discordar de si mesmo na mesma tela.
    #
    # `parcial` primeiro: "metade não voltou" é mais grave que "voltou há 40
    # minutos", e a idade não se perde — `leitura` e `ultima_leitura_boa` viajam
    # na mesma linha da resposta, com o carimbo de cada uma.
    #
    # `parcial` explícito é o vocabulário em memória do sincronizador; o
    # derivado do motivo é o que sobrevive a uma ida ao banco. Os dois chegam ao
    # mesmo lugar de propósito.
    if texto == PARCIAL or str(motivo or "").strip():
        return PARCIAL

    # `velho` antes de `vazio_confirmado`: uma leitura vazia de três dias atrás
    # continua sendo de três dias atrás. `vazio_confirmado` responde "há
    # campanha lá?"; `velho` responde "quando isso foi medido?" — e a segunda
    # decide se dá para confiar na primeira.
    if (_utc(agora) - _utc(lido_em)).total_seconds() > janela_recente_s:
        return VELHO
    if campanhas == 0:
        return VAZIO_CONFIRMADO
    return RECENTE


#: O vocabulário que esta função sabe interpretar. Qualquer coisa fora daqui é
#: tratada como idade desconhecida — ver o comentário no fim de
#: `frescor_do_conjunto`.
_FRESCORES_CONHECIDOS: frozenset[str] = frozenset(FRESCORES)

#: As duas palavras que significam "esta conta não contribuiu com dado nenhum".
_SEM_RESPOSTA: frozenset[str] = frozenset((FALHOU, NUNCA_LIDO))


def frescor_do_conjunto(frescores: list[str]) -> Frescor:
    """O frescor da resposta inteira — regra C em uma função.

    ⚠️ **Esta é a única regra de frescor de conjunto do pacote.**
    `inventario.pior_frescor` existia em paralelo e respondia diferente para a
    mesma entrada: ele era um `min` por gravidade, então `{falhou, recente}`
    saía `falhou` lá e `parcial` aqui — a diferença entre "o sistema caiu" e
    "uma conta de três caiu", que são telas e ações opostas. `pior_frescor` foi
    removido e `inventario.py` chama esta função.

    O resultado depende só do CONJUNTO de valores, nunca da ordem nem da
    repetição — é o que permite `test_tabela_de_frescor_do_conjunto` cobrir
    **todas** as combinações do vocabulário (2⁶ subconjuntos) em vez de amostras.

    A ordem das perguntas é a regra:

    1. **Alguma conta não respondeu e outra respondeu** → `parcial`. Nunca
       `falhou`: dizer que tudo falhou quando duas de três contas responderam
       apaga dado bom e induz o operador a tratar um problema pontual como
       queda geral.
    2. **Nenhuma respondeu** → `falhou` (ou `nunca_lido`, se ninguém tentou).
    3. Todas responderam → o **pior** entre elas, porque o conjunto não pode
       parecer mais fresco que a sua parte mais velha.
    """
    if not frescores:
        return NUNCA_LIDO

    # ⚠️ FALHA FECHADA. O `return "recente"` que estava aqui era o ramo PADRÃO,
    # não um ramo condicional: qualquer string fora do vocabulário — um typo,
    # uma coluna nova, um valor vindo de uma versão futura do snapshot — saía
    # como o estado MAIS otimista que existe.
    #
    # Frescor é a promessa de que o número na tela é recente. Uma promessa que
    # se emite por omissão não é promessa. Se não reconhecemos o valor, não
    # sabemos a idade, e "não sei" é `velho` — que faz o operador conferir —
    # e nunca `recente`, que faz ele confiar. A troca acontece ANTES das
    # perguntas para que um valor desconhecido nunca escape por um ramo de cima.
    conhecidos = {f if f in _FRESCORES_CONHECIDOS else VELHO for f in frescores}

    sem_resposta = conhecidos & _SEM_RESPOSTA
    com_resposta = conhecidos - _SEM_RESPOSTA

    if sem_resposta and com_resposta:
        return PARCIAL
    if sem_resposta:
        # Todas sem resposta. `falhou` domina `nunca_lido`: tentamos e não deu.
        return FALHOU if FALHOU in sem_resposta else NUNCA_LIDO

    if PARCIAL in com_resposta:
        return PARCIAL
    if VELHO in com_resposta:
        return VELHO
    if com_resposta == {VAZIO_CONFIRMADO}:
        return VAZIO_CONFIRMADO
    return RECENTE


# ---------------------------------------------------------------------------
# PRESENÇA — ADR-13
# ---------------------------------------------------------------------------


def presenca(
    *,
    customer_id: str | None,
    resultado_da_conta: str | None,
    encontrada_na_conta: bool | None,
    estado_externo: str | None = None,
    conta_no_escopo: bool = True,
    nunca_reconciliada: bool = False,
) -> str | None:
    """O que sabemos sobre a existência desta campanha.

    Devolve `None` para o caso normal — a conta respondeu e a campanha estava
    lá, sem ressalva. Os seis estados do ADR-13 nomeiam **exceções**; nenhum
    deles nomeia "está tudo bem", e inventar um sétimo termo aqui seria decidir
    sozinho um vocabulário que o contrato congelou.

    Não existe `sumiu da conta`, e a ausência dele é o ponto: *some* é
    conclusão, e a conclusão erra quando a causa real foi uma leitura que
    falhou. Cada um dos seis nomeia o que foi **observado**.

    Levanta `LeituraAusente` quando não há tentativa de leitura e a linha não é
    legado. Sem isso, "não perguntei" viraria `None` — e `None` aqui significa
    "está tudo bem". É a diferença entre não saber e afirmar que está bom.
    """
    # 1. Linha histórica sem conta: ela é visível, não ausente. Declarar
    #    ausência seria inventar uma medição, porque não sabemos onde procurar.
    if nunca_reconciliada and customer_id is None:
        return "legado_nao_reconciliado"

    # 2. Sabemos que existe, não sabemos onde. Foi o estado das quatro linhas
    #    medidas em `campaigns` ([E-02]).
    if customer_id is None:
        return "conta_nao_identificada"

    # 3. A conta existe, mas não está sob o MCC da casa ([E-13]). A varredura
    #    não a alcança, e isso não é falha nem ausência.
    if not conta_no_escopo:
        return "fora_de_escopo"

    if resultado_da_conta is None:
        if nunca_reconciliada:
            return "legado_nao_reconciliado"
        raise LeituraAusente(
            "não há leitura desta conta: presença não se deduz de nada. "
            "Grave a tentativa em trafego_snapshot_conta antes de escrever o espelho."
        )

    # 4. Não foi possível ler: não dá para afirmar presença NEM ausência.
    if resultado_da_conta == "falhou":
        return "sincronizacao_falhou"

    if encontrada_na_conta is None:
        raise LeituraAusente(
            "a conta respondeu, mas ninguém disse se a campanha estava na resposta"
        )

    # 5. A conta respondeu, a leitura foi boa, e a campanha não estava lá.
    if not encontrada_na_conta:
        return "nao_encontrada"

    # 6. Está lá, e a própria conta a declara removida.
    if (estado_externo or "").strip().upper() == "REMOVED":
        return "removida"

    return None


def presenca_projetada(armazenada: object, *, conta_falhou: bool) -> str:
    """A presença que a TELA mostra, dado o desfecho da última tentativa.

    É a tradução de mão única entre as seis palavras do banco e as sete da API,
    e ela mora aqui — e não em `inventario.py`, onde estava — para que o sino, a
    aba Atenção e a listagem não possam discordar sobre o que uma linha significa.

    Duas traduções, e as duas são deliberadas:

    · **NULO vira `presente`.** A migration grava `presenca` NULA quando não há
      anomalia nenhuma (a CHECK aceita os seis **ou** NULL). Ler esse nulo como
      "não sei" marcaria como duvidosa toda campanha viva; lê-lo como `presente`
      afirma exatamente o que a varredura observou.

    · **Conta que falhou vira `sincronizacao_falhou`, seja qual for o valor
      guardado.** Quando a conta não pôde ser lida, nenhuma afirmação sobre
      presença se sustenta — nem "está lá" nem "sumiu". O valor armazenado é a
      última verdade conhecida e fica intacto no espelho, para voltar sozinho
      quando a conta responder de novo.

    Valor fora do vocabulário — só acontece se alguém escrever na tabela por
    fora — sai como `conta_nao_identificada`: dizer "não sei onde ela está" é a
    afirmação mais fraca disponível, e é preferível a escolher um dos seis e
    afirmar algo que ninguém observou.
    """
    if conta_falhou:
        return "sincronizacao_falhou"
    texto = str(armazenada or "").strip()
    if not texto:
        return PRESENTE
    return texto if texto in PRESENCAS_NA_API else "conta_nao_identificada"


# ---------------------------------------------------------------------------
# ATENÇÃO — a condição que o sino conta e a aba lista
# ---------------------------------------------------------------------------
#
# ⚠️ UMA regra, três consumidores. O sino (`totais.atencao`), a aba Atenção
# (`filtros.atencao`) e o quadro de alertas (`alertas.py`) respondem à MESMA
# pergunta, e antes disso a resposta vinha de uma coluna gerada do banco que a
# migration canônica não tem. Ela passa a ser derivada, aqui, uma vez só.
#
# `SEM_IMPRESSAO` e `SEM_CLIQUE` são os dois sintomas que o contrato nomeia
# (`AlertaDeEntrega.sintoma`). Eles descrevem o que foi MEDIDO, não a causa.

SEM_IMPRESSAO = "sem_impressao"
SEM_CLIQUE = "sem_clique"

#: O que a conta responde quando a campanha está ligada. Qualquer outra coisa
#: (`PAUSED`, `REMOVED`) não pede atenção por não entregar: ela não deveria.
LIGADA = "ENABLED"

#: Ligada e pausada são os dois estados que o operador reconhece como "existe e
#: eu decido sobre ela". Qualquer outro (`UNSPECIFIED`, `UNKNOWN`) é presente,
#: mas não é nenhum dos dois — e a ordem operacional os separa por isso.
PAUSADA = "PAUSED"


#: Quantas horas ligada antes de "não gastou" virar alerta.
#:
#: ⚠️ NÃO É NÚMERO MEDIDO — é escolha de operação, e o mesmo 24 de
#: `volc_ads/entrega.py`. Menos que isso pega campanha que subiu à noite e
#: ainda não teve um dia de leilão; mais que isso é um dia de verba parada.
HORAS_ATE_ALERTAR: int = 24

#: Quantas impressões são precisas antes de a culpa poder ser do anúncio.
#:
#: ⚠️ PEGO NA PRÓPRIA CONTA, EM 20/08/2026, e replicado de `volc_ads/entrega.py`
#: com o mesmo valor de propósito: uma impressão em 24 horas não diz nada sobre
#: CTR, e o corte ingênuo (`impressoes > 0`) mandou o operador reescrever o
#: texto de uma campanha cujo problema era não entrar no leilão. Conselho errado
#: com cara de diagnóstico é pior que nenhum conselho.
#:
#: A duplicação com `volc_ads` está registrada: aquele módulo importa o SDK do
#: Google e não pode ser carregado no caminho de leitura (ADR-08), então o valor
#: viaja copiado. Se os dois divergirem, a tela e o diagnóstico manual passam a
#: dizer coisas diferentes sobre a mesma campanha.
IMPRESSOES_PARA_CULPAR_O_ANUNCIO: int = 100


def sintoma_de_entrega(
    *,
    estado_externo: str | None,
    impressoes: int | None,
    cliques: int | None,
) -> str | None:
    """O sintoma medido de uma campanha ligada que não converteu clique, ou `None`.

    ⚠️ Regra B em forma de ramo: `impressoes is None` NÃO é `sem_impressao`.
    "Não consegui medir" e "medi e deu zero" levam a ações opostas — a primeira
    manda conferir a varredura, a segunda manda conferir a campanha. Um `or 0`
    nesta função apagaria a diferença para sempre, e foi assim que o zero virou
    o valor mais mentiroso do sistema.

    ⚠️ O corte entre os dois sintomas NÃO é `impressoes > 0`, é
    `IMPRESSOES_PARA_CULPAR_O_ANUNCIO` — ver a constante.
    """
    if (estado_externo or "").strip().upper() != LIGADA:
        return None
    if impressoes is None:
        return None
    if cliques is not None and cliques > 0:
        return None
    if impressoes >= IMPRESSOES_PARA_CULPAR_O_ANUNCIO:
        return SEM_CLIQUE
    return SEM_IMPRESSAO


def ordem_de_revisao(sintoma: str | None) -> tuple[str, ...]:
    """O que conferir, em ordem. Didática, e sem apontar valor.

    Primeiro o que o Google diz, porque quando ele diz algo é sempre a causa.
    Depois o que muda com mais frequência e sem aviso. Nenhum item sugere um
    número: ADR-11 continua valendo — não há regra de lance aprovada, e uma
    sugestão de valor aqui seria automação disfarçada de dica.
    """
    if sintoma is None:
        return ()
    ordem = ["o que o Google está dizendo"]
    if sintoma == SEM_IMPRESSAO:
        ordem += ["o lance do grupo", "o orçamento diário"]
    else:
        ordem += ["o texto do anúncio", "a página de destino"]
    return tuple(ordem)


def merece_alerta(
    *,
    estado_externo: str | None,
    custo_micros: int | None,
    horas_ligada: float | None,
    horas_ate_alertar: int = HORAS_ATE_ALERTAR,
) -> bool:
    """Ligada há tempo bastante e sem ter gastado um centavo.

    Espelha `volc_ads.entrega.Diagnostico.alerta`, e as três recusas são as
    mesmas:

    · não está ligada → não deveria gastar, e não gastar não é sintoma;
    · gastou → está entregando, seja pouco ou muito;
    · **não sabemos há quanto tempo está ligada → NÃO alerta.**

    A terceira é a que parece defensiva e não é. `horas_ligada` sai do diário de
    eventos, e um diário que ainda não viu a campanha mudar de estado não sabe
    desde quando ela está assim. Alertar mesmo assim transformaria "acabei de
    começar a observar" em "está parada há tempo demais" — e o alerta que grita
    no primeiro dia é o alerta que ninguém lê no trigésimo.

    ⚠️ `custo_micros is None` (não medido) também não alerta, pela mesma razão:
    não medi não é não gastou. Quem cuida desse caso é `pede_atencao`, que marca
    a linha para conferência sem afirmar que ela está parada.
    """
    if (estado_externo or "").strip().upper() != LIGADA:
        return False
    if custo_micros is None or custo_micros > 0:
        return False
    if horas_ligada is None:
        return False
    return horas_ligada >= horas_ate_alertar


#: Acordo entre o nosso registro e a conta — história, não pendência.
REMOVIDA = "removida"


def pede_atencao(
    *,
    presenca_armazenada: object,
    estado_externo: str | None,
    impressoes: int | None,
    cliques: int | None,
    entrega_medida: bool,
    conta_falhou: bool = False,
) -> bool:
    """Esta campanha precisa de um olho humano agora?

    Quatro condições, e cada uma nomeia algo OBSERVADO:

    1. **A conta não pôde ser lida.** Não sabemos nada sobre ela agora, e não
       saber é motivo para olhar. Esta é a que o E-07 mediu: três contas
       falhando era visualmente idêntico a "tudo bem".
    2. **A presença tem ressalva — MENOS `removida`.** `presente` (o NULO do
       banco) não pede nada, e `removida` também não: ela é ACORDO entre o
       nosso registro e a conta. A conta diz que a campanha foi removida, e nós
       registramos isso; não há o que conferir, é história.

       `nao_encontrada` é o oposto e continua pedindo: ali a leitura foi BOA e
       a campanha não estava lá — nosso registro e a conta DISCORDAM, e a
       discordância é o que merece um olho.

       Medido na primeira varredura real: das 84 campanhas, 79 estavam
       `removida`. Sem esta exceção, 81 de 84 apareciam pedindo atenção — o
       alerta marcando o universo, que é o mesmo que alerta nenhum. É
       exatamente o que o último parágrafo desta docstring já dizia; a
       condição é que não cumpria.
    3. **Ligada e sem entrega medida.** "Está gastando e não sei quanto" é
       exatamente o estado que alguém precisa conferir. Chamar isso de "tudo
       bem" seria a regra E violada onde ela mais custa.
    4. **Ligada e com sintoma medido** — `sem_impressao` ou `sem_clique`.

    Uma campanha pausada ou removida NUNCA entra por não entregar: ela não
    deveria entregar. Marcá-la encheria a aba de linhas corretas e faria o
    operador parar de olhar — que é como um alerta morre.
    """
    # ⚠️ `removida` é testada ANTES da falha de leitura, e a ordem é a regra.
    #
    # Remoção no Google Ads é TERMINAL: uma campanha removida não volta. O
    # acordo registrado continua valendo mesmo quando a conta não pôde ser lida
    # nesta rodada — não saber o que acontece agora não desfaz o que já foi
    # acordado.
    #
    # Com a ordem invertida, uma única conta falhando devolvia as 79 removidas
    # para a fila: o sino saltaria de 2 para 81 e o operador veria "81 pedem
    # atenção" com 79 de história dentro. É exatamente o alarme que marca o
    # universo que a v9_02 tirou da tela — só que entrando pela porta dos
    # fundos, e apenas no dia em que uma conta cai, que é o pior dia para o
    # alerta ficar inútil.
    if str(presenca_armazenada or "").strip() == REMOVIDA:
        return False
    if conta_falhou:
        return True
    ressalva = str(presenca_armazenada or "").strip()
    if ressalva:
        return True
    ligada = (estado_externo or "").strip().upper() == LIGADA
    if not ligada:
        return False
    if not entrega_medida:
        return True
    return sintoma_de_entrega(
        estado_externo=estado_externo, impressoes=impressoes, cliques=cliques
    ) is not None


#: O estado que a conta usa para declarar remoção. É o enum do Google, e vale
#: como texto porque `estado_externo` no espelho é livre — a conta responde o
#: que quiser e o espelho registra honestamente.
REMOVED = "REMOVED"

#: Os degraus de `ordem_operacional`. Nomeados porque `4` sozinho num `sorted()`
#: não diz nada, e porque a view SQL usa os mesmos números.
ORDEM_ATENCAO = 0
ORDEM_LIGADA = 1
ORDEM_PAUSADA = 2
ORDEM_OUTROS_PRESENTES = 3
ORDEM_HISTORICO = 4


def e_historico(*, presenca_armazenada: object,
                estado_externo: str | None) -> bool:
    """A conta declara esta campanha como removida?

    Duas fontes para o MESMO fato, unidas por OU:

      `presenca = 'removida'`      o nosso registro de que a conta declarou
      `estado_externo = 'REMOVED'` o que a conta respondeu

    Hoje elas andam juntas — o sincronizador grava uma a partir da outra — e a
    medição de 26/08/2026 confirma: 79 e 79, as mesmas linhas. Olhar só para uma
    seria confiar que nunca se separam.

    O modo de falhar é o que decide a forma da regra. Com OU, uma campanha
    removida jamais reaparece como operacional; para uma campanha VIVA sumir do
    padrão seria preciso que ambas afirmassem remoção, o que nenhum caminho do
    código faz por acidente.

    ⚠️ `nao_encontrada` NÃO é histórico. Ali a leitura foi boa e a campanha não
    estava lá: o nosso registro e a conta DISCORDAM. `marcar_ausentes` grava
    essa presença e não toca em `estado_externo`, que segue sendo o último
    conhecido — tipicamente `ENABLED`. Tratar isso como história arquivaria uma
    divergência sem ninguém ter olhado, que é o oposto do que o ADR-13 criou o
    estado para fazer.
    """
    if str(presenca_armazenada or "").strip() == REMOVIDA:
        return True
    return (estado_externo or "").strip().upper() == REMOVED


def ordem_operacional(
    *,
    presenca_armazenada: object,
    estado_externo: str | None,
    impressoes: int | None,
    cliques: int | None,
    entrega_medida: bool,
) -> int:
    """Em que degrau esta campanha entra na lista. Menor sobe primeiro.

    A pergunta que a ordem responde é **"o que exige o operador agora?"**, e não
    "o que está mais viva?". Por isso atenção é o eixo primário: uma pausada que
    a conta não confirma (`nao_encontrada`) sobe na frente de uma ligada que
    está bem, porque a primeira é uma divergência aberta e a segunda não é nada.

    Histórico é testado ANTES de atenção, e a ordem dos dois testes é o que
    impede a lista de inverter. `pede_atencao()` já devolve `False` para
    `removida` (v9_02), mas uma conta que falhou devolve `True` para TODAS as
    campanhas dela — inclusive as removidas. Sem o histórico na frente, uma
    falha de leitura jogaria as 79 removidas para o degrau 0, à frente das 5 que
    existem. Foi essa a inversão que a v9_02 corrigiu na fila e que aqui
    voltaria pela porta dos fundos.

    ⚠️ Espelho literal do `CASE` de `v9_03_historico_e_ordem_operacional.sql`.
    Duas definições da mesma regra é o defeito, não a solução: se elas
    divergirem, a ordem do banco e a ordem que o teste afirma passam a ser
    coisas diferentes e nada na tela denuncia. `test_ordem_da_view_concorda_com_o_dominio`
    compara as duas linha a linha contra um Postgres real.
    """
    if e_historico(presenca_armazenada=presenca_armazenada,
                   estado_externo=estado_externo):
        return ORDEM_HISTORICO
    # ⚠️ `conta_falhou=False`, SEMPRE — e o parâmetro nem existe nesta função.
    #
    # `ordem_operacional` é a segunda chave do keyset do cursor, e um keyset
    # exige chave ESTÁVEL: a página seguinte é "o que vem depois desta tupla", e
    # se a tupla se move, o ponto deixa de existir.
    #
    # "A conta falhou" é fato da CONTA. Uma gravação de snapshot reescreveria o
    # degrau de todas as campanhas dela de uma vez, e o cursor emitido antes
    # passaria a apontar para o nada — a página seguinte voltaria vazia, e as
    # campanhas restantes sumiriam da listagem enquanto o cabeçalho continuava
    # contando todas.
    #
    # A falha não se perde: `pede_atencao` continua marcando essas campanhas
    # (o sino conta), e o cabeçalho do grupo declara `frescor: falhou` com o
    # motivo. O que sai daqui é só a ORDEM.
    if pede_atencao(presenca_armazenada=presenca_armazenada,
                    estado_externo=estado_externo,
                    impressoes=impressoes, cliques=cliques,
                    entrega_medida=entrega_medida,
                    conta_falhou=False):
        return ORDEM_ATENCAO
    estado = (estado_externo or "").strip().upper()
    if estado == LIGADA:
        return ORDEM_LIGADA
    if estado == PAUSADA:
        return ORDEM_PAUSADA
    return ORDEM_OUTROS_PRESENTES


# ---------------------------------------------------------------------------
# ENTREGA — regras B e C
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Entrega:
    """Uma medida de entrega. `None` é "não medi"; zero é zero medido.

    A interface renderiza os dois de formas diferentes ("—" e "0"), e nem o
    backend nem o banco convertem um no outro em lugar nenhum.
    """

    impressoes: int | None = None
    cliques: int | None = None
    custo_micros: int | None = None
    moeda: str | None = None
    lida_em: datetime | None = None

    def __post_init__(self) -> None:
        tem_numero = any(
            v is not None for v in (self.impressoes, self.cliques, self.custo_micros)
        )
        if tem_numero and self.lida_em is None:
            raise LeituraAusente(
                "entrega com número e sem carimbo de leitura: um custo sem data "
                "é indistinguível de um custo de ontem"
            )

    @property
    def foi_medida(self) -> bool:
        return self.lida_em is not None

    def como_dicionario(self, agora: datetime) -> dict[str, object]:
        return {
            "impressoes": self.impressoes,
            "cliques": self.cliques,
            "custo_micros": self.custo_micros,
            "moeda": self.moeda,
            "leitura": (
                leitura(self.lida_em, agora).como_dicionario()
                if self.lida_em is not None
                else None
            ),
        }


def preservar_ultima_entrega(nova: Entrega, anterior: Entrega | None) -> Entrega:
    """Regra C dentro da linha: falha nova não apaga a última medida boa.

    Espelha o gatilho `trafego_espelho_preserva_ultima_boa` de propósito. O
    banco garante sozinho — o escritor não precisa lembrar — e esta função
    existe para que o backend possa **exibir** o mesmo resultado sem reler a
    linha depois de gravar.

    O carimbo viaja junto com o número preservado. Preservar a medida e deixar
    o carimbo avançar seria pior que apagar: viraria dado velho passando por
    novo, que é exatamente o defeito que a regra A existe para impedir.
    """
    if anterior is None or anterior.lida_em is None:
        return nova
    if nova.lida_em is not None and nova.lida_em >= anterior.lida_em:
        return nova
    return anterior


def teto_de_cliques(
    *,
    verba_diaria_micros: int | None,
    lance_micros: int | None,
    estrategia: str | None,
) -> int | None:
    """Quantos cliques por dia a verba compra — só quando o número é real.

    Exige os dois valores **e** lance manual. Com lance automático o CPC varia
    leilão a leilão, e verba ÷ lance viraria uma divisão sobre um número que o
    Google não se comprometeu a cobrar: um teto de aparência precisa, calculado
    a partir de uma premissa falsa, é pior que nenhum teto.

    Medido em 24/08: as duas campanhas vivas eram `MANUAL_CPC` com lance de
    R$ 0,12 e verba de R$ 10 ([E-01]) — 83 cliques por dia, que é o número que a
    tela mostra.
    """
    if verba_diaria_micros is None or lance_micros is None:
        return None
    if not lance_micros:
        return None
    if (estrategia or "").strip().upper() not in ESTRATEGIAS_COM_TETO_DE_CLIQUES:
        return None
    return int(verba_diaria_micros // lance_micros)


# ---------------------------------------------------------------------------
# apoio
# ---------------------------------------------------------------------------


def inteiro_ou_nulo(valor: object) -> int | None:
    """Converte para `int` preservando a ausência. Regra B em três linhas.

    `int(v or 0)` é o idioma que apaga a diferença entre "não medi" e "medi e
    deu zero", e ele aparece naturalmente em toda fronteira de dado. Ter uma
    função nomeada é o que permite proibir o idioma: quem escreve `or 0` numa
    revisão tem onde ser mandado.
    """
    if valor is None or valor == "":
        return None
    try:
        return int(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _utc(quando: datetime) -> datetime:
    """Instante ingênuo é tratado como UTC — e a escolha é declarada.

    Comparar um `datetime` com fuso a um sem fuso levanta `TypeError` no meio de
    um cálculo de idade, e o sintoma aparece longe da causa. Assumir UTC aqui é
    seguro porque o schema grava `timestamptz` e o Postgres devolve com fuso; o
    ingênuo só aparece quando alguém constrói o valor à mão, em teste.
    """
    return quando if quando.tzinfo else quando.replace(tzinfo=timezone.utc)


def _iso(quando: datetime) -> str:
    return _utc(quando).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
