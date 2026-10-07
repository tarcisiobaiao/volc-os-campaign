"""
Funnel Reviewer (Fase 3 — R7): backstop determinístico que roda DEPOIS do
Arquiteto (`FunnelProOrchestrator`) e ANTES de `apply_roles_and_slugs`. É um
segundo passe do Gemini que VALIDA e REPARA o funil arquitetado — nunca o
cria do zero.

**Fail-open**: se a chave Gemini não estiver configurada, se `complete_json`
lançar qualquer exceção, ou se o modelo devolver algo inutilizável, `review()`
devolve o funil ORIGINAL (`architect_output`) intocado, com `changes=[]` e
`estado="nao_revisado"`. Um funil deve SEMPRE sobreviver ao revisor — ver
Global Constraints do plano
(docs/superpowers/plans/2026-07-23-pautador-pro-nicho-idioma-funil.md).

## Aponta, não achata (30/09/2026)

O critério de tom mandava "reescrever para um tom informacional e útil", e as
mudanças iam só para log `debug`. Agora:

- tom, voz e promessa sem sustentação são APONTADOS em `achados` (trecho,
  motivo, evidência), sem reescrita;
- o código garante o que dá para conferir: `funnel_strategy.tone_voice` do
  Arquiteto não é trocado (a proposta do revisor vira achado), e tom/avatar
  nunca somem do plano;
- `changes`, `achados` e `estado` voltam no resultado; o orquestrador os grava
  em `funnel_architecture.revisao_arquitetura`. Continuam fora da resposta HTTP.
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
     pt-BR), traduza-o para pt-BR — exceto `funnel_strategy.tone_voice`, que
     você não altera: se ele não estiver em pt-BR, registre em `achados`.
   - Além do idioma, `intro_section` e `closing_section` devem ser ARRAYS de
     bullets em pt-BR (diretrizes para o redator, não prosa pronta). Se
     vierem como uma string única de parágrafo(s), converta em uma lista de
     2-4 bullets pt-BR mantendo o conteúdo/sentido original.
   - Campos puramente estruturais (`page_type`) não são texto de leitura e
     podem permanecer como estão.

3. **Datas pertinentes**
   Não acrescente ano por hábito. Mantenha data apenas quando necessária à intenção
   e sustentada nos insumos; não simule uma atualização que não foi verificada.

4. **Tom, voz e promessa — aponte, não reescreva**
   Não reescreva o tom, o ângulo nem a voz do Arquiteto, e não troque um
   benefício verdadeiro por um texto neutro: `funnel_strategy.tone_voice` fica
   exatamente como veio. Avalie a PROMESSA no contexto, nunca uma palavra
   isolada: prazo ou contagem de tempo artificial (ex.: "em 30 segundos"),
   número ou estatística sem sustentação nos fatos da entidade, urgência ou
   escassez fabricada, garantia de resultado certo. Ao encontrar um desses,
   NÃO altere o campo: registre em `achados` a página, o campo, o trecho
   exato, o motivo e a evidência (o fato da entidade que falta ou que o
   contradiz). Texto correto porém genérico não é violação — no máximo, um
   achado de oportunidade.

5. **Relevância e profundidade**
   Cada página de SOLUÇÃO deve entregar uma resposta completa, com seções
   pertinentes à dúvida, sem cota de H2. Deve ser realmente necessária. Página rasa ou
   desnecessária (ex.: uma página inteira só sobre "como entrar em
   contato") deve ser FUNDIDA com outra página de solução relacionada, ou
   derrubada — nunca deixe uma página fraca sozinha no funil final.

6. **Contrato de intenção e navegação**
   Preserve e revise `editorial` em TODAS as páginas: reader_question, useful_delivery,
   cta_label e links (target + reason). Rótulos são no idioma publicável; diretrizes em PT-BR.
   Se fundir, remover ou renomear páginas, atualize TODOS os targets para slugs existentes.
   Não rotacione soluções nem varie rótulos por obrigação. Priorize a dúvida relevante.
   Não esconda a resposta em FAQ ou fragmente conteúdo só para gerar mais cliques.
   Campos ausentes devem ser preenchidos a partir da intenção, não de fatos inventados.

Ao final, você pode ter fundido, derrubado ou reordenado páginas — o que
importa é que o funil final seja factualmente correto, no idioma certo, sem
datas por hábito e relevante/profundo, com a voz do Arquiteto preservada e
toda promessa sem sustentação registrada em `achados`.
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
      "target_keywords": ["..."],
      "editorial": {"reader_question": "...", "useful_delivery": "...", "cta_label": "...",
                    "links": [{"target": "slug-existente", "reason": "..."}]}
    }
  ],
  "changes": [
    "Descrição curta, em PT-BR, de cada correção aplicada"
  ],
  "achados": [
    {"pagina": 1, "campo": "hook_to_next_page", "trecho": "texto exato",
     "motivo": "o que pode estar errado, em PT-BR",
     "evidencia": "o fato da entidade que falta ou que contradiz o trecho"}
  ]
}

Mantenha em cada página TODAS as chaves originais que ela já tinha (mesmo as
que você não precisou corrigir). `changes` deve listar, em frases curtas e em
PT-BR, cada correção feita (ex.: "Removido ano do h1_title da P2", "Traduzido
intro_section da P1 para pt-BR", "Página de contato fundida na P3 (rasa)").
`achados` lista o que você viu e NÃO alterou (promessa sem sustentação, tom,
voz), sempre com o trecho exato e a evidência.
Se nada precisou ser corrigido, devolva as páginas como vieram e
`changes: []`; sem achados, `achados: []`.
</output_rules>"""

# Campos de um achado. Qualquer outra chave que o modelo inventar é descartada:
# o achado vai gravado na arquitetura e o motor o lê como dado.
_CAMPOS_DE_ACHADO = ("pagina", "campo", "trecho", "proposta", "motivo", "evidencia")


def _texto(valor: Any) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def _achados(bruto: Any) -> List[Dict[str, Any]]:
    """O que o revisor APONTOU sem mudar, num formato só.

    String solta vira `{"motivo": ...}`; dicionário mantém só os campos
    conhecidos; item sem `trecho` nem `motivo` não é achado e sai.
    """
    saida: List[Dict[str, Any]] = []
    for item in bruto if isinstance(bruto, list) else []:
        if isinstance(item, str):
            if item.strip():
                saida.append({"motivo": item.strip()})
        elif isinstance(item, dict):
            limpo = {k: item[k] for k in _CAMPOS_DE_ACHADO
                     if item.get(k) not in (None, "", [], {})}
            if limpo.get("motivo") or limpo.get("trecho"):
                saida.append(limpo)
    return saida


def _estrategia_preservada(original: Dict[str, Any], proposta: Any,
                           achados: List[Dict[str, Any]]) -> Dict[str, Any]:
    """A `funnel_strategy` revisada, com a VOZ e o PÚBLICO do Arquiteto garantidos.

    - Chave que o revisor esqueceu continua a do Arquiteto (nada some do plano).
    - `tone_voice` é do Arquiteto: se o revisor propôs outro, o original fica e
      a proposta vira achado — é a trava de código para "o revisor não reescreve
      o tom", que o prompt sozinho não garante.
    - `avatar_summary` pode ser refinado pelo revisor (fato, país, processo),
      mas nunca apagado.
    """
    fs = {**original, **(proposta if isinstance(proposta, dict) else {})}

    tom_original = _texto(original.get("tone_voice"))
    tom_proposto = _texto(fs.get("tone_voice"))
    if tom_original:
        fs["tone_voice"] = original["tone_voice"]
        if tom_proposto and tom_proposto != tom_original:
            achados.append({
                "campo": "funnel_strategy.tone_voice",
                "trecho": tom_original,
                "proposta": tom_proposto,
                "motivo": "o revisor propôs outra voz; a do Arquiteto foi mantida "
                          "(proposta registrada, não aplicada)",
            })

    if not _texto(fs.get("avatar_summary")) and _texto(original.get("avatar_summary")):
        fs["avatar_summary"] = original["avatar_summary"]
    return fs


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

    Fail-open: qualquer falha (sem chave, exceção, output inutilizável) devolve
    o funil original intocado, com `estado="nao_revisado"` e o motivo — sem a
    mensagem crua da exceção, que no cliente Gemini traz a URL com a chave.
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
    def _original(architect_output: Dict[str, Any], motivo: str) -> Dict[str, Any]:
        return {
            "funnel_strategy": architect_output.get("funnel_strategy") or {},
            "pages": architect_output.get("pages") or [],
            "changes": [],
            "achados": [],
            "estado": "nao_revisado",
            "motivo": motivo,
        }

    async def review(
        self,
        architect_output: Dict[str, Any],
        *,
        entity_facts: Dict[str, Any],
        forced_language: str,
    ) -> Dict[str, Any]:
        client = self._gemini()
        if client is None:
            self.log("Revisor sem chave Gemini — funil original mantido (fail-open).", level="debug")
            return self._original(architect_output, "revisor sem chave Gemini configurada")

        try:
            user = _build_reviewer_user_message(
                architect_output=architect_output,
                entity_facts=entity_facts or {},
                forced_language=forced_language or "",
            )
            candidate = await client.complete_json(REVIEWER_SYSTEM_PROMPT, user)
        except Exception as exc:  # noqa: BLE001 — fail-open: nunca propaga
            self.log(f"Revisor (LLM) falhou, funil original mantido: {exc}", level="warning")
            # Só o tipo: a mensagem crua pode trazer a URL com a chave.
            return self._original(
                architect_output, f"falha na chamada ao revisor ({type(exc).__name__})")

        if not isinstance(candidate, dict) or not isinstance(candidate.get("pages"), list) or not candidate["pages"]:
            self.log("Revisor devolveu output inutilizável — funil original mantido (fail-open).", level="warning")
            return self._original(architect_output, "saída do revisor inutilizável (sem páginas)")

        changes = candidate.get("changes")
        achados = _achados(candidate.get("achados"))
        result = {
            "funnel_strategy": _estrategia_preservada(
                architect_output.get("funnel_strategy") or {},
                candidate.get("funnel_strategy"), achados),
            "pages": candidate["pages"],
            "changes": changes if isinstance(changes, list) else [],
            "achados": achados,
            "estado": "revisado",
        }
        self.log(
            f"Revisor aplicou {len(result['changes'])} correção(ões) e apontou "
            f"{len(achados)} achado(s) no funil.",
            level="debug",
            payload={"changes": result["changes"], "achados": achados},
        )
        return result
