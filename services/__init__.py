"""Runtimes separáveis do VOLC O.S.

Cada subpacote aqui é um serviço que HOJE roda no processo do backend e que foi
desenhado para sair dele sem reescrita: a fronteira é um contrato de job, não
uma chamada de função. Ver `docs/creative-engines/ADR-001-SERVICO-CRIATIVO-VOLC.md`.
"""
