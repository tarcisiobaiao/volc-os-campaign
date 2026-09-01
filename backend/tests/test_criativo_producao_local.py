"""A produção local ponta a ponta, como a tela `/criativos` vai consumi-la.

Rodar:
    backend/.venv/bin/python -m pytest backend/tests/test_criativo_producao_local.py -q

O que se prova aqui é o CONTRATO com a UI, não o interior da bancada (isso é
`test_criativo_bancada.py`). Em particular, os quatro desfechos que a tela tem de
distinguir e que um envelope descuidado colapsaria num só:

    pedido recusado      `erro` preenchido, `trabalho_id` None
    render falhou        `estado == "failed"`, `falha.codigo` com a causa
    ainda rodando        `terminal is False`, `assets` vazio por PENDÊNCIA
    produziu             `estado == "rendered"`, `assets` e `recibo` presentes

`assets == []` aparece em três dos quatro. É por isso que ele nunca pode ser a
pergunta que a tela faz.
"""

from __future__ import annotations

import json

import pytest

from app.criativo.bancada import servico
from volc_ads.criativo.contrato import NaturezaDaProcedencia

INSUMO = "banner do FGTS de setembro"


@pytest.fixture
def bancada(tmp_path, monkeypatch):
    """Uma bancada limpa por teste.

    O singleton do PROCESSO (qual fila, qual pasta) é o que precisa ser
    reiniciado; o estado de execução já é por trabalho. Sem isto, o primeiro
    teste que rodasse fixaria a pasta para todos os outros.
    """
    monkeypatch.setenv("CRIATIVO_BANCADA_DIR", str(tmp_path / "bancada"))
    monkeypatch.setenv("CRIATIVO_AMBIENTE", "local")
    monkeypatch.setattr(servico, "_BANCADA", None, raising=False)
    yield servico
    monkeypatch.setattr(servico, "_BANCADA", None, raising=False)


def _produzir(bancada, receita_id="display-minimo", **extra):
    campos = {"receita_id": receita_id, "tenant_id": "volc", "insumo": INSUMO}
    campos.update(extra)
    return bancada.produzir_local(**campos)


# ── o catálogo de receitas ──────────────────────────────────────────────────


def test_as_receitas_locais_declaram_natureza_e_que_nao_sao_publicaveis(bancada):
    receitas = bancada.receitas_locais()
    assert {r["receita_id"] for r in receitas} == {
        "display-minimo", "demand-gen-minimo"
    }
    for receita in receitas:
        assert receita["motor_slug"] == "png-local"
        assert receita["disponivel"] is True
        assert receita["natureza"] == NaturezaDaProcedencia.LOCAL.value
        # A tela não pode oferecer botão de publicar sobre isto.
        assert receita["publicavel"] is False
        assert receita["saidas"]
        for saida in receita["saidas"]:
            assert saida["largura"] > 0 and saida["altura"] > 0
            assert saida["papel"], saida


def test_as_saidas_saem_da_regua_do_canal_e_nao_de_uma_lista_escrita_a_mao(bancada):
    from volc_ads.criativo import requisitos

    por_id = {r["receita_id"]: r for r in bancada.receitas_locais()}
    display = por_id["display-minimo"]
    exigencia = requisitos.exigencia_binaria_de("DISPLAY")

    assert display["exigencia_fonte"] == exigencia.fonte
    assert display["exigencia_provisoria"] is exigencia.provisorio
    tipos = {s["tipo"] for s in display["saidas"]}
    assert tipos == {t.value for t in exigencia.obrigatorios}


def test_motores_disponiveis_traz_natureza_e_publicavel(bancada):
    motores = {m["slug"]: m for m in bancada.motores_disponiveis()}
    assert "png-local" in motores
    assert motores["png-local"]["natureza"] == "local"
    assert motores["png-local"]["publicavel"] is False
    # O motor local não tem pré-requisito: se ele sumir do registro, é defeito.
    assert motores["png-local"]["versoes"]["zlib"]


# ── o desfecho feliz ────────────────────────────────────────────────────────


@pytest.mark.parametrize("receita_id", ["display-minimo", "demand-gen-minimo"])
def test_uma_receita_produz_asset_real_com_recibo_e_atravessa_a_ponte(
    bancada, receita_id
):
    envelope = _produzir(bancada, receita_id)

    assert envelope["erro"] is None
    assert envelope["falha"] is None
    assert envelope["estado"] == "rendered"
    assert envelope["terminal"] is True
    assert envelope["trabalho_id"]
    assert envelope["recibo"] is not None
    assert envelope["assinatura_determinista"]
    assert envelope["artefatos_perdidos"] == []

    assert envelope["assets"]
    for asset in envelope["assets"]:
        assert asset["conteudo_hash"].startswith("sha256:")
        assert asset["mime"] == "image/png"
        assert asset["largura"] > 0 and asset["altura"] > 0
        assert asset["bytes_totais"] > 0
        assert asset["papel"]
        assert asset["natureza"] == "local"
        assert asset["publicavel"] is False
        proc = asset["procedencia"]
        assert proc["motor"] == "png-local"
        assert proc["insumo"] == INSUMO
        assert proc["pedido"] == envelope["trabalho_id"]
        assert proc["quando"]
        # `0.0` seria a afirmação de que a peça saiu de graça, e um COGS que
        # soma esses zeros fecha bonito e está errado.
        assert proc["custo_usd"] is None

    entrega = envelope["entrega"]
    assert entrega is not None and entrega["tentada"] is True
    assert entrega["ok"] is True
    assert entrega["veredito"]["ok"] is True
    assert len(entrega["linhagem"]) == len(envelope["assets"])
    assert entrega["recusas"] == []


def test_a_linhagem_da_entrega_aponta_para_os_mesmos_arquivos_dos_assets(bancada):
    envelope = _produzir(bancada)
    por_hash = {a["conteudo_hash"]: a for a in envelope["assets"]}

    for linha in envelope["entrega"]["linhagem"]:
        asset = por_hash[linha["conteudo_hash"]]
        assert linha["identidade"] == asset["identidade"]
        assert linha["mime"] == asset["mime"]
        assert linha["largura"] == asset["largura"]
        assert linha["altura"] == asset["altura"]
        assert linha["motor"] == "png-local"
        assert linha["custo_usd"] is None
        assert linha["confirmada"] is True


def test_o_envelope_e_JSON_nativo_sem_default(bancada):
    """A rota serializa isto direto. Um `datetime` ou um `Enum` aqui estouraria
    `TypeError` no handler, longe de quem o introduziu."""
    envelope = _produzir(bancada)
    json.dumps(envelope)   # sem `default=`, de propósito


def test_nenhum_caminho_de_disco_vaza_para_a_tela(bancada, tmp_path):
    """`Artefato.caminho` existe e é lido; ele não pode sair daqui.

    O operário já paga esse preço em `_mensagem_para_o_operador`, pelo mesmo
    motivo: o operador não precisa do caminho e não deveria vê-lo.
    """
    envelope = _produzir(bancada)
    # O recibo cru é diagnóstico e carrega caminho; o que a TELA lê são
    # `assets`, `entrega` e `falha`.
    para_a_tela = json.dumps({
        "assets": envelope["assets"],
        "entrega": envelope["entrega"],
        "falha": envelope["falha"],
        "erro": envelope["erro"],
        "motor": envelope["motor"],
    })
    assert str(tmp_path) not in para_a_tela
    assert "/var/folders" not in para_a_tela
    assert ".volc-os" not in para_a_tela


# ── idempotência e reprodutibilidade ────────────────────────────────────────


def test_dois_pedidos_identicos_convergem_para_o_mesmo_trabalho(bancada):
    a = _produzir(bancada)
    b = _produzir(bancada)
    assert a["trabalho_id"] == b["trabalho_id"]
    assert a["chave_de_idempotencia"] == b["chave_de_idempotencia"]


def test_inquilinos_diferentes_com_o_mesmo_pedido_sao_trabalhos_diferentes(bancada):
    a = _produzir(bancada, tenant_id="volc")
    b = _produzir(bancada, tenant_id="outro")
    assert a["trabalho_id"] != b["trabalho_id"]


def test_a_mesma_receita_em_duas_bancadas_produz_os_mesmos_hashes(
    bancada, tmp_path, monkeypatch
):
    """Reprodutibilidade: o hash é o do arquivo, e o arquivo é função do pedido."""
    primeiro = [a["conteudo_hash"] for a in _produzir(bancada)["assets"]]

    monkeypatch.setenv("CRIATIVO_BANCADA_DIR", str(tmp_path / "outra"))
    monkeypatch.setattr(servico, "_BANCADA", None, raising=False)
    segundo = [a["conteudo_hash"] for a in _produzir(servico)["assets"]]

    assert primeiro == segundo
    assert primeiro  # não é uma igualdade entre duas listas vazias


def test_insumos_diferentes_produzem_arquivos_diferentes(bancada):
    a = [x["conteudo_hash"] for x in _produzir(bancada)["assets"]]
    b = [
        x["conteudo_hash"]
        for x in _produzir(bancada, insumo="outro briefing")["assets"]
    ]
    assert a != b


# ── a recusa de promover ensaio a produção ──────────────────────────────────


@pytest.mark.parametrize("receita_id", ["display-minimo", "demand-gen-minimo"])
def test_peca_local_e_recusada_quando_o_destino_e_producao(bancada, receita_id):
    envelope = _produzir(bancada, receita_id, destino="producao")

    assert envelope["estado"] == "rendered"      # produziu
    entrega = envelope["entrega"]
    assert entrega["destino"] == "producao"
    assert entrega["ok"] is False                # e não sobe
    # ⚠️ O par que a tela precisa distinguir: o LOTE é bom, o payload não sai.
    assert entrega["veredito"]["ok"] is True
    assert entrega["linhagem"] == []
    assert any("local" in m for m in entrega["recusas"])
    assert set(entrega["naturezas"].values()) == {"local"}


def test_destino_desconhecido_e_recusado_antes_de_qualquer_producao(bancada):
    envelope = _produzir(bancada, destino="homologacao")
    assert envelope["erro"]["codigo"] == "destino_desconhecido"
    assert envelope["trabalho_id"] is None


# ── os desfechos que não são sucesso ────────────────────────────────────────


def test_receita_desconhecida_nao_e_falha_de_render(bancada):
    envelope = _produzir(bancada, receita_id="nao-existe")
    assert envelope["erro"]["codigo"] == "receita_desconhecida"
    # As duas ausências que separam "pedido recusado" de "render falhou".
    assert envelope["trabalho_id"] is None
    assert envelope["estado"] is None
    assert envelope["falha"] is None
    assert envelope["assets"] == []
    assert envelope["entrega"] is None


def test_insumo_vazio_e_recusado_sem_criar_trabalho(bancada):
    deposito, _, _ = bancada.montar()
    antes = deposito.contar_por_estado()
    envelope = _produzir(bancada, insumo="   ")
    assert envelope["erro"]["codigo"] == "insumo_vazio"
    assert deposito.contar_por_estado() == antes


def test_tenant_vazio_e_recusado(bancada):
    envelope = _produzir(bancada, tenant_id="")
    assert envelope["erro"]["codigo"] == "tenant_vazio"


def test_ambiente_sem_processo_longo_recusa_em_vez_de_render_no_request(
    bancada, monkeypatch
):
    """A fronteira de `despacho.py` é fail-closed, e esta camada não a contorna.

    Chamar `DespachanteLocal` direto daqui produziria um 201 sobre um trabalho
    que a plataforma vai congelar — a mentira que aquela fronteira existe para
    impedir. A peça local é barata; o precedente não é.
    """
    deposito, _, _ = bancada.montar()
    antes = deposito.contar_por_estado()
    monkeypatch.setenv("CRIATIVO_AMBIENTE", "vercel")

    envelope = _produzir(bancada)
    assert envelope["erro"]["codigo"] == "ambiente_sem_processo_longo"
    assert envelope["trabalho_id"] is None
    assert deposito.contar_por_estado() == antes


def test_motor_ausente_recusa_o_pedido_em_vez_de_enfileirar_o_que_nao_roda(
    bancada, monkeypatch
):
    """Uma máquina sem o motor não aceita o pedido, e não o guarda para falhar
    depois. Enfileirar aqui produziria um `failed` com `motor_desconhecido` que
    o operador só veria depois de esperar."""
    deposito, operario, _ = bancada.montar()
    monkeypatch.delitem(operario.motores, "png-local")
    antes = deposito.contar_por_estado()

    envelope = _produzir(bancada)
    assert envelope["erro"]["codigo"] == "motor_indisponivel"
    assert envelope["trabalho_id"] is None
    assert deposito.contar_por_estado() == antes


def test_estado_de_trabalho_inexistente_e_None_e_nao_envelope_vazio(bancada):
    assert bancada.estado_da_producao("nao-existe", tenant_id="volc") is None


def test_um_inquilino_nao_le_o_trabalho_do_outro(bancada):
    envelope = _produzir(bancada, tenant_id="volc")
    assert bancada.estado_da_producao(
        envelope["trabalho_id"], tenant_id="outro"
    ) is None
    assert bancada.estado_da_producao(
        envelope["trabalho_id"], tenant_id="volc"
    ) is not None


def test_artefato_apagado_do_disco_vira_recusa_nomeada_e_nao_asset_fantasma(
    bancada
):
    """O recibo confere os bytes no instante do render; o arquivo pode sumir
    depois. Construir o asset a partir da DECLARAÇÃO descreveria um arquivo que
    não existe mais."""
    import pathlib

    envelope = _produzir(bancada)
    for artefato in envelope["recibo"]["artefatos"]:
        pathlib.Path(artefato["caminho"]).unlink()

    de_novo = bancada.estado_da_producao(
        envelope["trabalho_id"], tenant_id="volc"
    )
    assert de_novo["assets"] == []
    assert len(de_novo["artefatos_perdidos"]) == len(envelope["assets"])
    assert all("não pôde ser lido" in m for m in de_novo["artefatos_perdidos"])
    # E a entrega reprova, com o motivo do canal — não com um payload vazio
    # que pareceria sucesso.
    assert de_novo["entrega"]["ok"] is False
    assert de_novo["entrega"]["veredito"]["ok"] is False


# ── ambiente ────────────────────────────────────────────────────────────────


def test_o_ambiente_diz_que_o_despachante_local_nao_e_duravel(bancada):
    ambiente = bancada.ambiente_da_bancada()
    assert ambiente["pode_produzir"] is True
    assert ambiente["despachante"] == "sincrono-local"
    # Dito em voz alta: o trabalho não sobrevive à morte deste processo.
    assert ambiente["duravel"] is False


def test_o_ambiente_serverless_diz_por_que_nao_pode_produzir(bancada, monkeypatch):
    monkeypatch.setenv("CRIATIVO_AMBIENTE", "vercel")
    ambiente = bancada.ambiente_da_bancada()
    assert ambiente["pode_produzir"] is False
    assert ambiente["motivo"]
    assert ambiente["ambiente"] == "vercel"
