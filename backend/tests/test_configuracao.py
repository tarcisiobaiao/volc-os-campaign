"""A configuração do motor, lida do código-fonte dele.

## Por que ler o TEXTO e não importar o módulo

O backend e o motor rodam em ambientes Python separados — venvs diferentes, e em
produção possivelmente máquinas diferentes. `import doctrine` nem sempre é
possível, e mesmo quando é, executaria o módulo inteiro (que compila expressões
regulares no import) só para ler sete listas de strings.

O preço disso é que a leitura vira regex sobre código, e regex sobre código
quebra em silêncio: uma tupla renomeada devolve `[]` sem erro nenhum, e a tela
mostra "0 itens" como se a lista estivesse vazia de propósito. Estes testes são
o alarme.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.redator import configuracao as cfg

MOTOR = Path(__file__).resolve().parents[2] / "funnelforge-migracao" / "engine"


@pytest.fixture(scope="module")
def lido() -> dict:
    if not (MOTOR / "config.yaml").is_file():
        pytest.skip(f"motor ausente em {MOTOR}")
    return cfg.ler(MOTOR)


# ── a doutrina ─────────────────────────────────────────────────────────────

def test_toda_lista_da_doutrina_tem_itens(lido: dict):
    """O alarme central: uma tupla renomeada no motor devolveria `[]` em
    silêncio, e a tela diria "0 itens" como se fosse intencional."""
    vazias = [d["nome"] for d in lido["doutrina"] if d["total"] == 0]
    assert vazias == [], f"o parser não achou: {vazias}"


def test_as_contagens_batem_com_o_motor(lido: dict):
    """Contagens medidas rodando o módulo do motor. Se ele ganhar ou perder um
    termo, este teste avisa — e alguém decide se a tela devia mesmo mudar."""
    por_nome = {d["nome"]: d["total"] for d in lido["doutrina"]}
    assert por_nome["BANNED_FEAR"] == 9
    assert por_nome["BANNED_OFFICIAL"] == 6
    assert por_nome["BANNED_CTA_FIRST_PERSON"] == 7
    assert por_nome["REQUIRED_COMPLIANCE_ANCHORS"] == 5
    assert por_nome["APPROVED_CTA_EXEMPLARS"] == 6


def test_os_termos_chegam_legiveis_e_nao_escapados(lido: dict):
    medo = next(d for d in lido["doutrina"] if d["nome"] == "BANNED_FEAR")
    assert "última chance" in medo["itens"]
    assert "vagas limitadas" in medo["itens"]
    # nada de aspas ou barras sobrando do parse
    for i in medo["itens"]:
        assert '"' not in i and "\\" not in i


def test_toda_lista_explica_o_que_governa(lido: dict):
    """Sete listas de strings sem o efeito escrito não dizem o que muda ao
    mexer em cada uma — e é justamente o efeito colateral que torna a edição
    perigosa."""
    for d in lido["doutrina"]:
        assert d["rotulo"] and d["efeito"]
        assert len(d["efeito"]) > 40


def test_o_aviso_de_conformidade_e_uma_frase_inteira(lido: dict):
    """Ele é montado por concatenação implícita de strings no fonte; juntar os
    pedaços com espaço é o que evita `…do funil.Este conteúdo…`."""
    aviso = lido["aviso_de_conformidade"]
    assert len(aviso) > 40
    assert '"' not in aviso


def test_parser_devolve_vazio_sem_estourar(tmp_path):
    """Motor ausente ou fonte irreconhecível: a tela ainda tem de abrir."""
    saida = cfg.ler(tmp_path)
    assert [d["total"] for d in saida["doutrina"]] == [0] * len(cfg.O_QUE_GOVERNA)
    assert saida["prompts"] == []
    assert saida["somente_leitura"] is True


def test_a_regex_nao_atravessa_para_a_tupla_seguinte(tmp_path):
    """⚠️ O modo mais provável de o parser mentir: `re.S` faz o `.` casar quebra
    de linha, então um fecha-parêntese não ancorado engoliria a próxima tupla e
    somaria os itens das duas. A âncora é `)` sozinho no fim da linha."""
    fonte = (
        'A: tuple[str, ...] = (\n    "um",\n    "dois",\n)\n\n'
        'B: tuple[str, ...] = (\n    "tres",\n)\n'
    )
    assert cfg._tupla_do_fonte(fonte, "A") == ["um", "dois"]
    assert cfg._tupla_do_fonte(fonte, "B") == ["tres"]


# ── prompts e modelos ──────────────────────────────────────────────────────

def test_os_onze_prompts_aparecem_com_conteudo(lido: dict):
    assert len(lido["prompts"]) == 11
    for p in lido["prompts"]:
        assert p["conteudo"].strip()
        assert p["linhas"] > 5


def test_todo_prompt_diz_que_parte_do_funil_governa(lido: dict):
    """Sem isso, `redator_p1.jinja` não responde "se eu mexer aqui, o que
    muda?" — e a resposta (a landing page) não é adivinhável pelo nome."""
    sem_rotulo = [p["arquivo"] for p in lido["prompts"] if not p["usado_por"]]
    assert sem_rotulo == [], f"prompt sem dono declarado: {sem_rotulo}"


def test_os_passos_trazem_modelo_e_temperatura(lido: dict):
    por_passo = {p["passo"]: p for p in lido["passos"]}
    assert "write_page" in por_passo and "judge" in por_passo
    assert por_passo["judge"]["temperatura"] == 0.0
    for p in lido["passos"]:
        assert p["modelo"]


def test_o_juiz_roda_noutro_provedor_que_o_redator(lido: dict):
    """Não é detalhe de configuração: um juiz do mesmo provedor herdaria os
    vícios de quem escreveu, e a avaliação deixaria de ser independente."""
    por_passo = {p["passo"]: p for p in lido["passos"]}
    familia = lambda m: m.split("/")[0].split("-")[0]  # noqa: E731
    assert familia(por_passo["judge"]["modelo"]) != familia(por_passo["write_page"]["modelo"])


def test_as_flags_da_corrida_chegam(lido: dict):
    c = lido["corrida"]
    for k in ("featured_image", "official_screenshots", "widgets_enabled", "publish_status"):
        assert k in c


def test_a_rota_declara_que_nao_grava(lido: dict):
    """Quem consumir esta resposta não deve assumir que existe um PUT em algum
    lugar. A decisão é declarada no payload, não só na tela."""
    assert lido["somente_leitura"] is True
    assert "histórico" in lido["por_que"]
