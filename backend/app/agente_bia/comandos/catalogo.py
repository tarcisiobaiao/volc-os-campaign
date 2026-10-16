"""Catálogo versionado dos comandos `/`: cada comando real do Hermes, classificado.

Classes (fechadas):

- `local_ui`        executado só pelo VOLC (front/backend), sem comando no Hermes;
- `hermes_safe`     poderia rodar na sessão web sem ferramenta nem mutação externa;
- `requires_tool`   depende de ferramenta, que a superfície web não tem;
- `external_mutation` altera algo fora da conversa (config do profile — que é
                    a mesma do Telegram —, memória, skills, jobs, gateway, conta);
- `telegram_only`   pertence ao canal de mensagens, ou lê dado de outras superfícies.

Disponibilidade na web é OUTRA pergunta: só `disponivel=True` vira executável na
interface, e só para `execucao in ("local", "backend")`. Nada aqui habilita
toolset; nenhum comando é repassado ao agente como texto.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

INVENTARIO = Path(__file__).with_name("inventario_hermes_v0_18_0.json")
VERSAO_HERMES = "0.18.0"

LOCAL, SAFE, TOOL, MUTA, TELEGRAM = "local_ui", "hermes_safe", "requires_tool", "external_mutation", "telegram_only"


@dataclass(frozen=True)
class ComandoWeb:
    """Comando executável na web. `execucao`: local (front) ou backend (rota tipada)."""
    nome: str
    descricao: str
    args: str
    execucao: str
    equivalentes_hermes: Tuple[str, ...]


#: O que a web oferece. Nomes em português; o equivalente no Hermes fica registrado.
COMANDOS_WEB: Tuple[ComandoWeb, ...] = (
    ComandoWeb("nova", "Abrir uma nova conversa, isolada da atual", "", "local", ("new", "clear")),
    ComandoWeb("conversas", "Ver e retomar suas conversas recentes", "", "local", ("history", "sessions", "resume")),
    ComandoWeb("anexar", "Escolher imagem ou documento para enviar", "", "local", ("image", "paste")),
    ComandoWeb("copiar", "Copiar a última resposta da Bia", "", "local", ("copy",)),
    ComandoWeb("contexto", "Incluir o contexto somente leitura de uma campanha", "<id da campanha>", "local", ()),
    ComandoWeb("status", "Ver o estado da conversa: mensagens, tokens, custo e versão do Hermes", "",
               "backend", ("status", "usage", "version")),
    ComandoWeb("ajuda", "Listar os comandos disponíveis e indisponíveis", "", "local", ("help", "commands")),
    ComandoWeb("cerebro", "Status dos três cérebros (só leitura: git, sem sincronizar)", "", "backend", ()),
    ComandoWeb("salvar", "Preparar uma captura desta conversa para o cérebro, com prévia antes de gravar",
               "", "local", ()),
)

#: Skills do Hermes com equivalente seguro na web (o resto das skills fica bloqueado).
EQUIVALENTES_DE_SKILL: Dict[str, str] = {
    "salve": "salvar",
    "cerebro": "cerebro",
}

#: Classe e motivo de cada comando do registro do Hermes. Ausente aqui = recusa
#: por padrão (nenhum comando novo de uma versão futura vira executável sozinho).
CLASSIFICACAO: Dict[str, Tuple[str, str]] = {
    # sessão — com equivalente local na web
    "new": (LOCAL, "Na web, nova conversa é do VOLC: /nova."),
    "clear": (LOCAL, "Na web, equivale a /nova."),
    "history": (LOCAL, "Na web, o histórico é o do VOLC: /conversas."),
    "sessions": (LOCAL, "No Hermes lista sessões de todas as superfícies; na web, /conversas lista só as suas."),
    "resume": (LOCAL, "Na web, retome pela lista de /conversas."),
    "help": (LOCAL, "Na web: /ajuda."),
    "commands": (LOCAL, "Na web: /ajuda."),
    "copy": (LOCAL, "Na web: /copiar."),
    "image": (LOCAL, "Na web: /anexar ou o botão de anexo."),
    "paste": (LOCAL, "Na web: cole a imagem no campo de mensagem."),
    # leitura da sessão — executada pelo backend do VOLC
    "status": (SAFE, "Na web: /status (só leitura, sessão desta conversa)."),
    "usage": (SAFE, "Na web: /status (tokens e custo desta conversa)."),
    "version": (SAFE, "Na web: /status (inclui a versão do Hermes)."),
    "profile": (SAFE, "Leitura inofensiva, mas o API Server não expõe o profile; fora da V1."),
    # sessão — seguros por natureza, mas fora da V1 web
    "title": (SAFE, "Títulos da web são do VOLC; fora da V1."),
    "compress": (SAFE, "Reescreve o histórico da sessão com outro modelo; fora da V1."),
    "undo": (SAFE, "Desfazer turnos conflita com o ledger e o recibo; fora da V1."),
    "branch": (SAFE, "Ramificar conflita com o ledger da conversa; fora da V1."),
    "retry": (SAFE, "Bloqueado por política: nada é reenviado sem uma nova mensagem sua."),
    # dependem de ferramenta ou de agente em segundo plano
    "background": (TOOL, "Roda o agente em segundo plano com ferramentas."),
    "queue": (TOOL, "Enfileira turnos fora do recibo do VOLC."),
    "steer": (TOOL, "Injeta mensagem depois de uma chamada de ferramenta."),
    "goal": (TOOL, "Meta permanente executada pelo agente com ferramentas."),
    "subgoal": (TOOL, "Critério de meta permanente."),
    "moa": (TOOL, "Mistura de agentes; custo e ferramentas fora da superfície web."),
    "learn": (TOOL, "Aprende skill lendo diretórios e URLs."),
    "rollback": (TOOL, "Restaura checkpoints de arquivos."),
    "stop": (TOOL, "Mata processos em segundo plano."),
    "agents": (TOOL, "Lista agentes e tarefas do gateway inteiro."),
    "tools": (TOOL, "Gerencia ferramentas (terminal)."),
    "toolsets": (TOOL, "Lista toolsets (terminal)."),
    "browser": (TOOL, "Conecta ferramentas de navegador."),
    "cron": (TOOL, "Agenda tarefas com ferramentas."),
    "journey": (TOOL, "Linha do tempo de aprendizado (terminal)."),
    # mudam algo fora da conversa — o profile é o MESMO do Telegram
    "model": (MUTA, "Troca o modelo do profile, que é o mesmo do Telegram."),
    "codex-runtime": (MUTA, "Muda o runtime do provider do profile."),
    "personality": (MUTA, "Muda a personalidade do profile (afeta o Telegram)."),
    "footer": (MUTA, "Muda a configuração do gateway."),
    "yolo": (MUTA, "Desliga aprovações de comandos perigosos."),
    "reasoning": (MUTA, "Muda o esforço de raciocínio do profile."),
    "fast": (MUTA, "Muda o modo de prioridade do provider."),
    "voice": (MUTA, "Muda o modo de voz do profile."),
    "memory": (MUTA, "Aprova ou altera gravações de memória longa compartilhada."),
    "skills": (MUTA, "Instala ou altera skills do profile."),
    "bundles": (MUTA, "Pacotes de skills do profile."),
    "curator": (MUTA, "Manutenção de skills em segundo plano."),
    "kanban": (MUTA, "Quadro compartilhado entre profiles."),
    "suggestions": (MUTA, "Aceita automações sugeridas."),
    "blueprint": (MUTA, "Cria automação a partir de modelo."),
    "reload-mcp": (MUTA, "Recarrega servidores MCP do profile."),
    "reload-skills": (MUTA, "Recarrega skills do profile."),
    "reload": (MUTA, "Recarrega variáveis de ambiente."),
    "restart": (MUTA, "Reinicia o gateway — derruba o Telegram."),
    "update": (MUTA, "Atualiza o Hermes."),
    "debug": (MUTA, "Envia logs para fora do servidor."),
    "credits": (MUTA, "Conta de créditos do provedor."),
    "billing": (MUTA, "Cobrança do provedor (terminal)."),
    "config": (MUTA, "Configuração do profile (terminal)."),
    "snapshot": (MUTA, "Cria ou restaura estado do Hermes (terminal)."),
    "statusbar": (MUTA, "Interface do terminal."),
    "timestamps": (MUTA, "Interface do terminal."),
    "verbose": (MUTA, "Exibição de progresso do gateway."),
    "skin": (MUTA, "Tema do terminal."),
    "indicator": (MUTA, "Indicador do terminal."),
    "busy": (MUTA, "Comportamento do terminal."),
    "pet": (MUTA, "Mascote do terminal."),
    "hatch": (MUTA, "Gera mascote (terminal)."),
    "plugins": (MUTA, "Plugins do profile (terminal)."),
    "redraw": (MUTA, "Interface do terminal."),
    "save": (MUTA, "Salva conversa em arquivo (terminal)."),
    "prompt": (MUTA, "Abre editor no servidor (terminal)."),
    "quit": (MUTA, "Encerra a CLI."),
    # canal de mensagens
    "start": (TELEGRAM, "Ping de início de plataforma de mensagens."),
    "topic": (TELEGRAM, "Tópicos de DM do Telegram."),
    "approve": (TELEGRAM, "Aprovação de comando perigoso no canal."),
    "deny": (TELEGRAM, "Negação de comando perigoso no canal."),
    "sethome": (TELEGRAM, "Canal principal do Telegram."),
    "platform": (TELEGRAM, "Pausa ou retoma plataforma de mensagens."),
    "platforms": (TELEGRAM, "Estado das plataformas de mensagens (terminal)."),
    "whoami": (TELEGRAM, "Nível de acesso no canal; na web, quem decide é o papel do VOLC."),
    "insights": (TELEGRAM, "Lê sessões de todas as superfícies, inclusive o Telegram."),
    "handoff": (TELEGRAM, "Passa a sessão para uma plataforma de mensagens."),
}

MOTIVO_SKILL = ("Skill do Hermes: na web não roda — a superfície web não carrega skills "
                "nem tem ferramentas. Use pelo Telegram.")


@dataclass(frozen=True)
class EntradaDoCatalogo:
    nome: str
    descricao: str
    args: str
    origem: str               # volc | hermes_registro | hermes_skill
    classe: str
    disponivel: bool
    execucao: Optional[str]   # local | backend | None
    motivo: str
    equivalente_web: Optional[str] = None
    aliases: Tuple[str, ...] = field(default_factory=tuple)
    superficies_hermes: Tuple[str, ...] = field(default_factory=tuple)

    def publico(self) -> Dict[str, object]:
        return asdict(self)


@lru_cache(maxsize=1)
def _inventario() -> Dict[str, list]:
    return json.loads(INVENTARIO.read_text(encoding="utf-8"))


def _equivalente(nome_hermes: str) -> Optional[str]:
    for c in COMANDOS_WEB:
        if nome_hermes in c.equivalentes_hermes:
            return c.nome
    return None


@lru_cache(maxsize=1)
def catalogo() -> Tuple[EntradaDoCatalogo, ...]:
    saida: List[EntradaDoCatalogo] = []
    for c in COMANDOS_WEB:
        classe = SAFE if c.execucao == "backend" else LOCAL
        saida.append(EntradaDoCatalogo(
            nome=c.nome, descricao=c.descricao, args=c.args, origem="volc", classe=classe,
            disponivel=True, execucao=c.execucao,
            motivo=("Executado pelo backend do VOLC, só leitura." if c.execucao == "backend"
                    else "Executado pela interface do VOLC."),
            aliases=tuple(f"/{a}" for a in c.equivalentes_hermes)))
    inv = _inventario()
    for r in inv["registro"]:
        classe, motivo = CLASSIFICACAO.get(r["name"], (MUTA, "Comando novo, ainda não classificado: recusado por padrão."))
        superficies = ("cli",) if r["cli_only"] else ("gateway",) if r["gateway_only"] else ("cli", "gateway")
        saida.append(EntradaDoCatalogo(
            nome=r["name"], descricao=r["description"], args=r["args_hint"] or "",
            origem="hermes_registro", classe=classe, disponivel=False, execucao=None, motivo=motivo,
            equivalente_web=_equivalente(r["name"]), aliases=tuple(r.get("aliases") or ()),
            superficies_hermes=superficies))
    for s in inv["skills"]:
        equivalente = EQUIVALENTES_DE_SKILL.get(s["name"])
        motivo = (f"No Telegram a skill escreve e faz git com ferramentas. Na web: /{equivalente}, "
                  "sem ferramenta para a Bia." if equivalente else MOTIVO_SKILL)
        saida.append(EntradaDoCatalogo(
            nome=s["name"], descricao="Skill do Hermes", args="", origem="hermes_skill", classe=TOOL,
            disponivel=False, execucao=None, motivo=motivo, equivalente_web=equivalente,
            superficies_hermes=("cli", "gateway")))
    return tuple(saida)


def procurar(nome: str) -> Optional[EntradaDoCatalogo]:
    """Entrada pelo nome (sem barra). Comando web vence nome igual do Hermes."""
    nome = (nome or "").lstrip("/").strip().lower()
    for e in catalogo():
        if e.nome == nome:
            return e
    return None


def classes_contagem() -> Dict[str, int]:
    contagem: Dict[str, int] = {}
    for e in catalogo():
        if e.origem != "volc":
            contagem[e.classe] = contagem.get(e.classe, 0) + 1
    return contagem
