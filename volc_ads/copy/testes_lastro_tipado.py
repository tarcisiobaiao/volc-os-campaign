"""Lastro TIPADO na copy Search — contrato entre as trilhas, decisão 2 (30/09/2026).

O que se prova aqui, sem rede e sem token:

  · `[contexto]` é tipo da seção 2 do `PROMPT.md`, com semântica escrita: sustenta
    relevância e nomeação, NUNCA número, prazo ou condição;
  · a checagem é DETERMINÍSTICA e SEMPRE ligada — roda com o juiz de sentido
    ligado, porque não depende de sentido: cruza a mecânica declarada (M6, M9,
    M10) e o dígito do texto com o TIPO do fato citado;
  · juiz de sentido fora do ar → a copy NÃO é aceita, com a pendência escrita,
    e a C7 completa volta a valer naquela rodada — nunca lista vazia calada;
  · o juiz recebe os fatos por extenso, com o tipo, e é ensinado que
    `[contexto]` não sustenta número;
  · o `PROMPT.md` (o que o modelo LÊ) ensina a exceção das raízes que o
    contrato aplica no teto de repetição (V4 da verificação adversarial).

Rodar:
    backend/.venv/bin/python -m pytest volc_ads/copy/testes_lastro_tipado.py -q
"""
from __future__ import annotations

import copy as _copy
import inspect


import pytest

from volc_ads.copy import contrato, juiz_semantico as js, render
from volc_ads.copy.ciclo import gerar
from volc_ads.copy.contrato import Classe, Pedido, checar, comprimento_efetivo, medir
from volc_ads.copy.mock import ClienteMock, JuizMock, copy_valida

# Os ids do `copy_valida()` com tipos plausíveis para o que cada título faz.
TIPOS = (("F1", "data"), ("F2", "numero"), ("F3", "mudanca"),
         ("F4", "fonte_legal"), ("F5", "prazo"))


def _pedido(**troca) -> Pedido:
    base = dict(n_headlines=15, n_descriptions=4, n_sitelinks=4, n_callouts=4,
                n_snippet=4, idioma="pt", fatos=tuple(i for i, _ in TIPOS),
                headers_snippet=("Tipos",), max_dki=1,
                tipos_dos_fatos=TIPOS, ano=2026)
    base.update(troca)
    return Pedido(**base)


def _sincronizar(d: dict, i: int) -> None:
    d["ancoragem"]["headlines"][i]["chars"] = comprimento_efetivo(d["headlines"][i])
    c = medir(d["headlines"])
    c["mecanicas_distintas"] = len({e["mecanica"] for e in d["ancoragem"]["headlines"]})
    c["max_titulos_por_fato"] = 2
    d["auditoria"]["contagem_final"] = c


def _codigos(achados) -> list[str]:
    return [a.codigo for a in achados]


def _base() -> dict:
    return _copy.deepcopy(copy_valida())


# ── a base: a copy válida continua válida com tipos ─────────────────────────

@pytest.mark.parametrize("semantico", [False, True])
def test_copy_valida_com_tipos_compativeis_nao_gera_achado_de_tipo(semantico):
    achados = checar(_base(), _pedido(), semantico_ativo=semantico)
    tipados = [a for a in achados if a.codigo.startswith(("C5.tipo", "C7.tipo"))]
    assert tipados == [], tipados


def test_sem_tipos_no_pedido_nada_muda():
    """Pedido antigo (sem `tipos_dos_fatos`): nenhuma checagem nova dispara.
    É o que mantém `provar_cascata` e os bancos antigos idênticos."""
    d = _base()
    d["ancoragem"]["headlines"][5]["fato"] = "F2"   # 'A Regra Muda em 31/10/2026'
    antigo = Pedido(n_headlines=15, n_descriptions=4, n_sitelinks=4, n_callouts=4,
                    n_snippet=4, fatos=("F1", "F2", "F3", "F4", "F5"),
                    headers_snippet=("Tipos",))
    assert not [a for a in checar(d, antigo) if ".tipo" in a.codigo]


# ── [contexto] não sustenta número, prazo nem condição ──────────────────────

@pytest.mark.parametrize("semantico", [False, True])
def test_digito_ancorado_so_em_contexto_vira_achado_mesmo_com_juiz(semantico):
    """O caso da verificação (V10): o f1 do Senac diz '27 Departamentos
    Regionais'. Como [contexto], ele NÃO sustenta '27' num título — e isso vale
    com o juiz de sentido ligado, porque não depende de sentido."""
    d = _base()
    d["headlines"][3] = "Senac: 27 Regionais no País"
    d["ancoragem"]["headlines"][3].update({"mecanica": "M4", "fato": "f1"})
    _sincronizar(d, 3)
    p = _pedido(fatos=("F1", "F2", "F3", "F4", "F5", "f1"),
                tipos_dos_fatos=TIPOS + (("f1", "contexto"),))
    achados = [a for a in checar(d, p, semantico_ativo=semantico)
               if a.codigo == "C7.tipo_incompativel"]
    assert len(achados) == 1, _codigos(checar(d, p, semantico_ativo=semantico))
    assert str(achados[0].alvo) == "headline[3]"
    assert achados[0].classe is Classe.FORMA_REESCREVER
    assert "[contexto]" in achados[0].detalhe


def test_contexto_nomeia_sem_numero_e_passa():
    """Nomear o que o [contexto] descreve é exatamente o uso dele."""
    d = _base()
    d["headlines"][3] = "Senac Tem Regional por Estado"
    d["ancoragem"]["headlines"][3].update({"mecanica": "M1", "fato": "f1"})
    _sincronizar(d, 3)
    p = _pedido(fatos=("F1", "F2", "F3", "F4", "F5", "f1"),
                tipos_dos_fatos=TIPOS + (("f1", "contexto"),))
    assert not [a for a in checar(d, p, semantico_ativo=True) if ".tipo" in a.codigo]


def test_o_ano_corrente_nao_e_numero_de_fato():
    """O `{ano}` é liberado até no MODO SEM LASTRO (seção 2). Um título que só
    tem o ano e cita um [contexto] não afirma número nenhum."""
    d = _base()
    d["headlines"][3] = "Regionais do Senac em 2026"
    d["ancoragem"]["headlines"][3].update({"mecanica": "M1", "fato": "f1"})
    _sincronizar(d, 3)
    p = _pedido(fatos=("F1", "F2", "F3", "F4", "F5", "f1"),
                tipos_dos_fatos=TIPOS + (("f1", "contexto"),))
    assert not [a for a in checar(d, p, semantico_ativo=True) if ".tipo" in a.codigo]
    # Outro ano é data, e data não vem de [contexto].
    d["headlines"][3] = "Regionais do Senac em 2008"
    _sincronizar(d, 3)
    assert "C7.tipo_incompativel" in _codigos(checar(d, p, semantico_ativo=True))


def test_prazo_ate_ancorado_so_em_contexto_vira_achado():
    d = _base()
    d["headlines"][3] = "Inscrição Até o Fim do Mês"
    d["ancoragem"]["headlines"][3].update({"mecanica": "M1", "fato": "f1"})
    _sincronizar(d, 3)
    p = _pedido(fatos=("F1", "F2", "F3", "F4", "F5", "f1"),
                tipos_dos_fatos=TIPOS + (("f1", "contexto"),))
    assert "C7.tipo_incompativel" in _codigos(checar(d, p, semantico_ativo=True))


def test_descricao_com_numero_e_so_contexto_vira_achado():
    d = _base()
    d["ancoragem"]["descriptions"][3]["fatos"] = ["f1", "f2"]   # '... prazo de 90 dias ...'
    p = _pedido(fatos=("F1", "F2", "F3", "F4", "F5", "f1", "f2"),
                tipos_dos_fatos=TIPOS + (("f1", "contexto"), ("f2", "contexto")))
    achados = [a for a in checar(d, p, semantico_ativo=True)
               if a.codigo == "C7.tipo_incompativel"]
    assert [str(a.alvo) for a in achados] == ["description[3]"], achados


def test_descricao_com_um_fato_numerico_e_um_contexto_passa():
    d = _base()
    d["ancoragem"]["descriptions"][3]["fatos"] = ["f1", "F2"]
    p = _pedido(fatos=("F1", "F2", "F3", "F4", "F5", "f1"),
                tipos_dos_fatos=TIPOS + (("f1", "contexto"),))
    assert not [a for a in checar(d, p, semantico_ativo=True) if ".tipo" in a.codigo]


def test_sitelink_com_numero_e_contexto_vira_achado_no_subcampo_certo():
    d = _base()
    d["sitelinks"][1]["description2"] = "São 27 regionais no país"
    d["ancoragem"]["sitelinks"][1]["fato"] = "f1"
    p = _pedido(fatos=("F1", "F2", "F3", "F4", "F5", "f1"),
                tipos_dos_fatos=TIPOS + (("f1", "contexto"),))
    achados = [a for a in checar(d, p, semantico_ativo=True)
               if a.codigo == "C7.tipo_incompativel"]
    assert [str(a.alvo) for a in achados] == ["sitelink[1].description2"], achados


# ── mecânica declarada × tipo do fato citado (C5) ───────────────────────────

@pytest.mark.parametrize("mecanica,titulo,tipo,passa", [
    ("M6", "Renda de 2 Salários Mínimos", "numero", True),
    ("M6", "Renda de 2 Salários Mínimos", "condicao", False),   # M6 nasce de [numero]
    ("M9", "Inscrições Até 15/10", "prazo", True),
    ("M9", "Inscrições Até 15/10", "data", True),
    ("M9", "Inscrições Até 15/10", "numero", False),
    ("M10", "Quem Ganha Até 2 Salários", "condicao", True),
    ("M10", "Quem Ganha Até 2 Salários", "numero", False),
    ("M10", "Quem Tem Direito à Vaga", "contexto", False),
])
def test_mecanica_de_numero_prazo_ou_condicao_exige_o_tipo_que_a_habilita(
        mecanica, titulo, tipo, passa):
    d = _base()
    d["headlines"][3] = titulo
    d["ancoragem"]["headlines"][3].update({"mecanica": mecanica, "fato": "x1"})
    _sincronizar(d, 3)
    p = _pedido(fatos=("F1", "F2", "F3", "F4", "F5", "x1"),
                tipos_dos_fatos=TIPOS + (("x1", tipo),))
    achados = [a for a in checar(d, p, semantico_ativo=True)
               if a.codigo == "C5.tipo_do_fato"]
    if passa:
        assert achados == [], achados
    else:
        assert len(achados) == 1 and str(achados[0].alvo) == "headline[3]", achados


def test_fato_inexistente_e_pego_com_o_juiz_ligado():
    """Existência é exata: não depende de sentido, então não se desliga."""
    d = _base()
    d["ancoragem"]["headlines"][5]["fato"] = "F9"   # 'A Regra Muda em 31/10/2026'
    assert "C7.fato_inexistente" in _codigos(checar(d, _pedido(), semantico_ativo=True))


def test_o_que_e_exato_no_lastro_roda_antes_do_portao_do_juiz():
    fonte = inspect.getsource(contrato.checar)
    antes, depois = fonte.split("if not semantico_ativo:")
    assert "_c5_tipo_do_fato" in antes and "_c7_lastro_tipado" in antes
    # O que depende de SENTIDO (dígito é nome ou alegação?) continua do juiz.
    assert "_c7_fato" in depois


# ── o juiz de sentido fora do ar ────────────────────────────────────────────

class _JuizFora:
    """Encena o juiz caindo em toda rodada."""

    def __init__(self):
        self.chamadas = 0

    def __call__(self, dados):
        self.chamadas += 1
        raise js.JuizIndisponivel("falha na chamada ao juiz (ReadTimeout)")


def test_juiz_indisponivel_nao_aceita_e_diz_por_que():
    d = _base()
    r = gerar(cliente=ClienteMock([d]), juiz=JuizMock(), pedido=_pedido(),
              prompt_usuario="<p>", juiz_semantico=_JuizFora())
    assert r.ok is False, "copy aceita sem o juiz de sentido"
    pend = [a for a in r.pendentes if a.codigo == "JS.indisponivel"]
    assert len(pend) == 1, r.pendentes
    assert pend[0].classe is Classe.JUIZ_INDISPONIVEL
    assert pend[0].alvo is None
    assert "ReadTimeout" in pend[0].detalhe and "não" in pend[0].detalhe.lower()
    assert any("juiz de sentido indisponível" in linha for linha in r.estado.diario)


def test_juiz_que_levanta_qualquer_erro_nao_derruba_a_geracao():
    """A propriedade antiga continua: o juiz nunca leva a cascata junto."""
    def _bug(dados):
        raise KeyError("campo")

    r = gerar(cliente=ClienteMock([_base()]), juiz=JuizMock(), pedido=_pedido(),
              prompt_usuario="<p>", juiz_semantico=_bug)
    assert r.ok is False
    assert [a.codigo for a in r.pendentes] == ["JS.indisponivel"]
    assert "KeyError" in r.pendentes[0].detalhe


def test_juiz_fora_religa_a_c7_completa_naquela_rodada():
    """Com o juiz ligado a C7 heurística (dígito sem fato) fica desligada; se
    ele cai, ela volta — senão a rodada ficaria sem checagem de lastro."""
    d = _base()
    d["headlines"][3] = "Tabela com 5 Faixas Legais"
    d["ancoragem"]["headlines"][3].update({"mecanica": "M1", "fato": "-"})
    _sincronizar(d, 3)
    # Juiz disponível e sem objeção: a C7 heurística não roda.
    ok = gerar(cliente=ClienteMock([_copy.deepcopy(d)]), juiz=JuizMock(),
               pedido=_pedido(), prompt_usuario="<p>",
               juiz_semantico=lambda dados: [])
    assert ok.ok, ok.relatorio()
    # Juiz fora: a C7 volta e pega o dígito sem fato.
    fora = gerar(cliente=ClienteMock([_copy.deepcopy(d),
                                      {"texto": "Tabela Oficial por Faixa",
                                       "mecanica": "M1", "fato": "-"}]),
                 juiz=JuizMock(), pedido=_pedido(), prompt_usuario="<p>",
                 juiz_semantico=_JuizFora())
    assert not fora.ok
    assert any("C7.sem_lastro" in linha for linha in fora.estado.diario), fora.relatorio()


def test_juiz_que_volta_na_rodada_seguinte_pode_aceitar():
    """A exigência é sobre o texto FINAL: julgado por ele, pode ser aceito."""
    d = _base()
    d["headlines"][3] = "Tabela com 5 Faixas Legais"
    d["ancoragem"]["headlines"][3].update({"mecanica": "M1", "fato": "-"})
    _sincronizar(d, 3)
    rodadas = iter([js.JuizIndisponivel("resposta ilegível do juiz"), [], []])

    def _instavel(dados):
        v = next(rodadas)
        if isinstance(v, Exception):
            raise v
        return v

    r = gerar(cliente=ClienteMock([d, {"texto": "Tabela Oficial por Faixa",
                                       "mecanica": "M1", "fato": "-"}]),
              juiz=JuizMock(), pedido=_pedido(), prompt_usuario="<p>",
              juiz_semantico=_instavel)
    assert r.ok, r.relatorio()


# ── o juiz de sentido: indisponibilidade explícita e o tipo na entrada ──────

class _Dubl:
    def __init__(self, resposta: str):
        self.resposta = resposta
        self.sistema = self.usuario = ""

    def gerar(self, sistema, usuario):
        self.sistema, self.usuario = sistema, usuario
        return self.resposta


@pytest.mark.parametrize("resposta", ["isto não é JSON", "", "{}",
                                      '{"observacoes": "não é lista"}',
                                      "```json\n{quebrado\n```"])
def test_resposta_fora_do_contrato_e_indisponibilidade(resposta):
    with pytest.raises(js.JuizIndisponivel) as exc:
        js.julgar(_Dubl(resposta), {"headlines": ["x"]}, fatos_texto="", nicho="x",
                  regras=[])
    assert exc.value.motivo


def test_lista_vazia_do_juiz_e_resposta_valida():
    assert js.julgar(_Dubl('{"observacoes": []}'), {"headlines": ["x"]},
                     fatos_texto="", nicho="x", regras=[]) == []


def test_transporte_que_cai_vira_indisponivel_sem_a_mensagem_crua():
    """A mensagem de erro de transporte pode carregar URL com chave; o motivo
    leva só o TIPO do erro."""
    class _Cai:
        def gerar(self, sistema, usuario):
            raise RuntimeError("GET https://x/?key=SEGREDO-123 falhou")

    with pytest.raises(js.JuizIndisponivel) as exc:
        js.julgar(_Cai(), {"headlines": ["x"]}, fatos_texto="", nicho="x", regras=[])
    assert "RuntimeError" in exc.value.motivo
    assert "SEGREDO" not in exc.value.motivo and "SEGREDO" not in str(exc.value)


def test_o_sistema_do_juiz_ensina_que_contexto_nao_sustenta_numero():
    d = _Dubl('{"observacoes": []}')
    js.julgar(d, {"headlines": ["x"]}, fatos_texto="  f1 [contexto] 27 regionais",
              nicho="x", regras=[])
    assert "[contexto]" in d.sistema
    trecho = d.sistema[d.sistema.index("[contexto]"):][:300].lower()
    assert "nunca" in trecho and "número" in trecho
    assert "f1 [contexto] 27 regionais" in d.usuario


def test_o_juiz_ve_as_descricoes_dos_sitelinks():
    """`description1/2` é o nome que o PROMPT.md manda o modelo usar; o juiz só
    lia `descricao1/2` e deixava a descrição do sitelink sem julgamento."""
    d = _Dubl('{"observacoes": []}')
    js.julgar(d, {"sitelinks": [{"title": "T", "description1": "27 regionais",
                                 "description2": "até 2 salários"}]},
              fatos_texto="", nicho="x", regras=[])
    assert "27 regionais" in d.usuario and "até 2 salários" in d.usuario


def test_fatos_do_juiz_levam_tipo_e_escopo():
    from types import SimpleNamespace

    from volc_ads.copy import encomendar as em

    enc = SimpleNamespace(fatos=[
        SimpleNamespace(id="f1", tipo="contexto", texto="27 Departamentos Regionais",
                        fonte="https://www.senac.br", escopo=""),
        SimpleNamespace(id="n2", tipo="numero", texto="2 salários mínimos",
                        fonte="https://planalto.gov.br", escopo="regional:SP"),
    ])
    txt = em._fatos_para_juiz(enc)
    assert "f1 [contexto] 27 Departamentos Regionais" in txt
    assert "n2 [numero] 2 salários mínimos" in txt and "regional:SP" in txt


# ── o PROMPT.md: [contexto] e a exceção das raízes ──────────────────────────

def test_contexto_e_tipo_da_secao_2_com_semantica_escrita():
    assert "contexto" in render.tipos_de_fato()
    corpo = render.corpo()
    i = corpo.index("[contexto]")
    trecho = corpo[i:i + 900].lower()
    assert "relevância" in trecho and "nomeação" in trecho
    assert "nunca" in trecho and "número" in trecho and "prazo" in trecho
    assert "condição" in trecho


# O teste V4 (o PROMPT.md ensina a exceção das raízes) mora no lugar original:
# `testes_juiz_semantico.test_o_prompt_ensina_a_mesma_excecao_que_o_contrato_aplica`.

def test_as_raizes_isentas_sao_as_mesmas_do_contrato():
    from volc_ads.copy.render import Encomenda, valores

    kws = ("saque aniversario fgts", "regras do saque aniversario fgts",
           "quem tem direito ao saque aniversario fgts")
    enc = Encomenda(nicho="Saque-Aniversário FGTS", url="https://x.com.br/a",
                    keywords=kws, ano=2026)
    v = valores(enc)["{raizes_fora_do_teto}"]
    for r in enc.pedido().raizes_do_termo:
        assert r in v
    diverso = Encomenda(nicho="Benefícios", url="https://x.com.br/a",
                        keywords=("saque fgts", "bolsa familia", "cadastro unico",
                                  "seguro desemprego", "pis pasep", "inss beneficio",
                                  "auxilio gas", "tarifa social"), ano=2026)
    assert not diverso.pedido().raizes_do_termo
    assert "nenhuma" in valores(diverso)["{raizes_fora_do_teto}"].lower()


def test_encomenda_leva_o_tipo_de_cada_fato_ao_pedido():
    from volc_ads.copy.render import Encomenda, Fato

    enc = Encomenda(nicho="Cursos Senac", url="https://x.com.br/a",
                    keywords=("cursos senac",), ano=2026,
                    fatos=(Fato("f1", "contexto", "27 regionais", "https://s"),
                           Fato("n2", "numero", "2 salários mínimos", "https://p")))
    p = enc.pedido()
    assert dict(p.tipos_dos_fatos) == {"f1": "contexto", "n2": "numero"}
    assert p.ano == 2026


def test_entrada_de_ancoragem_sem_indice_valido_nao_vira_alvo_negativo():
    """`Alvo("headline", -1)` reescreveria o ÚLTIMO título na regeneração."""
    d = _base()
    d["ancoragem"]["headlines"][3] = {"mecanica": "M6", "fato": "x1"}   # sem "i"
    d["ancoragem"]["headlines"].append({"i": 99, "mecanica": "M6", "fato": "x1"})
    p = _pedido(fatos=("F1", "F2", "F3", "F4", "F5", "x1"),
                tipos_dos_fatos=TIPOS + (("x1", "contexto"),))
    alvos = [a.alvo for a in checar(d, p, semantico_ativo=True)
             if a.codigo in ("C5.tipo_do_fato", "C7.tipo_incompativel")]
    assert all(a is not None and 0 <= a.indice < 15 for a in alvos), alvos
