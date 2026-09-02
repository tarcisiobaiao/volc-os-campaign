"""Deadman da coleta D0/D-1 — o observador que existe FORA da execução.

## Por que este módulo existe

Os workflows `gads_dia_d0`/`gads_dia_d1` já alertam quando algo dá errado
DENTRO deles: releem o recibo no banco e, se ele não pousou, gravam
`INDETERMINADO`. Isso é bom e continua valendo. Mas tem um limite que nenhum
alerta interno pode vencer: **um workflow que não roda não alerta**. Se a agenda
for desligada, se a instância cair, se o gatilho for removido — o silêncio é
indistinguível do sucesso, porque nos dois casos não chega alerta nenhum.

Deadman é justamente o observador que trata silêncio como evidência. Ele não
pergunta "a execução falhou?"; pergunta "onde está a execução que já devia ter
acontecido?".

## O que ele NÃO faz, de propósito

**Não agenda nada.** n8n é a autoridade única de agenda
(`docs/closure/hermes-p10-t16-n8n-ledger-v12-v1/ADR-N8N-AUTORIDADE-DE-AGENDA.md`),
e um deadman que instalasse o próprio timer criaria o segundo dono que o ADR
existe para impedir. Este é um classificador PURO, de leitura, que alguém
consulta — o QG, uma rota, um teste. Quem pergunta define quando pergunta.

**Não classifica sozinho.** A tabela-verdade mora em
`docs/contracts/HEALTH-DEADMAN-GOOGLE-INTELLIGENCE.md` e já está implementada e
provada em `volc_ads.inteligencia_google.saude.projetar_saude_coletor`. Esse
classificador tinha zero consumidores de produção: o contrato existia, a prova
existia, e nada aplicava. Este módulo é o adaptador que faltava — ele traduz, e
delega a decisão.

## As duas fontes, e por que cada uma é a certa

**Expectativa** vem do PRÓPRIO workflow versionado (`n8n/volc_gads_*.json`):
a expressão cron e o `active`. Derivar a expectativa de qualquer outro lugar
seria inventar uma segunda verdade sobre a agenda — e a primeira coisa que um
deadman precisa acertar é o que ele estava esperando.

⚠️ Consequência direta e desejada: com `active: false`, o estado é
`DESABILITADO`, **não** `ATRASADO`. Rotina desligada por contrato não é rotina
atrasada, e um deadman que gritasse aqui seria ruído — e ruído treina gente a
ignorar alarme.

**Evidência** vem de `public.trafego_coleta_execucao_saude`, a view da v12_04.

⚠️ Essa view **ainda não existe no Supabase oficial** — a v12_04 não foi
aplicada. Ausência de fonte NÃO é ausência de execução: quem não consegue olhar
não pode dizer "não aconteceu". Por isso existe `FONTE_INDISPONIVEL`, que vira
`INDETERMINADO` com motivo próprio, e nunca `NUNCA_EXECUTADO` nem `SAUDAVEL`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

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

__all__ = [
    "JobDeColeta",
    "FonteDeEvidencia",
    "intervalo_do_cron",
    "job_do_workflow",
    "diagnosticar_coleta",
]


# Um dia inteiro. É o maior intervalo que qualquer passada D0/D-1 pode ter.
_UM_DIA = timedelta(days=1)


@dataclass(frozen=True)
class JobDeColeta:
    """A EXPECTATIVA, lida do workflow que é a autoridade de agenda."""

    job: str
    origem_janela: str
    cron: str
    ativo: bool
    fuso: str
    workflow_arquivo: str


class FonteDeEvidencia:
    """Motivos pelos quais NÃO houve leitura — que não são 'não executou'."""

    DISPONIVEL = "DISPONIVEL"
    VIEW_AUSENTE = "VIEW_AUSENTE"
    LEITURA_FALHOU = "LEITURA_FALHOU"


def intervalo_do_cron(expressao: str) -> timedelta:
    """O MAIOR intervalo entre duas passadas consecutivas da expressão.

    ⚠️ O maior, e não o menor, e a diferença decide alarme falso. O D0 roda às
    06/12/18/23: os saltos são 6h, 6h, 5h e 7h (23h → 06h do dia seguinte). Se a
    expectativa fosse o menor salto (5h), toda passada das 23h nasceria
    "atrasada" às 04h da manhã, todo dia, sem nada ter acontecido. O deadman
    precisa esperar o pior caso legítimo antes de acusar.

    Só entende a forma que estes dois workflows usam: minuto e hora fixos, dia
    e mês livres. Qualquer outra forma levanta ValueError em vez de devolver um
    palpite — expectativa chutada é a raiz do alarme que ninguém confia.
    """
    campos = expressao.split()
    if len(campos) != 5:
        raise ValueError(f"cron fora do formato de 5 campos: {expressao!r}")
    minuto, hora, dia, mes, semana = campos
    if dia != "*" or mes != "*" or semana != "*":
        raise ValueError(
            f"cron com dia/mes/semana restritos nao e suportado aqui: {expressao!r}"
        )
    if not minuto.isdigit():
        raise ValueError(f"minuto do cron precisa ser fixo: {expressao!r}")

    try:
        horas = sorted({int(h) for h in hora.split(",")})
    except ValueError as erro:
        raise ValueError(f"horas do cron nao sao numericas: {expressao!r}") from erro
    if not horas or any(h < 0 or h > 23 for h in horas):
        raise ValueError(f"horas do cron fora de 0..23: {expressao!r}")

    if len(horas) == 1:
        return _UM_DIA

    saltos = [
        timedelta(hours=b - a) for a, b in zip(horas, horas[1:])
    ] + [timedelta(hours=24 - horas[-1] + horas[0])]
    return max(saltos)


def job_do_workflow(workflow: Mapping[str, Any], arquivo: str) -> JobDeColeta:
    """Extrai a expectativa do workflow versionado. Não adivinha nada."""
    nos = workflow.get("nodes") or []

    cron = None
    for no in nos:
        if no.get("type") == "n8n-nodes-base.scheduleTrigger":
            regra = (no.get("parameters") or {}).get("rule") or {}
            for intervalo in regra.get("interval") or []:
                if intervalo.get("field") == "cronExpression":
                    cron = intervalo.get("expression")
    if not cron:
        raise ValueError(f"{arquivo}: nenhum scheduleTrigger com cronExpression")

    config: dict[str, str] = {}
    for no in nos:
        if no.get("name") != "Config":
            continue
        atribuicoes = (
            ((no.get("parameters") or {}).get("assignments") or {}).get("assignments")
            or []
        )
        for a in atribuicoes:
            nome = a.get("name")
            if nome:
                config[str(nome)] = str(a.get("value", ""))

    job = config.get("JOB", "").strip()
    if not job:
        raise ValueError(f"{arquivo}: Config sem JOB")
    modo = config.get("JANELA_MODO", "").strip()
    if modo not in {"D0", "D-1"}:
        raise ValueError(f"{arquivo}: JANELA_MODO invalido: {modo!r}")

    # ⚠️ O workflow declara a agenda DUAS vezes: no cron do gatilho e em
    # `PASSOS`, que é o que o código usa para escolher o passo da execução. Se as
    # duas divergirem, a expectativa do deadman é ambígua — e deadman com
    # expectativa ambígua produz alarme que ninguém confia. Conferir aqui é
    # barato e transforma um desencontro silencioso em recusa nomeada.
    passos = [p.strip() for p in config.get("PASSOS", "").split(",") if p.strip()]
    if passos:
        try:
            horas_dos_passos = sorted({int(p) for p in passos})
        except ValueError as erro:
            raise ValueError(f"{arquivo}: PASSOS nao numericos: {passos!r}") from erro
        horas_do_cron = sorted({int(h) for h in str(cron).split()[1].split(",")})
        if horas_dos_passos != horas_do_cron:
            raise ValueError(
                f"{arquivo}: AGENDA_AMBIGUA — o cron diz {horas_do_cron} e "
                f"PASSOS diz {horas_dos_passos}"
            )

    # `active` ausente NÃO é `True`. Workflow sem o campo é workflow cujo estado
    # de agenda ninguém declarou, e o padrão seguro é desligado.
    ativo = workflow.get("active")
    if not isinstance(ativo, bool):
        ativo = False

    return JobDeColeta(
        job=job,
        origem_janela=modo,
        cron=str(cron),
        ativo=ativo,
        fuso=config.get("TZ", "").strip() or "America/Sao_Paulo",
        workflow_arquivo=arquivo,
    )


def _instante(valor: Any) -> datetime | None:
    """Converte o que a view devolveu, sem inventar fuso.

    ⚠️ Timestamp naive não é convertido para UTC por conveniência: o contrato
    trata naive como INDETERMINADO, e transformá-lo aqui apagaria justamente a
    anomalia que ele existe para denunciar. Por isso devolve como está.
    """
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


def _identidade(job: JobDeColeta, login_customer_id: str, customer_id: str) -> IdentidadeColetor:
    return IdentidadeColetor(
        login_customer_id=login_customer_id,
        customer_id=customer_id,
        coletor_id=job.job,
        tipo_coletor="gads_campanha_dia",
    )


def diagnosticar_coleta(
    job: JobDeColeta,
    fechamentos: Sequence[Mapping[str, Any]] | None,
    *,
    login_customer_id: str,
    customer_id: str,
    now: datetime,
    fonte: str = FonteDeEvidencia.DISPONIVEL,
    tolerancia_atraso: timedelta | None = None,
) -> ProjecaoSaudeColetor:
    """Traduz ledger + workflow para o contrato de saúde, e delega a decisão.

    `fechamentos` são linhas de `public.trafego_coleta_execucao_saude` (que já
    filtra `tipo_lote='fechamento'`), da mais recente para a mais antiga ou em
    qualquer ordem — a mais recente é escolhida aqui pelo `encerrada_em`.
    """
    identidade = _identidade(job, login_customer_id, customer_id)

    # ── ausência de FONTE não é ausência de EXECUÇÃO ────────────────────────
    # Este é o ramo que separa "olhei e não havia" de "não consegui olhar". Sem
    # ele, um banco sem a v12_04 responderia NUNCA_EXECUTADO — uma afirmação
    # sobre o mundo feita por quem não conseguiu observá-lo.
    if fonte != FonteDeEvidencia.DISPONIVEL:
        mensagem = (
            "a view trafego_coleta_execucao_saude nao existe neste banco "
            "(v12_04 nao aplicada): sem fonte, o estado da coleta e desconhecido"
            if fonte == FonteDeEvidencia.VIEW_AUSENTE
            else "a leitura da view de saude falhou: o estado da coleta e desconhecido"
        )
        return ProjecaoSaudeColetor(
            identidade=identidade,
            estado=EstadoSaudeColetor.INDETERMINADO,
            motivo=MotivoDiagnostico.SEM_SUCESSO_CONFIRMADO,
            mensagem=mensagem,
            calculado_em=now,
        )

    schedule = ScheduleColetor(
        intervalo_esperado=intervalo_do_cron(job.cron),
        tolerancia_atraso=tolerancia_atraso,
        desabilitado=not job.ativo,
        expressao=job.cron,
    )

    linhas = [
        l for l in (fechamentos or [])
        if str(l.get("job") or "") == job.job
        and str(l.get("origem_janela") or "") == job.origem_janela
    ]

    if not linhas:
        # Olhamos, a fonte respondeu, e não havia execução. ISSO é
        # NUNCA_EXECUTADO — e só isso.
        return projetar_saude_coletor(
            ReciboColetor(identidade=identidade, schedule=schedule), now=now
        )

    ultima = max(
        linhas,
        key=lambda l: _instante(l.get("encerrada_em")) or datetime.min.replace(tzinfo=timezone.utc),
    )

    encerrada = _instante(ultima.get("encerrada_em"))
    resultado = str(ultima.get("resultado") or "")

    # ⚠️ SUCESSO É SÓ 'ok'. 'parcial' e 'falhou' são tentativas COM desfecho
    # ruim, e promover 'parcial' a sucesso é exatamente o falso verde que o
    # ledger inteiro existe para impedir — a v12_04 já recusa fechar 'ok' com
    # linha rejeitada, e essa recusa não pode ser desfeita aqui.
    sucesso = encerrada if resultado == "ok" else None

    # ⚠️ O `motivo` do ledger NÃO atravessa para a projeção. `FalhaColetor` só
    # aceita código e classe de taxonomias fechadas, e isso é desenho, não
    # limitação: o motivo do fechamento cita conta e campanha
    # ("8017851692/AUTENTICACAO"), e a projeção de saúde é a superfície pública.
    # Quem precisa do detalhe lê o recibo, com a autorização que o recibo exige.
    falha = None
    if resultado == "falhou" and encerrada is not None:
        falha = FalhaColetor(codigo="FALHA_COLETA", classe="DESCONHECIDA")
    elif resultado == "parcial" and encerrada is not None:
        falha = FalhaColetor(codigo="COLETA_PARCIAL", classe="PARCIAL")

    return projetar_saude_coletor(
        ReciboColetor(
            identidade=identidade,
            schedule=schedule,
            ultima_tentativa_em=encerrada,
            ultimo_sucesso_em=sucesso,
            ultimo_heartbeat_em=_instante(ultima.get("batimento_em")),
            falha_ultima_tentativa=falha,
        ),
        now=now,
    )
