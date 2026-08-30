"""Reinício do backend NÃO pode matar um run que está vivo.

## O defeito, encontrado em produção

O motor roda como processo SEPARADO — de propósito, para não levar a API junto
quando estoura, e para poder ter timeout e cancelamento. A consequência é que
ele **sobrevive** a um reinício do backend.

A primeira versão da reconciliação não sabia disso: ela olhava o dicionário
`_em_execucao` (que é memória do processo do backend e nasce vazio depois de um
reload) e concluía que todo run aberto estava órfão.

Aconteceu de verdade no primeiro run real, às 18:08 de 17/08/2026. Salvei um
arquivo, o `uvicorn --reload` recarregou, a reconciliação rodou, e a linha do
run virou `failed` com "O backend foi reiniciado" — enquanto o PID 30389 seguia
escrevendo em `runs/cartao-credito-negativado-20260817-180844/` e gastando.

Um run declarado morto enquanto gasta é a pior combinação possível: a tela para
de acompanhar, o operador acha que não custou nada, e o dinheiro sai assim mesmo.
"""
from __future__ import annotations

import asyncio
import os

from app.redator import worker


class _SupaFalso:
    def __init__(self, linhas):
        self.linhas = linhas
        self.patches: list[dict] = []

    async def patch(self, tabela, match, valores):
        self.patches.append({"match": match, **valores})
        return []

    async def select(self, tabela, params):
        return list(self.linhas)


def test_run_com_processo_vivo_nao_e_fechado():
    """O caso real: backend reiniciou, motor continua rodando."""
    meu_pid = os.getpid()          # garantidamente vivo
    supa = _SupaFalso([{"id": 3, "status": "running", "artefatos": {"pid": meu_pid}}])

    n = asyncio.run(worker.reconciliar(supa))

    assert n == 0, "fechou um run cujo processo está vivo"
    assert supa.patches == [], "não pode nem tocar na linha"


def test_run_com_processo_morto_e_fechado():
    """PID que não existe mais = órfão de verdade. Fechar é o certo, senão o
    card fica preso: o disparo recusa novo run enquanto houver um aberto."""
    supa = _SupaFalso([{"id": 4, "status": "running", "artefatos": {"pid": 999999}}])

    n = asyncio.run(worker.reconciliar(supa))

    assert n == 1
    assert supa.patches[0]["status"] == "failed"
    assert "reiniciado" in supa.patches[0]["erro"]


def test_run_sem_pid_gravado_e_tratado_como_orfao():
    """Linha antiga, de antes de o PID passar a ser gravado. Sem informação,
    o certo é fechar — deixar aberta prenderia o card para sempre."""
    supa = _SupaFalso([{"id": 5, "status": "queued", "artefatos": {}}])

    assert asyncio.run(worker.reconciliar(supa)) == 1


def test_pid_invalido_nao_explode():
    """`artefatos` é jsonb livre; um valor lixo ali não pode derrubar a subida
    da API, que é quando a reconciliação roda."""
    for lixo in ("abc", None, {"a": 1}, -1):
        supa = _SupaFalso([{"id": 6, "status": "running", "artefatos": {"pid": lixo}}])
        assert asyncio.run(worker.reconciliar(supa)) == 1


def test_processo_vivo_de_outro_dono_conta_como_vivo():
    """PermissionError significa que o PID EXISTE e é de outro usuário.
    Tratar como morto seria declarar morto quem está gastando."""
    assert worker._processo_vivo(1) is True      # init/launchd, sempre vivo
