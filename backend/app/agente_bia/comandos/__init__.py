"""Comandos `/` da Bia na web: inventário real do Hermes + classificação + execução allowlisted.

Medido no Hermes v0.18.0 (15/10/2026, somente leitura): 82 comandos no
registro canônico (`hermes_cli/commands.py::COMMAND_REGISTRY`) e 48 comandos de
skill (`agent/skill_commands.get_skill_commands`). A superfície `api_server`
NÃO interpreta `/`: texto com barra iria ao modelo como prompt. Por isso a web
nunca repassa `/…` ao agente; só os comandos desta lista rodam, por contrato
tipado (`POST /api/agent/comandos/{nome}`) ou localmente no front.
"""
