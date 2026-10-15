"""Deadman da coleta de insights Meta (D-1 e recoleta) — o observador de fora.

Irmão de `backend/app/trafego/deadman_coleta.py`, que vigia a coleta Google.
O motivo de existir é o mesmo: os workflows Meta alertam por dentro ("Batimento
e saude" → `system_settings`), mas **um workflow que não roda não alerta**. Este
módulo pergunta "onde está o fechamento que já devia ter pousado?".

## O que ele reaproveita, e o que não

A TABELA-VERDADE não é reescrita aqui: a decisão é de
`volc_ads.inteligencia_google.saude.projetar_saude_coletor`, a mesma do deadman
Google (`docs/contracts/HEALTH-DEADMAN-GOOGLE-INTELLIGENCE.md`). O intervalo
esperado sai de `deadman_coleta.intervalo_do_cron`. Este módulo só TRADUZ:

* **expectativa** — do workflow versionado `n8n/volc_meta_insights_dia_*.json`
  (cron, `active`, `JOB`, `JANELA_MODO`, `PASSOS`), gerado por
  `n8n/gerar_flows_meta_ledger.py`. Workflow desligado é DESABILITADO, não
  ATRASADO;
* **evidência** — os fechamentos de execução em `public.trafego_meta_sync_run`
  (`escopo = 'insights_fechamento'`). A RPC grava o rótulo da rodada em
  `cursor_final.window` (`<data_do_disparo>:<origem_janela>`) e a completude da
  execução em `cursor_final.leitura_completa`. É o rótulo que separa o
  fechamento do D-1 do da recoleta.

⚠️ A identidade de `saude.IdentidadeColetor` é a hierarquia Google (MCC e
conta, 6 a 12 dígitos). Um job Meta cobre TODAS as contas prontas do read model
numa execução só, e conta Meta não é id Google. Por isso a identidade interna é
uma subclasse que declara o escopo Meta sem fingir ids Google, e a projeção
PÚBLICA deste módulo (`ProjecaoSaudeInsightsMeta`) nem carrega esses campos.

## O que ele NÃO faz

Não agenda, não lê o banco, não chama a Meta, não alerta. É um classificador
puro que alguém consulta. Ausência de FONTE (a tabela não existe no Supabase
oficial — o schema Meta ainda não foi aplicado) é INDETERMINADO, nunca
NUNCA_EXECUTADO.

## Limite declarado

O fechamento não grava o `disparo` (agenda × manual): a RPC guarda só o rótulo
`window`. Uma rodada MANUAL do mesmo workflow conta como evidência do papel. Ela
de fato leu a mesma janela, então os números estão em dia — mas o deadman não
prova que a AGENDA está viva quando alguém roda à mão todo dia.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from volc_ads.inteligencia_google.saude import (
    EstadoSaudeColetor,
    FalhaColetor,
    IdentidadeColetor,
    MotivoDiagnostico,
    ProjecaoSaudeColetor,
    ReciboColetor,
    ScheduleColetor,
    projetar_saude_coletor,
)

from ..deadman_coleta import intervalo_do_cron

__all__ = [
    "MODOS_META",
    "FonteMeta",
    "JobInsightsMeta",
    "ProjecaoSaudeInsightsMeta",
    "job_do_workflow_meta",
    "diagnosticar_insights_meta",
]

#: Os dois papéis que `n8n/gerar_flows_meta_ledger.py` produz.
MODOS_META = frozenset({"D-1", "RECOLETA"})
ESCOPO_FECHAMENTO = "insights_fechamento"
_JOB = re.compile(r"^[a-z0-9_]{3,40}$")
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FonteMeta:
    """Por que NÃO houve leitura — o que não é o mesmo que 'não executou'."""

    DISPONIVEL = "DISPONIVEL"
    TABELA_AUSENTE = "TABELA_AUSENTE"
    LEITURA_FALHOU = "LEITURA_FALHOU"


@dataclass(frozen=True)
class JobInsightsMeta:
    """A EXPECTATIVA, lida do workflow que é a autoridade de agenda."""

    job: str
    origem_janela: str
    cron: str
    ativo: bool
    fuso: str
    workflow_arquivo: str


@dataclass(frozen=True)
class ProjecaoSaudeInsightsMeta:
    """Superfície pública: estado, motivo e tempos. Nenhuma conta, nenhum valor."""

    job: str
    origem_janela: str
    workflow_arquivo: str
    estado: EstadoSaudeColetor
    motivo: MotivoDiagnostico
    mensagem: str
    calculado_em: datetime
    tempo_desde_ultimo_sucesso: timedelta | None = None
    tempo_desde_ultima_tentativa: timedelta | None = None
    atraso_estimado: timedelta | None = None
    falha_codigo: str | None = None
    falha_classe: str | None = None


@dataclass(frozen=True)
class _IdentidadeJobMeta(IdentidadeColetor):
    """Escopo de um job Meta dentro do contrato de saúde.

    ⚠️ NÃO são ids Google. `login_customer_id` vira o provedor e `customer_id`
    o escopo da execução (todas as contas prontas). A validação Google de 6 a 12
    dígitos não se aplica, e por isso é trocada pela validação do job — e esta
    identidade nunca sai deste módulo.
    """

    def __post_init__(self) -> None:
        if self.login_customer_id != "META_ADS":
            raise ValueError("identidade Meta exige provedor META_ADS")
        if self.customer_id != "contas_prontas":
            raise ValueError("job Meta cobre as contas prontas do read model")
        if not _JOB.fullmatch(self.coletor_id):
            raise ValueError("coletor_id Meta fora do formato do JOB")
        if self.volc_campaign_id is not None or self.campaign_id is not None:
            raise ValueError("job Meta nao tem escopo de campanha")


def _config(workflow: Mapping[str, Any]) -> dict[str, str]:
    for no in workflow.get("nodes") or []:
        if no.get("name") != "Config":
            continue
        atribuicoes = (
            ((no.get("parameters") or {}).get("assignments") or {}).get("assignments")
            or []
        )
        return {str(a["name"]): str(a.get("value", "")) for a in atribuicoes if a.get("name")}
    return {}


def job_do_workflow_meta(
    workflow: Mapping[str, Any],
    arquivo: str,
    *,
    ativo_na_instancia: bool | None = None,
) -> JobInsightsMeta:
    """Extrai a expectativa do workflow Meta versionado. Não adivinha nada.

    ⚠️ O artefato versionado nasce SEMPRE `active: false` (o gerador fixa e o
    validador exige). Ligado ou não é fato da INSTÂNCIA n8n, não do arquivo: quem
    consulta e leu a instância passa `ativo_na_instancia`. Sem isso, o deadman
    responde DESABILITADO para sempre — o que é verdade sobre o arquivo e
    silêncio sobre um workflow ligado que falha.
    """
    volc = ((workflow.get("meta") or {}).get("volc") or {})
    if volc.get("provider") != "META_ADS":
        raise ValueError(f"{arquivo}: nao e um workflow de insights Meta")

    crons = [
        intervalo.get("expression")
        for no in workflow.get("nodes") or []
        if no.get("type") == "n8n-nodes-base.scheduleTrigger"
        for intervalo in (((no.get("parameters") or {}).get("rule") or {}).get("interval") or [])
        if intervalo.get("field") == "cronExpression"
    ]
    if len(crons) != 1 or not crons[0]:
        raise ValueError(f"{arquivo}: precisa de exatamente um scheduleTrigger com cron")
    cron = str(crons[0])

    cfg = _config(workflow)
    job = cfg.get("JOB", "").strip()
    if not _JOB.fullmatch(job):
        raise ValueError(f"{arquivo}: Config sem JOB valido")
    modo = cfg.get("JANELA_MODO", "").strip().upper()
    if modo not in MODOS_META:
        raise ValueError(f"{arquivo}: JANELA_MODO invalido: {modo!r}")
    if volc.get("papel") != modo:
        raise ValueError(f"{arquivo}: meta.volc.papel diverge do JANELA_MODO")

    # A agenda aparece duas vezes: no cron e em PASSOS. Divergência = expectativa
    # ambígua, e deadman com expectativa ambígua produz alarme que ninguém confia.
    intervalo_do_cron(cron)  # valida a forma antes de ler as horas
    passos = [p.strip() for p in cfg.get("PASSOS", "").split(",") if p.strip()]
    try:
        horas_dos_passos = sorted({int(p) for p in passos})
    except ValueError as erro:
        raise ValueError(f"{arquivo}: PASSOS nao numericos: {passos!r}") from erro
    horas_do_cron = sorted({int(h) for h in cron.split()[1].split(",")})
    if horas_dos_passos != horas_do_cron:
        raise ValueError(
            f"{arquivo}: AGENDA_AMBIGUA — o cron diz {horas_do_cron} e "
            f"PASSOS diz {horas_dos_passos}"
        )

    # `active` ausente NÃO é `True`: o padrão seguro é desligado.
    ativo = workflow.get("active")
    if not isinstance(ativo, bool):
        ativo = False
    if ativo_na_instancia is not None:
        if not isinstance(ativo_na_instancia, bool):
            raise TypeError("ativo_na_instancia deve ser bool")
        ativo = ativo_na_instancia

    fuso = (cfg.get("TZ_DO_DISPARO", "").strip()
            or ((workflow.get("settings") or {}).get("timezone") or "").strip())
    if not fuso:
        raise ValueError(f"{arquivo}: sem fuso da agenda")

    return JobInsightsMeta(
        job=job,
        origem_janela=modo,
        cron=cron,
        ativo=ativo,
        fuso=fuso,
        workflow_arquivo=arquivo,
    )


def _instante(valor: Any) -> datetime | None:
    """Converte o timestamp do PostgREST sem inventar fuso (naive fica naive)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor
    texto = str(valor).strip().replace(" ", "T", 1)
    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


def _origem_do_fechamento(linha: Mapping[str, Any]) -> str | None:
    """`cursor_final.window` = `<YYYY-MM-DD>:<origem>`. Forma diferente = não é dele."""
    cursor = linha.get("cursor_final")
    if not isinstance(cursor, Mapping):
        return None
    janela = cursor.get("window")
    if not isinstance(janela, str) or ":" not in janela:
        return None
    data, origem = janela.split(":", 1)
    if not _DATA.fullmatch(data):
        return None
    return origem


def _falha(linha: Mapping[str, Any]) -> FalhaColetor | None:
    """Fechamento incompleto é tentativa com desfecho ruim, nunca sucesso.

    `leitura_completa` só é `True` quando a execução fechou `ok` (o fluxo manda
    `completo: resultado === 'ok'`, e a RPC grava `false` quando o campo falta).
    Com alguma conta aceita é PARCIAL; sem nenhuma, ou sem a contagem, é falha
    sem classe conhecida — ausência de contagem não vira "zero contas".
    """
    cursor = linha.get("cursor_final")
    completa = cursor.get("leitura_completa") if isinstance(cursor, Mapping) else None
    if completa is True:
        return None
    contagens = linha.get("contagens")
    aceitas = contagens.get("contas_aceitas") if isinstance(contagens, Mapping) else None
    if isinstance(aceitas, int) and not isinstance(aceitas, bool) and aceitas > 0:
        return FalhaColetor(codigo="COLETA_PARCIAL", classe="PARCIAL")
    return FalhaColetor(codigo="FALHA_COLETA", classe="DESCONHECIDA")


def _publica(job: JobInsightsMeta, p: ProjecaoSaudeColetor) -> ProjecaoSaudeInsightsMeta:
    return ProjecaoSaudeInsightsMeta(
        job=job.job,
        origem_janela=job.origem_janela,
        workflow_arquivo=job.workflow_arquivo,
        estado=p.estado,
        motivo=p.motivo,
        mensagem=p.mensagem,
        calculado_em=p.calculado_em,
        tempo_desde_ultimo_sucesso=p.tempo_desde_ultimo_sucesso,
        tempo_desde_ultima_tentativa=p.tempo_desde_ultima_tentativa,
        atraso_estimado=p.atraso_estimado,
        falha_codigo=p.falha_codigo.value if p.falha_codigo is not None else None,
        falha_classe=p.falha_classe.value if p.falha_classe is not None else None,
    )


def diagnosticar_insights_meta(
    job: JobInsightsMeta,
    fechamentos: Sequence[Mapping[str, Any]] | None,
    *,
    now: datetime,
    fonte: str = FonteMeta.DISPONIVEL,
    tolerancia_atraso: timedelta | None = None,
) -> ProjecaoSaudeInsightsMeta:
    """Traduz `trafego_meta_sync_run` + workflow para o contrato de saúde.

    `fechamentos` são linhas de `public.trafego_meta_sync_run`, em qualquer
    ordem. Só contam as de `escopo = 'insights_fechamento'` cujo rótulo
    `cursor_final.window` termina na origem do job; a mais recente é escolhida
    por `concluido_em`.
    """
    identidade = _IdentidadeJobMeta(
        login_customer_id="META_ADS",
        customer_id="contas_prontas",
        coletor_id=job.job,
        tipo_coletor="META_INSIGHTS_CONJUNTO_DIA",
    )

    # `None` é "não li", não "li e não havia": sem a lista, a fonte não respondeu.
    if fechamentos is None and fonte == FonteMeta.DISPONIVEL:
        fonte = FonteMeta.LEITURA_FALHOU
    if fonte != FonteMeta.DISPONIVEL:
        mensagem = (
            "a tabela trafego_meta_sync_run nao existe neste banco (schema Meta "
            "nao aplicado): sem fonte, o estado da coleta e desconhecido"
            if fonte == FonteMeta.TABELA_AUSENTE
            else "a leitura de trafego_meta_sync_run falhou: o estado da coleta e desconhecido"
        )
        return _publica(job, ProjecaoSaudeColetor(
            identidade=identidade,
            estado=EstadoSaudeColetor.INDETERMINADO,
            motivo=MotivoDiagnostico.SEM_SUCESSO_CONFIRMADO,
            mensagem=mensagem,
            calculado_em=now,
        ))

    schedule = ScheduleColetor(
        intervalo_esperado=intervalo_do_cron(job.cron),
        tolerancia_atraso=tolerancia_atraso,
        desabilitado=not job.ativo,
        expressao=job.cron,
    )

    linhas = [
        l for l in (fechamentos or [])
        if str(l.get("escopo") or "") == ESCOPO_FECHAMENTO
        and _origem_do_fechamento(l) == job.origem_janela
    ]
    if not linhas:
        return _publica(job, projetar_saude_coletor(
            ReciboColetor(identidade=identidade, schedule=schedule), now=now))

    # Instante sem fuso ou ilegível não é comparável com os outros: ele vai ao
    # contrato de saúde, que responde INDETERMINADO, em vez de explodir aqui ou
    # ser descartado em silêncio.
    suspeitas = [l for l in linhas
                 if (t := _instante(l.get("concluido_em"))) is None or t.tzinfo is None]
    if suspeitas:
        ultima = suspeitas[0]
        if _instante(ultima.get("concluido_em")) is None:
            return _publica(job, ProjecaoSaudeColetor(
                identidade=identidade,
                estado=EstadoSaudeColetor.INDETERMINADO,
                motivo=MotivoDiagnostico.INCONSISTENCIA_TEMPORAL,
                mensagem="fechamento sem concluido_em legivel",
                calculado_em=now,
            ))
    else:
        ultima = max(linhas, key=lambda l: _instante(l.get("concluido_em")))
    concluida = _instante(ultima.get("concluido_em"))
    falha = _falha(ultima) if concluida is not None else None
    # ⚠️ Sucesso é SÓ fechamento completo. Promover parcial a sucesso é o falso
    # verde que o ledger inteiro existe para impedir.
    sucesso = concluida if falha is None else None

    return _publica(job, projetar_saude_coletor(
        ReciboColetor(
            identidade=identidade,
            schedule=schedule,
            ultima_tentativa_em=concluida,
            ultimo_sucesso_em=sucesso,
            falha_ultima_tentativa=falha,
        ),
        now=now,
    ))
