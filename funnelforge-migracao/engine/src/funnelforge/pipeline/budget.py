# funnel-forge/src/funnelforge/pipeline/budget.py
"""Teto de gasto por run e por página, conferido ANTES de cada chamada paga.

O pipeline não tinha freio: um passo em laço de retentativa, um fallback caro
ou um funil de 12 páginas gastavam até acabar — e a conta só aparecia no
report.md, depois de paga. Aqui o dinheiro é um recurso finito declarado no
`config.yaml`: quando o teto do run ou o da página corrente já foi atingido, a
próxima chamada paga não sai, e o erro diz quanto foi gasto, qual era o teto e
em que passo parou.

Deliberadamente conservador em dois pontos:

- O teto NÃO é orçamento apertado, é rede de segurança. O padrão fica bem
  acima do medido em campo (~US$ 0,45/página, ~US$ 2,10/funil de 5) justamente
  para não reprovar trabalho bom — ele existe para pegar o laço em fuga.
- Só bloqueia quando o gasto JÁ acumulado atingiu o teto (ou quando a
  estimativa conhecida da próxima chamada o ultrapassa, caso da imagem, cujo
  preço é declarado). Não adivinha custo de chamada de texto: o preço só é
  conhecido depois da resposta.
"""
from __future__ import annotations


class OrcamentoEstourado(RuntimeError):
    """Levantada ANTES de gastar. Carrega os números para a mensagem do relatório."""

    def __init__(self, escopo: str, passo: str, gasto_usd: float, teto_usd: float) -> None:
        self.escopo = escopo          # "run" | "pagina"
        self.passo = passo
        self.gasto_usd = gasto_usd
        self.teto_usd = teto_usd
        super().__init__(
            f"Teto de custo do {escopo} atingido antes do passo '{passo}': "
            f"US$ {gasto_usd:.4f} de US$ {teto_usd:.4f}. "
            f"A chamada paga NÃO foi feita — nada de continuar gastando."
        )


class Orcamento:
    """Contador de gasto com dois tetos: o do run inteiro e o da página corrente.

    `entrar_na_pagina` zera o contador da página (chamado pelo pipeline no topo
    de cada página); passos de nível de run (extract) rodam com a página em
    None e só consomem o teto do run.
    """

    def __init__(self, teto_run_usd: float, teto_pagina_usd: float) -> None:
        self.teto_run_usd = float(teto_run_usd)
        self.teto_pagina_usd = float(teto_pagina_usd)
        self.gasto_run_usd = 0.0
        self.gasto_pagina_usd = 0.0
        self.pagina: str | None = None
        # Gasto por página já encerrada, para o relatório final.
        self.gasto_por_pagina: dict[str, float] = {}

    # -- ciclo de vida --------------------------------------------------------

    def entrar_na_pagina(self, rotulo: str) -> None:
        self._fechar_pagina()
        self.pagina = rotulo
        self.gasto_pagina_usd = 0.0

    def _fechar_pagina(self) -> None:
        if self.pagina is not None:
            self.gasto_por_pagina[self.pagina] = round(self.gasto_pagina_usd, 6)

    # -- uso ------------------------------------------------------------------

    def exigir_saldo(self, passo: str, estimativa_usd: float = 0.0) -> None:
        """Levanta `OrcamentoEstourado` se a próxima chamada paga não couber."""
        if self.teto_run_usd > 0 and self.gasto_run_usd + estimativa_usd >= self.teto_run_usd:
            raise OrcamentoEstourado("run", passo, self.gasto_run_usd, self.teto_run_usd)
        if (self.pagina is not None and self.teto_pagina_usd > 0
                and self.gasto_pagina_usd + estimativa_usd >= self.teto_pagina_usd):
            raise OrcamentoEstourado(
                "pagina", passo, self.gasto_pagina_usd, self.teto_pagina_usd)

    def registrar(self, passo: str, custo_usd: float) -> None:
        """Debita um gasto REAL — inclusive o de tentativa que foi descartada.
        Só o que é debitado aqui conta como dinheiro gasto."""
        custo = float(custo_usd or 0.0)
        if custo <= 0:
            return
        self.gasto_run_usd += custo
        if self.pagina is not None:
            self.gasto_pagina_usd += custo

    def relatorio(self) -> dict:
        self._fechar_pagina()
        return {
            "teto_run_usd": self.teto_run_usd,
            "teto_pagina_usd": self.teto_pagina_usd,
            "gasto_run_usd": round(self.gasto_run_usd, 6),
            "gasto_por_pagina": dict(self.gasto_por_pagina),
        }


def preco_declarado_da_imagem(settings) -> float:
    """Preço da geração de UMA imagem, por qualidade, vindo do `config.yaml`.

    A API de imagens não devolve custo e a chamada nem passa pelo LiteLLM
    (`adapters/image_openai.py` usa httpx cru), então este é o único jeito de a
    imagem aparecer no ledger. É número DECLARADO: se a tabela de preços do
    provedor mudar, muda aqui — o pipeline não tem como descobrir sozinho.
    """
    cfg = getattr(settings, "budget", None)
    if cfg is None:
        return 0.0
    qualidade = str(getattr(getattr(settings, "run", None), "image_quality", "") or "")
    tabela = cfg.image_price_usd or {}
    return float(tabela.get(qualidade, cfg.image_price_fallback_usd))
