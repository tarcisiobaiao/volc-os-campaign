from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from volc_ads.inteligencia_google.modelo import DocumentoColeta, EstadoColeta
from volc_ads.inteligencia_google.saude import (
    EstadoSaudeColetor,
    FalhaColetor,
    IdentidadeColetor,
    MotivoDiagnostico,
    ReciboColetor,
    ScheduleColetor,
    avaliar_saude_coletores,
    detectar_conflitos_schedules,
    projetar_saude_coletor,
    recibo_de_documentos,
)


@pytest.fixture
def agora() -> datetime:
    return datetime(2026, 8, 29, 18, tzinfo=timezone.utc)


def identidade(
    *,
    login_customer_id: str = "6016739364",
    customer_id: str = "8017851692",
    coletor_id: str = "google-inteligencia-d0",
    tipo_coletor: str = "EXPERIMENTOS",
) -> IdentidadeColetor:
    return IdentidadeColetor(
        login_customer_id=login_customer_id,
        customer_id=customer_id,
        coletor_id=coletor_id,
        tipo_coletor=tipo_coletor,
    )


def schedule(**trocas) -> ScheduleColetor:
    base = {"intervalo_esperado": timedelta(hours=1)}
    base.update(trocas)
    return ScheduleColetor(**base)


def recibo(agora: datetime, **trocas) -> ReciboColetor:
    base = {
        "identidade": identidade(),
        "schedule": schedule(),
        "ultima_tentativa_em": agora - timedelta(minutes=10),
        "ultimo_sucesso_em": agora - timedelta(minutes=10),
    }
    base.update(trocas)
    return ReciboColetor(**base)


def documento(
    instante: datetime,
    *,
    estado: EstadoColeta = EstadoColeta.VAZIO_CONFIRMADO,
    customer_id: str = "8017851692",
    login_customer_id: str = "6016739364",
    tipo_sinal: str = "EXPERIMENTOS",
    erro_codigo: str | None = None,
    erro_classe: str | None = None,
    erro_detalhe: str | None = None,
) -> DocumentoColeta:
    if estado in {
        EstadoColeta.INELEGIVEL,
        EstadoColeta.NAO_SUPORTADO,
        EstadoColeta.FALHOU,
    }:
        quantidade = None
    elif estado is EstadoColeta.COM_DADOS:
        quantidade = 1
    else:
        quantidade = 0
    return DocumentoColeta(
        tipo_sinal=tipo_sinal,
        estado=estado,
        customer_id=customer_id,
        login_customer_id=login_customer_id,
        competencia=date(2026, 8, 29),
        coletada_em=instante,
        bucket="daily:2026-08-29",
        quantidade=quantidade,
        erro_codigo=erro_codigo,
        erro_classe=erro_classe,
        erro_detalhe=erro_detalhe,
    )


class TestContrato:
    def test_identidade_normaliza_mcc_conta_job_e_tipo(self):
        escopo = identidade(
            login_customer_id="601-673-9364",
            customer_id=" 801 785 1692 ",
            coletor_id=" Google-Inteligencia-D0 ",
            tipo_coletor=" experimentos ",
        )
        assert escopo == IdentidadeColetor(
            "6016739364", "8017851692", "google-inteligencia-d0", "EXPERIMENTOS"
        )

    @pytest.mark.parametrize("campo", ["login_customer_id", "customer_id"])
    def test_identidade_recusa_conta_invalida(self, campo):
        argumentos = {
            "login_customer_id": "6016739364",
            "customer_id": "8017851692",
            "coletor_id": "job",
            "tipo_coletor": "TIPO",
        }
        argumentos[campo] = "tenant-a"
        with pytest.raises(ValueError, match="digitos"):
            IdentidadeColetor(**argumentos)

    def test_schedule_preserva_zero_e_recusa_intervalo_nao_positivo(self):
        configurado = schedule(
            tolerancia_atraso=timedelta(0),
            tolerancia_heartbeat=timedelta(0),
        )
        assert configurado.tolerancia_atraso == timedelta(0)
        assert configurado.tolerancia_heartbeat == timedelta(0)
        with pytest.raises(ValueError, match="estritamente positivo"):
            schedule(intervalo_esperado=timedelta(0))

    def test_falha_e_estruturada_e_nao_aceita_detalhe_livre(self):
        falha = FalhaColetor("RESOURCE_EXHAUSTED", "GoogleAdsException")
        assert falha.codigo == "RESOURCE_EXHAUSTED"
        assert not hasattr(falha, "detalhe")
        with pytest.raises(ValueError, match="rotulo publico"):
            FalhaColetor("Bearer SECRET-TOKEN", "Runtime Error")

    def test_falha_exige_tentativa(self):
        with pytest.raises(ValueError, match="exige ultima_tentativa"):
            ReciboColetor(
                identidade=identidade(),
                schedule=schedule(),
                falha_ultima_tentativa=FalhaColetor("TIMEOUT", "TimeoutError"),
            )

    def test_relogio_e_obrigatoriamente_injetado(self, agora):
        with pytest.raises(ValueError, match="exatamente um"):
            projetar_saude_coletor(recibo(agora))
        with pytest.raises(ValueError, match="exatamente um"):
            projetar_saude_coletor(recibo(agora), now=agora, clock=lambda: agora)
        assert projetar_saude_coletor(
            recibo(agora), clock=lambda: agora
        ).calculado_em == agora


class TestTabelaVerdade:
    def test_saudavel_exige_sucesso_confirmado(self, agora):
        projecao = projetar_saude_coletor(recibo(agora), now=agora)
        assert projecao.estado is EstadoSaudeColetor.SAUDAVEL
        assert projecao.motivo is MotivoDiagnostico.OK

    def test_tentativa_sem_primeiro_sucesso_e_indeterminada(self, agora):
        projecao = projetar_saude_coletor(
            recibo(agora, ultimo_sucesso_em=None), now=agora
        )
        assert projecao.estado is EstadoSaudeColetor.INDETERMINADO
        assert projecao.motivo is MotivoDiagnostico.TENTATIVA_SEM_DESFECHO

    def test_tentativa_sem_sucesso_expirada_e_atrasada(self, agora):
        projecao = projetar_saude_coletor(
            recibo(
                agora,
                ultima_tentativa_em=agora - timedelta(hours=2),
                ultimo_sucesso_em=None,
            ),
            now=agora,
        )
        assert projecao.estado is EstadoSaudeColetor.ATRASADO
        assert projecao.motivo is MotivoDiagnostico.SEM_SUCESSO_CONFIRMADO
        assert projecao.atraso_estimado == timedelta(hours=1)

    def test_nova_tentativa_sem_desfecho_nao_usa_sucesso_anterior(self, agora):
        projecao = projetar_saude_coletor(
            recibo(
                agora,
                ultima_tentativa_em=agora - timedelta(minutes=5),
                ultimo_sucesso_em=agora - timedelta(minutes=20),
            ),
            now=agora,
        )
        assert projecao.estado is EstadoSaudeColetor.INDETERMINADO
        assert projecao.motivo is MotivoDiagnostico.TENTATIVA_SEM_DESFECHO

    @pytest.mark.parametrize(
        "heartbeat",
        [None, datetime(2026, 8, 29, 17, 55, tzinfo=timezone.utc)],
    )
    def test_sem_execucao_e_nunca_executado_mesmo_com_heartbeat(self, agora, heartbeat):
        projecao = projetar_saude_coletor(
            recibo(
                agora,
                ultima_tentativa_em=None,
                ultimo_sucesso_em=None,
                ultimo_heartbeat_em=heartbeat,
            ),
            now=agora,
        )
        assert projecao.estado is EstadoSaudeColetor.NUNCA_EXECUTADO
        assert projecao.motivo is MotivoDiagnostico.SEM_EXECUCAO_PREVIA

    def test_heartbeat_obrigatorio_ausente_e_indeterminado_nao_zero(self, agora):
        projecao = projetar_saude_coletor(
            recibo(
                agora,
                schedule=schedule(tolerancia_heartbeat=timedelta(minutes=15)),
                ultimo_heartbeat_em=None,
            ),
            now=agora,
        )
        assert projecao.estado is EstadoSaudeColetor.INDETERMINADO
        assert projecao.motivo is MotivoDiagnostico.HEARTBEAT_AUSENTE
        assert projecao.tempo_desde_ultimo_heartbeat is None

    def test_heartbeat_expirado_e_atrasado(self, agora):
        projecao = projetar_saude_coletor(
            recibo(
                agora,
                schedule=schedule(tolerancia_heartbeat=timedelta(minutes=5)),
                ultimo_heartbeat_em=agora - timedelta(minutes=15),
            ),
            now=agora,
        )
        assert projecao.estado is EstadoSaudeColetor.ATRASADO
        assert projecao.motivo is MotivoDiagnostico.HEARTBEAT_EXPIRADO
        assert projecao.atraso_estimado == timedelta(minutes=10)

    def test_heartbeat_zero_exige_sinal_no_mesmo_instante(self, agora):
        projecao = projetar_saude_coletor(
            recibo(
                agora,
                schedule=schedule(tolerancia_heartbeat=timedelta(0)),
                ultimo_heartbeat_em=agora,
            ),
            now=agora,
        )
        assert projecao.estado is EstadoSaudeColetor.SAUDAVEL

    def test_sucesso_stale_e_atrasado(self, agora):
        projecao = projetar_saude_coletor(
            recibo(
                agora,
                ultima_tentativa_em=agora - timedelta(hours=2),
                ultimo_sucesso_em=agora - timedelta(hours=2),
            ),
            now=agora,
        )
        assert projecao.estado is EstadoSaudeColetor.ATRASADO
        assert projecao.motivo is MotivoDiagnostico.INTERVALO_EXECUCAO_EXPIRADO

    def test_fronteira_exata_da_janela_ainda_e_saudavel(self, agora):
        instante = agora - timedelta(hours=1, minutes=10)
        projecao = projetar_saude_coletor(
            recibo(
                agora,
                schedule=schedule(tolerancia_atraso=timedelta(minutes=10)),
                ultima_tentativa_em=instante,
                ultimo_sucesso_em=instante,
            ),
            now=agora,
        )
        assert projecao.estado is EstadoSaudeColetor.SAUDAVEL

    def test_falha_preserva_ultimo_sucesso_sem_expor_detalhe(self, agora):
        projecao = projetar_saude_coletor(
            recibo(
                agora,
                ultima_tentativa_em=agora - timedelta(minutes=5),
                ultimo_sucesso_em=agora - timedelta(hours=2),
                falha_ultima_tentativa=FalhaColetor("TIMEOUT", "TimeoutError"),
            ),
            now=agora,
        )
        assert projecao.estado is EstadoSaudeColetor.FALHOU
        assert projecao.tempo_desde_ultimo_sucesso == timedelta(hours=2)
        assert projecao.tempo_desde_ultima_tentativa == timedelta(minutes=5)
        assert "TIMEOUT/TimeoutError" in projecao.mensagem

    def test_desabilitado_tem_estado_proprio(self, agora):
        projecao = projetar_saude_coletor(
            recibo(agora, schedule=schedule(desabilitado=True)), now=agora
        )
        assert projecao.estado is EstadoSaudeColetor.DESABILITADO

    def test_schedule_ausente_e_indeterminado(self, agora):
        projecao = projetar_saude_coletor(
            recibo(agora, schedule=None), now=agora
        )
        assert projecao.estado is EstadoSaudeColetor.INDETERMINADO
        assert projecao.motivo is MotivoDiagnostico.SCHEDULE_AUSENTE

    def test_timezone_naive_e_futuro_falham_fechado(self, agora):
        naive = projetar_saude_coletor(
            recibo(
                agora,
                ultima_tentativa_em=datetime(2026, 8, 29, 17),
                ultimo_sucesso_em=None,
            ),
            now=agora,
        )
        futuro = projetar_saude_coletor(
            recibo(
                agora,
                ultima_tentativa_em=agora + timedelta(seconds=1),
                ultimo_sucesso_em=None,
            ),
            now=agora,
        )
        assert naive.motivo is MotivoDiagnostico.TIMEZONE_NAIVE
        assert futuro.motivo is MotivoDiagnostico.TIMESTAMP_NO_FUTURO

    def test_sucesso_sem_tentativa_e_inconsistencia(self, agora):
        projecao = projetar_saude_coletor(
            recibo(
                agora,
                ultima_tentativa_em=None,
                ultimo_sucesso_em=agora - timedelta(minutes=5),
            ),
            now=agora,
        )
        assert projecao.motivo is MotivoDiagnostico.INCONSISTENCIA_TEMPORAL

    def test_mesma_entrada_e_relogio_produzem_mesma_saida(self, agora):
        entrada = recibo(agora)
        assert projetar_saude_coletor(
            entrada, now=agora
        ) == projetar_saude_coletor(entrada, now=agora)


class TestIsolamentoDeTenant:
    def test_schedules_de_contas_diferentes_nao_conflitam(self, agora):
        conta_a = recibo(agora, identidade=identidade(customer_id="1111111111"))
        conta_b = recibo(
            agora,
            identidade=identidade(customer_id="2222222222"),
            schedule=schedule(intervalo_esperado=timedelta(hours=8)),
        )
        projecoes = avaliar_saude_coletores([conta_a, conta_b], now=agora)
        assert [p.estado for p in projecoes] == [
            EstadoSaudeColetor.SAUDAVEL,
            EstadoSaudeColetor.SAUDAVEL,
        ]

    def test_schedules_de_mccs_diferentes_nao_conflitam(self, agora):
        mcc_a = recibo(agora, identidade=identidade(login_customer_id="1111111111"))
        mcc_b = recibo(
            agora,
            identidade=identidade(login_customer_id="2222222222"),
            schedule=schedule(intervalo_esperado=timedelta(hours=8)),
        )
        assert all(
            p.estado is EstadoSaudeColetor.SAUDAVEL
            for p in avaliar_saude_coletores([mcc_a, mcc_b], now=agora)
        )

    def test_schedules_divergentes_no_mesmo_escopo_conflitam(self, agora):
        escopo = identidade()
        primeiro = recibo(agora, identidade=escopo)
        segundo = recibo(
            agora,
            identidade=escopo,
            schedule=schedule(intervalo_esperado=timedelta(hours=8)),
        )
        projecoes = avaliar_saude_coletores([primeiro, segundo], now=agora)
        assert all(
            p.motivo is MotivoDiagnostico.SCHEDULE_CONFLITANTE
            for p in projecoes
        )

    def test_detector_exige_chave_de_identidade(self):
        with pytest.raises(TypeError, match="IdentidadeColetor"):
            detectar_conflitos_schedules({"job": [schedule(), schedule()]})


class TestAdaptadorContratoReal:
    def test_documento_vazio_confirmado_com_zero_e_sucesso_real(self, agora):
        doc = documento(agora - timedelta(minutes=5))
        entrada = recibo_de_documentos(
            [doc], coletor_id="google-inteligencia-d0", schedule=schedule()
        )
        assert entrada.customer_id == "8017851692"
        assert entrada.tipo_coletor == "EXPERIMENTOS"
        assert entrada.ultimo_sucesso_em == agora - timedelta(minutes=5)
        assert projetar_saude_coletor(entrada, now=agora).estado is EstadoSaudeColetor.SAUDAVEL

    def test_registro_serializado_normaliza_identidade_e_iso_z(self, agora):
        entrada = recibo_de_documentos(
            [{
                "login_customer_id": "601-673-9364",
                "customer_id": "801-785-1692",
                "tipo_sinal": "experimentos",
                "coletada_em": "2026-08-29T17:55:00Z",
                "estado": "vazio_confirmado",
                "erro_codigo": None,
                "erro_classe": None,
            }],
            coletor_id=" Google-Inteligencia-D0 ",
            schedule=schedule(),
        )
        assert entrada.identidade == identidade()
        assert projetar_saude_coletor(entrada, now=agora).estado is EstadoSaudeColetor.SAUDAVEL

    def test_falha_recente_preserva_sucesso_anterior_e_ignora_detalhe(self, agora):
        historico = [
            documento(agora - timedelta(hours=2)),
            documento(
                agora - timedelta(minutes=5),
                estado=EstadoColeta.FALHOU,
                erro_codigo="TIMEOUT",
                erro_classe="TimeoutError",
                erro_detalhe="Bearer SECRET-TOKEN customer=8017851692",
            ),
        ]
        entrada = recibo_de_documentos(
            historico, coletor_id="google-inteligencia-d0", schedule=schedule()
        )
        projecao = projetar_saude_coletor(entrada, now=agora)
        assert projecao.estado is EstadoSaudeColetor.FALHOU
        assert projecao.tempo_desde_ultimo_sucesso == timedelta(hours=2)
        assert "SECRET-TOKEN" not in projecao.mensagem
        assert "8017851692" not in projecao.mensagem

    def test_rotulo_de_erro_inseguro_vira_codigo_generico(self, agora):
        entrada = recibo_de_documentos(
            [{
                "login_customer_id": "6016739364",
                "customer_id": "8017851692",
                "tipo_sinal": "EXPERIMENTOS",
                "coletada_em": agora - timedelta(minutes=5),
                "estado": "falhou",
                "erro_codigo": "Bearer SECRET-TOKEN",
                "erro_classe": "Runtime Error",
                "erro_detalhe": "nao deve ser lido",
            }],
            coletor_id="job",
            schedule=schedule(),
        )
        assert entrada.falha_ultima_tentativa == FalhaColetor(
            "FALHA_COLETA", "ErroColeta"
        )

    def test_falha_e_sucesso_no_mesmo_instante_falham_fechado(self, agora):
        entrada = recibo_de_documentos(
            [
                documento(agora - timedelta(minutes=5)),
                documento(
                    agora - timedelta(minutes=5),
                    estado=EstadoColeta.FALHOU,
                    erro_codigo="PARCIAL",
                    erro_classe="FalhaParcial",
                ),
            ],
            coletor_id="job",
            schedule=schedule(),
        )
        assert projetar_saude_coletor(entrada, now=agora).estado is EstadoSaudeColetor.FALHOU

    def test_sucesso_posterior_supera_falha_antiga(self, agora):
        entrada = recibo_de_documentos(
            [
                documento(
                    agora - timedelta(minutes=30),
                    estado=EstadoColeta.FALHOU,
                    erro_codigo="TIMEOUT",
                    erro_classe="TimeoutError",
                ),
                documento(agora - timedelta(minutes=5)),
            ],
            coletor_id="job",
            schedule=schedule(),
        )
        assert entrada.falha_ultima_tentativa is None
        assert projetar_saude_coletor(entrada, now=agora).estado is EstadoSaudeColetor.SAUDAVEL

    def test_historico_nao_pode_misturar_tenants_ou_tipos(self, agora):
        with pytest.raises(ValueError, match="misturam tenant"):
            recibo_de_documentos(
                [
                    documento(agora, customer_id="1111111111"),
                    documento(agora, customer_id="2222222222"),
                ],
                coletor_id="job",
                schedule=schedule(),
            )

    def test_registro_falho_exige_codigo_e_classe_nao_vazios(self, agora):
        registro = {
            "login_customer_id": "6016739364",
            "customer_id": "8017851692",
            "tipo_sinal": "EXPERIMENTOS",
            "coletada_em": agora,
            "estado": "falhou",
            "erro_codigo": "",
            "erro_classe": "TimeoutError",
        }
        with pytest.raises(ValueError, match="exige erro_codigo"):
            recibo_de_documentos([registro], coletor_id="job", schedule=schedule())

    def test_registro_nao_falho_nao_aceita_erro_stale(self, agora):
        registro = {
            "login_customer_id": "6016739364",
            "customer_id": "8017851692",
            "tipo_sinal": "EXPERIMENTOS",
            "coletada_em": agora,
            "estado": "vazio_confirmado",
            "erro_codigo": "TIMEOUT",
            "erro_classe": "TimeoutError",
        }
        with pytest.raises(ValueError, match="nao falho"):
            recibo_de_documentos([registro], coletor_id="job", schedule=schedule())

    def test_adaptador_recusa_historico_vazio(self):
        with pytest.raises(ValueError, match="ao menos um"):
            recibo_de_documentos([], coletor_id="job", schedule=schedule())
