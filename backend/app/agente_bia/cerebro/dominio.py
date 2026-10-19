"""Regras do cérebro pela web — sem I/O."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional

INTENCAO_RASCUNHO = "rascunho_cerebro"
TEXTO_PADRAO_RASCUNHO = "Preparar captura desta conversa para o cérebro."

#: Os três cérebros. A chave é o que circula; o repositório só existe no executor.
DESTINOS: Dict[str, str] = {
    "volc": "cerebro-volc",
    "arbitragem": "cerebro-arbitragem",
    "pessoal": "cerebro-pessoal",
}
TIPOS = ("decisao", "captura", "pendencia", "referencia", "nota")
MAX_TITULO = 120
MAX_CONTEUDO = 20_000
MAX_TAGS = 8

#: Os mesmos sinais que o `/salve` do Telegram recusa (SKILL.md, "Proteger segredos").
_SEGREDOS = re.compile(
    r"(ghp_[A-Za-z0-9]{8,}|github_pat_|\bsk-[A-Za-z0-9_-]{12,}|xox[abp]-|AKIA[0-9A-Z]{12,}"
    r"|BEGIN [A-Z ]*PRIVATE KEY|refresh_token|client_secret|password\s*=|passwd\s*=|token\s*=|api_key\s*="
    r"|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,})",
    re.I)


class CapturaRecusada(Exception):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(codigo)
        self.codigo = codigo
        self.mensagem = mensagem


def pedido_de_rascunho(observacao: str) -> str:
    """O que vai à Bia. Escrito pelo servidor; o navegador só manda a intenção."""
    obs = observacao.strip()
    nota = "" if not obs or obs == TEXTO_PADRAO_RASCUNHO else f"\n\nObservação do operador: {obs}"
    return (
        "Prepare uma CAPTURA desta conversa para o cérebro VOLC, no espírito da sua skill /salve, "
        "mas SEM salvar nada: aqui você não tem ferramentas. Quem grava é o servidor do VOLC, só "
        "depois de o Tarcisio revisar e confirmar.\n"
        "Responda SOMENTE com um bloco ```json contendo exatamente estas chaves:\n"
        '{"destino": "volc" | "arbitragem" | "pessoal", "titulo": "até 80 caracteres", '
        '"tipo": "decisao" | "captura" | "pendencia" | "referencia" | "nota", '
        '"resumo": "2 a 4 frases", "decisoes": ["…"], "aprendizados": ["…"], '
        '"pendencias": ["…"], "hipoteses": ["…"], "tags": ["…"]}\n'
        "Regras: separe DECISÃO (o que foi decidido) de HIPÓTESE (o que ainda é suposição); listas "
        "podem ser vazias; não copie o histórico inteiro nem o conteúdo bruto de anexos; nunca inclua "
        "token, senha, cookie, chave de API ou ID sensível de conta. Escolha o destino pelo mesmo "
        "roteamento do /salve (VOLC = operação/clientes/metodologia; arbitragem = publisher/tráfego/"
        "monetização; pessoal = estratégia, diretoria, identidade)." + nota)


@dataclass(frozen=True)
class Captura:
    destino: str
    titulo: str
    tipo: str
    conteudo: str
    tags: tuple


def _limpo(texto: str) -> str:
    texto = unicodedata.normalize("NFC", texto or "")
    return "".join(ch for ch in texto if ch in "\n\t" or (ord(ch) >= 32 and ord(ch) not in range(0x202A, 0x202F)
                                                         and ord(ch) not in range(0x2066, 0x206A)))


def validar_captura(destino: str, titulo: str, tipo: str, conteudo: str,
                    tags: Optional[List[str]] = None) -> Captura:
    if destino not in DESTINOS:
        raise CapturaRecusada("destino_invalido", "Destino precisa ser volc, arbitragem ou pessoal.")
    if tipo not in TIPOS:
        raise CapturaRecusada("tipo_invalido", "Tipo de captura inválido.")
    titulo = _limpo(titulo).replace("\n", " ").strip()
    conteudo = _limpo(conteudo).strip()
    if not titulo:
        raise CapturaRecusada("titulo_vazio", "Dê um título à captura.")
    if len(titulo) > MAX_TITULO:
        raise CapturaRecusada("titulo_grande", f"Título acima de {MAX_TITULO} caracteres.")
    if not conteudo:
        raise CapturaRecusada("conteudo_vazio", "A captura está vazia.")
    if len(conteudo) > MAX_CONTEUDO:
        raise CapturaRecusada("conteudo_grande", f"Captura acima de {MAX_CONTEUDO} caracteres.")
    if _SEGREDOS.search(conteudo) or _SEGREDOS.search(titulo):
        raise CapturaRecusada("parece_segredo",
                              "A captura parece conter segredo (token, senha ou chave). Tire isso e "
                              "guarde no cofre, não no cérebro.")
    limpas = []
    for t in (tags or [])[:MAX_TAGS]:
        t = unicodedata.normalize("NFKD", _limpo(t)).encode("ascii", "ignore").decode().lower()
        t = re.sub(r"[^a-z0-9-]", "", t.replace(" ", "-"))[:32]
        if t and t not in limpas:
            limpas.append(t)
    return Captura(destino, titulo, tipo, conteudo, tuple(limpas))
