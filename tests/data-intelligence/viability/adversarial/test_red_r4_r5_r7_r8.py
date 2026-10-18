"""RED, rodada 2 — achados R4 (revshare/imposto não observados ≠ confiança alta), R5 (janela consistente
com o as_of e com o próprio intervalo), R7 (nenhuma moeda por padrão nos adapters) e R8 (recibo da CLI
cobre `contracts/money.py` e `contracts/vocab.py`).

Escrita contra o candidato V2 aprovado (34a5f960). Cada teste diz no docstring o que a V2 faz hoje e o que
o comportamento-alvo fixado pelo integrador exige. "Falha por construção" = o contrato/adapter nem aceita a
forma pedida; "falha de asserção" = aceita e devolve o valor errado. R6 fica de fora por decisão documentada.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from volc_dil.contracts import Dinheiro
from volc_dil.viability import adaptadores
from volc_dil.viability.adaptadores import de_ledger_campanha_dia, de_pautador_card
from volc_dil.viability.contrato import ContratoViabilidadeViolado, EntradaViabilidade, Evidencia, JanelaObservada, Taxa
from volc_dil.viability.gate import Confianca, Veredito, avaliar

from _entradas import AS_OF, EFETIVO, entrada

RAIZ = Path(__file__).resolve().parents[4]
LAB = RAIZ / "experiments" / "data-intelligence-lab"
CLI = LAB / "scripts" / "viability_cli.py"
FIXTURES = LAB / "fixtures" / "viability"
SENAC = FIXTURES / "senac_sanitizada.json"


# =============================================================================================== R4
def _taxa(valor: str, ev: Evidencia, prov: str) -> Taxa:
    """Taxa VERSIONADA com valor (effective_at/disponivel_em obrigatórios quando há valor)."""
    return Taxa(valor=Decimal(valor), evidencia=ev, proveniencia=prov, effective_at=EFETIVO, disponivel_em=EFETIVO, versao=f"{prov}-red")


def _taxa_sem_valor(ev: Evidencia) -> Taxa:
    return Taxa(valor=None, evidencia=ev, proveniencia="ausente")


def _forte(**kw):
    """Tudo forte: receita 800 BRL OBSERVED, moeda observada, sem câmbio, 634 cliques, 16 dias maduros, cobertura completa,
    tolerância autorizada. Só revshare/imposto variam por teste. Com revshare e imposto OBSERVED o gate deve poder dar HIGH."""
    e = entrada(receita="800", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.OBSERVED,
                perda="300", horizonte=14)
    return replace(e, **kw)


REVSHARE_OBS = _taxa("1", Evidencia.OBSERVED, "contrato")
IMPOSTO_OBS = _taxa("0.05", Evidencia.OBSERVED, "nota_fiscal")


def _codigos(r) -> set[str]:
    return {m.codigo for m in r.reasons}


def test_red_r4_controle_revshare_e_imposto_observados_permitem_high():
    """Controle (deve passar antes e depois): revshare OBSERVED (contrato) + imposto OBSERVED (nota fiscal), todo o resto forte
    → `already_profitable` com confiança HIGH continua alcançável. Sem este controle, a correção poderia 'passar' matando o HIGH."""
    r = avaliar(_forte(revshare=REVSHARE_OBS, imposto=IMPOSTO_OBS))
    assert r.verdict is Veredito.ALREADY_PROFITABLE, (r.verdict, _codigos(r))
    assert r.confidence_class is Confianca.HIGH, (r.confidence_class, _codigos(r))


@pytest.mark.parametrize("ev", [Evidencia.ATTESTED, Evidencia.ESTIMATED], ids=lambda e: e.value)
def test_red_r4a_revshare_nao_observado_nunca_permite_high(ev):
    """R4. revshare 1 com evidência ATTESTED ("tela") ou ESTIMATED, imposto OBSERVED, resto forte.

    V2 (34a5f960) está errada porque `_confianca` só olha moeda, câmbio, custo, cliques, volume, receita realizada e governança:
    um revshare lido da tela entra na economia com o mesmo peso de um contrato e o gate devolve HIGH. O valor declarado
    continua aplicado (ver r4c); só a confiança é capada em MEDIUM com razão tipada `revshare_<evidencia>`.
    """
    r = avaliar(_forte(revshare=_taxa("1", ev, "tela"), imposto=IMPOSTO_OBS))
    assert r.confidence_class is not Confianca.HIGH, f"V2 devolve HIGH com revshare {ev.value}: {_codigos(r)}"
    assert r.confidence_class.ordem() <= Confianca.MEDIUM.ordem()
    assert f"revshare_{ev.value}" in _codigos(r), _codigos(r)


def test_red_r4a_revshare_unknown_sem_valor_nunca_permite_high():
    """R4. revshare sem valor (UNKNOWN): a economia não aplica nada (receita bruta = líquida) e hoje o gate dá HIGH como se
    o publisher recebesse 100%. Esperado: ≤ MEDIUM com razão `revshare_unknown`."""
    r = avaliar(_forte(revshare=_taxa_sem_valor(Evidencia.UNKNOWN), imposto=IMPOSTO_OBS))
    assert r.confidence_class is not Confianca.HIGH, f"V2 devolve HIGH sem revshare: {_codigos(r)}"
    assert "revshare_unknown" in _codigos(r), _codigos(r)


@pytest.mark.parametrize("ev", [Evidencia.ATTESTED, Evidencia.ESTIMATED], ids=lambda e: e.value)
def test_red_r4b_imposto_nao_observado_nunca_permite_high(ev):
    """R4. imposto 0,05 ATTESTED/ESTIMATED, revshare OBSERVED, resto forte. Hoje: HIGH. Esperado: ≤ MEDIUM, razão `imposto_<ev>`."""
    r = avaliar(_forte(revshare=REVSHARE_OBS, imposto=_taxa("0.05", ev, "planilha")))
    assert r.confidence_class is not Confianca.HIGH, f"V2 devolve HIGH com imposto {ev.value}: {_codigos(r)}"
    assert f"imposto_{ev.value}" in _codigos(r), _codigos(r)


def test_red_r4b_imposto_unknown_sem_valor_nunca_permite_high():
    """R4. imposto desconhecido (o default de todas as fixtures e do helper de teste): nada é descontado e hoje o gate dá HIGH.
    Esperado: ≤ MEDIUM com razão tipada `imposto_unknown`."""
    r = avaliar(_forte(revshare=REVSHARE_OBS, imposto=_taxa_sem_valor(Evidencia.UNKNOWN)))
    assert r.confidence_class is not Confianca.HIGH, f"V2 devolve HIGH sem imposto: {_codigos(r)}"
    assert "imposto_unknown" in _codigos(r), _codigos(r)


def test_red_r4c_valor_declarado_continua_aplicado_sem_desconto_inventado():
    """R4 (guarda da correção; passa hoje e tem de continuar passando). A cap de confiança NÃO pode virar desconto:
    revshare 0,7 ATTESTED e revshare 0,7 OBSERVED produzem exatamente os mesmos números (contribuição observada e
    conservadora, RPC, break-even, cenários); e 0,7 ≠ 1 prova que o valor declarado é mesmo aplicado."""
    atestado = avaliar(_forte(revshare=_taxa("0.7", Evidencia.ATTESTED, "tela"), imposto=IMPOSTO_OBS))
    observado = avaliar(_forte(revshare=_taxa("0.7", Evidencia.OBSERVED, "contrato"), imposto=IMPOSTO_OBS))
    cheio = avaliar(_forte(revshare=REVSHARE_OBS, imposto=IMPOSTO_OBS))
    for campo in ("contribution_observed", "contribution_conservative", "observed_rpc", "conservative_affordable_cpc", "break_even_cpc", "stress"):
        assert getattr(atestado, campo) == getattr(observado, campo), campo
    assert atestado.contribution_observed != cheio.contribution_observed, "revshare 0,7 não foi aplicado"
    assert atestado.contribution_observed.micros < cheio.contribution_observed.micros


def test_red_r4d_cap_vale_tambem_no_veredito_inviavel():
    """R4 no ramo `unviable_under_declared_scenarios`: lá a confiança sai de `c2 = HIGH if moeda_provada and conf is HIGH`.
    Receita 100 BRL observada (inviável), revshare ATTESTED → hoje HIGH. Esperado: ≤ MEDIUM, mesma razão tipada."""
    e = entrada(receita="100", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.OBSERVED, perda="300", horizonte=14)
    r = avaliar(replace(e, imposto=IMPOSTO_OBS))  # revshare do helper = ATTESTED ("tela")
    assert r.verdict is Veredito.UNVIABLE_UNDER_DECLARED_SCENARIOS, r.verdict
    assert r.confidence_class is not Confianca.HIGH, f"V2 devolve HIGH no ramo inviável com revshare atestado: {_codigos(r)}"
    assert "revshare_attested" in _codigos(r)


# =============================================================================================== R5
def _janela(inicio: str, fim: str, **kw) -> JanelaObservada:
    return JanelaObservada(inicio=inicio, fim=fim, **kw)


def test_red_r5_controle_janela_consistente_e_fim_igual_ao_as_of_constroem():
    """Controle: 16 dias (26/09..11/10) com 16 maduros + 0 imaturos constrói; `fim` == data do as_of (15/10) também constrói."""
    entrada(janela=_janela("2026-09-26", "2026-10-11", dias_maduros=16, dias_imaturos=0, cobertura_receita_ppm=1_000_000))
    entrada(janela=_janela("2026-10-01", "2026-10-15", dias_maduros=10, dias_imaturos=5, cobertura_receita_ppm=1_000_000))


def test_red_r5a_fim_posterior_ao_as_of_e_lookahead_por_construcao():
    """R5. `janela.fim` = 16/10 com `as_of` = 15/10 12:00 UTC.

    V2 (34a5f960) aceita: `EntradaViabilidade` confere `disponivel_em`/`effective_at` contra o as_of, mas não a janela —
    uma janela que termina no futuro passa como observada. Esperado: ContratoViabilidadeViolado na construção.
    """
    with pytest.raises(ContratoViabilidadeViolado):
        entrada(janela=_janela("2026-10-01", "2026-10-16", dias_maduros=10, dias_imaturos=0, cobertura_receita_ppm=1_000_000))


def test_red_r5b_dias_maduros_acima_do_intervalo_e_recusado():
    """R5. inicio 12/10, fim 15/10 (4 dias) e 16 dias maduros — exatamente o que a fixture Senac declara hoje.
    V2 aceita (só confere inicio <= fim). Esperado: ContratoViabilidadeViolado em `JanelaObservada` ou em `EntradaViabilidade`."""
    with pytest.raises(ContratoViabilidadeViolado):
        j = _janela("2026-10-12", "2026-10-15", dias_maduros=16, dias_imaturos=3)
        entrada(janela=j)


def test_red_r5c_maduros_mais_imaturos_acima_do_intervalo_e_recusado():
    """R5. 10 dias (01/10..10/10), 7 maduros + 4 imaturos = 11 > 10. Hoje aceito. Esperado: recusado."""
    with pytest.raises(ContratoViabilidadeViolado):
        j = _janela("2026-10-01", "2026-10-10", dias_maduros=7, dias_imaturos=4, cobertura_receita_ppm=1_000_000)
        entrada(janela=j)


def test_red_r5d_dias_receita_madura_acima_do_intervalo_e_recusado():
    """R5. 10 dias, 5 maduros, `dias_receita_madura` = 12 > 10. Hoje aceito (o contrato só compara custo com maduros)."""
    with pytest.raises(ContratoViabilidadeViolado):
        j = _janela("2026-10-01", "2026-10-10", dias_maduros=5, dias_imaturos=0, dias_custo_maduro=5, dias_receita_madura=12)
        entrada(janela=j)


def test_red_r5e_ledger_com_dia_posterior_ao_as_of_e_recusado():
    """R5 pelo adapter: uma linha do ledger datada 20/10 com `disponivel_em` <= as_of (15/10) — a janela derivada termina no futuro.
    Hoje `de_ledger_campanha_dia` monta `JanelaObservada(dias[0], dias[-1])` e a entrada passa. Esperado: ContratoViabilidadeViolado."""
    linhas = [_linha("2026-10-13", 100_000_000, 300, 150_000_000), _linha("2026-10-20", 100_000_000, 300, 150_000_000)]
    with pytest.raises(ContratoViabilidadeViolado):
        de_ledger_campanha_dia("cand-red-r5e", linhas, as_of=AS_OF)


def _invariantes_da_janela(doc: dict) -> list[str]:
    """Checagem ARITMÉTICA, independente do contrato: o que o contrato V2 corrigido tem de impor."""
    e = doc.get("entrada", doc)
    j = e["janela"]
    ini, fim = date.fromisoformat(j["inicio"]), date.fromisoformat(j["fim"])
    as_of = datetime.fromisoformat(e["as_of"]).astimezone(timezone.utc).date()
    span = (fim - ini).days + 1
    falhas = []
    if fim > as_of:
        falhas.append(f"fim {fim} > as_of {as_of}")
    if j["dias_maduros"] + j.get("dias_imaturos", 0) > span:
        falhas.append(f"dias_maduros {j['dias_maduros']} + dias_imaturos {j.get('dias_imaturos', 0)} > intervalo {span} ({ini}..{fim})")
    for k in ("dias_custo_maduro", "dias_receita_madura"):
        if j.get(k) is not None and j[k] > span:
            falhas.append(f"{k} {j[k]} > intervalo {span}")
    return falhas


def test_red_r5f_fixture_senac_respeita_a_janela():
    """R5 na fixture Senac (`senac_sanitizada.json`). Hoje: inicio 12/10, fim 15/10, 16 maduros + 3 imaturos → 19 dias em 4.
    O gerador usa `corte_maturidade` como início e `as_of` como fim, mas copia `dias` da janela madura inteira.
    Esperado depois de B corrigir o gerador: a aritmética fecha E o contrato carrega a fixture sem violar."""
    doc = json.loads(SENAC.read_text(encoding="utf-8"))
    assert _invariantes_da_janela(doc) == [], _invariantes_da_janela(doc)
    EntradaViabilidade.de_json(doc["entrada"])


@pytest.mark.parametrize("fixture", sorted(p.name for p in FIXTURES.glob("*.json") if p.name != "MANIFEST.json"))
def test_red_r5g_toda_fixture_versionada_respeita_a_janela(fixture):
    """R5 em TODAS as fixtures versionadas (a mesma regra vale para o replay). As fixtures do `base()` do gerador declaram
    26/09..11/10 (16 dias) com 16 maduros + 3 imaturos = 19: também violam, não só a Senac. Quando o contrato passar a impor
    a regra, essas fixtures param de carregar — este teste é o aviso antecipado."""
    doc = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    assert _invariantes_da_janela(doc) == [], _invariantes_da_janela(doc)
    EntradaViabilidade.de_json(doc.get("entrada", doc))


# =============================================================================================== R7
def _linha(dia: str, custo: int, cliques: int, receita, *, status: str = "observed", maduro: bool = True, **extra) -> dict:
    l = {"dia": dia, "custo_micros": custo, "custo_moeda": "BRL", "custo_moeda_evidencia": "observed", "cliques": cliques,
         "receita_micros": receita, "receita_moeda": "BRL", "receita_moeda_evidencia": "observed", "receita_status": status,
         "maduro": maduro, "disponivel_em": AS_OF.isoformat()}
    l.update(extra)
    return l


def _sem(l: dict, *chaves: str) -> dict:
    for k in chaves:
        l.pop(k, None)
    return l


def _medida_degradada_ou_recusa(construir, medida: str):
    """Aceita as duas correções admitidas pelo integrador: (a) a medida vira valor=None / evidência UNKNOWN / moeda UNKNOWN com flag
    `moeda_ausente`; (b) fail-closed, ContratoViabilidadeViolado mencionando `moeda_ausente`. Devolve a entrada no caso (a), None no (b)."""
    try:
        e = construir()
    except ContratoViabilidadeViolado as exc:
        assert "moeda_ausente" in str(exc), f"recusa sem o motivo tipado `moeda_ausente`: {exc}"
        return None
    m = getattr(e, medida)
    assert m.valor is None, f"V2 inventa moeda por padrão: {medida}.valor = {m.valor}"
    assert m.evidencia is Evidencia.UNKNOWN, m.evidencia
    assert m.moeda_evidencia is Evidencia.UNKNOWN, m.moeda_evidencia
    assert "moeda_ausente" in (*m.flags_qualidade, *e.flags_qualidade), (m.flags_qualidade, e.flags_qualidade)
    return e


def test_red_r7_controle_ledger_com_moedas_declaradas_constroi_dinheiro():
    """Controle: linhas com `custo_moeda` e `receita_moeda` declaradas → Dinheiro em BRL dos dois lados (passa hoje e depois)."""
    e = de_ledger_campanha_dia("cand-red-r7-ctl", [_linha("2026-10-13", 100_000_000, 300, 150_000_000)], as_of=AS_OF)
    assert e.custo.valor == Dinheiro(100_000_000, "BRL") and e.receita.valor == Dinheiro(150_000_000, "BRL")
    assert e.custo.moeda_evidencia is Evidencia.OBSERVED


def test_red_r7a_ledger_sem_custo_moeda_nao_inventa_brl():
    """R7. Linhas com custo em micros mas SEM `custo_moeda` (nem `custo_moeda_evidencia`).

    V2 (34a5f960) está errada porque `_moeda_unica(linhas, "custo_moeda", "custo", "BRL")` devolve o literal "BRL" quando
    nenhuma linha declara moeda: o custo vira `Dinheiro(300 BRL)` com `moeda_evidencia` UNKNOWN e a economia roda em cima
    de uma moeda que ninguém reportou. Esperado: valor=None, UNKNOWN, flag `moeda_ausente` — ou recusa tipada.
    """
    linhas = [_sem(_linha(f"2026-10-{d:02d}", 100_000_000, 300, 150_000_000), "custo_moeda", "custo_moeda_evidencia") for d in (11, 12, 13)]
    e = _medida_degradada_ou_recusa(lambda: de_ledger_campanha_dia("cand-red-r7a", linhas, as_of=AS_OF), "custo")
    if e is not None:
        r = avaliar(e)
        assert r.verdict in (Veredito.INSUFFICIENT_EVIDENCE,), f"veredito nascido de moeda inventada: {r.verdict.value}"


def test_red_r7b_ledger_sem_receita_moeda_nao_inventa_usd():
    """R7. Linhas com receita em micros mas SEM `receita_moeda`: hoje o adapter constrói `Dinheiro(…, "USD")` — a moeda do
    JoinAds vira literal do código, exatamente o que o contrato chama de 'moeda atestada promovida'. Esperado como em r7a."""
    linhas = [_sem(_linha(f"2026-10-{d:02d}", 100_000_000, 300, 150_000_000), "receita_moeda", "receita_moeda_evidencia") for d in (11, 12, 13)]
    e = _medida_degradada_ou_recusa(lambda: de_ledger_campanha_dia("cand-red-r7b", linhas, as_of=AS_OF), "receita")
    if e is not None:
        assert e.custo.valor == Dinheiro(300_000_000, "BRL"), "o custo (declarado) continua real"


def test_red_r7c_ledger_sem_nenhuma_moeda_nao_inventa_par_de_cambio():
    """R7. Sem `custo_moeda` nem `receita_moeda` em nenhuma linha e sem dict de câmbio: hoje a entrada sai com
    `Cambio(taxa=None, de="USD", para="BRL")` — um par USD→BRL que ninguém declarou. Esperado: nenhum par inventado
    (de/para vazios ou iguais à moeda desconhecida), ou recusa tipada."""
    linhas = [_sem(_linha(f"2026-10-{d:02d}", 100_000_000, 300, 150_000_000), "custo_moeda", "custo_moeda_evidencia", "receita_moeda", "receita_moeda_evidencia") for d in (11, 12, 13)]
    try:
        e = de_ledger_campanha_dia("cand-red-r7c", linhas, as_of=AS_OF)
    except ContratoViabilidadeViolado as exc:
        assert "moeda_ausente" in str(exc)
        return
    assert e.cambio.taxa is None
    assert not (e.cambio.de == "USD" and e.cambio.para == "BRL"), f"par de câmbio inventado: {e.cambio.de}->{e.cambio.para}"


def test_red_r7d_cambio_com_taxa_sem_par_declarado_e_recusado():
    """R7 em `_cambio`: dict de câmbio com taxa 5,25 versionada mas SEM `de`/`para`. Hoje o adapter completa o par com as
    moedas das medidas (`d.get("de", de)`) — uma taxa sem par vira USD→BRL por inferência. Esperado: ContratoViabilidadeViolado,
    ou câmbio ausente (taxa=None) com a taxa descartada; nunca um `Cambio` com taxa e par inferido."""
    cambio = {"taxa": "5.25", "evidencia": "observed", "proveniencia": "ptax", "effective_at": EFETIVO.isoformat(), "disponivel_em": EFETIVO.isoformat(), "versao": "ptax-red"}
    linhas = [_linha(f"2026-10-{d:02d}", 100_000_000, 300, 150_000_000, receita_moeda="USD") for d in (11, 12, 13)]
    try:
        e = de_ledger_campanha_dia("cand-red-r7d", linhas, as_of=AS_OF, cambio=cambio)
    except ContratoViabilidadeViolado:
        return
    assert e.cambio.taxa is None, f"V2 infere o par do câmbio: {e.cambio.de}->{e.cambio.para} taxa {e.cambio.taxa}"


def test_red_r7e_de_pautador_card_exige_moeda_explicita():
    """R7. `de_pautador_card(card, as_of=…)` sem `moeda`: hoje `moeda: str = "BRL"` no assinatura e a entrada nasce com
    `Cambio(None, "BRL", "BRL")` — a moeda do card é um literal do código. Esperado: parâmetro sem default (TypeError) ou
    ContratoViabilidadeViolado."""
    assert inspect.signature(de_pautador_card).parameters["moeda"].default is inspect.Parameter.empty, "`moeda` ainda tem default em de_pautador_card"
    with pytest.raises((TypeError, ContratoViabilidadeViolado)):
        de_pautador_card({"id": "card-red", "vertical": "v", "pais": "BR"}, as_of=AS_OF)


def test_red_r7f_de_pautador_card_com_moeda_explicita_constroi():
    """Controle: com `moeda="BRL"` explícita o card sem histórico constrói e o câmbio não aplica (mesma moeda)."""
    e = de_pautador_card({"id": "card-red", "vertical": "v", "pais": "BR"}, as_of=AS_OF, moeda="BRL")
    assert e.cambio.de == e.cambio.para == "BRL" and e.custo.valor is None


# =============================================================================================== R8
def _cli(lab: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(lab / "scripts" / "viability_cli.py"), *args], capture_output=True, text=True, cwd=str(lab))


@pytest.fixture
def lab_copia(tmp_path) -> Path:
    """Cópia isolada de src/, scripts/, fixtures/viability e uv.lock: o recibo gerado aqui aponta para ESTE código, e só este
    código é adulterado — nunca o worktree."""
    lab = tmp_path / "lab"
    for sub in ("src", "scripts"):
        shutil.copytree(LAB / sub, lab / sub, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(FIXTURES, lab / "fixtures" / "viability")
    if (LAB / "uv.lock").is_file():
        shutil.copy2(LAB / "uv.lock", lab / "uv.lock")
    return lab


@pytest.fixture
def avaliado_na_copia(lab_copia, tmp_path) -> tuple[Path, Path]:
    saida = tmp_path / "saida"
    r = _cli(lab_copia, "evaluate", str(lab_copia / "fixtures" / "viability" / "campanha_favoravel.json"), "--saida", str(saida))
    assert r.returncode in (0, 3), r.stderr
    assert (saida / "recibo.json").is_file()
    return lab_copia, saida


def _recibo(saida: Path) -> dict:
    return json.loads((saida / "recibo.json").read_text(encoding="utf-8"))


def _adulterar(lab: Path, rel: str) -> None:
    p = lab / "src" / "volc_dil" / "contracts" / rel
    assert p.is_file(), p
    p.write_text(p.read_text(encoding="utf-8") + "\n# red team: comentário inofensivo que não muda o comportamento\n", encoding="utf-8")


def test_red_r8_controle_copia_integra_verifica_exit_0(avaliado_na_copia):
    """Controle: cópia intacta → `verify` exit 0 (passa hoje; prova que a cópia isolada reproduz o recibo)."""
    lab, saida = avaliado_na_copia
    r = _cli(lab, "verify", str(saida / "recibo.json"))
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)


@pytest.mark.parametrize("arquivo", ["money.py", "vocab.py"])
def test_red_r8a_adulterar_contracts_invalida_verify_exit_4(avaliado_na_copia, arquivo):
    """R8. Depois do `evaluate`, acrescentar uma linha de comentário a `src/volc_dil/contracts/<money|vocab>.py` da CÓPIA e rodar
    `verify` a partir dela.

    V2 (34a5f960) está errada porque `MODULOS` cobre só `viability/*.py` + a CLI: `Dinheiro` (micros, moeda, conversão,
    `de_decimal`) e o vocabulário ficam fora do `codigo_sha256`, então um kernel com aritmética monetária trocada reproduz
    o recibo antigo e `verify` sai 0. Esperado: exit 4 ("codigo_sha256 difere").
    """
    lab, saida = avaliado_na_copia
    _adulterar(lab, arquivo)
    r = _cli(lab, "verify", str(saida / "recibo.json"))
    assert r.returncode == 4, f"verify aceitou {arquivo} adulterado: exit {r.returncode}; stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "codigo_sha256" in r.stderr, r.stderr


def test_red_r8b_codigo_sha256_do_recibo_muda_quando_money_muda(avaliado_na_copia, tmp_path):
    """R8. O `codigo_sha256` gravado num recibo novo tem de mudar quando money.py muda (hoje fica idêntico)."""
    lab, saida = avaliado_na_copia
    antes = _recibo(saida)["codigo_sha256"]
    _adulterar(lab, "money.py")
    saida2 = tmp_path / "saida2"
    r = _cli(lab, "evaluate", str(lab / "fixtures" / "viability" / "campanha_favoravel.json"), "--saida", str(saida2))
    assert r.returncode in (0, 3), r.stderr
    depois = _recibo(saida2)["codigo_sha256"]
    assert antes != depois, "codigo_sha256 não cobre contracts/money.py"


def test_red_r8c_modulos_do_recibo_incluem_money_e_vocab():
    """R8 (checagem direta, barata): a lista de módulos que entra no hash do recibo inclui `contracts/money.py` e
    `contracts/vocab.py`. Se a CLI deixar de expor `MODULOS`, é falha por construção (o e2e acima continua valendo)."""
    spec = importlib.util.spec_from_file_location("viability_cli_red", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    modulos = getattr(mod, "MODULOS", None)
    if modulos is None:
        pytest.fail("falha por construção: a CLI não expõe `MODULOS`")
    nomes = {Path(p).resolve().relative_to(LAB).as_posix() for p in modulos}
    assert {"src/volc_dil/contracts/money.py", "src/volc_dil/contracts/vocab.py"} <= nomes, sorted(nomes)
