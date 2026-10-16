"""Ponte com o Simulator Lab (thread E): `RegistroObservacao` → `Observacao` (thread A) e verdade contrafactual.

Importa `volc_dil.fundacao.simulador` só dentro das funções: o pacote shadow funciona sem ele, e os
testes que dependem dele usam `pytest.importorskip`.

Regras do adaptador (as do contrato da A, aplicadas a um registro que não traz payload bruto):

| registro do simulador | Observacao |
|---|---|
| `observed` com valor ≠ 0 | `observed` |
| `observed` com 0 (forma do zero falso / MCP) | `missing` `observado_zero_sem_confirmacao` (02 §4: zero afirmado é `zero_confirmed`) |
| `zero_confirmed` de custo/cliques/impressões Google Ads campanha × dia | `missing` `zero_sem_prova_de_linha` — mesma regra do adaptador v21 quando o payload não vem na junção (R3: o zero sintetizado sai idêntico ao confirmado) |
| `zero_confirmed` de outra fonte | `zero_confirmed` |
| `late` (coleta atrasada COM valor) | `observed`/`zero_confirmed` com motivo `coleta_atrasada`; o atraso já está no `available_at` |
| `partial` | `partial` com `cobertura_ppm` de `cobertura_ate` |
| `custom_key_efetiva ≠ custom_key_solicitada` | `invalid` `chave_substituida:<pedida>-><devolvida>` (regra do adaptador JoinAds v2) |
| `missing`/`unavailable`/`unsupported`/`invalid` | idem, com o motivo do registro |
| `pageviews` | descartado (sem `Metrica`; pageview não é sessão) |

Receita JoinAds ganha as dimensões que o adaptador v2 produz (`custom_key`, `custom_value`,
`revenue_basis=client`), para que snapshot e junção tratem simulador e dado real do mesmo jeito.
A verdade (`Mundo`) só é lida por `VerdadeSimulador`, para AVALIAÇÃO.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from fractions import Fraction
from typing import Optional, Sequence

from volc_dil.contracts.vocab import Metrica, ValueKind

from ..observacao.modelo import Coletor, EntidadeRef, Observacao, ObservacaoInvalida
from ..observacao.vocab import COBERTURA_PPM_MAX, COBERTURA_PPM_MIN, StatusObservacao
from .avaliacao import FluxoSintetico
from .snapshot import CambioDeclarado
from .tipos import BPS, EntidadeCampanha

_METRICA = {"cost": Metrica.CUSTO, "revenue": Metrica.RECEITA, "clicks": Metrica.CLIQUES,
            "impressions": Metrica.IMPRESSOES, "sessions": Metrica.SESSOES, "destino": Metrica.CONVERSOES}


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def registro_para_observacao(r, versao_simulador: str = "desconhecida") -> Optional[Observacao]:
    """Um `RegistroObservacao` → `Observacao` canônica, ou None se a métrica não tem lugar no vocabulário."""
    metrica = _METRICA.get(r.metrica)
    if metrica is None:
        return None
    ini, fim = _dt(r.janela_inicio), _dt(r.janela_fim)
    obs_at, disp, ing = _dt(r.observed_at), _dt(r.available_at), _dt(r.ingested_at)
    valor, status, motivo, cob = r.valor, r.status, r.motivo, None
    if r.custom_key_solicitada and r.custom_key_efetiva and r.custom_key_efetiva != r.custom_key_solicitada:
        status, valor, motivo = "invalid", None, f"chave_substituida:{r.custom_key_solicitada}->{r.custom_key_efetiva}"
    elif status == "late":
        status = "zero_confirmed" if valor == 0 else "observed"
        motivo = f"coleta_atrasada:previsto={r.available_previsto}"
    if status == "observed" and valor == 0:
        status, valor, motivo = "missing", None, "observado_zero_sem_confirmacao"
    if (status == "zero_confirmed" and r.fonte == "google_ads" and r.entidade_tipo == "campaign"
            and metrica in (Metrica.CUSTO, Metrica.CLIQUES, Metrica.IMPRESSOES)):
        status, valor, motivo = "missing", None, "zero_sem_prova_de_linha"
    if status == "partial":
        ate = _dt(r.cobertura_ate) if r.cobertura_ate else obs_at
        ppm = int((ate - ini).total_seconds() * 1_000_000 // (fim - ini).total_seconds())
        cob = max(COBERTURA_PPM_MIN, min(COBERTURA_PPM_MAX, ppm))
        motivo = motivo or "janela_aberta"
    dims = dict(r.dimensoes)
    vk = None
    if metrica is Metrica.RECEITA:
        vk = ValueKind.REPORTED_REVENUE
        if r.fonte == "joinads":
            dims["revenue_basis"] = "client"
            if r.custom_key_efetiva:
                dims["custom_key"] = r.custom_key_efetiva
            if r.entidade_tipo == "campaign":
                dims["custom_value"] = r.entidade
    return Observacao(
        fonte=r.fonte, conta=r.conta, entidade=EntidadeRef(r.entidade_tipo, r.entidade), grao=tuple(r.grao),
        metrica=metrica, valor=valor, unidade=r.unidade, moeda=r.moeda if r.unidade == "micros" else None,
        janela_inicio=ini, janela_fim=fim, timezone=r.timezone, observed_at=obs_at, available_at=disp, ingested_at=ing,
        run_id=r.run_id, lote_id=r.leitura_id, payload_sha256=r.payload_sha256,
        payload_ref=f"simulador:{r.leitura_id}:sha256:{r.payload_sha256}",
        schema_version=f"simulador.{r.fonte}.{r.tipo_leitura}", coletor=Coletor(f"simulador_{r.fonte}", versao_simulador),
        status=status, motivo=motivo, value_kind=vk, dimensoes=tuple(sorted(dims.items())), cobertura_ppm=cob,
    )


@dataclass
class ResultadoAdaptacaoSimulador:
    observacoes: tuple[Observacao, ...]
    n_registros: int
    descartados_sem_metrica: int
    rejeitados: list[tuple[str, str]] = field(default_factory=list)  # (obs_id, erro)
    por_regra: dict = field(default_factory=dict)


def observacoes_do_simulador(registros: Sequence) -> ResultadoAdaptacaoSimulador:
    from volc_dil.fundacao.simulador import VERSAO_SIMULADOR

    saida, rej, sem, regras = [], [], 0, {}
    for r in registros:
        try:
            o = registro_para_observacao(r, VERSAO_SIMULADOR)
        except ObservacaoInvalida as e:
            rej.append((r.obs_id, str(e)))
            continue
        if o is None:
            sem += 1
            continue
        if o.status.value != r.status:
            chave = f"{r.status}->{o.status.value}:{(o.motivo or '').split(':')[0]}"
            regras[chave] = regras.get(chave, 0) + 1
        saida.append(o)
    return ResultadoAdaptacaoSimulador(tuple(saida), len(registros), sem, rej, dict(sorted(regras.items())))


class VerdadeSimulador:
    """Lucro contrafactual por campanha × dia re-simulando o `Mundo` com outra verba (CRN da thread E).

    Campanhas e dias são independentes no simulador (pacing diário, ruído exógeno, maturação por idade),
    então o lucro da célula (c, d) com fator f é lido de um mundo re-simulado com fator f uniforme.
    Lucro em micros BRL: receita USD convertida pela taxa verdadeira do mundo.
    """

    def __init__(self, sim) -> None:
        from volc_dil.fundacao.simulador import gerar_mundo

        self._gerar = gerar_mundo
        self.sim = sim
        m = sim.mundo
        self.ents = [EntidadeCampanha(c.conta, c.id) for c in m.campanhas]
        self.dias = list(m.dias)
        self.existe = m.existe_dia()
        self.orc_base = m.flags["orcamento_hora_micros"][:, ::24].astype("int64")
        self.taxa = Fraction(str(m.params.cambio_brl_por_usd))
        self.usd = [c.moeda_receita == "USD" for c in m.campanhas]
        self._cache: dict[int, dict] = {}
        self.resimulacoes = 0

    def celulas(self) -> list:
        return [(e, d) for c, e in enumerate(self.ents) for i, d in enumerate(self.dias) if self.existe[c, i]]

    def _matriz(self, fator: int) -> dict:
        if fator not in self._cache:
            import numpy as np

            orc = (self.orc_base * fator // BPS // 10_000 * 10_000).astype(np.int64)
            m = self._gerar(self.sim.espec.mundo, self.sim.seed, orcamento_diario_micros=orc)
            self.resimulacoes += 1
            custo, rec = m.diario("custo_final_micros"), m.diario("receita_micros")
            out = {}
            for c, e in enumerate(self.ents):
                for i, d in enumerate(self.dias):
                    if not self.existe[c, i]:
                        continue
                    r = int(rec[c, i])
                    r_brl = r * self.taxa.numerator // self.taxa.denominator if self.usd[c] else r
                    out[(e, d)] = r_brl - int(custo[c, i])
            self._cache[fator] = out
        return self._cache[fator]

    def lucros(self, plano: dict) -> dict:
        out = {}
        for cel, fator in plano.items():
            v = self._matriz(int(fator)).get(cel)
            if v is not None:
                out[cel] = v
        return out


def fluxo_do_simulador(nome: str, seed: int, *, n_campanhas: Optional[int] = None, n_dias: Optional[int] = None) -> FluxoSintetico:
    from volc_dil.fundacao.simulador import VERSAO_CATALOGO, VERSAO_SIMULADOR, simular

    sim = simular(nome, seed, n_campanhas=n_campanhas, n_dias=n_dias)
    ad = observacoes_do_simulador(sim.leituras.registros)
    taxa = Fraction(str(sim.mundo.params.cambio_brl_por_usd))
    cambio = CambioDeclarado("USD", "BRL", taxa.numerator, taxa.denominator, "declarado:cambio_sintetico_do_simulador")
    presos = sum(1 for e in sim.leituras.execucoes if e.get("status") == "running")
    meta = {"gerador": f"simulador@{VERSAO_SIMULADOR}/catalogo@{VERSAO_CATALOGO}", "cenario": nome,
            "n_registros": ad.n_registros, "n_observacoes": len(ad.observacoes), "descartados_sem_metrica": ad.descartados_sem_metrica,
            "rejeitados": len(ad.rejeitados), "regras_aplicadas": ad.por_regra, "runs_presos": presos,
            "inicio": sim.mundo.dias[0].isoformat(), "n_dias": len(sim.mundo.dias)}
    return FluxoSintetico(ad.observacoes, VerdadeSimulador(sim), (cambio,), nome, seed, meta)


def cortes_do_simulador(fluxo: FluxoSintetico, *, dia_inicial: int = 5, passo: timedelta = timedelta(hours=1)) -> tuple:
    from datetime import date

    from .fluxo import cortes_regulares
    from .linhas_formato_real import instante_local

    ini = date.fromisoformat(fluxo.meta["inicio"])
    n = fluxo.meta["n_dias"]
    return cortes_regulares(instante_local(ini + timedelta(days=dia_inicial), 0), instante_local(ini + timedelta(days=n - 1), 0), passo)
