"""O dominio, e a prova de que ele nao divergiu da migration.

## O teste mais importante deste arquivo nao testa comportamento

`test_o_vocabulario_do_python_e_o_do_banco` LE a v14_01 e compara as listas. Uma
divergencia entre `dominio.ESTADOS` e o CHECK do banco nao quebra nenhum teste
de comportamento — ela produz, em producao, um 400 que ninguem entende: o Python
aceita o valor, o Postgres recusa, e a mensagem fala de constraint. O mesmo
dispositivo ja existe em `test_cofre_ativos.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.publicacao_organica import dominio as dom

RAIZ = Path(__file__).resolve().parents[2]
MIGRACAO = RAIZ / "supabase" / "migrations" / "v14_01_publicacao_organica.sql"


def _valores_do_check(sql: str, constraint: str) -> set[str]:
    """Extrai a lista literal de um `CHECK (coluna IN ('a','b',...))`."""
    trecho = sql[sql.index(constraint):]
    trecho = trecho[: trecho.index("))") + 2]
    return set(re.findall(r"'([a-zA-Z_]+)'", trecho))


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRACAO.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Anti-deriva
# ---------------------------------------------------------------------------


def test_o_vocabulario_do_python_e_o_do_banco(sql: str) -> None:
    assert _valores_do_check(sql, "publicacao_organica_job_estado_valido") == set(dom.ESTADOS)
    assert _valores_do_check(sql, "publicacao_organica_job_modo_valido") == set(dom.MODOS)
    assert _valores_do_check(sql, "publicacao_organica_recibo_estado_valido") == set(dom.ESTADOS_EXTERNOS)
    assert _valores_do_check(sql, "publicacao_organica_destino_plataforma_valida") == set(dom.PLATAFORMAS)
    assert _valores_do_check(sql, "publicacao_organica_destino_provedor_valido") == set(dom.PROVEDORES)


def test_todo_estado_tem_leitura_e_nenhum_incerto_e_verde() -> None:
    for estado in dom.ESTADOS:
        leitura = dom.leitura_do_estado(estado)
        assert leitura.rotulo, estado
        assert leitura.proxima_acao, estado
        assert leitura.tom in {"neutro", "aguardando", "atencao", "sucesso", "falha"}

    # ⚠️ A REGRA QUE A MISSAO PEDE POR ESCRITO: nada de verde para parcial ou
    # desconhecido. `reconciliado` e o UNICO `sucesso` — porque e o unico estado
    # que exige referencia externa, URL e instante para existir.
    verdes = [e for e in dom.ESTADOS if dom.tom_de(e) == "sucesso"]
    assert verdes == ["reconciliado"], verdes
    for incerto in dom.ESTADOS_INCERTOS:
        assert dom.tom_de(incerto) != "sucesso"


def test_estado_desconhecido_nunca_vira_sucesso() -> None:
    # Um estado que o banco ganhe amanha e a tela ainda nao conheca precisa cair
    # em `atencao`. Um `else: sucesso` otimista faria a tela pintar de verde um
    # estado que ninguem sabe o que significa.
    leitura = dom.leitura_do_estado("um_estado_que_nao_existe")
    assert leitura.tom == "atencao"
    assert "Nao trate como publicado" in leitura.proxima_acao


def test_a_forma_da_chave_do_python_e_a_do_banco(sql: str) -> None:
    assert "^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$" in sql
    assert dom.forma_de_chave_valida("pub-" + "a" * 40)
    assert not dom.forma_de_chave_valida("curta")
    assert not dom.forma_de_chave_valida("com espaco no meio aqui")


# ---------------------------------------------------------------------------
# Chave de idempotencia
# ---------------------------------------------------------------------------


def _pedido(**troca):
    base = dict(
        peca_id="11111111-1111-1111-1111-1111111111aa", peca_versao=1,
        autorizacao_id="11111111-1111-1111-1111-1111111111bb",
        destino_id="11111111-1111-1111-1111-1111111111cc",
        modo="draft", timezone="America/Sao_Paulo", horario_local=None,
        corpo={"texto": "oi"}, consentimento_agora=False,
    )
    base.update(troca)
    return dom.montar_pedido(**base)


def test_a_chave_e_derivada_do_conteudo_e_nao_sorteada() -> None:
    a, b = _pedido(), _pedido()
    assert dom.chave_de_idempotencia(a) == dom.chave_de_idempotencia(b)
    # Ordem de chaves no corpo nao muda o digest: um retry que remonte o dict em
    # outra ordem tem de cair no MESMO replay.
    fora_de_ordem = _pedido(corpo={"z": 1, "texto": "oi"})
    na_ordem = _pedido(corpo={"texto": "oi", "z": 1})
    assert dom.chave_de_idempotencia(fora_de_ordem) == dom.chave_de_idempotencia(na_ordem)


def test_mudar_o_texto_muda_a_chave() -> None:
    assert dom.chave_de_idempotencia(_pedido()) != dom.chave_de_idempotencia(
        _pedido(corpo={"texto": "outro"}))


def test_mudar_o_destino_ou_o_horario_muda_a_chave() -> None:
    base = dom.chave_de_idempotencia(_pedido())
    outro_destino = dom.chave_de_idempotencia(
        _pedido(destino_id="11111111-1111-1111-1111-1111111111dd"))
    agendado = dom.chave_de_idempotencia(
        _pedido(modo="schedule", horario_local="2099-01-02 10:00"))
    assert len({base, outro_destino, agendado}) == 3


# ---------------------------------------------------------------------------
# `now` sem consentimento — contraprova J na camada de dominio
# ---------------------------------------------------------------------------


def test_now_sem_consentimento_e_recusado_antes_do_banco() -> None:
    with pytest.raises(dom.PedidoRecusado) as erro:
        _pedido(modo="now")
    assert erro.value.codigo == "consentimento_ausente"


def test_consentimento_sem_now_tambem_e_recusado() -> None:
    # Marcar "publicar agora" e escolher `draft` e contradicao. Aceitar em
    # silencio deixaria a caixa marcada num job que nao publica — e a proxima
    # pessoa acharia que ela nao faz nada.
    with pytest.raises(dom.PedidoRecusado) as erro:
        _pedido(modo="draft", consentimento_agora=True)
    assert erro.value.codigo == "consentimento_sem_now"


def test_now_com_consentimento_passa_no_dominio() -> None:
    pedido = _pedido(modo="now", consentimento_agora=True)
    assert pedido.como_payload()["consentimento_agora"] is True


# ---------------------------------------------------------------------------
# Timezone e horario — contraprova K na camada de dominio
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("zona", ["America/Nao_Existe", "", "UTC+3", "Sao Paulo"])
def test_timezone_invalido_e_recusado(zona: str) -> None:
    with pytest.raises(dom.PedidoRecusado):
        dom.validar_timezone(zona)


@pytest.mark.parametrize("zona", ["America/Sao_Paulo", "UTC", "Europe/Lisbon"])
def test_timezone_valido_passa(zona: str) -> None:
    assert dom.validar_timezone(zona) == zona


@pytest.mark.parametrize("texto", [
    "2099-13-01 10:00",       # mes 13
    "2099-02-30 10:00",       # dia que nao existe
    "2099-01-01 10:00-03:00",  # offset no texto: o fuso e o outro campo
    "amanha as 10",
    "2099-01-01",
])
def test_horario_local_malformado_e_recusado(texto: str) -> None:
    with pytest.raises(dom.PedidoRecusado):
        dom.validar_horario_local(texto)


def test_horario_local_normaliza_para_segundos() -> None:
    assert dom.validar_horario_local("2099-07-15 09:30") == "2099-07-15 09:30:00"
    assert dom.validar_horario_local("2099-07-15T09:30:45") == "2099-07-15 09:30:45"


def test_schedule_sem_horario_e_recusado() -> None:
    with pytest.raises(dom.PedidoRecusado) as erro:
        _pedido(modo="schedule")
    assert erro.value.codigo == "horario_ausente"


def test_draft_com_horario_e_recusado() -> None:
    # Um horario num draft e uma promessa que ninguem cumpre: o control plane
    # nao vai agendar nada, e a tela mostraria uma hora que nao significa nada.
    with pytest.raises(dom.PedidoRecusado) as erro:
        _pedido(modo="draft", horario_local="2099-01-01 10:00")
    assert erro.value.codigo == "horario_inesperado"


# ---------------------------------------------------------------------------
# Sanitizacao — contraprova H na camada de dominio
# ---------------------------------------------------------------------------


#: ⚠️ MONTADOS EM PARTES, e isso nao e driblar o scanner. Um literal com forma
#: de credencial neste arquivo reprovaria `scripts/verificar_segredos.py`, e a
#: saida seria enfraquecer o scanner para acomodar o teste. Montar em partes
#: mantem os dois honestos: nao ha string com forma de credencial no arquivo, e
#: o valor testado em tempo de execucao e exatamente o que se quer redigir.
_SEGREDOS_SINTETICOS = (
    "xox" + "b-0123456789abcdefghij",
    "s" + "k-0123456789abcdefghij",
    "po" + "s_0123456789abcdefghij",
    "ey" + "JhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc",
    "op:" + "//VOLC/Pagina/credential",
)


@pytest.mark.parametrize("segredo", _SEGREDOS_SINTETICOS)
def test_o_erro_sanitizado_nao_carrega_o_segredo(segredo: str) -> None:
    bruto = f"o control plane recusou (400): {{'echo': {{'Authorization': '{segredo}'}}}}"
    limpo = dom.sanitizar_erro(bruto)
    assert segredo not in limpo
    # E ainda diz alguma coisa util: uma redacao que apaga tudo tambem apaga o
    # diagnostico, e ai o operador fica sem saber o que aconteceu.
    assert "400" in limpo


def test_o_erro_sanitizado_tem_teto() -> None:
    assert len(dom.sanitizar_erro("x" * 5000)) <= dom.LIMITE_DE_ERRO


def test_erro_vazio_vira_frase_e_nao_string_vazia() -> None:
    assert dom.sanitizar_erro(None) == "sem detalhe"
    assert dom.sanitizar_erro("   ") == "sem detalhe"


@pytest.mark.parametrize("chave", [
    "access_token", "accessToken", "ACCESS-TOKEN", "password", "senha",
    "Authorization", "cookie", "service_role_key", "localizador",
])
def test_chave_sensivel_no_recibo_e_recusada(chave: str) -> None:
    with pytest.raises(dom.PedidoRecusado) as erro:
        dom.recusar_chave_sensivel({"ok": 1, chave: "qualquer coisa"})
    assert erro.value.codigo == "campo_proibido"
    # ⚠️ A MENSAGEM CITA O CAMPO, NUNCA O VALOR.
    assert "qualquer coisa" not in str(erro.value)


def test_chave_sensivel_aninhada_e_dentro_de_array_tambem_e_recusada() -> None:
    with pytest.raises(dom.PedidoRecusado):
        dom.recusar_chave_sensivel({"resposta": [{"meta": {"apiKey": "x"}}]})


def test_corpo_do_pedido_com_chave_sensivel_e_recusado() -> None:
    with pytest.raises(dom.PedidoRecusado):
        _pedido(corpo={"texto": "oi", "password": "x"})
