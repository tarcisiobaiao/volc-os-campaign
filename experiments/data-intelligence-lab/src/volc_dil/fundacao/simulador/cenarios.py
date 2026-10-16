"""Catálogo versionado de cenários nomeados do Simulator Lab.

Cada cenário é ``EspecCenario`` = mundo + observador + o que exercita + a armadilha esperada.
Tamanho default: 50 campanhas × 30 dias × 24 h (``escala_10x``: 500 × 30). Posições de eventos
são frações do período, então ``EspecCenario.reduzir`` preserva a semântica em outro tamanho.

Todos os cenários com o mesmo tamanho e seed compartilham a MESMA base aleatória (mundos
pareados, ver ``mundo.py``): a diferença entre ``estavel`` e ``outlier_bot`` é só o que o
cenário injeta. Mudar qualquer parâmetro de um cenário exige subir ``VERSAO_CATALOGO``.
"""
from __future__ import annotations

from dataclasses import replace

from volc_dil.contracts.fingerprint import sha256_de

from .parametros import (
    EspecCenario,
    JanelaForaDoAr,
    MudancaOrcamento,
    ParametrosMundo,
    ParametrosObservador,
    QuebraRegime,
)

VERSAO_CATALOGO = "1.0.0"

_M = ParametrosMundo()
_O = ParametrosObservador()


def _c(nome, descricao, mundo=None, obs=None, exercita=(), armadilhas=(), adversarial=False,
       evidencia="") -> EspecCenario:
    return EspecCenario(nome=nome, descricao=descricao, mundo=mundo or _M, observador=obs or _O,
                        exercita=tuple(exercita), armadilhas=tuple(armadilhas), adversarial=adversarial,
                        evidencia=evidencia)


def _construir() -> dict[str, EspecCenario]:
    cs = [
        _c("estavel",
           "Só campanhas maduras, sem quebra, sem outlier; observação com cadências default e taxas baixas de defeito.",
           mundo=replace(_M, frac_novas=0.0),
           exercita=("D0 parcial → D-1 → backfill", "estimativa JoinAds convergindo", "base pareada dos demais")),
        _c("campanha_nova_aprendendo",
           "Metade das campanhas lança dentro do período: volume em rampa, CPC alto e CTR baixo no aprendizado, ruído maior.",
           mundo=replace(_M, frac_novas=0.5, novas_inicio_max_frac=0.6),
           exercita=("curva de maturação de campanha nova", "heterocedasticidade no aprendizado",
                     "campanha sem histórico antes do lançamento (sem registro, não zero)")),
        _c("atraso_receita_longo",
           "Receita JoinAds sem intradiária, primeira leitura em D+1 10h e fechamento só na 6ª releitura; estimativas iniciais baixas.",
           obs=replace(_O, join_horas_intradia=(), join_d1_hora=10, join_releituras=6, join_f0=0.5,
                       join_tau_maturacao_h=60.0, join_sigma_estimativa=0.15, p_atraso=0.10),
           exercita=("atraso de receita de dias", "estimativa preliminar enviesada para baixo", "coleta atrasada")),
        _c("restatement_custo",
           "Cliques inválidos altos e crédito tardio: D0/D-1 superestimam o custo; o backfill em D+7 revisa para baixo.",
           mundo=replace(_M, taxa_cliques_invalidos=0.12, p_bot_hora=0.002, bot_deteccao=0.9),
           obs=replace(_O, gads_frac_credito_d1=0.2, gads_backfill_dias=7),
           exercita=("restatement de custo", "custo preliminar ≠ custo fechado")),
        _c("fonte_fora_do_ar",
           "JoinAds fora do ar 60 h (a partir de 40% do período) e Google Ads 14 h (70%), mais falhas esparsas de execução.",
           obs=replace(_O, p_execucao_indisponivel=0.01,
                       janelas_fora_do_ar=(JanelaForaDoAr("joinads", 0.4, 5, 60),
                                           JanelaForaDoAr("google_ads", 0.7, 10, 14))),
           exercita=("unavailable com valor None", "recuperação tardia (late) da leitura final")),
        _c("outlier_bot",
           "Rajadas de bots (cliques cobrados, quase sem pageview/receita, parcialmente creditados) e picos de RPM.",
           mundo=replace(_M, p_bot_hora=0.004, bot_mult=20.0, p_pico_rpm_hora=0.002),
           exercita=("outlier de clique inválido", "pico de RPM", "custo sem receita correspondente")),
        _c("quebra_regime_rpm",
           "Change points: RPM cai 40% em 70% das campanhas no meio do período; CPC sobe 40% em 30% delas aos 65%.",
           mundo=replace(_M, quebras=(QuebraRegime("rpm", 0.7, 0.5, 14, 0.6), QuebraRegime("cpc", 0.3, 0.65, 9, 1.4))),
           exercita=("quebra de regime de RPM", "mudança de CPC", "modelo que degrada sem avisar")),
        _c("mudanca_orcamento",
           "Orçamentos mais apertados; 30% das campanhas dobram o orçamento às 14h de 1/3 do período e 30% cortam pela metade às 9h de 2/3.",
           mundo=replace(_M, orcamento_razao_min=0.5, orcamento_razao_max=1.0,
                         mudancas_orcamento=(MudancaOrcamento(0.3, 1 / 3, 14, 2.0), MudancaOrcamento(0.3, 2 / 3, 9, 0.5))),
           exercita=("saturação de orçamento", "mudança intradiária de orçamento", "CPC sobe com o orçamento")),
        _c("sazonal_fim_de_semana",
           "Fim de semana com 60% do volume e 80% do RPM; ciclo diário mais forte.",
           mundo=replace(_M, fator_fds_volume=0.6, fator_fds_rpm=0.8, amp_diaria=0.7),
           exercita=("sazonalidade semanal", "sazonalidade diária")),
        _c("escala_10x",
           "10× campanhas (500) em 10 contas; mesma dinâmica do default. Mede custo do gerador e do observador.",
           mundo=replace(_M, n_campanhas=500, n_contas=10),
           exercita=("performance", "volume de registros")),
        _c("vazamento_tentado",
           "Leituras não intradiárias com observed_at retrodatado ao fim da janela: quem filtra por observed_at vê o valor revisado/final antes de ele existir.",
           obs=replace(_O, p_retrodatar=1.0, join_releituras=4),
           armadilhas=("retrodatado",), adversarial=True,
           exercita=("as_of por available_at", "vazamento de futuro")),
        _c("zero_falso",
           "A fonte devolve 0 (status observed) onde a linha está ausente ou a fonte caiu — forma do Google Ads MCP 0.0.4.",
           obs=replace(_O, p_zero_falso=1.0, p_ausente=0.03, p_execucao_indisponivel=0.02,
                       janelas_fora_do_ar=(JanelaForaDoAr("google_ads", 0.5, 8, 12),)),
           armadilhas=("zero_falso",), adversarial=True,
           exercita=("null ≠ zero", "zero que a verdade diz ausente/positivo")),
        _c("moeda_misturada",
           "Metade das campanhas tem receita JoinAds nativa em USD; custo sempre BRL. Somar sem moeda mistura grandezas.",
           mundo=replace(_M, frac_campanhas_receita_usd=0.5),
           armadilhas=("moeda_nao_brl",), adversarial=True,
           exercita=("moeda explícita", "ROAS sem câmbio é inválido")),
        _c("identidade_trocada",
           "JoinAds troca a custom_key para id_post_wp (5% das linhas com dado e todas sem dado) e os ids de post colidem com ids de campanha.",
           mundo=replace(_M, p_pausa_dia=0.05),
           obs=replace(_O, join_p_troca_chave_com_dado=0.05, join_ids_post_colidem=True),
           armadilhas=("custom_key_trocada", "id_colide_com_campanha"), adversarial=True,
           exercita=("identidade estrita", "custom_key efetiva ≠ solicitada")),
        # ── armadilhas CONFIRMADAS em produção (integrador, leitura read-only de 2026-10-16) ──
        _c("sensor_sem_campanha",
           "R2: o sensor anula utm_campaign numérico (≥10 dígitos); sessões pagas chegam só com source/medium/term, agregadas na conta. ~2% ainda carregam a campanha.",
           obs=replace(_O, site_descarta_utm_campaign_numerica=True, site_p_campanha_preservada=0.02),
           armadilhas=("campanha_descartada_sensor",), adversarial=True,
           exercita=("sessão sem chave de campanha", "ausente ≠ zero no join sessão×campanha"),
           evidencia="RECIBO-LEITURAS-20261016 L4 (28/28 sessões paid sem utm.campaign); INVENTARIO §10 R2"),
        _c("zero_sintetizado_coletor",
           "R3: o coletor grava cost=0/impressions=0 para campanha sem linha de métrica (4 campanhas listadas sem tráfego por campanha ativa ⇒ ~80% de linhas zeradas) e para linha ausente de campanha ativa.",
           obs=replace(_O, gads_zero_sintetizado=True, gads_razao_campanhas_sem_metrica=4.0, p_ausente=0.03),
           armadilhas=("zero_sintetizado", "campanha_sem_linha"), adversarial=True,
           exercita=("zero sintetizado indistinguível de zero confirmado", "prova de status da campanha"),
           evidencia="RECIBO-LEITURAS-20261016 L11 (88 de 110 campaign_day com cost=0 e impressions=0); INVENTARIO §10 R3"),
        _c("dedup_por_segundo",
           "R4: raw_events deduplica por (sid, pid, event_name, ts_sec); pageviews do mesmo nome no mesmo segundo colapsam (3% humano, 50% bot), somados a rajadas de bot.",
           mundo=replace(_M, p_bot_hora=0.004, bot_mult=20.0, bot_continuacao=0.8),
           obs=replace(_O, site_dedup_por_segundo=True),
           armadilhas=("dedup_por_segundo",), adversarial=True,
           exercita=("contagem do sensor < verdade", "subcontagem correlacionada com bot"),
           evidencia="RECIBO-LEITURAS-20261016 L3 (UNIQUE raw_events_dedup); INVENTARIO §10 R4"),
        _c("gatilho_legado_joinads",
           "R5: fonte legado_daily_metrics = efeito do gatilho JoinAds→daily_campaign_metrics: receita só do último domínio (3 domínios por campanha) e custo 0 na linha nova até a sincronização de custo.",
           obs=replace(_O, emitir_legado_daily_metrics=True, legado_dominios_por_campanha=3),
           armadilhas=("ultimo_dominio_vence", "custo_zero_inserido"), adversarial=True,
           exercita=("receita subcontada por sobrescrita", "custo 0 que não é medição", "não ler daily_campaign_metrics"),
           evidencia="RECIBO-LEITURAS-20261016 L2 (trg_joinads_sync_daily ativo); INVENTARIO §10 R5"),
        _c("custo_d0_multiversao",
           "Custo D0 com 16 runs por dia (7h–22h, atraso de 1 h): até ~16 versões distintas de cost_micros por campanha-dia antes do D-1.",
           obs=replace(_O, gads_horas_d0=tuple(range(7, 23)), gads_lag_d0_h=1),
           armadilhas=("multiversao_d0",), adversarial=True,
           exercita=("maturação intradiária de custo", "as_of escolhe a versão certa"),
           evidencia="RECIBO-LEITURAS-20261016 L10 (15/10: 80 leituras, 14 valores distintos de cost_micros, 16 runs)"),
        _c("execucao_presa",
           "5% dos runs ficam presos em running (sem reaper) e não entregam nada; leitura final presa é recuperada mais tarde (late).",
           obs=replace(_O, p_execucao_presa=0.05),
           armadilhas=("run_preso",), adversarial=True,
           exercita=("observabilidade de runs órfãos", "lacuna sem registro de falha"),
           evidencia="RECIBO-LEITURAS-20261016 L9 (3 runs em running desde 15/10 11:48)"),
    ]
    return {c.nome: c for c in cs}


CATALOGO: dict[str, EspecCenario] = _construir()
NOMES = tuple(CATALOGO)
ADVERSARIAIS = tuple(n for n, c in CATALOGO.items() if c.adversarial)


def cenario(nome: str) -> EspecCenario:
    try:
        return CATALOGO[nome]
    except KeyError as exc:
        raise KeyError(f"cenário desconhecido: {nome!r}; conhecidos: {', '.join(NOMES)}") from exc


def catalogo_sha256() -> str:
    """Fingerprint do catálogo inteiro (muda se qualquer parâmetro mudar)."""
    return sha256_de({"versao": VERSAO_CATALOGO, "cenarios": {n: c.como_dict() for n, c in CATALOGO.items()}})
