"""A fonte é a que o PROVEDOR devolveu, nunca a que o modelo digitou.

## O defeito, medido em produção

Primeiro run real, 17/08/2026, card "Cartão para Negativado". A pesquisa da
página 1 devolveu três fontes primárias. Conferi uma a uma, com curl:

    404  gov.br/servidor/.../margem-consignavel-regras-e-limites-a-partir-de-2026
    404  blog.nubank.com.br/novas-regras-do-consignado-do-inss-em-2026/
    403  c6bank.com.br                    (existe, bloqueia robô)

Duas eram invenção — caminhos plausíveis na forma, inexistentes no mundo. A
página morreu no gate, 236 segundos e US$ 0,3945 depois.

E a busca do Google TINHA rodado: o Gemini abriu páginas de verdade, e as URIs
delas voltaram na mesma resposta, dentro de `groundingMetadata`. O cliente lia
só `choices[0].message.content` e descartava o resto. O modelo então precisava
REDIGITAR os endereços de memória dentro do JSON — que é exatamente onde a
alucinação nasce.

Estávamos pagando por citação real, jogando fora, e punindo o modelo por não
lembrar.

## O que estes testes travam

1. A colheita acha as URIs em qualquer forma do dicionário (a API já usou duas).
2. As citações do provedor SUBSTITUEM a lista do modelo — assim uma
   `fonte_primaria` fabricada falha em `fact_source_not_listed` de imediato, sem
   tocar a rede, em vez de custar uma visita de 236 s.
3. Sem citação nenhuma, o comportamento antigo continua — trocar alucinação por
   apagão não seria melhora.
"""
from __future__ import annotations

from funnelforge.adapters.litellm_client import _uris_do_grounding
from funnelforge.adapters.research_perplexity import _com_citacoes_reais
from funnelforge.domain.models import ResearchFacts

REDIRECT = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/xyz"
INVENTADA = "https://www.gov.br/servidor/pt-br/assuntos/consignacao/margem-2026"


class _Resposta:
    def __init__(self, meta):
        self._hidden_params = {"vertex_ai_grounding_metadata": meta} if meta else {}


def test_colhe_uris_em_grounding_chunks():
    r = _Resposta([{"groundingChunks": [
        {"web": {"uri": "https://www.serasa.com.br/limpa-nome/", "title": "t"}},
        {"web": {"uri": "https://www.bcb.gov.br/estabilidadefinanceira", "title": "t"}},
    ]}])
    assert _uris_do_grounding(r) == [
        "https://www.serasa.com.br/limpa-nome/",
        "https://www.bcb.gov.br/estabilidadefinanceira",
    ]


def test_colhe_uris_em_grounding_attributions():
    """A outra forma que a API já usou. A varredura é defensiva de propósito:
    a chave muda entre versões e não dá para depender de uma só."""
    r = _Resposta([{"groundingAttributions": [
        {"web": {"uri": "https://www.serasa.com.br/x", "title": "t"}}]}])
    assert _uris_do_grounding(r) == ["https://www.serasa.com.br/x"]


def test_nao_repete_e_ignora_o_que_nao_e_url():
    r = _Resposta([{
        "groundingChunks": [{"web": {"uri": "https://a.com/1"}},
                            {"web": {"uri": "https://a.com/1"}}],
        "webSearchQueries": ["cartao para negativado"],
        "searchEntryPoint": {"renderedContent": "<div>...</div>"},
    }])
    assert _uris_do_grounding(r) == ["https://a.com/1"]


def test_sem_grounding_devolve_vazio():
    assert _uris_do_grounding(_Resposta(None)) == []
    assert _uris_do_grounding(type("X", (), {})()) == []


def test_citacoes_do_provedor_substituem_a_lista_do_modelo():
    """O coração do conserto: a URL inventada pelo modelo SAI de `fontes`.

    Com ela fora, `research_facts_contract` reprova a `fonte_primaria` fabricada
    em `fact_source_not_listed` — sem visita, sem 236 segundos, sem US$ 0,39.
    """
    facts = ResearchFacts(resumo="r", fontes=[INVENTADA])
    novo = _com_citacoes_reais(facts, ["https://www.serasa.com.br/limpa-nome/"])

    assert novo.fontes == ["https://www.serasa.com.br/limpa-nome/"]
    assert INVENTADA not in novo.fontes
    assert novo.resumo == "r"          # o resto do fato não é tocado


def test_sem_citacao_a_lista_do_modelo_permanece():
    """Nem toda chamada aciona a busca. Zerar as fontes nesse caso trocaria
    alucinação por apagão — toda página reprovaria por falta de fonte."""
    facts = ResearchFacts(resumo="r", fontes=["https://algum.site/x"])
    assert _com_citacoes_reais(facts, []).fontes == ["https://algum.site/x"]


def test_redirect_do_grounding_e_resolvido(monkeypatch):
    """As citações do Gemini vêm como `grounding-api-redirect/<hash>`: reais,
    mas ilegíveis num artigo — e o gate de mesmo domínio precisa do host real."""
    import funnelforge.adapters.research_perplexity as mod

    class _Resp:
        url = "https://www.serasa.com.br/limpa-nome/"

    class _Cliente:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url): return _Resp()
        def close(self): pass

    monkeypatch.setattr(mod.httpx, "Client", _Cliente)
    novo = _com_citacoes_reais(ResearchFacts(resumo="r"), [REDIRECT])
    assert novo.fontes == ["https://www.serasa.com.br/limpa-nome/"]


def test_falha_de_rede_mantem_a_uri_original(monkeypatch):
    """Citação feia que existe é melhor que citação nenhuma."""
    import funnelforge.adapters.research_perplexity as mod

    class _Cliente:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url): raise OSError("sem rede")
        def close(self): pass

    monkeypatch.setattr(mod.httpx, "Client", _Cliente)
    assert _com_citacoes_reais(ResearchFacts(resumo="r"), [REDIRECT]).fontes == [REDIRECT]
