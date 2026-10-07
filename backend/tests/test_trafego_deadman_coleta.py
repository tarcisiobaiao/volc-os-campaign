"""O deadman da coleta D0/D-1: o que ele afirma, e o que ele se recusa a afirmar.

Um deadman erra de duas formas, e as duas custam caro:
 - alarme falso treina gente a ignorar alarme;
 - silêncio confortável esconde rotina morta.

Estas provas medem exatamente a fronteira entre as duas.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.trafego.deadman_coleta import (
    FonteDeEvidencia,
    JobDeColeta,
    diagnosticar_coleta,
    intervalo_do_cron,
    job_do_workflow,
)
from volc_ads.inteligencia_google.saude import EstadoSaudeColetor, MotivoDiagnostico

RAIZ = Path(__file__).resolve().parents[2]
D0 = RAIZ / "n8n" / "volc_gads_campanha_dia_d0.json"
D1 = RAIZ / "n8n" / "volc_gads_campanha_dia_d1.json"

AGORA = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
CONTA = "5470000000"


def _job(**troca) -> JobDeColeta:
    base = dict(
        job="gads_dia_d0",
        origem_janela="D0",
        cron="0 6,12,18,23 * * *",
        ativo=True,
        fuso="America/Sao_Paulo",
        workflow_arquivo="teste",
    )
    base.update(troca)
    return JobDeColeta(**base)


def _fechamento(**troca) -> dict:
    base = {
        "job": "gads_dia_d0",
        "origem_janela": "D0",
        "execucao_chave": "gads_dia_d0:D0:2026-09-02:06",
        "resultado": "ok",
        "motivo": None,
        "encerrada_em": AGORA - timedelta(hours=1),
        "batimento_em": AGORA - timedelta(hours=1),
        "linhas_aceitas": 3,
    }
    base.update(troca)
    return base


def _diag(job, fechamentos, **kw):
    return diagnosticar_coleta(
        job, fechamentos, login_customer_id=CONTA, customer_id=CONTA, now=AGORA, **kw
    )


# ────────────────────────────────────────────────── a expectativa, e seu erro ──

def test_o_intervalo_e_o_MAIOR_salto_e_nao_o_menor():
    """Se fosse o menor, toda passada das 23h nasceria atrasada de madrugada.

    D0 roda 06/12/18/23: os saltos são 6h, 6h, 5h e 7h (23h → 06h do dia
    seguinte). Esperar 5h produziria alarme todo dia às 04h, sem nada ter
    acontecido. O deadman tem de esperar o pior caso legítimo.
    """
    assert intervalo_do_cron("0 6,12,18,23 * * *") == timedelta(hours=7)
    assert intervalo_do_cron("0 6 * * *") == timedelta(days=1)


def test_cron_que_o_parser_nao_entende_e_recusado_e_nao_chutado():
    for expressao in ("0 6 1 * *", "0 6 * 3 *", "*/5 * * * *", "0 6 * *", "0 99 * * *"):
        with pytest.raises(ValueError):
            intervalo_do_cron(expressao)


def test_a_expectativa_sai_dos_workflows_versionados_de_verdade():
    for caminho, job_esperado, modo, cron in (
        (D0, "gads_dia_d0", "D0", "0 6,12,18,23 * * *"),
        (D1, "gads_dia_d1", "D-1", "0 6 * * *"),
    ):
        j = job_do_workflow(json.loads(caminho.read_text()), caminho.name)
        assert (j.job, j.origem_janela, j.cron) == (job_esperado, modo, cron)
        # O contrato de hoje: os dois seguem INATIVOS.
        assert j.ativo is False


def test_active_ausente_nao_vira_ligado():
    """Padrão seguro: agenda cujo estado ninguém declarou é agenda desligada."""
    bruto = json.loads(D0.read_text())
    bruto.pop("active", None)
    assert job_do_workflow(bruto, "sem-active").ativo is False


def test_cron_e_PASSOS_em_desacordo_e_recusado_com_nome():
    """Duas declarações da mesma agenda que divergem = expectativa ambígua."""
    bruto = json.loads(D0.read_text())
    for no in bruto["nodes"]:
        if no["name"] == "Config":
            for a in no["parameters"]["assignments"]["assignments"]:
                if a["name"] == "PASSOS":
                    a["value"] = "06,12"
    with pytest.raises(ValueError, match="AGENDA_AMBIGUA"):
        job_do_workflow(bruto, "divergente")


# ──────────────────────────────────────── não conseguir olhar não é "não houve" ──

@pytest.mark.parametrize("fonte", [FonteDeEvidencia.VIEW_AUSENTE, FonteDeEvidencia.LEITURA_FALHOU])
def test_sem_fonte_o_estado_e_indeterminado_e_nunca_uma_afirmacao_sobre_o_mundo(fonte):
    """A v12_04 não está aplicada no banco oficial: a view não existe.

    Quem não consegue observar não pode dizer "nunca executou" nem "está tudo
    bem". As duas seriam afirmações sobre um mundo que não foi olhado.
    """
    p = _diag(_job(), None, fonte=fonte)
    assert p.estado is EstadoSaudeColetor.INDETERMINADO
    assert p.estado is not EstadoSaudeColetor.NUNCA_EXECUTADO
    assert p.estado is not EstadoSaudeColetor.SAUDAVEL


def test_olhar_e_nao_achar_nada_e_diferente_de_nao_conseguir_olhar():
    """Com a fonte disponível e a agenda LIGADA, zero execução é NUNCA_EXECUTADO."""
    p = _diag(_job(ativo=True), [])
    assert p.estado is EstadoSaudeColetor.NUNCA_EXECUTADO


def test_agenda_desligada_por_contrato_nao_e_rotina_atrasada():
    """Hoje os dois workflows estão active:false. Gritar aqui seria ruído."""
    p = _diag(_job(ativo=False), [])
    assert p.estado is EstadoSaudeColetor.DESABILITADO
    assert p.motivo is MotivoDiagnostico.COLETOR_DESABILITADO


# ──────────────────────────────────────────────── o desfecho, e o falso verde ──

def test_sucesso_recente_com_agenda_ligada_e_saudavel():
    p = _diag(_job(ativo=True), [_fechamento()])
    assert p.estado is EstadoSaudeColetor.SAUDAVEL


def test_parcial_NAO_e_sucesso():
    """A v12_04 recusa fechar 'ok' com linha rejeitada. Essa recusa não pode
    ser desfeita aqui promovendo 'parcial' a saudável."""
    p = _diag(_job(ativo=True), [_fechamento(resultado="parcial", motivo="3 linhas rejeitadas")])
    assert p.estado is not EstadoSaudeColetor.SAUDAVEL
    assert p.estado is EstadoSaudeColetor.FALHOU


def test_falhou_e_falhou():
    p = _diag(_job(ativo=True), [_fechamento(resultado="falhou", motivo="todas as contas falharam")])
    assert p.estado is EstadoSaudeColetor.FALHOU


def test_sucesso_velho_demais_e_atraso_e_nao_saude():
    """Sucesso de 9h atrás, com intervalo esperado de 7h: a rotina parou."""
    velho = AGORA - timedelta(hours=9)
    p = _diag(_job(ativo=True), [_fechamento(encerrada_em=velho, batimento_em=velho)])
    assert p.estado is EstadoSaudeColetor.ATRASADO


def test_o_motivo_bruto_do_ledger_nunca_atravessa_para_a_projecao():
    """O motivo cita conta e campanha; a projeção de saúde é superfície pública."""
    segredo = "8017851692/AUTENTICACAO e 7788990011/COTA"
    p = _diag(_job(ativo=True), [_fechamento(resultado="falhou", motivo=segredo)])
    inteiro = json.dumps(
        {
            "mensagem": p.mensagem,
            "motivo": p.motivo.value,
            "codigo": p.falha_codigo.value if p.falha_codigo else None,
            "classe": p.falha_classe.value if p.falha_classe else None,
        }
    )
    assert "8017851692" not in inteiro
    assert "7788990011" not in inteiro
    assert segredo not in inteiro


def test_execucao_de_OUTRO_job_nao_cura_este():
    """O fechamento do D0 não pode fazer o D-1 parecer saudável."""
    do_d0 = _fechamento(job="gads_dia_d0", origem_janela="D0")
    p = _diag(_job(job="gads_dia_d1", origem_janela="D-1", cron="0 6 * * *", ativo=True), [do_d0])
    assert p.estado is EstadoSaudeColetor.NUNCA_EXECUTADO


def test_a_execucao_mais_recente_e_a_que_vale_mesmo_fora_de_ordem():
    velho_ok = _fechamento(
        execucao_chave="a", resultado="ok",
        encerrada_em=AGORA - timedelta(hours=6), batimento_em=AGORA - timedelta(hours=6),
    )
    novo_falho = _fechamento(
        execucao_chave="b", resultado="falhou", motivo="caiu",
        encerrada_em=AGORA - timedelta(hours=1), batimento_em=AGORA - timedelta(hours=1),
    )
    # ordem embaralhada de propósito: quem decide é o relógio, não a posição
    p = _diag(_job(ativo=True), [velho_ok, novo_falho])
    assert p.estado is EstadoSaudeColetor.FALHOU


def test_timestamp_naive_nao_e_normalizado_por_conveniencia():
    """Converter naive para UTC aqui apagaria a anomalia que o contrato denuncia."""
    naive = datetime(2026, 9, 2, 11, 0)
    p = _diag(_job(ativo=True), [_fechamento(encerrada_em=naive, batimento_em=naive)])
    assert p.estado is EstadoSaudeColetor.INDETERMINADO


def test_os_workflows_reais_de_hoje_produzem_o_estado_honesto_de_hoje():
    """Fim a fim, com os artefatos versionados e o banco oficial como ele está:
    v12_04 não aplicada => a view não existe => INDETERMINADO nos dois jobs."""
    for caminho in (D0, D1):
        j = job_do_workflow(json.loads(caminho.read_text()), caminho.name)
        p = _diag(j, None, fonte=FonteDeEvidencia.VIEW_AUSENTE)
        assert p.estado is EstadoSaudeColetor.INDETERMINADO
        assert "v12_04" in p.mensagem
