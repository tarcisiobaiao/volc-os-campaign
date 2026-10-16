"""Normalizador tolerante a schema drift: payload bruto versionado → observações + rejeições.

Regras:

- esquema escolhido pela versão do payload; versão desconhecida → rejeição `schema_desconhecido`;
- JSON lido com `parse_float=Decimal` (dinheiro nunca passa por float); float que chegue mesmo
  assim → `invalid` (`float_recusado:<campo>`);
- campo obrigatório ausente → `invalid` com motivo `campo_obrigatorio_ausente:<campo>` (ou
  rejeição da linha, quando é o campo de identidade e não há entidade a quem atribuir);
- campos extras → ignorados e listados em `campos_extras` (drift registrado, não fatal);
- aliases declarados (ex.: `custon_key`/`custom_key` da JoinAds) são aceitos;
- chave devolvida diferente da pedida (JoinAds troca `custom_key` em silêncio quando não há
  dado) → a linha é REJEITADA (nunca vira entidade falsa) e cada entidade esperada recebe
  `invalid` com motivo `chave_substituida:<pedida>-><devolvida>`;
- entidade esperada sem linha numa resposta íntegra → `missing` (`linha_ausente_na_resposta`);
- valor nulo explícito da fonte → `missing` (`valor_nulo_na_fonte:<campo>`), nunca 0;
- 0 explícito → `zero_confirmed`; janela ainda aberta em `observed_at` → `partial` com cobertura
  proporcional ao tempo decorrido (motivo `janela_aberta`).

Puro: recebe bytes e contexto, devolve dados. Quem grava é outra camada.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Optional, Sequence

from ...contracts.money import MICROS
from ...contracts.vocab import Metrica, ValueKind
from . import chaves
from .modelo import Coletor, EntidadeRef, Observacao
from .vocab import COBERTURA_PPM_MAX, COBERTURA_PPM_MIN, StatusObservacao, Unidade

Validador = Callable[[Mapping[str, Any], "ContextoLeitura"], Optional[str]]


@dataclass(frozen=True)
class CampoMetrica:
    nomes: tuple[str, ...]  # nomes[0] é o canônico; os demais, aliases aceitos
    metrica: Metrica
    unidade: Unidade
    value_kind: Optional[ValueKind] = None

    @property
    def canonico(self) -> str:
        return self.nomes[0]


@dataclass(frozen=True)
class EsquemaPayload:
    schema_version: str
    campo_entidade: tuple[str, ...]  # nome canônico + aliases do id da entidade na linha
    campos_metrica: tuple[CampoMetrica, ...]
    campo_chave: Optional[tuple[str, ...]] = None  # chave de dimensão devolvida pela fonte (ex.: custom_key)
    campos_obrigatorios: tuple[tuple[str, ...], ...] = ()  # obrigatórios não mapeados (ex.: date)
    campo_linhas: Optional[str] = None  # None: o payload é a lista de linhas
    validador: Optional[Validador] = None  # regra extra por linha; devolve motivo de invalidez ou None

    @property
    def nomes_conhecidos(self) -> frozenset[str]:
        nomes: set[str] = set(self.campo_entidade)
        for c in self.campos_metrica:
            nomes.update(c.nomes)
        if self.campo_chave:
            nomes.update(self.campo_chave)
        for grupo in self.campos_obrigatorios:
            nomes.update(grupo)
        return frozenset(nomes)


@dataclass(frozen=True)
class PayloadBruto:
    schema_version: str
    corpo: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.corpo).hexdigest()

    @property
    def ref(self) -> str:
        return f"sha256:{self.sha256}"


@dataclass(frozen=True)
class ContextoLeitura:
    fonte: str
    conta: str
    entidade_tipo: str
    grao: tuple[str, ...]
    janela_inicio: datetime
    janela_fim: datetime
    timezone: str
    observed_at: datetime
    available_at: datetime
    ingested_at: datetime
    run_id: str
    lote_id: str
    coletor: Coletor
    moeda: Optional[str] = None
    chave_pedida: Optional[str] = None
    dimensoes: tuple[tuple[str, str], ...] = ()
    entidades_esperadas: tuple[str, ...] = ()
    request_id: Optional[str] = None
    source_updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class Rejeicao:
    """Algo do payload que não pôde virar observação (vai para `dead_letter`)."""

    motivo: str
    indice: Optional[int] = None
    detalhe: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ResultadoNormalizacao:
    schema_version: str
    payload_sha256: str
    observacoes: tuple[Observacao, ...]
    rejeicoes: tuple[Rejeicao, ...]
    campos_extras: tuple[str, ...] = field(default_factory=tuple)

    def por_status(self) -> dict[str, int]:
        saida: dict[str, int] = {}
        for o in self.observacoes:
            saida[o.status.value] = saida.get(o.status.value, 0) + 1
        return dict(sorted(saida.items()))


# --------------------------------------------------------------------------- construção
def _obs(
    ctx: ContextoLeitura,
    payload: PayloadBruto,
    entidade_id: str,
    campo: CampoMetrica,
    status: StatusObservacao,
    valor: Optional[int] = None,
    motivo: Optional[str] = None,
    cobertura_ppm: Optional[int] = None,
) -> Observacao:
    moeda = ctx.moeda if campo.unidade is Unidade.MICROS else None
    return Observacao(
        fonte=ctx.fonte,
        conta=ctx.conta,
        entidade=EntidadeRef(ctx.entidade_tipo, entidade_id),
        grao=ctx.grao,
        dimensoes=ctx.dimensoes,
        metrica=campo.metrica,
        value_kind=campo.value_kind,
        valor=valor,
        unidade=campo.unidade,
        moeda=moeda,
        janela_inicio=ctx.janela_inicio,
        janela_fim=ctx.janela_fim,
        timezone=ctx.timezone,
        observed_at=ctx.observed_at,
        source_updated_at=ctx.source_updated_at,
        available_at=ctx.available_at,
        ingested_at=ctx.ingested_at,
        run_id=ctx.run_id,
        request_id=ctx.request_id,
        lote_id=ctx.lote_id,
        payload_sha256=payload.sha256,
        payload_ref=payload.ref,
        schema_version=payload.schema_version,
        coletor=ctx.coletor,
        status=status,
        motivo=motivo,
        cobertura_ppm=cobertura_ppm,
    )


def _cobertura_ppm(ctx: ContextoLeitura) -> int:
    total = (ctx.janela_fim - ctx.janela_inicio).total_seconds()
    decorrido = (ctx.observed_at - ctx.janela_inicio).total_seconds()
    ppm = int(decorrido * 1_000_000 // total) if total > 0 else COBERTURA_PPM_MIN
    return max(COBERTURA_PPM_MIN, min(COBERTURA_PPM_MAX, ppm))


def _primeiro(linha: Mapping[str, Any], nomes: Sequence[str]) -> tuple[bool, Any]:
    for n in nomes:
        if n in linha:
            return True, linha[n]
    return False, None


def _converter(bruto: Any, campo: CampoMetrica) -> tuple[Optional[int], Optional[str]]:
    """(valor, motivo_de_invalidez). Sem float e sem coerção silenciosa."""
    nome = campo.canonico
    if isinstance(bruto, bool):
        return None, f"valor_invalido:{nome}"
    if isinstance(bruto, float):
        return None, f"float_recusado:{nome}"
    try:
        dec = bruto if isinstance(bruto, Decimal) else Decimal(str(bruto).strip()) if isinstance(bruto, (int, str)) else None
    except InvalidOperation:
        dec = None
    if dec is None or not dec.is_finite():
        return None, f"valor_invalido:{nome}"
    if campo.unidade is Unidade.MICROS:
        micros = dec * MICROS
        if micros != micros.to_integral_value():
            return None, f"precisao_acima_de_micros:{nome}"  # sem arredondamento silencioso
        return int(micros), None  # a moeda vem do contexto, nunca do número
    if dec != dec.to_integral_value():
        return None, f"contagem_fracionaria:{nome}"
    if dec < 0:
        return None, f"contagem_negativa:{nome}"
    return int(dec), None


def observacoes_sem_dado(
    ctx: ContextoLeitura,
    payload: PayloadBruto,
    campos: Sequence[CampoMetrica],
    status: StatusObservacao,
    motivo: str,
) -> tuple[Observacao, ...]:
    """Para cada entidade esperada × métrica: missing/late/unavailable/unsupported/invalid com motivo.

    Ex.: HTTP 503 → `unavailable` (payload = corpo do erro); D-1 ainda não publicado → `late`;
    métrica que a fonte não mede → `unsupported`.
    """
    if status in (StatusObservacao.OBSERVED, StatusObservacao.ZERO_CONFIRMED, StatusObservacao.PARTIAL):
        raise ValueError("observacoes_sem_dado só emite status sem valor")
    return tuple(_obs(ctx, payload, e, c, status, motivo=motivo) for e in ctx.entidades_esperadas for c in campos)


# --------------------------------------------------------------------------- normalização
def normalizar(
    payload: PayloadBruto,
    esquemas: Mapping[str, EsquemaPayload],
    ctx: ContextoLeitura,
) -> ResultadoNormalizacao:
    esquema = esquemas.get(payload.schema_version)
    if esquema is None:
        return ResultadoNormalizacao(
            payload.schema_version, payload.sha256, (),
            (Rejeicao("schema_desconhecido", detalhe=(("schema_version", payload.schema_version),)),),
        )
    campos = esquema.campos_metrica

    def falha_total(motivo: str) -> ResultadoNormalizacao:
        obs = observacoes_sem_dado(ctx, payload, campos, StatusObservacao.INVALID, motivo)
        return ResultadoNormalizacao(payload.schema_version, payload.sha256, obs, (Rejeicao(motivo),))

    try:
        corpo = json.loads(payload.corpo.decode("utf-8"), parse_float=Decimal)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return falha_total("payload_nao_json")
    linhas = corpo if esquema.campo_linhas is None else (corpo.get(esquema.campo_linhas) if isinstance(corpo, dict) else None)
    if not isinstance(linhas, list):
        return falha_total("estrutura_inesperada")

    conhecidos = esquema.nomes_conhecidos
    extras: set[str] = set()
    rejeicoes: list[Rejeicao] = []
    por_entidade: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
    devolvidas: set[str] = set()

    for i, linha in enumerate(linhas):
        if not isinstance(linha, dict):
            rejeicoes.append(Rejeicao("linha_nao_objeto", i))
            continue
        extras.update(k for k in linha if k not in conhecidos)
        if esquema.campo_chave:
            achou, chave = _primeiro(linha, esquema.campo_chave)
            if not achou or chave is None:
                rejeicoes.append(Rejeicao(f"campo_obrigatorio_ausente:{esquema.campo_chave[0]}", i))
                continue
            if ctx.chave_pedida is not None and str(chave) != ctx.chave_pedida:
                devolvidas.add(str(chave))
                rejeicoes.append(
                    Rejeicao("chave_substituida", i, (("devolvida", str(chave)), ("pedida", ctx.chave_pedida)))
                )
                continue
        achou, ent = _primeiro(linha, esquema.campo_entidade)
        if not achou or ent is None or isinstance(ent, bool) or not isinstance(ent, (str, int)) or not str(ent).strip():
            rejeicoes.append(Rejeicao(f"campo_obrigatorio_ausente:{esquema.campo_entidade[0]}", i))
            continue
        ent_id = str(ent)
        if ent_id != ent_id.strip() or chaves.tem_controle(ent_id):
            rejeicoes.append(Rejeicao("entidade_invalida", i))
            continue
        por_entidade.setdefault(ent_id, []).append((i, linha))

    observacoes: list[Observacao] = []
    janela_aberta = ctx.observed_at < ctx.janela_fim
    for ent_id, ocorrencias in sorted(por_entidade.items()):
        if len(ocorrencias) > 1:
            observacoes.extend(_obs(ctx, payload, ent_id, c, StatusObservacao.INVALID, motivo="linha_duplicada") for c in campos)
            continue
        _, linha = ocorrencias[0]
        motivo_linha = None
        for grupo in esquema.campos_obrigatorios:
            if not _primeiro(linha, grupo)[0]:
                motivo_linha = f"campo_obrigatorio_ausente:{grupo[0]}"
                break
        if motivo_linha is None and esquema.validador is not None:
            motivo_linha = esquema.validador(linha, ctx)
        for c in campos:
            if motivo_linha is not None:
                observacoes.append(_obs(ctx, payload, ent_id, c, StatusObservacao.INVALID, motivo=motivo_linha))
                continue
            achou, bruto = _primeiro(linha, c.nomes)
            if not achou:
                observacoes.append(_obs(ctx, payload, ent_id, c, StatusObservacao.INVALID, motivo=f"campo_obrigatorio_ausente:{c.canonico}"))
                continue
            if bruto is None:
                observacoes.append(_obs(ctx, payload, ent_id, c, StatusObservacao.MISSING, motivo=f"valor_nulo_na_fonte:{c.canonico}"))
                continue
            valor, motivo = _converter(bruto, c)
            if motivo is not None:
                observacoes.append(_obs(ctx, payload, ent_id, c, StatusObservacao.INVALID, motivo=motivo))
            elif c.unidade is Unidade.MICROS and ctx.moeda is None:
                observacoes.append(_obs(ctx, payload, ent_id, c, StatusObservacao.INVALID, motivo="moeda_nao_declarada"))
            elif janela_aberta:
                observacoes.append(_obs(ctx, payload, ent_id, c, StatusObservacao.PARTIAL, valor=valor,
                                        motivo="janela_aberta", cobertura_ppm=_cobertura_ppm(ctx)))
            elif valor == 0:
                observacoes.append(_obs(ctx, payload, ent_id, c, StatusObservacao.ZERO_CONFIRMED, valor=0))
            else:
                observacoes.append(_obs(ctx, payload, ent_id, c, StatusObservacao.OBSERVED, valor=valor))

    vistos = set(por_entidade)
    faltantes = [e for e in ctx.entidades_esperadas if e not in vistos]
    if faltantes:
        if devolvidas:
            motivo = f"chave_substituida:{ctx.chave_pedida}->{','.join(sorted(devolvidas))}"
            status = StatusObservacao.INVALID
        elif rejeicoes:
            motivo, status = "resposta_com_linhas_rejeitadas", StatusObservacao.INVALID
        else:
            motivo, status = "linha_ausente_na_resposta", StatusObservacao.MISSING
        sub = ContextoLeitura(**{**ctx.__dict__, "entidades_esperadas": tuple(faltantes)})
        observacoes.extend(observacoes_sem_dado(sub, payload, campos, status, motivo))

    return ResultadoNormalizacao(
        payload.schema_version,
        payload.sha256,
        tuple(observacoes),
        tuple(rejeicoes),
        tuple(sorted(extras)),
    )
