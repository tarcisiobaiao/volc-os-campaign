"""Limites de API conhecidos, com fonte e estado de confirmação, e consumo por cenário.

Regra: número sem fonte no repositório NÃO entra como fato. `estado` diz o grau de confiança:
- "documentado no repo com fonte oficial citada" — está no repositório citando a documentação
  oficial; não foi re-verificado nesta missão (sem rede);
- "observado no repo" — parâmetro de código/config, não limite do fornecedor;
- "não confirmado" — sem fonte; valor None.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .volume import ResultadoJob

J = "wip/historico-joinads-20261015"
MS = "wip/historico-measurement-20261015"


@dataclass(frozen=True)
class Limite:
    fonte: str
    nome: str
    valor: float | None
    unidade: str
    estado: str
    evidencia: str


LIMITES: tuple[Limite, ...] = (
    Limite("google_ads", "operacoes_dia_token_basic", 15_000, "operações/dia por developer token",
           "documentado no repo com fonte oficial citada", f"{J}:docs/growth-engine/matriz-api/comum.md:174"),
    Limite("google_ads", "operacoes_dia_token_explorer_producao", 2_880, "operações/dia por developer token",
           "documentado no repo com fonte oficial citada", f"{J}:docs/growth-engine/matriz-api/comum.md:173"),
    Limite("google_ads", "operacoes_dia_token_standard", None, "operações/dia",
           "não confirmado", f"{J}:docs/growth-engine/matriz-api/comum.md:175 ([NÃO CONFIRMADO])"),
    Limite("google_ads", "nivel_de_acesso_do_token_volc", None, "Explorer|Basic|Standard",
           "não confirmado", "não encontrado no repo"),
    Limite("google_ads", "operacoes_por_search_ou_searchstream", 1, "operação por requisição (páginas com token válido não contam)",
           "documentado no repo com fonte oficial citada", f"{J}:docs/growth-engine/matriz-api/comum.md:179-181"),
    Limite("google_ads", "resposta_grpc_max", 64, "MB por resposta",
           "documentado no repo com fonte oficial citada", f"{J}:docs/growth-engine/matriz-api/comum.md:189"),
    Limite("google_ads", "page_size", None, "linhas por página (campo removido da API; canônicos usam searchStream)",
           "observado no repo", f"{J}:backend/app/trafego/sincronizador.py:594-599; {J}:P/collector-inventory.json:118"),
    Limite("google_ads", "qps", None, "token bucket por CID e por developer token; QPS não publicado",
           "documentado no repo com fonte oficial citada", f"{J}:docs/growth-engine/matriz-api/comum.md:197-198"),
    Limite("joinads", "rate_limit", None, "requisições/unidade de tempo", "não confirmado", "não encontrado no repo"),
    Limite("joinads", "paginacao_top_url_country", 250, "linhas por chamada (parâmetro do coletor)", "observado no repo",
           f"{J}:n8n/gerar_flows_joinads_v2.py:234,237"),
    Limite("gtm", "lote_navegador_eventos", 20, "eventos por envio", "observado no repo",
           f"{MS}:measurement/gtm/volc-sensor-v3.html:32"),
    Limite("gtm", "lote_navegador_ms", 10_000, "ms entre envios", "observado no repo",
           f"{MS}:measurement/gtm/volc-sensor-v3.html:31"),
    Limite("gtm", "corpo_max_servidor", 64 * 1024, "bytes por requisição", "observado no repo",
           f"{MS}:supabase/functions/volc-ingest/index.ts:6-7"),
)


def limite(nome: str) -> Limite:
    for x in LIMITES:
        if x.nome == nome:
            return x
    raise KeyError(nome)


def chamadas_por_fonte(jobs: list[ResultadoJob]) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in jobs:
        out[r.fonte] = out.get(r.fonte, 0.0) + r.chamadas_dia
    return out


def avaliar_google_ads(jobs: list[ResultadoJob]) -> dict:
    """Operações/dia (searchStream = 1 operação) contra os níveis de token documentados.

    Conta só as consultas de relatório; OAuth refresh não consome quota de operações. Retries que
    chegam ao serviço (GoogleAdsFailure) contam — o modelo não os inclui (piso).
    """
    ops = chamadas_por_fonte(jobs).get("google_ads", 0.0)
    out = {"operacoes_dia": ops, "nota": "piso: sem retries, sem consultas ad hoc nem MCP/scripts paralelos"}
    for nome in ("operacoes_dia_token_basic", "operacoes_dia_token_explorer_producao"):
        lim = limite(nome)
        out[nome] = {"limite": lim.valor, "uso": ops / lim.valor, "cabe": ops <= lim.valor, "estado": lim.estado}
    return out


def tabela_limites() -> list[dict]:
    return [asdict(x) for x in LIMITES]
