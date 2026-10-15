"""Caso de uso: gerar o lote shadow da carteira de uma conta Google Ads.

Para cada campanha que aparece no fato de custo da conta na janela, grava um
experimento no formato único do Freedom Lab (`contracts/experimento.schema.json`,
validado por `volc_lab.experimentos.validar`) com o mesmo layout que a tela do
W7 já lê: `resultado.json` + `transformacao.csv` + `experimento.json` com o
sha256 de cada artefato. Depois grava o manifesto do lote em `_lotes/`, com o
sha256 de cada `experimento.json`.

Garantias:

- **Nada executa.** `executada` é False e `valor_sugerido` é None em todo
  resultado; o lote não chama API nenhuma além das duas leituras das portas.
- **Experimento assinado não é reescrito.** Se a pasta de um experimento já
  existe, ou ela é byte a byte igual (rodada repetida, idempotente) ou o lote
  inteiro é recusado ANTES de escrever qualquer coisa. O mesmo vale para outro
  experimento da mesma campanha com o mesmo `as_of` (a tela devolveria 409
  `experimentos_ambiguos`).
- **Escrita sem estado intermediário visível.** Os artefatos vão para uma
  pasta temporária sem `experimento.json`, que a tela ignora; a pasta é
  renomeada e só então o manifesto entra, por `os.replace`.
- **Replay idêntico.** O resultado é calculado duas vezes a partir do recorte
  de entrada gravado; `reproducible = identical` só sai se os bytes baterem.

"Assinado" aqui é o que o W7 confere: sha256 de cada artefato no manifesto da
própria pasta. Detecta deriva, não adulteração deliberada (quem edita os dois
passa); não é assinatura criptográfica.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Sequence
from zoneinfo import ZoneInfo

from volc_lab.brokers.recibos import mascarar
from volc_lab.experimentos import validar
from volc_lab.sombra_carteira import dominio
from volc_lab.sombra_carteira.portas import (
    ContratoQuebrado, Cotacao, CustoDia, FonteCambio, FonteCusto, FonteReceita, ReceitaObservada,
)

FUSO_CONTA = ZoneInfo("America/Sao_Paulo")
RAIZ_LAB = Path(__file__).resolve().parents[3]
CONTRATO_LOTE = "sombra_carteira_lote.v1"
_CONTA = re.compile(r"^[0-9]{10}$")

LACUNAS_FIXAS = (
    "custo do fato canônico google_ads_campanha_dia é o último valor (ON CONFLICT substitui a linha); "
    "não há as-of de custo, e a recoleta do W11 pode mudar um dia já lido",
    "receita lida de receita_as_of (v23_01, W12) no instante da leitura; a v23_01 ainda não está aplicada em produção",
    "receita em BRL pela receita de origem × cambio_resolver (W12) resolvido NA LEITURA, com o mesmo conhecido_ate "
    "da receita; o receita_brl gravado na ingestão não é usado (congela o câmbio); dia com câmbio defasado ou sem "
    "cotação fica sem receita, nunca zero",
    "GAM sem o roteador de atribuição no diário do W12: dia com GAM não reconcilia (pode ser adset Meta)",
    "JoinAds soma todos os domínios (joinads_domain) da campanha no dia, como a v17_04; diferente da v17_04, "
    "a receita de mais de um projeto NÃO é recusada, porque o diário do W12 não guarda project_id",
    "joinads_metrics.revenue tem DEFAULT 0: receita 0,00 pode ser default, não medição",
    "fuso do campo date do JoinAds não declarado; o custo está no fuso da conta (America/Sao_Paulo)",
    "conversions_value do Google é valor estático por conversão, não receita; ignorado na decisão",
    "limiares são parâmetros do laboratório, não a política do dono (volc_ads/inteligencia_decisao/politicas.py)",
    "só aparecem campanhas com linha no fato de custo da conta na janela; campanha nunca coletada não é vista",
    "ROAS bruto: revshare e imposto não descontados",
)


class LoteRecusado(RuntimeError):
    """O lote não pode ser gravado sem reescrever ou contradizer o que já existe."""


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _json_bytes(obj: Any) -> bytes:
    # allow_nan=False: NaN/Infinity não são JSON e derrubariam a leitura da tela.
    return (json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True, default=str,
                       allow_nan=False) + "\n").encode()


def codigo_sha256() -> str:
    """Hash do código que decide (domínio + este caso de uso + contratos)."""
    h = hashlib.sha256()
    for nome in ("portas.py", "dominio.py", "aplicacao.py"):
        h.update((Path(__file__).parent / nome).read_bytes())
    return h.hexdigest()


def lock_sha256() -> str:
    return _sha256_bytes((RAIZ_LAB / "uv.lock").read_bytes())


def _instante(lido_em: str) -> datetime:
    """`lido_em` precisa dizer o fuso; sem ele o as_of dependeria do relógio da máquina."""
    try:
        quando = datetime.fromisoformat(str(lido_em).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContratoQuebrado(f"lido_em ilegível ({lido_em!r})") from exc
    if quando.tzinfo is None:
        raise ContratoQuebrado(f"lido_em sem fuso ({lido_em!r}): o as_of ficaria ambíguo")
    return quando.astimezone(timezone.utc)


def _data_local(instante: str) -> date:
    return _instante(instante).astimezone(FUSO_CONTA).date()


def _as_of(custo_lido_em: str, receita_lido_em: str) -> datetime:
    """O dado mais velho manda: a leitura anterior ainda não viu o que a outra viu."""
    return min(_instante(custo_lido_em), _instante(receita_lido_em))


def _rotulo(instante: datetime) -> str:
    return instante.strftime("%Y%m%dt%H%M%Sz")


@dataclass(frozen=True)
class Recorte:
    """O que entra num experimento: só as linhas da campanha, conta mascarada."""

    campanha: str
    custo: list[dict[str, Any]]
    receita: list[dict[str, Any]]
    custo_lido_em: str
    receita_lido_em: str
    custo_fonte: str
    receita_fonte: str
    cambio: list[dict[str, Any]]
    cambio_lido_em: str
    cambio_fonte: str


def _pedidos_de_cambio(receita_linhas: Sequence[dict]) -> list[tuple[str, date]]:
    """(par, dia) de cada receita em moeda estrangeira com valor."""
    pedidos = set()
    for linha in receita_linhas:
        r = ReceitaObservada.da_linha(linha)
        if r.receita is not None and r.moeda != "BRL":
            pedidos.add((f"{r.moeda}/BRL", r.data_referencia))
    return sorted(pedidos)


def _cotacao_bate(cot: dict, pedidos: set[tuple[str, date]]) -> bool:
    c = Cotacao.da_linha(cot)
    return (c.par, c.data) in pedidos


def _recortes(conta: str, custo_linhas: Sequence[dict], receita_linhas: Sequence[dict],
              leituras: tuple[str, str, str, str]) -> dict[str, list]:
    custo_lido_em, receita_lido_em, custo_fonte, receita_fonte = leituras
    campanhas: dict[str, list[dict]] = {}
    for linha in custo_linhas:
        c = CustoDia.da_linha(linha)
        if c.customer_id != conta:
            raise ContratoQuebrado(f"linha de custo de outra conta ({mascarar(c.customer_id)})")
        campanhas.setdefault(c.campaign_id, []).append({**linha, "customer_id": mascarar(conta)})
    receitas: dict[str, list[dict]] = {}
    for linha in receita_linhas:
        # Filtra pela campanha ANTES de validar: uma linha estranha de outra rede
        # (adset Meta via utm) não derruba a carteira Google. A da conta é
        # validada estritamente.
        chave = linha.get("chave") if isinstance(linha, dict) else None
        cid = str(chave.get("utm_campaign_value")) if isinstance(chave, dict) else None
        if cid in campanhas:
            ReceitaObservada.da_linha(linha)
            receitas.setdefault(cid, []).append(dict(linha))
    return {cid: [linhas, receitas.get(cid, [])] for cid, linhas in sorted(campanhas.items())}


def _ordenar_custo(linhas: list[dict]) -> list[dict]:
    return sorted(linhas, key=lambda l: (str(l["metric_date"]), json.dumps(l["segmentos"], sort_keys=True)))


def _ordenar_receita(linhas: list[dict]) -> list[dict]:
    return sorted(linhas, key=lambda l: (str(l["data_referencia"]), str(l["fonte"]),
                                         json.dumps(l["chave"], sort_keys=True)))


def _csv(av: dominio.Avaliacao) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    # Colunas que a tela do W7 lê: date, custo_brl, clicks, receita_brl, maduro, estado.
    w.writerow(["date", "custo_brl", "clicks", "custo_origem", "receita_brl", "receita_moeda_origem",
                "cambio_modo", "fontes_receita", "valor_conversao_google", "maduro", "estado"])
    vazio = lambda v: "" if v is None else v  # noqa: E731 — ausência é célula vazia, nunca 0
    duas = lambda v: "" if v is None else round(v, 2)  # noqa: E731
    quatro = lambda v: "" if v is None else round(v, 4)  # noqa: E731
    for d in av.dias:
        w.writerow([d.data.isoformat(), vazio(d.custo_brl), vazio(d.cliques), vazio(d.custo_origem),
                    duas(d.receita_brl),
                    quatro(d.receita_moeda_origem), "|".join(d.cambio_modos), "|".join(d.fontes_receita),
                    vazio(d.valor_conversao_google), "true" if d.maduro else "false", d.estado])
    return buf.getvalue().encode()


def _status(custo: list[dict]) -> tuple[Optional[str], Optional[str]]:
    """Nome e status da campanha na linha de custo mais recente."""
    if not custo:
        return None, None
    ultima = max(custo, key=lambda l: str(l["metric_date"]))
    return ultima.get("campaign_name"), ultima.get("campaign_status")


def calcular(recorte: Recorte, conta_mascarada: str, lote_id: str,
             parametros: Optional[dict[str, float]] = None) -> dict[str, bytes]:
    """Artefatos de um experimento a partir do recorte. Determinístico."""
    custo = _ordenar_custo(recorte.custo)
    receita = _ordenar_receita(recorte.receita)
    cambio = sorted(recorte.cambio, key=lambda l: (str(l["par"]), str(l["data"])))
    instante = _as_of(recorte.custo_lido_em, recorte.receita_lido_em)
    as_of = instante.astimezone(FUSO_CONTA).date()
    receitas = dominio.cambio_na_leitura([ReceitaObservada.da_linha(l) for l in receita],
                                         [Cotacao.da_linha(l) for l in cambio])
    av = dominio.avaliar(
        recorte.campanha,
        [CustoDia.da_linha(l) for l in custo],
        receitas,
        as_of, parametros, LACUNAS_FIXAS,
    )
    nome, status = _status(custo)
    entrada_custo = _json_bytes({
        "_sobre": "Recorte de google_ads_campanha_dia (v12_04) desta campanha; conta mascarada.",
        "fonte": recorte.custo_fonte, "lido_em": recorte.custo_lido_em,
        "campaign_id": recorte.campanha, "linhas": custo})
    entrada_receita = _json_bytes({
        "_sobre": "Recorte de receita_as_of (v23_01) desta campanha. null = ausente, não zero.",
        "fonte": recorte.receita_fonte, "lido_em": recorte.receita_lido_em,
        "campaign_id": recorte.campanha, "linhas": receita})
    entrada_cambio = _json_bytes({
        "_sobre": ("Respostas de cambio_resolver (v23_01) para os dias desta campanha, no corte da "
                   "leitura de receita. Sem linha para um dia = sem_cotacao."),
        "fonte": recorte.cambio_fonte, "lido_em": recorte.cambio_lido_em,
        "campaign_id": recorte.campanha, "linhas": cambio})
    resultado = {
        "contrato_motor": "sombra_carteira.v1",
        "campanha": recorte.campanha,
        "campanha_nome": nome,
        "campanha_status": status,
        "conta": conta_mascarada,
        "lote_id": lote_id,
        # O instante da leitura, e não só o dia: uma segunda rodada no mesmo dia
        # é mais recente e vence na tela, sem empate nem reescrita.
        "as_of": instante.isoformat(),
        "as_of_data": av.as_of.isoformat(),
        "corte_maturidade": av.corte_maturidade.isoformat(),
        "parametros": av.parametros,
        "codigo_sha256": codigo_sha256(),
        # De onde sai cada número; o painel legado (daily_campaign_metrics) não entra.
        "fontes": {
            "custo_brl": ("google_ads_campanha_dia (v12_04): linha não segmentada, último valor do dia "
                          "(D0, D-1 ou recoleta W11, ver custo_origem por dia); custo_micros / 1e6"),
            "cliques": "google_ads_campanha_dia (v12_04).cliques",
            "receita_brl": ("receita_as_of (v23_01, W12).receita (moeda de origem) × cambio_resolver (v23_01) "
                            "resolvido na leitura, modo exata ou anterior; defasada e sem_cotacao ficam nulas; "
                            "nunca o receita_brl da ingestão nem revenue_converted"),
            "cambio_lido_em": recorte.cambio_lido_em,
            "valor_conversao_google": "google_ads_campanha_dia.valor_conversoes; exibido como não confiável, não decide",
            "custo_lido_em": recorte.custo_lido_em,
            "receita_lido_em": recorte.receita_lido_em,
        },
        "estado_dado": av.estado_dado,
        "motivo_estado_dado": av.motivo_estado_dado,
        "janela_madura": av.janela_madura,
        "janela_madura_recente": av.janela_madura_recente,
        "fracao_custo_maduro_sem_receita": av.fracao_custo_maduro_sem_receita,
        "custo_maduro_sem_receita_por_estado": av.custo_maduro_por_estado,
        "roas_sob_estresse": av.roas_sob_estresse,
        "valor_conversao_google_total": av.valor_conversao_google_total,
        "recomendacao": asdict(av.recomendacao),
    }
    return {
        "custo_campanha_dia.json": entrada_custo,
        "receita_observada.json": entrada_receita,
        "cambio_lido.json": entrada_cambio,
        "transformacao.csv": _csv(av),
        "resultado.json": _json_bytes(resultado),
    }


def _manifesto(experimento_id: str, artefatos: dict[str, bytes], base_ref: str,
               reproduzido: bool) -> dict[str, Any]:
    resultado = json.loads(artefatos["resultado.json"])
    madura = resultado["janela_madura"]
    rec = resultado["recomendacao"]
    roas = madura["roas"]
    entrada_sha = _sha256_bytes(artefatos["custo_campanha_dia.json"] + artefatos["receita_observada.json"]
                                + artefatos["cambio_lido.json"])
    lidos = sorted([json.loads(artefatos["custo_campanha_dia.json"])["lido_em"],
                    json.loads(artefatos["receita_observada.json"])["lido_em"]])
    min_effect = 0.5
    if resultado["estado_dado"] != dominio.COMPLETO or roas is None:
        desfecho, decisao = "inconclusive", "repeat"
    elif roas < 1.0:
        desfecho = "supported"
        decisao = "adopt" if (1.0 - roas) >= min_effect and reproduzido else "repeat"
    else:
        desfecho, decisao = "refuted", "reject"
    observado: dict[str, Any] = {
        "janela_madura": madura,
        "janela_madura_recente": resultado["janela_madura_recente"],
        "direcao_shadow": rec["direcao"],
        "estado_dado": resultado["estado_dado"],
        "fracao_custo_maduro_sem_receita": resultado["fracao_custo_maduro_sem_receita"],
    }
    if roas is not None:
        observado["roas_maduro"] = {"baseline": 1.0, "candidate": roas}
    return {
        "experiment_id": experimento_id,
        "hypothesis": {
            "statement": (f"No grão campanha × dia reconciliável, a campanha {resultado['campanha']} "
                          "não paga o próprio custo na janela madura"),
            "falsified_if": "ROAS bruto reconciliado da janela madura >= 1,0",
            "primary_metric": "roas_maduro", "direction": "decrease", "min_effect": min_effect,
        },
        "baseline": {"description": "equilíbrio: receita bruta = custo (ROAS 1,0)", "values": {"roas": 1.0}},
        "input_snapshot": {
            "id": f"{experimento_id}-entrada",
            "source": ("custo: google_ads_campanha_dia (v12_04, W11); "
                       "receita: receita_as_of (v23_01, W12); câmbio: cambio_resolver na leitura (v23_01, W12)"),
            "sha256": entrada_sha,
            "captured_at": lidos[0],
            "contains_pii": False,
        },
        "method": {
            "description": ("Motor shadow da carteira (volc_lab.sombra_carteira): custo não segmentado × "
                            "receita em BRL do W12 por dia; maturidade exclui os últimos dias no fuso da "
                            "conta; dia sem câmbio, sem receita, com GAM sem atribuição ou com sobreposição "
                            "fica sem dado; decisão por ROAS maduro, estresse e fração de custo sem receita."),
            "seeds_not_applicable_reason": "transformação determinística, sem amostragem",
            "replay_without_api": True,
            "external_writes": 0,
            "external_calls": {"mode": "none", "count": 0},
            "environment": {"base_ref": base_ref, "lock_sha256": lock_sha256(),
                            "codigo_sha256": resultado["codigo_sha256"]},
        },
        "dependencies": [],
        "metrics": {
            "time": {"unit": "s", "kind": "not_measured",
                     "not_measured_reason": "a duração fica fora dos artefatos para o replay reproduzir os mesmos sha256"},
            "cost": {"unit": "USD", "value": 0, "kind": "observed"},
            "quality": {"unit": "dias reconciliados maduros", "value": madura["dias"], "kind": "observed"},
        },
        "result": {
            "observed": observado,
            "estimated": {"roas_sob_estresse": resultado["roas_sob_estresse"]},
            "hypothesis_outcome": desfecho,
            "reproducible": "identical" if reproduzido else "not_reproduced",
        },
        "limitations": list(rec["lacunas"]) or ["sem lacuna declarada"],
        "decision": decisao,
        "rollback_or_cleanup": {
            "steps": ["nenhuma ação externa executada; nada a desfazer"],
            "done": True,
            "verified_by": "o motor só lê pelas portas; recomendacao.executada = false",
        },
        "artifacts": [{"path": n, "sha256": _sha256_bytes(b)} for n, b in sorted(artefatos.items())],
    }


def experimento_id(campanha: str, instante: datetime) -> str:
    return f"gads-{campanha}-sombra-{_rotulo(instante)}"


def _normalizar(as_of: Any) -> Optional[datetime]:
    """O mesmo critério de recência da tela do W7 (naive em UTC)."""
    try:
        quando = datetime.fromisoformat(str(as_of))
    except ValueError:
        return None
    if quando.tzinfo is not None:
        quando = quando.astimezone(timezone.utc).replace(tzinfo=None)
    return quando


def _ja_existentes(destino: Path) -> dict[tuple[str, Optional[datetime]], str]:
    """(campanha, as_of normalizado) → id de cada experimento já gravado. Ilegível recusa o lote."""
    vistos: dict[tuple[str, Optional[datetime]], str] = {}
    if not destino.is_dir():
        return vistos
    for manifesto in sorted(destino.glob("*/experimento.json")):
        resultado = manifesto.parent / "resultado.json"
        if not resultado.exists():
            continue
        try:
            r = json.loads(resultado.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise LoteRecusado(f"resultado ilegível em {manifesto.parent.name}: não dá para afirmar ausência") from exc
        vistos[(str(r.get("campanha")), _normalizar(r.get("as_of")))] = manifesto.parent.name
    return vistos


def _identico(pasta: Path, artefatos: dict[str, bytes], manifesto: bytes) -> bool:
    if (pasta / "experimento.json").read_bytes() != manifesto:
        return False
    return all((pasta / n).is_file() and (pasta / n).read_bytes() == b for n, b in artefatos.items())


def gerar_lote(
    conta: str,
    fonte_custo: FonteCusto,
    fonte_receita: FonteReceita,
    fonte_cambio: FonteCambio,
    destino: Path,
    *,
    base_ref: str,
    hoje: date,
    parametros: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    """Lê as duas portas uma vez, gera um experimento por campanha e o lote."""
    if not _CONTA.fullmatch(conta):
        raise ValueError("conta Google Ads precisa ter 10 dígitos, sem hífen")
    p = {**dominio.PARAMETROS_PADRAO, **(parametros or {})}
    inicio = hoje - timedelta(days=int(p["janela_dias"]) + 1)
    custo = fonte_custo.custo_campanha_dia(conta, inicio, hoje)
    receita = fonte_receita.receita_vigente(inicio, hoje)
    instante = _as_of(custo.lido_em, receita.lido_em)
    as_of = instante.isoformat()
    if not custo.linhas:
        # Fato vazio é coleta que não rodou, não carteira sem campanha.
        raise LoteRecusado("a leitura de custo veio vazia para a conta; nada a afirmar, nada gravado")
    mascara = mascarar(conta)
    # A máscara sozinha colide entre contas (547****539); o hash curto separa.
    lote_id = (f"sombra-carteira-{mascara.replace('*', 'x')}-{_sha256_bytes(conta.encode())[:8]}"
               f"-{_rotulo(instante)}")

    brutos = _recortes(conta, custo.linhas, receita.linhas,
                       (custo.lido_em, receita.lido_em, custo.fonte, receita.fonte))
    # Uma leitura de câmbio para a conta inteira, no mesmo corte da receita.
    todos_pedidos = _pedidos_de_cambio([l for _, rec in brutos.values() for l in rec])
    cambio = fonte_cambio.cotacoes(todos_pedidos, receita.lido_em, int(p["max_defasagem_cambio_dias"]))
    recortes: dict[str, Recorte] = {}
    for cid, (custo_l, receita_l) in brutos.items():
        pedidos = set(_pedidos_de_cambio(receita_l))
        recortes[cid] = Recorte(cid, custo_l, receita_l, custo.lido_em, receita.lido_em, custo.fonte,
                                receita.fonte, [dict(c) for c in cambio.linhas if _cotacao_bate(c, pedidos)],
                                cambio.lido_em, cambio.fonte)
    preparados: list[tuple[str, dict[str, bytes], bytes, dict[str, Any]]] = []
    for cid, recorte in recortes.items():
        artefatos = calcular(recorte, mascara, lote_id, p)
        # O replay parte dos BYTES do recorte gravado, não do objeto em memória.
        replay = calcular(_recorte_dos_bytes(cid, artefatos), mascara, lote_id, p)
        eid = experimento_id(cid, instante)
        manifesto = _manifesto(eid, artefatos, base_ref, artefatos == replay)
        manifesto_b = _json_bytes(manifesto)
        preparados.append((eid, artefatos, manifesto_b, manifesto))

    # Tudo validado e conferido ANTES de escrever qualquer coisa.
    existentes = _ja_existentes(destino)
    novos: list[tuple[str, dict[str, bytes], bytes]] = []
    repetidos: list[str] = []
    for eid, artefatos, manifesto_b, manifesto in preparados:
        resultado = json.loads(artefatos["resultado.json"])
        dono = existentes.get((resultado["campanha"], _normalizar(resultado["as_of"])))
        if dono is not None and dono != eid:
            raise LoteRecusado(f"a campanha {resultado['campanha']} já tem o experimento {dono} com o "
                               f"mesmo as_of {resultado['as_of']}; gravar {eid} criaria ambiguidade")
        pasta = destino / eid
        if pasta.exists():
            if not (pasta / "experimento.json").is_file() or not _identico(pasta, artefatos, manifesto_b):
                raise LoteRecusado(f"{eid} já existe com conteúdo diferente; experimento assinado não é reescrito")
            repetidos.append(eid)
            continue
        _validar_em_disco(eid, artefatos, manifesto)
        novos.append((eid, artefatos, manifesto_b))

    itens = []
    for eid, artefatos, manifesto_b, _ in preparados:
        r = json.loads(artefatos["resultado.json"])
        itens.append({
            "experimento_id": eid,
            "campanha": r["campanha"],
            "campanha_nome": r["campanha_nome"],
            "campanha_status": r["campanha_status"],
            "estado_dado": r["estado_dado"],
            "direcao": r["recomendacao"]["direcao"],
            "executada": False,
            "manifesto_sha256": _sha256_bytes(manifesto_b),
        })
    lote = {
        "contrato": CONTRATO_LOTE,
        "lote_id": lote_id,
        "conta": mascara,
        "as_of": as_of,
        "parametros": p,
        "codigo_sha256": codigo_sha256(),
        "base_ref": base_ref,
        "leituras": {"custo": {"fonte": custo.fonte, "lido_em": custo.lido_em, "linhas": len(custo.linhas)},
                     "receita": {"fonte": receita.fonte, "lido_em": receita.lido_em, "linhas": len(receita.linhas)},
                     "cambio": {"fonte": cambio.fonte, "lido_em": cambio.lido_em, "linhas": len(cambio.linhas),
                                "pedidos": len(todos_pedidos)}},
        "experimentos": itens,
        "resumo": _resumo(itens),
        "isolamento": {"chamadas_externas_alem_das_portas": 0, "mutacoes_executadas": 0, "oferece_aplicar": False},
    }
    lote_b = _json_bytes(lote)
    lotes = destino / "_lotes"
    alvo = lotes / f"{lote_id}.json"
    # Conferido ANTES de gravar qualquer experimento: recusa não deixa disco parcial.
    if alvo.exists() and alvo.read_bytes() != lote_b:
        raise LoteRecusado(f"o lote {lote_id} já existe com conteúdo diferente")

    destino.mkdir(parents=True, exist_ok=True)
    for eid, artefatos, manifesto_b in novos:
        _gravar(destino, eid, artefatos, manifesto_b)
    lotes.mkdir(parents=True, exist_ok=True)
    if not alvo.exists():
        tmp = lotes / f".{lote_id}.json.tmp"
        tmp.write_bytes(lote_b)
        os.replace(tmp, alvo)
    return {"lote_id": lote_id, "lote_sha256": _sha256_bytes(lote_b), "novos": [n[0] for n in novos],
            "repetidos": repetidos, "resumo": lote["resumo"], "caminho": str(alvo)}


def _resumo(itens: list[dict[str, Any]]) -> dict[str, Any]:
    por_direcao: dict[str, int] = {}
    por_estado: dict[str, int] = {}
    for i in itens:
        por_direcao[i["direcao"]] = por_direcao.get(i["direcao"], 0) + 1
        por_estado[i["estado_dado"]] = por_estado.get(i["estado_dado"], 0) + 1
    return {"campanhas": len(itens), "por_direcao": dict(sorted(por_direcao.items())),
            "por_estado_dado": dict(sorted(por_estado.items()))}


def _validar_em_disco(eid: str, artefatos: dict[str, bytes], manifesto: dict[str, Any]) -> None:
    """O validador do lab confere sha256 em disco; valida numa pasta descartável fora do destino."""
    with tempfile.TemporaryDirectory(prefix="volc-sombra-") as tmp:
        pasta = Path(tmp)
        for nome, b in artefatos.items():
            (pasta / nome).write_bytes(b)
        erros = validar(manifesto, pasta)
    if erros:
        raise LoteRecusado(f"{eid} não passa no contrato de experimentos: {'; '.join(erros)}")


def _gravar(destino: Path, eid: str, artefatos: dict[str, bytes], manifesto_b: bytes) -> None:
    # A pasta temporária não tem experimento.json: a tela não a enxerga. Nome
    # único, para duas execuções simultâneas não apagarem a pasta uma da outra.
    tmp = Path(tempfile.mkdtemp(prefix=f".tmp-{eid}-", dir=destino))
    for nome, b in artefatos.items():
        (tmp / nome).write_bytes(b)
    final = destino / eid
    os.rename(tmp, final)
    parcial = final / ".experimento.json.tmp"
    parcial.write_bytes(manifesto_b)
    os.replace(parcial, final / "experimento.json")


def _recorte_dos_bytes(campanha: str, artefatos: dict[str, bytes]) -> Recorte:
    custo = json.loads(artefatos["custo_campanha_dia.json"])
    receita = json.loads(artefatos["receita_observada.json"])
    cambio = json.loads(artefatos["cambio_lido.json"])
    return Recorte(campanha, custo["linhas"], receita["linhas"], custo["lido_em"],
                   receita["lido_em"], custo["fonte"], receita["fonte"],
                   cambio["linhas"], cambio["lido_em"], cambio["fonte"])


def replay(pasta: Path) -> dict[str, Any]:
    """Recalcula um experimento gravado a partir do próprio recorte e compara."""
    resultado = json.loads((pasta / "resultado.json").read_text(encoding="utf-8"))
    entradas = {n: (pasta / n).read_bytes()
                for n in ("custo_campanha_dia.json", "receita_observada.json", "cambio_lido.json")}
    # A conta já está mascarada no recorte; o replay a usa como está.
    recorte = _recorte_dos_bytes(resultado["campanha"], entradas)
    novos = calcular(recorte, resultado["conta"], resultado["lote_id"], resultado["parametros"])
    divergentes = sorted(n for n, b in novos.items() if (pasta / n).read_bytes() != b)
    return {"experimento_id": pasta.name, "identico": not divergentes, "divergentes": divergentes}
