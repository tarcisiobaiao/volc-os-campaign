# funnel-forge/src/funnelforge/pipeline/retry_policy.py
"""Política de retentativa: separa o que MELHORA se tentar de novo do que só
custa outra chamada para dar o MESMO resultado.

Antes disto o `Runner` tratava tudo igual: qualquer reprovação de validador
virava uma nova chamada paga ao redator, e qualquer exceção do provedor
derrubava o passo sem distinguir um 429 (que passa em 3 segundos) de um 401
(que nunca passa). Os dois extremos custavam caro: no primeiro caso o pipeline
pagava três redações para reprovar pelo mesmo motivo determinístico; no
segundo, desistia de uma página por um soluço de rede.

Duas classificações, nenhuma delas com IA:

1) `classificar_excecao` — erro de TRANSPORTE/CONTRATO com o provedor.
   TRANSITÓRIO (429, 5xx, timeout, conexão) merece nova tentativa com espera.
   TERMINAL (401/403, chave inválida, janela de contexto estourada, schema
   ou parâmetro recusado, modelo inexistente, política de conteúdo) não
   merece: a segunda chamada devolve o mesmo erro e a fatura conta as duas.

2) `classificar_issues` — reprovação de VALIDADOR.
   Recuperável é o defeito de TEXTO: o redator recebe o feedback e pode
   escrever melhor (idioma, tamanho da intro, ponte antes do CTA, ...).
   Terminal é a reprovação que não fala sobre o texto e sim sobre o INSUMO:
   `pagespec` valida `page.routes`, um dado determinístico que o redator não
   escreve — reprovou uma vez, reprova sempre; e `official_link_density` com
   `official_links` vazio é impossível de satisfazer, porque não existe link
   oficial para o texto costurar.

Regra do conjunto: basta UMA issue terminal para selar o resultado. Se o passo
vai reprovar de qualquer jeito, escrever de novo é dinheiro no lixo.

3) (reforma editorial, B5) a classe `patchavel` — só no ramo `editorial_v2`.
   Julgamento SEMÂNTICO por palavra ou regex (lista de medo, de falsa
   oficialidade, de verbo de execução, de expressão jurídica, de idioma...) não
   reprova nem manda reescrever a página inteira: vira LOCALIZADOR entregue ao
   revisor contextual, que decide pelo sentido e, se for o caso, propõe o menor
   ajuste. A régua é a do inventário da Frente A (decisões `converter_em_aviso`
   e `contextualizar`) e da diretriz 8 do operador: erro/bloqueio só para
   dependência técnica comprovada, exigência objetiva da plataforma, segurança
   ou escopo. As regras de decisão `remover` (1ª pessoa na LP, cota de blocos
   visuais) saem do ramo novo. Tudo o que é objetivo continua `estrutural`.
   Sem a flag, nada disto é consultado: o ramo antigo fica byte a byte igual.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class Veredito:
    """Decisão sobre retentar, com o motivo legível que vai para o log.jsonl."""

    retentar: bool
    classe: str   # "transitorio" | "terminal" | "desconhecido" | "recuperavel"
    motivo: str


# --- 1) exceções do provedor -------------------------------------------------

# Casado contra "<NomeDaClasse> <mensagem>" em minúsculas. Sem importar litellm:
# este módulo tem de continuar puro (e testável) sem o SDK instalado.
_TERMINAIS_EXCECAO: tuple[tuple[str, str], ...] = (
    ("authenticationerror", "credencial recusada (401)"),
    ("permissiondenied", "sem permissão para o modelo (403)"),
    ("invalid_api_key", "chave de API inválida"),
    ("incorrect api key", "chave de API inválida"),
    ("contextwindowexceeded", "janela de contexto estourada"),
    ("context length", "janela de contexto estourada"),
    ("maximum context", "janela de contexto estourada"),
    ("too many tokens", "janela de contexto estourada"),
    ("badrequesterror", "requisição recusada pelo provedor (400)"),
    ("invalidrequest", "requisição recusada pelo provedor (400)"),
    ("unprocessable", "requisição recusada pelo provedor (422)"),
    ("unsupportedparams", "parâmetro não suportado pelo modelo"),
    ("response_format", "schema/response_format recusado"),
    ("invalid schema", "schema/response_format recusado"),
    ("notfounderror", "modelo inexistente (404)"),
    ("model not found", "modelo inexistente (404)"),
    ("does not exist", "modelo inexistente (404)"),
    ("contentpolicy", "conteúdo recusado pela política do provedor"),
    ("content_policy", "conteúdo recusado pela política do provedor"),
    ("budgetexceedederror", "teto de gasto do provedor atingido"),
)

_TRANSITORIOS_EXCECAO: tuple[tuple[str, str], ...] = (
    ("ratelimit", "limite de taxa (429)"),
    ("429", "limite de taxa (429)"),
    ("timeout", "estouro de tempo"),
    ("timed out", "estouro de tempo"),
    ("apiconnection", "falha de conexão"),
    ("connection error", "falha de conexão"),
    ("serviceunavailable", "serviço indisponível (503)"),
    ("internalservererror", "erro interno do provedor (5xx)"),
    ("internal server error", "erro interno do provedor (5xx)"),
    ("overloaded", "provedor sobrecarregado"),
    ("temporarily", "indisponibilidade temporária"),
    (" 500", "erro interno do provedor (5xx)"),
    (" 502", "erro interno do provedor (5xx)"),
    (" 503", "erro interno do provedor (5xx)"),
    (" 504", "erro interno do provedor (5xx)"),
)


def classificar_excecao(exc: BaseException) -> Veredito:
    """Decide se vale repetir a chamada que levantou `exc`.

    `AssertionError` é TERMINAL de propósito: ela não vem do provedor, vem de
    um contrato quebrado no nosso lado (ou de um teste com prompt não
    roteirizado). Repetir só multiplica o mesmo defeito.
    """
    if isinstance(exc, AssertionError):
        return Veredito(False, "terminal", "AssertionError: defeito de contrato, não do provedor")
    texto = f"{type(exc).__name__} {exc}".lower()
    for agulha, motivo in _TERMINAIS_EXCECAO:
        if agulha in texto:
            return Veredito(False, "terminal", motivo)
    for agulha, motivo in _TRANSITORIOS_EXCECAO:
        if agulha in texto:
            return Veredito(True, "transitorio", motivo)
    # Desconhecido retenta: o objetivo é não jogar trabalho fora, e o número de
    # tentativas já tem teto (`max_retries`) e freio de orçamento.
    return Veredito(True, "desconhecido", f"erro não classificado: {type(exc).__name__}")


# --- 2) reprovações de validador --------------------------------------------

# Códigos que NÃO falam sobre o texto gerado. Todos vêm de `enforce_pagespec`
# (pagespec.py), que valida `page.routes` — grafo determinístico montado por
# `build_funnel_routes`, que o redator não escreve e o feedback não muda.
#
# `self_loop` e `bare_rec` ficam FORA de propósito: esses dois códigos também
# são emitidos pelos validadores de TEXTO `no_self_loop`/`no_bare_rec` (que
# leem hrefs do corpo), e `run_validators` não diz qual validador produziu a
# issue. Na dúvida, retenta — o erro caro é desistir de página boa.
_CODIGOS_TERMINAIS: frozenset[str] = frozenset({
    "cta_too_few",
    "cta_too_many",
    "target_not_allowed",
    "target_forbidden",
    "target_missing",
    "targets_not_distinct",
    "not_single_destination",
    "anchor_incongruent",
    # gate da pesquisa: é fiação/configuração (nenhum verificador ao vivo
    # ligado), não um texto que possa melhorar.
    "fact_source_verifier_missing",
    # O PORTÃO DO DESTINO PAGO SOBRE O PLANO. `plano_de_destino_pago` ignora o
    # texto gerado por construção: ele lê H1, título, subtítulos e âncoras de
    # CTA, que o redator não escreve. Reprovou uma vez, reprova igual nas três —
    # a alegação do incidente estava no H1 do plano, e nenhuma redação a muda.
    "titulo_sugere_origem_oficial",
    "servico_governamental_restrito",
    "ancora_incongruente_com_destino",
    # E o portão que não pôde ser consultado: reescrever o texto não conserta um
    # import quebrado.
    "portao_de_destino_indisponivel",
})


# --- 3) a régua do ramo editorial novo (B5) ------------------------------------

# Julgamento semântico por palavra/regex -> LOCALIZADOR para o revisor. Entre
# parênteses, a regra do inventário da Frente A (`inventario-regras.json`).
CODIGOS_PATCHAVEIS: frozenset[str] = frozenset({
    "fear_language",             # FF-01 lista de medo/escassez (converter_em_aviso)
    "official_impersonation",    # FF-02 lista de falsa oficialidade (contextualizar)
    "cta_execution",             # FF-03 radical de verbo no botão (contextualizar)
    "cta_destination_mismatch",  # FF-05 regex rótulo × href (contextualizar)
    "no_compliance",             # FF-08 presença de "utilidade pública" (contextualizar)
    "language_pt",               # FF-12 lista de vazamento de idioma (converter_em_aviso)
    "ungrounded_legal_claim",    # FF-18 expressão de força legal (converter_em_aviso)
    "anchor_incongruent",        # FF-26 congruência âncora × H1 por token (contextualizar)
    "cta_incongruent",           # FF-26 idem, no texto do botão (validador opcional)
    "missing_bridge",            # ponte antes do CTA por posição (heurística opcional)
    # D2 — portão de composição (`checks.composicao_editorial`): achados para o
    # revisor. O slot do Ad Inserter (`ad_slot_inseguro`) fica `estrutural`.
    "composicao_paredao_de_texto",
    "composicao_repeticao_visual",
    "bloco_tabela_sem_cabecalho",
    "bloco_details_sem_summary",
    "bloco_pullquote_duplicado",
    "plano_visual_nao_cumprido",
})
# Regras com decisão `remover` no inventário: saem do ramo novo.
CODIGOS_REMOVIDOS_NO_V2: frozenset[str] = frozenset({
    "cta_first_person",          # FF-04 1ª pessoa na LP (nenhuma política; NE-03)
    "missing_semantic_block",    # FF-16 cota de blocos visuais por forma de pergunta
})


def classe_da_issue(issue: Any) -> str:
    """`estrutural` (bloqueia/retenta como hoje), `patchavel` (localizador para o
    revisor) ou `removido` (não vale no ramo novo).

    Dois códigos dependem da MENSAGEM porque o mesmo código cobre um caso
    objetivo e um heurístico:
    - `critical_claim_without_citation`: número sem a fonte citada é objetivo
      (FF-17, fica); afirmação JURÍDICA sem a fonte é o ramo de FF-18.
    - `directional_copy_outside_widget`: dentro da zona das âncoras de anúncio
      é dependência técnica comprovada (FF-15/PUB-11, fica); fora dela é aviso.
    """
    code = getattr(issue, "code", "")
    mensagem = str(getattr(issue, "message", "") or "")
    if code in CODIGOS_REMOVIDOS_NO_V2:
        return "removido"
    if code in CODIGOS_PATCHAVEIS:
        return "patchavel"
    if code == "critical_claim_without_citation" and mensagem.startswith("Afirmação legal"):
        return "patchavel"
    if code == "directional_copy_outside_widget" and "zona de anúncio" not in mensagem:
        return "patchavel"
    return "estrutural"


def separar_para_o_revisor(issues: Iterable[Any]) -> tuple[list[Any], list[Any]]:
    """(bloqueantes, localizadores) no ramo novo; as removidas somem."""
    bloqueantes: list[Any] = []
    localizadores: list[Any] = []
    for issue in issues:
        classe = classe_da_issue(issue)
        if classe == "estrutural":
            bloqueantes.append(issue)
        elif classe == "patchavel":
            localizadores.append(issue)
    return bloqueantes, localizadores


def classificar_issues(issues: Iterable[Any], ctx: dict | None = None) -> Veredito:
    """Decide se vale reescrever o texto depois destas reprovações."""
    ctx = ctx or {}
    lista = list(issues)
    if not lista:
        return Veredito(False, "aprovado", "sem reprovações")
    if ctx.get("editorial_v2"):
        lista, localizadores = separar_para_o_revisor(lista)
        if not lista:
            return Veredito(
                False, "patchavel",
                f"{len(localizadores)} localizador(es) por palavra: vão ao revisor "
                "contextual, sem reescrita integral")
    for issue in lista:
        code = getattr(issue, "code", "")
        if code in _CODIGOS_TERMINAIS:
            return Veredito(
                False, "terminal",
                f"[{code}] não depende do texto gerado; reescrever reprova igual")
        if code == "official_links_few" and not (ctx.get("official_links") or []):
            return Veredito(
                False, "terminal",
                "[official_links_few] a pesquisa não trouxe nenhum link oficial; "
                "nenhum texto satisfaz a densidade mínima")
    return Veredito(True, "recuperavel", "defeito de texto: o feedback pode corrigir")
