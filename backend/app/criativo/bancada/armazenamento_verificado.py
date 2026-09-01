"""A máquina de estados do armazenamento — em Python, e não só no gatilho.

## O achado que este módulo existe para fechar

O roadmap dava P17-T06 como "máquina provada". Ela estava provada — em SQL. A
sequência `LOCAL -> UPLOADED_UNVERIFIED -> VERIFIED_OK | VERIFIED_MISMATCH`
existia em exatamente dois lugares: o gatilho
`criativo_render_artefato_imutavel` de `supabase/migrations/v11_03_execucao_criativa.sql`
e as asserções de `scripts/provas-v11_03.sql`. Medido em 01/09/2026:

    rg -n "UPLOADED_UNVERIFIED|VERIFIED_MISMATCH" --glob '!node_modules'
    → nenhum `.py`, nenhum `.ts`

Ou seja: a garantia morava inteira numa migração que ainda não foi aplicada, e o
código que de fato sobe arquivo — `armazenamento.py` — não conhecia nenhum
desses estados. Um gatilho não aplicado é uma regra escrita, não uma regra em
vigor; e mesmo aplicado ele só recusaria a ESCRITA errada no banco, sem nunca
ler um byte de volta do object storage para saber se o artefato está lá inteiro.

## O que é conferir, e o que não é

Conferir é: ler de volta do armazenamento e comparar bytes e sha256 com o que
foi enviado. Não é o 200 do upload, não é o `guardar()` que voltou sem exceção,
e não é o hash calculado localmente duas vezes — este último passa mesmo quando
o objeto remoto está truncado, porque nunca olhou para o objeto remoto.

Enquanto a releitura não aconteceu, o estado é `UPLOADED_UNVERIFIED`. Esse
estado é a coisa mais importante do módulo: é o nome do intervalo em que o
produto NÃO SABE, e é justamente esse intervalo que costuma ser apagado por um
booleano `ok=True` escrito logo depois do upload.

## As três ausências que continuam distintas aqui

1. **Objeto ausente** (`ObjetoNaoEncontrado`): o armazenamento respondeu que não
   tem. É resposta, e o veredito é `VERIFIED_MISMATCH` — subiu e não está lá.
2. **Armazenamento indisponível** (`ArmazenamentoIndisponivel`): ninguém
   respondeu. NÃO é divergência: o estado fica `UPLOADED_UNVERIFIED` com motivo,
   porque afirmar `MISMATCH` aqui carimbaria um veredito terminal em cima de uma
   pergunta que nunca chegou a ser feita.
3. **Bucket ausente** (`BucketAusente`): o destino não existe. Recusa fechada,
   antes de qualquer upload, e nunca queda silenciosa para disco local.

## Fronteira declarada

Nada aqui fala com `database.agenciavolc.com.br`. O adaptador remoto é exercido
por um duplo de transporte em memória em
`backend/tests/test_criativo_storage_verificado.py`. O bucket `criativos` não
existe no Supabase oficial (zero linhas em `storage.buckets`, 27/08/2026) e
criá-lo exige autorização externa que esta missão não tem: o adaptador está
implementado e DESARMADO, e o preflight é o que garante que "desarmado" apareça
como recusa legível em vez de silêncio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Protocol

from ..armazenamento import (
    ArmazenamentoIndisponivel,
    ArquivoRecusado,
    BucketAusente,
    EscritaNaoConferida,
    ObjetoNaoEncontrado,
    conferir_chave,
    conferir_upload,
    sha256_de,
)

# ─────────────────────────────────────────────────────────────────────────────
# A máquina
# ─────────────────────────────────────────────────────────────────────────────


class EstadoDoArmazenamento(str, Enum):
    """Os quatro estados do gatilho, com os mesmos nomes.

    Os nomes são iguais aos do SQL de propósito. Traduzir para português aqui
    faria a mesma máquina existir com dois vocabulários, e a próxima divergência
    entre banco e aplicação apareceria como uma discussão de tradução.

    - `LOCAL`: chave nula, conferência nula. O artefato existe no disco do
      operário e em lugar nenhum além dele.
    - `UPLOADED_UNVERIFIED`: chave preenchida, conferência nula. Subiu; ninguém
      leu de volta. **Não é "verificado", não é "pronto", não é "ok".**
    - `VERIFIED_OK`: chave, carimbo e hash remoto igual ao local.
    - `VERIFIED_MISMATCH`: chave, carimbo e hash remoto diferente — ou objeto
      ausente na releitura. Terminal, e registrado; esconder divergência é o
      único desfecho pior do que ter uma.
    """

    LOCAL = "LOCAL"
    UPLOADED_UNVERIFIED = "UPLOADED_UNVERIFIED"
    VERIFIED_OK = "VERIFIED_OK"
    VERIFIED_MISMATCH = "VERIFIED_MISMATCH"


#: As setas do gatilho, e SÓ elas. `LOCAL -> VERIFIED_*` existe porque upload e
#: conferência podem acontecer no mesmo passo; `VERIFIED_*` não sai de si mesmo
#: porque reescrever o veredito apagaria a auditoria de uma divergência.
TRANSICOES: dict[EstadoDoArmazenamento, frozenset[EstadoDoArmazenamento]] = {
    EstadoDoArmazenamento.LOCAL: frozenset(
        {
            EstadoDoArmazenamento.UPLOADED_UNVERIFIED,
            EstadoDoArmazenamento.VERIFIED_OK,
            EstadoDoArmazenamento.VERIFIED_MISMATCH,
        }
    ),
    EstadoDoArmazenamento.UPLOADED_UNVERIFIED: frozenset(
        {EstadoDoArmazenamento.VERIFIED_OK, EstadoDoArmazenamento.VERIFIED_MISMATCH}
    ),
    EstadoDoArmazenamento.VERIFIED_OK: frozenset(),
    EstadoDoArmazenamento.VERIFIED_MISMATCH: frozenset(),
}

#: Onde a máquina para. Um artefato conferido não volta a ser "não conferido":
#: se alguém precisar reenviar, isso é um artefato NOVO, com chave nova.
TERMINAIS: frozenset[EstadoDoArmazenamento] = frozenset(
    {EstadoDoArmazenamento.VERIFIED_OK, EstadoDoArmazenamento.VERIFIED_MISMATCH}
)


class TransicaoDeArmazenamentoProibida(ValueError):
    def __init__(self, de: EstadoDoArmazenamento, para: EstadoDoArmazenamento) -> None:
        super().__init__(f"transicao proibida no armazenamento: {de.value} -> {para.value}")
        self.de, self.para = de, para


def pode_ir(de: EstadoDoArmazenamento, para: EstadoDoArmazenamento) -> bool:
    return para in TRANSICOES[de]


class MaquinaDeArmazenamento:
    """O caminho percorrido, e não só o ponto de chegada.

    Guarda o histórico porque o estado final sozinho não distingue "conferi e
    bateu" de "afirmei que bateu sem conferir": os dois terminam em
    `VERIFIED_OK`. O histórico obriga a passagem por `UPLOADED_UNVERIFIED` a
    aparecer, e é isso que um teste consegue exigir.
    """

    def __init__(self) -> None:
        self._estado = EstadoDoArmazenamento.LOCAL
        self._historico: list[EstadoDoArmazenamento] = [EstadoDoArmazenamento.LOCAL]

    @property
    def estado(self) -> EstadoDoArmazenamento:
        return self._estado

    @property
    def historico(self) -> tuple[EstadoDoArmazenamento, ...]:
        return tuple(self._historico)

    def avancar(self, para: EstadoDoArmazenamento) -> EstadoDoArmazenamento:
        if not pode_ir(self._estado, para):
            raise TransicaoDeArmazenamentoProibida(self._estado, para)
        self._estado = para
        self._historico.append(para)
        return para


def estado_de(
    *,
    storage_chave: str | None,
    storage_conferido_em: datetime | None,
    storage_hash_conferido: str | None,
    sha256_do_artefato: str,
) -> EstadoDoArmazenamento:
    """Classifica uma LINHA (do banco ou de um registro) na mesma máquina.

    Recebe exatamente as três colunas que o gatilho olha em
    `criativo_render_artefato`. Existe para que a leitura de volta do banco e a
    publicação usem a MESMA regra: sem isto, a aplicação teria a sua noção de
    "verificado" e o banco a dele, que é a dupla verdade que o P17-T04 já pagou
    para eliminar na fila de trabalhos.

    Duas linhas impossíveis levantam em vez de virar um estado plausível:
    conferência sem endereço (regra 3 do gatilho) e hash conferido sem carimbo
    de conferência — meia conferência registrada é pior que nenhuma, porque
    parece completa.
    """
    if storage_chave is None:
        if storage_conferido_em is not None:
            raise ValueError(
                "conferencia sem endereco no armazenamento: "
                "storage_conferido_em preenchido com storage_chave nula"
            )
        if storage_hash_conferido is not None:
            raise ValueError("hash conferido sem endereco no armazenamento")
        return EstadoDoArmazenamento.LOCAL

    if storage_conferido_em is None:
        if storage_hash_conferido is not None:
            raise ValueError(
                "hash conferido sem carimbo de conferencia: "
                "conferencia pela metade nao e um estado"
            )
        return EstadoDoArmazenamento.UPLOADED_UNVERIFIED

    # ⚠️ Carimbo COM hash nulo é o objeto ausente na releitura: a conferência
    # aconteceu e não havia o que hashear. Preencher esse campo com um hash de
    # bytes vazios seria inventar um conteúdo que ninguém leu — ausência
    # preservada como ausência, e o veredito é divergência.
    if storage_hash_conferido is None:
        return EstadoDoArmazenamento.VERIFIED_MISMATCH
    if storage_hash_conferido == sha256_do_artefato:
        return EstadoDoArmazenamento.VERIFIED_OK
    return EstadoDoArmazenamento.VERIFIED_MISMATCH


# ─────────────────────────────────────────────────────────────────────────────
# A chave canônica
# ─────────────────────────────────────────────────────────────────────────────

#: Um segmento de chave: minúsculas, dígitos, `_` e `-`. Sem `.` (que abriria
#: `..` por composição) e sem `/` (que criaria um nível de diretório vindo de
#: um identificador que ninguém validou).
_SEGMENTO = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_EXTENSAO = re.compile(r"^[a-z0-9]{1,8}$")


def _segmento(nome: str, valor: str) -> str:
    if not _SEGMENTO.match(valor or ""):
        raise ArquivoRecusado(
            f"{nome} invalido para chave de armazenamento: {valor!r}"
        )
    return valor


def chave_canonica(tenant_id: str, job_id: str, slot: str, sha256: str,
                   extensao: str) -> str:
    """`criativos/<tenant>/<job>/<slot>_<hash>.<ext>` — tenant na frente.

    Duas diferenças deliberadas em relação a `armazenamento.chave_de_asset`, que
    continua servindo o Estúdio antigo e não foi alterada:

    1. **O primeiro nível é o TENANT, não o projeto.** É por tenant que o acesso
       é decidido, e uma chave que começa pelo projeto obriga qualquer política
       de prefixo a conhecer o mapa projeto→tenant para dizer quem pode ler o
       quê.

    2. **Identificador fora do alfabeto é RECUSADO, não normalizado.**
       `chave_de_asset` aplica `.lower()` na chave inteira, então os tenants
       `Cliente` e `cliente` produzem a MESMA chave — dois inquilinos no mesmo
       endereço. Normalizar identificador de dono é criar colisão silenciosa;
       recusar é barulhento e correto.

    O hash entra na chave para que a mesma peça não ocupe dois endereços e para
    que um endereço nunca sirva conteúdo diferente do que já serviu.
    """
    curto = sha256.removeprefix("sha256:")[:32]
    if not re.fullmatch(r"[0-9a-f]{32}", curto):
        raise ArquivoRecusado(f"sha256 invalido para chave: {sha256!r}")
    ext = (extensao or "").lstrip(".")
    if not _EXTENSAO.match(ext):
        raise ArquivoRecusado(f"extensao invalida para chave: {extensao!r}")
    tenant = _segmento("tenant_id", tenant_id)
    job = _segmento("job_id", job_id)
    peca = _segmento("slot", slot)
    return conferir_chave(f"criativos/{tenant}/{job}/{peca}_{curto}.{ext}")


# ─────────────────────────────────────────────────────────────────────────────
# A publicação
# ─────────────────────────────────────────────────────────────────────────────


class ArtefatoNaoVerificado(RuntimeError):
    """Alguém pediu o artefato como verificado, e ele não é.

    Existe para que "não verificado" não possa ser consumido por engano como
    "verificado": quem quiser o caminho feliz chama `exigir_verificado()` e
    recebe uma exceção legível em vez de um objeto de aparência normal.
    """


@dataclass(frozen=True)
class Publicacao:
    """O que se sabe sobre um artefato no armazenamento, incluindo o que não se sabe."""

    estado: EstadoDoArmazenamento
    chave: str
    mime: str
    bytes_local: int
    sha256_local: str
    #: `None` quando a releitura não aconteceu (falha) — e também quando
    #: aconteceu e o objeto não estava lá. São coisas diferentes, e `estado` as
    #: separa: `UPLOADED_UNVERIFIED` na primeira, `VERIFIED_MISMATCH` na segunda.
    bytes_remoto: int | None = None
    sha256_remoto: str | None = None
    conferido_em: datetime | None = None
    #: Sempre preenchido quando o desfecho não é `VERIFIED_OK`. Um estado ruim
    #: sem motivo obriga quem lê o log a adivinhar, e a adivinhação mais comum é
    #: "deve ter sido a rede".
    motivo: str | None = None
    historico: tuple[EstadoDoArmazenamento, ...] = field(default_factory=tuple)

    @property
    def verificado(self) -> bool:
        """Verdadeiro só com releitura feita, carimbo e hashes idênticos.

        Três condições e não uma: um `estado` construído à mão não basta para
        afirmar conferência, e é essa a diferença entre um campo e uma prova.
        """
        return (
            self.estado is EstadoDoArmazenamento.VERIFIED_OK
            and self.conferido_em is not None
            and self.sha256_remoto is not None
            and self.sha256_remoto == self.sha256_local
            and self.bytes_remoto == self.bytes_local
        )

    def exigir_verificado(self) -> Publicacao:
        if not self.verificado:
            raise ArtefatoNaoVerificado(
                f"{self.chave}: estado {self.estado.value}"
                + (f" — {self.motivo}" if self.motivo else "")
            )
        return self

    def para_registro(self) -> dict[str, Any]:
        """As três colunas do gatilho, e nada além delas.

        `UPLOADED_UNVERIFIED` sai com carimbo e hash NULOS de propósito: é assim
        que o banco também representa "subiu e não foi conferido", e escrever um
        carimbo aqui gravaria uma conferência que não houve — que o gatilho, por
        ser terminal, nunca deixaria corrigir depois.
        """
        conferiu = self.estado in TERMINAIS
        return {
            "storage_chave": self.chave if self.estado is not EstadoDoArmazenamento.LOCAL else None,
            "storage_conferido_em": self.conferido_em if conferiu else None,
            "storage_hash_conferido": self.sha256_remoto if conferiu else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# A porta que o publicador exige
# ─────────────────────────────────────────────────────────────────────────────


class ArmazenamentoConferivel(Protocol):
    """Um armazenamento que pode ser conferido: preflight, escrita e RELEITURA.

    `ler` está no contrato porque sem ele não existe conferência — e um
    adaptador que só escreve não pode ser usado por `publicar_artefato`, o que é
    a forma de tipo de dizer "aqui não se afirma verificado sem ler de volta".
    """

    nome: str

    def conferir_bucket(self) -> None: ...
    def guardar(self, chave: str, dados: bytes, mime: str) -> EscritaNaoConferida: ...
    def ler(self, chave: str) -> bytes: ...


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def publicar_artefato(
    loja: ArmazenamentoConferivel,
    *,
    chave: str,
    dados: bytes,
    mime: str,
    relogio: Callable[[], datetime] = _agora,
) -> Publicacao:
    """Sobe o artefato e o confere lendo de volta. Nesta ordem, sempre.

    Sequência, e cada passo existe por um motivo que já falhou em algum lugar:

    1. **política** (`conferir_upload`) antes de tocar em qualquer destino —
       recusar depois de escrever significa ter escrito;
    2. **preflight de bucket** — sem ele, "o destino não existe" só aparece no
       meio do upload, e a saída barata para isso é cair para local em silêncio;
    3. **upload**, que leva a máquina a `UPLOADED_UNVERIFIED` e a NADA MAIS;
    4. **releitura remota** — o único passo capaz de dizer alguma coisa sobre o
       objeto que está lá;
    5. **comparação de bytes E sha256**, e o veredito terminal.

    Não levanta por divergência: `VERIFIED_MISMATCH` é um resultado que precisa
    ser REGISTRADO, e exceção é fácil demais de engolir num `except`. Levanta,
    sim, quando o destino não existe ou a política recusa — aí não há nada para
    registrar porque nada aconteceu.
    """
    conferir_upload(dados, mime)
    conferir_chave(chave)
    sha_local = sha256_de(dados)
    maquina = MaquinaDeArmazenamento()

    # 2. Preflight. `BucketAusente` e `ArmazenamentoIndisponivel` sobem: nenhum
    # byte foi enviado, então não existe estado a registrar — e o chamador
    # precisa distinguir "não tentei" de "tentei e deu errado".
    loja.conferir_bucket()

    # 3. Upload. O retorno de `guardar` é `EscritaNaoConferida` e é usado só como
    # o que é: contagem de bytes escritos. Ele não pode promover estado nenhum.
    escrita = loja.guardar(chave, dados, mime)
    bytes_local = getattr(escrita, "bytes_escritos", None) or len(dados)
    maquina.avancar(EstadoDoArmazenamento.UPLOADED_UNVERIFIED)

    parcial = Publicacao(
        estado=maquina.estado,
        chave=chave,
        mime=mime,
        bytes_local=bytes_local,
        sha256_local=sha_local,
        motivo="upload concluido; releitura ainda nao aconteceu",
        historico=maquina.historico,
    )

    # 4. Releitura. As duas falhas abaixo são deliberadamente diferentes.
    try:
        remoto = loja.ler(chave)
    except ObjetoNaoEncontrado:
        # O armazenamento RESPONDEU que não tem. É divergência: o upload disse
        # que aceitou e a leitura diz que não há nada. Terminal, e sem hash —
        # não se inventa o hash de um conteúdo que não foi lido.
        maquina.avancar(EstadoDoArmazenamento.VERIFIED_MISMATCH)
        return Publicacao(
            estado=maquina.estado,
            chave=chave,
            mime=mime,
            bytes_local=bytes_local,
            sha256_local=sha_local,
            bytes_remoto=None,
            sha256_remoto=None,
            conferido_em=relogio(),
            motivo="objeto ausente na releitura: o upload foi aceito e o objeto nao esta la",
            historico=maquina.historico,
        )
    except ArmazenamentoIndisponivel as erro:
        # ⚠️ NINGUÉM RESPONDEU. Isto não é divergência e não pode virar veredito:
        # `VERIFIED_MISMATCH` é terminal, e carimbá-lo aqui condenaria um
        # artefato possivelmente íntegro por causa de um timeout. Fica
        # `UPLOADED_UNVERIFIED`, com motivo, para ser conferido de novo depois.
        return Publicacao(
            estado=parcial.estado,
            chave=chave,
            mime=mime,
            bytes_local=bytes_local,
            sha256_local=sha_local,
            motivo=f"releitura nao concluida: {erro}",
            historico=parcial.historico,
        )

    # 5. Comparação. Bytes E hash: o tamanho sozinho não pega troca de conteúdo,
    # e comparar só o hash esconderia, no relato, o quanto o objeto encolheu.
    sha_remoto = sha256_de(remoto)
    igual = sha_remoto == sha_local and len(remoto) == bytes_local
    maquina.avancar(
        EstadoDoArmazenamento.VERIFIED_OK if igual else EstadoDoArmazenamento.VERIFIED_MISMATCH
    )
    return Publicacao(
        estado=maquina.estado,
        chave=chave,
        mime=mime,
        bytes_local=bytes_local,
        sha256_local=sha_local,
        bytes_remoto=len(remoto),
        sha256_remoto=sha_remoto,
        conferido_em=relogio(),
        motivo=None
        if igual
        else (
            "divergencia na releitura: "
            f"local {bytes_local}B {sha_local[:19]}… vs "
            f"remoto {len(remoto)}B {sha_remoto[:19]}…"
        ),
        historico=maquina.historico,
    )


__all__ = [
    "ArmazenamentoConferivel",
    "ArmazenamentoIndisponivel",
    "ArtefatoNaoVerificado",
    "BucketAusente",
    "EstadoDoArmazenamento",
    "MaquinaDeArmazenamento",
    "Publicacao",
    "TERMINAIS",
    "TRANSICOES",
    "TransicaoDeArmazenamentoProibida",
    "chave_canonica",
    "estado_de",
    "pode_ir",
    "publicar_artefato",
]
