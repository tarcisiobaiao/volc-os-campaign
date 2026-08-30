"""Banco de provas de `subir.py` e `isencao.py`. Zero rede, zero conta tocada.

Rodar da raiz do projeto — e SÓ com `-m`:

    PYTHONPATH=. backend/.venv/bin/python -m volc_ads.testes_subir

⚠️ `python volc_ads/testes_subir.py` (por CAMINHO) quebra, e a mensagem não
aponta para cá: rodar por caminho põe `volc_ads/` no início do `sys.path`, e
`volc_ads/copy/` passa a sombrear o módulo `copy` da STDLIB. O SDK do Google
morre em `from copy import deepcopy`, dentro de
`google/ads/googleads/interceptors/helpers.py`. Quem cair nisso conclui que a
suíte está quebrada — ela não está; o comando é que estava errado.

⚠️ Os 24 casos deste arquivo rodam por este `main()`, e NÃO pelo `pytest`. Sob
o `pytest.ini` do projeto (`python_functions = test_* prova_*`), o pytest coleta
daqui apenas os 4 `test_*`. Somar "458 passed" com "23/24" seria somar dois
universos diferentes e inventar cobertura.

## Como este arquivo consegue provar o caminho de escrita sem escrever

Não usa dublê para o Google. Usa os **protos de verdade** da v25 instalada:
`GoogleAdsClient` é construído com uma credencial falsa, o que não fala com
ninguém — construir o cliente não abre conexão — e `get_type()` devolve as
mensagens reais. Então quando um teste afirma que
`ad_group_ad_operation.policy_validation_parameter.exempt_policy_violation_keys`
existe e aceita uma `PolicyViolationKey`, isso não é a opinião de um mock: é o
proto da v25 respondendo. Um nome de campo errado quebra o teste na hora, que
é exatamente a classe de erro que custa uma chamada recusada.

O que continua sendo dublê é o que devolve rede: a resposta do mutate e as
exceções. Essas são montadas à mão — mas a resposta é montada com o tipo real
`MutateGoogleAdsResponse`, então a leitura dos resource names também é provada
contra o proto.

## O caminho autorizado NUNCA é executado

`mutar()` real não é chamado em nenhum teste. Não há costura para injetar um
`mutar` falso, e isso é deliberado: uma função de escrita injetável é um jeito
de alguém achar que escreveu quando não escreveu — e, pior, de o portão da
trava ser contornado por parâmetro. Os testes cobrem as portas ANTES da escrita
e as funções puras DEPOIS dela; o meio, que é `with destravar(): mutar()`, é
justamente o que a trava fechada impede de rodar.

Uso:
    backend/.venv/bin/python -m volc_ads.testes_subir
"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import google.auth.credentials as _credenciais
import pytest
from google.ads.googleads.client import GoogleAdsClient

from . import isencao, subir
from .copy.mock import falha_politica
from .gads import modo
from .gads.errors import (
    ChavePolitica,
    ErroGads,
    FalhaGads,
    Politica,
    TopicoPolitica,
)

CONTA = "8017851692"
MCC = "6016739364"
MOTIVO = "prova offline do caminho de escrita"


class _CredencialFalsa(_credenciais.Credentials):
    """Credencial que não autentica nada — só existe para o cliente instanciar."""

    def refresh(self, request):
        """Método abstrato da classe base. Nunca é chamado: nada aqui autentica."""


def cliente_offline() -> GoogleAdsClient:
    """Cliente que só serve para `get_type()`. Não fala com a rede."""
    return GoogleAdsClient(
        credentials=_CredencialFalsa(), developer_token="TESTE", version="v25"
    )


# ── material de teste ──────────────────────────────────────────────────────


def grafo(c, nome_campanha: str = "FORGE BR 20260818_120000 fgts saque"):
    """Três operações reais, o suficiente para exercitar impressão e nome."""
    ops = []

    o = c.get_type("MutateOperation")
    o.campaign_budget_operation.create.name = "Budget_20260818_120000"
    ops.append(o)

    o = c.get_type("MutateOperation")
    o.campaign_operation.create.name = nome_campanha
    o.campaign_operation.create.advertising_channel_type = (
        c.enums.AdvertisingChannelTypeEnum.SEARCH
    )
    ops.append(o)

    o = c.get_type("MutateOperation")
    o.ad_group_ad_operation.create.ad_group = f"customers/{CONTA}/adGroups/-3"
    ops.append(o)

    return tuple(ops)


def preparo_provado(c, operacoes=None, conta: str = CONTA) -> subir.Preparo:
    """Um `Preparo` com selo, montado como `preparar()` montaria.

    O selo é emitido aqui com a mesma função que `preparar()` usa porque
    `preparar()` de verdade precisa de conta e de `validate_only`. O que os
    testes provam não é a emissão — é a VERIFICAÇÃO: que mexer no grafo depois
    invalida o selo.
    """
    ops = operacoes if operacoes is not None else grafo(c)
    autoridade = subir._autoridade_das_operacoes(ops, canal_esperado="SEARCH")
    return subir.Preparo(
        customer_id=conta,
        login_customer_id=MCC,
        operacoes=ops,
        nome_campanha=subir._nome_campanha(ops),
        selo=subir.Selo(
            customer_id=conta,
            login_customer_id=MCC,
            canal=autoridade.canal,
            tipos_operacoes=autoridade.tipos,
            hashes_operacoes=autoridade.hashes,
            impressao=autoridade.impressao,
            n_operacoes=len(ops),
            carimbo="20260818_120000",
        ),
    )


@pytest.mark.parametrize(
    ("entrada", "canonico"),
    [
        ("PERFORMANCE_MAX", "PERFORMANCE_MAX"),
        ("PMAX", "PERFORMANCE_MAX"),
    ],
)
def test_canal_sem_construtor_falha_antes_de_montar(
    entrada: str,
    canonico: str,
):
    """Inventariar um canal nunca autoriza criá-lo com o builder de outro.

    ⚠️ DISPLAY saiu desta lista quando ganhou construtor real. DEMAND_GEN saiu
    quando ganhou builder de prova/validate_only: continua proibido em
    ``subir()``, e essa fronteira vive em ``testes_demand_gen.py``. O portão
    segue fechado aqui para canais sem nem mesmo um builder provável.
    """
    with pytest.raises(subir.CanalSemConstrutor) as erro:
        subir.preparar(
            CONTA,
            object(),  # não é lido: o portão vem antes do construtor
            login_customer_id=MCC,
            canal=entrada,
        )

    mensagem = str(erro.value)
    assert canonico in mensagem
    assert "disponível para montar/validate_only: DEMAND_GEN, DISPLAY, SEARCH" in mensagem


def test_registry_resolve_search_e_canoniza_a_entrada():
    canal, construtor = subir.resolver_construtor(" search ")

    assert canal == "SEARCH"
    assert construtor is subir.search.construir


class ExcecaoComVeredito(Exception):
    """Encena uma GoogleAdsException: o servidor processou e recusou."""

    def __init__(self) -> None:
        super().__init__("policy violation")
        self.failure = object()  # basta existir: é o sinal que `subir` lê


class ExcecaoSemVeredito(Exception):
    """Encena a conexão que caiu: nenhum GoogleAdsFailure chegou de volta."""


def falha_achado(topico: str = "GOVERNMENT_DOCUMENTS_AND_OFFICIAL_SERVICES",
                 tipo: str = "LIMITED",
                 caminho_alvo: str = "ad_group_ad_operation",
                 indice: int = 40) -> FalhaGads:
    """`policy_finding_error` — o outro formato, o que NÃO tem chave."""
    return FalhaGads(
        erros=(
            ErroGads(
                campo_codigo="policy_finding_error",
                valor_codigo="POLICY_FINDING",
                mensagem="The ad was found to violate a policy topic.",
                caminho_campo=f"mutate_operations[{indice}].{caminho_alvo}.create.ad",
                indice_operacao=indice,
                politica=Politica(
                    formato="achado",
                    topicos=(
                        TopicoPolitica(topico=topico, tipo=tipo,
                                       evidencias=("Baixe seu Novo RG",)),
                    ),
                ),
            ),
        ),
        request_id="prova-achado",
    )


def falha_violacao_criterio(indice: int = 20) -> FalhaGads:
    """Violação numa KEYWORD — outro alvo, outro caminho de campo."""
    return FalhaGads(
        erros=(
            ErroGads(
                campo_codigo="policy_violation_error",
                valor_codigo="POLICY_ERROR",
                mensagem="Keyword violates policy.",
                caminho_campo=(
                    f"mutate_operations[{indice}].ad_group_criterion_operation"
                    ".create.keyword.text"
                ),
                indice_operacao=indice,
                politica=Politica(
                    formato="violacao",
                    nome_externo="Trademarks",
                    isentavel=True,
                    chave=ChavePolitica(policy_name="TRADEMARK",
                                        violating_text="nubank"),
                ),
            ),
        ),
        request_id="prova-criterio",
    )


# ── casos: as portas antes da escrita ──────────────────────────────────────


def caso_trava_fechada(c) -> tuple[bool, str]:
    """Com a trava fechada, subir() para no `destravar()` e nada sai da máquina."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            subir.subir(preparo_provado(c), motivo=MOTIVO, pasta_recibos=tmp)
        except modo.EscritaBloqueada as exc:
            msg = str(exc)
            recibos = list(Path(tmp).glob("*.json"))
            ok = "FORGE_PERMITIR_ESCRITA" in msg and not recibos
            return ok, (
                f"EscritaBloqueada levantada · recibos gravados: {len(recibos)}\n"
                + "\n".join(f"        │ {ln}" for ln in msg.splitlines())
            )
        return False, "NÃO levantou EscritaBloqueada — a trava não segurou"


def caso_trava_ambiente(c) -> tuple[bool, str]:
    """Trava já aberta por outro frame: subir() recusa em vez de aproveitar.

    A abertura é simulada mexendo no global de `modo` em vez de definir
    FORGE_PERMITIR_ESCRITA, e isso não é atalho de teste — definir a variável
    armaria o caminho de escrita real dentro de uma suíte. Como a variável
    continua ausente, mesmo se esta porta falhasse o `destravar()` seguraria.
    """
    anterior = modo._destravado_no_codigo
    modo._destravado_no_codigo = True
    try:
        subir.subir(preparo_provado(c), motivo=MOTIVO)
        return False, "NÃO levantou TravaAberta"
    except subir.TravaAberta as exc:
        return True, str(exc).splitlines()[0]
    except modo.EscritaBloqueada:
        return False, "parou só no destravar() — a porta da trava ambiente não existe"
    finally:
        modo._destravado_no_codigo = anterior


def caso_sem_selo(c) -> tuple[bool, str]:
    """Payload que nunca passou por validate_only não sobe."""
    preparo = dataclasses.replace(
        preparo_provado(c), selo=None, recusa_local="15 headlines, 1 duplicata"
    )
    try:
        subir.subir(preparo, motivo=MOTIVO)
        return False, "NÃO levantou PayloadNaoValidado"
    except subir.PayloadNaoValidado as exc:
        return "validate_only" in str(exc), str(exc).splitlines()[0]
    except modo.EscritaBloqueada:
        return False, "a trava respondeu antes do selo — a ordem das portas está trocada"


def caso_selo_desatualizado(c) -> tuple[bool, str]:
    """Grafo alterado DEPOIS da prova: o selo pega.

    ⚠️ `Preparo` é frozen, e isso não protege nada aqui: a tupla guarda protos
    mutáveis, então `preparo.operacoes[2].…append(…)` altera o que seria
    enviado sem tocar no dataclass. É a razão de o selo carregar impressão
    digital e não um booleano `validado=True`.
    """
    preparo = preparo_provado(c)
    antes = preparo.selo.impressao
    preparo.operacoes[2].ad_group_ad_operation.create.ad.final_urls.append(
        "https://exemplo.invalido/pagina-trocada"
    )
    depois = subir._impressao(preparo.operacoes)
    try:
        subir.subir(preparo, motivo=MOTIVO)
        return False, "NÃO levantou PayloadNaoValidado"
    except subir.PayloadNaoValidado as exc:
        ok = "hash individual" in str(exc) and antes != depois
        return ok, f"{antes[:12]} → {depois[:12]} · {str(exc).splitlines()[0]}"


def caso_selo_de_outra_conta(c) -> tuple[bool, str]:
    """Selo provado na conta A não autoriza escrita na conta B."""
    preparo = preparo_provado(c)
    trocado = dataclasses.replace(preparo, customer_id="1111111111")
    try:
        subir.subir(trocado, motivo=MOTIVO)
        return False, "NÃO levantou PayloadNaoValidado"
    except subir.PayloadNaoValidado as exc:
        return "não autoriza escrita em outra" in str(exc), str(exc).splitlines()[0]


def caso_motivo_vazio(c) -> tuple[bool, str]:
    """Sem motivo declarado não há recibo legível daqui a um mês."""
    try:
        subir.subir(preparo_provado(c), motivo="subir")
        return False, "aceitou motivo de 5 caracteres"
    except ValueError as exc:
        return "motivo descritivo" in str(exc), str(exc).splitlines()[0]


# ── casos: o que o recibo tem de saber dizer ───────────────────────────────


def caso_resource_names(c) -> tuple[bool, str]:
    """Os resource names devolvidos pelo mutate são colhidos e tipados."""
    resposta = c.get_type("MutateGoogleAdsResponse")
    esperado = [
        ("campaign_budget_result", f"customers/{CONTA}/campaignBudgets/111"),
        ("campaign_result", f"customers/{CONTA}/campaigns/222"),
        ("ad_group_result", f"customers/{CONTA}/adGroups/333"),
        ("ad_group_ad_result", f"customers/{CONTA}/adGroupAds/333~444"),
    ]
    for campo, rn in esperado:
        item = c.get_type("MutateOperationResponse")
        getattr(item, campo).resource_name = rn
        resposta.mutate_operation_responses.append(item)

    criados = subir._colher_criados(resposta)
    ok = [(x.tipo, x.resource_name) for x in criados] == esperado
    campanha = next((x.resource_name for x in criados
                     if x.tipo == "campaign_result"), "")
    return ok, f"{len(criados)} recursos · campanha = {campanha}"


def caso_recusado_vs_indeterminado(c) -> tuple[bool, str]:
    """As duas metades do 'tudo ou nada' — e o terceiro caso, que é 'não sei'."""
    est_r, exp_r = subir._estado_da_conta(ExcecaoComVeredito())
    est_i, exp_i = subir._estado_da_conta(ExcecaoSemVeredito())
    est_n, _ = subir._estado_da_conta(None)

    base = subir.Recibo(
        estado=subir.TENTANDO, carimbo="20260818_120000", customer_id=CONTA,
        login_customer_id=MCC, nome_campanha="FORGE BR", n_operacoes=3,
        impressao="a" * 64, motivo=MOTIVO,
    )
    falha = falha_politica("Antecipe Seu FGTS Hoje")
    recusado = subir._com_falha(base, falha, bruta=ExcecaoComVeredito())
    indeterminado = subir._com_falha(base, falha, bruta=None)

    ok = (
        est_r == subir.RECUSADO
        and est_i == subir.INDETERMINADO
        and est_n == subir.INDETERMINADO
        and recusado.nada_foi_criado is True
        and indeterminado.nada_foi_criado is None
        and "NADA foi criado" in exp_r
        and "CONFIRA A CONTA" in exp_i
    )
    return ok, (
        f"com veredito → {est_r} (nada_foi_criado={recusado.nada_foi_criado}) · "
        f"sem veredito → {est_i} (nada_foi_criado={indeterminado.nada_foi_criado})"
    )


def caso_gravacao_em_duas_fases(c) -> tuple[bool, str]:
    """O pré-recibo sai antes da chamada e o veredito sobrescreve o MESMO arquivo.

    É a recuperação de um processo morto no meio: se o segundo `_gravar` nunca
    acontecer, o que fica no disco é um recibo em TENTANDO — a única pista de
    que alguma coisa saiu daqui e nunca foi confirmada.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp)
        tentando = subir.Recibo(
            estado=subir.TENTANDO, carimbo="20260818_120000", customer_id=CONTA,
            login_customer_id=MCC, nome_campanha="FORGE BR 20260818_120000 fgts",
            n_operacoes=72, impressao="d" * 64, motivo=MOTIVO,
            explicacao="requisição enviada; veredito ainda não recebido",
        )
        subir._gravar(tentando, pasta)
        so_o_pre = json.loads(
            (pasta / tentando.arquivo).read_text(encoding="utf-8")
        )

        final = subir._com_falha(tentando, falha_politica("Antecipe Seu FGTS Hoje"),
                                 bruta=ExcecaoComVeredito())
        subir._gravar(final, pasta)
        arquivos = sorted(p.name for p in pasta.glob("*.json"))
        lido = json.loads((pasta / final.arquivo).read_text(encoding="utf-8"))

    ok = (
        so_o_pre["estado"] == subir.TENTANDO
        and so_o_pre["nada_foi_criado"] is None      # em TENTANDO ninguém sabe
        and len(arquivos) == 1                        # sobrescreveu, não duplicou
        and lido["estado"] == subir.RECUSADO
        and lido["nada_foi_criado"] is True
        and lido["falha"]["erros"][0]["politica"]["chave"]["violating_text"]
        == "Antecipe Seu FGTS Hoje"
    )
    return ok, (f"1ª gravação = {so_o_pre['estado']} · 2ª = {lido['estado']} · "
                f"arquivos no disco: {arquivos}")


def caso_uma_tentativa_so(c) -> tuple[bool, str]:
    """`SEM_RETENTATIVA` mesmo: falha de transporte NÃO é repetida.

    Um create não é idempotente. Se `client.executar()` retentasse um
    DEADLINE_EXCEEDED que chegou depois de o servidor aplicar o mutate, a
    segunda tentativa criaria a campanha inteira de novo.

    Este caso mede também o defeito citado em `subir.py`: `ErroEsgotado` sai
    SEM `__cause__`, porque `client.executar()` levanta sem `from exc`. É por
    isso que o caminho esgotado não consegue distinguir "a API recusou" de "a
    resposta nunca voltou" e cai em INDETERMINADO.
    """
    from .gads.client import ErroEsgotado, executar

    class _Indisponivel(Exception):
        """gRPC UNAVAILABLE — o que `classificar()` lê como TRANSIENT."""

        def code(self):
            return type("Codigo", (), {"name": "UNAVAILABLE"})()

    chamadas = []

    def _falha():
        chamadas.append(1)
        raise _Indisponivel("servidor sumiu no meio")

    try:
        executar(_falha, politica=subir.SEM_RETENTATIVA, rotulo="prova")
        return False, "não levantou — a política de retry não foi respeitada"
    except ErroEsgotado as exc:
        ok = (
            len(chamadas) == 1
            and exc.tentativas == 1
            and exc.__cause__ is None       # o defeito, medido e não suposto
            and exc.falha.retentavel
        )
        estado, _ = subir._estado_da_conta(exc.__cause__)
        ok = ok and estado == subir.INDETERMINADO
        return ok, (f"{len(chamadas)} chamada(s) · __cause__={exc.__cause__} · "
                    f"veredito de conta: {estado}")


def caso_recibo_serializa(c) -> tuple[bool, str]:
    """O recibo com falha de política dentro tem de virar JSON — é o relatório."""
    resposta = c.get_type("MutateGoogleAdsResponse")
    item = c.get_type("MutateOperationResponse")
    item.campaign_result.resource_name = f"customers/{CONTA}/campaigns/222"
    resposta.mutate_operation_responses.append(item)

    base = subir.Recibo(
        estado=subir.TENTANDO, carimbo="20260818_120000", customer_id=CONTA,
        login_customer_id=MCC, nome_campanha="FORGE BR 20260818_120000 fgts",
        n_operacoes=3, impressao="b" * 64, motivo=MOTIVO,
    )
    aceito = subir._com_sucesso(base, resposta)
    recusado = subir._com_falha(base, falha_politica("Antecipe Seu FGTS Hoje"),
                                bruta=ExcecaoComVeredito())

    texto_a = json.dumps(aceito.para_json(), ensure_ascii=False)
    texto_r = json.dumps(recusado.para_json(), ensure_ascii=False)
    ok = (
        aceito.estado == subir.ACEITO
        and aceito.recurso("campaign_result").endswith("/campaigns/222")
        and aceito.nada_foi_criado is False
        and "PAUSED" in aceito.explicacao
        and "Antecipe Seu FGTS Hoje" in texto_r
        and "exempt" not in texto_a  # o recibo não pede isenção por conta própria
        and aceito.arquivo.startswith("20260818_120000_" + CONTA)
    )
    return ok, f"aceito={len(texto_a)}B recusado={len(texto_r)}B · {aceito.arquivo}"


def caso_nome_da_campanha(c) -> tuple[bool, str]:
    """O nome sai do payload, não de um carimbo re-derivado."""
    nome = "FORGE BR 20260818_120000 fgts saque"
    lido = subir._nome_campanha(grafo(c, nome))
    vazio = subir._nome_campanha(())
    return lido == nome and vazio == "", f"{lido!r}"


# ── casos: o remédio certo para cada formato de erro ───────────────────────


def caso_remedio_violacao_anuncio(c) -> tuple[bool, str]:
    """policy_violation_error num anúncio → exempt_policy_violation_keys.

    E o campo fica DENTRO de `policy_validation_parameter`, que é a parte que o
    cabeçalho de `errors.py` não detalha.
    """
    plano = isencao.montar(falha_politica("Antecipe Seu FGTS Hoje"))
    if len(plano.pedidos) != 1:
        return False, f"esperava 1 pedido, veio {len(plano.pedidos)}"
    pedido = plano.pedidos[0]

    op = c.get_type("MutateOperation")
    op.ad_group_ad_operation.create.ad_group = f"customers/{CONTA}/adGroups/-3"
    isencao.aplicar(c, op, pedido)

    param = op.ad_group_ad_operation.policy_validation_parameter
    chaves = list(param.exempt_policy_violation_keys)
    ok = (
        pedido.caminho
        == "ad_group_ad_operation.policy_validation_parameter"
           ".exempt_policy_violation_keys"
        and len(chaves) == 1
        and chaves[0].violating_text == "Antecipe Seu FGTS Hoje"
        and chaves[0].policy_name == "FINANCIAL_SERVICES"
        # o remédio do OUTRO formato não pode ter sido tocado: o proto exige
        # que ele fique vazio, e populá-lo junto faz a API recusar
        and len(param.ignorable_policy_topics) == 0
    )
    return ok, f"{pedido.caminho} ← {chaves[0].policy_name}/{chaves[0].violating_text!r}"


def caso_remedio_achado_anuncio(c) -> tuple[bool, str]:
    """policy_finding_error → ignorable_policy_topics, e nenhuma chave."""
    plano = isencao.montar(falha_achado())
    if len(plano.pedidos) != 1:
        return False, f"esperava 1 pedido, veio {len(plano.pedidos)}"
    pedido = plano.pedidos[0]

    op = c.get_type("MutateOperation")
    op.ad_group_ad_operation.create.ad_group = f"customers/{CONTA}/adGroups/-3"
    isencao.aplicar(c, op, pedido)

    param = op.ad_group_ad_operation.policy_validation_parameter
    topicos = list(param.ignorable_policy_topics)
    ok = (
        pedido.caminho
        == "ad_group_ad_operation.policy_validation_parameter"
           ".ignorable_policy_topics"
        and topicos == ["GOVERNMENT_DOCUMENTS_AND_OFFICIAL_SERVICES"]
        and len(param.exempt_policy_violation_keys) == 0
    )
    return ok, f"{pedido.caminho} ← {topicos}"


def caso_remedio_violacao_keyword(c) -> tuple[bool, str]:
    """Na keyword o campo é DIRETO na operação — sem policy_validation_parameter."""
    plano = isencao.montar(falha_violacao_criterio())
    if len(plano.pedidos) != 1:
        return False, f"esperava 1 pedido, veio {len(plano.pedidos)}"
    pedido = plano.pedidos[0]

    op = c.get_type("MutateOperation")
    op.ad_group_criterion_operation.create.ad_group = f"customers/{CONTA}/adGroups/-3"
    isencao.aplicar(c, op, pedido)

    chaves = list(op.ad_group_criterion_operation.exempt_policy_violation_keys)
    ok = (
        pedido.caminho == "ad_group_criterion_operation.exempt_policy_violation_keys"
        and "policy_validation_parameter" not in pedido.caminho
        and len(chaves) == 1
        and chaves[0].violating_text == "nubank"
    )
    return ok, f"{pedido.caminho} ← {chaves[0].policy_name}/{chaves[0].violating_text!r}"


def caso_achado_em_keyword_sem_remedio(c) -> tuple[bool, str]:
    """`AdGroupCriterionOperation` não tem ignorable_policy_topics na v25."""
    plano = isencao.montar(
        falha_achado(caminho_alvo="ad_group_criterion_operation", indice=21)
    )
    sem_campo = not hasattr(
        c.get_type("MutateOperation").ad_group_criterion_operation,
        "ignorable_policy_topics",
    )
    ok = (
        not plano.acionavel
        and len(plano.recusas) == 1
        and "sem campo de remédio" in plano.recusas[0].motivo
        and sem_campo
    )
    return ok, f"proto confirma ausência do campo: {sem_campo} · {plano.recusas[0]}"


def caso_violacao_nao_isentavel(c) -> tuple[bool, str]:
    """is_exemptible=False: pedir isenção é requisição rejeitada, não anúncio salvo."""
    plano = isencao.montar(falha_politica("Baixe seu Novo RG", isentavel=False))
    ok = (
        not plano.acionavel
        and len(plano.recusas) == 1
        and "não isentável" in plano.recusas[0].motivo
    )
    return ok, str(plano.recusas[0])


def caso_topico_proibido(c) -> tuple[bool, str]:
    """PROHIBITED não vira publicável por ser ignorado."""
    plano = isencao.montar(falha_achado(topico="DANGEROUS_PRODUCTS", tipo="PROHIBITED"))
    ok = (
        not plano.acionavel
        and len(plano.recusas) == 1
        and "nenhum tópico ignorável" in plano.recusas[0].motivo
    )
    return ok, str(plano.recusas[0])


def caso_remedios_conflitantes(c) -> tuple[bool, str]:
    """Violação E achado na mesma operação: o proto proíbe os dois juntos."""
    v = falha_politica("Antecipe Seu FGTS Hoje", indice_operacao=40)
    a = falha_achado(indice=40)
    plano = isencao.montar(FalhaGads(erros=v.erros + a.erros, request_id="misto"))
    ok = (
        not plano.acionavel
        and any("mutuamente exclusivos" in r.motivo for r in plano.recusas)
    )
    return ok, str(plano.recusas[0])


def caso_alvo_trocado(c) -> tuple[bool, str]:
    """Pedido de anúncio numa operação de critério apagaria a operação.

    Medido no proto da v25: escrever numa sub-operação diferente troca o oneof
    e zera a anterior, sem erro nenhum.
    """
    plano = isencao.montar(falha_politica("Antecipe Seu FGTS Hoje"))
    op = c.get_type("MutateOperation")
    op.ad_group_criterion_operation.create.ad_group = f"customers/{CONTA}/adGroups/-3"
    try:
        isencao.aplicar(c, op, plano.pedidos[0])
        return False, "aceitou aplicar pedido de anúncio em operação de critério"
    except isencao.AlvoTrocado as exc:
        intacta = (
            op.ad_group_criterion_operation.create.ad_group
            == f"customers/{CONTA}/adGroups/-3"
        )
        return intacta, f"{str(exc).splitlines()[0]} · operação intacta: {intacta}"


def caso_recibo_alimenta_isencao(c) -> tuple[bool, str]:
    """O recibo de um RECUSADO carrega tudo o que `isencao.montar()` precisa.

    É o elo entre os dois módulos, e ele é de DADO, não de chamada: o recibo
    guarda a `FalhaGads` inteira e alguém, depois, decide levá-la à isenção.
    """
    base = subir.Recibo(
        estado=subir.TENTANDO, carimbo="20260818_120000", customer_id=CONTA,
        login_customer_id=MCC, nome_campanha="FORGE BR", n_operacoes=72,
        impressao="c" * 64, motivo=MOTIVO,
    )
    recibo = subir._com_falha(base, falha_politica("Antecipe Seu FGTS Hoje"),
                              bruta=ExcecaoComVeredito())
    plano = isencao.montar(recibo.falha)
    ok = (
        recibo.estado == subir.RECUSADO
        and plano.acionavel
        and plano.pedidos[0].chaves[0].violating_text == "Antecipe Seu FGTS Hoje"
        and isencao.SIGNIFICADO in plano.relatorio()
        and "DECISÃO HUMANA" in plano.relatorio()
    )
    return ok, plano.relatorio().splitlines()[0] + " · relatório diz o que significa"


def caso_nada_pede_sozinho(c) -> tuple[bool, str]:
    """`subir.py` não importa `isencao`: pedir isenção nunca é efeito colateral.

    A checagem é sobre IMPORT e sobre os campos de isenção — citar `isencao.py`
    numa docstring é o contrário do problema, é o aviso de onde a decisão mora.
    """
    fonte = (Path(__file__).resolve().parent / "subir.py").read_text(encoding="utf-8")
    importa = [
        ln for ln in fonte.splitlines()
        if ln.lstrip().startswith(("import ", "from ")) and "isencao" in ln
    ]
    campos = [campo for campo in ("exempt_policy", "ignorable_policy")
              if campo in fonte]
    ok = not importa and not campos
    return ok, (f"imports de isencao: {len(importa)} · "
                f"campos de isenção citados: {campos or 'nenhum'}")



def _linhagem_de_prova():
    """Duas linhagens completas, com instante FIXO. Nenhum relógio real."""
    from volc_ads.campanha.brief import Linhagem
    return (
        Linhagem(
            nome="banner", papel="marketing", identidade="cri_aaa111",
            conteudo_hash="sha256:" + "a" * 64, motor="openai:gpt-image-2",
            versao_do_motor="2026-08", insumo="banner de FGTS, tom sóbrio",
            insumo_hash="f0f0f0f0f0f0f0f0", pedido="ped-001",
            quando="2026-08-27T15:30:00+00:00", origem="gerado",
            mime="image/png", largura=1200, altura=628, bytes_totais=48120,
            custo_usd=0.04,
            exigencia_fonte="matriz-api/display.md §3",
            exigencia_provisoria=False,
        ),
        Linhagem.desconhecida("quadrado-a-mao", "marketing_quadrada"),
    )


def caso_linhagem_no_pre_recibo(c) -> tuple[bool, str]:
    """A procedência está EM DISCO antes de a requisição partir.

    É no pré-recibo que ela vale mais. Se a chamada morrer sem veredito, o
    estado é INDETERMINADO e alguém vai ter de conferir a conta à mão; nesse
    momento o arquivo já sabe quais bytes, com qual hash e de qual insumo
    saíram daqui. Sem isso, conferir seria comparar imagens a olho.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp)
        tentando = subir.Recibo(
            estado=subir.TENTANDO, carimbo="20260827_153000", customer_id=CONTA,
            login_customer_id=MCC, nome_campanha="FORGE BR 20260827 display",
            n_operacoes=8, impressao="e" * 64, motivo=MOTIVO,
            linhagem=_linhagem_de_prova(),
        )
        subir._gravar(tentando, pasta)
        pre = json.loads((pasta / tentando.arquivo).read_text(encoding="utf-8"))

        # E sobrevive ao veredito, seja ele qual for.
        final = subir._com_falha(tentando, falha_politica("Antecipe"),
                                 bruta=ExcecaoComVeredito())
        subir._gravar(final, pasta)
        depois = json.loads((pasta / final.arquivo).read_text(encoding="utf-8"))

    ln = pre["linhagem"]
    ok = (
        pre["estado"] == subir.TENTANDO
        and len(ln) == 2
        # ORDEM preservada — lista, não conjunto.
        and [x["papel"] for x in ln] == ["marketing", "marketing_quadrada"]
        and ln[0]["conteudo_hash"].startswith("sha256:")
        and ln[0]["motor"] == "openai:gpt-image-2"
        and ln[0]["insumo"] == "banner de FGTS, tom sóbrio"
        and ln[0]["quando"] == "2026-08-27T15:30:00+00:00"
        and (ln[0]["largura"], ln[0]["altura"]) == (1200, 628)
        and ln[0]["custo_usd"] == 0.04
        and ln[0]["confirmada"] is True
        # A montada à mão NÃO se diz confirmada, e o desconhecido é null.
        and ln[1]["confirmada"] is False
        and ln[1]["motor"] is None
        and ln[1]["custo_usd"] is None
        and ln[1]["largura"] is None
        and len(depois["linhagem"]) == 2      # o veredito não apaga o rastro
        and depois["estado"] == subir.RECUSADO
    )
    return ok, (f"pré-recibo com {len(ln)} linhagens · "
                f"confirmadas: {sum(1 for x in ln if x['confirmada'])}/2 · "
                f"sobreviveu ao veredito: {len(depois['linhagem'])}")


def caso_linhagem_serializa_sem_default(c) -> tuple[bool, str]:
    """`json.dumps` SEM `default=` — como `_gravar` de fato chama.

    Este caso existe por um motivo concreto: a primeira gravação do recibo
    acontece DENTRO do `with modo.destravar(...)`. Um `datetime` cru na
    linhagem estouraria `TypeError` ali, com a trava ABERTA e a requisição
    prestes a sair. Por isso `Linhagem.quando` é `str` ISO e há guarda de tipo
    no `__post_init__` — este caso prova que a guarda basta.
    """
    from volc_ads.campanha.brief import Linhagem
    base = subir.Recibo(
        estado=subir.TENTANDO, carimbo="20260827_153000", customer_id=CONTA,
        login_customer_id=MCC, nome_campanha="FORGE BR 20260827 display",
        n_operacoes=8, impressao="f" * 64, motivo=MOTIVO,
        linhagem=_linhagem_de_prova(),
    )
    # Exatamente a chamada de `_gravar`: sem `default=`, sem fallback.
    texto = json.dumps(base.para_json(), ensure_ascii=False, indent=2)
    relido = json.loads(texto)

    # E a guarda que impede o caso perigoso de sequer ser construído.
    recusou_datetime = False
    try:
        Linhagem(nome="x", papel="marketing", quando=datetime(2026, 8, 27))
    except TypeError:
        recusou_datetime = True

    ok = (
        "openai:gpt-image-2" in texto
        and relido["linhagem"][0]["confirmada"] is True
        and relido["linhagem"][1]["confirmada"] is False
        and recusou_datetime
    )
    return ok, (f"{len(texto)}B sem `default=` · guarda de datetime: "
                f"{'ativa' if recusou_datetime else 'AUSENTE'}")


CASOS = [
    ("trava fechada", caso_trava_fechada),
    ("trava já aberta", caso_trava_ambiente),
    ("payload sem selo", caso_sem_selo),
    ("selo desatualizado", caso_selo_desatualizado),
    ("selo de outra conta", caso_selo_de_outra_conta),
    ("motivo insuficiente", caso_motivo_vazio),
    ("resource names", caso_resource_names),
    ("recusado × indeterminado", caso_recusado_vs_indeterminado),
    ("gravação em duas fases", caso_gravacao_em_duas_fases),
    ("uma tentativa só", caso_uma_tentativa_so),
    ("recibo serializa", caso_recibo_serializa),
    ("nome vem do payload", caso_nome_da_campanha),
    ("violação → chaves", caso_remedio_violacao_anuncio),
    ("achado → tópicos", caso_remedio_achado_anuncio),
    ("violação em keyword", caso_remedio_violacao_keyword),
    ("achado em keyword", caso_achado_em_keyword_sem_remedio),
    ("violação não isentável", caso_violacao_nao_isentavel),
    ("tópico PROHIBITED", caso_topico_proibido),
    ("remédios conflitantes", caso_remedios_conflitantes),
    ("alvo trocado", caso_alvo_trocado),
    ("recibo → isenção", caso_recibo_alimenta_isencao),
    ("nada pede sozinho", caso_nada_pede_sozinho),
    ("linhagem no pré-recibo", caso_linhagem_no_pre_recibo),
    ("linhagem serializa", caso_linhagem_serializa_sem_default),
]


def main() -> int:
    # Porta do próprio teste. Com a variável ligada, um caso que hoje para no
    # `destravar()` passaria a escrever de verdade numa conta real. Não existe
    # flag para seguir mesmo assim.
    if os.environ.get("FORGE_PERMITIR_ESCRITA") == "1":
        print("RECUSADO: FORGE_PERMITIR_ESCRITA=1 no ambiente. Estes testes "
              "exercitam o caminho de escrita e só são seguros com a trava "
              "fechada. Nada foi executado.")
        return 2

    c = cliente_offline()
    print("═" * 78)
    print("SUBIR + ISENÇÃO CONTRA OS PROTOS DA v25 — nenhuma chamada de rede")
    print(f"trava de escrita: {'ABERTA' if modo.escrita_permitida() else 'fechada'}"
          f" · estado: {modo.estado()}")
    print("═" * 78)

    resultados = []
    for nome, fabrica in CASOS:
        try:
            ok, detalhe = fabrica(c)
        except Exception as exc:  # noqa: BLE001 — um caso quebrado é uma falha
            ok, detalhe = False, f"exceção inesperada: {type(exc).__name__}: {exc}"
        resultados.append((nome, ok))
        print(f"\n{'✅' if ok else '❌'} {nome}")
        for linha in str(detalhe).splitlines():
            print(f"      {linha}")

    passaram = sum(1 for _, ok in resultados if ok)
    print("\n" + "═" * 78)
    print(f"{passaram}/{len(resultados)} casos passaram")
    reprovados = [n for n, ok in resultados if not ok]
    if reprovados:
        print("reprovados: " + ", ".join(reprovados))
    print(f"trava ao final: {'ABERTA' if modo.escrita_permitida() else 'fechada'}")
    print("═" * 78)
    return 0 if not reprovados else 1


if __name__ == "__main__":
    raise SystemExit(main())
