"""Provas do motor de widgets.

A prova central é `test_todo_arquetipo_passa_no_sanitizador`: ela roda o
`sanitize_widget_block` DE VERDADE sobre os quatro arquétipos renderizados. Era
essa checagem que, até 19/08/2026, só acontecia em produção — depois de a
chamada paga ter sido feita.

Rodar:
    funnelforge-migracao/engine/.venv/bin/python -m pytest \
        funnelforge-migracao/engine/tests/test_widgets.py -q
"""
from __future__ import annotations

import json
import re

import pytest

from funnelforge.pipeline.validators.checks import sanitize_widget_block
from funnelforge.widgets import ARQUETIPOS, WidgetInvalido, ler, renderizar, texto_visivel


def _cru(arquetipo: str = "diagnostico", **troca) -> str:
    """Um JSON válido mínimo, para as provas mexerem em um campo por vez."""
    base = {
        "arquetipo": arquetipo,
        "titulo": "O que travou o seu saque",
        "subtitulo": "Escolha o que aconteceu e veja a causa provável.",
        "controles": [{
            "id": "sintoma", "rotulo": "O que aconteceu quando você pediu?",
            "opcoes": [
                {"valor": "negado", "texto": "Negaram o meu pedido"},
                {"valor": "analise", "texto": "Está em análise há dias"},
            ],
        }],
        "cenarios": [
            {"quando": {"sintoma": "negado"}, "chip": "conta bloqueada", "tom": "risco",
             "titulo": "O sistema exige conta ativa", "corpo": "A conta indicada precisa "
             "estar ativa no seu nome.", "passos": ["Confira a conta no aplicativo",
                                                    "Refaça o pedido"]},
            {"quando": {"sintoma": "analise"}, "chip": "prazo normal", "tom": "atencao",
             "titulo": "A análise ainda está no prazo", "corpo": "Pedidos passam por "
             "conferência antes do crédito.", "passos": ["Acompanhe pelo aplicativo",
                                                         "Evite abrir outro pedido"]},
        ],
        "rodape": "Fonte: canais oficiais citados no texto.",
    }
    base.update(troca)
    return json.dumps(base, ensure_ascii=False)


# ── a prova que faltava: o sanitizador roda ANTES de produção ────────────────

@pytest.mark.parametrize("arquetipo", sorted(ARQUETIPOS))
def test_todo_arquetipo_passa_no_sanitizador(arquetipo):
    """Nenhum gabarito pode ser recusado pelas regras da casa.

    Antes isto dependia de o modelo lembrar de 116 linhas de instrução. A p3 da
    run 9 caiu aqui; a p3 da run #4 caiu por UM caractere `&`.
    """
    spec = ARQUETIPOS[arquetipo]
    controles = [{"id": f"c{i}", "rotulo": f"Pergunta {i}",
                  "opcoes": [{"valor": "a", "texto": "Alternativa A"},
                             {"valor": "b", "texto": "Alternativa B"}]}
                 for i in range(1, int(spec["max_controles"]) + 1)]  # type: ignore[call-overload]
    # ⚠️ Os dois cenários têm a MESMA silhueta de propósito: `_equilibrio`
    # recusa formas diferentes, porque é isso que produz o buraco branco.
    cenarios = [{"chip": "resultado", "tom": "ok", "titulo": "Título do cenário",
                 "corpo": "Explicação do primeiro cenário.", "padrao": True,
                 "listas": [{"rotulo": "prós", "itens": ["um", "dois"]}]},
                {"chip": "outro", "tom": "risco", "titulo": "Outro cenário",
                 "corpo": "Explicação do segundo cenário.",
                 "listas": [{"rotulo": "contras", "itens": ["três", "quatro"]}]}]
    bloco = renderizar(ler(_cru(arquetipo, controles=controles, cenarios=cenarios)))

    assert sanitize_widget_block(bloco) == [], f"{arquetipo} foi recusado"


def test_o_script_nao_tem_ampersand():
    """`&` no script é escapado pelo WordPress e quebra o JavaScript.

    Custou a p3 do run #4 inteira: US$ 0,79 de trabalho perdidos por um `&&`.
    """
    js = re.search(r"<script>(.*?)</script>", renderizar(ler(_cru())), re.S).group(1)
    assert "&" not in js
    assert ".style.display" not in js


def test_empilhamento_em_grid_e_visibility():
    bloco = renderizar(ler(_cru()))
    assert "grid-area:1/1" in bloco
    assert "visibility" in bloco


def test_um_style_e_um_script():
    bloco = renderizar(ler(_cru()))
    assert bloco.count("<style>") == 1 and bloco.count("<script>") == 1
    assert bloco.count("<!-- wp:html -->") == 1


def test_nao_usa_paragrafo():
    """`<p>` em bloco raw é recusado por `paragraph_in_raw_html`."""
    assert not re.search(r"<p[\s>]", renderizar(ler(_cru())))


# ── o widget-fantasma não passa mais ────────────────────────────────────────
#
# ⚠️ `widget_p5` da run 9 marcou OK num bloco de 354 caracteres que era uma
# `<ul>` com dois itens. O sanitizador não reclamou porque ele só sabe dizer o
# que é PROIBIDO — nunca o que é exigido.

def test_cenario_sem_conteudo_e_recusado():
    cru = _cru(cenarios=[{"chip": "a", "tom": "ok", "titulo": "Só o título"},
                         {"chip": "b", "tom": "ok", "titulo": "Outro"}])
    with pytest.raises(WidgetInvalido) as e:
        ler(cru)
    assert any("resultado em branco" in m for m in e.value.motivos)


def test_um_cenario_so_e_recusado():
    cru = _cru(cenarios=[{"chip": "a", "tom": "ok", "titulo": "T", "corpo": "C",
                          "padrao": True}])
    with pytest.raises(WidgetInvalido):
        ler(cru)


def test_controle_com_uma_opcao_e_recusado():
    cru = _cru(controles=[{"id": "s", "rotulo": "R",
                           "opcoes": [{"valor": "a", "texto": "única"}]}])
    with pytest.raises(WidgetInvalido) as e:
        ler(cru)
    assert any("mínimo é 2" in m for m in e.value.motivos)


# ── cobertura: ninguém responde e fica olhando para o vazio ─────────────────

def test_combinacao_descoberta_e_nomeada_na_recusa():
    """A retentativa precisa da LISTA do que faltou, não do veredito."""
    cru = _cru(cenarios=[
        {"quando": {"sintoma": "negado"}, "chip": "a", "tom": "ok", "titulo": "T",
         "corpo": "C"},
        {"quando": {"sintoma": "negado"}, "chip": "b", "tom": "ok", "titulo": "T2",
         "corpo": "C2"},
    ])
    with pytest.raises(WidgetInvalido) as e:
        ler(cru)
    assert any("sintoma=analise" in m for m in e.value.motivos)


def test_cenario_padrao_dispensa_cobertura_total():
    cru = _cru(cenarios=[
        {"quando": {"sintoma": "negado"}, "chip": "a", "tom": "ok", "titulo": "T",
         "corpo": "C"},
        {"chip": "geral", "tom": "neutro", "titulo": "Caso geral", "corpo": "C",
         "padrao": True},
    ])
    assert len(ler(cru).cenarios) == 2


# ── tolerância na forma, rigor na substância ────────────────────────────────

@pytest.mark.parametrize("embrulho", [
    "```json\n{cru}\n```",
    "Aqui está o widget:\n{cru}",
    "{cru}\n\nEspero que ajude!",
])
def test_cerca_e_prosa_em_volta_sao_toleradas(embrulho):
    """Recusar por uma crase custa uma retentativa inteira de US$ 0,14."""
    assert ler(embrulho.format(cru=_cru())).arquetipo == "diagnostico"


def test_json_quebrado_diz_onde_quebrou():
    with pytest.raises(WidgetInvalido) as e:
        ler('{"arquetipo": "diagnostico", }')
    assert "linha" in str(e.value)


def test_resposta_sem_json_nenhum_e_recusada():
    with pytest.raises(WidgetInvalido) as e:
        ler("Desculpe, não consigo montar esse widget.")
    assert "não contém um objeto JSON" in str(e.value)


def test_acento_e_aspas_no_conteudo_nao_vazam_para_o_html():
    cru = _cru(titulo='Saque "aniversário" & você')
    bloco = renderizar(ler(cru))
    assert "&quot;" in bloco and "&amp;" in bloco
    assert '<h3 class="vw-tit">Saque "aniversário"' not in bloco


def test_valor_com_acento_vira_identificador_seguro():
    """O valor viaja em `data-*` e numa comparação de string no script."""
    cru = _cru(controles=[{"id": "sintoma", "rotulo": "R", "opcoes": [
        {"valor": "não apareceu", "texto": "Não apareceu"},
        {"valor": "veio menor", "texto": "Veio menor"}]}],
        cenarios=[{"chip": "a", "tom": "ok", "titulo": "T", "corpo": "C", "padrao": True},
                  {"chip": "b", "tom": "ok", "titulo": "T2", "corpo": "C2"}])
    # `diagnostico` desenha `select`, então o valor sai no <option>. O
    # `comparador` desenha botões e o mesmo valor sai em `data-vw-opt`.
    # a primeira opção nasce escolhida — é o que evita o buraco branco
    assert '<option value="nao-apareceu" selected>' in renderizar(ler(cru))
    cru_bt = cru.replace('"arquetipo": "diagnostico"', '"arquetipo": "comparador"')
    assert 'data-vw-opt="nao-apareceu"' in renderizar(ler(cru_bt))


# ── a fronteira com o pipeline ──────────────────────────────────────────────

def test_arquetipos_batem_com_o_mapa_do_pipeline():
    """Se o motor de pautas ganhar um quinto engajamento, os dois crescem juntos.

    O prompt antigo descrevia NOVE arquétipos e o mapa alcançava QUATRO: cinco
    catálogos viajavam em toda chamada sem poder ser escolhidos.
    """
    from funnelforge.pipeline.steps import ENGAJAMENTO_PARA_ARQUETIPO

    do_mapa = {v for v in ENGAJAMENTO_PARA_ARQUETIPO.values() if v}
    daqui = {str(v["nome"]) for v in ARQUETIPOS.values()}
    assert do_mapa == daqui, f"divergiram: {do_mapa ^ daqui}"


def test_texto_visivel_nao_carrega_css():
    """O portão factual julga o conteúdo; antes recebia 4 KB de folha de estilo."""
    t = texto_visivel(ler(_cru()))
    assert "grid-area" not in t and "--vw-tinta" not in t
    assert "O sistema exige conta ativa" in t
    assert "Negaram o meu pedido" in t


def test_id_e_estavel_entre_execucoes():
    """Diff de publicação que muda por id sorteado esconde a mudança real."""
    assert renderizar(ler(_cru())) == renderizar(ler(_cru()))


# ── O BURACO BRANCO ─────────────────────────────────────────────────────────
#
# ⚠️ Medido em 19/08/2026, nas páginas publicadas, com alturas reais do
# navegador:
#
#   p3: cenários de 368 a 413px (1,1×) · abertura 148px → 265px de branco
#   p4: cenários de 207 a 864px (4,2×) · abertura 148px → 716px de branco
#
# Todos os cenários dividem a mesma célula do grid — é daí que vem o CLS zero —,
# então o container fica com a altura do MAIOR. Duas causas somavam: a abertura
# era muito mais curta que qualquer cenário, e os cenários variavam entre si.
#
# Pior: essa altura reservada empurra o anúncio de baixo o TEMPO TODO. O custo
# do CLS estava sendo pago permanentemente em vez de uma vez.

def test_a_peca_nasce_respondida():
    """Sem abertura vazia: a primeira opção já vem escolhida e o cenário dela
    já sai visível."""
    bloco = renderizar(ler(_cru()))
    assert "data-vw-abertura" not in bloco, "a abertura vazia voltou"
    assert "Selecione…" not in bloco
    assert bloco.count('style="visibility:visible"') == 1, (
        "exatamente um cenário nasce visível")


def test_o_cenario_visivel_e_o_da_primeira_opcao():
    """Se o inicial não casasse com o preselecionado, a peça abriria mostrando
    uma resposta que não corresponde ao controle — pior que abrir vazia."""
    bloco = renderizar(ler(_cru()))
    inicio = bloco.index('style="visibility:visible"')
    trecho = bloco[max(0, inicio - 400):inicio + 400]
    assert "sintoma=negado" in trecho, trecho[:200]


def test_o_controle_carrega_o_valor_inicial():
    bloco = renderizar(ler(_cru()))
    assert 'data-vw-valor="negado"' in bloco
    assert 'data-vw-valor=""' not in bloco


def test_silhuetas_diferentes_sao_recusadas():
    """Um cenário com `passos` ao lado de um sem é a maior fonte de variação —
    e é trivial de corrigir, então vira recusa com o nome dos culpados."""
    cru = _cru(cenarios=[
        {"quando": {"sintoma": "negado"}, "chip": "com passos", "tom": "ok",
         "titulo": "T", "corpo": "Corpo do primeiro cenário aqui.",
         "passos": ["um", "dois", "três"]},
        {"quando": {"sintoma": "analise"}, "chip": "sem passos", "tom": "ok",
         "titulo": "T2", "corpo": "Corpo do segundo cenário aqui."},
    ])
    with pytest.raises(WidgetInvalido) as e:
        ler(cru)
    motivo = " ".join(e.value.motivos)
    assert "mesma forma" in motivo
    assert "com passos" in motivo and "sem passos" in motivo


def test_cenario_muito_mais_gordo_e_recusado_com_a_razao():
    """A retentativa precisa saber QUAL encurtar e por quanto."""
    cru = _cru(cenarios=[
        {"quando": {"sintoma": "negado"}, "chip": "gordo", "tom": "ok", "titulo": "T",
         "corpo": "x" * 400},
        {"quando": {"sintoma": "analise"}, "chip": "magro", "tom": "ok", "titulo": "T2",
         "corpo": "curto"},
    ])
    with pytest.raises(WidgetInvalido) as e:
        ler(cru)
    motivo = " ".join(e.value.motivos)
    assert "gordo" in motivo and "magro" in motivo
    assert "×" in motivo


def test_variacao_dentro_do_limite_passa():
    """Não é para obrigar cenários idênticos — só a não deixar um ser o dobro."""
    cru = _cru(cenarios=[
        {"quando": {"sintoma": "negado"}, "chip": "a", "tom": "ok", "titulo": "T",
         "corpo": "x" * 120},
        {"quando": {"sintoma": "analise"}, "chip": "b", "tom": "ok", "titulo": "T2",
         "corpo": "x" * 100},
    ])
    assert len(ler(cru).cenarios) == 2


def test_o_prompt_pede_cenarios_do_mesmo_tamanho():
    from funnelforge.prompts import render

    p = render("redator_widget", country="Brasil", year=2026, title="T",
               article="<p>x</p>", arquetipo="diagnostico", facts="")
    assert "MESMO TAMANHO" in p
    assert "Mesma forma" in p and "Mesmo volume" in p


def test_o_prompt_avisa_que_a_primeira_opcao_ja_vem_escolhida():
    """Sem isso o modelo põe o caso mais grave primeiro, e a peça abre
    afirmando o pior sobre quem acabou de chegar."""
    from funnelforge.prompts import render

    p = render("redator_widget", country="Brasil", year=2026, title="T",
               article="<p>x</p>", arquetipo="diagnostico", facts="")
    assert "JÁ VEM ESCOLHIDA" in p
    assert "mais neutra" in p


# ── URL dentro do widget vira texto cru ─────────────────────────────────────
#
# ⚠️ Visto na regeração de 19/08/2026: o modelo escreveu
# `[Caixa Econômica Federal] (https://www.caixa.gov.br)` no corpo de um cenário.
# O gabarito escapa tudo — corretamente —, então aquilo chegou ao leitor com
# colchetes e parênteses à mostra.

@pytest.mark.parametrize("sujeira", [
    "conforme a [Caixa Econômica Federal] (https://www.caixa.gov.br)",
    "veja em https://www.caixa.gov.br o detalhe",
    "consulte www.fgts.gov.br",
])
def test_url_no_cenario_e_recusada(sujeira):
    cru = _cru(cenarios=[
        {"quando": {"sintoma": "negado"}, "chip": "com url", "tom": "ok",
         "titulo": "T", "corpo": sujeira},
        {"quando": {"sintoma": "analise"}, "chip": "limpo", "tom": "ok",
         "titulo": "T2", "corpo": "Texto sem endereço nenhum aqui dentro."},
    ])
    with pytest.raises(WidgetInvalido) as e:
        ler(cru)
    assert "com url" in " ".join(e.value.motivos)


def test_url_no_rodape_e_recusada():
    with pytest.raises(WidgetInvalido) as e:
        ler(_cru(rodape="Fonte: Caixa (https://www.caixa.gov.br)"))
    assert "rodapé" in " ".join(e.value.motivos)


def test_texto_sem_url_passa():
    assert ler(_cru(rodape="Fonte: canais oficiais da Caixa Econômica Federal."))


def test_o_prompt_proibe_url_no_widget():
    from funnelforge.prompts import render
    p = render("redator_widget", country="Brasil", year=2026, title="T",
               article="<p>x</p>", arquetipo="diagnostico", facts="")
    assert "NENHUMA URL DENTRO DO WIDGET" in p


def test_os_marcadores_resistem_ao_tema_do_site():
    """⚠️ Medido em 19/08/2026 na página no ar: o tema traz
    `.content ul li::before{content:"•"}` — especificidade (0,1,2) — e ela
    vencia `.vw-passo::before` (0,1,1). O número do passo virava bolinha, e a
    ORDEM, que é a informação inteira de um passo a passo, sumia.

    O widget mora dentro de um tema que ele não controla; seletor curto é
    aposta, não contrato."""
    from funnelforge.widgets.estilo import CSS

    assert ".vw ul.vw-passos li.vw-passo::before" in CSS
    assert ".vw ul li.vw-litem::before" in CSS
    # e o número continua vindo do contador, não de texto fixo
    assert "content:counter(vwp)" in CSS
