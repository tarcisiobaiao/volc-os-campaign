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


def _bloco_de_correcoes(correcoes: list[str] | None) -> str:
    """A reprovação ESTRUTURAL da tentativa anterior (tipo ou escopo fora do
    vocabulário fechado), dita com o valor errado e a lista válida.

    Mesmo princípio de `_bloco_de_fontes_reprovadas`: retentar sem dizer o que
    falhou é repetir a mesma resposta pagando de novo."""
    if not correcoes:
        return ""
    lista = "\n".join(f"  - {c}" for c in correcoes[:10])
    return (
        "\n\nATENCAO -- TENTATIVA ANTERIOR RECUSADA pelo contrato de tipagem:\n"
        f"{lista}\n"
        "Devolva o JSON inteiro de novo, corrigindo exatamente isso. Nao mude o que "
        "estava certo.\n"
    )


# O vocabulário fechado dos tipos, com a semântica que o contrato entre as
# trilhas fixou. Mesma ordem de `domain.models.TIPOS_DE_FATO` (o teste confere).
_VOCABULARIO_DE_TIPOS = (
    ("numero", "quantidade, valor, percentual ou limite numerico"),
    ("prazo", "duracao ou data-limite para agir (ex.: dias para responder)"),
    ("data", "data de um evento, de inicio ou de fim"),
    ("mudanca", "algo que mudou ou vai mudar na regra"),
    ("condicao", "requisito ou criterio que decide quem pode (ex.: limite de renda)"),
    ("orgao", "instituicao responsavel, quem faz o que"),
    ("fonte_legal", "a propria lei, decreto, portaria ou artigo como referencia"),
    ("processo", "etapa ou canal de um procedimento"),
    ("contexto", "fato descritivo que situa o tema; nunca sustenta numero, prazo ou condicao"),
)


def _bloco_de_tipagem() -> str:
    linhas = "\n".join(f"- {tipo}: {sentido}" for tipo, sentido in _VOCABULARIO_DE_TIPOS)
    return (
        "TIPO DE CADA FATO (obrigatorio em dados_validados e em fatos_verificados; "
        "vocabulario FECHADO, nenhum outro valor e aceito):\n"
        f"{linhas}\n"
        "Escolha o tipo pelo que o fato AFIRMA, nao pelo campo em que ele esta.\n"
        'ESCOPO (quando souber): "nacional", "regional:UF" (ex.: "regional:SP") ou '
        '"unidade" (vale so para uma unidade, escola ou agencia). Se nao souber, omita.\n'
        "CITAVEL (quando souber): false se a fonte e contraditoria ou instavel sobre o "
        "fato (ex.: a mesma pagina traz dois numeros diferentes); true se o fato pode "
        "ser citado como esta. Se nao souber, omita.\n\n"
    )


def _research_prompt(topic: str, structure: str,
                     reprovadas: list[str] | None = None,
                     correcoes: list[str] | None = None) -> str:
    today = date.today().strftime("%d/%m/%Y")
    return (
        # VIGÊNCIA × DATA HISTÓRICA. O texto antigo mandava "use SEMPRE o ano
        # corrente", e isso empurrava ANO para dentro do conteúdo: um decreto de
        # 2008 em vigor é fato VIGENTE com data histórica, não "ano passado".
        f"Hoje e {today}. VIGENCIA E DATA HISTORICA SAO COISAS DIFERENTES:\n"
        "- vigencia = a regra, o valor ou o prazo vale HOJE? So entra como atual o que "
        "esta em vigor nesta data; regra revogada, valor antigo ou edital encerrado "
        "nunca entra como se fosse atual.\n"
        "- data historica = quando a regra nasceu ou o fato aconteceu (ex.: uma lei "
        "antiga que continua em vigor). Ela vai em vigente_desde, com o ano verdadeiro; "
        "nao a troque pelo ano de hoje e nao acrescente ano onde a fonte nao poe.\n"
        "Se nao conseguir confirmar que um valor ainda vale hoje, nao o ponha em "
        "fatos_verificados.\n\n"
        "Pesquise e retorne SOMENTE um objeto JSON (UTF-8, sem markdown) com fatos "
        "verificaveis e vigentes sobre o tema abaixo, no schema exato:\n"
        '{"resumo": "...", "dados_validados": [{"fato": "...", "fonte": "...", '
        '"tipo": "...", "escopo": "...", "citavel": true}], '
        '"fatos_verificados": [{"valor": "...", "unidade": "...", '
        '"fonte_primaria": "https://...", "dispositivo": "... ou nao se aplica", '
        '"vigente_desde": "AAAA-MM-DD", "verificado_em": "AAAA-MM-DD", '
        '"tipo": "...", "escopo": "...", "citavel": true}], '
        '"passo_a_passo": ["..."], "fontes": ["https://..."]}\n\n'
        + _bloco_de_tipagem() +
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
        + _bloco_de_correcoes(correcoes)
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
                 fontes_reprovadas: list[str] | None = None,
                 correcoes: list[str] | None = None) -> ResearchFacts:
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
                     "content": _research_prompt(topic, structure, fontes_reprovadas,
                                                 correcoes)}]
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


# ---------------------------------------------------------------------------
# PESQUISA ÚNICA DO FUNIL (dossiê factual pré-redação)
# ---------------------------------------------------------------------------

EVIDENCIA_RESUMIDA = (
    "evidencia_resumida: síntese curta, factual e escrita com palavras próprias. Não "
    "reproduza trechos literais extensos. A proveniência será comprovada pelo "
    "groundingMetadata e pela URL verificada.")


def _prompt_do_funil(assunto: str, paginas: list[dict], faltantes: list[dict] | None,
                     *, estruturado: bool = False) -> str:
    """Um prompt para o funil INTEIRO (ou, na complementação, só para o que
    falta). Cada fato diz a quais páginas e a quais requisitos ele serve.

    Não pede trecho literal da fonte: o canário de 07/10/2026 voltou vazio 3/3
    pedindo "trecho copiado, nada de paráfrase". A prova de origem é o
    groundingMetadata + a URL verificada, nunca o texto do modelo.
    `estruturado`: o formato vem do schema nativo (Structured Output), não do
    texto do prompt."""
    hoje = date.today().strftime("%d/%m/%Y")
    mapa = json.dumps(paginas, ensure_ascii=False, indent=1)
    alvo = ""
    if faltantes:
        lista = "\n".join(f"- pagina {f['duvida_id']}: requisito {f['requisito']} "
                          f"({f['descricao']}; tipos aceitos: {', '.join(f['tipos'])})"
                          for f in faltantes)
        alvo = ("\n\nCOMPLEMENTACAO DIRIGIDA: a rodada anterior nao trouxe lastro para os "
                f"requisitos abaixo. Pesquise SOMENTE eles:\n{lista}\n")
    tipos = ", ".join(t for t, _ in _VOCABULARIO_DE_TIPOS)
    if estruturado:
        formato = ("redacao. Pesquise na web com a busca do Google; a resposta segue o schema "
                   "JSON fornecido (lista `fatos`).\n\n")
    else:
        formato = (
            "redacao. Pesquise na web e devolva SOMENTE um objeto JSON (sem markdown):\n"
            '{"fatos": [{"afirmacao": "...", "tipo": "...", "valor": "...", "unidade": "...", '
            '"fonte": "https://pagina-que-a-busca-abriu", "vigente_desde": "AAAA-MM-DD", '
            '"dispositivo": "...", "evidencia_resumida": "...", '
            '"paginas": ["duvida_id"], "requisitos": ["id_do_requisito"]}]}\n\n')
    return (
        f"Hoje e {hoje}. Voce prepara o DOSSIE FACTUAL de um funil editorial antes de qualquer "
        + formato +
        f"Assunto do funil: {assunto}\n"
        f"Paginas, perguntas, promessas e requisitos que cada uma precisa provar:\n{mapa}\n\n"
        f"tipo (vocabulario fechado): {tipos}.\n"
        "REGRAS:\n"
        "- fonte = URL de uma pagina que a sua busca realmente abriu. URL de memoria nao vale.\n"
        "- numero, prazo, data e mudanca exigem valor, unidade e vigente_desde (a vigencia que "
        "a fonte declara). Sem isso, nao inclua o fato.\n"
        "- formula, regra ou metodo de calculo e tipo processo, mesmo quando a fonte traz um "
        "exemplo numerico; numero fica para valor, limite ou percentual que muda no tempo.\n"
        "- regra, elegibilidade e obrigacao exigem fonte oficial ou primaria.\n"
        f"- {EVIDENCIA_RESUMIDA}\n"
        "- paginas: os duvida_id que o fato sustenta; requisitos: os ids que ele cobre.\n"
        "- nao transforme inferencia em fato; nao complete lacuna por plausibilidade. Se nao "
        "achar, nao invente: deixe o requisito sem fato.\n"
        "- se fontes divergirem, traga as duas versoes como fatos separados."
        + alvo
    )


def pesquisar_funil(llm: LLMClient, cfg: StepConfig, assunto: str, paginas: list[dict],
                    faltantes: list[dict] | None = None, *, ler=None):
    """A pesquisa do dossiê. Gemini com busca vai pelo SDK nativo (Search +
    Structured Output + telemetria completa); o resto, pelo LiteLLM. A escolha
    é pelo modelo configurado — nunca um cai para o outro.

    `ler` é a leitura das páginas citadas (o bucket do run, quando existe):
    a mesma fonte não é baixada de novo em outra rodada."""
    if cfg.model.startswith("chatgpt/") and getattr(cfg, "web_search", False):
        # `chatgpt_plan_web_search`: provider dedicado do dossiê. O cliente
        # genérico do plano continua recusando web_search.
        from funnelforge.adapters.pesquisa_plano import pesquisar_dossie_plano
        return pesquisar_dossie_plano(llm, cfg, assunto, paginas, faltantes, ler=ler)
    if cfg.model.startswith("gemini/") and getattr(cfg, "web_search", False):
        from funnelforge.adapters.pesquisa_gemini import pesquisar_dossie_nativo
        return pesquisar_dossie_nativo(cfg, assunto, paginas, faltantes)
    return pesquisar_funil_litellm(llm, cfg, assunto, paginas, faltantes)


def pesquisar_funil_litellm(llm: LLMClient, cfg: StepConfig, assunto: str, paginas: list[dict],
                            faltantes: list[dict] | None = None):
    """Uma rodada de pesquisa do funil com grounding. As citações do PROVEDOR
    (canonizadas, redirects resolvidos) são a lista de fontes candidatas; o
    texto do modelo nunca acrescenta URL a ela."""
    from funnelforge.pipeline.dossie import RespostaDaPesquisa
    mensagem = [{"role": "user", "content": _prompt_do_funil(assunto, paginas, faltantes)}]
    resultado = llm.complete(cfg.model, cfg.fallbacks, mensagem, cfg.temperature,
                             web_search=getattr(cfg, "web_search", False))
    with httpx.Client(timeout=12.0, follow_redirects=True, headers={"User-Agent": _UA}) as c:
        citacoes = list(dict.fromkeys(_canonica(u, c) for u in (resultado.citations or [])))
    # Resposta vazia ou ilegível NÃO é "zero fatos": é defeito da chamada, e
    # complementar às cegas só paga de novo pelo mesmo vazio.
    fim = getattr(resultado, "finish_reason", "") or "não informado"
    defeito = ""
    if not (resultado.text or "").strip():
        defeito = f"provedor devolveu texto vazio (finish_reason={fim})"
        dados = {"fatos": []}
    else:
        try:
            dados = _tolerant_json(resultado.text)
        except (ValueError, json.JSONDecodeError):
            dados = {"fatos": []}
            defeito = f"resposta sem JSON legível (finish_reason={fim})"
    return RespostaDaPesquisa(
        dados=dados, citacoes=citacoes, modelo_pedido=cfg.model,
        modelo_servido=resultado.model_used, auth_mode=getattr(resultado, "auth_mode", "") or "",
        prompt_tokens=resultado.prompt_tokens, completion_tokens=resultado.completion_tokens,
        custo_usd=resultado.cost_usd, latencia_ms=resultado.latency_ms,
        consultas_de_busca=getattr(resultado, "consultas_de_busca", 0) or 0,
        finish_reason=getattr(resultado, "finish_reason", "") or "", defeito=defeito)
