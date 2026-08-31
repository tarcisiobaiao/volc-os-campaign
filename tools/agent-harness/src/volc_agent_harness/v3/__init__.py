"""Harness V3 — compilação de missão, ledger de evidência e ratchet de recuperação.

Cinco das nove execuções da rodada anterior falharam por especificação, e nenhuma
por infraestrutura. O writer é o recurso caro; descobrir um gate quebrado depois
de 39 minutos dele é o defeito que este pacote existe para tornar impossível.
"""

from .failures import FailureClass, HarnessFailure, classify_gate_exit, classify_exception

__all__ = ["FailureClass", "HarnessFailure", "classify_gate_exit", "classify_exception"]
