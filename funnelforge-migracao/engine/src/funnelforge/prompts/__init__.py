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
})


def render(name: str, **ctx) -> str:
    if name in _PROMPTS_COM_DOUTRINA:
        # A doutrina VENCE o que o chamador mandou: ninguém apaga a lista de
        # proibições por acidente (nem um passo do pipeline, nem um teste).
        ctx = {**ctx, **doctrine_context()}
    return _env.get_template(f"{name}.jinja").render(**ctx)
