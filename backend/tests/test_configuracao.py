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

# Os prompts que o motor tem HOJE (30/09/2026). Era "os onze" até 17–18/09,
# quando entraram `editorial_identity`, `image_review`, `interior_editorial` e
# `reader_contract` — e o número fixo virou falha sem dizer o que mudou.
# Conjunto e não contagem: um prompt que SOME daqui é um prompt que a tela
# deixou de mostrar (ou que o motor perdeu); um que APARECE é pego pelo teste
# de dono logo abaixo, com o nome dele na mensagem.
PROMPTS_DE_HOJE = {
    "blocks_gutenberg.jinja", "declarador_engajamento.jinja", "editorial_identity.jinja",
    "extractor.jinja", "image_prompt.jinja", "image_prompt_lp.jinja", "image_review.jinja",
    "interior_editorial.jinja", "judge.jinja", "reader_contract.jinja", "redator_p1.jinja",
    "redator_pages.jinja", "redator_presell.jinja", "redator_widget.jinja", "seo.jinja",
    # fluxo editorial v2 (30/09/2026) — reconciliado na B8: os previstos pelo
    # contrato entre trilhas (`briefing`, `revisor`) existem, com os 9 `*_v2`
    "briefing.jinja", "revisor.jinja", "blocks_gutenberg_v2.jinja",
    "image_prompt_lp_v2.jinja", "image_prompt_v2.jinja", "interior_editorial_v2.jinja",
    "reader_contract_v2.jinja", "redator_p1_v2.jinja", "redator_pages_v2.jinja",
    "redator_presell_v2.jinja", "seo_v2.jinja",
}


def test_todo_prompt_do_motor_aparece_com_conteudo(lido: dict):
    nomes = {p["arquivo"] for p in lido["prompts"]}
    no_disco = {p.name for p in (MOTOR / "src" / "funnelforge" / "prompts").glob("*.jinja")}
    assert nomes == no_disco, "a tela lista prompts diferentes dos que o motor tem"
    sumiram = sorted(PROMPTS_DE_HOJE - nomes)
    assert sumiram == [], f"prompt sumiu da tela (ou do motor): {sumiram}"
    for p in lido["prompts"]:
        assert p["conteudo"].strip()
        assert p["linhas"] > 5


def test_todo_prompt_diz_que_parte_do_funil_governa(lido: dict):
    """Sem isso, `redator_p1.jinja` não responde "se eu mexer aqui, o que
    muda?" — e a resposta (a landing page) não é adivinhável pelo nome."""
    sem_rotulo = [p["arquivo"] for p in lido["prompts"] if not p["usado_por"]]
    assert sem_rotulo == [], f"prompt sem dono declarado: {sem_rotulo}"


def test_os_prompts_novos_e_os_previstos_tem_dono():
    """Independe do disco: os quatro de 17–18/09 e os dois que a trilha do motor
    vai criar já nascem com dono — o teste acima não pode ficar vermelho no
    minuto em que `briefing.jinja` aparecer."""
    novos = ("editorial_identity.jinja", "image_review.jinja",
             "interior_editorial.jinja", "reader_contract.jinja",
             # fluxo editorial v2 (B8): o dono de cada um diz que só roda no v2
             "briefing.jinja", "revisor.jinja", "blocks_gutenberg_v2.jinja",
             "image_prompt_lp_v2.jinja", "image_prompt_v2.jinja",
             "interior_editorial_v2.jinja", "reader_contract_v2.jinja",
             "redator_p1_v2.jinja", "redator_pages_v2.jinja", "redator_presell_v2.jinja",
             "seo_v2.jinja")
    for nome in novos:
        assert cfg.QUEM_USA_O_PROMPT.get(nome), f"{nome} sem dono declarado"
        if nome.endswith("_v2.jinja") or nome in ("briefing.jinja", "revisor.jinja"):
            assert "v2" in cfg.QUEM_USA_O_PROMPT[nome], nome


def test_nenhum_dono_declarado_para_prompt_que_nao_existe(lido: dict):
    """O registro não pode acumular rótulo de arquivo que ninguém tem: todo dono
    declarado corresponde a um prompt no disco."""
    no_disco = {p["arquivo"] for p in lido["prompts"]}
    fantasmas = set(cfg.QUEM_USA_O_PROMPT) - no_disco
    assert fantasmas == set(), f"dono declarado para prompt inexistente: {sorted(fantasmas)}"


def test_o_extractor_e_declarado_como_legado():
    """O disparo do VOLC O.S. roda `run-volc`, que chega com o plano pronto: o
    `extractor.jinja` só roda no comando legado `run`. A tela dizia que ele
    fazia "a leitura do briefing e o plano do funil" — e quem lia acreditava
    que mexer nele mudava os funis de hoje."""
    rotulo = cfg.QUEM_USA_O_PROMPT["extractor.jinja"]
    assert "legado" in rotulo.lower()
    assert "run-volc" in rotulo


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
