"""A intenção e a regra: por que uma campanha existe, e por que ela mudaria.

## Duas declarações, e a diferença entre elas

| | `IntencaoDeCampanha` | `RegraDeOtimizacao` |
|---|---|---|
| responde | por que esta campanha existe | por que ela mudaria |
| vida | uma, imutável | versionada, aposentável |
| quem declara | o operador, no lançamento | quem responde pela regra |
| onde mora | `trafego_intencao` | `trafego_regra_otimizacao` |

As duas são **declarações datadas com autor**, e nenhuma delas é estado
derivado. É a mesma doutrina que fez `procedencia` sair de `campaigns` na v9_01:
lá, um gatilho reescrevia `status_source` no mesmo comando em que a aplicação a
declarava, e a procedência ficou inalcançável por construção (E-08, ADR-10).

## Por que a regra é dado, e não código

Uma regra em Python não pode ser **citada** por uma proposta. Ela não tem versão
estável, não tem responsável declarado, não tem data de vigência — e o dia em
que alguém a ajusta, todas as propostas antigas passam a ser explicadas pela
regra nova. Isso reescreve retroativamente a razão de um gasto.

Guardada como dado versionado e imutável, "por que mexemos no orçamento em
12/09?" tem resposta verificável para sempre: a proposta cita `regra_id`, e
aquela linha não muda.

## As doze declarações obrigatórias

`objetivo · plataformas · canais · janela mínima · atraso de conversão · amostra
mínima · dados obrigatórios · teto de orçamento · limite de alteração ·
cooldown · confiança · condição de rollback · responsável`

Cada uma impede um acidente conhecido de automação de mídia, e os dois mais
caros estão em `_LIMITE_OBRIGATORIO` e `_AMOSTRA_OBRIGATORIA`:

* **sem amostra mínima**, um clique sem conversão "prova" que a campanha não
  funciona, e a regra pausa uma campanha que ainda não teve chance;
* **sem limite de alteração**, um erro de sinal multiplica o orçamento em vez de
  dividi-lo, e ninguém percebe até a fatura.

## T1: a máquina recomenda, o humano aplica

Este módulo **não aplica nada**. Ele avalia suficiência de evidência e diz qual
é o próximo passo. A aplicação exige uma linha de `trafego_aprovacao` com
decisão humana, e isso é imposto por FK **e** por gatilho — não por um `if`
daqui.

`T2` (a máquina aplicando sozinha) não existe no vocabulário, nem aqui nem na
CHECK do banco. A ausência é o registro da decisão do ADR-11, e ela entra por
migração — com nome, data e motivo — e não por um valor que já estava lá
esperando.

## O contrato com o Agente G

`docs/growth-engine/legado-n8n/regras-canonicas.json` descreve as regras
herdadas do n8n neste mesmo formato. `validar_regra_canonica()` é o validador do
contrato, e `backend/tests/test_intencao_regras_canonicas.py` roda o arquivo
inteiro contra ele assim que ele existir. Enquanto não existir, **este módulo é
o contrato**.

Sem I/O: nenhum import de rede, de SDK ou de Supabase.
"""
from __future__ import annotations

from dataclasses import MISSING, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ═══════════════════════════════════════════════════════════════════════════
# VOCABULÁRIO — os mesmos termos que as CHECKs da v10_02 aceitam
# ═══════════════════════════════════════════════════════════════════════════

PLATAFORMAS: Tuple[str, ...] = ("GOOGLE_ADS", "META_ADS")

#: O vocabulário canônico de canal (ADR-18) mais o coringa `*`. O coringa existe
#: para a regra de conta: sem ele, uma regra de orçamento teria de listar treze
#: canais e sairia errada no dia em que o Google criar o décimo quarto.
CANAIS: Tuple[str, ...] = (
    "*", "SEARCH", "DISPLAY", "DEMAND_GEN", "PERFORMANCE_MAX",
    "VIDEO", "SHOPPING", "DISCOVERY", "MULTI_CHANNEL",
    "LOCAL", "LOCAL_SERVICES", "SMART", "HOTEL", "TRAVEL",
)

#: ⚠️ `T2` não está aqui, e a ausência é o ponto. Ver o docstring do módulo.
NIVEIS_DE_AUTONOMIA: Tuple[str, ...] = ("T0", "T1")

SUFICIENCIAS: Tuple[str, ...] = ("suficiente", "insuficiente", "nao_avaliada")

ESTADOS_DA_PROPOSTA: Tuple[str, ...] = (
    "aguardando_aprovacao", "aprovada", "recusada", "expirada",
    "aplicada", "revertida", "cancelada",
)

#: Espelha o `CASE` de `trafego_proposta_painel.proximo_passo`.
PASSOS: Tuple[str, ...] = (
    "verificar", "acompanhar", "nada", "expirar", "aplicar", "aguardar_humano",
)

#: As medidas que uma regra pode exigir em `dados_obrigatorios`. Fechada porque
#: cada termo aqui tem de ter uma coluna correspondente em `trafego_evidencia`:
#: um nome que ninguém sabe medir viraria uma regra que nunca pode ser avaliada,
#: e o sintoma seria silêncio — a regra simplesmente não dispararia nunca.
MEDIDAS: Tuple[str, ...] = (
    "impressoes", "cliques", "custo_micros", "conversoes",
    "valor_conversao_micros",
)


class ErroDeIntencao(ValueError):
    """Recusa do domínio. Nunca vira 500 sem mensagem."""


# ═══════════════════════════════════════════════════════════════════════════
# A INTENÇÃO
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class IntencaoDeCampanha:
    """`CampaignIntent`. O que se quer alcançar, declarado com autor e base.

    ⚠️ **Imutável**, e não "editável com histórico". A intenção é a pergunta que
    o lote responde; reescrever a pergunta depois da resposta faz o par contar
    uma história que ninguém viveu. Mudou a intenção? É outra intenção, com
    outro id — o custo é uma linha, e o benefício é que "por que criamos esta
    campanha?" sempre tem resposta verificável.

    `campaign_lineage_id` é a SEGUNDA identidade do sistema (ADR-02): a que
    atravessa relançamentos e plataformas. A primeira — a da instância — só
    nasce quando a campanha existe, e mora em `trafego_lote_item`.
    """

    intencao_id: str
    plataforma: str
    conta_externa: str
    objetivo: str
    rotulo: str
    declarada_por: str
    declarada_com_base_em: str
    campaign_lineage_id: Optional[str] = None
    destino_url: Optional[str] = None
    verba_diaria_teto_micros: Optional[int] = None
    moeda: Optional[str] = None
    motivo: Optional[str] = None
    evidencia: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.plataforma not in PLATAFORMAS:
            raise ErroDeIntencao(
                f"plataforma {self.plataforma!r} não existe. As plataformas "
                f"são: {', '.join(PLATAFORMAS)}.")
        for campo in ("intencao_id", "conta_externa", "objetivo", "rotulo",
                      "declarada_por"):
            if not str(getattr(self, campo) or "").strip():
                raise ErroDeIntencao(f"{campo} vazio.")
        # "Com base em quê" não é opcional: uma intenção sem base declarada é um
        # palpite com carimbo de decisão, e é exatamente ela que ninguém
        # consegue auditar seis meses depois.
        if not str(self.declarada_com_base_em or "").strip():
            raise ErroDeIntencao(
                "intenção sem base declarada é palpite com carimbo de decisão.")
        # Verba sem moeda é um número que ninguém sabe ler: R$ 50 e US$ 50 não
        # são o mesmo teto. Mesma CHECK do banco.
        if self.verba_diaria_teto_micros is not None:
            if self.verba_diaria_teto_micros < 0:
                raise ErroDeIntencao("teto negativo não é teto.")
            if not self.moeda:
                raise ErroDeIntencao(
                    "teto de verba sem moeda. R$ 50 e US$ 50 não são o mesmo "
                    "teto, e o motor compararia o número com um limite em outra "
                    "unidade.")


# ═══════════════════════════════════════════════════════════════════════════
# A REGRA DE OTIMIZAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

_AMOSTRA_OBRIGATORIA = (
    "amostra_minima_cliques", "amostra_minima_impressoes",
    "amostra_minima_conversoes",
)
_LIMITE_OBRIGATORIO = (
    "limite_alteracao_pct", "limite_alteracao_absoluto_micros",
)


@dataclass(frozen=True)
class RegraDeOtimizacao:
    """`OptimizationRule`. Uma versão publicada, imutável.

    A identidade estável é `chave`; `versao` distingue as publicações. O cooldown
    é por `chave` e não por versão — publicar a v2 não pode zerar a carência que
    a v1 acabou de impor sobre a mesma campanha, que seria a rota mais fácil para
    uma regra brigar consigo mesma.
    """

    chave: str
    versao: int
    titulo: str
    objetivo: str
    plataformas: Tuple[str, ...]
    canais: Tuple[str, ...]
    janela_minima_dias: int
    atraso_conversao_dias: int
    frescor_maximo_horas: int
    dados_obrigatorios: Tuple[str, ...]
    cooldown_horas: int
    confianca_minima: float
    condicao_rollback: str
    rollback_janela_horas: int
    responsavel: str
    fonte: str
    declarada_por: str
    amostra_minima_cliques: Optional[int] = None
    amostra_minima_impressoes: Optional[int] = None
    amostra_minima_conversoes: Optional[float] = None
    teto_orcamento_micros: Optional[int] = None
    teto_orcamento_moeda: Optional[str] = None
    limite_alteracao_pct: Optional[float] = None
    limite_alteracao_absoluto_micros: Optional[int] = None
    nivel_autonomia: str = "T1"
    deteccao: Mapping[str, Any] = field(default_factory=dict)
    acao: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validar_campos(self.__dict__)

    def aplica_a(self, plataforma: str, canal: Optional[str]) -> bool:
        """`*` em `canais` vale para qualquer canal, inclusive um desconhecido.

        Canal `None` — campanha cujo espelho não trouxe o canal — só casa com o
        coringa. Deixá-lo casar com uma regra de canal específico seria aplicar
        uma regra de Search a algo que talvez seja PMax, e as duas medem coisas
        diferentes.
        """
        if plataforma not in self.plataformas:
            return False
        if "*" in self.canais:
            return True
        return canal is not None and canal in self.canais


def _exigir(cond: bool, msg: str) -> None:
    if not cond:
        raise ErroDeIntencao(msg)


def _validar_campos(d: Mapping[str, Any]) -> None:
    """As mesmas regras das CHECKs da v10_02, do lado de cá.

    Existir nos dois lugares não é duplicação inútil: aqui a recusa vira uma
    mensagem antes de a linha sair; lá ela vira a garantia de que nenhum caminho
    grava uma regra sem limite — nem um script solto, nem um backfill.
    """
    chave = str(d.get("chave") or "")
    _exigir(bool(chave) and chave.replace("_", "").isalnum()
            and chave[0].isalpha() and chave == chave.lower() and len(chave) >= 3,
            f"chave {chave!r} inválida: minúsculas, dígitos e `_`, "
            f"começando por letra, com 3+ caracteres.")
    _exigir(int(d.get("versao") or 0) >= 1, "versão começa em 1.")

    for campo in ("titulo", "objetivo", "condicao_rollback", "responsavel",
                  "fonte", "declarada_por"):
        _exigir(bool(str(d.get(campo) or "").strip()),
                f"{campo} não pode ser vazio.")

    plataformas = tuple(d.get("plataformas") or ())
    _exigir(bool(plataformas) and all(p in PLATAFORMAS for p in plataformas),
            f"plataformas inválidas: {plataformas!r}.")
    canais = tuple(d.get("canais") or ())
    _exigir(bool(canais) and all(c in CANAIS for c in canais),
            f"canais inválidos: {canais!r}. Use o enum do Google ou `*`.")

    _exigir(int(d.get("janela_minima_dias") or 0) >= 1,
            "janela mínima abaixo de 1 dia transforma ruído em diagnóstico.")
    _exigir(int(d.get("atraso_conversao_dias") if
                d.get("atraso_conversao_dias") is not None else -1) >= 0,
            "atraso de conversão precisa ser declarado (0 é um valor válido; "
            "ausente não é).")
    _exigir(int(d.get("frescor_maximo_horas") or 0) >= 1,
            "frescor máximo abaixo de 1h não é avaliável.")
    _exigir(int(d.get("cooldown_horas") or 0) >= 1,
            "cooldown abaixo de 1h deixa a regra brigar consigo mesma.")
    _exigir(int(d.get("rollback_janela_horas") or 0) >= 1,
            "janela de rollback abaixo de 1h não observa nada.")

    conf = d.get("confianca_minima")
    _exigir(conf is not None and 0 < float(conf) <= 1,
            f"confiança mínima fora de (0, 1]: {conf!r}.")

    dados = tuple(d.get("dados_obrigatorios") or ())
    _exigir(bool(dados), "regra sem dados obrigatórios não tem como declarar "
                         "suficiência de evidência.")
    desconhecidos = [m for m in dados if m not in MEDIDAS]
    _exigir(not desconhecidos,
            f"dados obrigatórios sem coluna correspondente em "
            f"trafego_evidencia: {desconhecidos!r}. Uma regra que exige o que "
            f"ninguém mede nunca dispara, e o sintoma é silêncio.")

    # ⚠️ Uma amostra mínima, pelo menos. Sem piso, a regra dispara sobre 1 clique
    # e chama isso de diagnóstico — a forma mais comum de uma automação de mídia
    # matar uma campanha nova.
    _exigir(any(d.get(c) is not None for c in _AMOSTRA_OBRIGATORIA),
            "regra sem amostra mínima dispara sobre um clique. Declare pelo "
            f"menos um de: {', '.join(_AMOSTRA_OBRIGATORIA)}.")
    # ⚠️ Um limite de alteração, pelo menos. Sem limite, um erro de sinal
    # multiplica o orçamento em vez de dividi-lo.
    _exigir(any(d.get(c) is not None for c in _LIMITE_OBRIGATORIO),
            "regra sem limite de alteração não é T1: é uma automação com "
            f"autorização ilimitada. Declare {' ou '.join(_LIMITE_OBRIGATORIO)}.")

    pct = d.get("limite_alteracao_pct")
    _exigir(pct is None or (0 < float(pct) <= 100),
            f"limite percentual fora de (0, 100]: {pct!r}.")
    absoluto = d.get("limite_alteracao_absoluto_micros")
    _exigir(absoluto is None or int(absoluto) >= 0,
            "limite absoluto negativo não é limite.")

    teto = d.get("teto_orcamento_micros")
    moeda = d.get("teto_orcamento_moeda")
    _exigir((teto is None) == (moeda is None),
            "teto de orçamento e moeda são um par indivisível: um número sem "
            "unidade não pode ser comparado com nada.")
    _exigir(moeda is None or (isinstance(moeda, str) and len(moeda) == 3
                              and moeda.isupper()),
            f"moeda fora do ISO-4217: {moeda!r}.")

    nivel = d.get("nivel_autonomia", "T1")
    _exigir(nivel in NIVEIS_DE_AUTONOMIA,
            f"nível de autonomia {nivel!r} não existe. T2 — a máquina aplicando "
            f"sozinha — não está aprovado (ADR-11) e entra por migração, não "
            f"por um valor esquecido no vocabulário.")


def validar_regra_canonica(bruta: Mapping[str, Any]) -> RegraDeOtimizacao:
    """O validador do contrato com `regras-canonicas.json` (Agente G).

    Ele aceita listas onde o dataclass quer tuplas — JSON não tem tupla — e
    recusa **campo desconhecido**, em vez de ignorá-lo. Ignorar seria pior que
    recusar: uma regra migrada do n8n com `max_budget` (em vez de
    `teto_orcamento_micros`) passaria calada e rodaria SEM TETO, que é o oposto
    do que o arquivo pretendia dizer.
    """
    if not isinstance(bruta, Mapping):
        raise ErroDeIntencao(f"regra não é objeto: {type(bruta).__name__}.")

    conhecidos = set(RegraDeOtimizacao.__dataclass_fields__)
    sobrando = sorted(set(bruta) - conhecidos)
    if sobrando:
        raise ErroDeIntencao(
            f"campo(s) desconhecido(s) na regra {bruta.get('chave')!r}: "
            f"{', '.join(sobrando)}. Ignorá-los faria uma regra rodar sem o "
            f"limite que o arquivo pretendia declarar.")

    # Sem default e sem default_factory = obrigatorio. Derivado do dataclass, e
    # nao escrito a mao: uma lista paralela ficaria desatualizada no primeiro
    # campo novo, e o sintoma seria uma regra aceita sem ele.
    obrigatorios = [
        c for c, f in RegraDeOtimizacao.__dataclass_fields__.items()
        if f.default is MISSING and f.default_factory is MISSING]
    faltando = sorted(c for c in obrigatorios if c not in bruta)
    if faltando:
        raise ErroDeIntencao(
            f"regra {bruta.get('chave')!r} sem: {', '.join(faltando)}.")

    dados = dict(bruta)
    for campo in ("plataformas", "canais", "dados_obrigatorios"):
        if campo in dados and dados[campo] is not None:
            dados[campo] = tuple(dados[campo])
    return RegraDeOtimizacao(**dados)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
# O LEGADO DO n8n — o adaptador, e o que ele deliberadamente NÃO inventa
# ═══════════════════════════════════════════════════════════════════════════
#
# `docs/growth-engine/legado-n8n/regras-canonicas.json` (Agente G) é um
# **inventário forense do que o legado declarou**; `trafego_regra_otimizacao` é
# o **contrato do que pode ser publicado**. São dois documentos com propósitos
# diferentes, e o mapeamento entre eles é o que revela a distância.
#
# ⚠️ Medido em 26/08/2026: as 19 regras do arquivo estão em `estado: proposta` e
# NENHUMA é publicável como está. Isso não é defeito de nenhum dos dois lados —
# é o achado. O legado impunha limites dentro de um `if` de workflow; aqui o
# limite tem de ser DECLARADO para poder ser imposto pelo gatilho
# `trafego_proposta_respeita_regra`. Um `null` no arquivo significa "não
# sabemos", e o adaptador **não preenche nenhum deles**: inventar um cooldown
# de 24h porque a coluna é `NOT NULL` seria transformar uma lacuna conhecida
# numa política com aparência de decidida.

#: Campo do arquivo do Agente G → coluna de `trafego_regra_otimizacao`.
#: `None` marca campo FORENSE: ele descreve a arqueologia (de qual flow veio,
#: o que falta, que literais o código tinha) e não tem coluna aqui de propósito.
#:
#: O mapa é conferido nos dois sentidos por
#: `test_intencao_regras_canonicas.py`: nenhum campo do arquivo pode ficar de
#: fora em silêncio, porque um campo ignorado é um limite que o arquivo
#: pretendia declarar e a regra rodaria sem.
MAPA_DO_LEGADO: Dict[str, Optional[str]] = {
    "id": "chave",
    "titulo": "titulo",
    "objetivo": "objetivo",
    "canais_aplicaveis": "canais",
    "janela_minima_dias": "janela_minima_dias",
    "atraso_de_conversao_dias": "atraso_conversao_dias",
    "amostra_minima": "amostra_minima_cliques",
    "dados_obrigatorios": "dados_obrigatorios",
    "teto_de_orcamento": "teto_orcamento_micros",
    "limite_de_alteracao": "limite_alteracao_pct",
    "cooldown_horas": "cooldown_horas",
    "confianca": "confianca_minima",
    "condicao_de_rollback": "condicao_rollback",
    "responsavel": "responsavel",
    "aprovacao_humana_obrigatoria": "nivel_autonomia",
    # ── forense: arqueologia, não política ──────────────────────────────────
    "estado": None,
    "ficha": None,
    "gatilho": None,
    "origem_legado": None,
    "pendencias": None,
    "valores_do_legado": None,
    "universal_demais_no_legado": None,
}

#: Colunas que o arquivo do legado **não tem campo nenhum** para preencher.
#: Não são esquecimento do Agente G: o legado nunca declarou nenhuma delas.
#: `frescor_maximo_horas` é a mais cara — sem ela, uma regra do n8n decidia com
#: o dado que estivesse na mão, sem piso de idade.
SEM_EQUIVALENTE_NO_LEGADO: Tuple[str, ...] = (
    "frescor_maximo_horas", "rollback_janela_horas",
)


def adaptar_regra_do_legado(bruta: Mapping[str, Any]
                            ) -> Tuple[Dict[str, Any], Tuple[str, ...]]:
    """`(campos, lacunas)` — o que dá para traduzir, e o que o legado não disse.

    O adaptador **traduz nomes e achata estruturas**; ele nunca inventa valor.
    Onde o legado traz `null`, ou traz prosa onde a coluna quer número, o campo
    sai do dicionário e o nome dele entra em `lacunas`. Quem decide o que fazer
    com a lacuna é gente, publicando uma versão da regra com o número declarado.

    Os quatro achatamentos que mais custam, e por que cada um vira lacuna:

    * `amostra_minima` é `{cliques, conversoes, impressoes, dias}` — `dias` não
      é amostra, é janela, e já tem coluna própria;
    * `limite_de_alteracao` no legado é **por modo**
      (`EXPLORATION`/`CALIBRATION`/`PRODUCTION`), e a coluna é escalar. Escolher
      um dos três aqui seria decidir sozinho qual regime vale;
    * `confianca` no legado é prosa (`{"exige": "...", "se_...": "..."}`) e a
      coluna é um número em (0,1];
    * `teto_de_orcamento` no legado é fórmula em texto
      (`max(budget*0.30, min(10, budget))`), e a coluna é micros + moeda.
    """
    campos: Dict[str, Any] = {}
    lacunas: List[str] = []

    def falta(nome: str) -> None:
        if nome not in lacunas:
            lacunas.append(nome)

    campos["chave"] = str(bruta.get("id") or "")
    campos["titulo"] = bruta.get("titulo") or ""
    campos["objetivo"] = bruta.get("objetivo") or ""
    campos["canais"] = tuple(bruta.get("canais_aplicaveis") or ())
    campos["dados_obrigatorios"] = tuple(bruta.get("dados_obrigatorios") or ())

    # A plataforma é implícita no legado: todo o `orakul-vos-auto-adjust` fala
    # com o Google Ads. Derivar isto é seguro; derivar um cooldown não seria.
    campos["plataformas"] = ("GOOGLE_ADS",)
    campos["versao"] = 1
    origem = bruta.get("origem_legado") or {}
    campos["fonte"] = (f"legado_n8n:{origem.get('flow', '?')}"
                       f"#{origem.get('no', '?')}")
    campos["declarada_por"] = "legado_n8n"
    campos["deteccao"] = {"gatilho": bruta.get("gatilho")}
    campos["acao"] = {}

    for coluna, valor in (("janela_minima_dias", bruta.get("janela_minima_dias")),
                          ("atraso_conversao_dias",
                           bruta.get("atraso_de_conversao_dias")),
                          ("cooldown_horas", bruta.get("cooldown_horas"))):
        if isinstance(valor, int) and not isinstance(valor, bool):
            campos[coluna] = valor
        else:
            falta(coluna)

    amostra = bruta.get("amostra_minima") or {}
    algum = False
    for coluna, chave in (("amostra_minima_cliques", "cliques"),
                          ("amostra_minima_impressoes", "impressoes"),
                          ("amostra_minima_conversoes", "conversoes")):
        valor = amostra.get(chave) if isinstance(amostra, Mapping) else None
        if valor is not None:
            campos[coluna] = valor
            algum = True
    if not algum:
        falta("amostra_minima")

    # ⚠️ Não há tradução automática possível daqui para baixo. Cada um destes
    # exige uma DECISÃO humana, e o adaptador registra a lacuna em vez de tomá-la.
    teto = bruta.get("teto_de_orcamento")
    if isinstance(teto, int) and not isinstance(teto, bool):
        campos["teto_orcamento_micros"] = teto
        campos["teto_orcamento_moeda"] = "BRL"
    elif teto is not None:
        falta("teto_de_orcamento (é fórmula em texto, e a coluna é micros+moeda)")

    limite = bruta.get("limite_de_alteracao")
    if isinstance(limite, (int, float)) and not isinstance(limite, bool):
        campos["limite_alteracao_pct"] = abs(float(limite)) * 100
    else:
        falta("limite_de_alteracao"
              + (" (o legado o declara POR MODO, e a coluna é escalar)"
                 if isinstance(limite, Mapping) else ""))

    conf = bruta.get("confianca")
    if isinstance(conf, (int, float)) and not isinstance(conf, bool):
        campos["confianca_minima"] = float(conf)
    else:
        falta("confianca"
              + (" (o legado a declara em prosa, e a coluna é número em (0,1])"
                 if isinstance(conf, Mapping) else ""))

    rollback = bruta.get("condicao_de_rollback")
    if isinstance(rollback, str) and rollback.strip():
        campos["condicao_rollback"] = rollback
    else:
        falta("condicao_de_rollback")

    resp = bruta.get("responsavel") or {}
    aprovador = resp.get("aprovador_humano") if isinstance(resp, Mapping) else None
    if aprovador:
        campos["responsavel"] = str(aprovador)
    else:
        # ⚠️ `dominio` não é responsável: um domínio não aposenta uma regra
        # quando ela passa a errar. Só uma pessoa faz isso.
        falta("responsavel.aprovador_humano")

    # `aprovacao_humana_obrigatoria: false` é EXATAMENTE o que a v10_02 recusa —
    # seria T2, e T2 não existe no vocabulário (ADR-11). O adaptador não o
    # traduz para T1 em silêncio: isso apagaria a diferença entre uma regra que
    # o legado queria automática e uma que ele já queria supervisionada.
    if bruta.get("aprovacao_humana_obrigatoria") is False:
        falta("aprovacao_humana_obrigatoria=false (seria T2; T2 não existe)")
    campos["nivel_autonomia"] = "T1"

    for coluna in SEM_EQUIVALENTE_NO_LEGADO:
        falta(f"{coluna} (o legado nunca declarou este limite)")

    return campos, tuple(lacunas)


def publicavel(bruta: Mapping[str, Any]) -> Tuple[bool, Tuple[str, ...]]:
    """`(pode_publicar, lacunas)` para uma regra do inventário do legado.

    Uma regra só é publicável quando o adaptador não deixou lacuna E o
    validador aceita o resultado. As duas condições, e não uma: o adaptador
    mede o que o legado não disse, e o validador mede se o que ele disse é
    defensável.
    """
    campos, lacunas = adaptar_regra_do_legado(bruta)
    if lacunas:
        return False, lacunas
    try:
        validar_regra_canonica(campos)
    except ErroDeIntencao as e:
        return False, (str(e),)
    return True, ()


# ═══════════════════════════════════════════════════════════════════════════
# SUFICIÊNCIA DE EVIDÊNCIA
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Suficiencia:
    """O veredito, com o que faltou nomeado.

    Três estados, e o do meio importa: `nao_avaliada` diz "ninguém olhou" e
    `insuficiente` diz "olhei e falta". Nenhuma das duas autoriza uma proposta —
    o gatilho `trafego_proposta_respeita_regra` recusa as duas —, mas só a
    segunda diz o que falta.
    """

    veredito: str
    motivo: Optional[str] = None
    faltantes: Tuple[str, ...] = ()

    @property
    def suficiente(self) -> bool:
        return self.veredito == "suficiente"


def _para_datetime(bruto: Any) -> Optional[datetime]:
    """Converte para `datetime` com fuso, ou devolve `None`.

    ⚠️ `date` precisa estar aqui, e a ordem dos `isinstance` importa.

    `datetime` É subclasse de `date`, mas o contrário não vale: um `date` puro
    caía no `return None` final e virava "janela ausente" — silenciosamente, na
    função que decide se uma recomendação tem lastro. O PostgREST devolve
    string, mas qualquer caminho que passe pelo driver do Postgres, ou um teste
    que escreva `date(2026, 8, 1)`, entrega `date`.
    """
    if isinstance(bruto, datetime):
        return bruto if bruto.tzinfo else bruto.replace(tzinfo=timezone.utc)
    if isinstance(bruto, date):
        # Meia-noite UTC: a janela é um intervalo de dias, e a hora não é
        # medida. Assumir o início do dia é a leitura conservadora para
        # `janela_inicio` e para `janela_fim` — em `fim` ela ENCURTA a janela,
        # nunca a alonga, então ela não fabrica suficiência.
        return datetime(bruto.year, bruto.month, bruto.day, tzinfo=timezone.utc)
    if isinstance(bruto, str) and bruto:
        try:
            d = datetime.fromisoformat(bruto.replace("Z", "+00:00"))
        except ValueError:
            return None
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return None


def avaliar_suficiencia(evidencia: Mapping[str, Any], regra: RegraDeOtimizacao,
                        *, agora: Optional[datetime] = None) -> Suficiencia:
    """As cinco perguntas que separam evidência de palpite.

    1. **as medidas obrigatórias estão presentes?** `None` é ausência, e ausência
       não vira zero — zero seria uma afirmação que ninguém observou;
    2. **a janela é longa o bastante?** Abaixo de `janela_minima_dias`, o dado é
       ruído com aparência de tendência;
    3. **o atraso de conversão já passou?** Conversão chega dias depois do
       clique; sem esperar, toda campanha nova parece um fracasso;
    4. **a amostra chegou ao piso?** Sem isso, um clique sem conversão "prova"
       algo;
    5. **o dado é fresco o bastante?** Decidir hoje com dado de três semanas
       atrás é decidir sobre um mundo que não existe mais.

    ⚠️ `agora` é parâmetro e não `datetime.now()` escondido lá dentro: uma função
    que lê o relógio por conta própria não é testável, e a única forma de
    exercitar o ramo (3) seria esperar três dias.
    """
    agora = agora or datetime.now(timezone.utc)
    faltantes: List[str] = []

    # (1) presença
    for medida in regra.dados_obrigatorios:
        if evidencia.get(medida) is None:
            faltantes.append(medida)
    if faltantes:
        return Suficiencia(
            "insuficiente",
            f"a regra {regra.chave} exige {', '.join(regra.dados_obrigatorios)} "
            f"e a evidência não trouxe {', '.join(faltantes)}. Ausência não vira "
            f"zero: zero seria uma afirmação que ninguém observou.",
            tuple(faltantes))

    inicio = _para_datetime(evidencia.get("janela_inicio"))
    fim = _para_datetime(evidencia.get("janela_fim"))
    colhida = _para_datetime(evidencia.get("colhida_em"))

    if colhida is None:
        return Suficiencia("insuficiente",
                           "evidência sem `colhida_em`: um número sem carimbo é "
                           "indistinguível de um número de ontem.",
                           ("colhida_em",))

    # (2) janela mínima
    #
    # ⚠️ Janela AUSENTE não é janela suficiente. O `if` abaixo pulava as
    # checagens 2 e 3 inteiras quando `inicio` ou `fim` não vinham, e a função
    # seguia para a amostra e podia devolver "suficiente" — numa regra que
    # declara `janela_minima_dias`. É a mesma família do delta ausente passando
    # como "dentro do limite": a omissão atravessa o teto e o registro afirma
    # que ele foi conferido.
    #
    # A exigência é INCONDICIONAL, e isso não é rigor gratuito: o próprio
    # domínio recusa construir regra com `janela_minima_dias` abaixo de 1
    # ("janela mínima abaixo de 1 dia transforma ruído em diagnóstico"). Não
    # existe regra que dispense a janela, então um `if` sobre isso seria um ramo
    # que nunca é falso — o código morto com nome bonito que o ADR-19 proíbe.
    if inicio is None or fim is None:
        faltando = tuple(c for c, v in (("janela_inicio", inicio), ("janela_fim", fim))
                         if v is None)
        return Suficiencia(
            "insuficiente",
            f"a regra {regra.chave} exige janela mínima de "
            f"{regra.janela_minima_dias} dia(s), e a evidência não declara "
            f"{' nem '.join(faltando)}. Sem saber o período medido não dá para "
            f"dizer que ele é longo o bastante.",
            faltando)

    if inicio is not None and fim is not None:
        dias = (fim - inicio).days + 1
        if dias < regra.janela_minima_dias:
            return Suficiencia(
                "insuficiente",
                f"janela de {dias} dia(s) contra o mínimo de "
                f"{regra.janela_minima_dias} da regra {regra.chave}.",
                ("janela",))

        # (3) atraso de conversão
        if regra.atraso_conversao_dias > 0:
            maduro_em = fim + timedelta(days=regra.atraso_conversao_dias)
            if colhida < maduro_em:
                return Suficiencia(
                    "insuficiente",
                    f"a janela fechou em {fim.date()} e a regra declara "
                    f"{regra.atraso_conversao_dias} dia(s) de atraso de "
                    f"conversão; a leitura de {colhida.date()} ainda não os "
                    f"cobriu. Conversão que ainda vai chegar não é conversão "
                    f"que não houve.",
                    ("atraso_conversao",))

    # (4) amostra mínima
    pisos = (
        ("cliques", regra.amostra_minima_cliques),
        ("impressoes", regra.amostra_minima_impressoes),
        ("conversoes", regra.amostra_minima_conversoes),
    )
    for medida, piso in pisos:
        if piso is None:
            continue
        observado = evidencia.get(medida)
        if observado is None:
            return Suficiencia(
                "insuficiente",
                f"a regra {regra.chave} exige amostra mínima de {piso} "
                f"{medida}, e {medida} não foi medido.", (medida,))
        if float(observado) < float(piso):
            return Suficiencia(
                "insuficiente",
                f"{medida}={observado} abaixo da amostra mínima de {piso} da "
                f"regra {regra.chave}.", (medida,))

    # (5) frescor
    idade = agora - colhida
    if idade > timedelta(hours=regra.frescor_maximo_horas):
        horas = idade.total_seconds() / 3600
        return Suficiencia(
            "insuficiente",
            f"a evidência foi colhida há {horas:.1f} h e a regra "
            f"{regra.chave} aceita no máximo {regra.frescor_maximo_horas} h.",
            ("frescor",))

    return Suficiencia("suficiente")


# ═══════════════════════════════════════════════════════════════════════════
# O PRÓXIMO PASSO DA PROPOSTA
# ═══════════════════════════════════════════════════════════════════════════


def proximo_passo_da_proposta(linha: Mapping[str, Any], *,
                              agora: Optional[datetime] = None) -> str:
    """A tradução literal do `CASE` de `trafego_proposta_painel.proximo_passo`.

    ⚠️ **Duas definições da mesma regra.** Se esta função e a view discordarem, a
    tela e o motor passam a discordar sobre a mesma proposta.
    `scripts/provar-ciclo-v10.sh` compara as duas contra um Postgres de verdade.

    O primeiro ramo é o mesmo do lote, e pela mesma razão: **aplicação em voo
    manda verificar, nunca reenviar.** Um orçamento dobrado duas vezes é um
    orçamento quadruplicado.
    """
    agora = agora or datetime.now(timezone.utc)
    estado = str(linha.get("estado") or "")
    desfecho = linha.get("aplicacao_desfecho")
    decisao = linha.get("aprovacao_decisao")
    expira = _para_datetime(linha.get("expira_em"))

    # ⚠️ `sem_resposta` significa o MESMO que `em_voo` aqui: a chamada saiu e
    # não sabemos o que ela fez na conta. Olhando só `em_voo`, uma aplicação
    # fechada como `sem_resposta` caía até `decisao == "aprovada"` e a resposta
    # virava `aplicar` — mandando reenviar o mesmo diff aprovado sobre uma conta
    # que pode já tê-lo recebido.
    if desfecho in ("em_voo", "sem_resposta"):
        return "verificar"
    if estado == "aplicada":
        return "acompanhar"
    if estado in ("recusada", "cancelada", "revertida", "expirada"):
        return "nada"
    if expira is not None and expira <= agora:
        return "expirar"
    if decisao == "aprovada":
        return "aplicar"
    if decisao is None:
        return "aguardar_humano"
    return "nada"


def pode_aplicar(proposta: Mapping[str, Any], aprovacao: Mapping[str, Any],
                 *, agora: Optional[datetime] = None,
                 cooldown_ate: Optional[Any] = None) -> Tuple[bool, Optional[str]]:
    """`(pode, por_que_nao)`. Espelha `trafego_aplicacao_exige_aprovacao`.

    As quatro recusas são as mesmas do gatilho, e existir dos dois lados é
    proposital: aqui a recusa vira mensagem antes do clique; lá ela vira a
    garantia de que nenhum caminho aplica sem aprovação — nem um script solto,
    nem um endpoint esquecido.
    """
    agora = agora or datetime.now(timezone.utc)

    if aprovacao.get("proposta_id") != proposta.get("proposta_id"):
        return False, ("a aprovação apontada é de outra proposta. "
                       "Autorização não é transferível.")
    if aprovacao.get("decisao") != "aprovada":
        return False, (f"a decisão humana registrada foi "
                       f"{aprovacao.get('decisao')!r}. A máquina recomenda, o "
                       f"humano aplica (T1).")
    expira = _para_datetime(proposta.get("expira_em"))
    if expira is not None and expira <= agora:
        return False, (f"a proposta expirou em {expira.isoformat()}. Recalcule o "
                       f"diff e peça aprovação de novo — o `antes` que o humano "
                       f"viu já não é o `antes` da conta.")
    ate = _para_datetime(cooldown_ate)
    if ate is not None and ate > agora:
        return False, (f"a regra está em carência sobre este alvo até "
                       f"{ate.isoformat()}. Aplicar agora faria a regra brigar "
                       f"consigo mesma.")
    return True, None
