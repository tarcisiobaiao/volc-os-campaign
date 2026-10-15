"""Regras da conversa da Bia. Sem framework, sem I/O.

## Estados de uma execução (um envio do usuário)

    queued ──► running ──► succeeded
                  │  └───► failed       (o Hermes RESPONDEU com erro antes de agir)
                  └──────► uncertain    (timeout, conexão caída, resposta ilegível)
    queued ──► cancelled                 (só antes de sair para o Hermes)
    uncertain ──► succeeded | failed     (só por reconciliação com read-back)

⚠️ Timeout é `uncertain`, nunca `cancelled` nem `failed`. O API Server do Hermes
não cancela o turno quando o cliente desiste: o agente pode ter respondido (e
gravado na sessão) depois que paramos de esperar. Dizer "cancelado" seria
afirmar algo que não sabemos.

⚠️ `uncertain` nunca é reenviado automaticamente. A única saída é a
reconciliação, que LÊ a sessão no Hermes e não chama o modelo de novo.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from enum import Enum
from typing import FrozenSet, Mapping, Optional


class Estado(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    CANCELLED = "cancelled"


TERMINAIS: FrozenSet[Estado] = frozenset({Estado.SUCCEEDED, Estado.FAILED, Estado.CANCELLED})
EM_VOO: FrozenSet[Estado] = frozenset({Estado.QUEUED, Estado.RUNNING})

#: Transições permitidas. A mesma tabela está no banco (v27_01), que é quem
#: manda; esta cópia existe para a aplicação recusar ANTES de ir à rede.
TRANSICOES: Mapping[Estado, FrozenSet[Estado]] = {
    Estado.QUEUED: frozenset({Estado.RUNNING, Estado.CANCELLED}),
    Estado.RUNNING: frozenset({Estado.SUCCEEDED, Estado.FAILED, Estado.UNCERTAIN}),
    Estado.UNCERTAIN: frozenset({Estado.SUCCEEDED, Estado.FAILED}),
    Estado.SUCCEEDED: frozenset(),
    Estado.FAILED: frozenset(),
    Estado.CANCELLED: frozenset(),
}


def transicao_valida(de: Estado, para: Estado) -> bool:
    return para in TRANSICOES.get(de, frozenset())


# ── limites ────────────────────────────────────────────────────────────────

#: Teto absoluto do texto de entrada. A configuração pode baixar, nunca subir.
MAX_ENTRADA_ABSOLUTO = 8000
#: Teto da resposta guardada e devolvida. Acima disso, corta e marca.
MAX_RESPOSTA = 20000


class EntradaInvalida(ValueError):
    """Mensagem vazia, grande demais ou com caractere de controle."""


_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalizar_entrada(texto: str, *, limite: int) -> str:
    """Texto pronto para o ledger e para o Hermes, ou `EntradaInvalida`.

    NFC para que o mesmo texto digitado de duas formas tenha o mesmo hash de
    idempotência. Controle (exceto \\n e \\t) é recusado, não removido: um
    NUL no meio do texto é sinal de cliente quebrado ou de injeção, e consertar
    em silêncio esconderia os dois.
    """
    if not isinstance(texto, str):
        raise EntradaInvalida("mensagem precisa ser texto")
    t = unicodedata.normalize("NFC", texto)
    if not t.strip():
        raise EntradaInvalida("mensagem vazia")
    teto = min(int(limite), MAX_ENTRADA_ABSOLUTO)
    if len(t) > teto:
        raise EntradaInvalida(f"mensagem com {len(t)} caracteres; o limite é {teto}")
    if _CONTROLE.search(t):
        raise EntradaInvalida("mensagem com caractere de controle")
    return t


def impressao_da_entrada(texto: str, contexto: Optional[Mapping[str, object]] = None) -> str:
    """sha256 do PEDIDO: texto normalizado + contexto canônico.

    É o que decide "mesmo pedido" na idempotência. O contexto entra: o mesmo
    texto sobre outra campanha (ou outra janela) é outro pedido, e o mesmo
    request_id com ele é conflito — nunca a resposta da campanha anterior.
    """
    canonico = json.dumps({"entrada": texto, "contexto": dict(contexto) if contexto else None},
                          ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


# ── filtro de resposta ─────────────────────────────────────────────────────
#
# A resposta do Hermes é texto de um modelo que pode ter lido qualquer coisa.
# Ela volta ao navegador como TEXTO (o front nunca renderiza HTML), mas antes
# disso passa por aqui: segredo com cara de segredo vira marcador, e o id da
# sessão Hermes — que é nosso e não do usuário — nunca sai.

_SEGREDOS = (
    # JWT (inclui access token do Supabase e service_role)
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    # Bearer <token>
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    # chaves de provedores comuns
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    # atribuições óbvias: API_SERVER_KEY=..., service_role_key: ...
    re.compile(r"(?i)\b[A-Z0-9_]*(?:KEY|SECRET|SERVICE_ROLE|PASSWORD|PASSWD|TOKEN)\b\s*[:=]\s*\S{8,}"),
)
_SESSAO_HERMES = re.compile(r"\bvolc_[0-9a-f]{32}\b")
MARCADOR_SEGREDO = "[removido: parecia credencial]"
MARCADOR_SESSAO = "[sessão interna]"
MARCADOR_CORTE = "\n\n[resposta cortada no limite de exibição]"


def filtrar_resposta(texto: Optional[str]) -> str:
    """Texto seguro para guardar e devolver. Nunca levanta."""
    if not isinstance(texto, str):
        return ""
    t = unicodedata.normalize("NFC", texto)
    t = _CONTROLE.sub("", t)
    for padrao in _SEGREDOS:
        t = padrao.sub(MARCADOR_SEGREDO, t)
    t = _SESSAO_HERMES.sub(MARCADOR_SESSAO, t)
    if len(t) > MAX_RESPOSTA:
        t = t[:MAX_RESPOSTA] + MARCADOR_CORTE
    return t


# ── erros sanitizados ──────────────────────────────────────────────────────
#
# O que vai para o usuário e para o ledger é um CÓDIGO da lista abaixo, nunca
# a mensagem do upstream: erro do Hermes pode carregar caminho de arquivo,
# trecho de prompt ou nome de ferramenta.

CODIGOS_DE_ERRO: Mapping[str, str] = {
    "hermes_timeout": "O Hermes não respondeu dentro do prazo. O resultado é incerto.",
    "hermes_conexao": "A conexão com o Hermes caiu durante o envio. O resultado é incerto.",
    "hermes_resposta_ilegivel": "O Hermes respondeu fora do contrato. O resultado é incerto.",
    "hermes_recusou": "O Hermes recusou o pedido antes de executá-lo.",
    "hermes_autenticacao": "O backend não foi aceito pelo Hermes (chave do profile).",
    "hermes_indisponivel": "O Hermes está indisponível.",
    "hermes_sessao_ausente": "A sessão desta conversa não existe mais no Hermes.",
    "processo_interrompido": "O backend reiniciou durante o envio. O resultado é incerto.",
    "contexto_indisponivel": "O contexto VOLC pedido não pôde ser lido.",
    "hermes_com_ferramentas": "O profile do Hermes expõe ferramentas; a Bia V1 recusa enviar.",
}


def mensagem_de_erro(codigo: Optional[str]) -> Optional[str]:
    if not codigo:
        return None
    return CODIGOS_DE_ERRO.get(codigo, "Falha sem detalhe público.")


AVISO_MODO_CONSULTA = "Bia em modo de consulta — nenhuma ação operacional será executada."
