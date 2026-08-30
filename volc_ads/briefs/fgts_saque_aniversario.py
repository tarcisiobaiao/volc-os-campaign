"""Brief da primeira campanha real — Saque-Aniversário FGTS, Crédito Up.

Destino único: a LP `/r/antecipacao-saque-aniversario-fgts/`. As páginas `/rec/`
são navegação interna e NUNCA destino de anúncio — inclusive de sitelink.

Três restrições moldaram cada linha deste arquivo, nesta ordem:

1. **A blocklist do próprio forge** (`campanha/limites.yaml`) proíbe em texto de
   anúncio: "antecipação", "empréstimo", "garantido", "crédito aprovado",
   "dinheiro na conta", "consulte seu cpf". O tema do funil é exatamente
   antecipação — então a copy fala de **regra, prazo, tabela e direito**, nunca
   da operação de crédito. Não é contorno da trava: é o que mantém o anúncio
   coerente com um portal que explica e não intermedeia.

2. **A base factual** (`auditoria-redator/04-artefatos-refatoracao/01-base-factual.md`).
   Nada aqui afirma o que a página deliberadamente não afirma: não há promessa de
   liberação de saldo, de aprovação, de prazo de desaverbação, nem piso comercial
   apresentado como regra geral.

3. **O precedente de política medido nas contas** (11/08/2026, 39 contas):
   `GOVERNMENT_DOCUMENTS_AND_OFFICIAL_SERVICES` deixou 57 anúncios FULLY_LIMITED,
   e o padrão reprovado é sempre o mesmo — imperativo que sugere que o site
   executa o serviço oficial ("Baixe seu Novo RG", "Solicite seu Novo RG",
   "Emitir o Novo RG"). Por isso não há um único imperativo de execução abaixo.

Keywords e lance saíram de medição, não de estimativa — ver `MEDIDO` em cada bloco.
"""

from __future__ import annotations

from volc_ads.campanha.brief import Brief, Copy, Sitelink, Snippet
from volc_ads.campanha.taxonomia import Nomenclatura

# ── conta ────────────────────────────────────────────────────────────────────
CUSTOMER_ID = "8017851692"        # Crédito Up
LOGIN_CUSTOMER_ID = "6016739364"  # MCC VOLC Negócios Digitais

URL_LP = "https://creditoup.com.br/r/antecipacao-saque-aniversario-fgts/"

# ── nomenclatura canônica ────────────────────────────────────────────────────
# `search.py` ainda NÃO consome isto (monta o nome com prefixo+carimbo). Fica
# registrado aqui porque é o nome que a taxonomia exige e que `analisar()`
# consegue reconstruir — ver a lacuna nº 1 do relatório.
NOME = Nomenclatura(
    site="CU",
    sequencia=1,
    tema="Saque-Aniversario FGTS",
    canal="SEARCH",
    slug="antecipacao-saque-aniversario-fgts",
)

# ── keywords ─────────────────────────────────────────────────────────────────
# MEDIDO em 39 contas, 12/07 a 10/08/2026, sobre keyword_view + search_term_view:
#
#   termo                              CPC     CPA    cliques
#   saque aniversário fgts            0,171   0,268       11
#   fgts saque aniversário            0,147   0,378      103
#   quem tem direito ao fgts          0,175   0,301       48
#   fgts (genérico)                   0,219   0,407    9.835
#
# O cluster de saque-aniversário compra 22% a 33% mais barato que o "fgts"
# genérico e converte melhor. O genérico ficou de fora de propósito: volume
# enorme com intenção difusa, e a LP responde uma pergunta específica.
#
# Os termos de consulta de saldo ("consultar fgts pelo cpf", CTR 9,3%) também
# ficaram fora: a intenção deles é a da P1, e a P1 não pode receber clique pago.
# Mandá-los para a LP é fabricar DESTINATION_MISMATCH.
KEYWORDS = [
    "saque aniversario fgts",
    "fgts saque aniversario",
    "saque aniversario fgts 2026",
    "como funciona o saque aniversario",
    "regras do saque aniversario",
    "quem tem direito ao saque aniversario",
    "saque aniversario quanto recebo",
    "calcular saque aniversario fgts",
    "tabela do saque aniversario",
    "saque aniversario ou saque rescisao",
    "mudar para saque aniversario fgts",
    "saque aniversario fgts prazo",
]

# ── negativas ────────────────────────────────────────────────────────────────
# Duas famílias, por motivos diferentes.
#
# (a) Intenção transacional e marca de instituição. Quem busca por elas quer
#     contratar, não ler — sai da página e leva o clique embora. Pior: é o
#     material que empurra a campanha para a classificação PERSONAL_LOANS,
#     que nas contas medidas aparece como PROHIBITED em 46 anúncios.
#     "caixa" ficou DE FORA de propósito: é o operador oficial e aparece em
#     consulta informativa legítima ("saque aniversario caixa como funciona").
#
# (b) Homônimos e público errado. "fgts digital" é sistema do EMPREGADOR,
#     não do trabalhador — audiência inteiramente distinta da LP.
NEGATIVAS_CAMPANHA = [
    # (a) transacional / marca
    "emprestimo", "consignado", "financiamento", "credito pessoal",
    "contratar", "simular emprestimo", "taxa de juros",
    "meutudo", "nubank", "bmg", "santander", "itau", "bradesco",
    "picpay", "daycoval", "banco pan", "will bank", "creditas",
    # (b) público errado / homônimo
    "fgts digital", "empregador", "recolhimento", "guia de recolhimento",
    "conectividade social", "e-social",
    "advogado", "acao judicial", "revisional", "correcao do fgts",
    "concurso", "curso", "vaga de emprego", "apk", "baixar aplicativo",
    "telefone", "0800", "reclame aqui",
]

# ── copy ─────────────────────────────────────────────────────────────────────
# Nenhum headline usa imperativo de execução. O verbo, quando existe, é do
# leitor sobre a informação ("entenda", "veja"), nunca do site sobre o benefício.
COPY = Copy(
    headlines=[
        "Saque-Aniversário FGTS 2026",
        "Regras do Saque-Aniversário",
        "Quem Tem Direito em 2026",
        "Como Funciona o Saque Anual",
        "Tabela Oficial por Faixa",
        "Calcule Seu Saque Anual",
        "O Prazo de 90 Dias Explicado",
        "A Regra Muda em 31/10/2026",
        "O Que Diz a Lei 8.036/90",
        "Saque-Aniversário: Guia 2026",
        "Regras Atualizadas do FGTS",
        "Demissão e Multa Rescisória",
        "Saque Anual: Como Calcular",
        "Entenda o Passo a Passo",
        "Saldo e Saque Anual: Difere",
    ],
    descriptions=[
        "Regras do Saque-Aniversário do FGTS em 2026: prazos, limites e "
        "quem tem direito.",
        "Portal informativo: consulte a tabela legal por faixa e calcule "
        "seu saque anual do ano.",
        "Conteúdo apoiado na Lei 8.036/90 e na Resolução CCFGTS 1.130/2025. "
        "Fontes citadas.",
        "Veja o prazo de 90 dias, a regra que muda em 31/10/2026 e a "
        "diferença entre saldo e saque.",
    ],
    # ATENÇÃO: `search.py` sobrescreve a URL de todo sitelink para
    # `{url_final}&sl={n}`. Todos apontam para a própria LP — o que por acaso
    # respeita a restrição de destino único, mas anula a função do sitelink.
    # Ver a lacuna nº 2 do relatório.
    sitelinks=[
        Sitelink("Regras de 2026",
                 "O que vale hoje", "E o que muda em outubro"),
        Sitelink("Tabela por faixa",
                 "Alíquota e parcela", "Conforme o Anexo da lei"),
        Sitelink("Quem tem direito",
                 "As condições mínimas", "Em linguagem simples"),
        Sitelink("Demissão e FGTS",
                 "O que fica disponível", "E o que continua retido"),
    ],
    callouts=[
        "Conteúdo informativo",
        "Fontes oficiais citadas",
        "Atualizado em 2026",
        "Portal independente",
    ],
    snippet=Snippet("Tipos", [
        "Saque-Aniversário",
        "Saque-Rescisão",
        "Multa rescisória",
        "Saque anual",
    ]),
)

# ── o brief ──────────────────────────────────────────────────────────────────
BRIEF = Brief(
    nicho="Saque-Aniversario FGTS",
    slug="antecipacao-saque-aniversario-fgts",
    url_final=URL_LP,
    keywords=KEYWORDS,
    copy=COPY,
    pais="BR",
    idioma="pt",

    # R$ 10/dia — canário. Decisão do operador, e Search comporta: a API não
    # impõe piso nenhum aqui (R$ 1,00 passou no validate_only). O piso de
    # R$ 25,40/dia que a API devolve em budget_per_day_minimum_error_details
    # vale só para Demand Gen, e este brief é Search.
    #
    # Ao CPC medido de ~R$ 0,17 são ~59 cliques/dia. É pouco para MaximizeConversions
    # sair do aprendizado rápido — mas a primeira rodada é para ver política
    # aprovar e o rastreio fechar, não para escalar. Sobe depois, com dado.
    budget_diario=10.0,

    # MEDIDO: CPC do cluster entre 0,147 e 0,219. 0,20 é teto de segurança do
    # ad group. Com MaximizeConversions a API ignora este lance — ele existe
    # como rede de proteção caso a estratégia seja trocada para manual.
    cpc_inicial=0.20,

    # DELIBERADAMENTE None. A conta tem ZERO campanhas e ZERO histórico de
    # conversão. tCPA sem histórico é chute com autoridade: o Google precisa de
    # ~30 conversões para calibrar. Sobe em MaximizeConversions puro, e o tCPA
    # entra na segunda rodada, ancorado no CPA real desta conta — não no CPA
    # dos primos. O alvo natural será ~R$ 0,35, abaixo do valor de R$ 10,00 por
    # adViewInterstitial.
    tcpa=None,

    # PHRASE, contra o hábito dos primos. As 109 keywords de FGTS medidas nas
    # contas ativas são quase todas BROAD — e funciona lá, porque há histórico
    # de conversão para o algoritmo pisar. Aqui não há nenhum. BROAD numa conta
    # zerada gasta o orçamento aprendendo o que PHRASE já sabe.
    match_type="PHRASE",

    negativas_campanha=NEGATIVAS_CAMPANHA,
    negativas_adgroup=[],

    vertical="informativo",
    ai_max=False,
    prefixo_nome="FORGE",
)
