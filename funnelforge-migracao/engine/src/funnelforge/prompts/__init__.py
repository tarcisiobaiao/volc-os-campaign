from __future__ import annotations

from jinja2 import Environment, PackageLoader, select_autoescape

from funnelforge.pipeline.doctrine import doctrine_context

_env = Environment(
    loader=PackageLoader("funnelforge", "prompts"),
    autoescape=select_autoescape(enabled_extensions=()),
    keep_trailing_newline=True,
)

# Os prompts que FALAM a doutrina de copy. Para eles, doctrine.py entra aqui --
# não é responsabilidade de cada chamador lembrar de passar.
#
# Era esse "lembrar" que faltava: `step_write` renderizava o redator_p1 SEM
# doctrine_context, e como os templates usavam `{% for f in banned_fear |
# default([]) %}`, a lista sumia EM SILÊNCIO e o prompt seguia com as
# proibições escritas à mão -- foi assim que um CTA em 1ª pessoa que o
# validador BANE virou instrução dentro do prompt da LP.
_PROMPTS_COM_DOUTRINA = frozenset({
    "redator_p1", "redator_pages", "redator_presell", "judge",
    # ramo editorial novo: as mesmas listas de falsidade (medo fabricado, falsa
    # oficialidade, execução simulada), que os validadores conferem de verdade.
    "redator_p1_v2", "redator_pages_v2", "redator_presell_v2",
})

# RAMO EDITORIAL NOVO (`run.editorial_v2`). Os templates v2 são ARQUIVOS
# SEPARADOS, resolvidos pelo nome — e não um `if` espalhado dentro dos antigos:
# com a flag desligada, os templates antigos nem são tocados, e o teste de ouro
# prova que o que se pede ao modelo continua byte a byte o mesmo.
_PROMPTS_COM_VERSAO_V2 = frozenset({
    "redator_p1", "redator_pages", "redator_presell", "seo",
    "image_prompt", "image_prompt_lp",
})

# O revisor contextual (B5) também recebe o contrato de identidade: é contra ele
# que os achados de `identidade` são julgados.
_PROMPTS_COM_IDENTIDADE = frozenset({"redator_widget", "seo", "seo_v2", "briefing", "revisor"})


def nome_do_prompt(nome: str, *, v2: bool) -> str:
    """O template do ramo pedido. No ramo novo, só troca quem TEM versão v2."""
    return f"{nome}_v2" if v2 and nome in _PROMPTS_COM_VERSAO_V2 else nome


def render(name: str, **ctx) -> str:
    if name in _PROMPTS_COM_DOUTRINA:
        # A doutrina VENCE o que o chamador mandou: ninguém apaga a lista de
        # proibições por acidente (nem um passo do pipeline, nem um teste).
        ctx = {**ctx, **doctrine_context()}
    text = _env.get_template(f"{name}.jinja").render(**ctx)
    if name in _PROMPTS_COM_DOUTRINA or name in _PROMPTS_COM_IDENTIDADE:
        text = _env.get_template("editorial_identity.jinja").render() + "\n" + text
    return text
