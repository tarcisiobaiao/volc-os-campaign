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
from typing import Any, BinaryIO, Literal, Protocol

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
    """Chave que não existe no armazenamento.

    ⚠️ É uma RESPOSTA: o armazenamento foi consultado e disse que não tem. Não
    confundir com `ArmazenamentoIndisponivel`, que é a ausência de resposta.
    """


class ArmazenamentoIndisponivel(RuntimeError):
    """O armazenamento não respondeu — ou respondeu que não pode responder.

    ⚠️ Este tipo existe para NÃO ser `ObjetoNaoEncontrado`. Rede caída, DNS que
    não resolve, 5xx do gateway e timeout têm uma coisa em comum: ninguém sabe
    se o objeto está lá. O `except (ObjetoNaoEncontrado, Exception): return
    False` que estava em `ArmazenamentoSupabase.existe()` transformava as quatro
    em "não existe" — e um `existe()` falso-negativo é upload duplicado no
    melhor caso e "o artefato sumiu" no pior, com o armazenamento intacto o
    tempo todo.

    Ausência é uma resposta. Falha é a ausência de resposta. São estados
    diferentes e o produto age diferente em cada um: um manda seguir, o outro
    manda parar e tentar de novo.
    """


class BucketAusente(ArmazenamentoIndisponivel):
    """O bucket não existe. Recusa fechada, nunca queda silenciosa para local.

    Medido em 27/08/2026: `select * from storage.buckets` em
    `database.agenciavolc.com.br` devolveu ZERO linhas. Um adaptador que
    descobre isso no meio de um upload e cai para disco local grava o artefato
    num lugar que ninguém vai ler de volta — e o job termina verde, apontando
    para um endereço remoto que nunca existiu.
    """


def sha256_de(dados: bytes) -> str:
    """`sha256:` prefixado — mesmo formato de `dominio.hash_de_conteudo`.

    Replicado aqui, e não importado, pela mesma razão declarada lá: a camada de
    I/O não importa o domínio por uma linha. A igualdade entre os dois é
    exercida em `test_criativo_storage_verificado.py`, para que a duplicação não
    vire divergência silenciosa.
    """
    return "sha256:" + hashlib.sha256(dados).hexdigest()


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
# O que uma escrita prova, e o que ela não prova
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EscritaNaoConferida:
    """O retorno de `guardar()` — e ele afirma menos do que se costuma ler nele.

    ⚠️ ESTE TIPO É O RECADO, e por isso ele existe em vez de um comentário.
    `guardar()` devolvia `None`, e "voltou sem exceção" era lido como "o objeto
    está lá, íntegro". Não está: um 200 prova que o servidor ACEITOU os bytes,
    não que os guardou inteiros, nem que a próxima leitura devolve os mesmos.
    Entre o `write` e o `fsync` do outro lado cabe um disco cheio, um proxy que
    trunca e um retry que grava metade.

    Quem quiser dizer VERIFIED tem de ler de volta e comparar — é o que
    `bancada.armazenamento_verificado.publicar_artefato` faz. `conferido` é
    propriedade e não campo de propósito: não existe construtor deste tipo capaz
    de afirmar conferência.
    """

    chave: str
    mime: str
    bytes_escritos: int
    sha256_local: str

    @property
    def conferido(self) -> Literal[False]:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# A porta
# ─────────────────────────────────────────────────────────────────────────────


class ArmazenamentoDeObjetos(Protocol):
    nome: str

    def conferir_bucket(self) -> None: ...
    def guardar(self, chave: str, dados: bytes, mime: str) -> EscritaNaoConferida: ...
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

    def conferir_bucket(self) -> None:
        """O preflight local: o diretório raiz existe e aceita escrita?

        Mesmo contrato do remoto, de propósito. Se só o adaptador do Supabase
        tivesse preflight, o teste que prova a recusa fechada só rodaria contra
        o adaptador que ninguém executa hoje — e o caminho realmente exercido
        continuaria sem prova.
        """
        if not self.raiz.is_dir():
            raise BucketAusente(f"diretório de armazenamento não existe: {self.raiz}")
        if not os.access(self.raiz, os.W_OK):
            raise ArmazenamentoIndisponivel(
                f"sem permissão de escrita em {self.raiz}"
            )

    def guardar(self, chave: str, dados: bytes, mime: str) -> EscritaNaoConferida:
        conferir_upload(dados, mime)
        alvo = self._caminho(chave)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        # Escrita atômica: um processo que morre no meio deixa `.parcial`, não
        # um arquivo truncado com nome definitivo que o hash diria estar certo.
        parcial = alvo.with_suffix(alvo.suffix + ".parcial")
        parcial.write_bytes(dados)
        parcial.replace(alvo)
        # ⚠️ Nem aqui, com o arquivo a um `read_bytes()` de distância, esta função
        # afirma conferência. Quem confere é quem lê de volta.
        return EscritaNaoConferida(chave, mime, len(dados), sha256_de(dados))

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
# O transporte, como porta
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RespostaHTTP:
    """O mínimo que o adaptador precisa saber de uma resposta: código e corpo."""

    status: int
    corpo: bytes = b""


class FalhaDeTransporte(ArmazenamentoIndisponivel):
    """A requisição não chegou, ou não voltou.

    Não diz nada sobre o objeto — e é exatamente por isso que não é
    `ObjetoNaoEncontrado`.
    """


class TransporteHTTP(Protocol):
    """A fronteira que torna o adaptador remoto PROVÁVEL sem rede.

    Sem ela, a única forma de exercer o adaptador do Supabase seria contra o
    Supabase — que é produção, e cujo bucket não existe. O resultado prático era
    um adaptador escrito e nunca executado, com quatro caminhos de erro que
    ninguém jamais viu rodar: bucket ausente, objeto ausente, rede caída e
    releitura divergente.
    """

    def requisitar(self, metodo: str, url: str, *, headers: dict[str, str],
                   corpo: bytes | None = None, timeout_s: float) -> RespostaHTTP: ...


class TransporteHttpx:
    """O transporte real. Traduz falha de rede em `FalhaDeTransporte`.

    ⚠️ A tradução é o ponto: `httpx` levanta `ConnectError`, `ReadTimeout` e
    parentes, e a versão anterior deste módulo capturava tudo isso com
    `except Exception` dentro de `existe()` e devolvia `False`. Aqui a exceção
    sobe com um tipo que ninguém consegue confundir com ausência.
    """

    def requisitar(self, metodo: str, url: str, *, headers: dict[str, str],
                   corpo: bytes | None = None, timeout_s: float) -> RespostaHTTP:
        import httpx  # noqa: PLC0415

        try:
            r = httpx.request(
                metodo, url, content=corpo, headers=headers, timeout=timeout_s
            )
        except (httpx.HTTPError, OSError) as erro:
            raise FalhaDeTransporte(
                f"{metodo} {url} falhou: {type(erro).__name__}: {erro}"
            ) from erro
        return RespostaHTTP(r.status_code, r.content)


# ─────────────────────────────────────────────────────────────────────────────
# Adaptador Supabase (produção — implementado e DESARMADO)
# ─────────────────────────────────────────────────────────────────────────────


class ArmazenamentoSupabase:
    """Storage do Supabase oficial, via API do backend com `service_role`.

    ⚠️ **IMPLEMENTADO E DESARMADO.** O bucket `criativos` não existe em
    `database.agenciavolc.com.br`: `select * from storage.buckets` devolveu zero
    linhas em 27/08/2026. Criar bucket é mudança de infraestrutura em produção e
    exige autorização explícita, que esta rodada não tem.

    Desarmado NÃO quer dizer não exercido. Todo caminho aqui — preflight,
    upload, leitura, ausência de objeto, ausência de bucket e queda de rede — é
    executado em `test_criativo_storage_verificado.py` contra um `TransporteHTTP`
    de mentira em memória. O que continua sem prova, e está declarado como tal, é
    o comportamento do Supabase real: nenhum teste desta casa fala com ele.

    Quando o bucket for criado, ativar é trocar a instância em
    `armazenamento_padrao()` — e rodar de novo o preflight, que é a única coisa
    capaz de dizer que o bucket passou a existir.
    """

    nome = "supabase"

    def __init__(self, base: str, chave: str, bucket: str = "criativos",
                 *, timeout_s: float = 30.0,
                 transporte: TransporteHTTP | None = None) -> None:
        self.base = (base or "").rstrip("/")
        self._chave = chave or ""
        self.bucket = bucket
        self.timeout_s = timeout_s
        self._transporte: TransporteHTTP = transporte or TransporteHttpx()
        self._bucket_conferido = False

    @property
    def habilitado(self) -> bool:
        return bool(self.base and self._chave)

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._chave,
            "Authorization": f"Bearer {self._chave}",
        }

    def _url_objeto(self, chave: str) -> str:
        return f"{self.base}/storage/v1/object/{self.bucket}/{chave}"

    def _erro_de_404(self, r: RespostaHTTP, chave: str) -> Exception:
        """Desempata os DOIS 404 diferentes que o Storage devolve.

        ⚠️ Esta é a armadilha do adaptador remoto. O Supabase responde 404 tanto
        para `{"error":"Bucket not found"}` quanto para
        `{"error":"Object not found"}`, e ler o primeiro como "o objeto não
        existe" é a queda silenciosa vestida de resposta normal: o produto
        concluiria "ainda não subiu" e tentaria de novo, para sempre, contra um
        bucket que nunca existiu.
        """
        texto = r.corpo.decode("utf-8", "replace").lower()
        if "bucket" in texto:
            self._bucket_conferido = False
            return BucketAusente(
                f"bucket '{self.bucket}' não existe em {self.base} "
                f"(o armazenamento respondeu 404 de BUCKET, não de objeto)"
            )
        return ObjetoNaoEncontrado(chave)

    def conferir_bucket(self) -> None:
        """Preflight: o bucket existe? Recusa fechada quando não existe.

        Só o SUCESSO é memorizado. Memorizar o fracasso faria o processo recusar
        para sempre um bucket criado um minuto depois; memorizar o sucesso é
        seguro porque bucket apagado reaparece como 404 no próprio upload, e o
        `_erro_de_404` derruba a memória quando isso acontece.
        """
        if self._bucket_conferido:
            return
        if not self.habilitado:
            raise ArmazenamentoIndisponivel(
                "armazenamento remoto sem base ou sem credencial: não dá para "
                "afirmar nem que o bucket existe nem que não existe"
            )
        r = self._transporte.requisitar(
            "GET",
            f"{self.base}/storage/v1/bucket/{self.bucket}",
            headers=self._headers(),
            timeout_s=self.timeout_s,
        )
        if r.status == 404:
            raise BucketAusente(
                f"bucket '{self.bucket}' não existe em {self.base}; "
                "criar bucket é mudança de infraestrutura e precisa de "
                "autorização explícita"
            )
        if r.status >= 400:
            raise ArmazenamentoIndisponivel(
                f"preflight do bucket '{self.bucket}' respondeu {r.status}"
            )
        self._bucket_conferido = True

    def guardar(self, chave: str, dados: bytes, mime: str) -> EscritaNaoConferida:
        conferir_upload(dados, mime)
        conferir_chave(chave)
        self.conferir_bucket()
        r = self._transporte.requisitar(
            "POST",
            self._url_objeto(chave),
            headers={**self._headers(), "Content-Type": mime, "x-upsert": "true"},
            corpo=dados,
            timeout_s=self.timeout_s,
        )
        if r.status == 404:
            raise self._erro_de_404(r, chave)
        if r.status >= 500:
            # ⚠️ 5xx NÃO é `ArquivoRecusado`. A versão anterior devolvia "o
            # armazenamento recusou o arquivo" para qualquer status >= 400, o que
            # virava um 400 para o operador: o produto acusava o arquivo dele por
            # uma falha do servidor, e o retry — que resolveria — nunca acontecia.
            raise ArmazenamentoIndisponivel(
                f"o armazenamento respondeu {r.status} ao gravar {chave}"
            )
        if r.status >= 400:
            raise ArquivoRecusado(
                f"o armazenamento recusou o arquivo (status {r.status})"
            )
        return EscritaNaoConferida(chave, mime, len(dados), sha256_de(dados))

    def ler(self, chave: str) -> bytes:
        conferir_chave(chave)
        r = self._transporte.requisitar(
            "GET",
            self._url_objeto(chave),
            headers=self._headers(),
            timeout_s=self.timeout_s,
        )
        if r.status == 404:
            raise self._erro_de_404(r, chave)
        if r.status >= 400:
            raise ArmazenamentoIndisponivel(
                f"a leitura de {chave} respondeu {r.status}"
            )
        return r.corpo

    def abrir(self, chave: str) -> BinaryIO:
        import io  # noqa: PLC0415

        return io.BytesIO(self.ler(chave))

    def tamanho(self, chave: str) -> int:
        return len(self.ler(chave))

    def existe(self, chave: str) -> bool:
        """Só devolve `False` quando o armazenamento DISSE que não tem.

        ⚠️ CONTRAPROVA VERMELHA (registrada em 01/09/2026, antes desta correção):
        com `httpx.get` levantando `ConnectError`, o `existe()` anterior —
        `except (ObjetoNaoEncontrado, Exception): return False` — devolvia
        `False` com a rede caída. A cláusula era, além de perigosa, inerte:
        `Exception` já cobre `ObjetoNaoEncontrado`, então o primeiro nome do
        `except` só servia para fazer o colapso parecer intencional e revisado.

        `ArmazenamentoIndisponivel` e `BucketAusente` sobem. Quem chama decide
        entre tentar de novo e parar — decisão que ninguém pode tomar quando a
        resposta chega como um `False` indistinguível de ausência real.
        """
        try:
            self.ler(chave)
        except ObjetoNaoEncontrado:
            return False
        except ArquivoRecusado:
            # Chave que a própria política recusa não existe em lugar nenhum:
            # não há consulta a fazer, e isto não esconde falha de infraestrutura.
            return False
        return True


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
