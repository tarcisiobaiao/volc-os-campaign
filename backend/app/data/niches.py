"""
Nichos selecionáveis do Pautador Pro (R1) — constantes-seed + resolução.

SEED_NICHES espelha o seed SQL de `src/sql/v7_11_pautador_niches.sql`
(tabela `public.pautador_niches`). Serve como fallback honesto quando o
Supabase está indisponível/desativado (mesmo padrão de
`app/data/countries.py::fallback_countries`).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Mesmos slugs/labels/guidance/allowed_verticals/sort_order da migração v7_11.
SEED_NICHES: List[Dict[str, Any]] = [
    {
        "slug": "beneficios_sociais",
        "label": "Benefícios sociais",
        "guidance": (
            "Programas de transferência de renda, auxílios, bolsas, pensões e "
            "amparo social — foco em quem recebe/solicita. NÃO incluir tributos, "
            "documentos ou serviços administrativos genéricos."
        ),
        "allowed_verticals": ["gov_beneficios"],
        "sort_order": 10,
    },
    {
        "slug": "servicos_governo",
        "label": "Serviços do governo",
        "guidance": (
            "Órgãos, sistemas, documentos, obrigações e serviços públicos "
            "(emissão, consulta, agendamento, cadastros). NÃO confundir com "
            "benefícios de renda."
        ),
        "allowed_verticals": ["gov_beneficios"],
        "sort_order": 20,
    },
    {
        "slug": "educacao",
        "label": "Educação",
        "guidance": (
            "Matrículas, bolsas, financiamento estudantil, vestibulares, cursos "
            "e certificações."
        ),
        "allowed_verticals": ["educacao"],
        "sort_order": 30,
    },
    {
        "slug": "emprego",
        "label": "Emprego",
        "guidance": (
            "Carreira, trabalho, vagas, trabalho por/em aplicativos, direitos "
            "trabalhistas, concursos e qualificação."
        ),
        "allowed_verticals": ["empregos_concursos"],
        "sort_order": 40,
    },
    {
        "slug": "financas",
        "label": "Finanças",
        "guidance": (
            "Crédito, empréstimo, financiamento, investimentos, seguros, "
            "impostos e apps financeiros."
        ),
        "allowed_verticals": ["financas", "credito", "seguros"],
        "sort_order": 50,
    },
    {
        "slug": "aplicativos",
        "label": "Aplicativos",
        "guidance": (
            "Apps de alto uso e dúvidas utilitárias (como funciona, cadastro, "
            "recuperar acesso, tarifas), com ângulo informacional de publisher."
        ),
        "allowed_verticals": ["tecnologia"],
        "sort_order": 60,
    },
]


def resolve_niches(slugs: Optional[List[str]], db_rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Filtra nichos pelos `slugs` pedidos, usando `db_rows` (Supabase) quando
    fornecido, senão as constantes-seed. `slugs` vazio/None -> retorna todos."""
    source = db_rows if db_rows is not None else SEED_NICHES
    if not slugs:
        return list(source)
    wanted = set(slugs)
    return [n for n in source if n.get("slug") in wanted]
