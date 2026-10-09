"""C12: ano anterior ao corrente em recurso de anúncio é reescrita, sempre.

Caso real (card 106, 09/10/2026): sem texto da LP o brief não tinha fatos, a
`C7` não cobrou lastro, e a cascata entregou "Gás do Povo Calendário 2025" e
"Regras do Gás do Povo 2024".
"""
from __future__ import annotations

from volc_ads.copy.contrato import Classe, Pedido, _c12_ano_passado


def _pedido(ano: int = 2026) -> Pedido:
    return Pedido(n_headlines=15, n_descriptions=4, n_sitelinks=4, n_callouts=4,
                  n_snippet=4, idioma="pt", fatos=(), headers_snippet=("Tipos",),
                  max_dki=1, ano=ano)


def test_caso_real_do_card_106():
    dados = {"headlines": ["Gás do Povo Calendário 2025", "Regras do Gás do Povo 2024",
                           "Gás do Povo: Como Funciona"],
             "descriptions": [], "callouts": [], "sitelinks": []}
    achados = _c12_ano_passado(dados, _pedido())
    assert [str(a.alvo) for a in achados] == ["headline[0]", "headline[1]"]
    assert all(a.classe is Classe.FORMA_REESCREVER for a in achados)


def test_ano_corrente_e_futuro_passam():
    dados = {"headlines": ["Calendário 2026", "Regras 2027"], "descriptions": ["Prazo até 2026."],
             "callouts": ["Atualizado 2026"], "sitelinks": [{"title": "Regras 2026"}]}
    assert _c12_ano_passado(dados, _pedido()) == []


def test_sitelink_e_callout_tambem_sao_conferidos():
    dados = {"headlines": [], "descriptions": [], "callouts": ["Tabela 2024"],
             "sitelinks": [{"title": "Regras", "description1": "Valores 2023"}]}
    alvos = [str(a.alvo) for a in _c12_ano_passado(dados, _pedido())]
    assert alvos == ["callout[0]", "sitelink[0].description1"]


def test_sem_ano_no_pedido_usa_o_relogio():
    import datetime

    passado = datetime.date.today().year - 1
    dados = {"headlines": [f"Regras {passado}"], "descriptions": [], "callouts": [], "sitelinks": []}
    assert len(_c12_ano_passado(dados, _pedido(ano=0))) == 1


def test_ano_como_data_de_fato_ou_norma_nao_e_rotulo():
    dados = {"headlines": ["A regra mudou em 2025", "Desde 2024 no CadÚnico"],
             "descriptions": ["Conteúdo apoiado na Resolução CCFGTS 1.130/2025."],
             "callouts": [], "sitelinks": []}
    assert _c12_ano_passado(dados, _pedido()) == []
