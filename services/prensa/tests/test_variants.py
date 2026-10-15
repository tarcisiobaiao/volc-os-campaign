"""`artboard.variants`: ou vira N PNGs nas proporções declaradas, ou falha alto.

O defeito que estes testes fecham: uma spec com três variants passava pelo
resolve e pelo render sem erro e devolvia UM PNG na proporção base (medido em
10/09/2026 e de novo em 15/10/2026 no main). Os testes de unidade rodam em
qualquer Python; os de render precisam do Chrome + Playwright e rodam no
container da PRENSA.
"""
import copy
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

MOTOR = Path(__file__).resolve().parents[1] / "motor"
sys.path.insert(0, str(MOTOR))

from variantes import (  # noqa: E402
    ORIGEM_SAFE_STORIES, VarianteInvalida, e_9x16, safe_area_stories, spec_da_variante,
    valida_variantes)

TRES = [
    {"id": "feed_4x5", "w": 1080, "h": 1350},
    {"id": "story_9x16", "w": 1080, "h": 1920},
    {"id": "square_1x1", "w": 1080, "h": 1080},
]

#: A safe_area de story do exemplo canônico do PRENSA-SPEC.md §3: reserva a
#: interface do Instagram em cima e embaixo.
SAFE_STORY = {"top": 220, "bottom": 340, "left": 72, "right": 140}

#: A margem do feed das specs de teste (e de spec_carrossel.json).
SAFE_FEED = {"top": 86, "bottom": 86, "left": 86, "right": 86}

#: O que uma variante 1080x1920 sem safe_area recebe sobre SAFE_FEED: a zona
#: segura de Stories da Meta (EV-META-20: 14% topo, 35% base, 6% laterais,
#: arredondado para cima), e os 86 da base nas laterais, que são maiores que 65.
SAFE_STORY_PADRAO = {"top": 269, "bottom": 672, "left": 86, "right": 86}


def _base(**artboard_extra) -> dict:
    return {
        "spec_id": "t",
        "artboard": {"base": {"w": 1080, "h": 1350, "formato": "feed_4x5"},
                     "safe_area": dict(SAFE_FEED),
                     **artboard_extra},
        "layers": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Contrato — sem navegador
# ─────────────────────────────────────────────────────────────────────────────

def test_sem_variants_o_caminho_e_o_de_sempre():
    assert valida_variantes(_base()) is None


def test_tres_variants_validas_sao_devolvidas_na_ordem():
    assert [v["id"] for v in valida_variantes(_base(variants=TRES))] == \
        ["feed_4x5", "story_9x16", "square_1x1"]


def test_spec_da_variante_troca_geometria_sem_mutar_a_original():
    spec = _base(variants=copy.deepcopy(TRES))
    spec["artboard"]["variants"][1]["safe_area"] = dict(SAFE_STORY)
    antes = copy.deepcopy(spec)
    story = spec_da_variante(spec, spec["artboard"]["variants"][1])

    assert spec == antes
    assert story["artboard"]["base"]["w"] == 1080 and story["artboard"]["base"]["h"] == 1920
    assert story["artboard"]["base"]["formato"] == "story_9x16"
    assert story["artboard"]["safe_area"] == SAFE_STORY
    assert "variants" not in story["artboard"]
    # variante sem safe_area herda a da base
    quadrado = spec_da_variante(spec, spec["artboard"]["variants"][2])
    assert quadrado["artboard"]["safe_area"] == spec["artboard"]["safe_area"]


# ── 9:16 sem safe_area: reserva a interface de Stories/Reels ────────────────

@pytest.mark.parametrize("w, h, esperado", [
    (1080, 1920, True), (1440, 2560, True), (720, 1280, True),
    (1080, 1910, True),            # dentro da tolerância de 1% do guia da Meta
    (1080, 1940, False),           # fora dela
    (1080, 1350, False), (1080, 1080, False), (1200, 628, False), (1920, 1080, False),
])
def test_deteccao_de_9x16_usa_a_tolerancia_da_meta(w, h, esperado):
    assert e_9x16(w, h) is esperado


def test_zona_segura_da_meta_em_px_arredonda_para_cima():
    assert safe_area_stories(1080, 1920) == {"top": 269, "bottom": 672, "left": 65, "right": 65}
    assert safe_area_stories(1440, 2560) == {"top": 359, "bottom": 896, "left": 87, "right": 87}


def test_9x16_sem_safe_area_reserva_a_interface_de_stories():
    spec = _base(variants=copy.deepcopy(TRES))
    story = spec_da_variante(spec, spec["artboard"]["variants"][1])
    assert story["artboard"]["safe_area"] == SAFE_STORY_PADRAO
    assert story["artboard"]["safe_area_origem"] == ORIGEM_SAFE_STORIES


def test_9x16_usa_o_maior_entre_a_margem_herdada_e_a_da_meta_por_lado():
    spec = _base(variants=[{"id": "story", "w": 1080, "h": 1920}])
    spec["artboard"]["safe_area"] = {"top": 300, "bottom": 40, "left": 40, "right": 120}
    story = spec_da_variante(spec, spec["artboard"]["variants"][0])
    assert story["artboard"]["safe_area"] == {"top": 300, "bottom": 672, "left": 65, "right": 120}


def test_9x16_escala_com_a_resolucao_recomendada_pela_meta():
    spec = _base(variants=[{"id": "story_hd", "w": 1440, "h": 2560}])
    story = spec_da_variante(spec, spec["artboard"]["variants"][0])
    assert story["artboard"]["safe_area"] == {"top": 359, "bottom": 896, "left": 87, "right": 87}


def test_9x16_com_safe_area_explicita_nao_muda():
    spec = _base(variants=copy.deepcopy(TRES))
    spec["artboard"]["variants"][1]["safe_area"] = dict(SAFE_STORY)
    story = spec_da_variante(spec, spec["artboard"]["variants"][1])
    assert story["artboard"]["safe_area"] == SAFE_STORY
    assert "safe_area_origem" not in story["artboard"]
    # explícita menor que a da Meta também é respeitada: quem declara decide
    spec["artboard"]["variants"][1]["safe_area"] = dict(SAFE_FEED)
    story = spec_da_variante(spec, spec["artboard"]["variants"][1])
    assert story["artboard"]["safe_area"] == SAFE_FEED


@pytest.mark.parametrize("variante", [
    {"id": "feed_4x5", "w": 1080, "h": 1350},
    {"id": "square_1x1", "w": 1080, "h": 1080},
    {"id": "link_191x1", "w": 1200, "h": 628},
    {"id": "quase_9x16", "w": 1080, "h": 1940},
])
def test_variantes_que_nao_sao_9x16_continuam_herdando_a_margem_da_base(variante):
    spec = _base(variants=[variante])
    filha = spec_da_variante(spec, variante)
    assert filha["artboard"]["safe_area"] == SAFE_FEED
    assert "safe_area_origem" not in filha["artboard"]
    # e a spec da variante é a mesma de antes desta mudança: só geometria trocada
    esperado = copy.deepcopy(spec)
    del esperado["artboard"]["variants"]
    esperado["artboard"]["base"].update(w=variante["w"], h=variante["h"], formato=variante["id"])
    esperado["artboard"]["variante"] = variante["id"]
    assert filha == esperado


def test_9x16_cuja_margem_padrao_nao_deixa_area_util_falha_antes_de_custo():
    # 90x160 é 9:16; as laterais herdadas de 86 já comem a largura toda
    with pytest.raises(VarianteInvalida, match="safe_area padrão de Stories"):
        valida_variantes(_base(variants=[{"id": "mini", "w": 90, "h": 160}]))


@pytest.mark.parametrize("variants, trecho", [
    ([], "lista não vazia"),
    ({"id": "x"}, "lista não vazia"),
    ([{"id": "a", "w": 1080, "h": 1080, "formato": "x"}], "não suportada"),
    ([{"id": "a", "w": 1080, "h": 1080}, {"id": "a", "w": 1080, "h": 1920}], "duplicado"),
    ([{"id": "A B", "w": 1080, "h": 1080}], "id ausente"),
    ([{"w": 1080, "h": 1080}], "id ausente"),
    ([{"id": "a", "w": 0, "h": 1080}], "inteiros > 0"),
    ([{"id": "a", "w": "1080", "h": 1080}], "inteiros > 0"),
    ([{"id": "a", "w": 1080, "h": 1080, "safe_area": {"top": 10}}], "exatamente"),
    ([{"id": "a", "w": 100, "h": 100,
       "safe_area": {"top": 0, "bottom": 0, "left": 60, "right": 60}}], "área útil"),
])
def test_variants_malformadas_falham_com_motivo(variants, trecho):
    with pytest.raises(VarianteInvalida, match=trecho):
        valida_variantes(_base(variants=variants))


def test_colocacao_automatica_com_variants_falha_explicito():
    spec = _base(variants=TRES)
    spec["colocacao"] = {"modo": "auto", "asset": "bg"}
    with pytest.raises(VarianteInvalida, match="colocacao"):
        valida_variantes(spec)


def test_selo_local_com_variants_falha_explicito():
    spec = _base(variants=TRES)
    spec["slides"] = [{"id": "s1", "layers": [
        {"id": "selo", "type": "scrim", "style": {"gradient": {"auto_local": True}}}]}]
    with pytest.raises(VarianteInvalida, match="selo local"):
        valida_variantes(spec)


def _spec_real(variants) -> tuple[dict, str]:
    """A capa do carrossel de produtividade, sem foto, com spec_id único.

    Sem o ghost "90": ele é um decorativo de 560px desenhado para 4x5, e no
    quadrado invade a headline — o gate de clearance reprova, como deve.
    """
    spec = json.loads((MOTOR / "spec_carrossel.json").read_text())
    spec["slides"] = spec["slides"][:1]
    spec["slides"][0]["layers"] = [c for c in spec["slides"][0]["layers"]
                                   if c.get("id") != "ghost_capa"]
    spec["spec_id"] = f"teste_variants_{uuid.uuid4().hex[:8]}"
    if variants is not None:
        spec["artboard"]["variants"] = variants
    return spec, spec["spec_id"]


def _roda(script: str, arquivo: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, script, arquivo], cwd=MOTOR,
                          capture_output=True, text=True, timeout=300)


def _limpa(spec_id: str) -> None:
    for f in (MOTOR / "out").glob(f"{spec_id}*"):
        f.unlink()
    for f in MOTOR.glob(f"{spec_id}*.json"):
        f.unlink()


def test_resolve_recusa_variants_invalidas_antes_de_custo():
    spec, sid = _spec_real([{"id": "feed_4x5", "w": 1080, "h": 1350, "bleed": 12}])
    arquivo = MOTOR / f"{sid}.json"
    arquivo.write_text(json.dumps(spec, ensure_ascii=False))
    try:
        r = _roda("resolve.py", arquivo.name)
        assert r.returncode == 1
        assert "bleed" in r.stdout and "não suportada" in r.stdout
        assert not list((MOTOR / "out").glob(f"{sid}*"))
    finally:
        _limpa(sid)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Render real — Chrome + Playwright (container da PRENSA)
# ─────────────────────────────────────────────────────────────────────────────

def _tem_render() -> bool:
    """O mesmo `channel="chrome"` do render.py — sem ele não há o que testar."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(channel="chrome", headless=True).close()
        return True
    except Exception:  # noqa: BLE001 - ImportError ou Chrome ausente
        return False


precisa_chrome = pytest.mark.skipif(not _tem_render(), reason="sem Chrome/Playwright: rode no container")


@precisa_chrome
def test_tres_variants_viram_tres_pngs_nas_dimensoes_declaradas():
    from PIL import Image

    # O layout da capa é ancorado em px para 4x5 e não cabe na zona segura de
    # Stories; a story declara a margem do feed para provar só a geometria.
    # A margem padrão de 9:16 tem testes próprios logo abaixo.
    variants = copy.deepcopy(TRES)
    variants[1]["safe_area"] = dict(SAFE_FEED)
    spec, sid = _spec_real(variants)
    arquivo = MOTOR / f"{sid}.json"
    arquivo.write_text(json.dumps(spec, ensure_ascii=False))
    try:
        r = _roda("resolve.py", arquivo.name)
        assert r.returncode == 0, r.stdout + r.stderr
        resolvido = next((MOTOR / "out").glob(f"{sid}.*.resolvido.json"))
        r = _roda("render.py", str(resolvido.relative_to(MOTOR)))
        assert r.returncode == 0, r.stdout + r.stderr

        pngs = sorted((MOTOR / "out").glob(f"{sid}*.png"))
        dims = {p.stem.removeprefix(f"{sid}_"): Image.open(p).size for p in pngs}
        assert dims == {"feed_4x5": (1080, 1350), "story_9x16": (1080, 1920),
                        "square_1x1": (1080, 1080)}
        # o veredito de cada variante foi escrito: verify rodou na geometria dela
        for vid in dims:
            assert (MOTOR / "out" / f"{sid}_{vid}.veredito.json").exists()
    finally:
        _limpa(sid)


@precisa_chrome
def test_variante_que_nao_cabe_reprova_alto_e_nao_escreve_seu_png():
    """A geometria da variante é JULGADA, não só aplicada.

    Com a safe_area de story do SPEC, o layout ancorado para 4x5 encosta na
    interface do Instagram: o verify da variante reprova, o processo sai com
    erro e o PNG dela não existe. Nada de devolver só as que passaram em 200.
    """
    variants = copy.deepcopy(TRES)
    variants[1]["safe_area"] = dict(SAFE_STORY)
    spec, sid = _spec_real(variants)
    arquivo = MOTOR / f"{sid}.json"
    arquivo.write_text(json.dumps(spec, ensure_ascii=False))
    try:
        assert _roda("resolve.py", arquivo.name).returncode == 0
        resolvido = next((MOTOR / "out").glob(f"{sid}.*.resolvido.json"))
        r = _roda("render.py", str(resolvido.relative_to(MOTOR)))
        assert r.returncode == 1
        assert f"{sid}_story_9x16: verify REPROVOU" in r.stdout
        assert "safe area" in r.stdout
        assert not (MOTOR / "out" / f"{sid}_story_9x16.png").exists()
    finally:
        _limpa(sid)


@precisa_chrome
def test_9x16_sem_safe_area_e_julgada_na_zona_segura_de_stories():
    """Antes, esta story herdava a margem do feed (86) e passava com a headline,
    o handle e os dots embaixo da interface do Instagram. Agora o verify dela
    roda com a zona segura da Meta e reprova; o 4x5 e o 1x1 seguem passando."""
    spec, sid = _spec_real(copy.deepcopy(TRES))
    arquivo = MOTOR / f"{sid}.json"
    arquivo.write_text(json.dumps(spec, ensure_ascii=False))
    try:
        assert _roda("resolve.py", arquivo.name).returncode == 0
        resolvido = next((MOTOR / "out").glob(f"{sid}.*.resolvido.json"))
        r = _roda("render.py", str(resolvido.relative_to(MOTOR)))
        assert r.returncode == 1
        assert f"{sid}_story_9x16: verify REPROVOU" in r.stdout
        assert "safe area" in r.stdout
        assert not (MOTOR / "out" / f"{sid}_story_9x16.png").exists()
        assert (MOTOR / "out" / f"{sid}_feed_4x5.png").exists()
        assert (MOTOR / "out" / f"{sid}_square_1x1.png").exists()
    finally:
        _limpa(sid)


@precisa_chrome
def test_9x16_sem_safe_area_com_layout_que_respeita_a_interface_passa():
    """O lado positivo: um layout de story que fica fora da faixa reservada
    passa no verify e sai em 1080x1920, sem declarar safe_area nenhuma."""
    from PIL import Image

    spec, sid = _spec_real([{"id": "story_9x16", "w": 1080, "h": 1920}])
    deslocamento = {"kicker_row": 300, "conteudo": 760, "handle": 690, "dots": 694}
    for camada in spec["slides"][0]["layers"]:
        if camada.get("id") in deslocamento:
            camada["pos"]["y"] = deslocamento[camada["id"]]
    arquivo = MOTOR / f"{sid}.json"
    arquivo.write_text(json.dumps(spec, ensure_ascii=False))
    try:
        assert _roda("resolve.py", arquivo.name).returncode == 0
        resolvido = next((MOTOR / "out").glob(f"{sid}.*.resolvido.json"))
        r = _roda("render.py", str(resolvido.relative_to(MOTOR)))
        assert r.returncode == 0, r.stdout + r.stderr
        assert Image.open(MOTOR / "out" / f"{sid}_story_9x16.png").size == (1080, 1920)
    finally:
        _limpa(sid)


@precisa_chrome
def test_render_recusa_variants_que_chegam_sem_passar_pelo_resolve():
    """A porta HTTP entrega spec resolvida direto ao render: ele também recusa."""
    spec, sid = _spec_real(copy.deepcopy(TRES))
    arquivo = MOTOR / f"{sid}.json"
    arquivo.write_text(json.dumps(spec, ensure_ascii=False))
    try:
        assert _roda("resolve.py", arquivo.name).returncode == 0
        resolvido = next((MOTOR / "out").glob(f"{sid}.*.resolvido.json"))
        dado = json.loads(resolvido.read_text())
        dado["colocacao"] = {"modo": "auto", "asset": "bg"}
        resolvido.write_text(json.dumps(dado, ensure_ascii=False))

        r = _roda("render.py", str(resolvido.relative_to(MOTOR)))
        assert r.returncode == 1
        assert "colocacao" in r.stdout
        assert not list((MOTOR / "out").glob(f"{sid}*.png"))
    finally:
        _limpa(sid)


@precisa_chrome
def test_sem_variants_continua_um_png_com_o_nome_de_sempre():
    spec, sid = _spec_real(None)
    arquivo = MOTOR / f"{sid}.json"
    arquivo.write_text(json.dumps(spec, ensure_ascii=False))
    try:
        assert _roda("resolve.py", arquivo.name).returncode == 0
        resolvido = next((MOTOR / "out").glob(f"{sid}.*.resolvido.json"))
        r = _roda("render.py", str(resolvido.relative_to(MOTOR)))
        assert r.returncode == 0, r.stdout + r.stderr
        assert [p.name for p in (MOTOR / "out").glob(f"{sid}*.png")] == [f"{sid}.png"]
    finally:
        _limpa(sid)
