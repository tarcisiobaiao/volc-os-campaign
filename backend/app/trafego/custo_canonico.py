"""Custo Google Ads do período, lido do fato canônico campanha-dia (v12_04).

## Por que este módulo existe

O custo herói do Hub lia `trafego_campanha_espelho.custo_micros`, um espelho
`LAST_30_DAYS` gravado pelo sincronizador do inventário: sem janela gravada,
sem dia, sem recibo (revisão D1, O5). A verdade do custo é
`google_ads_campanha_dia`, alimentada pelo D0, pelo D-1 e pela recoleta (W11),
com chave conta + campanha + data, micros com moeda, `colhida_em` e ledger.

Este módulo é DOMÍNIO puro: recebe linhas já lidas (fato e fechamentos do
ledger) e devolve o contrato. Quem lê o banco é `custo_canonico_fonte.py`.

## As três regras que ele defende

1. **Dia sem coleta é "sem dado", nunca zero.** O Google não devolve linha para
   campanha sem atividade no dia, então "nenhuma linha" só significa zero
   quando o ledger prova que o dia foi lido: um fechamento `ok` da conta cuja
   janela cobre o dia. Sem isso o dia é `sem_coleta` e o custo dele é `None`.
2. **Total só é total quando todo dia é fechado.** `custo_micros` da conta (e
   da moeda) é `None` se faltar qualquer dia; `custo_micros_coberto` é a soma
   do que há, e a `verdade` diz `parcial` com o motivo.
3. **Removida entra e é marcada.** Campanha REMOVED gastou de verdade no
   período: soma no custo e aparece com `removida: true`. Esconder rebaixaria
   o custo em silêncio, que foi exatamente o defeito do herói.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

FONTE = "google_ads_campanha_dia"

#: Jobs do ledger que escrevem o fato campanha-dia: o coletor Python
#: (`volc_ads.coleta`, D0/D-1/recoleta) e os dois fluxos n8n v12. As famílias
#: granulares da v17_01 dividem o ledger mas NÃO cobrem o campanha-dia.
JOBS_DO_FATO = ("gads_campanha_dia", "gads_dia_d0", "gads_dia_d1")

JANELA_MAXIMA_DIAS = 90
JANELA_PADRAO_DIAS = 30

# Estados de um dia de uma conta, do mais forte para o mais fraco.
# ⚠️ "fechado" é a janela fechada da v12_04 (D-1 ou backfill), não "imutável":
# o Google ainda ajusta custo depois do D-1, e é a recoleta (W11) que relê.
# `real` quer dizer "todo dia lido com janela fechada", nada além disso.
FECHADO = "fechado"            # D-1 ou backfill `ok` cobre o dia
INTRADIA = "intradia"          # só D0 `ok`: completo no instante, ainda imaturo
# Conservador por desenho: um fechamento n8n `parcial` rebaixa TODAS as contas
# aceitas nele, mesmo a que foi lida inteira — o ledger não diz qual conta
# teve a linha recusada.
PARCIAL = "parcial"            # houve fechamento, mas `parcial` (linha recusada)
SEM_FECHAMENTO = "sem_fechamento"  # há linha do fato, mas nenhum fechamento útil
SEM_COLETA = "sem_coleta"      # nada prova que o dia foi lido

REAL, PARCIAL_V, INDISPONIVEL = "real", "parcial", "indisponivel"


class PeriodoInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Periodo:
    inicio: date
    fim: date

    def __post_init__(self) -> None:
        if self.fim < self.inicio:
            raise PeriodoInvalido("período invertido: fim antes do início")
        if self.dias > JANELA_MAXIMA_DIAS:
            raise PeriodoInvalido(f"período de {self.dias} dias; o máximo é {JANELA_MAXIMA_DIAS}")

    @property
    def dias(self) -> int:
        return (self.fim - self.inicio).days + 1

    def datas(self) -> List[date]:
        return [self.inicio + timedelta(days=i) for i in range(self.dias)]


def periodo_padrao(hoje: date, dias: int = JANELA_PADRAO_DIAS) -> Periodo:
    """Os `dias` dias fechados até ontem. Hoje fica fora: D0 é imaturo."""
    return Periodo(hoje - timedelta(days=dias), hoje - timedelta(days=1))


# ── leitura defensiva das linhas ────────────────────────────────────────────

def _data(valor: Any) -> Optional[date]:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _instante(valor: Any) -> Optional[datetime]:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor
    texto = str(valor).strip().replace(" ", "T", 1)
    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


def _micros(valor: Any) -> Optional[int]:
    """bigint do PostgREST chega como número; string ou bool é recusado."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    raise ValueError(f"custo_micros não inteiro: {valor!r}")


def _iso(t: Optional[datetime]) -> Optional[str]:
    return t.isoformat() if t is not None else None


# ── cobertura: o ledger diz quais dias foram lidos ──────────────────────────

_PESO = {FECHADO: 4, PARCIAL: 3, INTRADIA: 2, SEM_FECHAMENTO: 1, SEM_COLETA: 0}


def _recusadas(f: Mapping[str, Any]) -> set:
    saida = set()
    for r in f.get("contas_recusadas") or []:
        cid = r.get("customer_id") if isinstance(r, Mapping) else r
        if cid:
            saida.add(str(cid))
    return saida


def contas_lidas(f: Mapping[str, Any]) -> List[str]:
    """Contas que um fechamento prova ter LIDO.

    `contas_aceitas` não basta: o coletor Python grava `[]` nela quando a
    leitura voltou sem linha (`volc_ads/coleta/familias/campanha_dia.py`), e o
    n8n grava a conta lida mesmo sem linha. Num fechamento `ok`, toda conta
    tentada e não recusada foi lida — inclusive a que não gastou nada, cujo
    zero é MEDIDO. Em `parcial`, só as aceitas.
    """
    aceitas = [str(c) for c in (f.get("contas_aceitas") or [])]
    if str(f.get("resultado") or "") != "ok":
        return aceitas
    recusadas = _recusadas(f)
    tentadas = [str(c) for c in (f.get("contas_tentadas") or []) if str(c) not in recusadas]
    return sorted(set(aceitas) | set(tentadas))


def cobertura(fechamentos: Iterable[Mapping[str, Any]], contas: Sequence[str],
              periodo: Periodo) -> Dict[str, Dict[date, str]]:
    """Estado de cada (conta, dia) a partir dos FECHAMENTOS do ledger.

    `falhou` não cobre nada. `ok` de D-1/backfill fecha o dia; `ok` de D0 deixa
    o dia `intradia`; `parcial` de qualquer origem deixa o dia `parcial`. Vale o
    estado mais forte entre os fechamentos que cobrem o dia.
    """
    estado = {c: {d: SEM_COLETA for d in periodo.datas()} for c in contas}
    for f in fechamentos:
        if str(f.get("job") or "") not in JOBS_DO_FATO:
            continue
        resultado = str(f.get("resultado") or "")
        if resultado not in ("ok", "parcial"):
            continue
        ini, fim = _data(f.get("janela_inicio")), _data(f.get("janela_fim"))
        if ini is None or fim is None:
            continue
        origem = str(f.get("origem_janela") or "")
        if resultado == "parcial":
            novo = PARCIAL
        elif origem in ("D-1", "backfill"):
            novo = FECHADO
        elif origem == "D0":
            novo = INTRADIA
        else:
            continue
        for conta in contas_lidas(f):
            dias = estado.get(str(conta))
            if dias is None:
                continue
            d = max(ini, periodo.inicio)
            while d <= min(fim, periodo.fim):
                if _PESO[novo] > _PESO[dias[d]]:
                    dias[d] = novo
                d += timedelta(days=1)
    return estado


# ── o contrato ──────────────────────────────────────────────────────────────

def _verdade(estados: Iterable[str]) -> str:
    estados = list(estados)
    if estados and all(e == FECHADO for e in estados):
        return REAL
    if all(e == SEM_COLETA for e in estados):
        return INDISPONIVEL
    return PARCIAL_V


def montar_custo(linhas: Iterable[Mapping[str, Any]], fechamentos: Iterable[Mapping[str, Any]],
                 *, contas: Optional[Sequence[str]], periodo: Periodo,
                 agora: datetime) -> Dict[str, Any]:
    """O custo do período por conta, campanha e dia, com proveniência e frescor.

    `linhas`: `google_ads_campanha_dia` (sem segmento) do período.
    `fechamentos`: `trafego_coleta_execucao` com `tipo_lote='fechamento'` cujas
    janelas tocam o período. `contas=None` infere as contas do que foi lido, e
    a resposta diz isso — conta nunca coletada não aparece sozinha.
    """
    linhas = [l for l in linhas
              if _data(l.get("metric_date")) is not None
              and periodo.inicio <= _data(l.get("metric_date")) <= periodo.fim]
    fechamentos = list(fechamentos)
    detalhe: List[str] = []

    if contas:
        alvo = sorted({str(c) for c in contas})
    else:
        # Inclui conta só TENTADA (falhou, recusada): ela aparece indisponível
        # em vez de sumir e deixar o resto parecer completo.
        alvo = sorted({str(l["customer_id"]) for l in linhas if l.get("customer_id")}
                      | {str(c) for f in fechamentos if str(f.get("job") or "") in JOBS_DO_FATO
                         for c in [*(f.get("contas_aceitas") or []), *(f.get("contas_tentadas") or [])]})
        detalhe.append("contas inferidas do fato e do ledger; peça `conta` para incluir "
                       "conta que nunca foi coletada")

    cob = cobertura(fechamentos, alvo, periodo)

    # Uma linha por (conta, campanha, dia). Duplicata é defeito, não soma: fica a
    # de `colhida_em` mais nova e a resposta conta quantas sobraram.
    unicas: Dict[tuple, Mapping[str, Any]] = {}
    duplicadas = 0
    for l in linhas:
        chave = (str(l.get("customer_id")), str(l.get("campaign_id")), _data(l.get("metric_date")))
        if chave[0] not in cob:
            continue
        atual = unicas.get(chave)
        if atual is not None:
            duplicadas += 1
            nova, velha = _instante(l.get("colhida_em")), _instante(atual.get("colhida_em"))
            if nova is None or (velha is not None and nova <= velha):
                continue
        unicas[chave] = l
    if duplicadas:
        detalhe.append(f"{duplicadas} linha(s) repetida(s) para a mesma conta, campanha e dia; "
                       "valeu a de colhida_em mais nova")

    saida_contas: List[Dict[str, Any]] = []
    for conta in alvo:
        dias_estado = dict(cob[conta])
        minhas = [l for (c, _, _), l in unicas.items() if c == conta]
        # Linha sem fechamento útil: o valor existe, mas nada prova que o dia
        # está completo. Mostra-se, rebaixado.
        # Linha D0 em dia FECHADO: o D-1/backfill leu a conta inteira e NÃO
        # devolveu esta campanha (estorno integral, por exemplo), senão a
        # precedência teria trocado a linha. O valor intradia ficou velho e
        # não pode sair como definitivo: o dia desce para `sem_fechamento`.
        provisorias = 0
        for l in minhas:
            d = _data(l.get("metric_date"))
            if dias_estado[d] == SEM_COLETA:
                dias_estado[d] = SEM_FECHAMENTO
            elif dias_estado[d] == FECHADO and str(l.get("origem_janela") or "") == "D0":
                dias_estado[d] = SEM_FECHAMENTO
                provisorias += 1

        moedas = sorted({str(l.get("currency_code")) for l in minhas if l.get("currency_code")})
        moeda = moedas[0] if len(moedas) == 1 else None

        por_dia: Dict[date, int] = {}
        nao_medidos: set = set()
        for l in minhas:
            d = _data(l.get("metric_date"))
            v = _micros(l.get("custo_micros"))
            if v is None:
                # Linha sem custo medido (NULL no fato) não vira zero: o dia
                # inteiro fica sem valor, porque a soma dele seria um chute.
                nao_medidos.add(d)
            else:
                por_dia[d] = por_dia.get(d, 0) + v

        serie = []
        for d in periodo.datas():
            e = dias_estado[d]
            # Zero só quando o dia foi lido INTEIRO e não veio linha. Em dia
            # `parcial` a linha da conta pode ter sido a recusada.
            if e == SEM_COLETA or d in nao_medidos:
                valor = None
            elif d in por_dia:
                valor = por_dia[d]
            else:
                valor = 0 if e in (FECHADO, INTRADIA) else None
            serie.append({"data": d.isoformat(), "estado": e, "custo_micros": valor})

        verdade = _verdade(dias_estado.values())
        tem_valor = any(s["custo_micros"] is not None for s in serie)
        # Sem nenhuma linha não há moeda, mas um período inteiro lido e vazio é
        # zero MEDIDO — e zero não precisa de moeda.
        somavel = moeda is not None or (len(moedas) == 0 and tem_valor)
        if nao_medidos and verdade == REAL:
            verdade = PARCIAL_V
        coberto = sum(s["custo_micros"] for s in serie if s["custo_micros"] is not None)
        motivos: List[str] = []
        if len(moedas) > 1:
            verdade = PARCIAL_V if verdade != INDISPONIVEL else verdade
            motivos.append(f"moedas divergentes no fato: {moedas}; nada somado")
        if nao_medidos:
            motivos.append(f"{len(nao_medidos)} dia(s) com linha sem custo medido (NULL), fora da soma")
        if provisorias:
            motivos.append(f"{provisorias} linha(s) D0 em dia fechado sem confirmação do D-1; "
                           "valor provisório, fora do total")
        for estado_, rotulo in ((SEM_COLETA, "sem coleta"), (SEM_FECHAMENTO, "sem fechamento no ledger"),
                                (PARCIAL, "com fechamento parcial"), (INTRADIA, "só intradia (D0)")):
            n = sum(1 for e in dias_estado.values() if e == estado_)
            if n:
                motivos.append(f"{n} dia(s) {rotulo}")

        campanhas = _campanhas(minhas, dias_estado, total_valido=(verdade == REAL and somavel))
        removidas_com_gasto = sum(1 for c in campanhas
                                  if c["removida"] and (c["custo_micros_coberto"] or 0) > 0)
        if removidas_com_gasto:
            motivos.append(f"{removidas_com_gasto} campanha(s) removida(s) com gasto, incluída(s) na soma")

        colhidas = [t for t in (_instante(l.get("colhida_em")) for l in minhas) if t is not None]
        meus_fechos = [f for f in fechamentos
                       if str(f.get("job") or "") in JOBS_DO_FATO
                       and str(f.get("resultado") or "") in ("ok", "parcial")
                       and conta in contas_lidas(f)]
        encerradas = [t for t in (_instante(f.get("encerrada_em")) for f in meus_fechos) if t is not None]
        ultima_colhida = max(colhidas) if colhidas else None

        saida_contas.append({
            "customer_id": conta,
            "moeda": moeda,
            "verdade": verdade,
            "motivos": motivos,
            "custo_micros": coberto if (verdade == REAL and somavel) else None,
            "custo_micros_coberto": coberto if (somavel and tem_valor) else None,
            "dias": serie,
            "frescor": {
                "ultima_colhida_em": _iso(ultima_colhida),
                "ultimo_fechamento_em": _iso(max(encerradas) if encerradas else None),
                "idade_horas": (round((agora - ultima_colhida).total_seconds() / 3600, 1)
                                if ultima_colhida is not None else None),
            },
            "campanhas": campanhas,
            "campanhas_removidas_com_gasto": removidas_com_gasto,
        })

    # Totais por moeda: nunca se soma BRL com USD.
    por_moeda: Dict[str, Dict[str, Any]] = {}
    for c in saida_contas:
        if c["moeda"] is None:
            continue
        m = por_moeda.setdefault(c["moeda"], {"contas": [], "custo_micros": 0,
                                              "custo_micros_coberto": 0, "completo": True})
        m["contas"].append(c["customer_id"])
        m["custo_micros_coberto"] += c["custo_micros_coberto"] or 0
        if c["custo_micros"] is None:
            m["completo"] = False
        else:
            m["custo_micros"] += c["custo_micros"]
    # Conta sem moeda conhecida que NÃO é zero medido pode ser de qualquer
    # moeda: nenhum total por moeda pode se dizer completo enquanto ela existir.
    incertas = [c["customer_id"] for c in saida_contas
                if c["moeda"] is None and c["custo_micros"] != 0]
    for m in por_moeda.values():
        if not m.pop("completo") or incertas:
            m["custo_micros"] = None
    if incertas:
        detalhe.append(f"{len(incertas)} conta(s) sem moeda conhecida e sem custo completo "
                       f"{incertas}: nenhum total por moeda é completo")
    # Só conta como "sem moeda" quem tem gasto que não dá para atribuir a uma
    # moeda (moedas divergentes). Conta vazia ou indisponível não tem o que somar.
    sem_moeda = [c["customer_id"] for c in saida_contas
                 if c["moeda"] is None and any("moedas divergentes" in m for m in c["motivos"])]
    if sem_moeda:
        detalhe.append(f"{len(sem_moeda)} conta(s) sem moeda determinável, fora dos totais: {sem_moeda}")

    verdades = [c["verdade"] for c in saida_contas]
    if not verdades or all(v == INDISPONIVEL for v in verdades):
        verdade_geral = INDISPONIVEL
    elif all(v == REAL for v in verdades) and not sem_moeda and not incertas:
        verdade_geral = REAL
    else:
        verdade_geral = PARCIAL_V

    return {
        "fonte": FONTE,
        "periodo": {"inicio": periodo.inicio.isoformat(), "fim": periodo.fim.isoformat(),
                    "dias": periodo.dias},
        "verdade": verdade_geral,
        "detalhe": detalhe,
        "moedas": por_moeda,
        "contas": saida_contas,
        "calculado_em": agora.astimezone(timezone.utc).isoformat(),
    }


def _campanhas(minhas: Sequence[Mapping[str, Any]], dias_estado: Mapping[date, str], *,
               total_valido: bool) -> List[Dict[str, Any]]:
    por_campanha: Dict[str, List[Mapping[str, Any]]] = {}
    for l in minhas:
        por_campanha.setdefault(str(l.get("campaign_id")), []).append(l)

    saida = []
    for cid, ls in sorted(por_campanha.items()):
        # A identidade descritiva vem da leitura MAIS NOVA DENTRO DO PERÍODO.
        # ⚠️ Não é o status de hoje: uma campanha removida depois do fim do
        # período aparece com o status que tinha nele. `status_lido_em` diz de
        # quando é o status; o estado atual mora no inventário.
        recente = max(ls, key=lambda l: (_instante(l.get("colhida_em"))
                                         or datetime.min.replace(tzinfo=timezone.utc),
                                         str(l.get("metric_date"))))
        brutos = [_micros(l.get("custo_micros")) for l in ls]
        valores = [v for v in brutos if v is not None]
        status = recente.get("campaign_status")
        colhidas = [t for t in (_instante(l.get("colhida_em")) for l in ls) if t is not None]
        saida.append({
            "campaign_id": cid,
            "volc_campaign_id": recente.get("volc_campaign_id"),
            "nome": recente.get("campaign_name"),
            "status": status,
            "canal": recente.get("advertising_channel_type"),
            "removida": status == "REMOVED",
            "status_lido_em": _iso(_instante(recente.get("colhida_em"))),
            # Total da campanha só vale se a CONTA tem todos os dias fechados:
            # dia sem coleta pode esconder gasto dela.
            "custo_micros": sum(valores) if (total_valido and None not in brutos) else None,
            "custo_micros_coberto": sum(valores) if valores else None,
            "dias_com_linha": len(ls),
            "origens": sorted({str(l.get("origem_janela")) for l in ls if l.get("origem_janela")}),
            "ultima_colhida_em": _iso(max(colhidas) if colhidas else None),
        })
    return saida
