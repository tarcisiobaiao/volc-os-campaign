"""A porta HTTP da bancada, e o unico lugar que decide ONDE o trabalho roda.

⚠️ A escolha do despachante e uma decisao de ambiente, nao de dominio. Hoje ha
um so: o local, sincrono, que roda no mesmo processo. Ele NAO e producao e a
diferenca esta declarada em `DespachanteLocal`. Quando Cloud Run Job ou worker
permanente entrarem, entram aqui — e `Encomenda`, `Recibo` e `MotorDeProducao`
nao mudam uma linha.

## Por que ha um singleton aqui, se o executor existe para nao ter singleton

Porque este e o singleton do PROCESSO (qual fila, qual pasta), nao do TRABALHO.
O que nao pode ser compartilhado e estado mutavel de execucao: diretorio,
semente, arquivo intermediario. Cada trabalho continua com o seu.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from .adaptadores.tipografico import MotorTipografico
from .contrato import FalhaDoMotor
from .deposito import DepositoDeTrabalhos
from .operario import DespachanteLocal, Operario, Reaper

_TRAVA = threading.Lock()
_BANCADA: tuple[DepositoDeTrabalhos, Operario, DespachanteLocal] | None = None
_REAPER: Reaper | None = None


def raiz_da_bancada() -> Path:
    """Onde a fila e os diretorios de trabalho vivem.

    ⚠️ Sem caminho absoluto embutido. `CRIATIVO_BANCADA_DIR` manda; sem ela, cai
    para `~/.volc-os/bancada`, que e a mesma familia de caminho que o
    `ArmazenamentoLocal` ja usa.
    """
    do_ambiente = os.environ.get("CRIATIVO_BANCADA_DIR")
    if do_ambiente:
        return Path(do_ambiente)
    return Path.home() / ".volc-os" / "bancada"


def montar() -> tuple[DepositoDeTrabalhos, Operario, DespachanteLocal]:
    global _BANCADA
    with _TRAVA:
        if _BANCADA is not None:
            return _BANCADA
        raiz = raiz_da_bancada()
        raiz.mkdir(parents=True, exist_ok=True)
        deposito = DepositoDeTrabalhos(raiz / "fila.db")

        motores: dict[str, Any] = {}
        # ⚠️ Um motor que nao consegue nascer NAO derruba a bancada, e tambem nao
        # e silenciado: ele simplesmente nao entra no registro, e um trabalho que
        # o pedir falha com `motor_desconhecido`, que e legivel. Registrar um
        # motor quebrado seria pior: a falha apareceria no meio do render.
        try:
            motores["tipografico-local"] = MotorTipografico()
        except FalhaDoMotor:
            pass

        operario = Operario(deposito, motores, raiz / "trabalhos")
        _BANCADA = (deposito, operario, DespachanteLocal(operario))
        return _BANCADA


def iniciar_reaper(*, intervalo_s: float = 10.0) -> Reaper:
    """Liga o coletor de leases vencidos. Idempotente."""
    global _REAPER
    with _TRAVA:
        if _REAPER is not None and _REAPER.vivo:
            return _REAPER
        deposito, _, _ = montar()
        _REAPER = Reaper(deposito, intervalo_s=intervalo_s).iniciar()
        return _REAPER


def parar_reaper() -> None:
    global _REAPER
    with _TRAVA:
        if _REAPER is not None:
            _REAPER.parar()
            _REAPER = None


def motores_disponiveis() -> list[dict[str, Any]]:
    """Quais motores esta maquina consegue rodar AGORA.

    Isto e diferente de `criativo_motor`, que diz quais motores existem no
    patrimonio. A tela precisa dos dois: um motor registrado que esta maquina nao
    consegue rodar nao pode oferecer botao de render.
    """
    _, operario, _ = montar()
    saida = []
    for slug, motor in sorted(operario.motores.items()):
        saida.append(
            {
                "slug": slug,
                "versao": getattr(motor, "versao", None),
                "versoes": motor.versoes_congeladas(),
                "produz": ["imagem"],
            }
        )
    return saida
