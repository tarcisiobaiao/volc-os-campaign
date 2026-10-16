"""Parâmetros do Simulator Lab: mundo verdadeiro, observador e especificação de cenário.

Todo número aqui é PARÂMETRO DE SIMULAÇÃO, nunca política operacional. A origem de cada
parâmetro (forma calibrada em dado real versionado, faixa da literatura ou arbitrário) está
em ``calibracao.FONTES_PARAMETROS`` e em ``docs/.../07-SIMULATOR-LAB.md``.

Dinheiro de configuração entra em micros inteiros (``*_micros``); grandezas de modelagem
(taxas, médias, desvios, elasticidades) são float por natureza e nunca viram registro de
dinheiro sem passar por arredondamento explícito para micros.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any

DISPOSITIVOS = ("mobile", "desktop", "tablet")
PAISES = ("BR", "PT", "US")
FONTES = ("google_ads", "joinads", "site_analytics", "legado_daily_metrics")


@dataclass(frozen=True)
class MudancaOrcamento:
    """Multiplica o orçamento diário de uma fração das campanhas a partir de (dia, hora) local."""

    frac_campanhas: float
    em_frac_periodo: float
    hora_local: int
    fator: float


@dataclass(frozen=True)
class QuebraRegime:
    """Change point: multiplica RPM ou CPC de uma fração das campanhas a partir de um instante."""

    alvo: str  # "rpm" | "cpc"
    frac_campanhas: float
    em_frac_periodo: float
    hora_local: int
    fator: float


@dataclass(frozen=True)
class ParametrosMundo:
    """Processo VERDADEIRO (o que aconteceu). Ver equações em 07-SIMULATOR-LAB.md §2."""

    n_campanhas: int = 50
    n_dias: int = 30
    data_inicio: str = "2026-08-03"  # segunda-feira
    timezone: str = "America/Sao_Paulo"
    n_contas: int = 2
    moeda_custo: str = "BRL"
    moeda_receita: str = "BRL"
    frac_campanhas_receita_usd: float = 0.0  # receita nativa em USD (moeda_misturada)
    cambio_brl_por_usd: float = 5.0  # só define a verdade USD a partir do gerador em BRL
    # ciclo de vida
    frac_novas: float = 0.2
    novas_inicio_max_frac: float = 0.5
    idade_madura_dias_min: int = 30
    idade_madura_dias_max: int = 365
    p_pausa_dia: float = 0.01
    # volume e leilão
    impressoes_dia_mediana: float = 4000.0
    impressoes_dia_sigma: float = 0.8
    ctr_media: float = 0.04
    ctr_concentracao: float = 150.0
    ctr_sigma_dia: float = 0.10
    roas_mediana: float = 1.0
    roas_sigma: float = 0.32
    cpc_sigma_hora: float = 0.15
    elasticidade_cpc: float = 0.30
    taxa_cliques_invalidos: float = 0.02
    # orçamento
    orcamento_razao_min: float = 0.6
    orcamento_razao_max: float = 1.6
    overdelivery: float = 1.0
    mudancas_orcamento: tuple[MudancaOrcamento, ...] = ()
    # sazonalidade
    amp_diaria: float = 0.55
    hora_pico: float = 21.0
    amp_diaria2: float = 0.15
    hora_pico2: float = 12.0
    fator_fds_volume: float = 0.90
    fator_fds_rpm: float = 0.92
    amp_rpm_hora: float = 0.12
    hora_pico_rpm: float = 20.0
    # dispositivos e países
    share_dispositivo: tuple[float, float, float] = (0.78, 0.17, 0.05)
    amp_share_mobile_noite: float = 0.08
    mult_ctr_dispositivo: tuple[float, float, float] = (1.0, 0.85, 0.9)
    mult_cpc_dispositivo: tuple[float, float, float] = (1.0, 1.25, 0.9)
    mult_rpm_dispositivo: tuple[float, float, float] = (1.0, 1.6, 1.2)
    prob_pais: tuple[float, float, float] = (0.85, 0.10, 0.05)
    mult_rpm_pais: tuple[float, float, float] = (1.0, 2.2, 3.5)
    # site / funil
    taxa_aterrissagem_min: float = 0.85
    taxa_aterrissagem_max: float = 0.97
    funil_passos: int = 5
    continuacao_min: float = 0.55
    continuacao_max: float = 0.80
    rpm_mediana_brl: float = 60.0
    rpm_sigma: float = 0.35
    dispersao_receita: float = 4.0
    # ruído
    choque_dia_sigma: float = 0.15
    choque_dia_ar: float = 0.6
    sobredispersao: float = 0.05
    # maturação de campanha nova (aprendizado do leilão)
    volume_inicial: float = 0.15
    tau_volume_h: float = 72.0
    amp_cpc_aprendizado: float = 0.6
    amp_ctr_aprendizado: float = 0.3
    tau_aprendizado_h: float = 120.0
    amp_ruido_aprendizado: float = 1.5
    # outliers
    p_bot_hora: float = 0.0
    bot_mult: float = 15.0
    bot_cliques_min: float = 20.0
    bot_share_desktop: float = 0.7
    bot_aterrissagem: float = 0.3
    bot_continuacao: float = 0.05
    bot_rpm_fator: float = 0.02
    bot_deteccao: float = 0.6
    p_pico_rpm_hora: float = 0.0
    pico_rpm_fator_min: float = 3.0
    pico_rpm_fator_max: float = 8.0
    # quebras de regime
    quebras: tuple[QuebraRegime, ...] = ()

    def __post_init__(self) -> None:
        if self.n_campanhas < 1 or self.n_dias < 1 or self.n_contas < 1:
            raise ValueError("n_campanhas, n_dias e n_contas precisam ser >= 1")
        if not (0.0 <= self.frac_campanhas_receita_usd <= 1.0):
            raise ValueError("frac_campanhas_receita_usd fora de [0, 1]")
        if self.funil_passos < 1:
            raise ValueError("funil_passos < 1")
        for nome in ("share_dispositivo", "prob_pais"):
            v = getattr(self, nome)
            if abs(sum(v) - 1.0) > 1e-9:
                raise ValueError(f"{nome} precisa somar 1")
        for q in self.quebras:
            if q.alvo not in ("rpm", "cpc"):
                raise ValueError(f"alvo de quebra inválido: {q.alvo}")
        if self.moeda_custo != "BRL":
            raise ValueError("o simulador modela custo Google Ads em BRL (contas sintéticas em BRL)")


@dataclass(frozen=True)
class JanelaForaDoAr:
    """Fonte indisponível de (início, início + duração) em horário local do período."""

    fonte: str
    inicio_frac_periodo: float
    hora_local: int
    duracao_h: int


@dataclass(frozen=True)
class ParametrosObservador:
    """Processo de OBSERVAÇÃO (o que cada fonte entrega e QUANDO). Ver 07-SIMULATOR-LAB.md §3."""

    # Google Ads: D0 em passadas intradiárias (parciais), D-1 (preliminar), backfill (final)
    gads_horas_d0: tuple[int, ...] = (6, 12, 18, 23)
    gads_lag_d0_h: int = 3
    gads_d1_hora: int = 4
    gads_frac_credito_d1: float = 0.5
    gads_backfill_dias: int = 3
    gads_backfill_hora: int = 5
    # JoinAds: intradiária estimada, releituras D-1..D-n, a última releitura fecha o valor
    join_horas_intradia: tuple[int, ...] = (6, 12, 18, 23)
    join_lag_intradia_h: int = 2
    join_d1_hora: int = 7
    join_releituras: int = 3
    join_f0: float = 0.85
    join_tau_maturacao_h: float = 18.0
    join_sigma_estimativa: float = 0.08
    join_quantum_micros: int = 10_000  # receita entregue a 2 casas decimais
    join_p_troca_chave_sem_dado: float = 1.0
    join_p_troca_chave_com_dado: float = 0.0
    join_ids_post_colidem: bool = False
    join_consulta_dispositivo: bool = True
    # site analytics (sessões e chegadas ao destino) — D-1
    site_d1_hora: int = 3
    # defeitos de coleta
    janelas_fora_do_ar: tuple[JanelaForaDoAr, ...] = ()
    p_execucao_indisponivel: float = 0.0
    p_ausente: float = 0.005
    p_payload_invalido: float = 0.002
    p_duplicata: float = 0.01
    p_atraso: float = 0.02
    atraso_min_h: float = 6.0
    atraso_max_h: float = 30.0
    p_zero_falso: float = 0.0
    p_retrodatar: float = 0.0
    p_execucao_presa: float = 0.0  # run fica em `running` sem reaper e não entrega nada
    # armadilhas confirmadas em produção (RECIBO-LEITURAS-20261016; INVENTARIO §10) — desligadas por default
    gads_zero_sintetizado: bool = False  # R3: coletor grava 0 para campanha sem linha de métrica
    gads_razao_campanhas_sem_metrica: float = 0.0  # R3: campanhas listadas sem tráfego, por campanha ativa
    site_descarta_utm_campaign_numerica: bool = False  # R2: sensor anula utm_campaign numérico >= 10 dígitos
    site_p_campanha_preservada: float = 0.02  # R2: fração de sessões pagas que ainda chega com campanha
    site_dedup_por_segundo: bool = False  # R4: UNIQUE (sid, pid, event_name, ts_sec) colapsa eventos
    site_p_colisao_humano: float = 0.03
    site_p_colisao_bot: float = 0.5
    emitir_legado_daily_metrics: bool = False  # R5: gatilho JoinAds→daily_campaign_metrics
    legado_dominios_por_campanha: int = 3
    legado_atraso_min: int = 5
    ingestao_lag_s_min: int = 5
    ingestao_lag_s_max: int = 300
    duracao_execucao_s_min: int = 30
    duracao_execucao_s_max: int = 600

    def __post_init__(self) -> None:
        if self.join_releituras < 1:
            raise ValueError("join_releituras >= 1 (a última releitura fecha o valor)")
        if self.gads_backfill_dias < 2:
            raise ValueError("gads_backfill_dias >= 2 (D-1 vem antes do backfill)")
        for j in self.janelas_fora_do_ar:
            if j.fonte not in FONTES:
                raise ValueError(f"fonte desconhecida: {j.fonte}")
        if not isinstance(self.join_quantum_micros, int) or self.join_quantum_micros < 1:
            raise TypeError("join_quantum_micros precisa ser int >= 1 (micros)")


@dataclass(frozen=True)
class EspecCenario:
    """Cenário nomeado: mundo + observador + o que ele exercita + a armadilha esperada."""

    nome: str
    descricao: str
    mundo: ParametrosMundo = field(default_factory=ParametrosMundo)
    observador: ParametrosObservador = field(default_factory=ParametrosObservador)
    exercita: tuple[str, ...] = ()
    armadilhas: tuple[str, ...] = ()
    adversarial: bool = False
    evidencia: str = ""  # de onde vem a armadilha (recibo/inventário), quando confirmada em produção

    def reduzir(self, *, n_campanhas: int | None = None, n_dias: int | None = None) -> "EspecCenario":
        """Mesmo cenário em outro tamanho (posições de eventos são frações do período)."""
        m = self.mundo
        novo = replace(m, n_campanhas=n_campanhas or m.n_campanhas, n_dias=n_dias or m.n_dias)
        return replace(self, mundo=novo)

    def como_dict(self) -> dict[str, Any]:
        return _para_json(asdict(self))


def _para_json(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _para_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_para_json(v) for v in o]
    return o


def nomes_campos(cls: type) -> tuple[str, ...]:
    return tuple(f.name for f in fields(cls))
