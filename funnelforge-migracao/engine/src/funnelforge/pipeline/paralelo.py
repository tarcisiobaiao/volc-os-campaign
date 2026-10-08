"""REDAÇÃO PARALELA SEGURA: páginas em workers isolados, consolidação serial.

Só roda depois do DOSSIÊ CONGELADO — a pesquisa (o gasto faturado) já
aconteceu, serial, e cada página recebe o seu pacote fechado. O que cada
worker tem:

* uma CÓPIA PROFUNDA do `RunState` (nunca o estado global);
* um `RunnerDaPagina`: o mesmo LLM, o orçamento visto pela página
  (`Orcamento.para_pagina`), `checkpoint` sem efeito e log/prompts em
  `<run>/paginas/pN/` — `state.json` e `log.jsonl` são só do consolidador;
* provedores que não são thread-safe (print oficial com browser, sitemap)
  atrás de uma trava única.

O worker devolve um `DeltaDaPagina`: o que mudou na cópia, SÓ nas chaves da
própria página. Mudança fora dela é violação registrada e não é aplicada. A
consolidação aplica os deltas em ordem de `page_number`, funde logs e prompts
na mesma ordem, e então refaz a checagem de unicidade entre as páginas do lote
— no paralelo o redator não vê os rascunhos irmãos, e o serial via.

Artefatos de auditoria (`pN.*`, `metadados_pN.json`) já nascem com o número da
página no nome e vão direto para a pasta do run: nomes disjuntos por
construção.
"""
from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from funnelforge.domain.models import Page, RunState, StepResult
from funnelforge.pipeline.runner import Runner

MAX_PAGE_WORKERS = 3

#: Campos do `RunState` indexados por número de página.
CAMPOS_POR_PAGINA = (
    "facts", "drafts", "seo", "images", "image_reviews", "screenshots",
    "official_links", "published", "briefings", "revisoes", "recibos",
    "decisoes_humanas", "normalizacoes", "decoracoes", "metadados",
)
#: O que nenhum worker pode mudar (é do run, não da página).
# `dossie`/`dossie_sha256`: o worker recebe o SNAPSHOT do dossiê com a própria
# página reavaliada; o dossiê do run é consolidado do cache compartilhado
# (`CompiladorDeDossie`), não aplicado por delta.
_CAMPOS_DO_RUN = tuple(c for c in RunState.model_fields
                       if c not in CAMPOS_POR_PAGINA + ("step_status", "plan", "dossie",
                                                         "dossie_sha256"))


def chave_da_pagina(chave: str, numero: int) -> bool:
    """`write_p3`, `blocked_p3`, `budget_p3`, `page_3` — passos da página 3."""
    return chave.endswith(f"_p{numero}") or chave == f"page_{numero}"


def pasta_da_pagina(runs_dir: Path, run_id: str, numero: int) -> Path:
    return runs_dir / run_id / "paginas" / f"p{numero}"


class RunnerDaPagina(Runner):
    """O Runner que um worker vê. Mesma política de chamada e retry; estado e
    log global intocados."""

    def __init__(self, base: Runner, numero: int, llm: Any, budget: Any) -> None:
        super().__init__(llm, base.max_retries, base.runs_dir, budget=budget,
                         backoff_s=base.backoff_s, backoff_max_s=base.backoff_max_s,
                         sleep=base.sleep)
        self.numero = numero

    def _pasta(self, run_id: str) -> Path:
        d = pasta_da_pagina(self.runs_dir, run_id, self.numero)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def checkpoint(self, run_id: str, state_json: str) -> None:
        """O estado global só é gravado pelo consolidador."""

    def log(self, run_id: str, entry: dict) -> None:
        with (self._pasta(run_id) / "log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def snapshot_prompt(self, run_id: str, step: str, messages: list[dict]) -> None:
        d = self._pasta(run_id) / "prompts"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{step}.txt").write_text(
            "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages),
            encoding="utf-8")

    def finalize_run_id(self, old: str, new: str) -> None:
        raise RuntimeError("worker de página não renomeia o run")


class Serializado:
    """Um provedor sem garantia de thread-safety (Playwright síncrono, cache de
    sitemap) atrás de uma trava: uma chamada por vez, do worker que for."""

    def __init__(self, alvo: Any, trava: threading.Lock) -> None:
        self._alvo, self._trava = alvo, trava

    def __getattr__(self, nome: str) -> Any:
        valor = getattr(self._alvo, nome)
        if not callable(valor):
            return valor

        def chamada(*a, **kw):
            with self._trava:
                return valor(*a, **kw)
        return chamada


class ContadorDeChamadas:
    """Envolve o LLM para medir as chamadas EM VOO (pico real de concorrência)
    sem mudar nada do que passa por ele."""

    def __init__(self, llm: Any) -> None:
        self._llm = llm
        self._trava = threading.Lock()
        self.em_voo = self.pico = self.total = 0

    def complete(self, *a, **kw):
        with self._trava:
            self.em_voo += 1
            self.total += 1
            self.pico = max(self.pico, self.em_voo)
        try:
            return self._llm.complete(*a, **kw)
        finally:
            with self._trava:
                self.em_voo -= 1

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._llm, nome)


@dataclass
class DeltaDaPagina:
    """O StateDelta de uma página: só o que mudou, só nas chaves dela."""
    page_number: int
    campos: dict[str, dict[int, Any]] = field(default_factory=dict)   # valor None = removido
    passos: dict[str, StepResult | None] = field(default_factory=dict)
    pagina: Page | None = None
    publicar: bool = False
    sinal: str | None = None            # "break" = teto do run
    violacoes: list[str] = field(default_factory=list)
    erro: str = ""
    duracao_s: float = 0.0
    rodou: bool = True


_REMOVIDO = object()


def extrair_delta(antes: RunState, depois: RunState, page: Page, *, sinal: str | None,
                  publicar: bool, duracao_s: float) -> DeltaDaPagina:
    n = page.page_number
    delta = DeltaDaPagina(page_number=n, sinal=sinal, publicar=publicar,
                          duracao_s=duracao_s)
    for campo in CAMPOS_POR_PAGINA:
        a, d = getattr(antes, campo), getattr(depois, campo)
        for k in sorted(set(a) | set(d)):
            va, vd = a.get(k, _REMOVIDO), d.get(k, _REMOVIDO)
            if va == vd:
                continue
            if k == n:
                delta.campos.setdefault(campo, {})[k] = None if vd is _REMOVIDO else vd
            else:
                delta.violacoes.append(f"{campo}[{k}]")
    a, d = antes.step_status, depois.step_status
    for k in list(d) + [k for k in a if k not in d]:
        va, vd = a.get(k, _REMOVIDO), d.get(k, _REMOVIDO)
        if va == vd:
            continue
        if chave_da_pagina(k, n):
            delta.passos[k] = None if vd is _REMOVIDO else vd
        else:
            delta.violacoes.append(f"step_status[{k}]")
    for campo in _CAMPOS_DO_RUN:
        if getattr(antes, campo) != getattr(depois, campo):
            delta.violacoes.append(campo)
    pa = {p.page_number: p for p in (antes.plan.pages if antes.plan else [])}
    pd = {p.page_number: p for p in (depois.plan.pages if depois.plan else [])}
    for k in sorted(set(pa) | set(pd)):
        if k != n and pa.get(k) != pd.get(k):
            delta.violacoes.append(f"plan.pages[{k}]")
    if antes.plan is not None and depois.plan is not None and (
            antes.plan.model_dump(exclude={"pages"}) != depois.plan.model_dump(exclude={"pages"})):
        delta.violacoes.append("plan")
    delta.pagina = pd.get(n)
    return delta


def aplicar_delta(state: RunState, delta: DeltaDaPagina) -> Page | None:
    """Aplica o delta (só a parte da página) e devolve a página consolidada."""
    for campo, valores in delta.campos.items():
        destino = getattr(state, campo)
        for k, v in valores.items():
            if v is None:
                destino.pop(k, None)
            else:
                destino[k] = v
    for k, v in delta.passos.items():
        if v is None:
            state.step_status.pop(k, None)
        else:
            state.step_status[k] = v
    if delta.pagina is None or state.plan is None:
        return None
    for i, p in enumerate(state.plan.pages):
        if p.page_number == delta.page_number:
            state.plan.pages[i] = delta.pagina
            return delta.pagina
    return None


def ordem_serial(passos: dict[str, StepResult], antes: list[str]) -> dict[str, StepResult]:
    """Os passos que já existiam ficam onde estavam; os novos entram agrupados
    por página (estável dentro da página), que é a ordem do laço serial."""
    import re
    novos = [k for k in passos if k not in set(antes)]

    def pagina(k: str) -> int:
        m = re.search(r"(?:_p|^page_)(\d+)$", k)
        return int(m.group(1)) if m else 10 ** 6
    ordem = [k for k in antes if k in passos] + sorted(novos, key=pagina)
    return {k: passos[k] for k in ordem}


def fundir_artefatos(runs_dir: Path, run_id: str, numero: int) -> None:
    """Log da página -> fim do `log.jsonl` do run; prompts -> `prompts/`.
    Chamado em ordem de `page_number`, então o log consolidado tem a mesma
    ordem por página que o serial."""
    origem = pasta_da_pagina(runs_dir, run_id, numero)
    raiz = runs_dir / run_id
    raiz.mkdir(parents=True, exist_ok=True)
    log = origem / "log.jsonl"
    if log.exists():
        with (raiz / "log.jsonl").open("a", encoding="utf-8") as f:
            f.write(log.read_text(encoding="utf-8"))
    prompts = origem / "prompts"
    if prompts.is_dir():
        (raiz / "prompts").mkdir(exist_ok=True)
        for arq in sorted(prompts.glob("*.txt")):
            shutil.copyfile(arq, raiz / "prompts" / arq.name)
