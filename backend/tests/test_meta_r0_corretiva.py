"""Regressões da rodada corretiva R0 — A02, A03, A05 e A06.

## O que estas provas são, e o que elas NÃO são

A revisão independente entregou quatro sondas de OBSERVAÇÃO: elas passavam
quando reproduziam o defeito. São úteis para adjudicar, e inúteis como aceite —
uma sonda que passa ao ver o bug volta a passar no dia em que o bug volta, e
some do radar quando ele é corrigido.

Cada teste aqui exige o comportamento CORRETO. Todos falham no HEAD revisado
(`187c4f1`) e passam depois da correção, e nenhum é cópia do monkeypatch global
das sondas — em particular o de expiração, que trocava `contrato.datetime` e
media verde um caminho que nunca consultava aquele relógio.

## Autoridade

Hermético do começo ao fim: ledger em memória, transporte Graph substituído,
Keychain substituído, zero socket. Nenhuma conta real, nenhum Supabase oficial,
nenhuma migration aplicada em banco nenhum por este arquivo.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

import test_meta_criacao_pausada_rotas as h
from app.trafego.meta_execucao import contrato as contrato_meta


@pytest.fixture(autouse=True)
def _cenario_limpo():
    h.CENARIO.reiniciar()
    yield
    h.CENARIO.reiniciar()


def _abrir_bancada(monkeypatch, ledger=None, plano=None):
    """Aprovação viva, ledger em memória e transporte falso. Nada real."""
    ledger = ledger if ledger is not None else h._LedgerEmMemoria()
    h._abrir(monkeypatch, ledger)
    cliente = h._cliente()
    resposta = asyncio.run(
        h._aprovar(cliente, ledger, plano or h._plano_para_envio()))
    assert resposta.status_code == 200, resposta.text
    return ledger, cliente, resposta.json()["aprovacao"]


def _criar(cliente, aprovacao):
    return cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
        "approval_id": aprovacao["approval_id"],
        "plano_sha256_esperado": aprovacao["plano_sha256"],
    })


def _reconciliar(cliente, approval_id):
    return cliente.post(
        "/api/trafego/meta/local/criacao/reconciliar",
        json={"approval_id": approval_id})


def _relogio_em(monkeypatch, instante: datetime) -> None:
    """Adianta o relógio DO DESPACHO, que é o único que julga validade.

    ⚠️ Substitui `contrato.agora_utc`, a FUNÇÃO que o caminho de criação
    realmente chama — não a classe `datetime` de um módulo. A sonda da revisão
    trocou a classe e passou sem que o relógio falso fosse consultado uma única
    vez; um teste montado assim mede a própria fixture, não o produto.
    """
    monkeypatch.setattr(contrato_meta, "agora_utc", lambda: instante)


# ---------------------------------------------------------------------------
# R0-A02 · read-back que não fica gravado nunca vira sucesso certificado
# ---------------------------------------------------------------------------

class _LedgerSemGravarEvidencia(h._LedgerEmMemoria):
    """O livro aceita tudo, menos registrar o que a leitura conferiu."""

    async def registrar_readback(self, **kwargs: Any) -> None:
        raise h.ErroDeNascimentoMeta(
            "META_CREATE_LEDGER_UNAVAILABLE", "armazenamento sintetico indisponivel")


def test_falha_ao_gravar_confirmacao_para_a_saga_e_recusa_o_sucesso(monkeypatch) -> None:
    """Sem confirmação durável, nenhum objeto dependente nasce.

    Antes: as quatro gravações falhavam, os quatro objetos nasciam e a resposta
    era 200 CREATED_PAUSED com ZERO read-back durável. A confirmação existia só
    no corpo HTTP — quer dizer, só no navegador.
    """
    ledger, cliente, aprovacao = _abrir_bancada(
        monkeypatch, _LedgerSemGravarEvidencia())
    resposta = _criar(cliente, aprovacao)

    assert resposta.status_code == 502, resposta.text
    corpo = resposta.json()["detail"]
    assert corpo["codigo"] == "META_READBACK_NOT_DURABLE"
    assert corpo["retry_permitido"] is False
    # ⚠️ O fato mais importante da correção: a saga PAROU no primeiro degrau.
    # Criar o conjunto sobre uma campanha cuja leitura só existe nesta resposta
    # seria pendurar objeto real em prova volátil.
    assert h.CENARIO.criados == ["campaign"]
    # O ID CONTINUA GRAVADO — é assim que o passo permanece recuperável.
    assert ledger.passos["passo-campaign"]["state"] == "CREATED"
    assert ledger.passos["passo-campaign"]["id_externo"] == h.IDS_CRIADOS["campaign"]
    # E o incidente declara que o livro ficou atrás do mundo.
    assert corpo["evidencia_duravel"] is False
    # Falha NOSSA não vira recusa PROVADA da Meta: nada foi marcado FAILED, o
    # que manteria alguém autorizado a reenviar por cima de um objeto que existe.
    assert ("falhar", "passo-campaign") not in ledger.eventos


def test_o_recibo_do_incidente_acompanha_a_resposta_de_falha(monkeypatch) -> None:
    """A tela leu o recibo ANTES do despacho; o 502 traz o estado de DEPOIS."""
    _, cliente, aprovacao = _abrir_bancada(monkeypatch, _LedgerSemGravarEvidencia())
    corpo = _criar(cliente, aprovacao).json()["detail"]
    recibo = corpo["recibo"]
    assert recibo["operations_expected"] == 4
    assert [passo["name"] for passo in recibo["steps"]] == ["campaign"]
    assert recibo["steps"][0]["state"] == "CREATED"
    assert recibo["steps"][0]["readback_confirmed"] is False


def test_ledger_que_nao_sabe_gravar_readback_recusa_antes_do_primeiro_post(
    monkeypatch,
) -> None:
    """Ausência de suporte no livro não pode virar aceite silencioso.

    Havia um caminho legado que seguia em silêncio quando o ledger não tinha o
    método. Silêncio não é compatibilidade: agora a recusa acontece antes de
    qualquer efeito externo.
    """
    class SemReadback(h._LedgerEmMemoria):
        registrar_readback = None

    _, cliente, aprovacao = _abrir_bancada(monkeypatch, SemReadback())
    # A aprovação já exercitou `validate_only`; o que precisa ficar em zero é o
    # que sai DAQUI para a frente.
    antes = len(h.CENARIO.posts)
    resposta = _criar(cliente, aprovacao)

    assert resposta.status_code == 409, resposta.text
    assert resposta.json()["detail"]["codigo"] == "META_READBACK_LEDGER_UNAVAILABLE"
    assert h.CENARIO.criados == []
    assert len(h.CENARIO.posts) == antes


def test_divergencia_sobrevive_a_falha_de_anotar_a_evidencia(monkeypatch) -> None:
    """O objeto existe e NÃO é o aprovado — e esse fato não é apagado.

    Trocar o código por META_READBACK_NOT_DURABLE apagaria o fato mais grave dos
    dois. O que cai é a DURABILIDADE, e ela é declarada em campo próprio.
    """
    h.CENARIO.divergir_em = "campaign"
    _, cliente, aprovacao = _abrir_bancada(monkeypatch, _LedgerSemGravarEvidencia())
    resposta = _criar(cliente, aprovacao)

    assert resposta.status_code == 502, resposta.text
    corpo = resposta.json()["detail"]
    assert corpo["codigo"] == "META_READBACK_DIVERGENT"
    assert corpo["evidencia_duravel"] is False
    assert h.CENARIO.criados == ["campaign"]


# ---------------------------------------------------------------------------
# R0-A03 · ID registrado não é read-back confirmado
# ---------------------------------------------------------------------------

#: O manifesto real nomeia os passos por CHAVE (`creative:variation-001`), e
#: `IDS_CRIADOS` guarda os ids por TIPO. Confundir os dois faria a fixture
#: montar um passo com id de outro objeto.
def _id_do_passo(nome: str) -> str:
    return h.IDS_CRIADOS[nome.split(":", 1)[0]]


def _passo_criado_sem_conferir(ledger, aprovacao, nome="campaign", ordinal=1):
    """O estado exato do crash: id gravado, leitura nunca feita."""
    ledger.passos[f"passo-{nome}"] = {
        "approval_id": aprovacao["approval_id"], "nome": nome, "ordinal": ordinal,
        "state": "CREATED", "id_externo": _id_do_passo(nome),
        "codigo": None, "readback": None, "prepared_at": h.PREPARADO_EM,
        "claim_token": None, "claim_generation": 2, "observados": [],
    }


def test_id_conhecido_sem_confirmacao_entra_na_recuperacao_e_e_lido_pelo_id(
    monkeypatch,
) -> None:
    """Zero ambíguos com zero leituras era indistinguível de "está tudo certo".

    Antes: o filtro era `state == "AMBIGUOUS"` e nada mais, então uma Campaign
    CRIADA com id gravado e leitura nunca feita ficava invisível — e a rota
    respondia `passos_ambiguos: 0` sobre um objeto que existe na conta.
    """
    ledger, cliente, aprovacao = _abrir_bancada(monkeypatch)
    _passo_criado_sem_conferir(ledger, aprovacao)
    h.CENARIO.gets.clear()

    resposta = _reconciliar(cliente, aprovacao["approval_id"])
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()

    # O passo APARECE, com nome próprio: ele não é ambíguo, é não confirmado.
    assert corpo["passos_sem_confirmacao"] == ["campaign"]
    assert corpo["passos_em_recuperacao"] == 1
    # ⚠️ E a leitura ACONTECEU — antes eram zero GETs.
    assert h.CENARIO.gets, "a recuperacao precisa ter lido a conta"
    # ⚠️ PELO ID, não por listagem: procedência prova mais que nome.
    assert any(
        url.rstrip("/").endswith(f"/{h.IDS_CRIADOS['campaign']}")
        for url in h.CENARIO.gets
    ), h.CENARIO.gets
    assert not any("/campaigns" in url for url in h.CENARIO.gets), (
        "identidade com id durável não pode ser reconstruída por nome")
    # A conclusão é registrada, e ela é uma CONFIRMAÇÃO, não um novo fechamento.
    assert corpo["conclusoes"][0]["conclusao"] == "CONFIRMADO_POR_LEITURA"
    assert ledger.passos["passo-campaign"]["readback_evidencia"]["matched"] is True
    # E o recibo passa a poder responder "isto foi conferido, e quando".
    assert corpo["recibo"]["steps"][0]["readback_confirmed"] is True
    # Nenhum POST saiu da recuperação. Nunca.
    assert h.CENARIO.criados == []
    assert corpo["efeito_externo"] == "NENHUM"


def test_recuperacao_por_id_nao_devolve_identificador_ao_navegador(
    monkeypatch,
) -> None:
    """O id resolvido é contrato interno. Ele entra no reconciliador, não na tela."""
    # IDs sintéticos curtos (1001...) podem coincidir com um trecho do SHA do
    # plano e acusar vazamento aleatoriamente. Mantém a inspeção do corpo inteiro.
    for indice, tipo in enumerate(h.IDS_CRIADOS, start=1):
        monkeypatch.setitem(h.IDS_CRIADOS, tipo, f"9999900000000000{indice:02d}")
    ledger, cliente, aprovacao = _abrir_bancada(monkeypatch)
    _passo_criado_sem_conferir(ledger, aprovacao)

    corpo = _reconciliar(cliente, aprovacao["approval_id"]).json()
    import json as _json
    texto = _json.dumps(corpo, ensure_ascii=False)
    for identificador in h.IDS_CRIADOS.values():
        assert identificador not in texto, f"id {identificador} vazou na resposta"
    assert corpo["recibo"]["steps"][0]["has_external_id"] is True


def test_criativo_com_id_conhecido_e_conferido_pelo_id(monkeypatch) -> None:
    """O que a busca por nome NUNCA consegue fazer.

    `AdCreative` não expõe `created_time`, então a correlação temporal é
    impossível e ele jamais é adotado por nome. Com id durável a pergunta é
    outra — e ela tem resposta.
    """
    ledger, cliente, aprovacao = _abrir_bancada(monkeypatch)
    criativo = "creative:variation-001"
    for ordinal, nome in enumerate(("campaign", "adset", criativo), start=1):
        _passo_criado_sem_conferir(ledger, aprovacao, nome, ordinal)
    h.CENARIO.gets.clear()

    corpo = _reconciliar(cliente, aprovacao["approval_id"]).json()
    conclusoes = {item["passo"]: item["conclusao"] for item in corpo["conclusoes"]}
    assert conclusoes[criativo] == "CONFIRMADO_POR_LEITURA"
    assert ledger.passos[f"passo-{criativo}"]["readback_evidencia"]["matched"] is True


def test_divergencia_lida_pelo_id_registra_e_nao_confirma(monkeypatch) -> None:
    """Existir não é estar aceito: divergência vira evidência, nunca conclusão boa."""
    ledger, cliente, aprovacao = _abrir_bancada(monkeypatch)
    _passo_criado_sem_conferir(ledger, aprovacao)
    h.CENARIO.divergir_em = "campaign"

    corpo = _reconciliar(cliente, aprovacao["approval_id"]).json()
    assert corpo["conclusoes"][0]["conclusao"] == "DIVERGENTE"
    passo = ledger.passos["passo-campaign"]
    assert passo["readback"] == "META_READBACK_DIVERGENT"
    assert passo["readback_evidencia"]["matched"] is False
    assert corpo["recibo"]["steps"][0]["readback_confirmed"] is False
    assert h.CENARIO.criados == []


def test_passo_ja_confirmado_nao_e_relido(monkeypatch) -> None:
    """Reler o que o livro já dá por conferido gastaria leitura e trocaria
    um id de procedência por um homônimo."""
    ledger, cliente, aprovacao = _abrir_bancada(monkeypatch)
    _passo_criado_sem_conferir(ledger, aprovacao)
    ledger.passos["passo-campaign"].update(
        readback_at="2026-09-07T12:00:00+00:00",
        readback_evidencia={"matched": True, "tipo": "campaign"})
    h.CENARIO.gets.clear()

    corpo = _reconciliar(cliente, aprovacao["approval_id"]).json()
    assert corpo["passos_em_recuperacao"] == 0
    assert h.CENARIO.gets == []


def test_passo_nunca_despachado_aparece_com_nome_proprio(monkeypatch) -> None:
    """A linha commita ANTES do POST: sem linha, nenhuma rede saiu por ali."""
    ledger, cliente, aprovacao = _abrir_bancada(monkeypatch)
    _passo_criado_sem_conferir(ledger, aprovacao)

    corpo = _reconciliar(cliente, aprovacao["approval_id"]).json()
    assert corpo["passos_nao_despachados"] == [
        "adset", "creative:variation-001", "ad:variation-001"]


# ---------------------------------------------------------------------------
# R0-A05 · expiração fecha NOVO despacho, e só ele
# ---------------------------------------------------------------------------

def _plano_com_politica_confirmada_ha(minutos: int) -> dict[str, Any]:
    plano = h._plano_para_envio()
    confirmado = (datetime.now(timezone.utc) - timedelta(minutes=minutos)).isoformat()
    plano["asset_policy_confirmed_at"] = confirmado
    for variacao in plano["variations"]:
        variacao["asset_policy_confirmed_at"] = confirmado
    return plano


def test_aprovacao_nunca_vive_mais_que_a_prova_que_a_sustenta(monkeypatch) -> None:
    """A atestação vale uma hora; a aprovação, quinze minutos.

    Aprovar no minuto 59 produzia `expires_at` DEPOIS de `policy_expires_at` —
    autoridade de gasto sobre prova que já não existe.
    """
    ledger, _, aprovacao = _abrir_bancada(
        monkeypatch, plano=_plano_com_politica_confirmada_ha(59))
    gravada = ledger.aprovacoes[aprovacao["approval_id"]]
    prova = min(
        datetime.fromisoformat(item["policy_expires_at"])
        for item in gravada["plano_congelado"]["asset_supply"]
    )
    assert gravada["expires_at"] == prova, (
        "a validade da aprovação precisa ser cortada pela validade da prova")


def test_prova_vencida_fecha_novo_despacho_antes_do_keychain(monkeypatch) -> None:
    """Minuto 61: a política venceu, a aprovação ainda vale — zero POSTs.

    ⚠️ O relógio adiantado é o de `contrato.agora_utc`, que é o que o despacho
    consulta de verdade.
    """
    _, cliente, aprovacao = _abrir_bancada(
        monkeypatch, plano=_plano_com_politica_confirmada_ha(30))

    def _keychain_proibido(*_: Any, **__: Any):
        raise AssertionError("o Keychain nao pode ser lido com a prova vencida")

    from app.routers import trafego_meta_criacao as rota
    monkeypatch.setattr(rota, "_credencial_salva", _keychain_proibido)
    _relogio_em(monkeypatch, datetime.now(timezone.utc) + timedelta(minutes=45))
    antes = len(h.CENARIO.posts)

    resposta = _criar(cliente, aprovacao)
    assert resposta.status_code == 409, resposta.text
    assert resposta.json()["detail"]["codigo"] == "META_ASSET_POLICY_RECEIPT_EXPIRED"
    # Nem criação, nem validate_only: a recusa é anterior a qualquer requisição
    # — e o Keychain, substituído por uma armadilha acima, nunca foi lido.
    assert h.CENARIO.criados == []
    assert len(h.CENARIO.posts) == antes


def test_expiracao_da_prova_nao_fecha_a_recuperacao_do_mesmo_snapshot(
    monkeypatch,
) -> None:
    """A assimetria é o contrato: fecha o que pode NASCER, nunca a leitura.

    É exatamente a regressão que `F02` consertou, e que a correção de R0-A05
    não pode reintroduzir por outra porta.
    """
    ledger, cliente, aprovacao = _abrir_bancada(
        monkeypatch, plano=_plano_com_politica_confirmada_ha(30))
    _passo_criado_sem_conferir(ledger, aprovacao)
    _relogio_em(monkeypatch, datetime.now(timezone.utc) + timedelta(hours=6))

    resposta = _reconciliar(cliente, aprovacao["approval_id"])
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["conclusoes"][0]["conclusao"] == "CONFIRMADO_POR_LEITURA"
    assert h.CENARIO.gets, "a leitura histórica precisa continuar acontecendo"
    assert h.CENARIO.criados == []


def test_vencimento_no_meio_da_saga_nao_libera_passo_novo(monkeypatch) -> None:
    """Cada degrau é um POST NOVO, e a prova é reconferida em cada um.

    Deixar o terceiro sair porque o primeiro saiu a tempo é o mesmo defeito da
    porta, noventa segundos depois.
    """
    _, cliente, aprovacao = _abrir_bancada(monkeypatch)
    real = contrato_meta.agora_utc
    vencido = datetime.now(timezone.utc) + timedelta(hours=6)
    estado = {"chamadas": 0}

    def relogio_que_avanca() -> datetime:
        # As duas primeiras perguntas são a da porta e a do primeiro degrau; a
        # partir do segundo degrau o tempo já passou.
        estado["chamadas"] += 1
        return real() if estado["chamadas"] <= 2 else vencido

    monkeypatch.setattr(contrato_meta, "agora_utc", relogio_que_avanca)
    resposta = _criar(cliente, aprovacao)

    assert resposta.status_code == 409, resposta.text
    assert resposta.json()["detail"]["codigo"] == "META_ASSET_POLICY_RECEIPT_EXPIRED"
    # A campanha nasceu antes do vencimento e PERMANECE — expiração não apaga o
    # que já existe. O que ela fecha é o degrau seguinte.
    assert h.CENARIO.criados == ["campaign"]


# ---------------------------------------------------------------------------
# R0-A06 · idade não substitui autoridade do trabalhador
# ---------------------------------------------------------------------------

class _LedgerQueTomaAReivindicacao(h._LedgerEmMemoria):
    """Outro processo reclama a linha ENQUANTO o primeiro ainda vai despachar."""

    async def preparar_passo(self, **kwargs: Any):
        resultado = await super().preparar_passo(**kwargs)
        if kwargs["nome"] == "campaign":
            passo = self.passos[resultado.passo_ref]
            passo["prepared_at"] = h.PREPARADO_EM
            await self.reclamar_orfao(
                passo_ref=resultado.passo_ref, idade_minima_s=300)
            assert passo["state"] == "AMBIGUOUS"
        return resultado


def test_trabalhador_cercado_nao_conclui_e_o_id_visto_nao_se_perde(
    monkeypatch,
) -> None:
    """A resposta antiga de DESPACHAR deixa de valer como autoridade.

    Antes: o trabalhador voltava com a reivindicação velha, despachava os quatro
    objetos e ainda fechava o passo por cima da promoção. A idade anunciava a
    dúvida sem tirar a caneta da mão de quem a causou.
    """
    ledger, cliente, aprovacao = _abrir_bancada(
        monkeypatch, _LedgerQueTomaAReivindicacao())
    resposta = _criar(cliente, aprovacao)

    assert ("reclamar", "passo-campaign") in ledger.eventos
    assert resposta.status_code == 502, resposta.text
    corpo = resposta.json()["detail"]
    assert corpo["codigo"] == "META_WORKER_FENCED"
    assert corpo["reconciliacao_necessaria"] is True
    assert corpo["retry_permitido"] is False

    # ⚠️ A SAGA PAROU NO PRIMEIRO DEGRAU. Antes eram quatro objetos.
    assert h.CENARIO.criados == ["campaign"]

    passo = ledger.passos["passo-campaign"]
    # A conclusão do cercado NÃO aconteceu: o passo continua ambíguo.
    assert passo["state"] == "AMBIGUOUS"
    assert passo["id_externo"] is None
    # ⚠️ E o id que ele viu nascer NÃO SE PERDEU. Nenhuma linha de banco cancela
    # uma requisição já entregue; jogar o id fora deixaria uma campanha órfã
    # invisível na conta.
    assert passo["observados"] == [h.IDS_CRIADOS["campaign"]]
    assert ("cercado", "passo-campaign") in ledger.eventos


def test_o_id_observado_pelo_cercado_alimenta_a_recuperacao_por_leitura(
    monkeypatch,
) -> None:
    """O recibo denuncia a ambiguidade sem entregar identificador nenhum."""
    ledger, cliente, aprovacao = _abrir_bancada(
        monkeypatch, _LedgerQueTomaAReivindicacao())
    _criar(cliente, aprovacao)

    corpo = _reconciliar(cliente, aprovacao["approval_id"]).json()
    passo = next(p for p in corpo["recibo"]["steps"] if p["name"] == "campaign")
    assert passo["observed_external_id_count"] == 1
    import json as _json
    assert h.IDS_CRIADOS["campaign"] not in _json.dumps(corpo, ensure_ascii=False)


def test_autoridade_vencida_nao_fecha_nem_falha_o_passo(monkeypatch) -> None:
    """As três escritas de conclusão recusam um token que já não vale.

    FALHAR é a mais perigosa das três: `FAILED` declara "nada nasceu" e LIBERA o
    plano para nova aprovação.
    """
    ledger = h._LedgerEmMemoria()
    _abrir_bancada(monkeypatch, ledger)

    async def cenario() -> None:
        passo = await ledger.preparar_passo(
            plano_sha256=next(iter(ledger.aprovacoes.values()))["plano_sha256"],
            approval_id=next(iter(ledger.aprovacoes)),
            ator=next(iter(ledger.aprovacoes.values()))["ator"],
            nome="campaign", payload_sha256="a" * 64)
        antigo = passo.claim_token
        assert antigo
        ledger.passos[passo.passo_ref]["prepared_at"] = h.PREPARADO_EM
        await ledger.reclamar_orfao(passo_ref=passo.passo_ref, idade_minima_s=300)

        for chamada in (
            lambda: ledger.fechar_passo(
                passo_ref=passo.passo_ref, id_externo="1001", claim_token=antigo),
            lambda: ledger.falhar_passo(
                passo_ref=passo.passo_ref, codigo="META_X", claim_token=antigo),
            lambda: ledger.marcar_ambiguo(
                passo_ref=passo.passo_ref, claim_token=antigo),
        ):
            try:
                await chamada()
            except h.ErroDeNascimentoMeta as exc:
                assert "META_STEP_CLAIM_FENCED" in str(exc)
            # `marcar_ambiguo` sobre um passo JÁ ambíguo é no-op de sucesso: não
            # há estado novo a conceder e não há nada a apagar.
        assert ledger.passos[passo.passo_ref]["state"] == "AMBIGUOUS"
        assert ledger.passos[passo.passo_ref]["id_externo"] is None

    asyncio.run(cenario())


def test_o_token_gira_ao_fechar_para_a_anotacao_nao_pousar_em_conclusao_nova(
    monkeypatch,
) -> None:
    """A terceira janela: entre a conclusão e o read-back.

    Se o token continuasse o mesmo, uma anotação de leitura atrasada — emitida
    com a autoridade do DESPACHO — poderia pousar sobre uma conclusão mais nova.
    """
    ledger = h._LedgerEmMemoria()
    _abrir_bancada(monkeypatch, ledger)

    async def cenario() -> None:
        aprovacao = next(iter(ledger.aprovacoes.values()))
        passo = await ledger.preparar_passo(
            plano_sha256=aprovacao["plano_sha256"],
            approval_id=aprovacao["approval_id"], ator=aprovacao["ator"],
            nome="campaign", payload_sha256="a" * 64)
        despacho = passo.claim_token
        girado = await ledger.fechar_passo(
            passo_ref=passo.passo_ref, id_externo="1001", claim_token=despacho)
        assert girado and girado != despacho

        with pytest.raises(h.ErroDeNascimentoMeta) as erro:
            await ledger.registrar_readback(
                passo_ref=passo.passo_ref, evidencia={"matched": True},
                claim_token=despacho)
        assert "META_STEP_CLAIM_FENCED" in str(erro.value)

        await ledger.registrar_readback(
            passo_ref=passo.passo_ref, evidencia={"matched": True},
            claim_token=girado)
        assert ledger.passos[passo.passo_ref]["readback_at"]

    asyncio.run(cenario())


def test_cercado_nao_sobrescreve_identidade_divergente(monkeypatch) -> None:
    """Preservar o id do cercado nunca pode apagar a conclusão de outro."""
    ledger = h._LedgerEmMemoria()
    _abrir_bancada(monkeypatch, ledger)

    async def cenario() -> None:
        aprovacao = next(iter(ledger.aprovacoes.values()))
        passo = await ledger.preparar_passo(
            plano_sha256=aprovacao["plano_sha256"],
            approval_id=aprovacao["approval_id"], ator=aprovacao["ator"],
            nome="campaign", payload_sha256="a" * 64)
        antigo = passo.claim_token
        # A recuperação concluiu com OUTRO id enquanto o despacho estava no ar.
        ledger.passos[passo.passo_ref]["prepared_at"] = h.PREPARADO_EM
        await ledger.reclamar_orfao(passo_ref=passo.passo_ref, idade_minima_s=300)
        await ledger.concluir_por_recuperacao(
            passo_ref=passo.passo_ref, id_externo="1001",
            evidencia={"matched": True})

        await ledger.registrar_despacho_cercado(
            passo_ref=passo.passo_ref, claim_token=antigo, id_externo="9999")
        linha = ledger.passos[passo.passo_ref]
        # A identidade concluída fica de pé; o id contestado fica AO LADO.
        assert linha["id_externo"] == "1001"
        assert linha["observados"] == ["9999"]
        assert linha["state"] == "CREATED"

    asyncio.run(cenario())


@pytest.mark.parametrize("conclusao", ["recuperacao", "readback_despacho", "readback_girado"])
@pytest.mark.parametrize("divergente", [False, True])
def test_token_revogado_nao_anota_depois_que_o_passo_fica_sem_dono(
    monkeypatch, conclusao: str, divergente: bool,
) -> None:
    """NULL no livro não reabilita um token antigo apresentado pelo worker."""
    from copy import deepcopy

    ledger = h._LedgerEmMemoria()
    _abrir_bancada(monkeypatch, ledger)

    async def cenario() -> None:
        aprovacao = next(iter(ledger.aprovacoes.values()))
        passo = await ledger.preparar_passo(
            plano_sha256=aprovacao["plano_sha256"],
            approval_id=aprovacao["approval_id"], ator=aprovacao["ator"],
            nome="campaign", payload_sha256="a" * 64)
        vencido = passo.claim_token
        evidencia = {"matched": True, "tipo": "campaign", "status": "PAUSED"}
        if conclusao == "recuperacao":
            ledger.passos[passo.passo_ref]["prepared_at"] = h.PREPARADO_EM
            await ledger.reclamar_orfao(passo_ref=passo.passo_ref, idade_minima_s=300)
            await ledger.concluir_por_recuperacao(
                passo_ref=passo.passo_ref, id_externo="1001", evidencia=evidencia)
        else:
            girado = await ledger.fechar_passo(
                passo_ref=passo.passo_ref, id_externo="1001", claim_token=vencido)
            await ledger.registrar_readback(
                passo_ref=passo.passo_ref, evidencia=evidencia, claim_token=girado)
            if conclusao == "readback_girado":
                vencido = girado

        antes = deepcopy(ledger.passos[passo.passo_ref])
        assert antes["claim_token"] is None
        with pytest.raises(h.ErroDeNascimentoMeta, match="META_STEP_CLAIM_FENCED"):
            await ledger.registrar_readback(
                passo_ref=passo.passo_ref,
                evidencia={"matched": not divergente, "tipo": "campaign",
                           "status": "ENABLED" if divergente else "PAUSED"},
                codigo="META_STALE_WORKER_PROBE" if divergente else None,
                claim_token=vencido)
        assert ledger.passos[passo.passo_ref] == antes
        # O caminho governado da recuperação, sem token, continua utilizável.
        await ledger.concluir_por_recuperacao(
            passo_ref=passo.passo_ref, id_externo="1001", evidencia=evidencia)
        assert ledger.passos[passo.passo_ref]["readback_evidencia"] == evidencia

    asyncio.run(cenario())
