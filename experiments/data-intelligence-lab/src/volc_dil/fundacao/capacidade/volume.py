"""Modelo de volume e armazenamento da coleta append-only (puro, determinístico, sem I/O).

Unidade de raciocínio: a **linha lógica** = (fonte, granularidade, entidade, segmento, dia da
janela). Cada execução de um job relê todas as linhas lógicas dos dias da sua janela. Em regime
estacionário (um dia entra e um sai da janela por dia) o modelo calcula, por job:

- execuções/dia (da agenda cron), chamadas/dia, linhas lidas/dia;
- versões distintas por linha lógica — quantas leituras trazem valor diferente da anterior —,
  que é o que sobra quando a gravação deduplica conteúdo idêntico;
- lotes/dia e lotes distintos/dia (dedup do payload por lote só funciona se NENHUMA linha mudou).

E, por cenário (jobs × escala × política de gravação × perfil de bytes medido): observações/dia,
bytes/dia (observação, índices, payload, rollup) e acumulado em 30 d, 13 meses e 3 anos.

Probabilidade de mudança entre duas leituras consecutivas da MESMA linha lógica:
- dia corrente (D0): ``p = fracao_mutavel · (1 − exp(−∫ λ(t) dt))`` entre as duas leituras, com
  ``λ(t) = λ_médio · w(hora)`` (perfil horário opcional, média 1). Linhas "mortas" (campanha sem
  entrega) nunca mudam;
- dia fechado: ``p = p_revisao_fechado`` por leitura (restatement, conversão atrasada).

`fracao_ativa` é a fração das entidades que a API DEVOLVE no dia (Google Ads omite linha sem
impressão em consulta com métrica): o que não volta é ausência, nunca zero, e não é contado.

λ, frações e p de revisão são PREMISSAS nomeadas (ou calibradas — ver `cenarios`), não medições.
Bytes vêm de medição no PostgreSQL descartável (`PerfilBytes`).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace

from .cron import Agenda, ler

HORIZONTES = {"30d": 30, "13m": 396, "3a": 1096}
GB = 1024**3
FORMATOS = ("longo", "largo")
# "linha_em_lote": hash por linha (só linhas novas entram) e as linhas novas de uma execução são
# gravadas JUNTAS num lote jsonb (comprime como lote, deduplica como linha).
DEDUP_PAYLOAD = ("nenhum", "lote", "linha", "linha_em_lote")


class ParametroInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Escala:
    """Estrutura do portfólio. Crescimento = mais contas com a mesma estrutura por conta."""

    contas: int
    campanhas_por_conta: float
    grupos_por_campanha: float
    anuncios_por_grupo: float
    keywords_por_conta: float
    termos_dia_por_campanha: float  # linhas termo-dia com impressão (só as que a API devolve)
    dispositivos: int = 3
    geos_por_campanha_dia: float = 10.0
    horas_por_dia: int = 24
    linhas_joinads_dia_por_conta: float = 30.0
    origem: str = "premissa"

    def __post_init__(self) -> None:
        for k, v in asdict(self).items():
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0:
                raise ParametroInvalido(f"{k} negativo")
        if self.contas < 1:
            raise ParametroInvalido("contas >= 1")

    def crescer(self, fator: float) -> "Escala":
        if fator <= 0:
            raise ParametroInvalido("fator > 0")
        return replace(self, contas=max(1, round(self.contas * fator)), origem=f"{self.origem} ×{fator:g}")

    def entidades_por_conta(self, base: str) -> float:
        c = self.campanhas_por_conta
        g = c * self.grupos_por_campanha
        tabela = {
            "conta": 1.0,
            "campanha": c,
            "grupo": g,
            "anuncio": g * self.anuncios_por_grupo,
            "keyword": self.keywords_por_conta,
            "termo_dia": c * self.termos_dia_por_campanha,
            "campanha_hora": c * self.horas_por_dia,
            "campanha_dispositivo": c * self.dispositivos,
            "campanha_geo": c * self.geos_por_campanha_dia,
            "joinads_linha": self.linhas_joinads_dia_por_conta,
        }
        if base not in tabela:
            raise ParametroInvalido(f"base desconhecida {base!r}")
        return tabela[base]


@dataclass(frozen=True)
class Job:
    """Um coletor agendado: lê `base` × janela a cada execução da agenda."""

    nome: str
    fonte: str
    base: str
    cron: str
    janela: tuple[int, int]  # (offset inicial, offset final) em dias: (0,0)=D0, (1,7)=D-7..D-1
    metricas_por_linha: int
    lambda_mudanca_h: float = 1.0  # média diária de eventos/hora que mudam uma linha viva
    fracao_ativa: float = 1.0
    fracao_mutavel: float = 1.0
    p_revisao_fechado: float = 0.05
    consultas_por_execucao: int = 1  # requisições por conta por execução (GAQL searchStream/endpoint)
    tipo_payload: str = "campanha"
    perfil_horario: tuple[float, ...] | None = None  # 24 pesos, média 1
    confirmacao: str = "documentado na missão, não confirmado"

    def __post_init__(self) -> None:
        a, b = self.janela
        if a < 0 or b < a:
            raise ParametroInvalido(f"janela inválida {self.janela}")
        for nome in ("fracao_ativa", "fracao_mutavel", "p_revisao_fechado"):
            if not 0.0 <= getattr(self, nome) <= 1.0:
                raise ParametroInvalido(f"{nome} deve estar em [0,1]")
        if self.lambda_mudanca_h < 0 or self.metricas_por_linha < 1 or self.consultas_por_execucao < 1:
            raise ParametroInvalido("λ>=0, métricas>=1, consultas>=1")
        if self.perfil_horario is not None:
            if len(self.perfil_horario) != 24 or any(w < 0 for w in self.perfil_horario):
                raise ParametroInvalido("perfil horário: 24 pesos >= 0")
            if abs(sum(self.perfil_horario) / 24 - 1.0) > 1e-6:
                raise ParametroInvalido("perfil horário precisa ter média 1")
        ler(self.cron)

    @property
    def agenda(self) -> Agenda:
        return ler(self.cron)

    @property
    def dias_janela(self) -> int:
        return self.janela[1] - self.janela[0] + 1

    @property
    def inclui_d0(self) -> bool:
        return self.janela[0] == 0

    def com_cron(self, cron: str) -> "Job":
        return replace(self, cron=cron)

    def intensidade(self, ini_min: float, fim_min: float) -> float:
        """∫ λ(t) dt entre dois instantes do mesmo dia (minutos desde 00:00)."""
        if self.perfil_horario is None:
            return self.lambda_mudanca_h * (fim_min - ini_min) / 60.0
        total = 0.0
        t = ini_min
        while t < fim_min - 1e-9:
            h = int(t // 60) % 24
            prox = min(fim_min, (math.floor(t / 60) + 1) * 60)
            total += self.lambda_mudanca_h * self.perfil_horario[h] * (prox - t) / 60.0
            t = prox
        return total


@dataclass(frozen=True)
class PerfilBytes:
    """Bytes por unidade, medidos no PostgreSQL descartável (`origem` diz de onde veio)."""

    formato: str  # "longo" (1 observação por métrica) | "largo" (1 por linha lógica lida)
    heap_por_observacao: float
    indices_por_observacao: float
    payload_linha_em_lote: dict[str, float]  # bytes/linha da API dentro de um lote jsonb comprimido
    payload_linha_individual: dict[str, float]  # bytes/linha quando cada linha é um payload (dedup por linha)
    manifesto_por_lote: float = 250.0  # linha do lote (chaves, sha256, contagem) sem o payload
    hash_por_linha: float = 56.0  # entrada de índice sha256(linha) → lote, no modo "linha_em_lote"
    rollup_por_linha: float = 300.0  # linha larga de rollup diário (heap + índices)
    sobrecarga_particao_bytes: float = 49_152.0  # fixa por partição (heap + 3 índices vazios, ~6 páginas)
    fator_particao: float = 1.0  # multiplicador em observação+índices (PK passa a incluir a chave de partição)
    origem: str = "aproximação"

    def __post_init__(self) -> None:
        if self.formato not in FORMATOS:
            raise ParametroInvalido(f"formato ∈ {FORMATOS}")


@dataclass(frozen=True)
class ResultadoJob:
    nome: str
    fonte: str
    execucoes_dia: int
    chamadas_dia: float
    linhas_logicas_novas_dia: float
    linhas_lidas_dia: float
    versoes_por_linha: float
    lotes_dia: float
    lotes_distintos_dia: float
    p_mudanca_d0_media: float | None
    metricas_por_linha: int
    tipo_payload: str

    @property
    def linhas_distintas_dia(self) -> float:
        return self.linhas_logicas_novas_dia * self.versoes_por_linha

    @property
    def fracao_redundante(self) -> float:
        return 1.0 - self.linhas_distintas_dia / self.linhas_lidas_dia if self.linhas_lidas_dia else 0.0


def calcular_job(job: Job, escala: Escala) -> ResultadoJob:
    ag = job.agenda
    n = ag.execucoes_por_dia
    e_ret = escala.contas * escala.entidades_por_conta(job.base) * job.fracao_ativa
    linhas_por_exec = e_ret * job.dias_janela
    dias_fechados = job.dias_janela - (1 if job.inclui_d0 else 0)
    instantes = ag.instantes_do_dia()
    # p de cada leitura após a 1ª do dia (a 1ª do dia sempre traz dia novo / janela nova)
    ps_d0 = ([job.fracao_mutavel * (1.0 - math.exp(-job.intensidade(instantes[i - 1], instantes[i])))
              for i in range(1, n)] if job.inclui_d0 else [])
    if job.inclui_d0:
        versoes = 1.0 + sum(ps_d0) + n * dias_fechados * job.p_revisao_fechado
        p_d0_media = sum(ps_d0) / len(ps_d0) if ps_d0 else 0.0
    else:
        versoes = 1.0 + (n * dias_fechados - 1) * job.p_revisao_fechado
        p_d0_media = None
    versoes = min(versoes, float(n * job.dias_janela))
    lotes = escala.contas * job.consultas_por_execucao * n
    # Lote = resposta de uma consulta, de uma conta, numa execução. Só repete o anterior se NENHUMA
    # linha mudou: P = Π(1 − p_i). Por isso dedup por lote rende pouco em janela grande.
    linhas_lote = linhas_por_exec / escala.contas / job.consultas_por_execucao
    r_d0 = linhas_lote / job.dias_janela if job.inclui_d0 else 0.0
    r_f = linhas_lote - r_d0
    iguais = 0.0
    for i in range(1, n):
        p0 = ps_d0[i - 1] if job.inclui_d0 else 0.0
        iguais += ((1.0 - p0) ** r_d0) * ((1.0 - job.p_revisao_fechado) ** r_f)
    return ResultadoJob(
        nome=job.nome, fonte=job.fonte, execucoes_dia=n, chamadas_dia=float(lotes),
        linhas_logicas_novas_dia=e_ret, linhas_lidas_dia=linhas_por_exec * n, versoes_por_linha=versoes,
        lotes_dia=float(lotes), lotes_distintos_dia=lotes * (1.0 - iguais / n), p_mudanca_d0_media=p_d0_media,
        metricas_por_linha=job.metricas_por_linha, tipo_payload=job.tipo_payload,
    )


@dataclass(frozen=True)
class Politica:
    """Como a gravação trata o que foi lido."""

    dedup_observacao: bool  # grava só versões que mudaram (chave lógica + valor)
    dedup_payload: str  # "nenhum" | "lote" | "linha" | "linha_em_lote"
    com_indices: bool = True
    particao_mensal: bool = False
    retencao_bruto_dias: int | None = None  # None = guarda tudo; senão o rollup diário guarda o resto
    rollup_diario: bool = False
    rotulo: str = ""

    def __post_init__(self) -> None:
        if self.dedup_payload not in DEDUP_PAYLOAD:
            raise ParametroInvalido(f"dedup_payload ∈ {DEDUP_PAYLOAD}")
        if self.retencao_bruto_dias is not None and not self.rollup_diario:
            raise ParametroInvalido("retenção do bruto exige rollup diário (senão é perda de dado)")


@dataclass
class ResultadoCenario:
    jobs: list[ResultadoJob]
    observacoes_dia: float
    linhas_payload_dia: float
    lotes_dia: float
    chamadas_dia: float
    bytes_observacao_dia: float
    bytes_indices_dia: float
    bytes_payload_dia: float
    bytes_rollup_dia: float
    acumulado_gb: dict[str, float] = field(default_factory=dict)

    @property
    def bytes_dia(self) -> float:
        return self.bytes_observacao_dia + self.bytes_indices_dia + self.bytes_payload_dia + self.bytes_rollup_dia

    @property
    def gb_dia(self) -> float:
        return self.bytes_dia / GB

    def resumo(self) -> dict:
        return {
            "chamadas_dia": self.chamadas_dia, "lotes_dia": self.lotes_dia, "observacoes_dia": self.observacoes_dia,
            "linhas_payload_dia": self.linhas_payload_dia, "gb_dia": self.gb_dia,
            "bytes_dia": {"observacao": self.bytes_observacao_dia, "indices": self.bytes_indices_dia,
                          "payload": self.bytes_payload_dia, "rollup": self.bytes_rollup_dia},
            "acumulado_gb": dict(self.acumulado_gb),
        }


def calcular_cenario(jobs: list[Job], escala: Escala, perfil: PerfilBytes, politica: Politica) -> ResultadoCenario:
    rs = [calcular_job(j, escala) for j in jobs]
    fator = (lambda r: r.metricas_por_linha) if perfil.formato == "longo" else (lambda r: 1)
    obs = sum((r.linhas_distintas_dia if politica.dedup_observacao else r.linhas_lidas_dia) * fator(r) for r in rs)
    b_pay = 0.0
    linhas_payload = 0.0
    for r in rs:
        if politica.dedup_payload == "linha":
            lp = r.linhas_distintas_dia
            b_pay += lp * perfil.payload_linha_individual[r.tipo_payload]
        elif politica.dedup_payload == "linha_em_lote":
            lp = r.linhas_distintas_dia
            b_pay += lp * (perfil.payload_linha_em_lote[r.tipo_payload] + perfil.hash_por_linha)
        else:
            frac = (r.lotes_distintos_dia / r.lotes_dia) if (politica.dedup_payload == "lote" and r.lotes_dia) else 1.0
            lp = r.linhas_lidas_dia * frac
            b_pay += lp * perfil.payload_linha_em_lote[r.tipo_payload]
        linhas_payload += lp
    lotes = sum(r.lotes_dia for r in rs)
    b_pay += lotes * perfil.manifesto_por_lote
    fp = perfil.fator_particao if politica.particao_mensal else 1.0
    b_obs = obs * perfil.heap_por_observacao * fp
    b_idx = obs * perfil.indices_por_observacao * fp if politica.com_indices else 0.0
    b_roll = sum(r.linhas_logicas_novas_dia for r in rs) * perfil.rollup_por_linha if politica.rollup_diario else 0.0
    res = ResultadoCenario(jobs=rs, observacoes_dia=obs, linhas_payload_dia=linhas_payload, lotes_dia=lotes,
                           chamadas_dia=sum(r.chamadas_dia for r in rs), bytes_observacao_dia=b_obs,
                           bytes_indices_dia=b_idx, bytes_payload_dia=b_pay, bytes_rollup_dia=b_roll)
    bruto_dia = b_obs + b_idx + b_pay
    for nome, dias in HORIZONTES.items():
        dias_bruto = dias if politica.retencao_bruto_dias is None else min(dias, politica.retencao_bruto_dias)
        total = bruto_dia * dias_bruto + b_roll * dias
        if politica.particao_mensal:
            total += math.ceil(dias / 30.4375) * perfil.sobrecarga_particao_bytes
        res.acumulado_gb[nome] = total / GB
    return res


@dataclass(frozen=True)
class PerfilGTM:
    sessoes_dia: float
    eventos_por_sessao: float
    duracao_sessao_s: float
    lote_max_eventos: int = 20
    lote_max_s: float = 10.0
    bytes_por_evento: float = 600.0
    indices_por_evento: float = 60.0
    origem: str = "premissa"


def calcular_gtm(p: PerfilGTM, horizontes: dict[str, int] = HORIZONTES) -> dict:
    """GTM é orientado a evento: não há "cadência de coleta", há lote no navegador.

    Requisições por sessão = max(⌈e/lote_max⌉, min(e, ⌈T/lote_s⌉)): o lote fecha por contagem OU
    por tempo; nunca há mais requisições que eventos.
    """
    if p.lote_max_eventos < 1 or p.lote_max_s <= 0:
        raise ParametroInvalido("lote inválido")
    e = p.eventos_por_sessao
    if e <= 0:
        req_sessao = 0
    else:
        req_sessao = max(math.ceil(e / p.lote_max_eventos), min(math.ceil(e), math.ceil(p.duracao_sessao_s / p.lote_max_s)))
    eventos = p.sessoes_dia * e
    b = eventos * (p.bytes_por_evento + p.indices_por_evento)
    return {
        "eventos_dia": eventos, "requisicoes_dia": p.sessoes_dia * req_sessao, "requisicoes_por_sessao": req_sessao,
        "eventos_por_requisicao": (e / req_sessao) if req_sessao else 0.0, "gb_dia": b / GB,
        "acumulado_gb": {k: b * d / GB for k, d in horizontes.items()}, "perfil": asdict(p),
    }
