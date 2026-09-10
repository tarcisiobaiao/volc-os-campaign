#!/usr/bin/env python3
"""PRENSA POC — resolve.py v2: valida o spec, resolve $tokens para literais e emite
spec RESOLVIDO + hash canônico. Clone estrutural do padrão motor-video/contrato/motor/resolve.py:
stdlib pura, determinístico, fail-fast, TUDO validado antes de qualquer custo.
v2: fontes vêm da SKIN (tokens.fonts), accent budget pré-custo, multi-slide.
Uso: python3 resolve.py <spec.json> [tokens_override.json]"""
from __future__ import annotations
import hashlib, json, re, sys
from pathlib import Path

AQUI = Path(__file__).parent

def err(msg: str) -> None:
    print(f"❌ RESOLVE: {msg}"); sys.exit(1)

AUSENTE = object()  # sentinela de token opcional não declarado pela skin

def busca_token(tokens: dict, ref: str):
    """Resolve "$color.text.primary". Ref quebrada = erro, nunca chute.
    Prefixo "$?" marca token OPCIONAL: a skin pode não ter aquele efeito
    (papel não faz halação de lente) e a peça simplesmente renderiza sem ele."""
    opcional = ref.startswith("$?")
    no = tokens
    for parte in ref.lstrip("$?").split("."):
        if not isinstance(no, dict) or parte not in no:
            if opcional:
                return AUSENTE
            err(f"token inexistente na skin: {ref}")
        no = no[parte]
    return no

def resolve_refs(valor, tokens: dict):
    if isinstance(valor, str) and valor.startswith("$"):
        achado = busca_token(tokens, valor)
        return AUSENTE if achado is AUSENTE else resolve_refs(achado, tokens)
    if isinstance(valor, dict):
        d = {k: resolve_refs(v, tokens) for k, v in valor.items()}
        return {k: v for k, v in d.items() if v is not AUSENTE}
    if isinstance(valor, list):
        return [v for v in (resolve_refs(x, tokens) for x in valor) if v is not AUSENTE]
    return valor

def valida_fontes(fontes: list) -> None:
    for fonte in fontes:
        arq = AQUI / fonte["file"]
        if not arq.exists():
            err(f"fonte ausente: {fonte['file']}")
        sha = hashlib.sha256(arq.read_bytes()).hexdigest()
        if sha != fonte["sha256"]:
            err(f"sha256 divergente em {fonte['file']}: esperado {fonte['sha256'][:12]}…, "
                f"real {sha[:12]}… (fonte adulterada = recusa pré-custo)")

def n_palavras(s: str) -> int:
    return len([w for w in re.split(r"\s+", s.strip()) if w])

def _lum_relativa(c8: float) -> float:
    c = c8 / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

def scrim_auto(spec: dict, asset_file: str, faixa: tuple[float, float], alvo: float) -> float:
    """Calcula o selo MÍNIMO que garante o contraste alvo do texto sobre este asset.

    O engine mede a foto (p95 da luminância Rec.709 na faixa onde o texto vive —
    conservador: os 5% mais claros) e resolve o alpha. Foto que já nasce escura
    recebe selo quase zero; foto clara recebe o quanto precisar. É o que torna o
    motor agnóstico de nicho: nenhum número de gradiente é chutado por humano.
    Mesma matemática do photo_engine.py do godmode_v4 (Rec.709 + WCAG)."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return 0.85  # sem medição possível: selo conservador, nunca otimista
    a8 = np.asarray(Image.open(AQUI / asset_file).convert("RGB"))
    H = a8.shape[0]
    banda = a8[int(faixa[0] * H):int(faixa[1] * H)]
    # LINEARIZA POR CANAL ANTES de ponderar — mesma ordem do pixel_gates.py do dace.
    # Fazer luma no gama e linearizar depois diverge até 12:1 vs 4:1 em cor
    # saturada, SEMPRE otimista: o selo sairia subdimensionado e o gate pegaria
    # depois (ou pior, não pegaria). Dois módulos com matemáticas diferentes brigam.
    lut = np.array([_lum_relativa(c) for c in range(256)])
    Yrel = (0.2126 * lut[banda[:, :, 0]] + 0.7152 * lut[banda[:, :, 1]]
            + 0.0722 * lut[banda[:, :, 2]])
    p95 = float(np.percentile(Yrel, 95))   # já em luminância RELATIVA
    max_rel = 1.05 / alvo - 0.05
    if max_rel <= 0:
        return 0.98
    for alpha in [i / 100 for i in range(0, 100)]:  # busca determinística, passo 1%
        if p95 * (1 - alpha) <= max_rel:   # selo preto atenua a luminância linear
            return round(alpha, 2)
    return 0.98

def valida_camadas(camadas: list, budget_default: int) -> None:
    for c in camadas:
        if c["type"] == "text":
            fit = c.get("fit") or err(f"camada de texto sem fit: {c['id']}")
            if fit["mode"] == "auto" and fit.get("overflow") != "fail":
                err(f"{c['id']}: fit auto exige overflow='fail' (doutrina fail-closed)")
            if not c.get("runs"):
                err(f"camada de texto sem runs: {c['id']}")
            # accent budget: verificado ANTES de custo, no dado — nunca por string-match no render
            acentuadas = sum(n_palavras(r["text"]) for r in c["runs"] if r.get("accent"))
            budget = (c.get("constraints") or {}).get("accent_max_palavras", budget_default)
            if acentuadas > budget:
                err(f"{c['id']}: accent budget estourado — {acentuadas} palavras acentuadas > máx {budget}. "
                    f"Accent é bisturi, não pincel (doutrina dace).")
        valida_camadas(c.get("children", []), budget_default)

def valida(spec: dict, tokens: dict) -> list:
    for campo in ("schema_version", "spec_id", "skin", "artboard", "gates"):
        if campo not in spec:
            err(f"campo obrigatório ausente: {campo}")
    base = spec["artboard"]["base"]
    if base["w"] <= 0 or base["h"] <= 0:
        err("artboard inválido")
    # fontes: a SKIN é dona das fontes; spec só as usa (marca é dado, engine é lei)
    fontes = tokens.get("fonts") or spec.get("fonts") or err("nem skin nem spec declaram fontes")
    valida_fontes(fontes)
    for asset in spec.get("assets", []):
        if not (AQUI / asset["file"]).exists():
            err(f"asset ausente: {asset['file']} (gere antes: gen_bg.py)")
    budget = ((spec.get("gates") or {}).get("accent_budget") or {}).get("max_palavras", 2)
    if "slides" in spec:
        for s in spec["slides"]:
            valida_camadas(s["layers"], budget)
    else:
        valida_camadas(spec.get("layers") or err("spec sem layers nem slides"), budget)
    return fontes

def main() -> None:
    if len(sys.argv) < 2:
        err("uso: resolve.py <spec.json> [tokens_override.json]")
    spec = json.loads((AQUI / sys.argv[1]).read_text())
    tokens_file = sys.argv[2] if len(sys.argv) > 2 else spec["skin"]["tokens_file"]
    tokens = json.loads((AQUI / tokens_file).read_text())
    fontes = valida(spec, tokens)
    resolvido = resolve_refs(spec, tokens)
    # camada opcional cuja skin não declara o efeito simplesmente não existe
    # (papel não vaza luz de lente) — some do plano, não vira layer quebrada
    def poda(camadas: list) -> list:
        vivas = []
        for c in camadas:
            if c.get("opcional") and set(c) <= {"id", "type", "opcional"}:
                continue
            if "children" in c:
                c["children"] = poda(c["children"])
            vivas.append(c)
        return vivas
    for sl in resolvido.get("slides", []):
        sl["layers"] = poda(sl["layers"])
    if "layers" in resolvido:
        resolvido["layers"] = poda(resolvido["layers"])
    # COLOCAÇÃO AUTOMÁTICA: em vez de assumir "texto embaixo", o engine mede a
    # foto e escolhe a região. É o corte espacial que o parque só tinha no positivo.
    col = resolvido.get("colocacao")
    if col and col.get("modo") == "auto":
        from analisa_foto import analisa
        asset = next(a for a in resolvido["assets"] if a["id"] == col["asset"])
        art = resolvido["artboard"]
        an = analisa(asset["file"], art["base"], art["safe_area"],
                     col.get("alvo_contraste", 4.5))
        if not an["viavel"]:
            err(f"nenhuma zona da foto comporta texto com contraste "
                f"{col.get('alvo_contraste', 4.5)}:1 — recusado antes do render")
        z, H = an["zona"], art["base"]["h"]
        # a zona medida diz onde o texto PODE ir; o bloco entra com respiro para
        # que descendentes e pontuação pendurada não vazem da zona (nem da safe area)
        r = col.get("respiro", 14)
        reserva = col.get("reserva_rodape", 0)
        for sl in resolvido.get("slides", []):
            for c in sl["layers"]:
                if c.get("id") == col.get("frame", "conteudo"):
                    c["pos"] = {"anchor": "bottom_left", "x": z["x"] + r,
                                "y": H - (z["y"] + z["h"]) + r + reserva}
                    c["max_width"] = z["w"] - 2 * r
                    c["zona_h"] = z["h"] - 2 * r - reserva
        # a paleta segue a zona: texto claro sobre zona escura, e vice-versa
        # VÉU: quando a foto não oferece lugar claramente bom (confiança baixa),
        # ou quando a medição pede selo, o engine reforça SÓ a zona escolhida —
        # com margem de segurança, porque confiança baixa significa que a próxima
        # foto do mesmo prompt pode cair pior.
        conf = an["medidas"]["confianca"]
        # CONFIANÇA EXIGIDA: foto sem lugar claramente bom não vira peça sozinha.
        # O véu compensa contraste, não compensa composição — texto encostado na
        # silhueta continua encostado. Numa fábrica, isso é recusa, não "publica
        # e torce": a foto é barata, republicar com credibilidade queimada não é.
        if conf != "alta" and col.get("exigir_confianca", "alta") == "alta":
            err(f"colocação de baixa confiança (dinâmica de quietude "
                f"{an['medidas']['dinamica_de_quietude']}x): esta foto não oferece "
                f"zona claramente melhor que as outras. Gere outra foto ou declare "
                f"exigir_confianca='baixa' para publicar assumindo o risco.")
        alpha_veu = max(an["selo_alpha"] or 0.0, 0.34 if conf == "baixa" else 0.0)
        if alpha_veu > 0.01:
            m = col.get("margem_veu", 60)
            veu = {"id": "veu", "type": "veu", "alpha": round(alpha_veu, 2),
                   "cor": col.get("cor_veu", "rgba(6,5,12,1)"),
                   "box": {"x": z["x"] - m, "y": z["y"] - m,
                           "w": z["w"] + 2 * m, "h": z["h"] + 2 * m}}
            for sl in resolvido.get("slides", []):
                alvo = next((i for i, c in enumerate(sl["layers"])
                             if c.get("id") == col.get("frame", "conteudo")), None)
                if alvo is not None:
                    sl["layers"].insert(alvo, veu)   # abaixo do texto, acima da cena
            print(f"   véu localizado: alpha {alpha_veu} (confiança {conf})")
        resolvido["colocacao_resolvida"] = an
        print(f"   colocação auto: zona {z['w']}x{z['h']} em ({z['x']},{z['y']}) · "
              f"luminância {an['medidas']['luminancia_media']} · "
              f"foco em ({an['foco']['x']},{an['foco']['y']}) · "
              f"texto {'claro' if an['texto_claro'] else 'escuro'} · "
              f"selo {an['selo_alpha']}")

    # selo adaptativo: medido no asset, não escolhido por gosto
    for camada in resolvido.get("layers", []):
        grad = (camada.get("style") or {}).get("gradient") or {}
        if camada.get("type") == "scrim" and grad.get("auto"):
            asset = next(a for a in resolvido["assets"] if a["id"] == camada["asset_ref"])
            alpha = scrim_auto(resolvido, asset["file"],
                               tuple(grad["faixa_texto"]), grad.get("contraste_alvo", 7.0))
            grad["stops"] = [{"at": f"{p}%", "cor": f"rgba(0,0,0,{round(alpha * f, 3)})"}
                             for p, f in grad["curva"]]
            grad["alpha_medido"] = alpha
            print(f"   selo auto: alpha {alpha} (asset {asset['file']})")
    resolvido["fonts"] = fontes
    resolvido["skin"]["id_resolvido"] = tokens.get("skin", spec["skin"]["id"])
    resolvido["skin"]["tokens_resolvidos_de"] = tokens_file
    canonico = json.dumps(resolvido, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    resolvido["hash_canonico"] = hashlib.sha256(canonico.encode()).hexdigest()
    slug_skin = re.sub(r"[^a-z0-9]+", "-", tokens.get("skin", "skin").lower()).strip("-")
    saida = AQUI / "out" / f"{spec['spec_id']}.{slug_skin}.resolvido.json"
    saida.parent.mkdir(exist_ok=True)
    saida.write_text(json.dumps(resolvido, indent=2, ensure_ascii=False))
    print(f"✅ RESOLVE ok · {saida.name} · hash {resolvido['hash_canonico'][:16]}…")

if __name__ == "__main__":
    main()
