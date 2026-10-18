"""Gera as fixtures do kernel de viabilidade (determinístico) em fixtures/viability/ + MANIFEST.json.

Contrato v2: a tolerância de perda carrega uma `Autorizacao` de laboratório (AUTH-LAB-0001, issuer
"owner:lab-fixture", hash calculado) e câmbio/revshare/imposto são versionados (effective_at/disponivel_em
<= as_of). Nenhuma autorização aqui é do owner real: prova integridade da fixture, não autoria.

A fixture "senac_sanitizada" é DERIVADA do experimento já versionado em
tools/freedom-lab/experimentos/senac-shadow-20261015/resultado.json (agregados da janela madura),
com o identificador substituído por um pseudônimo (sha256 truncado). Nenhum número da Senac está
no código do kernel; está aqui, na fixture, e é lido do artefato sanitizado. A janela é derivada
do arquivo, não declarada: `janela_madura.dias` dias maduros terminando em `corte_maturidade`
(inicio = corte - (dias - 1)), `fim` = `as_of` do arquivo, `dias_imaturos` = parametros.dias_imaturos;
o gerador confere que maduros + imaturos == span e recusa gerar se não bater.

Janela-base das demais fixtures: 16 dias maduros (2026-09-26..2026-10-11) + 3 imaturos (2026-10-12..14),
span 19 ≤ as_of 2026-10-15 — o contrato v2 recusa contagens que excedem o span.

Uso (da raiz do lab): .venv/bin/python -I scripts/viability_gerar_fixtures.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

RAIZ_LAB = Path(__file__).resolve().parents[1]
RAIZ_REPO = RAIZ_LAB.parents[1]
sys.path.insert(0, str(RAIZ_LAB / "src"))

from volc_dil.contracts import Dinheiro  # noqa: E402
from volc_dil.viability.contrato import (  # noqa: E402
    Autorizacao, Cambio, EntradaViabilidade, Evidencia, JanelaObservada, MedidaContagem, MedidaMonetaria, PerdaMaxima, PontoSimulacao,
    SimulacaoEntrada, Taxa, json_canonico,
)

SAIDA = RAIZ_LAB / "fixtures" / "viability"
AS_OF = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
# Parâmetros versionados (câmbio, revshare, imposto) e a autorização da tolerância valem desde o início da janela
# e foram conhecidos no mesmo instante: nunca depois do as_of.
EFETIVO = datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc)
AUTORIZACAO = Autorizacao.emitir(authorization_id="AUTH-LAB-0001", version="1", issuer="owner:lab-fixture", effective_at=EFETIVO, expires_at=None, disponivel_em=EFETIVO)
SENAC = RAIZ_REPO / "tools" / "freedom-lab" / "experimentos" / "senac-shadow-20261015" / "resultado.json"


def mon(valor, moeda, ev=Evidencia.OBSERVED, moeda_ev=Evidencia.OBSERVED, fonte=""):
    if valor is None:
        return MedidaMonetaria(None, ev, moeda_ev, AS_OF, fonte)
    return MedidaMonetaria(Dinheiro.de_decimal(str(valor), moeda), ev, moeda_ev, AS_OF, fonte)


def cnt(v, ev=Evidencia.OBSERVED):
    return MedidaContagem(v, ev, AS_OF)


def cambio(taxa=None, ev=Evidencia.ESTIMATED, prov="literal_app", de="USD", para="BRL"):
    if taxa is None:
        return Cambio(None, de, para, "ausente", Evidencia.ABSENT)
    return Cambio(Decimal(str(taxa)), de, para, prov, ev, effective_at=EFETIVO, disponivel_em=EFETIVO, versao=f"{prov}-2026-10-15")


def taxa(v=None, ev=Evidencia.ATTESTED, prov="tela"):
    if v is None:
        return Taxa(None, Evidencia.UNKNOWN, "ausente")
    return Taxa(Decimal(str(v)), ev, prov, effective_at=EFETIVO, disponivel_em=EFETIVO, versao=f"{prov}-2026-10-15")


def perda(v=None, h=None):
    if v is None:
        return PerdaMaxima(None, None, None)
    return PerdaMaxima(Dinheiro.de_decimal(str(v), "BRL"), h, AUTORIZACAO)


def base(cid, **kw):
    d = dict(candidato_id=cid, vertical="generica", pais="BR", fonte_custo="google_ads", fonte_receita="joinads", as_of=AS_OF,
             janela=JanelaObservada("2026-09-26", "2026-10-14", 16, 3, dias_custo_maduro=16, dias_receita_madura=16, dias_custo_sem_receita=0, cobertura_receita_ppm=1_000_000),
             cliques=cnt(634), custo=mon("554.75", "BRL"),
             receita=mon("40.79", "BRL"), cambio=cambio(), revshare=taxa(1), imposto=taxa(), perda_maxima=perda(300, 14))
    d.update(kw)
    return EntradaViabilidade(**d)


def sim(pontos, tipo="CPC_BID", estrategia="MANUAL_CPC"):
    return SimulacaoEntrada(tipo, "BRL", tuple(PontoSimulacao(*p) for p in pontos), AS_OF, estrategia)


def senac_sanitizada() -> tuple[EntradaViabilidade, dict]:
    d = json.loads(SENAC.read_text())
    jm = d["janela_madura"]
    fx = Decimal(str(d["parametros"]["cambio_usd_brl"]))
    pseudo = "camp-" + hashlib.sha256(str(d["campanha"]).encode()).hexdigest()[:10]
    receita_usd = (Decimal(str(jm["receita_brl"])) / fx).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
    # janela derivada do experimento: maduros terminam no corte de maturidade; imaturos vão do corte ao as_of do arquivo
    dias_maduros, dias_imaturos = int(jm["dias"]), int(d["parametros"]["dias_imaturos"])
    corte, fim = date.fromisoformat(d["corte_maturidade"]), date.fromisoformat(d["as_of"])
    inicio = corte - timedelta(days=dias_maduros - 1)
    span = (fim - inicio).days + 1
    if dias_maduros + dias_imaturos != span:
        raise ValueError(f"senac: janela_madura.dias + dias_imaturos ({dias_maduros} + {dias_imaturos}) != span {span} ({inicio}..{fim}); fixture não gerada")
    e = base(pseudo, vertical="educacao", janela=JanelaObservada(inicio.isoformat(), fim.isoformat(), dias_maduros, dias_imaturos),
             cliques=cnt(int(jm["cliques"])), custo=mon(str(jm["custo_brl"]), "BRL"),
             receita=mon(str(receita_usd), "USD", Evidencia.RECONCILED, Evidencia.ATTESTED, "joinads"),
             cambio=cambio(fx), revshare=taxa(1), imposto=taxa(), perda_maxima=perda(300, 14))
    # proveniência sem nome nem caminho da campanha: só o sha256 do artefato sanitizado de origem
    sobre = {"derivada_de": "experimento shadow versionado em tools/freedom-lab/experimentos (resultado.json)",
             "fonte_sha256": hashlib.sha256(SENAC.read_bytes()).hexdigest(),
             "janela": f"{dias_maduros} dias maduros até corte_maturidade {corte.isoformat()} + {dias_imaturos} imaturos até as_of {fim.isoformat()} (span {span})",
             "nota": "receita_usd = receita_brl / cambio fixo do experimento; moeda JoinAds atestada; id pseudonimizado por sha256; "
                     "tolerância com autorização de laboratório (AUTH-LAB-0001, issuer owner:lab-fixture), não do owner real"}
    return e, sobre


ADR_DESTRUTIVA = [(50_000, 500, 20_000_000), (100_000, 1000, 80_000_000), (200_000, 1300, 160_000_000)]


def fixtures() -> dict[str, tuple[EntradaViabilidade, dict]]:
    s, sobre_s = senac_sanitizada()
    fav = base("cand-favoravel", receita=mon("800", "BRL"), cambio=cambio(None, de="BRL", para="BRL"))
    return {
        "senac_sanitizada": (s, sobre_s),
        "campanha_favoravel": (fav, {"nota": "rpc 1,26 > cpc 0,875; moeda observada"}),
        "proximo_do_equilibrio": (base("cand-equilibrio", receita=mon("600", "BRL"), cambio=cambio(None, de="BRL", para="BRL")), {"nota": "central +45, conservador < 0"}),
        "moeda_desconhecida": (base("cand-moeda-desc", receita=mon("7.77", "USD", Evidencia.RECONCILED, Evidencia.UNKNOWN), cambio=cambio()), {"nota": "moeda da receita não se sabe"}),
        "moeda_apenas_atestada": (base("cand-atestada", receita=mon("200", "USD", Evidencia.RECONCILED, Evidencia.ATTESTED), cambio=cambio("5.25")), {"nota": "favorável mas só atestada → test_with_cap no máximo"}),
        "cambio_ausente": (base("cand-sem-cambio", receita=mon("7.77", "USD", Evidencia.RECONCILED, Evidencia.ATTESTED), cambio=cambio(None)), {"nota": "USD sem taxa"}),
        "custo_ausente": (base("cand-sem-custo", custo=mon(None, "BRL", Evidencia.ABSENT, Evidencia.UNKNOWN)), {}),
        "receita_ausente": (base("cand-sem-receita", receita=mon(None, "USD", Evidencia.ABSENT, Evidencia.UNKNOWN), cambio=cambio("5.25")), {}),
        "receita_zero_observada": (base("cand-receita-zero", receita=mon("0", "BRL"), cambio=cambio(None, de="BRL", para="BRL")), {"nota": "zero confirmado ≠ ausente"}),
        "receita_atrasada": (base("cand-receita-late", receita=mon(None, "USD", Evidencia.UNKNOWN, Evidencia.ATTESTED), cambio=cambio("5.25"), flags_qualidade=("receita_late",)), {"nota": "esperada e não publicada"}),
        "dados_imaturos": (base("cand-imaturo", janela=JanelaObservada("2026-10-13", "2026-10-15", 1, 2, dias_custo_maduro=1, dias_receita_madura=1, cobertura_receita_ppm=1_000_000), receita=mon("60", "BRL", Evidencia.IMMATURE, Evidencia.OBSERVED), cambio=cambio(None, de="BRL", para="BRL")), {}),
        "limite_financeiro_ausente": (base("cand-sem-perda", receita=mon("600", "BRL"), cambio=cambio(None, de="BRL", para="BRL"), perda_maxima=perda()), {}),
        "simulacao_inexistente": (base("cand-sem-sim", receita=mon("800", "BRL"), cambio=cambio(None, de="BRL", para="BRL")), {"nota": "sem pontos → diagnóstico, não erro"}),
        "simulacao_pontos_duplicados": (base("cand-sim-dup", receita=mon("800", "BRL"), cambio=cambio(None, de="BRL", para="BRL"),
                                             simulacao=sim([(100_000, 1000, 80_000_000), (100_000, 1000, 80_000_000), (150_000, 1200, 120_000_000)])), {}),
        "simulacao_nao_monotonica": (base("cand-sim-nm", receita=mon("800", "BRL"), cambio=cambio(None, de="BRL", para="BRL"),
                                          simulacao=sim([(100_000, 1000, 80_000_000), (150_000, 900, 120_000_000), (200_000, 1300, 160_000_000)])), {}),
        "curva_ultimos_20pct_destroem": (base("cand-curva-20", cliques=cnt(1000), custo=mon("80", "BRL"), receita=mon("160", "BRL"),
                                              cambio=cambio(None, de="BRL", para="BRL"), simulacao=sim(ADR_DESTRUTIVA)),
                                         {"nota": "últimos 300 cliques (23%) custam 0,27 marginal vs rpc 0,144"}),
        "roas_medio_bom_marginal_destroi": (base("cand-roas-medio", cliques=cnt(1300), custo=mon("160", "BRL"), receita=mon("208", "BRL"),
                                                 cambio=cambio(None, de="BRL", para="BRL"), simulacao=sim(ADR_DESTRUTIVA)),
                                            {"nota": "ROAS médio 1,3 no último ponto; segmento final destrói valor"}),
        "campanha_nova_sem_historico": (base("cand-novo", janela=JanelaObservada("2026-10-15", "2026-10-15", 0, 0), cliques=cnt(None, Evidencia.ABSENT),
                                             custo=mon(None, "BRL", Evidencia.ABSENT, Evidencia.UNKNOWN), receita=mon(None, "BRL", Evidencia.ABSENT, Evidencia.UNKNOWN),
                                             cambio=cambio(None, de="BRL", para="BRL"), fonte_custo="pesquisa", fonte_receita="pesquisa",
                                             cpc_intervalo=(Dinheiro.de_decimal("0.30", "BRL"), Dinheiro.de_decimal("0.60", "BRL")),
                                             rpc_intervalo=(Dinheiro.de_decimal("0.70", "BRL"), Dinheiro.de_decimal("1.10", "BRL"))),
                                        {"nota": "só pesquisa (nunca autoriza verba) + tolerância do owner"}),
    }


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    shas = {}
    for nome, (e, sobre) in sorted(fixtures().items()):
        doc = {"_sobre": {"gerador": "scripts/viability_gerar_fixtures.py", **sobre}, "entrada": e.para_json()}
        p = SAIDA / f"{nome}.json"
        p.write_text(json_canonico(doc) + "\n", encoding="utf-8")
        shas[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    (SAIDA / "MANIFEST.json").write_text(json.dumps({"gerador": "scripts/viability_gerar_fixtures.py", "sha256": shas}, indent=1, sort_keys=True) + "\n")
    print(f"{len(shas)} fixtures em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
