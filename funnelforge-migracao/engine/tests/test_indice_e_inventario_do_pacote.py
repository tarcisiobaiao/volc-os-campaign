"""Índice de evidências do bucket e o MESMO pacote para redator e revisor."""
from funnelforge.adapters.bucket import BucketDoRun
from funnelforge.domain.models import ResearchFacts
from funnelforge.pipeline.dossie import (compilar_dossie, indice_de_evidencias,
                                         projecao_para_o_prompt)
from funnelforge.pipeline.inventario import montar_inventario
from tests.test_dossie_factual import (CITADAS, FATOS_COMPLETOS, HOJE, _Deps, _estado, _ler,
                                       _Pesquisa, _registrar_canais)


def _com_bucket():
    textos = {f["fonte"]: [] for f in FATOS_COMPLETOS}
    for f in FATOS_COMPLETOS:
        valor = f"{f.get('valor') or ''} {f.get('unidade') or ''}"
        textos[f["fonte"]].append(f"{f['afirmacao']}. {valor}.")

    def ler(url):
        corpo = " ".join(textos.get(url, ["Página sem relação com o tema."]))
        return {"ok": True, "status": 200, "sha256": f"sha-{len(url)}",
                "titulo": "Documento oficial", "url_final": url,
                "texto": "Cabeçalho do site. " + corpo + " Rodapé com contatos."}
    bucket = BucketDoRun(cache=None, ler=ler)
    for url in CITADAS:
        bucket.documento(url)                     # a pesquisa já leu estas páginas
    deps = _Deps()
    deps.bucket = bucket
    return deps


def _dossie(deps):
    state = _estado()
    return state, compilar_dossie(state, deps, _Pesquisa(FATOS_COMPLETOS),
                                  registrar_canais=_registrar_canais, hoje=HOJE,
                                  ler_documento=_ler)


def test_fato_aponta_documento_e_trecho_da_propria_fonte():
    state, dossie = _dossie(_com_bucket())
    lidos = [f for f in dossie.fatos if f.documento]
    assert lidos and all(f.documento["id"] and f.documento["coletado_em"] for f in lidos)
    com_trecho = [f for f in lidos if f.trecho_do_documento]
    assert com_trecho
    assert all("Rodapé" not in f.trecho_do_documento or f.afirmacao[:20] in
               f.trecho_do_documento for f in com_trecho)
    indice = indice_de_evidencias(dossie)
    item = next(i for i in indice["fatos"] if i["id"] == com_trecho[0].fact_id)
    assert item["documento"] == com_trecho[0].documento["id"]
    assert item["trecho_do_documento"] and item["fonte"] and item["coletado_em"]
    assert item["paginas"] and {"pagina", "uso"} <= set(item["paginas"][0])
    assert {p["pagina"] for p in indice["paginas"]} == {p.page_number for p in state.plan.pages}


def test_sem_bucket_nada_e_inventado_e_o_dump_do_fato_nao_muda():
    state, dossie = _dossie(_Deps())
    assert all(not f.documento and not f.trecho_do_documento for f in dossie.fatos)
    dump = dossie.fatos[0].model_dump(mode="json")
    assert "documento" not in dump and "trecho_do_documento" not in dump
    sem_data = next(i for i in indice_de_evidencias(dossie)["fatos"] if not i["vigente_desde"])
    assert sem_data["vigente_desde"] == "" and "confianca" not in sem_data


def test_revisor_le_os_fatos_do_pacote_mesmo_com_state_facts_divergente():
    state, dossie = _dossie(_com_bucket())
    state.dossie = dossie.model_dump(mode="json")
    page = next(p for p in state.plan.pages if projecao_para_o_prompt(
        state.dossie, p.page_number).get("fatos"))
    factual = projecao_para_o_prompt(state.dossie, page.page_number)
    state.pacotes = {page.page_number: {"factual": factual}}
    state.facts[page.page_number] = ResearchFacts(sparse=True)   # projeção vencida

    inv = montar_inventario(state, page)

    assert [f.id for f in inv.fatos] == [f["id"] for f in factual["fatos"]]
    assert all(f.verificada_ao_vivo for f in inv.fatos)
    com_trecho = [f for f in inv.fatos if f.trecho]
    assert com_trecho == [f for f in inv.fatos if any(
        x["id"] == f.id and x.get("trecho") for x in factual["fatos"])]


def test_revisao_global_leva_cada_fato_uma_vez_e_ids_resolviveis(tmp_path, monkeypatch):
    import re

    from funnelforge.domain.models import PageDraft, StepResult, StepStatus
    from funnelforge.pipeline import inteligencia, steps as st
    from funnelforge.pipeline.inteligencia import congelar_pacotes
    from tests.test_ctas_do_funil import estado, roteiro

    state, deps, _ = estado(tmp_path, roteiro())
    congelar_pacotes(state, deps)
    for p in state.plan.pages:
        state.drafts[p.page_number] = PageDraft(
            page_number=p.page_number, page_type=p.page_type,
            format="lp_json" if p.page_type == "LANDING PAGE" else "gutenberg",
            content=('{"hero_title": "t"}' if p.page_type == "LANDING PAGE"
                     else "<!-- wp:paragraph --><p>Texto.</p><!-- /wp:paragraph -->"))
    enviada = {}

    class Captura:
        runs_dir = tmp_path / "runs"

        def run_llm_step(self, nome, cfg, mensagens, ctx, run_id):
            enviada["texto"] = mensagens[0]["content"]
            return '{"paginas": []}', StepResult(step=nome, status=StepStatus.OK)

    monkeypatch.setattr(st, "_revisar_pagina", lambda *a, **k: None)
    deps.runner = Captura()
    inteligencia.revisar_lote(state, state.plan.pages, deps)
    texto = enviada["texto"]
    assert "ÍNDICE FACTUAL DO LOTE" in texto
    ids = set(re.findall(r"f_[0-9a-f]{12}", texto))
    assert ids
    for fid in ids:                                   # todo id citado se resolve no índice
        assert re.search(rf"- {fid} \[", texto), fid
    fatos = {f["id"]: f["afirmacao"] for n in state.pacotes
             for f in state.pacotes[n]["factual"]["fatos"]}
    for fid, afirmacao in fatos.items():
        assert texto.count(f"- {fid} [") == 1          # o texto do fato vai uma vez
    assert texto.count("PACOTE DE POLÍTICAS DO LOTE (vale para todas as páginas)") == 1
