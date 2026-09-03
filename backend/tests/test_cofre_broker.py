"""O broker 1Password -> AdsPower: as recusas, a fronteira do segredo e o recibo.

## O que estes testes protegem

Quatro promessas que, se quebradas, quebram em silencio:

1. **O segredo nao vira texto.** Nem no recibo, nem no log, nem no `repr` de uma
   excecao. A defesa nao e disciplina de quem escreve: e uma classe que recusa
   `str`, `format`, `json` e `copy`.
2. **A resposta do AdsPower nao e copiada.** Um perfil do AdsPower guarda a
   CONTA que ele autentica — usuario, senha, cookie e chave de 2FA. O recibo e
   montado por PROJECAO, e o teste alimenta os quatro campos proibidos e exige
   que nenhum sobreviva.
3. **Fail closed.** Trancar o 1Password interrompe o acesso. Sem Bearer ativo
   nao ha modo degradado, e a Local API nao chega a ser chamada.
4. **Esta versao so pergunta.** Nenhuma acao publicada muta; abrir perfil e
   recusado pelo NOME, com o estado `blocked/exige_checkpoint`.

Hermeticos: nenhum teste aqui abre socket, chama `op` ou toca no AdsPower.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import pickle
import sys
from typing import Any

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.asset_vault.broker import cli  # noqa: E402
from app.asset_vault.broker import dominio as dom  # noqa: E402
from app.asset_vault.broker.aplicacao import Broker, Pedido, Registro  # noqa: E402
from app.asset_vault.broker.infraestrutura import (  # noqa: E402
    VARIAVEL_DO_BEARER,
    ClienteLocalApi,
    SegredoDoAmbiente,
)

#: O canario. Se este texto reaparecer em qualquer saida, houve vazamento.
CHAVE = "NAO-E-UMA-CHAVE-REAL-mas-serve-de-canario-9f2a"
ENDERECO = "http://127.0.0.1:50325"

#: A resposta do `user/list` como o AdsPower a devolve: o perfil INTEIRO, com a
#: conta que ele autentica dentro. Nada em negrito aqui e invencao — e por isso
#: que a projecao existe.
RESPOSTA_DE_PERFIS: dict[str, Any] = {
    "code": 0, "msg": "success",
    "data": {"list": [{
        "user_id": "k11abc", "serial_number": 7, "name": "Piloto organico",
        "group_id": "g1", "group_name": "VOLC", "domain_name": "facebook.com",
        "created_time": 1756800000,
        "username": "conta@exemplo.com", "password": "Tr0ub4dor&3",
        "fakey": "JBSWY3DPEHPK3PXP", "cookie": '[{"name":"c_user","value":"1"}]',
        "remark": "senha antiga: Tr0ub4dor&3",
        "user_proxy_config": {"proxy_soft": "luminati", "proxy_user": "u",
                              "proxy_password": "p", "proxy_host": "1.2.3.4"},
    }]},
}


class PortaDuble:
    """A Local API de mentira. Registra o que recebeu; nao abre socket."""

    def __init__(self, resposta: Any = None, erro: Exception | None = None):
        self.chamadas: list[tuple[str, dict[str, str]]] = []
        self.bearer_como_texto: list[str] = []
        self._resposta = resposta if resposta is not None else {"code": 0, "msg": "ok"}
        self._erro = erro

    async def chamar(self, acao, parametros, bearer, timeout_s):
        self.chamadas.append((acao.nome, dict(parametros)))
        # O duble NAO chama `.revelar()`. Ele registra o que sairia se alguem
        # tratasse o Segredo como texto — que e o descuido real.
        self.bearer_como_texto.append(f"{bearer}")
        if self._erro is not None:
            raise self._erro
        return self._resposta


class FonteDuble:
    nome_da_variavel = VARIAVEL_DO_BEARER
    origem = "teste"

    def __init__(self, valor: str | None = CHAVE, referencia: str | None = None):
        self._valor = valor
        self._referencia = referencia

    def bearer(self):
        return dom.exigir_bearer(self._valor, nome_da_variavel=self.nome_da_variavel)

    def referencia_declarada(self):
        return self._referencia


def montar(porta: PortaDuble, *, valor: str | None = CHAVE, perfis=("k11abc",),
           registro: Registro | None = None, referencia: str | None = None) -> Broker:
    return Broker(endereco=ENDERECO, perfis_permitidos=perfis,
                  fonte=FonteDuble(valor, referencia), porta=porta,
                  registro=registro if registro is not None else Registro())


def rodar(corotina):
    return asyncio.run(corotina)


# ── 1. Loopback: o sidecar nao pode ser alcancavel de fora ──────────────────


@pytest.mark.parametrize("endereco,porque", [
    ("http://local.adspower.net:50325", "nome depende de DNS para provar loopback"),
    ("http://10.0.0.5:50325", "IP de rede, nao de loopback"),
    ("http://0.0.0.0:50325", "escutar em tudo nao e escutar em loopback"),
    ("https://127.0.0.1:50325", "TLS aqui so acrescenta certificado para desligar"),
    ("http://user:senha@127.0.0.1:50325", "credencial na URL vai para o log"),
    ("http://127.0.0.1", "porta implicita e como um broker acaba na 80"),
    ("http://127.0.0.1:50325/api/v1", "o caminho vem do catalogo, nao do operador"),
    ("http://127.0.0.1:50325?token=x", "query no endereco base"),
    # `.port` levanta ValueError numa porta nao numerica, e o ValueError cru
    # escaparia do `except` do CLI como traceback em vez de recibo.
    ("http://127.0.0.1:cinquenta", "porta que nao e numero"),
    ("", "endereco ausente"),
])
def test_o_endereco_so_pode_ser_loopback_literal(endereco, porque):
    with pytest.raises(dom.BrokerRecusado):
        dom.exigir_endereco_de_loopback(endereco)


def test_a_forma_canonica_continua_sendo_uma_url():
    assert dom.exigir_endereco_de_loopback("http://127.0.0.1:50325/") == ENDERECO
    # IPv6 sem colchetes nao e URL. Uma forma "canonica" que nenhum cliente
    # HTTP aceita nao e canonica.
    assert dom.exigir_endereco_de_loopback("http://[::1]:50325") == "http://[::1]:50325"


def test_broker_com_endereco_externo_nao_chega_a_existir():
    """A validacao e na CONSTRUCAO: um broker apontado para fora nao deve
    receber pedido nenhum, nem para recusa-lo."""
    with pytest.raises(dom.BrokerRecusado):
        Broker(endereco="http://192.168.0.10:50325", perfis_permitidos=("k11abc",),
               fonte=FonteDuble(), porta=PortaDuble())


# ── 2. Modo sem verificacao falha no preflight ──────────────────────────────


@pytest.mark.parametrize("flag", ["--no-verify", "--insecure", "--sem-verificacao",
                                  "--disable-auth", "--no-auth", "--no-masking"])
def test_modo_sem_verificacao_falha_antes_de_qualquer_chamada(flag):
    """O guia de MCP do AdsPower ensina a desligar a verificacao. O ADR de
    28/08/2026 recusa esse modo como configuracao VOLC — e a recusa acontece no
    preflight porque depois de a chamada sair nao ha o que desfazer."""
    with pytest.raises(dom.BrokerRecusado):
        dom.exigir_verificacao_ligada([flag], {})


@pytest.mark.parametrize("variavel", ["ADSPOWER_NO_AUTH", "ADSPOWER_INSECURE",
                                      "VOLC_BROKER_SEM_VERIFICACAO"])
def test_variavel_que_desliga_a_verificacao_tambem_falha(variavel):
    with pytest.raises(dom.BrokerRecusado):
        dom.exigir_verificacao_ligada([], {variavel: "1"})


def test_a_variavel_desligada_explicitamente_nao_e_recusa():
    """`ADSPOWER_NO_AUTH=0` e alguem dizendo "nao, nao quero isso". Recusar
    ensinaria a apagar a variavel em vez de responder."""
    dom.exigir_verificacao_ligada(["--acao", "status"], {"ADSPOWER_NO_AUTH": "0"})


# ── 3. Allowlist de acao: o checkpoint tem NOME ─────────────────────────────


@pytest.mark.parametrize("acao", sorted(dom.ACOES_QUE_EXIGEM_CHECKPOINT))
def test_acao_mutante_e_recusada_pelo_nome_e_nao_como_desconhecida(acao):
    """"acao desconhecida" faria o proximo supor erro de digitacao e tentar de
    novo. "esta acao exige checkpoint" diz o que falta e a quem pedir."""
    with pytest.raises(dom.BrokerRecusado) as erro:
        dom.exigir_acao(acao)
    assert erro.value.estado == "blocked/exige_checkpoint"
    assert "checkpoint" in str(erro.value)


def test_nenhuma_acao_publicada_nesta_versao_muta():
    """A promessa da missao, provada em vez de prometida: esta versao SO
    pergunta. Se alguem publicar uma acao mutante no catalogo, este teste cai
    antes de o codigo chegar ao host do AdsPower."""
    assert [a.nome for a in dom.ACOES.values() if a.muta] == []


def test_acao_inexistente_e_recusada_sem_estado_de_checkpoint():
    with pytest.raises(dom.BrokerRecusado) as erro:
        dom.exigir_acao("voar")
    assert erro.value.estado == "falha/preflight"


def test_o_transporte_recusa_acao_mutante_mesmo_fora_do_catalogo():
    """Cinto e suspensorio. O catalogo e uma lista, e listas ganham linha nova;
    a camada que abre o socket e a ultima que pode dizer nao."""
    inventada = dom.Acao(nome="abrir_perfil", metodo="GET", caminho="/api/v1/browser/start",
                         muta=True, exige_perfil=True, parametros=("user_id",),
                         descricao="nao deveria passar")
    with pytest.raises(dom.BrokerRecusado) as erro:
        rodar(ClienteLocalApi(ENDERECO).chamar(
            inventada, {"user_id": "k11abc"}, dom.Segredo("x"), 1.0))
    assert erro.value.estado == "blocked/exige_checkpoint"


# ── 4. Allowlist de perfil e de parametro ───────────────────────────────────


def test_sem_allowlist_o_broker_nao_age():
    """Um broker que aceita qualquer perfil e um broker que qualquer processo
    local pode usar para tocar qualquer sessao."""
    with pytest.raises(dom.BrokerRecusado):
        dom.exigir_perfil("k11abc", [])


def test_perfil_fora_da_allowlist_e_recusado_sem_listar_os_de_dentro():
    with pytest.raises(dom.BrokerRecusado) as erro:
        dom.exigir_perfil("k99zzz", ["k11abc", "k22def"])
    # Quem nao esta na allowlist tambem nao precisa saber quem esta.
    assert "k11abc" not in str(erro.value)


def test_parametro_fora_do_contrato_da_acao_e_recusado_e_nao_ignorado():
    """Ignorar em silencio e como `extra="forbid"` existe no Cofre: quem mandou
    acha que pegou."""
    with pytest.raises(dom.BrokerRecusado):
        dom.exigir_parametros(dom.ACOES["inventario_perfis"], {"cookie": "abc"})


@pytest.mark.parametrize("valor", ["1 OR 1=1", "../../etc/passwd", "a" * 200, ""])
def test_valor_de_parametro_com_forma_estranha_e_recusado(valor):
    with pytest.raises(dom.BrokerRecusado):
        dom.exigir_parametros(dom.ACOES["inventario_perfis"], {"page": valor})


def test_a_acao_sem_perfil_recusa_um_perfil_enviado_por_engano():
    porta = PortaDuble()
    with pytest.raises(dom.BrokerRecusado):
        rodar(montar(porta).executar(Pedido(
            acao="status", perfil="k11abc", chave_idempotencia="status-0001")))
    assert porta.chamadas == []


# ── 5. Timeout ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("valor", [0, -1, 0.1, 3600, "muito"])
def test_timeout_fora_da_faixa_e_recusado(valor):
    with pytest.raises(dom.BrokerRecusado):
        dom.exigir_timeout(valor)


def test_sem_timeout_o_padrao_e_finito():
    """Sem limite superior, um sidecar travado vira um job travado."""
    assert 0 < dom.exigir_timeout(None) <= dom.TIMEOUT_MAXIMO_S


# ── 6. A FRONTEIRA DO SEGREDO ───────────────────────────────────────────────


@pytest.mark.parametrize("caminho", ["repr", "str", "format", "porcento"])
def test_o_segredo_nao_vira_texto_por_nenhum_caminho(caminho):
    s = dom.Segredo(CHAVE)
    saida = {"repr": repr(s), "str": str(s), "format": f"{s}", "porcento": "%s" % (s,)}[caminho]
    assert CHAVE not in saida
    assert saida == "<segredo omitido>"


@pytest.mark.parametrize("ato,nome", [
    (lambda s: json.dumps({"x": s}), "json"),
    (lambda s: copy.deepcopy(s), "deepcopy"),
    (lambda s: copy.copy(s), "copy"),
    (lambda s: pickle.dumps(s), "pickle"),
    (lambda s: len(s), "len"),
])
def test_o_segredo_recusa_serializacao_copia_e_medida(ato, nome):
    """`len` esta na lista porque comprimento vaza entropia: ele estreita o
    espaco de busca de quem procura a chave. E a mesma recusa que o smoke do
    1Password ja faz."""
    with pytest.raises(TypeError):
        ato(dom.Segredo(CHAVE))


def test_o_segredo_sai_por_uma_porta_so():
    s = dom.Segredo(CHAVE)
    assert s.revelar() == CHAVE


def test_o_segredo_nao_vira_texto_no_caminho_ate_a_porta():
    porta = PortaDuble()
    rodar(montar(porta).executar(Pedido(acao="status", chave_idempotencia="status-0002")))
    assert porta.bearer_como_texto == ["<segredo omitido>"]


# ── 7. FAIL CLOSED: trancar o 1Password interrompe o acesso ─────────────────


def test_sem_a_variavel_o_broker_para_antes_da_rede():
    porta = PortaDuble()
    with pytest.raises(dom.AcessoIndisponivel) as erro:
        rodar(montar(porta, valor=None).executar(
            Pedido(acao="status", chave_idempotencia="revogacao-0001")))
    assert erro.value.estado == "blocked/segredo_ausente"
    assert porta.chamadas == [], "chamou a Local API sem Bearer ativo"


def test_com_o_cofre_trancado_a_variavel_chega_com_a_REFERENCIA_e_o_broker_para():
    """Este e o comportamento real do `op run` com o 1Password trancado: a
    variavel chega com o `op://` literal, nao com o valor. Um broker que a
    mandasse como Bearer publicaria o endereco do item no log de acesso do
    AdsPower — o unico lugar onde ele nunca deveria estar."""
    porta = PortaDuble()
    with pytest.raises(dom.AcessoIndisponivel) as erro:
        rodar(montar(porta, valor="op://VOLC/AdsPower/credential").executar(
            Pedido(acao="status", chave_idempotencia="revogacao-0002")))
    assert erro.value.estado == "blocked/segredo_nao_resolvido"
    assert porta.chamadas == []
    # E a recusa NAO repete a referencia recebida.
    assert "op://VOLC" not in str(erro.value)


def test_valor_de_exemplo_nao_passa_por_chave():
    with pytest.raises(dom.BrokerRecusado):
        dom.exigir_bearer("changeme", nome_da_variavel="X")


def test_a_fonte_do_ambiente_le_a_variavel_certa_e_nao_o_processo_inteiro():
    fonte = SegredoDoAmbiente({VARIAVEL_DO_BEARER: CHAVE})
    assert fonte.bearer().revelar() == CHAVE
    assert SegredoDoAmbiente({}).referencia_declarada() is None
    with pytest.raises(dom.AcessoIndisponivel):
        SegredoDoAmbiente({}).bearer()


def test_o_segredo_pede_a_chave_DEPOIS_de_validar_o_pedido():
    """Pedir a chave antes de saber se o pedido e legitimo faz o 1Password
    mostrar um prompt de aprovacao para uma acao que ia ser recusada de qualquer
    jeito — e um prompt sem motivo ensina quem opera a aprovar sem ler."""
    class FonteQueConta(FonteDuble):
        def __init__(self):
            super().__init__(CHAVE)
            self.pedidos = 0

        def bearer(self):
            self.pedidos += 1
            return super().bearer()

    fonte = FonteQueConta()
    broker = Broker(endereco=ENDERECO, perfis_permitidos=("k11abc",),
                    fonte=fonte, porta=PortaDuble())
    with pytest.raises(dom.BrokerRecusado):
        rodar(broker.executar(Pedido(acao="voar", chave_idempotencia="ordem-0001")))
    assert fonte.pedidos == 0


# ── 8. PROJECAO: a conta que o perfil autentica nao e copiada ───────────────


@pytest.mark.parametrize("proibido", [
    "Tr0ub4dor&3",          # senha da conta
    "JBSWY3DPEHPK3PXP",     # chave de 2FA
    "c_user",               # cookie de sessao
    "conta@exemplo.com",    # usuario
    "luminati",             # provedor do proxy
    "1.2.3.4",              # host do proxy
    "proxy_password",
    "senha antiga",         # `remark` e campo livre, e fica FORA da projecao
])
def test_a_conta_guardada_no_perfil_nao_sobrevive_a_projecao(proibido):
    """O `user/list` do AdsPower devolve o perfil inteiro, e o perfil guarda a
    conta que ele autentica. Uma sanitizacao por REMOCAO copiaria todo campo
    novo que o AdsPower adicionasse; a projecao copia so o que foi nomeado."""
    projetado = dom.projetar_resposta(dom.ACOES["inventario_perfis"], RESPOSTA_DE_PERFIS)
    assert proibido not in json.dumps(projetado, ensure_ascii=False)


def test_a_projecao_preserva_a_identidade_que_o_inventario_precisa():
    projetado = dom.projetar_resposta(dom.ACOES["inventario_perfis"], RESPOSTA_DE_PERFIS)
    perfil = projetado["perfis"][0]
    assert perfil["user_id"] == "k11abc"
    assert perfil["name"] == "Piloto organico"
    assert perfil["domain_name"] == "facebook.com"
    # Booleano, nunca a configuracao: host, porta, usuario e senha do proxy sao
    # exatamente o que o ADR mantem fora do Cofre e do recibo.
    assert perfil["tem_proxy"] is True
    assert set(perfil) == set(dom.CAMPOS_DE_PERFIL) | {"tem_proxy"}


def test_um_campo_novo_do_adspower_nao_entra_sozinho():
    bruto = copy.deepcopy(RESPOSTA_DE_PERFIS)
    bruto["data"]["list"][0]["campo_que_o_adspower_adicionou"] = "sk-abcdefghij0123456789"
    projetado = dom.projetar_resposta(dom.ACOES["inventario_perfis"], bruto)
    assert "campo_que_o_adspower_adicionou" not in projetado["perfis"][0]
    assert "sk-abcdefghij" not in json.dumps(projetado)


def test_material_de_credencial_colado_no_nome_do_perfil_e_redigido():
    """Recusar o inventario inteiro por causa de um nome mal escolhido seria
    pior do que redigir: o operador perderia a unica lista que ele tem."""
    bruto = copy.deepcopy(RESPOSTA_DE_PERFIS)
    bruto["data"]["list"][0]["name"] = "perfil op://VOLC/Item/campo do piloto"
    projetado = dom.projetar_resposta(dom.ACOES["inventario_perfis"], bruto)
    assert "op://" not in json.dumps(projetado)
    assert "perfil" in projetado["perfis"][0]["name"]


def test_estado_desconhecido_de_perfil_nao_e_fechado():
    """A Local API responde "Active"/"Inactive". Qualquer outra coisa e ausencia
    de resposta, e achatar ausencia em "fechado" e como o QA visual conclui que
    o perfil esta livre e abre um segundo navegador sobre a mesma sessao."""
    def aberto(dados):
        return dom.projetar_resposta(dom.ACOES["estado_do_perfil"], dados)["aberto"]

    assert aberto({"code": 0, "data": {"status": "Active"}}) is True
    assert aberto({"code": 0, "data": {"status": "Inactive"}}) is False
    assert aberto({"code": 0, "data": {}}) is None
    assert aberto({"code": 0, "data": {"status": "Vixe"}}) is None


@pytest.mark.parametrize("bruto", ["texto", None, ["lista"], 7])
def test_resposta_em_forma_inesperada_e_indisponibilidade_e_nao_lista_vazia(bruto):
    with pytest.raises(dom.AcessoIndisponivel):
        dom.projetar_resposta(dom.ACOES["inventario_perfis"], bruto)


def test_lista_de_perfis_com_elemento_estranho_nao_vira_lista_curta():
    """O mesmo defeito que o Cofre ja mediu em 01/09/2026: descartar o que nao
    se entende produz um vazio que parece verdade."""
    with pytest.raises(dom.AcessoIndisponivel):
        dom.projetar_resposta(dom.ACOES["inventario_perfis"],
                              {"code": 0, "data": {"list": [None]}})


# ── 9. O recibo ─────────────────────────────────────────────────────────────


def test_o_recibo_traz_postura_do_bearer_e_nunca_o_valor():
    recibo = rodar(montar(PortaDuble(RESPOSTA_DE_PERFIS),
                          referencia="op://VOLC/AdsPower/credential").executar(
        Pedido(acao="inventario_perfis", chave_idempotencia="inventario-0001")))
    texto = json.dumps(recibo, ensure_ascii=False, default=str)
    assert CHAVE not in texto
    assert "op://" not in texto
    assert recibo["bearer"]["presente"] is True
    assert recibo["bearer"]["nome_da_variavel"] == VARIAVEL_DO_BEARER
    assert "valor" not in recibo["bearer"]


def test_o_recibo_registra_a_FORMA_da_referencia_e_nao_os_segmentos():
    """Digest de LOCALIZADOR, nao de segredo: ele correlaciona duas execucoes
    sem abrir caminho para adivinhar valor nenhum. Cofre, item e campo nao
    saem daqui — e a mesma disciplina do smoke do 1Password."""
    recibo = rodar(montar(PortaDuble(),
                          referencia="op://VOLC/AdsPower/credential").executar(
        Pedido(acao="status", chave_idempotencia="status-0003")))
    forma = recibo["referencia"]
    assert forma["presente"] is True and forma["segmentos"] == 3
    assert len(forma["digest"]) == 16
    for segmento in ("VOLC", "AdsPower", "credential"):
        assert segmento not in json.dumps(forma)


def test_a_peneira_final_derruba_um_recibo_com_material_de_credencial():
    with pytest.raises(dom.BrokerRecusado) as erro:
        dom.recusar_vazamento({"nota": "op://VOLC/Item/campo"})
    assert erro.value.estado == "falha/vazamento"


def test_a_peneira_final_derruba_um_recibo_com_chave_proibida():
    """E ela levanta o vocabulario do BROKER, nao o do Cofre.

    Reaproveitar a regra sem traduzir o erro faria `PayloadRecusado` subir por
    um `except` que so conhece `BrokerRecusado` — e um vazamento viraria
    traceback em vez de recibo.
    """
    with pytest.raises(dom.BrokerRecusado) as erro:
        dom.recusar_vazamento({"ok": True, "cookie": "abc"})
    assert erro.value.estado == "falha/vazamento"


def test_o_recibo_diz_como_virar_verificacao_no_cofre():
    """O recibo do broker vira verificacao no Cofre. Dizer isso no proprio
    recibo evita que alguem invente um alvo diferente e a trilha fique
    ilegivel."""
    recibo = rodar(montar(PortaDuble()).executar(
        Pedido(acao="status", chave_idempotencia="status-0004")))
    assert recibo["vira_verificacao_como"]["alvo"] == "credencial"
    assert "verificacoes" in recibo["vira_verificacao_como"]["rota"]


# ── 10. Idempotencia ────────────────────────────────────────────────────────


def test_replay_e_visivel_e_nao_uma_segunda_observacao():
    registro = Registro()
    broker = montar(PortaDuble(), registro=registro)
    primeiro = rodar(broker.executar(Pedido(acao="status", chave_idempotencia="ritmo-0001")))
    segundo = rodar(broker.executar(Pedido(acao="status", chave_idempotencia="ritmo-0001")))
    assert primeiro["idempotente"] is False
    assert segundo["idempotente"] is True
    assert primeiro["run_id"] == segundo["run_id"]


def test_mesma_chave_com_entrada_diferente_e_conflito_e_nao_operacao_nova():
    """Mesma semantica do Cofre. Reusar a chave com outra entrada esconderia
    duas operacoes numa so."""
    registro = Registro()
    broker = montar(PortaDuble(RESPOSTA_DE_PERFIS), registro=registro)
    rodar(broker.executar(Pedido(acao="status", chave_idempotencia="ritmo-0002")))
    with pytest.raises(dom.BrokerRecusado) as erro:
        rodar(broker.executar(Pedido(acao="inventario_perfis",
                                     chave_idempotencia="ritmo-0002")))
    assert erro.value.estado == "falha/conflito_de_idempotencia"
    assert "ritmo-0002" not in str(erro.value), "a frase de conflito carrega a chave"


def test_a_chave_do_broker_usa_a_MESMA_gramatica_do_cofre():
    """Duas gramaticas para a mesma ideia produzem uma chave que o broker
    aceita e o Cofre recusa — e o recibo do broker precisa virar verificacao
    no Cofre."""
    from app.asset_vault import dominio as cofre_dom
    for boa in ("inventario-2026-09-02-01", "status.0001:a"):
        assert dom.exigir_chave_de_idempotencia(boa) == cofre_dom.exigir_chave_de_idempotencia(boa)
    for ruim in ("curta", "", "chave com espaco"):
        # E a recusa sai como `BrokerRecusado`: quem chama o broker nao conhece
        # `PayloadRecusado`, e a chave malformada e a recusa mais comum do CLI.
        with pytest.raises(dom.BrokerRecusado):
            dom.exigir_chave_de_idempotencia(ruim)


def test_a_impressao_digital_deriva_do_conteudo_e_nao_do_relogio():
    a = dom.impressao_digital("status", None, {}, ENDERECO)
    b = dom.impressao_digital("status", None, {}, ENDERECO)
    c = dom.impressao_digital("status", None, {"page": "2"}, ENDERECO)
    assert a == b and a != c


# ── 11. Indisponibilidade nao vira inventario vazio ─────────────────────────


def test_local_api_fora_do_ar_nao_vira_zero_perfis():
    """Um broker que responde "nenhum perfil" porque o AdsPower esta fechado
    afirma um inventario vazio com a mesma cara com que afirmaria trinta."""
    caido = PortaDuble(erro=dom.AcessoIndisponivel(
        "sem Local API", estado="blocked/local_api_ausente"))
    recibo = rodar(montar(caido).executar(
        Pedido(acao="inventario_perfis", chave_idempotencia="caido-0001")))
    assert recibo["estado"] == "blocked/local_api_ausente"
    assert "perfis" not in recibo["resultado"]
    assert recibo["codigo_de_saida"] == dom.ESTADOS["blocked/local_api_ausente"]


def test_cada_estado_tem_codigo_de_saida_proprio():
    """Um runner externo precisa distinguir "nao deu para tentar" de "tentou e
    vazou" sem parsear texto."""
    codigos = list(dom.ESTADOS.values())
    assert len(codigos) == len(set(codigos))
    assert dom.ESTADOS["ok"] == 0
    assert all(c > 0 for e, c in dom.ESTADOS.items() if e != "ok")


# ── 12. A linha de comando ──────────────────────────────────────────────────


def test_o_autoteste_do_cli_passa_sem_rede_sem_adspower_e_sem_1password():
    """A prova que roda em qualquer maquina — inclusive nesta, que nao tem
    AdsPower nem 1Password instalados."""
    assert cli.autoteste() == 0


def test_o_preflight_nao_faz_rede_e_reporta_presenca_sem_revelar(capsys, monkeypatch):
    """Presenca, nunca valor: um booleano nao vaza nem entropia."""
    monkeypatch.setenv(VARIAVEL_DO_BEARER, CHAVE)
    codigo = cli.principal([
        "--preflight", "--endereco", ENDERECO, "--perfis-permitidos", "k11abc"])
    saida = capsys.readouterr().out
    assert codigo == 0
    corpo = json.loads(saida)
    assert corpo["preflight"]["faz_rede"] is False
    assert corpo["preflight"]["bearer_presente_no_ambiente"] is True
    assert CHAVE not in saida
    assert corpo["preflight"]["acoes_que_exigem_checkpoint"] == sorted(
        dom.ACOES_QUE_EXIGEM_CHECKPOINT)


def test_o_cli_recusa_endereco_externo_com_recibo_e_codigo_proprio(capsys):
    codigo = cli.principal(["--acao", "status", "--endereco", "http://10.0.0.5:50325",
                            "--chave-idempotencia", "status-0009"])
    corpo = json.loads(capsys.readouterr().out)
    assert codigo == dom.ESTADOS["falha/preflight"]
    assert corpo["estado"] == "falha/preflight"


def test_o_cli_recusa_abrir_perfil_com_o_codigo_de_checkpoint(capsys):
    """A recusa mais importante desta versao: abrir navegador exige uma
    autorizacao que ainda nao foi concedida."""
    codigo = cli.principal(["--acao", "abrir_perfil", "--perfil", "k11abc",
                            "--perfis-permitidos", "k11abc",
                            "--chave-idempotencia", "abertura-0001"])
    corpo = json.loads(capsys.readouterr().out)
    assert codigo == dom.ESTADOS["blocked/exige_checkpoint"]
    assert corpo["estado"] == "blocked/exige_checkpoint"


def test_uma_recusa_tambem_deixa_recibo(capsys):
    """Sair com um `print` no stderr faria a recusa ser o unico ato do broker
    sem trilha — justamente o ato que mais interessa a quem audita."""
    cli.principal(["--acao", "status", "--chave-idempotencia", "x"])
    corpo = json.loads(capsys.readouterr().out)
    assert corpo["ferramenta"] == "cofre-broker-adspower"
    assert corpo["tarefa"] == "P03-T11"
    assert corpo["motivo"]
