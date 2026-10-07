"""Contrato semantico da coleta Google Ads -> Supabase.

Zero e um valor medido. Ausencia, nao aplicabilidade e falha nao carregam valor.
Uma chamada que voltou sem itens e ``vazio_confirmado``; excecao e ``falhou``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

COLETOR_VERSAO = 3
API_VERSAO = "v25"

# Uma familia e o nome da PERGUNTA que a leitura respondeu. Ela existe porque o
# `tipo_sinal` do ledger v12_01 e um CHECK fechado em seis valores, e leituras
# diferentes podem precisar caber sob o mesmo valor sem se confundirem. Formato
# fechado de proposito: a familia entra na chave de idempotencia, e um separador
# ou um sinal de igual dentro dela criaria ambiguidade na chave.
_FAMILIA = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


class EstadoColeta(str, Enum):
    COM_DADOS = "com_dados"
    VAZIO_CONFIRMADO = "vazio_confirmado"
    PARCIAL = "parcial"
    INELEGIVEL = "inelegivel"
    NAO_SUPORTADO = "nao_suportado"
    FALHOU = "falhou"


class EstadoValor(str, Enum):
    MEDIDO = "medido"
    AUSENTE = "ausente"
    NAO_APLICAVEL = "nao_aplicavel"
    FALHOU = "falhou"


def _jsonavel(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Enum):
        return valor.value
    raise TypeError(f"tipo nao serializavel: {type(valor).__name__}")


def _json_canonico(valor: Any) -> str:
    return json.dumps(
        valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=_jsonavel,
    )


@dataclass(frozen=True)
class Item:
    tipo_item: str
    payload: dict[str, Any]
    recurso_externo: str | None = None

    def serializar(self, ordinal: int) -> dict[str, Any]:
        return {
            "ordinal": ordinal,
            "tipo_item": self.tipo_item,
            "recurso_externo": self.recurso_externo,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class Metrica:
    recurso_tipo: str
    recurso_externo: str
    nome: str
    estado_valor: EstadoValor
    valor_numerico: int | float | Decimal | None = None
    valor_texto: str | None = None
    unidade: str | None = None
    moeda: str | None = None

    def __post_init__(self) -> None:
        tem_numero = self.valor_numerico is not None
        tem_texto = self.valor_texto is not None
        if self.estado_valor is EstadoValor.MEDIDO and tem_numero == tem_texto:
            raise ValueError("metrica medida exige exatamente um valor")
        if self.estado_valor is not EstadoValor.MEDIDO and (tem_numero or tem_texto):
            raise ValueError("metrica nao medida nao pode carregar valor")

    def serializar(self) -> dict[str, Any]:
        return {
            "recurso_tipo": self.recurso_tipo,
            "recurso_externo": self.recurso_externo,
            "nome": self.nome,
            "estado_valor": self.estado_valor.value,
            "valor_numerico": None if self.valor_numerico is None else str(self.valor_numerico),
            "valor_texto": self.valor_texto,
            "unidade": self.unidade,
            "moeda": self.moeda,
        }


@dataclass
class DocumentoColeta:
    tipo_sinal: str
    estado: EstadoColeta
    customer_id: str
    login_customer_id: str
    competencia: date
    coletada_em: datetime
    bucket: str
    quantidade: int | None
    payload: dict[str, Any] = field(default_factory=dict)
    itens: list[Item] = field(default_factory=list)
    metricas: list[Metrica] = field(default_factory=list)
    volc_campaign_id: str | None = None
    campaign_id: str | None = None
    janela_inicio: date | None = None
    janela_fim: date | None = None
    request_ids: list[str] = field(default_factory=list)
    erro_codigo: str | None = None
    erro_classe: str | None = None
    erro_detalhe: str | None = None
    familia: str | None = None

    def __post_init__(self) -> None:
        if self.familia is not None and not _FAMILIA.fullmatch(self.familia):
            raise ValueError("familia possui formato invalido")
        if self.coletada_em.tzinfo is None:
            raise ValueError("coletada_em precisa de timezone")
        if (self.volc_campaign_id is None) != (self.campaign_id is None):
            raise ValueError("identidade interna e externa da campanha viajam juntas")
        if self.estado is EstadoColeta.COM_DADOS and (self.quantidade or 0) <= 0:
            raise ValueError("com_dados exige quantidade positiva")
        if self.estado is EstadoColeta.VAZIO_CONFIRMADO and self.quantidade != 0:
            raise ValueError("vazio_confirmado exige quantidade zero")
        if self.estado in {
            EstadoColeta.INELEGIVEL, EstadoColeta.NAO_SUPORTADO, EstadoColeta.FALHOU,
        } and self.quantidade is not None:
            raise ValueError("estado sem leitura nao pode inventar quantidade")
        if self.estado is EstadoColeta.FALHOU and not (self.erro_codigo and self.erro_classe):
            raise ValueError("falha precisa de codigo e classe")

    @classmethod
    def agora(cls, **kwargs: Any) -> "DocumentoColeta":
        instante = datetime.now(timezone.utc)
        return cls(coletada_em=instante, competencia=instante.date(), **kwargs)

    def serializar(self) -> dict[str, Any]:
        escopo = self.campaign_id or "conta"
        # Uma falha não pode ocupar para sempre a chave do intervalo e esconder
        # uma repetição posterior bem-sucedida. Estado entra na identidade para
        # preservar ambos os recibos; código/classe distinguem falhas diferentes.
        desfecho = self.estado.value
        if self.estado is EstadoColeta.FALHOU:
            desfecho = "|".join((desfecho, self.erro_codigo or "", self.erro_classe or ""))
        partes = [
            self.customer_id, escopo, self.tipo_sinal, self.bucket,
            str(COLETOR_VERSAO), desfecho,
        ]
        if self.familia is not None:
            # Componente ADICIONAL, nunca posicional: sem familia a chave sai
            # byte a byte igual a de antes desta linha existir, e o que ja esta
            # gravado continua deduplicando contra a proxima repeticao. O
            # prefixo `familia=` desambigua do sufixo de uma falha, cujos dois
            # componentes sao codigo e classe de excecao — nenhum deles carrega
            # `=`, entao nenhuma falha consegue se disfarcar de familia.
            partes.append(f"familia={self.familia}")
        chave = hashlib.sha256("|".join(partes).encode()).hexdigest()
        # A familia viaja no payload porque a RPC v12_01 grava `documento->
        # 'payload'` inteiro e nao tem coluna para ela. O hash cobre o payload
        # efetivo, entao o recibo continua verificavel campo a campo.
        payload = (
            self.payload if self.familia is None
            else {**self.payload, "familia": self.familia}
        )
        payload_hash = hashlib.sha256(_json_canonico(payload).encode()).hexdigest()
        return {
            "chave_idempotencia": chave,
            "tipo_sinal": self.tipo_sinal,
            "familia": self.familia,
            "estado": self.estado.value,
            "customer_id": self.customer_id,
            "login_customer_id": self.login_customer_id,
            "volc_campaign_id": self.volc_campaign_id,
            "campaign_id": self.campaign_id,
            "janela_inicio": self.janela_inicio.isoformat() if self.janela_inicio else None,
            "janela_fim": self.janela_fim.isoformat() if self.janela_fim else None,
            "competencia": self.competencia.isoformat(),
            "coletada_em": self.coletada_em.isoformat(),
            "bucket": self.bucket,
            "api_versao": API_VERSAO,
            "coletor_versao": COLETOR_VERSAO,
            "quantidade": self.quantidade,
            "request_ids": self.request_ids,
            "payload": payload,
            "payload_sha256": payload_hash,
            "erro_codigo": self.erro_codigo,
            "erro_classe": self.erro_classe,
            "erro_detalhe": self.erro_detalhe,
            "itens": [item.serializar(i) for i, item in enumerate(self.itens)],
            "metricas": [metrica.serializar() for metrica in self.metricas],
        }


def metrica_de_dict(
    objeto: dict[str, Any], caminho: tuple[str, ...], *, recurso_tipo: str,
    recurso_externo: str, nome: str, unidade: str | None = None,
    moeda: str | None = None,
) -> Metrica:
    atual: Any = objeto
    for parte in caminho:
        if not isinstance(atual, dict) or parte not in atual:
            return Metrica(
                recurso_tipo, recurso_externo, nome, EstadoValor.AUSENTE,
                unidade=unidade, moeda=moeda,
            )
        atual = atual[parte]
    if atual is None:
        return Metrica(
            recurso_tipo, recurso_externo, nome, EstadoValor.AUSENTE,
            unidade=unidade, moeda=moeda,
        )
    if isinstance(atual, bool):
        return Metrica(
            recurso_tipo, recurso_externo, nome, EstadoValor.MEDIDO,
            valor_texto=str(atual).lower(), unidade=unidade, moeda=moeda,
        )
    if isinstance(atual, (int, float, Decimal)) or (
        isinstance(atual, str) and atual.replace(".", "", 1).isdigit()
    ):
        return Metrica(
            recurso_tipo, recurso_externo, nome, EstadoValor.MEDIDO,
            valor_numerico=Decimal(str(atual)), unidade=unidade, moeda=moeda,
        )
    return Metrica(
        recurso_tipo, recurso_externo, nome, EstadoValor.MEDIDO,
        valor_texto=str(atual), unidade=unidade, moeda=moeda,
    )


# ── termos de busca: o que o leitor DIGITOU, em três estados ─────────────────
#
# Contrato entre as trilhas (30/09/2026): o mesmo JSON que o motor valida em
# `funnelforge.domain.models.TermosDeBusca`. Cada lado valida o seu.
#
#   presente          consulta feita na janela, com termos
#   vazio_confirmado  consulta feita na janela, zero termos — É informação
#   ausente           ninguém coletou; NUNCA vira lista (nem vazia)
#
# Antes disto a encomenda da copy fixava `termos_de_busca=()` e o prompt dizia
# "vazia — nenhum termo colhido": uma ausência apresentada como medição.

ESTADOS_TERMOS = ("presente", "vazio_confirmado", "ausente")
FUSO_PADRAO = "America/Sao_Paulo"
# Mesmo teto do motor (`pipeline/inventario.LIMITE_DE_TERMOS`). É corte de
# prompt declarado, não amostra estatística.
LIMITE_TERMOS_PADRAO = 25
_FONTE_TERMOS = re.compile(r"^(search_term_view|arquivo:[0-9a-f]{64})$")

# O que parece dado pessoal num termo digitado. Os mesmos padrões do motor:
# um termo descartado de um lado e aceito do outro seria dado pessoal chegando
# a um prompt por uma das portas.
_DADO_PESSOAL = (
    re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),          # CPF
    re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),     # CNPJ
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),                      # e-mail
    re.compile(r"(?:\d[\s.\-]?){10,}"),                          # telefone, cartão
)


def tem_dado_pessoal(termo: str) -> bool:
    return any(r.search(termo or "") for r in _DADO_PESSOAL)


@dataclass(frozen=True)
class JanelaDeTermos:
    inicio: date
    fim: date
    fuso: str = FUSO_PADRAO

    def __post_init__(self) -> None:
        if not isinstance(self.inicio, date) or not isinstance(self.fim, date):
            raise ValueError("janela precisa de datas")
        if self.fim < self.inicio:
            raise ValueError("janela com fim antes do início")

    def para_json(self) -> dict[str, str]:
        return {"inicio": self.inicio.isoformat(), "fim": self.fim.isoformat(),
                "fuso": self.fuso}

    def rotulo(self) -> str:
        return f"{self.inicio.isoformat()} a {self.fim.isoformat()} ({self.fuso})"


@dataclass(frozen=True)
class TermoDeBusca:
    termo: str
    impressoes: int
    cliques: int
    custo: float | None = None

    def __post_init__(self) -> None:
        if not str(self.termo or "").strip():
            raise ValueError("termo vazio")
        if self.impressoes < 0 or self.cliques < 0:
            raise ValueError("contagem negativa")


@dataclass(frozen=True)
class TermosDeBusca:
    """Ver o bloco acima. `para_json()` emite SÓ as chaves do contrato.

    `total_na_fonte` (termos distintos lidos), `descartados_por_dado_pessoal` e
    `limite` (top-N aplicado) são a declaração do corte: ficam no objeto para o
    prompt dizer quanto viu, e não viajam no JSON do contrato.
    """

    estado: str
    janela: JanelaDeTermos | None = None
    coletado_em: str | None = None
    fonte: str | None = None
    termos: tuple[TermoDeBusca, ...] = ()
    motivo_ausencia: str | None = None
    total_na_fonte: int = 0
    descartados_por_dado_pessoal: int = 0
    limite: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "termos", tuple(self.termos))
        if self.estado not in ESTADOS_TERMOS:
            raise ValueError(f"estado {self.estado!r} fora de {ESTADOS_TERMOS}")
        if self.estado in ("ausente", "vazio_confirmado") and self.termos:
            raise ValueError(f"estado '{self.estado}' não pode trazer termos")
        if self.estado == "ausente":
            if not str(self.motivo_ausencia or "").strip():
                raise ValueError("'ausente' precisa dizer por quê (motivo_ausencia)")
            return
        if self.estado == "presente" and not self.termos:
            raise ValueError("estado 'presente' sem nenhum termo")
        faltando = [n for n in ("janela", "coletado_em", "fonte") if not getattr(self, n)]
        if faltando:
            raise ValueError(f"estado '{self.estado}' sem {', '.join(faltando)}")
        if not _FONTE_TERMOS.match(self.fonte or ""):
            raise ValueError("fonte deve ser 'search_term_view' ou 'arquivo:<sha256>'")

    def para_json(self) -> dict[str, Any]:
        return {
            "estado": self.estado,
            "janela": self.janela.para_json() if self.janela else None,
            "coletado_em": self.coletado_em,
            "fonte": self.fonte,
            "termos": [{"termo": t.termo, "impressoes": t.impressoes,
                        "cliques": t.cliques, "custo": t.custo} for t in self.termos],
            "motivo_ausencia": self.motivo_ausencia,
        }

    @classmethod
    def de_json(cls, dados: dict[str, Any]) -> "TermosDeBusca":
        j = dados.get("janela")
        janela = (JanelaDeTermos(date.fromisoformat(j["inicio"]),
                                 date.fromisoformat(j["fim"]),
                                 j.get("fuso") or FUSO_PADRAO) if j else None)
        return cls(
            estado=dados.get("estado", ""), janela=janela,
            coletado_em=dados.get("coletado_em"), fonte=dados.get("fonte"),
            termos=tuple(TermoDeBusca(str(t["termo"]), int(t["impressoes"]),
                                      int(t["cliques"]),
                                      None if t.get("custo") is None else float(t["custo"]))
                         for t in (dados.get("termos") or [])),
            motivo_ausencia=dados.get("motivo_ausencia"),
        )


def termos_ausentes(motivo: str) -> TermosDeBusca:
    return TermosDeBusca(estado="ausente", motivo_ausencia=motivo)


def _inteiro(valor: Any) -> int:
    try:
        return int(str(valor))
    except (TypeError, ValueError):
        return 0


def agregar_linhas_gaql(linhas: list[dict[str, Any]]) -> dict[str, TermoDeBusca]:
    """Linhas de `search_term_view` (uma por termo × dia × grupo) → UM termo.

    Métrica que não veio na linha é o zero do proto3 (o campo foi pedido; a API
    não o imprime quando vale zero). Custo sem `cost_micros` em NENHUMA linha do
    termo fica `None`: não foi medido, e zero seria um custo inventado.
    """
    somas: dict[str, list[Any]] = {}
    for linha in linhas:
        termo = str(((linha.get("search_term_view") or {}).get("search_term")) or "").strip()
        if not termo:
            continue
        m = linha.get("metrics") or {}
        acc = somas.setdefault(termo, [0, 0, None])
        acc[0] += _inteiro(m.get("impressions"))
        acc[1] += _inteiro(m.get("clicks"))
        if m.get("cost_micros") is not None:
            acc[2] = (acc[2] or 0) + _inteiro(m.get("cost_micros"))
    return {
        t: TermoDeBusca(t, imp, cli, None if micros is None else round(micros / 1_000_000, 2))
        for t, (imp, cli, micros) in somas.items()
    }


def termos_de_linhas(
    linhas: list[dict[str, Any]], *, fonte: str, janela: JanelaDeTermos,
    coletado_em: str, limite: int = LIMITE_TERMOS_PADRAO,
) -> TermosDeBusca:
    """Agrega, tira dado pessoal, ordena (cliques, impressões) e corta no top-N.

    Zero linha na janela é `vazio_confirmado`. Linhas que só traziam dado
    pessoal NÃO são vazio (houve busca) nem lista: são `ausente`, com o motivo.
    """
    agregados = agregar_linhas_gaql(linhas)
    if not agregados:
        return TermosDeBusca(estado="vazio_confirmado", janela=janela,
                             coletado_em=coletado_em, fonte=fonte, limite=limite)
    limpos = [t for t in agregados.values() if not tem_dado_pessoal(t.termo)]
    descartados = len(agregados) - len(limpos)
    if not limpos:
        return termos_ausentes(
            f"os {len(agregados)} termos colhidos em {janela.rotulo()} pareciam dado "
            f"pessoal e foram descartados antes do prompt")
    ordenados = sorted(limpos, key=lambda t: (-t.cliques, -t.impressoes, t.termo))
    return TermosDeBusca(
        estado="presente", janela=janela, coletado_em=coletado_em, fonte=fonte,
        termos=tuple(ordenados[:limite]), total_na_fonte=len(agregados),
        descartados_por_dado_pessoal=descartados, limite=limite,
    )
