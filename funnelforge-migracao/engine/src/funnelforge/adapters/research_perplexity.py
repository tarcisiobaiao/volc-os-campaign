from __future__ import annotations

import json
import re
from datetime import date

import httpx

from funnelforge.config.settings import StepConfig
from funnelforge.domain.models import ResearchFacts
from funnelforge.ports.llm import LLMClient

# UA de navegador: seguir o redirecionamento do grounding com UA de robô faz
# vários sites responderem 403 e a citação canônica se perder.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n?|```\s*$")


def _tolerant_json(text: str) -> dict:
    """Same tolerant-JSON parsing strategy used by pipeline.steps: strips
    ```json fences, then slices from the first `{` to the last `}`."""
    stripped = _FENCE_RE.sub("", text.strip()).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in LLM output")
    return json.loads(stripped[start : end + 1])


def _bloco_de_fontes_reprovadas(reprovadas: list[str] | None) -> str:
    """O feedback da tentativa anterior — o que separa retentar de repetir.

    Sem isto, cada nova tentativa refazia a MESMA busca com o MESMO prompt e
    tinha grande chance de devolver as MESMAS URLs. Medido no primeiro run
    real: 3 tentativas, US$ 0,3945, e as três fontes primárias eram as mesmas
    duas alucinações (404 de verdade) mais um site que bloqueia robô.

    A instrução é dura de propósito: o modelo tende a produzir caminhos
    plausíveis (`/consignacao/margem-consignavel-regras-e-limites-a-partir-de-2026`)
    que nunca existiram. Dizer QUAIS falharam e por quê é a única informação
    nova que a segunda tentativa tem.
    """
    if not reprovadas:
        return ""
    lista = "\n".join(f"  - {u}" for u in reprovadas[:8])
    return (
        "\n\nATENCAO -- TENTATIVA ANTERIOR REPROVADA. Estas URLs que voce "
        "devolveu como fonte primaria NAO EXISTEM ou nao respondem:\n"
        f"{lista}\n"
        "NAO as repita. Elas foram verificadas por visita real e falharam.\n"
        "Traga fontes que uma visita HTTP consiga abrir: prefira a PAGINA RAIZ "
        "de um canal oficial a um caminho profundo que voce nao tem certeza que "
        "existe. Se nao houver fonte que voce possa garantir, devolva "
        '"fatos_verificados": [] -- texto sem numero e melhor que numero com '
        "fonte inventada.\n"
    )


def _research_prompt(topic: str, structure: str,
                     reprovadas: list[str] | None = None) -> str:
    today = date.today().strftime("%d/%m/%Y")
    return (
        f"CRITICO: hoje e {today} (ano corrente {date.today().year}). Pesquise dados "
        "VIGENTES nesta data e use SEMPRE o ano corrente; nunca cite anos passados "
        "(ex.: 2024, 2025) como se fossem os valores/regras atuais.\n\n"
        "Pesquise e retorne SOMENTE um objeto JSON (UTF-8, sem markdown) com fatos "
        "verificaveis e atualizados sobre o tema abaixo, no schema exato:\n"
        '{"resumo": "...", "dados_validados": [{"fato": "...", "fonte": "..."}], '
        '"fatos_verificados": [{"valor": "...", "unidade": "...", '
        '"fonte_primaria": "https://...", "dispositivo": "... ou nao se aplica", '
        '"vigente_desde": "AAAA-MM-DD", "verificado_em": "AAAA-MM-DD"}], '
        '"passo_a_passo": ["..."], "fontes": ["https://..."]}\n\n'
        f"Tema: {topic}\n"
        f"Estrutura do conteudo que sera escrito: {structure}\n\n"
        "Todo numero, percentual, prazo, limite ou dispositivo legal IMPORTANTE deve "
        "estar em fatos_verificados com fonte_primaria, unidade, vigencia e data de "
        "verificacao. Copie essa mesma URL para fontes. Nao transforme resumo de busca "
        "em fonte primaria e nao complete lacunas por plausibilidade. "
        'Se nao encontrar nenhuma fonte confiavel, retorne '
        '"fontes": [].\n'
        "URL EXATA (nunca o portal generico): quando um passo acontece numa pagina "
        "oficial de servico/consulta, retorne em 'fontes' a URL EXATA DAQUELA PAGINA "
        "DE SERVICO (ex.: a pagina de consulta de situacao cadastral do CPF, "
        "https://servicos.receita.fazenda.gov.br/servicos/cpf/consultasituacao/"
        "consultapublica.asp), NUNCA o host/portal generico do orgao (ex.: nao o "
        "gov.br/receitafederal). O mesmo vale para consultas de saldo/beneficio: a "
        "pagina exata do servico, verificada como acessivel.\n"
        "PLATAFORMAS/SERVICOS: para cada plataforma, app, fintech ou instituicao "
        "citada no passo a passo ou nas tabelas, inclua a URL EXATA do site oficial "
        "dela em 'fontes' e associe o nome dela a essa URL em dados_validados[].fonte."
        + _bloco_de_fontes_reprovadas(reprovadas)
    )


def _canonica(uri: str, cliente: httpx.Client | None = None) -> str:
    """Segue o redirecionamento do grounding e devolve o endereço final.

    O Gemini entrega as citações como `vertexaisearch.cloud.google.com/
    grounding-api-redirect/<hash>` — reais e verificáveis, mas ilegíveis dentro
    de um artigo. O leitor precisa ver `www.gov.br/...`, e o gate de mesmo
    domínio precisa do host de verdade para decidir o que é link externo.

    Falha de rede devolve a URI original: melhor uma citação feia que existe do
    que nenhuma.
    """
    if "grounding-api-redirect" not in uri:
        return uri
    fechar = cliente is None
    c = cliente or httpx.Client(timeout=12.0, follow_redirects=True,
                                headers={"User-Agent": _UA})
    try:
        r = c.get(uri)
        final = str(r.url)
        return final if final.startswith("http") else uri
    except Exception:  # noqa: BLE001 - citação feia é melhor que citação nenhuma
        return uri
    finally:
        if fechar:
            c.close()


def _com_citacoes_reais(facts: ResearchFacts, citacoes: list[str]) -> ResearchFacts:
    """As citações do PROVEDOR passam a ser a lista autoritativa de fontes.

    ## Por que substituir, e não somar

    `research_facts_contract` exige que a `fonte_primaria` de cada fato tipado
    esteja em `fontes`. Enquanto `fontes` fosse a lista que o MODELO digitou,
    uma URL inventada satisfazia o contrato (ele mesmo a pôs nos dois lugares) e
    só morria depois, na visita ao vivo — 236 segundos e US$ 0,39 mais tarde,
    medido no primeiro run real.

    Com as citações reais no lugar, uma `fonte_primaria` fabricada falha em
    `fact_source_not_listed` de imediato, sem tocar a rede. O gate fica mais
    barato E mais preciso ao mesmo tempo.

    ## Quando NÃO substituir

    Nem toda resposta aciona a busca. Sem citação nenhuma, manter o
    comportamento antigo (a lista do modelo, verificada ao vivo) é melhor que
    zerar as fontes e reprovar tudo — seria trocar alucinação por apagão.
    """
    if not citacoes:
        return facts
    with httpx.Client(timeout=12.0, follow_redirects=True,
                      headers={"User-Agent": _UA}) as c:
        reais = []
        for u in citacoes:
            canon = _canonica(u, c)
            if canon not in reais:
                reais.append(canon)
    dados = facts.model_dump()
    dados["fontes"] = reais
    return ResearchFacts(**dados)


class PerplexityResearch:
    """`ResearchProvider` backed by an LLM step configured for web-grounded
    research (typically a Perplexity `sonar-*` model, via `step_cfg`).

    The adapter still returns a sparse object instead of raising on provider
    failure so telemetry/state can be persisted.  The pipeline now validates
    that object through the same fail-closed research contract used by the
    fallback path; sparse research therefore cannot reach the writer.
    """

    def __init__(self, llm: LLMClient, step_cfg: StepConfig | None):
        self._llm = llm
        self._cfg = step_cfg
        # Telemetry (FIX 5, smoke): research goes through this adapter, not
        # `Runner.run_llm_step`, so its cost/tokens used to show as 0 in
        # report.md. Record the LAST call's telemetry here so
        # `pipeline.steps.step_research` can copy it into the
        # `research_p{n}` StepResult it stores.
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.last_cost_usd = 0.0
        self.last_latency_ms = 0

    def research(self, topic: str, structure: str,
                 fontes_reprovadas: list[str] | None = None) -> ResearchFacts:
        # Zera a telemetria ANTES de tentar. `last_*` é estado de instância e o
        # mesmo adapter atende todas as páginas: quando uma chamada morria, os
        # números da página ANTERIOR ficavam pendurados e `step_research` os
        # copiava como se fossem desta -- o ledger cobrava duas vezes por uma
        # pesquisa que só aconteceu uma. Com retentativa isso ficaria pior.
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.last_cost_usd = 0.0
        self.last_latency_ms = 0
        if self._cfg is None:
            return ResearchFacts(sparse=True)
        messages = [{"role": "user",
                     "content": _research_prompt(topic, structure, fontes_reprovadas)}]
        try:
            result = self._llm.complete(
                self._cfg.model, self._cfg.fallbacks, messages, self._cfg.temperature,
                web_search=getattr(self._cfg, "web_search", False),
            )
            self.last_prompt_tokens = result.prompt_tokens
            self.last_completion_tokens = result.completion_tokens
            self.last_cost_usd = result.cost_usd
            self.last_latency_ms = result.latency_ms
            raw = _tolerant_json(result.text)
            facts = ResearchFacts(**raw)
            facts = _com_citacoes_reais(facts, result.citations)
        except Exception:  # noqa: BLE001 - pipeline turns sparse into a hard gate
            return ResearchFacts(sparse=True)
        if not facts.fontes:
            facts.sparse = True
        return facts
