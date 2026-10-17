"""CLI local do kernel de viabilidade (offline/shadow). Nenhuma chamada externa.

Uso (da raiz do lab, com o Python do lab):
  .venv/bin/python -I scripts/viability_cli.py evaluate   entrada.json --saida DIR
  .venv/bin/python -I scripts/viability_cli.py frontier   entrada.json --saida DIR
  .venv/bin/python -I scripts/viability_cli.py simulation entrada.json --saida DIR
  .venv/bin/python -I scripts/viability_cli.py replay     fixtures/viability --saida DIR
  .venv/bin/python -I scripts/viability_cli.py verify     DIR/recibo.json

Exit codes: 0 conclusivo · 2 entrada inválida · 3 insuficiente/indisponível · 4 invariante violada.
Saídas: resultado JSON canônico, relatório humano curto, recibo com hashes (entrada, resultado, código).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path

RAIZ_LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_LAB / "src"))

from volc_dil.viability import VERSAO_KERNEL  # noqa: E402
from volc_dil.viability.contrato import ContratoViabilidadeViolado, EntradaViabilidade, hash_entrada, json_canonico  # noqa: E402
from volc_dil.viability.economia import Indisponivel, envelope_conservador, fronteira  # noqa: E402
from volc_dil.viability.gate import ResultadoViabilidade, Veredito, avaliar  # noqa: E402
from volc_dil.viability.invariantes import InvarianteViolada, verificar_invariantes  # noqa: E402
from volc_dil.viability.simulacao import CurvaIndisponivel, analisar_simulacao  # noqa: E402

EXIT_OK, EXIT_ENTRADA_INVALIDA, EXIT_INSUFICIENTE, EXIT_INVARIANTE = 0, 2, 3, 4
MODULOS = sorted((RAIZ_LAB / "src" / "volc_dil" / "viability").glob("*.py"))


def codigo_sha256() -> str:
    h = hashlib.sha256()
    for p in MODULOS:
        h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()


def carregar(caminho: Path) -> EntradaViabilidade:
    doc = json.loads(caminho.read_text(encoding="utf-8"))
    return EntradaViabilidade.de_json(doc.get("entrada", doc))


def _fmt_micros(v) -> str:
    if v is None:
        return "—"
    f = Fraction(v)
    return f"{float(f) / 1e6:.4f}"


def relatorio_humano(r: ResultadoViabilidade) -> str:
    j = r.para_json()
    linhas = [
        f"# Viabilidade — {r.candidato_id} (as_of {r.as_of})", "",
        f"**Veredito:** {r.verdict.value} · **confiança:** {r.confidence_class.value} · **recomendação:** {r.recomendacao.value}", "",
        f"- CPC observado: {_fmt_micros(r.observed_cpc)} · RPC observado: {_fmt_micros(r.observed_rpc)} · break-even CPC: {_fmt_micros(r.break_even_cpc)} · CPC sustentável conservador: {_fmt_micros(r.conservative_affordable_cpc)}",
        f"- RPC necessário: {_fmt_micros(r.required_rpc)} (×{'—' if r.required_rpc_multiplier is None else f'{float(r.required_rpc_multiplier):.2f}'})",
        f"- Contribuição observada: {'—' if r.contribution_observed is None else r.contribution_observed.decimal()} · conservadora: {'—' if r.contribution_conservative is None else r.contribution_conservative.decimal()}",
        f"- Teto: spend {'—' if r.max_experiment_spend is None else r.max_experiment_spend.decimal()} · cliques {r.max_experiment_clicks} · dias {r.max_experiment_days} · stop-loss {'—' if r.stop_loss is None else r.stop_loss.decimal()} · maturação {r.maturity_wait} d",
        "", "## Razões", *([f"- [{m.severidade}] {m.codigo}: {m.detalhe}" for m in r.reasons] or ["- nenhuma"]),
        "", "## Evidência faltante", *([f"- {x}" for x in r.missing_evidence] or ["- nenhuma"]),
        "", "## Próximas leituras (somente leitura)", *([f"- {x}" for x in r.next_read_only_actions] or ["- nenhuma"]),
        "", "## Proibido", *[f"- {x}" for x in r.prohibited_actions],
        "", f"input_hash `{r.input_hash}` · result_hash `{r.result_hash}` · ações externas: {j['external_actions']}", "",
    ]
    return "\n".join(linhas)


def recibo(e: EntradaViabilidade, r: ResultadoViabilidade, resultado_path: Path) -> dict:
    return {"kernel_version": VERSAO_KERNEL, "codigo_sha256": codigo_sha256(), "entrada": e.para_json(), "input_hash": r.input_hash,
            "result_hash": r.result_hash, "resultado_arquivo": resultado_path.name,
            "resultado_sha256": hashlib.sha256(resultado_path.read_bytes()).hexdigest(), "external_actions": 0}


def cmd_evaluate(args) -> int:
    saida = Path(args.saida); saida.mkdir(parents=True, exist_ok=True)
    try:
        e = carregar(Path(args.entrada))
    except (ContratoViabilidadeViolado, KeyError, ValueError, TypeError) as exc:
        print(f"entrada inválida: {exc}", file=sys.stderr)
        return EXIT_ENTRADA_INVALIDA
    r = avaliar(e)
    try:
        verificar_invariantes(e, r)
    except InvarianteViolada as exc:
        print(f"invariante violada: {exc}", file=sys.stderr)
        return EXIT_INVARIANTE
    rp = saida / "resultado.json"
    rp.write_text(json_canonico(r.para_json()) + "\n", encoding="utf-8")
    (saida / "relatorio.md").write_text(relatorio_humano(r), encoding="utf-8")
    (saida / "recibo.json").write_text(json.dumps(recibo(e, r, rp), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{r.verdict.value} · {r.recomendacao.value} · {r.confidence_class.value} · {rp}")
    return EXIT_INSUFICIENTE if r.verdict is Veredito.INSUFFICIENT_EVIDENCE else EXIT_OK


def cmd_frontier(args) -> int:
    saida = Path(args.saida); saida.mkdir(parents=True, exist_ok=True)
    try:
        e = carregar(Path(args.entrada))
    except (ContratoViabilidadeViolado, KeyError, ValueError, TypeError) as exc:
        print(f"entrada inválida: {exc}", file=sys.stderr); return EXIT_ENTRADA_INVALIDA
    fr = fronteira(e)
    if isinstance(fr, Indisponivel):
        (saida / "fronteira.json").write_text(json_canonico({"disponivel": False, "motivo": fr.motivo, "detalhe": fr.detalhe}) + "\n")
        print(f"fronteira indisponível: {fr.motivo}"); return EXIT_INSUFICIENTE
    doc = {"disponivel": True, "moeda": fr.moeda, "cpc_central_micros": str(fr.cpc_central), "rpc_conservador_micros": str(fr.rpc_conservador),
           "required_rpc_micros": str(fr.required_rpc), "required_rpc_multiplier": None if fr.required_rpc_multiplier is None else str(fr.required_rpc_multiplier),
           "queda_cpc_necessaria": str(fr.queda_cpc_necessaria), "folga_cpc_micros": str(fr.folga_cpc), "distancia_economica": str(fr.distancia_economica),
           "iso_contribuicao_zero": [[str(c), str(r)] for c, r in fr.iso_contribuicao_zero],
           "envelope": {"cpc_conservador_micros": str(fr.envelope.cpc_conservador), "rpc_central_micros": str(fr.envelope.rpc_central), "rpc_otimista_micros": str(fr.envelope.rpc_otimista),
                        "contribuicao_central": fr.envelope.contribuicao_central.para_json(), "contribuicao_conservadora": fr.envelope.contribuicao_conservadora.para_json(),
                        "receita_realizada": fr.envelope.receita_realizada, "premissas": [list(p) for p in fr.envelope.premissas], "limitacoes": list(fr.envelope.limitacoes)},
           "input_hash": hash_entrada(e)}
    (saida / "fronteira.json").write_text(json_canonico(doc) + "\n")
    print(f"distância econômica {float(fr.distancia_economica):.3f} · multiplicador RPC {'—' if fr.required_rpc_multiplier is None else f'{float(fr.required_rpc_multiplier):.2f}'}")
    return EXIT_OK


def cmd_simulation(args) -> int:
    saida = Path(args.saida); saida.mkdir(parents=True, exist_ok=True)
    try:
        e = carregar(Path(args.entrada))
    except (ContratoViabilidadeViolado, KeyError, ValueError, TypeError) as exc:
        print(f"entrada inválida: {exc}", file=sys.stderr); return EXIT_ENTRADA_INVALIDA
    env = envelope_conservador(e)
    if isinstance(env, Indisponivel):
        (saida / "simulacao.json").write_text(json_canonico({"disponivel": False, "motivo": f"economia_{env.motivo}"}) + "\n")
        print(f"sem RPC conservador: {env.motivo}"); return EXIT_INSUFICIENTE
    fm = analisar_simulacao(e.simulacao, env.rpc_conservador, normalizar_nao_monotonica=args.normalizar)
    (saida / "simulacao.json").write_text(json_canonico({**fm.para_json(), "input_hash": hash_entrada(e)}) + "\n")
    if isinstance(fm, CurvaIndisponivel):
        print(f"simulação indisponível: {fm.motivo} {fm.detalhe}"); return EXIT_INSUFICIENTE
    print(f"último sustentável {fm.ultimo_ponto_sustentavel and fm.ultimo_ponto_sustentavel.modificacao_micros} · primeiro destrutivo {fm.primeiro_ponto_destrutivo and fm.primeiro_ponto_destrutivo.modificacao_micros}")
    return EXIT_OK


# --------------------------------------------------------------------------- replay com baselines
def _baselines(e: EntradaViabilidade, r: ResultadoViabilidade) -> dict:
    """Regras ingênuas no mesmo vocabulário de decisão. Não são comparadas por 'acerto': só registradas."""
    tem_campanha = e.custo.valor is not None
    env = envelope_conservador(e)
    eco = None if isinstance(env, Indisponivel) else env.economia
    def cpc_medio():
        if e.simulacao is not None and eco is not None:
            fm = analisar_simulacao(e.simulacao, env.rpc_conservador)
            if not isinstance(fm, CurvaIndisponivel):
                return "expandir" if fm.pontos[-1].contribuicao_media_micros > 0 else "parar"
        if eco is None:
            return "inconclusivo"
        return "continuar" if eco.receita_liquida.micros >= eco.custo.micros else "parar"
    return {
        "manter": "continuar" if tem_campanha else "inconclusivo",
        "nao_lancar": "parar" if tem_campanha else "nao_lancar",
        "alocacao_igual": "continuar_igual" if tem_campanha else "lancar_igual",
        "cpc_medio": cpc_medio(),
        "rpc_medio": ("inconclusivo" if eco is None else ("continuar" if eco.rpc >= eco.cpc else "parar")),
    }


def _kernel_marginal(r: ResultadoViabilidade) -> str:
    s = r.simulacao
    if not s or not s.get("disponivel"):
        return "sem_curva"
    if s.get("primeiro_ponto_destrutivo_micros") is None:
        return "expandir_dentro_da_faixa"
    u = s.get("ultimo_ponto_sustentavel_micros")
    return f"expandir_ate_{u}" if u is not None else "nao_expandir"


def cmd_replay(args) -> int:
    saida = Path(args.saida); saida.mkdir(parents=True, exist_ok=True)
    casos = []
    pior = EXIT_OK
    for p in sorted(Path(args.fixtures).glob("*.json")):
        if p.name == "MANIFEST.json":
            continue
        caso = {"fixture": p.stem, "fixture_sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        try:
            e = carregar(p)
        except (ContratoViabilidadeViolado, KeyError, ValueError, TypeError) as exc:
            caso.update(status="entrada_invalida", erro=str(exc)); casos.append(caso); pior = max(pior, EXIT_ENTRADA_INVALIDA); continue
        r = avaliar(e)
        try:
            verificar_invariantes(e, r)
            caso["invariantes"] = "ok"
        except InvarianteViolada as exc:
            caso["invariantes"] = f"violada: {exc}"; pior = EXIT_INVARIANTE
        caso.update(status="ok", verdict=r.verdict.value, recomendacao=r.recomendacao.value, confianca=r.confidence_class.value,
                    input_hash=r.input_hash, result_hash=r.result_hash, baselines=_baselines(e, r), kernel_marginal=_kernel_marginal(r),
                    razoes=[m.codigo for m in r.reasons], faltante=list(r.missing_evidence),
                    contribuicao_observada=None if r.contribution_observed is None else r.contribution_observed.micros,
                    spend_cap=None if r.max_experiment_spend is None else r.max_experiment_spend.micros)
        casos.append(caso)
    doc = {"kernel_version": VERSAO_KERNEL, "codigo_sha256": codigo_sha256(), "casos": casos,
           "declaracao": {"superioridade_declarada": False,
                          "nota": "baselines registradas no mesmo vocabulário; nenhuma é avaliada por 'acerto' porque não há resultado maduro para comparar. A diferença entre `cpc_medio` e `kernel_marginal` é o ponto do ADR §2: média ≠ marginal."}}
    doc["replay_hash"] = hashlib.sha256(json_canonico({k: v for k, v in doc.items() if k != "replay_hash"}).encode()).hexdigest()
    (saida / "replay.json").write_text(json_canonico(doc) + "\n", encoding="utf-8")
    md = ["# Replay do kernel de viabilidade", "", f"kernel `{VERSAO_KERNEL}` · código `{doc['codigo_sha256'][:12]}…` · replay_hash `{doc['replay_hash'][:12]}…`", "",
          "| fixture | veredito | recomendação | confiança | manter | não lançar | igual | CPC médio | RPC médio | kernel marginal | invariantes |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in casos:
        if c["status"] != "ok":
            md.append(f"| {c['fixture']} | entrada inválida | — | — | — | — | — | — | — | — | — |"); continue
        b = c["baselines"]
        md.append(f"| {c['fixture']} | {c['verdict']} | {c['recomendacao']} | {c['confianca']} | {b['manter']} | {b['nao_lancar']} | {b['alocacao_igual']} | {b['cpc_medio']} | {b['rpc_medio']} | {c['kernel_marginal']} | {c['invariantes']} |")
    md += ["", "Nenhuma superioridade é declarada: não há resultado maduro contra o qual medir. A tabela mostra onde regras ingênuas e o kernel divergem e por quê.", ""]
    (saida / "replay.md").write_text("\n".join(md), encoding="utf-8")
    print(f"{len(casos)} casos · replay_hash {doc['replay_hash'][:12]} · exit {pior}")
    return pior


def cmd_verify(args) -> int:
    p = Path(args.recibo)
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
        e = EntradaViabilidade.de_json(rec["entrada"])
    except (ContratoViabilidadeViolado, KeyError, ValueError, TypeError) as exc:
        print(f"recibo inválido: {exc}", file=sys.stderr); return EXIT_ENTRADA_INVALIDA
    falhas = []
    if rec.get("input_hash") != hash_entrada(e):
        falhas.append("input_hash não bate com a entrada do recibo")
    r = avaliar(e)
    if rec.get("result_hash") != r.result_hash:
        falhas.append("result_hash não reproduz (código ou entrada mudaram, ou recibo adulterado)")
    if rec.get("codigo_sha256") != codigo_sha256():
        falhas.append("codigo_sha256 difere do código atual")
    rp = p.with_name(rec.get("resultado_arquivo", "resultado.json"))
    if rp.exists() and hashlib.sha256(rp.read_bytes()).hexdigest() != rec.get("resultado_sha256"):
        falhas.append("resultado.json difere do recibo")
    try:
        verificar_invariantes(e, r)
    except InvarianteViolada as exc:
        falhas.append(f"invariante: {exc}")
    if falhas:
        print("recibo NÃO verificado: " + "; ".join(falhas), file=sys.stderr); return EXIT_INVARIANTE
    print(f"recibo verificado · result_hash {r.result_hash[:12]} reproduzido"); return EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="volc-dil viability", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome, fn in (("evaluate", cmd_evaluate), ("frontier", cmd_frontier), ("simulation", cmd_simulation)):
        s = sub.add_parser(nome); s.add_argument("entrada"); s.add_argument("--saida", required=True)
        if nome == "simulation":
            s.add_argument("--normalizar", action="store_true", help="remove pontos não monotônicos COM recibo")
        s.set_defaults(fn=fn)
    s = sub.add_parser("replay"); s.add_argument("fixtures"); s.add_argument("--saida", required=True); s.set_defaults(fn=cmd_replay)
    s = sub.add_parser("verify"); s.add_argument("recibo"); s.set_defaults(fn=cmd_verify)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
