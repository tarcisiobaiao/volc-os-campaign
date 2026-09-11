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
