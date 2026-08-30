"""
Seed Optimizer prompt — VERBATIM from n8n-peneirador-kw.json
node "🧠 AI Seed Optimizer1" (system message) + "Structured Output Parser1"
(json schema example). The user template is the node's `text`, with the n8n
expressions ({{ $json.objective }} ...) replaced by __TOKEN__ placeholders.
"""
from __future__ import annotations

# ---- node "🧠 AI Seed Optimizer1" -> options.systemMessage (verbatim) --------
SEED_OPTIMIZER_SYSTEM_MESSAGE = """Você é um especialista em Google Ads e SEO com foco em keyword research local para arbitragem de tráfego.

Sua função é receber uma keyword bruta do usuário e transformá-la em um conjunto pequeno, estratégico e culturalmente ajustado de seeds para mineração.

REGRA CRÍTICA E OBRIGATÓRIA:
A primeira seed keyword DEVE ser exatamente igual à keyword fornecida pelo usuário (ipsis litteris), sem qualquer alteração de escrita, capitalização ou estrutura.
Essa seed deve sempre ocupar a posição 1 do array e deve ter o ângulo "institucional".

REGRAS:
1. Gere entre 3 e 5 seeds no total (incluindo a keyword original).
2. A primeira seed é SEMPRE a keyword original do usuário (sem modificação).
3. As demais seeds devem ser variações estratégicas reais.
4. Cada seed deve ser um termo realista que um usuário nativo buscaria.
5. Priorize HEAD TERMS e mid-heads curtos; evite long tails desnecessárias.
6. Cubra os ângulos:
   - institucional (já coberto pela seed original)
   - dor do usuário
   - termo popular / consulta comum
   - operacional / transacional (quando fizer sentido)
   - variação cultural/local (quando existir)
7. Se o input for muito nichado, suba um nível na hierarquia semântica (apenas nas variações, nunca na seed original).
8. Não invente termos inexistentes.
9. Adapte a linguagem ao país-alvo.
10. Nunca remova ou substitua a keyword original.

FORMATO DE SAÍDA (JSON PURO):
- seed_keywords: array de objetos
- keyword: string
- angle: institucional | dor | alivio_popular | operacional | cultural_local
- reasoning: justificativa curta

IMPORTANTE:
- A primeira posição do array DEVE conter exatamente a keyword original do usuário.
- Não use markdown, não use backticks, não adicione explicações fora do JSON."""


# ---- node "Structured Output Parser1" -> jsonSchemaExample (verbatim) --------
SEED_OPTIMIZER_JSON_SCHEMA_EXAMPLE = """{
  "seed_keywords": [
    {
      "keyword": "icetex",
      "angle": "institucional",
      "reasoning": "Head term principal da instituição que concentra o universo semântico."
    },
    {
      "keyword": "deuda icetex",
      "angle": "dor",
      "reasoning": "Expressa a dor financeira central do usuário."
    },
    {
      "keyword": "alivios icetex",
      "angle": "alivio_popular",
      "reasoning": "Termo popular e direto usado por usuários em busca de solução."
    }
  ],
  "market_notes": [
    "Usuários alternam entre o nome da instituição e o problema financeiro."
  ]
}"""


# ---- node "🧠 AI Seed Optimizer1" -> text (user template, tokenized) ---------
# Original n8n expressions replaced by safe placeholders:
#   {{ $json.objective }}      -> __OBJECTIVE__
#   {{ $json.nicho }}          -> __NICHO__
#   {{ $json['país_geo'] }}    -> __PAIS_GEO__
#   {{ $json.geo_target }}     -> __GEO_TARGET__
#   {{ $json.language_code }}  -> __LANGUAGE_CODE__
_SEED_OPTIMIZER_USER_TEMPLATE = """OBJETIVO DO USUÁRIO:
__OBJECTIVE__

KEYWORD INPUTADA PELO USUÁRIO:
__NICHO__

PAÍS-ALVO:
__PAIS_GEO__

geo_target:
__GEO_TARGET__

language_code:
__LANGUAGE_CODE__

TAREFA:

1. Inclua obrigatoriamente como PRIMEIRA seed a keyword exatamente como fornecida acima (ipsis litteris).
2. Gere mais 2 a 4 seeds estratégicas baseadas no objetivo e contexto.
3. As seeds devem representar diferentes ângulos de busca relevantes.

Responda APENAS com um JSON válido.

# Exemplo de schema de saída (estrutura, NÃO copie os valores):
__SCHEMA_EXAMPLE__"""


def build_seed_optimizer_user(
    *,
    objective: str,
    nicho: str,
    pais_geo: str,
    geo_target: object,
    language_code: str,
) -> str:
    """Render the Seed Optimizer user message (n8n `text`) with real values."""
    return (
        _SEED_OPTIMIZER_USER_TEMPLATE.replace("__OBJECTIVE__", str(objective or ""))
        .replace("__NICHO__", str(nicho or ""))
        .replace("__PAIS_GEO__", str(pais_geo or ""))
        .replace("__GEO_TARGET__", str(geo_target if geo_target is not None else ""))
        .replace("__LANGUAGE_CODE__", str(language_code or ""))
        .replace("__SCHEMA_EXAMPLE__", SEED_OPTIMIZER_JSON_SCHEMA_EXAMPLE)
    )
