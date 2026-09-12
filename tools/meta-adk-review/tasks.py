"""Lead-curated implementation tickets, not open-ended discovery requests."""
from dataclasses import dataclass, replace
import json
from config import Lane, lane


@dataclass(frozen=True)
class Ticket:
    slug: str
    lane_name: str
    title: str
    evidence: str
    acceptance: tuple[str, ...]
    sources: tuple[tuple[str, int, int], ...]
    writes: tuple[str, ...]
    test: str
    research: str

    def scoped_lane(self) -> Lane:
        return replace(lane(self.lane_name), entrypoints=tuple(s[0] for s in self.sources),
                       write_prefixes=self.writes, test_prefixes=(self.test,))

    def contract(self) -> str:
        return json.dumps({"id": self.slug, "title": self.title, "observed_before": self.evidence,
                           "acceptance": self.acceptance, "allowed_files": self.writes,
                           "required_test": self.test, "research_question": self.research},
                          ensure_ascii=False, indent=2)


COPY = 'src/components/trafego/meta/VarinhaDeCopy.tsx'
COPY_TEST = 'src/components/trafego/meta/__tests__/nomenclatura-copy.test.tsx'
TEXTS = 'src/components/trafego/meta/TextosDoAnuncioFlexivel.tsx'
TEXTS_TEST = 'src/components/trafego/meta/__tests__/textos-flexiveis.test.tsx'
ATTRIBUTION = 'backend/app/trafego/meta/atribuicao.py'
FINANCIAL = 'backend/app/trafego/meta/financeiro.py'
FINANCIAL_TEST = 'backend/tests/test_meta_financial_lineage.py'
API_TYPES = 'src/lib/pautadorApi.ts'
FINANCIAL_VIEW = 'src/components/trafego/meta/ConjuntosFinanceiros.tsx'
FINANCIAL_VIEW_TEST = 'src/components/trafego/meta/__tests__/conjuntos-financeiros.test.tsx'

TICKETS = {
    "copy_retry": Ticket(
        "copy_retry", "creative_system", "Preservar sugestões válidas quando nova geração falha",
        "generate() chama setResult(null) antes de save/read/suggest. Um retry que falha apaga o preview já pago. "
        "As guardas de fingerprint já existem; não são um bug e devem ser mantidas.",
        (
            "No MESMO contexto, retry mantém preview visível até resposta nova bem-sucedida; erro não o apaga.",
            "Enquanto busy, acrescentar/substituir são disabled e apply também verifica busy; sem aplicação automática.",
            "Erro no mesmo contexto reabilita preview anterior. Sucesso substitui atomicamente a sugestão anterior.",
            "Contexto alterado jamais aplica resposta antiga. Preview já obsoleto pode ser limpo ao iniciar retry, "
            "preservando a regressão existente de mudança de contexto durante voo.",
            "Teste promises pendentes, rejeição, resposta nova, onApply não chamado indevidamente e guardas existentes.",
            "Preservar limite cinco, deduplicação, demo, salvamento e consentimento explícito para geração.",
        ),
        ((COPY, 1, 160), (COPY_TEST, 1, 400)), (COPY, COPY_TEST), COPY_TEST,
        "Consulte documentação oficial Meta flexible ad format: limites de cinco textos por tipo; "
        "e React react.dev sobre race conditions em respostas assíncronas. Esta missão não muda payload nem elegibilidade.",
    ),
    "flexible_focus": Ticket(
        "flexible_focus", "creative_system", "Edição de variações com continuidade de foco",
        "Adicionar/remover em TextosDoAnuncioFlexivel só executa onChange; adicionar quinta opção desabilita "
        "o botão focado e remover um item elimina o controle focado sem reposicionamento.",
        (
            "Adicionar opção foca o novo input/textarea após React renderizar, inclusive quinta opção.",
            "Remover opção foca campo seguinte no mesmo grupo; se última, anterior; grupo opcional vazio foca Adicionar descrição.",
            "Somente ação local de adicionar/remover solicita foco. Render externo não rouba foco; disabled impede mutação.",
            "Preservar conteúdo literal de outros itens/grupos, mínimos (1/1/0), máximo cinco e formato do onChange.",
            "Testes com componente controlado assertam document.activeElement em adicionar/remover e isolamento de dois editores.",
            "Sem query global ambígua, timers arbitrários, novas dependências, CSS global ou mudança no contrato Meta.",
        ),
        ((TEXTS, 1, 180), (TEXTS_TEST, 1, 400)), (TEXTS, TEXTS_TEST), TEXTS_TEST,
        "Consulte W3C WAI sobre foco de teclado ao remover controles dinâmicos, react.dev refs/focus, "
        "e documentação Meta flexible ad format para distinguir pools de teste A/B. Não mude limites do produto.",
    ),
    "funnel_evidence_contract": Ticket(
        "funnel_evidence_contract", "measurement_ops",
        "Preservar o percurso clique no link → chegada à LP → monetização e qualificar a evidência",
        "O coletor e a view latest já guardam inline_link_clicks e landing_page_views, mas "
        "linha_de_conjunto_dia descarta ambos. O financeiro já leva GAM impressions/clicks, receita, "
        "completude, provisionalidade e reconciliação, porém não publica um estado de evidência nem explicita "
        "que profit_gross desconta somente mídia.",
        (
            "LinhaAtribuicao e Total preservam inline_link_clicks e landing_page_views como int|null; total do período "
            "é null se qualquer linha do grão não mediu a etapa, e zero medido continua zero.",
            "Publicar landing_page_load_rate_pct = LPV/link clicks*100, cost_per_landing_page_view = spend/LPV e "
            "gam_impressions_per_landing_page_view = GAM impressions/LPV somente com denominador positivo; nunca dividir por zero.",
            "O financeiro vazio e preenchido expõem os campos no total e por conjunto, sem alterar o grão adset/dia, "
            "a atribuição de receita, o mascaramento ou a reconciliação campaign-level.",
            "Publicar contribution_observed como alias honesto de revenue_brl - Meta spend e evidence_state determinístico: "
            "INCOMPLETE quando gasto/receita incompletos, PROVISIONAL quando inclui hoje, UNRECONCILED quando a leitura "
            "campaign-level diverge, OBSERVED_COMPLETE apenas quando nenhuma dessas condições existe. Incluir reasons e "
            "economic_basis='gam_revenue_brl_minus_meta_spend'; custos além de mídia ficam explicitamente NOT_MODELED.",
            "O estado é informativo e não autoriza pausa, escala, publicação ou gasto. Não criar score/threshold arbitrário.",
            "Testes cobrem soma, ausência, zero, denominadores, estado de evidência e preservam os testes atuais.",
        ),
        ((ATTRIBUTION, 120, 400), (FINANCIAL, 100, 400), (FINANCIAL_TEST, 1, 400)),
        (ATTRIBUTION, FINANCIAL, FINANCIAL_TEST), FINANCIAL_TEST,
        "Consulte a documentação oficial Meta Insights para inline_link_clicks, landing_page_view e action metrics. "
        "A pesquisa só valida semântica de campo; não mude janela, atribuição ou política com base em fonte secundária.",
    ),
    "funnel_evidence_ui": Ticket(
        "funnel_evidence_ui", "measurement_ops",
        "Tornar o percurso e a confiança da contribuição visíveis no dashboard Meta",
        "ConjuntosFinanceiros mostra gasto/receita/ROAS e prova da soma, mas oculta os campos de clique no link e "
        "chegada à LP já coletados. O operador não enxerga em qual ponte há perda nem que lucro bruto é somente "
        "receita GAM menos mídia Meta.",
        (
            "Estender os tipos sem afrouxar campos existentes e renderizar, antes da tabela, uma única superfície densa "
            "'Percurso até a monetização' com cliques no link, LPV, impressões GAM e receita, preservando null como travessão.",
            "Mostrar as pontes LPV/clique no link, custo por LPV e impressões GAM/LPV somente quando o servidor as fornecer; "
            "explicar que impressões GAM podem incluir múltiplos slots/refresh e não são pessoas ou retenção.",
            "Mostrar 'Contribuição observada' com a base receita GAM menos mídia Meta e um estado textual para "
            "INCOMPLETE, PROVISIONAL, UNRECONCILED ou OBSERVED_COMPLETE; nunca chamar de lucro líquido nem usar score inventado.",
            "Estados desconhecidos/ausentes ensinam o que falta. Layout é lista no mobile e grade/divisores no desktop, "
            "sem nested cards, raw hex, gradiente decorativo ou nova dependência; foco/semântica WCAG preservados.",
            "Testes cobrem campos completos, ausência sem zero inventado, explicação GAM e todos os estados de evidência.",
        ),
        ((API_TYPES, 500, 150), (FINANCIAL_VIEW, 1, 400), (FINANCIAL_VIEW_TEST, 1, 240)),
        (API_TYPES, FINANCIAL_VIEW, FINANCIAL_VIEW_TEST), FINANCIAL_VIEW_TEST,
        "Consulte apenas documentação oficial Meta para os nomes das métricas e W3C/WAI para descrição de grupos de dados. "
        "Não invente benchmark, cor de performance ou recomendação automática.",
    ),
}


def preload(host, ticket: Ticket) -> str:
    """Read via the same redacting capability host and register edit hashes."""
    sources = [host.read_file(path, start, count) for path, start, count in ticket.sources]
    if any('error' in item for item in sources):
        raise ValueError('ticket context could not be loaded safely')
    encoded = json.dumps(sources, ensure_ascii=False)
    if len(encoded) > 60_000:
        raise ValueError('ticket too broad: split into smaller implementation tickets')
    return encoded
