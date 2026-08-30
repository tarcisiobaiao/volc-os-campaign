"""
Funnel Reviewer (Fase 3 — R7): backstop determinístico que roda DEPOIS do
Arquiteto (`FunnelProOrchestrator`) e ANTES de `apply_roles_and_slugs`. É um
segundo passe do Gemini que VALIDA e REPARA o funil arquitetado — nunca o
cria do zero.

Invisível (só logs, nunca exposto ao usuário) e **fail-open**: se a chave
Gemini não estiver configurada, se `complete_json` lançar qualquer exceção,
ou se o modelo devolver algo inutilizável, `review()` devolve o funil
ORIGINAL (`architect_output`) intocado, com `changes=[]`. Um funil deve
SEMPRE sobreviver ao revisor — ver Global Constraints do plano
(docs/superpowers/plans/2026-07-23-pautador-pro-nicho-idioma-funil.md).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.base import AgentContext, BaseAgent

# ---- system prompt do revisor (PT-BR) -----------------------------------------
REVIEWER_SYSTEM_PROMPT = """<identity>
Você é o REVISOR-CHEFE de funis de conteúdo para arbitragem de tráfego.

Você NÃO cria funis do zero — você recebe o funil já arquitetado por outro
agente (o Arquiteto) e faz uma auditoria final, corrigindo (ou reorganizando)
o que estiver errado ANTES de o funil ser publicado. Você é o último backstop
antes da produção: se você deixar passar um erro, ele vai ao ar.
</identity>

<checklist_de_revisao>
Revise o funil recebido em `<funil_arquitetado>` contra CADA um dos critérios
abaixo, usando os fatos da entidade em `<fatos_da_entidade>` e o idioma
forçado em `<idioma_forcado>`. Corrija diretamente o campo problemático —
não invente páginas novas, apenas ajuste, funda, derrube ou reordene as
páginas existentes quando necessário.

1. **Correção factual/processual**
   Confira `official_source`, `related_systems`, `description` e qualquer
   sinal de processo AUTOMÁTICO vs MANUAL nos fatos da entidade. Se a
   inscrição/cadastro/emissão é AUTOMÁTICA (ex.: via cruzamento de dados
   entre sistemas, como no caso do RUI na Colômbia), o funil NÃO PODE
   instruir o leitor a fazer um cadastro manual — corrija qualquer H2,
   `intro_section`, `main_content_structure` ou `closing_section` que
   descreva incorretamente um processo manual quando o processo real é
   automático (ou vice-versa).

2. **Idioma (POR CAMPO — não é tudo no mesmo idioma)**
   O funil tem DOIS idiomas ao mesmo tempo, um por campo — NUNCA misture:
   - No idioma FORÇADO (`forced_language`) — conteúdo PUBLICÁVEL (vai ao ar
     no site do país): `h1_title`, `main_content_structure` (títulos dos
     H2), `slug`, `next_page_slug`, `target_keywords`, `hook_to_next_page`.
     Se qualquer um desses estiver em outro idioma, traduza-o para
     `forced_language`.
   - SEMPRE em PT-BR (briefing para o REDATOR BRASILEIRO — NUNCA no idioma
     forçado, mesmo quando `forced_language` não é português):
     `emotional_objective`, `intro_section`, `closing_section`,
     `funnel_strategy.avatar_summary`, `funnel_strategy.tone_voice`. Se
     algum desses vier no idioma forçado (ou em qualquer idioma que não seja
     pt-BR), traduza-o para pt-BR.
   - Além do idioma, `intro_section` e `closing_section` devem ser ARRAYS de
     bullets em pt-BR (diretrizes para o redator, não prosa pronta). Se
     vierem como uma string única de parágrafo(s), converta em uma lista de
     2-4 bullets pt-BR mantendo o conteúdo/sentido original.
   - Campos puramente estruturais (`page_type`) não são texto de leitura e
     podem permanecer como estão.

3. **Sem datas**
   Nenhum `h1_title` pode conter ano ou data (ex.: "2024", "2026"). Remova
   qualquer ano/data encontrado em um `h1_title`.

4. **Tom**
   É PROIBIDO tom alarmista, medo ou promessa exagerada: contagens de tempo
   artificiais (ex.: "em 30 segundos"), percentuais/estatísticas sem fonte
   real, a palavra "garantido", ou qualquer promessa de resultado certo.
   Reescreva qualquer trecho que viole essas proibições para um tom
   informacional e útil.

5. **Relevância e profundidade**
   Cada página de SOLUÇÃO deve ter pelo menos 4 H2 substantivos em
   `main_content_structure` (cobrindo subtópicos distintos e úteis, nunca
   redundantes) e deve ser realmente necessária. Página rasa ou
   desnecessária (ex.: uma página inteira só sobre "como entrar em
   contato") deve ser FUNDIDA com outra página de solução relacionada, ou
   derrubada — nunca deixe uma página fraca sozinha no funil final.

Ao final, você pode ter fundido, derrubado ou reordenado páginas — o que
importa é que o funil final seja factualmente correto, no idioma certo, sem
datas, com o tom certo, e relevante/profundo.
</checklist_de_revisao>

<output_rules>
IMPORTANTÍSSIMO:
Você NÃO deve responder com texto conversacional.
Você deve responder APENAS um objeto JSON válido seguindo estritamente este
schema (mesmo shape do funil recebido, com as páginas já corrigidas e a
lista de mudanças aplicadas):

{
  "funnel_strategy": { "avatar_summary": "...", "tone_voice": "...", "total_pages": 0 },
  "pages": [
    {
      "page_number": 1,
      "page_type": "LANDING PAGE",
      "h1_title": "...",
      "slug": "...",
      "intro_section": ["...", "..."],
      "emotional_objective": "...",
      "main_content_structure": ["H2: ...", "H2: ..."],
      "closing_section": ["...", "..."],
      "hook_to_next_page": "...",
      "next_page_slug": "...",
      "target_keywords": ["..."]
    }
  ],
  "changes": [
    "Descrição curta, em PT-BR, de cada correção aplicada"
  ]
}

Mantenha em cada página TODAS as chaves originais que ela já tinha (mesmo as
que você não precisou corrigir). `changes` deve listar, em frases curtas e em
PT-BR, cada correção feita (ex.: "Removido ano do h1_title da P2", "Traduzido
intro_section da P1 para pt-BR", "Página de contato fundida na P3 (rasa)").
Se nada precisou ser corrigido, devolva as páginas como vieram e
`changes: []`.
</output_rules>"""


def _build_reviewer_user_message(
    *, architect_output: Dict[str, Any], entity_facts: Dict[str, Any], forced_language: str
) -> str:
    import json

    return (
        "<idioma_forcado>\n"
        f"{forced_language}\n"
        "</idioma_forcado>\n\n"
        "<fatos_da_entidade>\n"
        f"{json.dumps(entity_facts or {}, ensure_ascii=False, indent=2)}\n"
        "</fatos_da_entidade>\n\n"
        "<funil_arquitetado>\n"
        f"{json.dumps(architect_output or {}, ensure_ascii=False, indent=2)}\n"
        "</funil_arquitetado>\n\n"
        "<comando>\n"
        "Audite e corrija o funil acima seguindo a checklist de revisão. "
        "Responda APENAS o JSON no schema definido.\n"
        "</comando>"
    )


class FunnelReviewer(BaseAgent):
    """R7 — segundo passe do Gemini que valida/repara o funil do Arquiteto.

    Invisível (só logs) e fail-open: qualquer falha (sem chave, exceção,
    output inutilizável) devolve o funil original intocado.
    """

    name = "FunnelReviewerAgent"
    phase = "funnel"

    def __init__(self, ctx: AgentContext):
        super().__init__(ctx)
        self.settings = ctx.settings

    def _gemini(self):
        if not self.settings.resolved_gemini_key:
            return None
        from app.llm.gemini import GeminiClient

        return GeminiClient(self.settings, model=self.settings.pautador_entity_funnel_model)

    @staticmethod
    def _original(architect_output: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "funnel_strategy": architect_output.get("funnel_strategy") or {},
            "pages": architect_output.get("pages") or [],
            "changes": [],
        }

    async def review(
        self,
        architect_output: Dict[str, Any],
        *,
        entity_facts: Dict[str, Any],
        forced_language: str,
    ) -> Dict[str, Any]:
        fallback = self._original(architect_output)

        client = self._gemini()
        if client is None:
            self.log("Revisor sem chave Gemini — funil original mantido (fail-open).", level="debug")
            return fallback

        try:
            user = _build_reviewer_user_message(
                architect_output=architect_output,
                entity_facts=entity_facts or {},
                forced_language=forced_language or "",
            )
            candidate = await client.complete_json(REVIEWER_SYSTEM_PROMPT, user)
        except Exception as exc:  # noqa: BLE001 — fail-open: nunca propaga
            self.log(f"Revisor (LLM) falhou, funil original mantido: {exc}", level="warning")
            return fallback

        if not isinstance(candidate, dict) or not isinstance(candidate.get("pages"), list) or not candidate["pages"]:
            self.log("Revisor devolveu output inutilizável — funil original mantido (fail-open).", level="warning")
            return fallback

        changes = candidate.get("changes")
        result = {
            "funnel_strategy": candidate.get("funnel_strategy") or fallback["funnel_strategy"],
            "pages": candidate["pages"],
            "changes": changes if isinstance(changes, list) else [],
        }
        self.log(
            f"Revisor aplicou {len(result['changes'])} correção(ões) no funil.",
            level="debug",
            payload={"changes": result["changes"]},
        )
        return result
