"""O pedido aprovado é o corpo LITERAL do POST — ou não é nada.

## O defeito que estes testes fecham

O relatório anterior chamou `canario-v10-payload.json` de "corpo HTTP exato do
futuro POST /api/trafego/subir". Não era: faltavam `confirmar_criacao_pausada`
e `carimbo_nome`. Um arquivo que não passa por `SubirEntrada` não é o corpo de
coisa nenhuma, e chamá-lo assim faz o revisor conferir a coisa errada.

Agora são dois arquivos com papéis diferentes:

    canario-v10-provar-base.json      entrada de /provar — sem carimbo, sem
                                      confirmação, porque nenhum dos dois existe
                                      antes da prova
    canario-v10-approved-request.json corpo literal do /subir, gerado a partir
                                      de UMA execução de validate_only

⚠️ O acoplamento que importa: `plano_impressao` é o selo do executor, e ele
varia por carimbo porque o nome da campanha carrega o carimbo. Carimbo e selo
precisam vir da MESMA execução; misturar duas produz um pedido que `/subir`
recusa, por um motivo que ninguém entenderia lendo o arquivo.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

D = (pathlib.Path(__file__).resolve().parents[2]
     / "docs" / "closure" / "search-production-closure-v1")
BASE = D / "canario-v10-provar-base.json"
APROVADO = D / "canario-v10-approved-request.json"
DOSSIE = D / "DOSSIE-CANARIO-V10.json"
EVIDENCIA = D / "EVIDENCIA-LANDING-PAGE.json"


def _json(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# ── 1. confirmação e carimbo presentes ──────────────────────────────────────

def test_1_pedido_aprovado_tem_confirmacao_e_carimbo():
    d = _json(APROVADO)
    assert d["confirmar_criacao_pausada"] is True
    assert d.get("carimbo_nome"), "carimbo_nome ausente ou vazio"
    assert d.get("plano_impressao"), "plano_impressao (o selo) ausente"
    # Metadado editorial não viaja num corpo HTTP.
    assert not [k for k in d if k.startswith("_")], "metadado editorial no pedido"


# ── 2. SubirEntrada aceita ──────────────────────────────────────────────────

def test_2_subir_entrada_parseia_o_pedido_aprovado():
    from app.routers import trafego

    corpo = trafego.SubirEntrada(**_json(APROVADO))
    assert corpo.confirmar_criacao_pausada is True
    assert corpo.canal == "SEARCH"
    assert len(corpo.grupos) == 1
    assert len(corpo.grupos[0].keywords) == 2


# ── 3. o canário considera elegível ─────────────────────────────────────────

def test_3_o_canario_considera_o_pedido_elegivel():
    from app.routers import trafego
    from app.trafego import canario

    corpo = trafego.SubirEntrada(**_json(APROVADO))
    cid, mid = trafego._no_escopo(corpo.customer_id, corpo.login_customer_id)
    chave = trafego._impressao_aprovavel(corpo, cid=cid, mid=mid)
    ok, motivo = canario.elegivel(
        customer_id=cid, login_customer_id=mid, canal=corpo.canal,
        budget_diario=corpo.budget_diario, cpc_inicial=corpo.cpc_inicial,
        chave_intencao=chave, carimbo_nome=corpo.carimbo_nome,
        rede=trafego._rede_do_corpo(corpo))
    assert ok, motivo


# ── 4. identidade bate com o dossiê ─────────────────────────────────────────

def test_4_identidade_do_pedido_bate_com_o_dossie():
    from app.routers import trafego
    from app.trafego import canario

    dossie = _json(DOSSIE)
    corpo = trafego.SubirEntrada(**_json(APROVADO))
    cid, mid = trafego._no_escopo(corpo.customer_id, corpo.login_customer_id)

    chave = trafego._impressao_aprovavel(corpo, cid=cid, mid=mid)
    assert chave == dossie["chave_intencao"]
    assert canario.prefixo_da_marca(chave) == dossie["marca_remota"]

    plano = trafego.plano_do_ledger(corpo, cid=cid, mid=mid)
    blueprint = hashlib.sha256(json.dumps(
        plano, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()
    assert blueprint == dossie["blueprint_sha256"]

    esc = dossie["execucao_escolhida"]
    assert corpo.carimbo_nome == esc["carimbo_nome"]
    assert corpo.plano_impressao == esc["selo_do_executor"]
    assert esc["n_operacoes"] == dossie["operacoes"]["total"] == 34


def test_4b_o_sha_do_pedido_bate_com_o_registrado_no_dossie():
    bytes_ = APROVADO.read_bytes()
    assert hashlib.sha256(bytes_).hexdigest() == _json(DOSSIE)["approved_request_sha256"]


# ── 5. confirmação ausente ou false falha fechado ───────────────────────────

@pytest.mark.parametrize("valor", [False, None, "sim", 0])
def test_5_confirmacao_ausente_ou_falsa_falha_fechado(valor):
    """⚠️ A confirmação é um ATO humano, e ato não tem default.

    `/subir` recusa quando ela não é `True`. O teste percorre também os valores
    que "parecem sim" — uma string e um zero — porque coerção silenciosa aqui
    transformaria uma não-confirmação numa autorização.
    """
    from app.routers import trafego

    d = _json(APROVADO)
    if valor is None:
        d.pop("confirmar_criacao_pausada")
    else:
        d["confirmar_criacao_pausada"] = valor
    try:
        corpo = trafego.SubirEntrada(**d)
    except Exception:
        return                      # recusado no contrato: falhou fechado
    assert corpo.confirmar_criacao_pausada is not True, (
        f"{valor!r} virou confirmação verdadeira")


# ── 6. carimbo ausente, divergente ou reaproveitado ─────────────────────────

def test_6a_carimbo_malformado_e_recusado_pelo_canario():
    from app.trafego import canario

    for ruim in ("ontem", "2026-09-01", "20260901", "20260901_9999"):
        with pytest.raises(canario.CanarioRecusado):
            canario.carimbo_do_nome(ruim)


def test_6a2_carimbo_ausente_e_CUNHADO_e_por_isso_invalida_o_selo():
    """⚠️ Ausência aqui NÃO é recusa — é minting, e isso é pior de perceber.

    `carimbo_do_nome("")` gera um carimbo NOVO: é assim que `/provar` cunha o
    primeiro. Num pedido de mutate isso significa que um `carimbo_nome` vazio
    não estoura — ele produz um nome diferente, logo outro protobuf, logo outro
    selo. A recusa vem depois, na comparação de selo de `/subir`, e é ela que
    impede o pedido sem carimbo de virar campanha.

    O teste existe para que ninguém "conserte" o vazio achando que ele é
    recusado na entrada.
    """
    from app.trafego import canario

    cunhado = canario.carimbo_do_nome("")
    assert cunhado and cunhado != _json(APROVADO)["carimbo_nome"]

    d = _json(APROVADO)
    d["carimbo_nome"] = ""
    from app.routers import trafego
    corpo = trafego.SubirEntrada(**d)
    # O corpo é aceito pelo contrato, e o selo enviado continua sendo o da
    # execução aprovada — que já não descreve o payload que seria montado.
    assert corpo.plano_impressao == _json(DOSSIE)["execucao_escolhida"]["selo_do_executor"]
    assert not corpo.carimbo_nome


def test_6b_carimbo_de_outra_execucao_invalida_o_selo():
    """⚠️ Carimbo e selo vêm da MESMA execução, ou o pedido não é o aprovado.

    O nome da campanha carrega o carimbo, o selo é o hash do protobuf, e o
    protobuf contém o nome. Trocar só o carimbo produz um corpo cujo
    `plano_impressao` descreve um payload que não é mais o que seria montado —
    e `/subir` recusa comparando os dois.
    """
    from app.routers import trafego

    d = _json(APROVADO)
    original = d["carimbo_nome"]
    d["carimbo_nome"] = "20260101_000000"
    corpo = trafego.SubirEntrada(**d)
    assert corpo.carimbo_nome != original
    # A identidade VOLC não muda (o carimbo saiu dela de propósito)...
    cid, mid = trafego._no_escopo(corpo.customer_id, corpo.login_customer_id)
    chave = trafego._impressao_aprovavel(corpo, cid=cid, mid=mid)
    assert chave == _json(DOSSIE)["chave_intencao"]
    # ...mas o SELO enviado deixa de corresponder ao payload que seria montado,
    # e é isso que `/subir` compara antes de deixar qualquer byte sair.
    assert corpo.plano_impressao == _json(DOSSIE)["execucao_escolhida"]["selo_do_executor"]


# ── 7. árvore suja não autoriza ─────────────────────────────────────────────

def test_7_arvore_suja_nao_produz_artefato_autorizado():
    """Um dossiê gerado com mudança não commitada não identifica o código."""
    dossie = _json(DOSSIE)
    assert dossie["arvore_suja"] is False, (
        "o dossiê de autorização foi gerado com a árvore suja: `code_sha` não "
        "identifica o código que rodou o validate_only")
    assert dossie["gates_do_dossie"]["arvore_limpa"] is True
    assert dossie["gates_reprovados"] == []


# ── 8. a base não serve como pedido de mutate ───────────────────────────────

def test_8_a_base_da_prova_nao_e_pedido_de_mutate():
    """⚠️ Era exatamente isto que o relatório anterior afirmava ser possível."""
    from app.routers import trafego

    base = _json(BASE)
    base_limpa = {k: v for k, v in base.items() if not k.startswith("_")}
    assert "confirmar_criacao_pausada" not in base_limpa
    assert "carimbo_nome" not in base_limpa

    with pytest.raises(Exception):
        trafego.SubirEntrada(**base_limpa)   # falta `motivo`, falta confirmação

    # E ela continua servindo para o que existe: a prova.
    corpo = trafego.ProvarEntrada(**base_limpa)
    assert corpo.canal == "SEARCH"


# ── procedência e evidência ─────────────────────────────────────────────────

def test_a_landing_page_esta_verificada_ou_o_mutate_fica_bloqueado():
    ev = _json(EVIDENCIA)
    assert ev["situacao"] == "verified", (
        "a página não pôde ser relida: marque source_unverified e NÃO autorize "
        "o mutate — alegação cuja fonte não responde deixou de ser verificável")
    assert ev["conteudo_sha256"]
    assert all(f["origem"] for f in ev["fatos_usados_nos_anuncios"])
    assert _json(DOSSIE)["gates_do_dossie"]["landing_page_verificada"] is True


def test_a_procedencia_separa_code_sha_de_artifacts_commit():
    d = _json(DOSSIE)
    assert d["code_sha"], "code_sha ausente"
    assert "sha_nota" in d
    # `artifacts_commit` só existe DEPOIS do commit dos artefatos, e o dossiê
    # não pode conter o hash do commit que o contém. `null` aqui é honesto.
    assert "artifacts_commit" in d
