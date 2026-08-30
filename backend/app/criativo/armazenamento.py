"""Object storage do Estúdio — e a URL assinada que substitui o caminho de arquivo.

## As duas coisas que este módulo existe para impedir

1. **Bytes no Postgres.** A SPEC §14 é explícita: "O banco guarda `storage_key`,
   hashes e metadados, não grandes bases64." Uma imagem 1080x1920 em PNG dá
   ~2 MB; três por job, e um `bytea` vira o gargalo de toda listagem de
   biblioteca que só queria ler nome e data.

2. **Caminho de filesystem no browser.** O ADR-001 rejeitou "chamar scripts
   externos diretamente pelo Hub" e a SPEC §15 pede "nenhum caminho do
   filesystem exibido ao frontend". O frontend recebe `previewUrl`, que é uma
   URL assinada e curta; a `storage_chave` nunca sai do backend.

## Por que a URL é assinada e não uma rota autenticada comum

Porque `<img src>` e `<video src>` não mandam header. Uma rota protegida por
`Authorization: Bearer` funciona no `fetch` e falha em toda tag de mídia, e a
saída de baixo custo para esse problema costuma ser deixar o arquivo público,
que é como um bucket privado vira um bucket aberto. O token vai na URL, é curto,
é escopado a UMA chave e expira.

## O que a assinatura NÃO é

Não é autorização de negócio. Ela prova que o backend emitiu aquela URL para
aquela chave, e nada mais. Quem decide se o operador pode ver o ativo é o
endpoint que EMITE o token, com JWT e papel conferidos. Confundir os dois faria
um token vazado valer para sempre e para tudo; por isso o TTL é de minutos e o
escopo é uma chave só.

## Dois adaptadores, uma porta

`ArmazenamentoLocal` é o de desenvolvimento e prova. `ArmazenamentoSupabase` é o
de produção, escrito contra a API de Storage do Supabase oficial. Ele está aqui
implementado e **não ativado**: o bucket não existe no servidor
(`select * from storage.buckets` devolveu zero linhas em 27/08/2026) e criar
bucket em produção é mudança de infraestrutura que precisa de autorização
explícita. Declarar isso é melhor que um adaptador que "deveria funcionar".
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Protocol

# ─────────────────────────────────────────────────────────────────────────────
# Política de arquivo
# ─────────────────────────────────────────────────────────────────────────────

# MIMEs aceitos, por allowlist. Denylist não serve: o conjunto de coisas
# perigosas é aberto e cresce, o de coisas que este produto precisa é fechado e
# tem cinco itens.
MIMES_DE_IMAGEM = frozenset({"image/png", "image/jpeg", "image/webp"})
MIMES_DE_VIDEO = frozenset({"video/mp4"})
MIMES_ACEITOS = MIMES_DE_IMAGEM | MIMES_DE_VIDEO

# 25 MB por imagem. Uma peça 1080x1920 PNG dá ~2 MB; 25 MB é folga de uma ordem
# de grandeza e ainda barra um upload que só pode ser engano ou ataque.
TETO_DE_IMAGEM_BYTES = 25 * 1024 * 1024

TTL_PADRAO_S = 300


class ArquivoRecusado(ValueError):
    """Upload que não passa na política. Vira 400, não 500."""


class ObjetoNaoEncontrado(KeyError):
    """Chave que não existe no armazenamento."""


def conferir_upload(dados: bytes, mime: str, *, teto: int = TETO_DE_IMAGEM_BYTES) -> None:
    """Tamanho e MIME, nesta ordem, antes de qualquer escrita.

    O tamanho vem primeiro de propósito: conferir MIME de um payload de 900 MB
    já significa tê-lo carregado.
    """
    if not dados:
        raise ArquivoRecusado("arquivo vazio")
    if len(dados) > teto:
        raise ArquivoRecusado(
            f"arquivo acima do limite de {teto // (1024 * 1024)} MB"
        )
    if mime not in MIMES_ACEITOS:
        raise ArquivoRecusado(f"tipo de arquivo não aceito: {mime}")


def nome_seguro(nome: str) -> str:
    """Um nome de arquivo que não navega, não some e não engana.

    Três defeitos clássicos, os três fechados aqui: `../` que sobe diretório,
    caractere de controle que trunca o nome no log, e nome vazio depois da
    limpeza (que viraria um arquivo sem nome, invisível na listagem).
    """
    base = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    base = os.path.basename(base).replace("\\", "").strip()
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    base = re.sub(r"_{2,}", "_", base).strip("._-")
    return base[:96] or "arquivo"


_CHAVE_VALIDA = re.compile(r"^[a-z0-9][a-z0-9/_.-]{0,255}$")


def conferir_chave(chave: str) -> str:
    """Recusa chave que possa escapar do diretório do armazenamento.

    A checagem é por allowlist de forma E por ausência de `..`, e não só por
    `..`: um `%2e%2e` já decodificado pelo servidor web passa por uma checagem
    ingênua de substring e é barrado pela allowlist, que não aceita `%`.
    """
    if not chave or ".." in chave or chave.startswith("/") or "//" in chave:
        raise ArquivoRecusado("chave de armazenamento inválida")
    if not _CHAVE_VALIDA.match(chave):
        raise ArquivoRecusado("chave de armazenamento inválida")
    return chave


def chave_de_asset(projeto_id: str, job_id: str, slot: str, content_hash: str,
                   extensao: str) -> str:
    """A chave é derivada do CONTEÚDO, não de contador nem de relógio.

    Duas consequências que valem o custo: o mesmo arquivo gerado duas vezes
    ocupa uma chave só (dedup de graça), e uma chave nunca é reaproveitada por
    conteúdo diferente, o que manteria um cache servindo a imagem antiga.
    """
    curto = content_hash.removeprefix("sha256:")[:32]
    return conferir_chave(
        f"criativos/{projeto_id}/{job_id}/{slot}_{curto}.{extensao.lstrip('.')}".lower()
    )


# ─────────────────────────────────────────────────────────────────────────────
# A porta
# ─────────────────────────────────────────────────────────────────────────────


class ArmazenamentoDeObjetos(Protocol):
    nome: str

    def guardar(self, chave: str, dados: bytes, mime: str) -> None: ...
    def ler(self, chave: str) -> bytes: ...
    def abrir(self, chave: str) -> BinaryIO: ...
    def tamanho(self, chave: str) -> int: ...
    def existe(self, chave: str) -> bool: ...


# ─────────────────────────────────────────────────────────────────────────────
# Adaptador local (desenvolvimento e prova)
# ─────────────────────────────────────────────────────────────────────────────


class ArmazenamentoLocal:
    """Arquivos em disco, FORA do repositório, servidos só pelo backend.

    O diretório fica fora da árvore de código de propósito: dentro dela, um
    `git add -A` distraído versionaria criativo de cliente, e um `vite` serviria
    os arquivos direto, sem passar por assinatura nenhuma.
    """

    nome = "local"

    def __init__(self, raiz: str | Path | None = None) -> None:
        bruto = raiz or _do_ambiente_ou_settings(
            "CRIATIVO_STORAGE_DIR", "criativo_storage_dir"
        ) or (
            Path.home() / ".volc-os" / "criativos"
        )
        self.raiz = Path(bruto).expanduser().resolve()
        self.raiz.mkdir(parents=True, exist_ok=True)

    def _caminho(self, chave: str) -> Path:
        conferir_chave(chave)
        alvo = (self.raiz / chave).resolve()
        # Segunda barreira, e ela é a que vale: `conferir_chave` julga a string,
        # esta julga o caminho RESOLVIDO. Symlink e normalização do sistema de
        # arquivos só aparecem depois do `resolve`, e é onde um escape sobrevive
        # a qualquer validação puramente textual.
        if not alvo.is_relative_to(self.raiz):
            raise ArquivoRecusado("chave de armazenamento inválida")
        return alvo

    def guardar(self, chave: str, dados: bytes, mime: str) -> None:
        conferir_upload(dados, mime)
        alvo = self._caminho(chave)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        # Escrita atômica: um processo que morre no meio deixa `.parcial`, não
        # um arquivo truncado com nome definitivo que o hash diria estar certo.
        parcial = alvo.with_suffix(alvo.suffix + ".parcial")
        parcial.write_bytes(dados)
        parcial.replace(alvo)

    def ler(self, chave: str) -> bytes:
        alvo = self._caminho(chave)
        if not alvo.is_file():
            raise ObjetoNaoEncontrado(chave)
        return alvo.read_bytes()

    def abrir(self, chave: str) -> BinaryIO:
        alvo = self._caminho(chave)
        if not alvo.is_file():
            raise ObjetoNaoEncontrado(chave)
        return alvo.open("rb")

    def tamanho(self, chave: str) -> int:
        alvo = self._caminho(chave)
        if not alvo.is_file():
            raise ObjetoNaoEncontrado(chave)
        return alvo.stat().st_size

    def existe(self, chave: str) -> bool:
        try:
            return self._caminho(chave).is_file()
        except ArquivoRecusado:
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Adaptador Supabase (produção — escrito, NÃO ativado)
# ─────────────────────────────────────────────────────────────────────────────


class ArmazenamentoSupabase:
    """Storage do Supabase oficial, via API do backend com `service_role`.

    ⚠️ **NÃO ATIVADO.** O bucket `criativos` não existe em
    `database.agenciavolc.com.br`: `select * from storage.buckets` devolveu zero
    linhas em 27/08/2026. Criar bucket é mudança de infraestrutura em produção e
    exige autorização explícita, que esta rodada não tem.

    Está aqui porque a fronteira precisa existir antes do bucket: escrever o
    adaptador depois obrigaria a mexer em quem chama, e é aí que "provisório"
    vira permanente. Quando o bucket for criado, ativar é trocar a instância em
    `armazenamento_padrao()`.
    """

    nome = "supabase"

    def __init__(self, base: str, chave: str, bucket: str = "criativos",
                 *, timeout_s: float = 30.0) -> None:
        self.base = (base or "").rstrip("/")
        self._chave = chave or ""
        self.bucket = bucket
        self.timeout_s = timeout_s

    @property
    def habilitado(self) -> bool:
        return bool(self.base and self._chave)

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._chave,
            "Authorization": f"Bearer {self._chave}",
        }

    def guardar(self, chave: str, dados: bytes, mime: str) -> None:
        import httpx  # noqa: PLC0415

        conferir_upload(dados, mime)
        conferir_chave(chave)
        r = httpx.post(
            f"{self.base}/storage/v1/object/{self.bucket}/{chave}",
            content=dados,
            headers={**self._headers(), "Content-Type": mime, "x-upsert": "true"},
            timeout=self.timeout_s,
        )
        if r.status_code >= 400:
            raise ArquivoRecusado("o armazenamento recusou o arquivo")

    def ler(self, chave: str) -> bytes:
        import httpx  # noqa: PLC0415

        conferir_chave(chave)
        r = httpx.get(
            f"{self.base}/storage/v1/object/{self.bucket}/{chave}",
            headers=self._headers(),
            timeout=self.timeout_s,
        )
        if r.status_code == 404:
            raise ObjetoNaoEncontrado(chave)
        r.raise_for_status()
        return r.content

    def abrir(self, chave: str) -> BinaryIO:
        import io  # noqa: PLC0415

        return io.BytesIO(self.ler(chave))

    def tamanho(self, chave: str) -> int:
        return len(self.ler(chave))

    def existe(self, chave: str) -> bool:
        try:
            self.ler(chave)
            return True
        except (ObjetoNaoEncontrado, Exception):  # noqa: BLE001
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Assinatura
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TokenInvalido(Exception):
    """Token ausente, adulterado ou expirado. Vira 403, nunca 500."""

    motivo: str

    def __str__(self) -> str:  # pragma: no cover
        return self.motivo


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def _deb64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


class Assinador:
    """Emite e confere o token curto que autoriza UMA chave por alguns minutos."""

    def __init__(self, segredo: str) -> None:
        if not segredo or len(segredo) < 16:
            raise ValueError("segredo de assinatura ausente ou curto demais")
        self._segredo = segredo.encode("utf-8")

    def assinar(self, chave: str, *, ttl_s: int = TTL_PADRAO_S) -> str:
        conferir_chave(chave)
        corpo = json.dumps(
            {"c": chave, "e": int(time.time()) + max(1, ttl_s)},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        alvo = _b64(corpo)
        return f"{alvo}.{_b64(self._mac(alvo.encode()))}"

    def conferir(self, token: str) -> str:
        try:
            alvo, assinatura = token.split(".", 1)
        except ValueError:
            raise TokenInvalido("token malformado") from None

        # `compare_digest` e não `==`: comparação curto-circuitada vaza, pelo
        # tempo, quantos bytes iniciais bateram, e isso é o suficiente para
        # forjar um MAC byte a byte.
        if not hmac.compare_digest(_b64(self._mac(alvo.encode())), assinatura):
            raise TokenInvalido("assinatura inválida")

        try:
            dados: dict[str, Any] = json.loads(_deb64(alvo))
        except (ValueError, json.JSONDecodeError):
            raise TokenInvalido("token malformado") from None

        # Comparação em ponto flutuante, e não `int() < int()`.
        #
        # Truncar os dois lados criava uma janela de até um segundo em que um
        # token já vencido ainda passava: assinado em t=1000.05 com ttl 1, ele
        # tem `exp=1001`; conferido em t=1001.25, `int(time.time())` também dá
        # 1001, e `1001 < 1001` é falso. Um segundo a mais é irrelevante para o
        # produto e fatal para o teste que prova a expiração, e um teste de
        # expiração intermitente é pior que nenhum.
        if float(dados.get("e", 0)) < time.time():
            raise TokenInvalido("token expirado")
        return conferir_chave(str(dados.get("c", "")))

    def _mac(self, alvo: bytes) -> bytes:
        return hmac.new(self._segredo, alvo, hashlib.sha256).digest()


def _do_ambiente_ou_settings(nome_env: str, campo: str) -> str | None:
    """Lê do ambiente do processo E do `.env`, nessa ordem.

    ⚠️ Existe porque as duas fontes NÃO são a mesma nesta casa. `Settings` usa
    `pydantic-settings` com `env_file=(".env", ".env.local")`, e isso lê o
    arquivo sem popular `os.environ`; não há `load_dotenv` em lugar nenhum. Ler
    só do ambiente fazia o Estúdio responder 503 no ambiente que a documentação
    manda montar, com a chave presente no arquivo o tempo todo.

    O ambiente vem primeiro porque é ele que a Vercel usa, e porque uma variável
    exportada na mão tem de vencer o arquivo.
    """
    valor = os.environ.get(nome_env)
    if valor:
        return valor
    try:
        from app.config import get_settings  # noqa: PLC0415 — evita ciclo de import

        return getattr(get_settings(), campo, None)
    except Exception:  # noqa: BLE001 — sem config, o chamador decide o que fazer
        return None


def segredo_de_assinatura() -> str:
    """O segredo do assinador, com derivação declarada quando não há um próprio.

    Preferência por `CRIATIVO_URL_SECRET`. Sem ele, deriva de
    `SUPABASE_SERVICE_ROLE_KEY` por HKDF-ish: `sha256("volc-criativos-url-v1" +
    chave)`. A derivação existe para que o produto funcione sem uma variável
    nova, e é DERIVAÇÃO e não uso direto para que o segredo de assinatura não
    seja o mesmo material da credencial do banco: um token de preview vazado não
    pode ser um passo em direção à `service_role`.
    """
    proprio = _do_ambiente_ou_settings("CRIATIVO_URL_SECRET", "criativo_url_secret")
    if proprio and len(proprio) >= 16:
        return proprio
    base = _do_ambiente_ou_settings(
        "SUPABASE_SERVICE_ROLE_KEY", "supabase_service_role_key"
    ) or ""
    if not base:
        raise RuntimeError(
            "sem segredo para assinar URL de preview: "
            "defina CRIATIVO_URL_SECRET ou SUPABASE_SERVICE_ROLE_KEY"
        )
    return hashlib.sha256(("volc-criativos-url-v1" + base).encode()).hexdigest()


_padrao: ArmazenamentoDeObjetos | None = None


def armazenamento_padrao() -> ArmazenamentoDeObjetos:
    """A instância do processo.

    Local por enquanto, e a razão está no docstring de `ArmazenamentoSupabase`:
    o bucket oficial não existe e criá-lo é ato de infraestrutura em produção.
    """
    global _padrao
    if _padrao is None:
        _padrao = ArmazenamentoLocal()
    return _padrao
