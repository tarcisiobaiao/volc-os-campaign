"""CREDENCIAL OpenAI do motor: API key (de sempre) ou plano ChatGPT (OAuth).

O perfil OAuth do VOLC é DESTE app: nunca se lê `~/.codex/auth.json`, token de
outro cliente, cookie de navegador nem `.env` inteiro.

Armazenamento:
- `ArmazemKeychain` (preferido no macOS): item genérico do Keychain via
  `security`. Limite conhecido: `security add-generic-password -w <valor>`
  recebe o valor por argumento, visível por instantes na tabela de processos
  do próprio usuário. Aceito para máquina de uso pessoal; o arquivo abaixo não
  tem esse limite.
- `ArmazemEmArquivo`: diretório 700 e arquivo 600 FORA do repositório, escrita
  atômica (temporário + `os.replace`).

Renovação: uma trava de arquivo (`fcntl.flock`) impede dois processos de
renovar ao mesmo tempo. Quem pega a trava RELÊ o perfil antes de renovar —
outro processo pode ter acabado de girar o refresh token.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Callable, Iterator, Protocol

from funnelforge.adapters.chatgpt_oauth import (
    ESCOPO_DO_PLANO,
    EscopoAusente,
    Post,
    SessaoExpirada,
    TokenSet,
    _post_httpx,
    renovar,
)

#: Renova quando faltar menos que isto para expirar (o access token vale 1 h).
MARGEM_DE_RENOVACAO_S = 120.0
SERVICO_KEYCHAIN = "volc-funnelforge.chatgpt"
CONTA_KEYCHAIN = "perfil-oauth"


def diretorio_padrao() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "volc-funnelforge"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "volc-funnelforge"


def _raiz_do_repo() -> Path:
    return Path(__file__).resolve().parents[5]


def _garantir_diretorio(pasta: Path) -> Path:
    pasta = pasta.expanduser().resolve()
    raiz = _raiz_do_repo()
    if pasta == raiz or raiz in pasta.parents:
        raise RuntimeError(f"o perfil OAuth não pode ficar dentro do repositório ({pasta}).")
    pasta.mkdir(parents=True, exist_ok=True)
    os.chmod(pasta, 0o700)
    return pasta


class Armazem(Protocol):
    def ler(self) -> dict | None: ...
    def gravar(self, dados: dict) -> None: ...
    def apagar(self) -> None: ...


class ArmazemEmArquivo:
    nome = "arquivo"

    def __init__(self, pasta: Path | None = None) -> None:
        self.pasta = _garantir_diretorio(pasta or diretorio_padrao())
        self.caminho = self.pasta / "perfil-chatgpt.json"

    def ler(self) -> dict | None:
        if not self.caminho.exists():
            return None
        return json.loads(self.caminho.read_text(encoding="utf-8"))

    def gravar(self, dados: dict) -> None:
        temporario = self.pasta / f".perfil-{uuid.uuid4().hex}.tmp"
        fd = os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(dados, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporario, self.caminho)
        finally:
            if temporario.exists():
                temporario.unlink()
        os.chmod(self.caminho, 0o600)

    def apagar(self) -> None:
        if self.caminho.exists():
            self.caminho.unlink()


class ArmazemKeychain:
    nome = "keychain"

    def __init__(self, executar: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                 servico: str = SERVICO_KEYCHAIN, conta: str = CONTA_KEYCHAIN) -> None:
        self._run, self.servico, self.conta = executar, servico, conta

    def _security(self, *args: str) -> subprocess.CompletedProcess:
        return self._run(["security", *args], capture_output=True, text=True, check=False)

    def ler(self) -> dict | None:
        r = self._security("find-generic-password", "-s", self.servico, "-a", self.conta, "-w")
        if r.returncode != 0:
            return None
        return json.loads(r.stdout.strip())

    def gravar(self, dados: dict) -> None:
        # `-U` atualiza o item no lugar: a troca é atômica para quem lê.
        r = self._security("add-generic-password", "-U", "-s", self.servico,
                           "-a", self.conta, "-w", json.dumps(dados))
        if r.returncode != 0:
            raise RuntimeError("não foi possível gravar o perfil no Keychain "
                               f"(security saiu com {r.returncode}).")

    def apagar(self) -> None:
        self._security("delete-generic-password", "-s", self.servico, "-a", self.conta)


def armazem_padrao(tipo: str = "keychain") -> Armazem:
    if tipo == "keychain" and sys.platform == "darwin":
        return ArmazemKeychain()
    return ArmazemEmArquivo()


@contextlib.contextmanager
def trava_de_renovacao(pasta: Path | None = None) -> Iterator[None]:
    pasta = _garantir_diretorio(pasta or diretorio_padrao())
    caminho = pasta / "renovacao.lock"
    with open(caminho, "a", encoding="utf-8") as f:
        os.chmod(caminho, 0o600)
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def id_do_host(pasta: Path | None = None) -> str:
    """O `ext_agent_host_id` deste host, no formato do exemplo oficial
    (`urn:uuid:<UUID>`): gerado UMA vez e reutilizado. Não é segredo.

    Um valor antigo `volc-<hex>` (recusado pelo provedor como
    `invalid_authorize_request`) é convertido para o MESMO UUID em formato URN,
    para o host continuar com uma identidade estável."""
    pasta = _garantir_diretorio(pasta or diretorio_padrao())
    caminho = pasta / "host-id"
    atual = caminho.read_text(encoding="utf-8").strip() if caminho.exists() else ""
    if atual.startswith("volc-"):
        atual = uuid.UUID(hex=atual.removeprefix("volc-")).urn
    if not atual:
        atual = uuid.uuid4().urn
    caminho.write_text(atual, encoding="utf-8")
    os.chmod(caminho, 0o600)
    return atual


class ApiKeyCredentialProvider:
    """O modo de sempre. A API key segue no ambiente para o LiteLLM; este
    provedor só existe para o modo ser declarado e exibido."""
    modo = "api_key"

    def status(self) -> dict:
        return {"modo": self.modo, "conectado": bool(os.environ.get("OPENAI_API_KEY")),
                "cobranca": "API faturada"}


class ChatGPTPlanCredentialProvider:
    modo = "chatgpt_plan"

    def __init__(self, armazem: Armazem, *, pasta_da_trava: Path | None = None,
                 post: Post = _post_httpx, agora: Callable[[], float] = time.time) -> None:
        self.armazem, self._pasta, self._post, self._agora = armazem, pasta_da_trava, post, agora

    def _carregar(self) -> TokenSet:
        dados = self.armazem.ler()
        if not dados:
            raise SessaoExpirada("não há sessão do ChatGPT neste host: rode "
                                 "`funnelforge auth login --provider chatgpt`.")
        token = TokenSet.from_dict(dados)
        if not token.tem_escopo_do_plano():
            raise EscopoAusente(f"a sessão salva não tem '{ESCOPO_DO_PLANO}'. Refaça o login.")
        return token

    def _precisa_renovar(self, token: TokenSet) -> bool:
        agora = self._agora()
        if token.expira_em(agora) > MARGEM_DE_RENOVACAO_S:
            return False
        return token.earliest_refresh_at is None or agora >= token.earliest_refresh_at \
            or token.expira_em(agora) <= 0

    def access_token(self, *, forcar_renovacao: bool = False) -> str:
        token = self._carregar()
        if not forcar_renovacao and not self._precisa_renovar(token):
            return token.access_token
        with trava_de_renovacao(self._pasta):
            atual = self._carregar()          # outro processo pode ter renovado
            if (not forcar_renovacao and not self._precisa_renovar(atual)) or (
                    forcar_renovacao and atual.refresh_token != token.refresh_token):
                return atual.access_token
            novo = renovar(atual, post=self._post, agora=self._agora)
            self.armazem.gravar(novo.to_dict())
            return novo.access_token

    def status(self) -> dict:
        """O que dá para mostrar a uma pessoa — nunca o token."""
        try:
            token = self._carregar()
        except (SessaoExpirada, EscopoAusente) as exc:
            return {"modo": self.modo, "conectado": False, "motivo": str(exc),
                    "cobranca": "uso do plano ChatGPT (não é API faturada)"}
        restante = token.expira_em(self._agora())
        return {"modo": self.modo, "conectado": True, "rotulo": "Conectado com ChatGPT",
                "conta": token.conta or "?",
                "client_id": (token.client_id[:12] + "…") if token.client_id else "",
                "escopos": sorted(token.scope.split()),
                "escopo_do_plano": token.tem_escopo_do_plano(),
                "acesso_expira_em_s": int(restante),
                "acao": ("renovação automática no próximo uso" if restante <= MARGEM_DE_RENOVACAO_S
                         else "nenhuma"),
                "armazenamento": getattr(self.armazem, "nome", "?"),
                "cobranca": "uso do plano ChatGPT (não é API faturada; limites do plano valem)"}

    def logout(self) -> None:
        """Remove a sessão LOCAL. A doc não documenta revogação remota: para
        desconectar o app na conta, use as configurações do ChatGPT."""
        self.armazem.apagar()


def client_id_do_host(pasta: Path | None = None) -> str:
    """O client_id EMITIDO para o VOLC neste host (registro dinâmico). Público,
    guardado fora do repositório; vale quando `openai.client_id` está vazio."""
    caminho = _garantir_diretorio(pasta or diretorio_padrao()) / "client-id"
    return caminho.read_text(encoding="utf-8").strip() if caminho.exists() else ""


def gravar_client_id_do_host(client_id: str, pasta: Path | None = None) -> None:
    if not client_id.startswith("oaiapp_"):
        raise ValueError("client_id emitido precisa ter o formato oaiapp_...")
    caminho = _garantir_diretorio(pasta or diretorio_padrao()) / "client-id"
    caminho.write_text(client_id, encoding="utf-8")
    os.chmod(caminho, 0o600)
