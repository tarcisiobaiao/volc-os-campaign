"""Contrato de entrada do runner — o que basta para subir uma campanha.

Um único brief serve todos os canais. O que muda entre Search, Display e
Demand Gen é o construtor que o consome, não a entrada — assim a camada de
copy e a de decisão não precisam saber em que canal vão parar.

As keywords entram de uma das duas formas, nunca das duas: `keywords` (lista
chapada, um ad group) ou `sub_intencoes` (a partição tipada que a mineração
do Pautador já entrega, um ad group por grupo).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import ClassVar

from ..referencia import geo as _geo
from .criterio import Criterio, de_lista


@dataclass
class Sitelink:
    texto: str
    descricao1: str = ""
    descricao2: str = ""


@dataclass
class Snippet:
    header: str
    valores: list[str] = field(default_factory=list)


@dataclass
class Copy:
    headlines: list[str] = field(default_factory=list)
    descriptions: list[str] = field(default_factory=list)
    # Display usa uma longa; Demand Gen só usa no formato de vídeo responsivo,
    # que a primeira onda recusa em vez de misturar com o multi-asset.
    long_headlines: list[str] = field(default_factory=list)
    sitelinks: list[Sitelink] = field(default_factory=list)
    callouts: list[str] = field(default_factory=list)
    snippet: Snippet | None = None
    business_name: str = ""


@dataclass(frozen=True)
class Linhagem:
    """De onde veio ESTE arquivo — o fato de procedência que atravessa a fronteira.

    ## Por que ela mora aqui, e não em `volc_ads/criativo/contrato.py`

    Porque `brief.py` **não importa `criativo/`** (a razão está algumas linhas
    abaixo, no docstring de `ImagemParaSubir`, e continua valendo). Quem conhece
    os dois lados é `volc_ads/criativo_ponte.py`: ele lê um `criativo.Asset` com
    sua `Procedencia` e **projeta** nesta `Linhagem`. A fonte é o `Asset`; isto
    aqui é a cópia que viaja.

    ## Por que ela é achatada, e todos os campos são JSON-nativos

    Não é preferência de estilo — é o formato do recibo que manda. `Recibo.
    para_json()` (`subir.py`) é `dataclasses.asdict`, e `_gravar` chama
    `json.dumps(...)` **sem `default=`**. Um `datetime` cru chegaria lá como
    objeto e estouraria `TypeError`. Pior: a primeira gravação do recibo
    acontece DENTRO do `with modo.destravar(...)`, ou seja, com a trava já
    aberta e a requisição prestes a sair. O melhor lugar para descobrir que a
    procedência não serializa é aqui, não ali.

    Por isso `quando` é `str` ISO-8601 com offset, e há uma guarda que recusa
    `datetime`. É uma guarda de regressão, não paranoia: o tipo certo em
    `Procedencia.quando` É `datetime`, e a conversão é fácil de esquecer.

    ## Ausência tem forma

    Todo campo que pode não ser sabido é `None` — e `None` quer dizer "ninguém
    apurou", nunca "apurei e deu zero/vazio". `custo_usd=None` é o motor que não
    reportou custo; `0.0` seria a afirmação de que a imagem foi de graça.

    `confirmada` é **propriedade derivada, nunca campo gravado**. Um booleano
    guardado sobrevive à edição do resto e passa a mentir — é o mesmo defeito
    que o `Selo` de `subir.py` já paga para evitar ao carregar a impressão
    digital do payload em vez de um `validado=True`.
    """

    #: Nome do Asset na conta — o mesmo de `ImagemParaSubir.nome`.
    nome: str
    #: Em qual lista de papel do contrato visual este arquivo entrou.
    papel: str

    #: `Asset.identidade` — o id interno derivado do conteúdo, que existe antes
    #: de qualquer chamada externa.
    identidade: str | None = None
    #: `sha256:...` do conteúdo. Conferido contra os bytes na fronteira.
    conteudo_hash: str | None = None

    motor: str | None = None
    #: `""` é resposta legítima aqui: o motor existe e não versiona. `None` é
    #: "não sei nem se há motor".
    versao_do_motor: str | None = None
    insumo: str | None = None
    insumo_hash: str | None = None
    pedido: str | None = None
    #: ISO-8601 com offset. NUNCA `datetime` — ver o docstring acima.
    quando: str | None = None
    origem: str | None = None

    mime: str | None = None
    largura: int | None = None
    altura: int | None = None
    bytes_totais: int | None = None
    custo_usd: float | None = None

    #: Identidade do asset-pai quando este arquivo é recorte/variante de outro.
    derivado_de: str | None = None
    #: `resource_name` do Google, quando o asset já existir na conta.
    id_externo: str | None = None

    #: Contra qual régua este arquivo foi julgado, e se ela é provisória.
    #: Viajam juntos porque um veredito sem a régua não é auditável depois.
    exigencia_fonte: str | None = None
    exigencia_provisoria: bool | None = None

    def __post_init__(self) -> None:
        if not self.nome.strip():
            raise ValueError("linhagem sem nome: ela acompanha um Asset nomeado")
        if not self.papel.strip():
            raise ValueError(
                f"linhagem de {self.nome!r} sem papel: é o papel que diz em qual "
                "campo do responsive display ad o arquivo entrou")
        if self.conteudo_hash is not None and not self.conteudo_hash.startswith("sha256:"):
            raise ValueError(
                f"hash sem algoritmo declarado: {self.conteudo_hash!r}. Um hash "
                "sem algoritmo é impossível de migrar depois")
        if self.quando is not None and not isinstance(self.quando, str):
            # GUARDA DE REGRESSÃO. `Procedencia.quando` é `datetime`, e a
            # conversão para ISO é fácil de esquecer. Se um `datetime` passar
            # daqui, o erro aparece na gravação do recibo — com a trava ABERTA.
            raise TypeError(
                f"linhagem de {self.nome!r}: `quando` precisa ser str ISO-8601, "
                f"veio {type(self.quando).__name__}. O recibo serializa com "
                "json.dumps sem `default=`, e isso estouraria com a trava aberta")
        for campo in ("largura", "altura", "bytes_totais"):
            valor = getattr(self, campo)
            if valor is not None and valor <= 0:
                # Mesma invariante de `criativo.contrato.Asset`. Ela existe dos
                # dois lados de propósito: uma fronteira que aceita o que o
                # outro lado recusa é por onde "não medi" vira "medi e deu zero".
                raise ValueError(f"{campo}={valor!r}: medida ausente é None, nunca 0")
        if self.custo_usd is not None and self.custo_usd < 0:
            raise ValueError(f"custo_usd={self.custo_usd!r}: custo negativo não é ausência")

    @classmethod
    def desconhecida(cls, nome: str, papel: str) -> "Linhagem":
        """A linhagem de um arquivo que não passou pela ponte.

        Existe para que a lista de linhagens mantenha correspondência 1:1 com
        as `asset_operation` emitidas. Sem ela, uma imagem montada à mão faria
        a lista encurtar e a linhagem da imagem seguinte seria atribuída ao
        arquivo errado — que é pior que não ter linhagem nenhuma.
        """
        return cls(nome=nome, papel=papel)

    @property
    def confirmada(self) -> bool:
        """Sabemos quem gerou, de quê, quando, e o que exatamente é o arquivo?

        Procedência incompleta NÃO é procedência confirmada. Esta propriedade é
        o que impede que "carreguei alguns campos" seja lido como "a origem
        está estabelecida".
        """
        return all((
            self.identidade,
            self.conteudo_hash,
            self.motor,
            self.insumo,
            self.quando,
            self.mime,
            self.largura is not None,
            self.altura is not None,
        ))

    def confere(self, dados: bytes) -> bool:
        """Estes bytes são MESMO os que esta linhagem descreve?

        Devolve `False` quando a linhagem não declara hash — não se pode
        confirmar o que não foi afirmado, e `True` por omissão seria a
        aprovação por ausência que este módulo inteiro existe para recusar.

        ⚠️ O formato é o mesmo de `criativo.contrato.hash_de_conteudo`, e ele
        NÃO pode ser importado aqui: `brief.py` não conhece `criativo/`. As
        duas implementações são conferidas uma contra a outra por teste
        (`testes_display.test_confere_usa_o_mesmo_hash_do_criativo`) — é a
        mesma técnica que a casa já usa para `limites.yaml` × `requisitos.yaml`
        quando um número tem dois leitores.
        """
        if not self.conteudo_hash:
            return False
        return self.conteudo_hash == "sha256:" + hashlib.sha256(dados).hexdigest()

    def para_json(self) -> dict:
        """Dicionário JSON-serializável, com `confirmada` explícita.

        `dataclasses.asdict` não enxerga `@property`, e é `asdict` que o recibo
        usa. Sem este método, o recibo gravaria todos os campos e omitiria
        justamente o veredito — mesma razão pela qual `Recibo.para_json`
        acrescenta `nada_foi_criado` à mão.
        """
        import dataclasses as _dc
        d = _dc.asdict(self)
        d["confirmada"] = self.confirmada
        return d


_AUTORIDADE_RECIBO_ASSET = object()


@dataclass(frozen=True, init=False)
class ReciboAssetAprovado:
    """Recibo tipado emitido pela fronteira catálogo → campanha.

    ``Linhagem`` continua sendo o relato de procedência, mas não é autorização:
    qualquer chamador consegue instanciá-la. Este recibo só nasce pela função
    privada usada por :mod:`volc_ads.criativo_ponte`, depois de o lote passar
    pela régua do canal e de os bytes baterem com o catálogo. O builder confere
    novamente o recibo contra bytes, hash, mime, dimensões, papel e resource
    name antes de sequer construir um cliente Google.

    A autoridade em memória não pretende ser assinatura persistente. Ela evita
    autoatestado dentro deste processo sem inventar chave secreta ou serviço
    externo. Persistir/reidratar recibos de catálogo é outra capacidade e
    permanece recusada nesta onda.
    """

    VERSAO: ClassVar[str] = "volc.asset.aprovado.v1"
    EMISSOR: ClassVar[str] = "volc_ads.criativo_ponte"

    catalogo_id: str
    aprovacao_id: str
    canal: str
    nome: str
    papel: str
    conteudo_hash: str
    mime: str
    largura: int
    altura: int
    bytes_totais: int
    resource_name: str | None
    exigencia_fonte: str | None
    exigencia_provisoria: bool | None
    medidor_id: str
    linhagem: Linhagem
    _autoridade: object = field(repr=False, compare=False)

    @classmethod
    def _emitir(
        cls,
        *,
        catalogo_id: str,
        canal: str,
        nome: str,
        papel: str,
        conteudo_hash: str,
        mime: str,
        largura: int,
        altura: int,
        bytes_totais: int,
        resource_name: str | None,
        exigencia_fonte: str | None,
        exigencia_provisoria: bool | None,
        medidor_id: str,
        reconferidor,
        linhagem: Linhagem,
    ) -> "ReciboAssetAprovado":
        valores = {
            "catalogo_id": str(catalogo_id or "").strip(),
            "canal": str(canal or "").strip().upper(),
            "nome": str(nome or "").strip(),
            "papel": str(papel or "").strip(),
            "conteudo_hash": str(conteudo_hash or "").strip(),
            "mime": str(mime or "").strip().lower(),
            "largura": largura,
            "altura": altura,
            "bytes_totais": bytes_totais,
            "resource_name": (
                None if resource_name is None else str(resource_name).strip()
            ),
            "exigencia_fonte": exigencia_fonte,
            "exigencia_provisoria": exigencia_provisoria,
            "medidor_id": str(medidor_id or "").strip(),
            "linhagem": linhagem,
        }
        for campo in (
            "catalogo_id",
            "canal",
            "nome",
            "papel",
            "mime",
            "medidor_id",
        ):
            if not valores[campo]:
                raise ValueError(f"recibo de asset sem {campo}")
        if not valores["conteudo_hash"].startswith("sha256:"):
            raise ValueError("recibo de asset exige conteudo_hash sha256")
        for campo in ("largura", "altura", "bytes_totais"):
            if not isinstance(valores[campo], int) or valores[campo] <= 0:
                raise ValueError(
                    f"recibo de asset: {campo} precisa ser inteiro positivo"
                )
        if not isinstance(linhagem, Linhagem):
            raise TypeError("recibo de asset exige Linhagem tipada")
        if not callable(reconferidor):
            raise TypeError("recibo de asset exige reconferidor de bytes")

        obj = object.__new__(cls)
        for campo, valor in valores.items():
            object.__setattr__(obj, campo, valor)
        object.__setattr__(obj, "_autoridade", _AUTORIDADE_RECIBO_ASSET)
        # Não é campo do dataclass: recibos não são persistíveis nesta onda e
        # uma função jamais pode vazar para ``asdict``/JSON como se fosse dado.
        object.__setattr__(obj, "_reconferidor", reconferidor)
        object.__setattr__(obj, "aprovacao_id", obj._impressao_esperada())
        return obj

    def _material(self) -> dict:
        return {
            "versao": self.VERSAO,
            "emissor": self.EMISSOR,
            "catalogo_id": self.catalogo_id,
            "canal": self.canal,
            "nome": self.nome,
            "papel": self.papel,
            "conteudo_hash": self.conteudo_hash,
            "mime": self.mime,
            "largura": self.largura,
            "altura": self.altura,
            "bytes_totais": self.bytes_totais,
            "resource_name": self.resource_name,
            "exigencia_fonte": self.exigencia_fonte,
            "exigencia_provisoria": self.exigencia_provisoria,
            "medidor_id": self.medidor_id,
            "linhagem": self.linhagem.para_json(),
        }

    def _impressao_esperada(self) -> str:
        bruto = json.dumps(
            self._material(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(bruto).hexdigest()

    @property
    def integro(self) -> bool:
        """Foi emitido pela ponte desta execução e não mudou depois?"""
        return (
            self._autoridade is _AUTORIDADE_RECIBO_ASSET
            and callable(getattr(self, "_reconferidor", None))
            and self.aprovacao_id == self._impressao_esperada()
        )

    def _medir_bytes(
        self, dados: bytes
    ) -> tuple[str | None, int | None, int | None, int]:
        """Relê os bytes com o medidor que emitiu o recibo, sem import reverso."""
        medido = self._reconferidor(dados)
        if not isinstance(medido, tuple) or len(medido) != 4:
            raise TypeError("reconferidor de asset devolveu contrato inválido")
        mime, largura, altura, bytes_totais = medido
        return mime, largura, altura, bytes_totais


def _emitir_recibo_asset_aprovado(**campos) -> ReciboAssetAprovado:
    """Única fábrica do recibo; usada apenas por ``criativo_ponte``."""
    return ReciboAssetAprovado._emitir(**campos)


@dataclass(frozen=True)
class AssetRemotoDemandGen:
    """Asset já existente, acompanhado dos bytes e do recibo que o aprovou.

    ``ImageAsset.data`` não volta da API. Portanto, reusar um resource name sem
    conservar os bytes no catálogo torna impossível conferir hash, mime e
    geometria antes do validate-only. Esta forma exige os dois; ``str`` puro
    continua aceito em Display por compatibilidade, mas Demand Gen o recusa.
    """

    resource_name: str
    dados: bytes
    recibo: ReciboAssetAprovado

    def __post_init__(self) -> None:
        if not str(self.resource_name or "").strip():
            raise ValueError("asset remoto sem resource_name")
        if not self.dados:
            raise ValueError(
                "asset remoto sem bytes de catálogo: não é possível reconferir "
                "hash, mime ou dimensões"
            )
        if not isinstance(self.recibo, ReciboAssetAprovado):
            raise TypeError("asset remoto exige ReciboAssetAprovado tipado")

    @property
    def nome(self) -> str:
        return self.recibo.nome

    @property
    def linhagem(self) -> Linhagem:
        return self.recibo.linhagem


@dataclass(frozen=True)
class ImagemParaSubir:
    """Uma imagem que ainda NÃO existe na conta e nasce no mesmo mutate.

    ## Por que ela existe, e por que não é só um `resource_name`

    Um `resource_name` só pode ser passado depois que alguém criou o Asset — e
    criar Asset é escrita no Google Ads. Enquanto esse era o único caminho, o
    construtor de Display dependia de uma mutação anterior para poder montar o
    payload, e a montagem deixava de ser provável offline.

    `MutateOperation.asset_operation` desfaz isso: o Asset nasce na mesma
    requisição atômica, referenciado por id temporário. Não há duas fases, então
    não existe o estado "o asset subiu e a campanha não"; não há round-trip, então
    não existe "o upload deu timeout, criou?".

    ## O que ela carrega, e o que ela deliberadamente não carrega

    `dados` são os bytes — `ImageAsset.data` é **mutate-only** na API: sobe na
    criação e nunca volta na leitura.

    ## O que esta classe garante, e o que continua sendo do outro lado

    Os campos de medida (`mime`, `largura`, `altura`) continuam sendo
    **transportados, não conferidos** — quem confere geometria é
    `volc_ads/criativo/validacao.py`, e desde 27/08/2026 ele **tem chamador de
    produção**: `volc_ads/criativo_ponte.py` roda `validar_lote()` ANTES de
    existir qualquer `ImagemParaSubir`. Um lote reprovado não vira payload
    incompleto; ele não vira payload nenhum.

    Recusar aqui continuaria duplicando a régua do criativo, e por isso não se
    faz. O que o construtor de Display PODE afirmar sozinho é sobre a presença
    da linhagem: uma imagem com `linhagem is None` não passou pela ponte, e
    portanto nenhuma validação de geometria a cobriu. Isso vira **aviso**, com o
    caminho de volta nomeado — não erro, porque `display` não sabe geometria e
    não pode virar um segundo juiz dela.

    `None` continua sendo "ninguém mediu", nunca "está tudo bem".

    ## `linhagem` substituiu `procedencia: str`, e a troca foi deliberada

    O campo antigo era uma string de formato livre declarada como "carregada e
    não lida". Ele não tinha um único produtor nem consumidor no repositório —
    nem nos testes. Mantê-lo ao lado de `linhagem` seria a segunda declaração da
    mesma verdade, com precedência silenciosa entre as duas; o próprio docstring
    antigo dizia que ele existia "para o dia em que o recibo passar a registrar
    procedência de criativo". Esse dia é este commit, e o campo virou o que
    prometia ser: um fato estruturado que chega ao recibo.

    ⚠️ **Esta classe não importa `volc_ads/criativo/`.** Ela declara os campos de
    que o construtor precisa, e quem chama monta a partir de um
    `criativo.Asset`. O construtor de campanha não deve depender do pacote de
    criativo para montar um payload — são donos diferentes, e o acoplamento
    tornaria impossível testar um sem o outro.
    """

    #: Nome do Asset na conta. Aparece na biblioteca do Google Ads e é o que um
    #: humano vê depois; não tem valor semântico para o leilão.
    nome: str
    #: Os bytes da imagem.
    dados: bytes
    #: De onde este arquivo veio, estruturado. `None` quando a imagem foi
    #: montada à mão e ninguém apurou a origem — e o construtor avisa nesse caso.
    linhagem: Linhagem | None = None
    mime: str | None = None
    largura: int | None = None
    altura: int | None = None
    #: Aprovação emitida pela ponte. Opcional para preservar o contrato Display;
    #: o builder Demand Gen a exige e a reconfere antes do cliente.
    recibo_aprovacao: ReciboAssetAprovado | None = None

    def __post_init__(self) -> None:
        if not self.nome.strip():
            raise ValueError(
                "imagem sem nome: o nome é o que identifica o Asset na conta "
                "depois, e um Asset anônimo é impossível de reencontrar")
        if not self.dados:
            raise ValueError(
                f"imagem {self.nome!r} sem bytes. `ImageAsset.data` é o "
                "conteúdo; sem ele a API cria um asset vazio e o anúncio fica "
                "com um espaço em branco que ninguém vê até a revisão")
        for campo in ("largura", "altura"):
            valor = getattr(self, campo)
            if valor is not None and valor <= 0:
                # `criativo.contrato.Asset` recusa isto desde sempre; esta
                # classe aceitava. A assimetria era o buraco por onde um
                # `_medir()` que devolvesse `0,0` em vez de `None,None` faria
                # "não medi" virar "medi e deu zero" ao cruzar a fronteira.
                raise ValueError(
                    f"imagem {self.nome!r}: {campo}={valor!r} — medida ausente "
                    "é None, nunca 0")


_MIME_CANONICO = {"image/jpg": "image/jpeg", "image/pjpeg": "image/jpeg"}


def _mime_canonico(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpo = str(valor).split(";", 1)[0].strip().lower()
    if not limpo:
        return None
    return _MIME_CANONICO.get(limpo, limpo)


def conferir_asset_demand_gen(
    item: ImagemParaSubir | AssetRemotoDemandGen,
    *,
    papel: str,
    customer_id: str,
) -> tuple[str, ...]:
    """Reconfere o recibo contra o objeto que entraria no proto.

    A função vive no contrato para preservar a direção de dependência:
    ``criativo_ponte`` emite o recibo e injeta seu medidor local, enquanto o
    builder conhece apenas ``brief``. Assim não nasce o ciclo campanha → ponte
    → campanha e a régua continua sendo a que aprovou o asset.
    """
    erros: list[str] = []
    if isinstance(item, ImagemParaSubir):
        recibo = item.recibo_aprovacao
        dados = item.dados
        resource_name = None
        nome = item.nome
        linhagem = item.linhagem
        mime_declarado = item.mime
        largura_declarada = item.largura
        altura_declarada = item.altura
    elif isinstance(item, AssetRemotoDemandGen):
        recibo = item.recibo
        dados = item.dados
        resource_name = item.resource_name
        nome = item.nome
        linhagem = item.linhagem
        mime_declarado = recibo.mime
        largura_declarada = recibo.largura
        altura_declarada = recibo.altura
    else:  # pragma: no cover - o chamador tipado barra antes
        return (f"forma de asset não suportada: {type(item).__name__}",)

    if not isinstance(recibo, ReciboAssetAprovado):
        return (
            "sem ReciboAssetAprovado emitido pela fronteira de catálogo; "
            "Linhagem preenchida pelo chamador não é aprovação",
        )
    if not recibo.integro:
        erros.append(
            "recibo não foi emitido pela ponte desta execução ou foi alterado"
        )
    if recibo.canal != "DEMAND_GEN":
        erros.append(f"recibo é do canal {recibo.canal!r}, não DEMAND_GEN")
    if recibo.papel != papel:
        erros.append(f"recibo aprovou papel {recibo.papel!r}, não {papel!r}")
    if recibo.nome != nome:
        erros.append(f"recibo nomeia {recibo.nome!r}, objeto nomeia {nome!r}")
    if recibo.resource_name != resource_name:
        erros.append(
            "resource_name diverge do recibo: "
            f"{resource_name!r} != {recibo.resource_name!r}"
        )
    if resource_name is not None and not str(resource_name).startswith(
        f"customers/{customer_id}/assets/"
    ):
        erros.append(
            f"asset remoto não está na conta {customer_id}: {resource_name!r}"
        )

    recomputado = "sha256:" + hashlib.sha256(dados).hexdigest()
    if recomputado != recibo.conteudo_hash:
        erros.append(
            "bytes/hash divergentes: o conteúdo atual não é o aprovado no catálogo"
        )
    if recibo.bytes_totais != len(dados):
        erros.append(
            "bytes_totais divergente: recibo "
            f"{recibo.bytes_totais}, atual {len(dados)}"
        )

    try:
        mime_medido, largura_medida, altura_medida, bytes_medidos = (
            recibo._medir_bytes(dados)
        )
    except Exception as exc:  # noqa: BLE001 — medidor incompatível recusa capacidade
        erros.append(
            "não foi possível reconferir mime/dimensões dos bytes com "
            f"{recibo.medidor_id}: {type(exc).__name__}: {exc}"
        )
        mime_medido = largura_medida = altura_medida = None
        bytes_medidos = -1
    if mime_medido is None or largura_medida is None or altura_medida is None:
        erros.append("bytes atuais não têm mime/dimensões de imagem corroboráveis")
    else:
        if _mime_canonico(recibo.mime) != _mime_canonico(mime_medido):
            erros.append(
                f"mime divergente: recibo {recibo.mime!r}, bytes {mime_medido!r}"
            )
        if (recibo.largura, recibo.altura) != (
            largura_medida,
            altura_medida,
        ):
            erros.append(
                "dimensões divergentes: recibo "
                f"{recibo.largura}x{recibo.altura}, bytes "
                f"{largura_medida}x{altura_medida}"
            )
    if bytes_medidos != len(dados):
        erros.append(
            f"medidor contou {bytes_medidos} bytes, objeto carrega {len(dados)}"
        )

    if _mime_canonico(mime_declarado) != _mime_canonico(recibo.mime):
        erros.append("mime transportado diverge do recibo")
    if (largura_declarada, altura_declarada) != (
        recibo.largura,
        recibo.altura,
    ):
        erros.append("dimensões transportadas divergem do recibo")

    if linhagem is None:
        erros.append("recibo sem Linhagem correspondente")
    else:
        if linhagem is not recibo.linhagem and linhagem != recibo.linhagem:
            erros.append("Linhagem transportada diverge da que o recibo aprovou")
        if linhagem.nome != recibo.nome:
            erros.append("nome da Linhagem diverge do recibo")
        if linhagem.papel != papel:
            erros.append("papel da Linhagem diverge do slot")
        if linhagem.identidade != recibo.catalogo_id:
            erros.append("identidade de catálogo da Linhagem diverge do recibo")
        if linhagem.conteudo_hash != recibo.conteudo_hash:
            erros.append("hash da Linhagem diverge do recibo")
        if _mime_canonico(linhagem.mime) != _mime_canonico(recibo.mime):
            erros.append("mime da Linhagem diverge do recibo")
        if (linhagem.largura, linhagem.altura) != (
            recibo.largura,
            recibo.altura,
        ):
            erros.append("dimensões da Linhagem divergem do recibo")
        if linhagem.bytes_totais != recibo.bytes_totais:
            erros.append("quantidade de bytes da Linhagem diverge do recibo")
        if linhagem.id_externo != resource_name:
            erros.append("id externo da Linhagem diverge do resource_name")
        if linhagem.exigencia_fonte != recibo.exigencia_fonte:
            erros.append("fonte de aprovação da Linhagem diverge do recibo")
        if linhagem.exigencia_provisoria != recibo.exigencia_provisoria:
            erros.append("estado provisório da aprovação diverge do recibo")

    return tuple(erros)


@dataclass(frozen=True)
class RedeDePesquisa:
    """Onde a campanha Search pode aparecer — declarado, nunca herdado.

    ## Por que isto existe

    `comum.py` ligava `target_search_network = True` como literal. Search
    Partners é inventário DIFERENTE do Google Search: outros sites, outro
    comportamento de consulta, outro CPC efetivo. Ele estava ligado em toda
    campanha Search da casa sem o operador escolher, sem aparecer no plano
    aprovado e sem entrar em nenhuma tela — a matriz de cobertura v25 já
    registrava isso como "efeito invisível".

    O defeito não era o valor `True`. Era ele não ser decisão de ninguém.

    ## Por que é frozen

    A rede entra no protobuf e portanto na impressão do payload. Um objeto
    mutável deixaria alguém trocar a rede DEPOIS do selo, e o selo continuaria
    conferindo — a autorização humana passaria a cobrir algo que o humano não
    viu. Para mudar, `dataclasses.replace()`, que devolve outro objeto.
    """

    google_search: bool
    search_partners: bool
    display_expansion: bool

    def __post_init__(self) -> None:
        if not self.google_search:
            raise ValueError(
                "uma campanha SEARCH sem `google_search` não é uma campanha "
                "Search. Se a intenção é outro canal, escolha outro canal."
            )
        if self.display_expansion:
            # A expansão para Display muda o inventário sem mudar o tipo da
            # campanha — é a forma mais silenciosa de sair da rede de pesquisa.
            # Ela não é proibida para sempre; é proibida enquanto ninguém tiver
            # escrito o que ela significa para verba, lance e medição.
            raise ValueError(
                "`display_expansion` ainda não tem contrato declarado no VOLC "
                "O.S.: ela troca o inventário sem trocar o tipo da campanha. "
                "Deixe False até existir decisão escrita."
            )

    def para_json(self) -> dict[str, bool]:
        return {
            "google_search": self.google_search,
            "search_partners": self.search_partners,
            "display_expansion": self.display_expansion,
        }


#: O que o builder fazia antes de a rede virar decisão. Parceiros LIGADOS.
#:
#: ⚠️ Não "corrija" esta constante para `search_partners=False`. Ela existe
#: para que campanhas antigas continuem nascendo exatamente como nasciam; mudar
#: o valor aqui alteraria em silêncio o alcance de todo brief que não declara
#: rede, que é o oposto do conserto. A aposentadoria dela é migrar os chamadores
#: para `rede` explícita e então remover o ramo — não reescrevê-la.
REDE_LEGADA_SEARCH = RedeDePesquisa(
    google_search=True, search_partners=True, display_expansion=False
)


@dataclass
class ImagensDisplay:
    """Assets de imagem do responsive display ad, POR PAPEL.

    ## Por que `Brief.imagens` (lista chapada) não serve aqui

    `imagens: list[str]` carrega resource names de Asset já criados — e um
    resource name (`customers/123/assets/456`) não diz proporção nenhuma. O
    `ResponsiveDisplayAdInfo` tem QUATRO campos de imagem, e cada um exige uma
    geometria diferente (v25, `common/types/ad_type_infos.py`):

        marketing_images         1.91:1  mín 600x314   ≥1 obrigatória
        square_marketing_images  1:1     mín 300x300   ≥1 obrigatória
        logo_images              4:1     mín 512x128
        square_logo_images       1:1     mín 128x128

    Adivinhar o papel a partir da ordem da lista subiria a imagem quadrada no
    campo do banner: a API recusaria o mutate inteiro por proporção, e o erro
    apontaria para o anúncio, não para quem montou a lista. Descobrir o papel
    lendo o Asset na API custa uma chamada de leitura por imagem e, pior, torna
    a montagem do payload dependente de rede.

    Por isso o papel é DECLARADO. É este o contrato com o motor de criativo
    (`volc_ads/criativo/`, outro dono): ele cria os assets e devolve os
    resource names já separados por papel.

    ## Duas formas por papel, e as duas contam igual nos tetos

    Cada lista aceita `str` — resource name de Asset **já criado** — ou
    `ImagemParaSubir`, um asset que nasce no mesmo mutate atômico. Misturar as
    duas na mesma lista é legítimo: uma campanha pode reaproveitar o banner que
    já está na conta e subir o quadrado novo.

    O que a API vê é o número de imagens no anúncio; de onde cada uma veio não
    muda o teto combinado de 15 (marketing) nem o de 5 (logo).
    """

    #: A ORDEM CANÔNICA dos papéis, declarada em UM lugar só.
    #:
    #: Ela já existia — dentro de `display.PAPEIS_DE_IMAGEM` — e é a ordem em
    #: que as `asset_operation` são emitidas no mutate, e portanto a ordem dos
    #: ids temporários -200, -201, … Quem quiser percorrer as imagens na mesma
    #: ordem do payload (o recibo, por exemplo) precisa desta sequência; se
    #: refizesse a caminhada com um laço próprio, existiriam duas declarações
    #: da mesma ordem, e a divergência só apareceria no dia em que o recibo
    #: atribuísse a procedência da logo ao banner.
    PAPEIS: ClassVar[tuple[str, ...]] = (
        "marketing", "marketing_quadrada", "logo", "logo_quadrado",
    )

    #: 1.91:1 — o banner. Pelo menos uma; combinada com as quadradas, teto 15.
    marketing: list[str | ImagemParaSubir] = field(default_factory=list)
    #: 1:1 — o quadrado. Pelo menos uma; mesmo teto combinado de 15.
    marketing_quadrada: list[str | ImagemParaSubir] = field(default_factory=list)
    #: 4:1 — a logo larga. Combinada com a quadrada, teto 5.
    logo: list[str | ImagemParaSubir] = field(default_factory=list)
    #: 1:1 — a logo quadrada. Mesmo teto combinado de 5.
    logo_quadrado: list[str | ImagemParaSubir] = field(default_factory=list)

    @property
    def todas(self) -> list[str | ImagemParaSubir]:
        # ⚠️ A anotação já disse `list[str]` e era falsa: estas listas carregam
        # as duas formas desde que `ImagemParaSubir` existe.
        return [item for papel in self.PAPEIS for item in getattr(self, papel)]

    def linhagens(self) -> tuple[Linhagem, ...]:
        """A procedência de cada imagem NOVA, na ordem em que ela entra no mutate.

        Correspondência 1:1 com as `asset_operation` emitidas por
        `display.construir`: mesma ordem de papel, mesma ordem dentro do papel,
        e **nada** para os `str` — um resource name é asset que já existe na
        conta, criado por outra rodada, e esta lista descreve o que nasce agora.

        Uma imagem sem linhagem entra como `Linhagem.desconhecida(...)` em vez
        de ser pulada. Pular encurtaria a lista e faria a linhagem da imagem
        seguinte ser atribuída ao arquivo errado — um rastro deslocado é pior
        que rastro ausente, porque parece um rastro.
        """
        saida: list[Linhagem] = []
        for papel in self.PAPEIS:
            for item in getattr(self, papel):
                if not isinstance(item, ImagemParaSubir):
                    continue
                saida.append(
                    item.linhagem
                    if item.linhagem is not None
                    else Linhagem.desconhecida(item.nome, papel)
                )
        return tuple(saida)


@dataclass
class ImagensDemandGen:
    """Imagens do anúncio multi-asset de Demand Gen, separadas por papel.

    Demand Gen não é Display renomeado: acrescenta retrato 4:5 e retrato alto
    9:16, usa somente logo quadrado e divide um teto combinado próprio entre
    as quatro orientações de marketing. A ordem abaixo é também a ordem dos
    ``asset_operation`` e das linhagens no recibo.
    """

    PAPEIS: ClassVar[tuple[str, ...]] = (
        "marketing",
        "marketing_quadrada",
        "marketing_retrato",
        "marketing_retrato_alto",
        "logo_quadrado",
    )

    marketing: list[str | ImagemParaSubir | AssetRemotoDemandGen] = field(
        default_factory=list
    )
    marketing_quadrada: list[
        str | ImagemParaSubir | AssetRemotoDemandGen
    ] = field(default_factory=list)
    marketing_retrato: list[
        str | ImagemParaSubir | AssetRemotoDemandGen
    ] = field(default_factory=list)
    marketing_retrato_alto: list[
        str | ImagemParaSubir | AssetRemotoDemandGen
    ] = field(default_factory=list)
    logo_quadrado: list[str | ImagemParaSubir | AssetRemotoDemandGen] = field(
        default_factory=list
    )

    @property
    def todas(self) -> list[str | ImagemParaSubir | AssetRemotoDemandGen]:
        return [item for papel in self.PAPEIS for item in getattr(self, papel)]

    def linhagens(self) -> tuple[Linhagem, ...]:
        saida: list[Linhagem] = []
        for papel in self.PAPEIS:
            for item in getattr(self, papel):
                if isinstance(item, ImagemParaSubir):
                    saida.append(
                        item.linhagem
                        if item.linhagem is not None
                        else Linhagem.desconhecida(item.nome, papel)
                    )
                elif isinstance(item, AssetRemotoDemandGen):
                    saida.append(item.linhagem)
        return tuple(saida)


ESTRATEGIAS_DE_CANAL_DEMAND_GEN: tuple[str, ...] = (
    "ALL_CHANNELS",
    "ALL_OWNED_AND_OPERATED_CHANNELS",
    "SELECTED_CHANNELS",
)

CANAIS_SELECIONAVEIS_DEMAND_GEN: tuple[str, ...] = (
    "youtube_in_stream",
    "youtube_in_feed",
    "youtube_shorts",
    "discover",
    "gmail",
    "display",
    "maps",
)


@dataclass(frozen=True)
class ControlesDeCanalDemandGen:
    """O ``oneof`` de canais de Demand Gen, sem recorrer ao default remoto.

    ``selected_channels`` só existe quando a estratégia o pede. ``None`` é
    ausência; conjunto vazio seria uma seleção confirmada porém inválida e é
    recusado em vez de virar implicitamente "todos".
    """

    estrategia: str
    selected_channels: frozenset[str] | None

    def __post_init__(self) -> None:
        if self.estrategia not in ESTRATEGIAS_DE_CANAL_DEMAND_GEN:
            raise ValueError(
                f"estratégia de canais Demand Gen {self.estrategia!r} inválida; "
                f"use {', '.join(ESTRATEGIAS_DE_CANAL_DEMAND_GEN)}"
            )
        if self.estrategia == "SELECTED_CHANNELS":
            if self.selected_channels is None:
                raise ValueError(
                    "SELECTED_CHANNELS exige `selected_channels`; ausência não "
                    "pode virar seleção vazia nem todos os canais"
                )
            if not self.selected_channels:
                raise ValueError(
                    "SELECTED_CHANNELS exige ao menos um canal verdadeiro"
                )
            desconhecidos = sorted(
                set(self.selected_channels) - set(CANAIS_SELECIONAVEIS_DEMAND_GEN)
            )
            if desconhecidos:
                raise ValueError(
                    f"canais Demand Gen desconhecidos: {desconhecidos}; use "
                    f"{', '.join(CANAIS_SELECIONAVEIS_DEMAND_GEN)}"
                )
        elif self.selected_channels is not None:
            raise ValueError(
                f"{self.estrategia} ocupa o outro ramo do oneof; "
                "`selected_channels` precisa ser ausência (None), não uma lista"
            )


@dataclass(frozen=True)
class ConfiguracaoDemandGen:
    """Escolhas perigosas e superfícies de segmentação do primeiro builder.

    Todos os campos são obrigatórios no construtor, inclusive os que podem ser
    listas vazias. Assim ``None`` continua significando "não informado" e
    ``()`` significa "confirmado vazio". Audiência, intenção e exclusão são
    conceitos distintos e nunca dividem uma lista genérica.
    """

    upgraded_targeting: bool | None
    controles_de_canal: ControlesDeCanalDemandGen | None
    audiencias: tuple[str, ...] | None
    intencoes: tuple[str, ...] | None
    exclusoes_de_audiencia: tuple[str, ...] | None

    def __post_init__(self) -> None:
        if self.upgraded_targeting is not None and not isinstance(
            self.upgraded_targeting, bool
        ):
            raise TypeError(
                "upgraded_targeting precisa ser bool explícito ou None; 0/1 "
                "não substituem a escolha imutável"
            )


# Nome do grupo sintético que `Brief.grupos()` devolve quando o brief não
# declara sub-intenção nenhuma. Não é rótulo de exibição: é o sinal, legível
# em um lugar só, de que o ad group deve manter o nome histórico do payload
# de quando existia um grupo apenas.
SEM_SUB_INTENCAO = "—"


@dataclass
class SubIntencao:
    """Um grupo de keywords que respondem à MESMA pergunta. Vira um ad group.

    Não é uma invenção deste módulo: `funis_sugeridos[].sub_intencoes` do
    Pautador já entrega os grupos TIPADOS, com keywords, volume e CPC por
    grupo. Medido no cluster do `opportunity_id 73` (linha 4 de
    `pautador_keyword_clusters`, 18/08/2026):

        ACESSO         7 kw · volume 31.030 · CPC minerado 0,74
        ELEGIBILIDADE 26 kw · volume 11.580 · CPC minerado 1,09
        VALOR          5 kw · volume  1.980 · CPC minerado 1,50
        OUTROS         5 kw · volume    530 · CPC minerado 0,16

    Spread de 9× entre o mais barato e o mais caro. Num ad group só, isso é um
    lance só para os quatro — caro demais para ACESSO e barato demais para
    VALOR ao mesmo tempo.

    ⚠️ Aqueles CPCs são MINERADOS, não da conta. `DATAFORSEO-MEDIDO.md` mediu,
    com 96 chamadas, que `keyword_info.cpc` superestima o CPC real em 7,4× e
    INVERTE a ordem dentro do cluster. Portanto: use-os para separar grupos
    (a separação é estrutural e sobrevive ao erro de escala), nunca para
    calcular `cpc_inicial` — quem preenche esse campo é o operador, com o CPC
    da própria conta.
    """

    nome: str
    keywords: list[str] = field(default_factory=list)
    # None = herda o do brief. Preencher só com CPC medido na conta.
    cpc_inicial: float | None = None
    tcpa: float | None = None
    # negativas SÓ deste grupo; as de `brief.negativas_adgroup` valem em todos
    negativas: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.nome.strip():
            raise ValueError("sub-intenção sem nome — o nome vira o do ad group")


@dataclass
class Brief:
    nicho: str
    slug: str
    url_final: str
    keywords: list[str]
    copy: Copy

    pais: str = "BR"
    idioma: str = "pt"
    budget_diario: float = 10.0
    cpc_inicial: float = 0.12
    tcpa: float | None = None
    conversao: str = ""          # nome da ação de conversão (p/ custom goal)
    prefixo_nome: str = "FORGE"
    # Congelado pela prova quando o plano será aprovado em outra requisição.
    # Ausente preserva o comportamento histórico dos chamadores locais.
    carimbo_nome: str | None = None

    # ⚠️ MANUAL_CPC é o padrão da casa, e a razão é de leilão, não de gosto:
    # sob `maximize_conversions` a API aceita `cpc_bid_micros` e o IGNORA na
    # veiculação — quem decide o lance é o modelo. Nascer em automático sem
    # histórico entrega o leilão a um modelo que ainda não tem o que aprender.
    # A doutrina medida (`GOOGLE ADS - New Campaigns Validation`, nó `Code1`) é
    # nascer manual e graduar em 30 conversões.
    #
    # Só vale para SEARCH. Display e Demand Gen não têm CPC manual como opção
    # razoável e continuam em MaxConv/tCPA.
    estrategia_lance: str = "MANUAL_CPC"   # MANUAL_CPC | MAXIMIZE_CONVERSIONS

    # ⚠️ ONDE O ANÚNCIO APARECE — decisão, e não default do builder.
    #
    # `None` significa "este chamador é antigo e herda `REDE_LEGADA_SEARCH`",
    # que tem PARCEIROS LIGADOS. Isso é compatibilidade deliberada: mudar o
    # default aqui alteraria em silêncio toda campanha já criada pela casa.
    #
    # O que mudou é que o estado legado deixou de ser um literal perdido dentro
    # de `comum.py` e virou constante nomeada — citável, testável e com
    # aposentadoria possível. Quem declara `rede` decide, e a decisão viaja até
    # o protobuf, o selo e o dossiê.
    rede: "RedeDePesquisa | None" = None

    # ⚠️ `match_type` é o match type PADRÃO do brief, não mais o único. Quem
    # declara `criterios` escolhe um por keyword; este campo só preenche a
    # lacuna de quem ainda entrega `list[str]`. Ver `criterio.de_lista`.
    match_type: str = "PHRASE"          # EXACT | PHRASE | BROAD
    negativas_campanha: list[str] = field(default_factory=list)
    negativas_adgroup: list[str] = field(default_factory=list)

    # O contrato TIPADO — positivas e negativas com match type, nível, grupo,
    # origem, motivo e evidência próprios. Vazio significa "este chamador ainda
    # fala o contrato antigo": `__post_init__` monta a lista canônica a partir
    # de `keywords`/`sub_intencoes`/`negativas_*` pelo adaptador explícito, e
    # daí para a frente existe UMA fonte de verdade — esta.
    #
    # Preenchido, ele é a verdade, e os campos de negativa antigos precisam
    # estar vazios: aceitar os dois criaria precedência silenciosa, que é o
    # mesmo defeito que `keywords` × `sub_intencoes` já barra logo abaixo.
    criterios: list[Criterio] = field(default_factory=list)

    # Um ad group por sub-intenção. Vazio = um ad group só, com `keywords`.
    sub_intencoes: list[SubIntencao] = field(default_factory=list)

    # `vertical` não é rótulo decorativo: é o eixo do portão de habilitação de
    # `policy/spec.py` (país × vertical) e o que decide se "empréstimo" é termo
    # REGULADO (financeiro, exige divulgação) ou DETURPAÇÃO (informativo, o
    # site não presta o serviço). Verticais com portão declarado no spec.json:
    # financeiro, governo_documentos, saude, jogos_azar.
    vertical: str = "informativo"
    # O que a CONTA comprova ter — ex.: {"verificacao_servicos_financeiros"}.
    # Vazio é o default seguro: sem certificação declarada, a vertical que a
    # exige neste país BARRA o mutate em vez de torcer para passar.
    certificacoes: set[str] = field(default_factory=set)
    ai_max: bool = False

    # imagens/vídeos próprios, por resource_name de Asset já criado
    imagens: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    # ⚠️ Display precisa das imagens SEPARADAS POR PAPEL — `imagens` acima não
    # carrega a proporção, e o RDA tem quatro campos de imagem com geometrias
    # diferentes. Ver `ImagensDisplay`. Vazio em brief de Search: o RSA não tem
    # imagem, e exigir o campo lá seria pedir dado para não usar.
    imagens_display: ImagensDisplay | None = None
    # Demand Gen tem contrato próprio: quatro orientações de marketing e logo
    # quadrado. Reusar `imagens_display` perderia 4:5/9:16 e aceitaria logo 4:1
    # num campo que o anúncio multi-asset não possui.
    imagens_demand_gen: ImagensDemandGen | None = None

    # Escolhas imutáveis, channel controls e segmentação de Demand Gen. Vazio
    # nos outros canais; no builder de Demand Gen a ausência é uma recusa.
    demand_gen: ConfiguracaoDemandGen | None = None

    # ── marcação de URL ─────────────────────────────────────────────────────
    # O contrato completo vive em `marcacao.py` e é montado por canal; aqui só
    # ficam as duas exceções que dependem da CONTA, não da campanha.
    #
    # `marcacao_gclid` só deve ser True se `customer.auto_tagging_enabled` for
    # False. Com auto-tagging ligado o Google já anexa o gclid, e declarar a
    # macro duplica o parâmetro — `marcacao.validar()` recusa.
    marcacao_gclid: bool = False
    marcacao_extra: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Resolve contra a fonte: 219 países, 151 idiomas. Levanta ValueError
        # com mensagem acionável se o par for inválido ou não segmentável.
        self._pais, self._idioma = _geo.resolver(self.pais, self.idioma)
        if self.budget_diario <= 0:
            raise ValueError("budget_diario precisa ser positivo")
        if not self.url_final.startswith("https://"):
            raise ValueError("url_final precisa ser https")
        if self.match_type not in ("EXACT", "PHRASE", "BROAD"):
            raise ValueError(f"match_type {self.match_type!r} inválido")
        if self.estrategia_lance not in ("MANUAL_CPC", "MAXIMIZE_CONVERSIONS"):
            raise ValueError(
                f"estrategia_lance {self.estrategia_lance!r} inválida — "
                "use MANUAL_CPC ou MAXIMIZE_CONVERSIONS"
            )
        # BROAD sem lance automático não tem sinal de leilão que filtre a
        # consulta: o Google recomenda broad apenas com Smart Bidding. Deixar
        # passar significa comprar consulta larga com lance cego.
        if self.estrategia_lance == "MANUAL_CPC" and self.match_type == "BROAD":
            raise ValueError(
                "BROAD com MANUAL_CPC não tem sinal de leilão que filtre a "
                "consulta. Use PHRASE agora e libere BROAD na graduação para "
                "MAXIMIZE_CONVERSIONS."
            )
        self._checar_keywords_ou_sub_intencoes()
        self._resolver_criterios()

    # ── contrato tipado ─────────────────────────────────────────────────────

    def _resolver_criterios(self) -> None:
        """Monta a lista canônica de critérios — a ÚNICA daqui para a frente.

        Três caminhos, e o resultado dos três é a mesma estrutura:

        1. Chamador antigo (`keywords`/`sub_intencoes` + `negativas_*`): o
           adaptador converte tudo, herdando `self.match_type` nas positivas e
           `BROAD` nas negativas — que é EXATAMENTE o que `search.py` fazia
           hardcoded antes.

           ⚠️ A compatibilidade é comportamental, mas NÃO é byte a byte em dois
           casos, e os dois são deliberados:

           - **negativa inválida agora BARRA em vez de sumir.** Antes, uma
             negativa com 90 caracteres ou 12 palavras era descartada em
             silêncio e a campanha subia sem ela. Trocar "descarte mudo" por
             "erro visível" é o ponto desta entrega — mas quem chama com uma
             negativa inválida recebe uma recusa onde antes recebia sucesso, e
             precisa corrigir a lista.
           - **duplicata entre `negativas_adgroup` e `SubIntencao.negativas`**
             agora sai com um aviso nomeando qual sobreviveu; antes era
             removida sem uma linha.

        2. Chamador novo (`criterios` preenchido): a lista é a verdade.

        3. Misto (`criterios` com positivas, negativas ainda no campo antigo):
           permitido, porque a migração acontece por partes. O que NÃO é
           permitido é declarar a mesma coisa nos dois lugares.
        """
        tipados = list(self.criterios)
        tem_pos = any(not c.negativa for c in tipados)
        tem_neg = any(c.negativa for c in tipados)

        legado_neg = bool(
            self.negativas_campanha
            or self.negativas_adgroup
            or any(s.negativas for s in self.sub_intencoes)
        )
        if tem_neg and legado_neg:
            raise ValueError(
                "negativas declaradas nos dois contratos: `criterios` já traz "
                "negativas e `negativas_campanha`/`negativas_adgroup`/"
                "`SubIntencao.negativas` também. Escolha um — com os dois, a "
                "precedência seria silenciosa e uma das listas sumiria do "
                "payload sem aviso."
            )

        saida: list[Criterio] = list(tipados)

        # Positivas tipadas precisam COBRIR as declaradas na estrutura. Sem
        # esta checagem, uma keyword que estivesse em `sub_intencoes` mas não
        # em `criterios` seria descartada em silêncio — a campanha subiria sem
        # ela e nada no payload denunciaria a falta. É a mesma doutrina do
        # portão `keywords` × `sub_intencoes`, aplicada um nível acima.
        if tem_pos:
            from .criterio import chave as _chave

            declaradas = {
                _chave(k) for sub in self.grupos() for k in sub.keywords
            }
            cobertas = {c.chave for c in tipados if not c.negativa}
            faltando = sorted(declaradas - cobertas)
            if faltando:
                raise ValueError(
                    f"`criterios` traz positivas mas não cobre {len(faltando)} "
                    f"keyword(s) declarada(s) na estrutura: {faltando[:5]}"
                    f"{'…' if len(faltando) > 5 else ''}. Keyword fora do "
                    "contrato tipado seria descartada em silêncio."
                )
            # E a recíproca, que é a mais perigosa das duas: positiva tipada que
            # NÃO está na estrutura entraria no ad group sem ninguém ter pedido.
            #
            # O caminho concreto: `Escolha.keywords_fora` (o que o operador
            # DESMARCOU) filtra `cockpit.grupos` na montagem, mas não filtra
            # `criterios`. Sem esta checagem, uma keyword desmarcada voltaria
            # pelo contrato tipado — e como um critério sem grupo vale em TODOS
            # os grupos, ela entraria em todos eles. A campanha compraria um
            # termo que o operador tirou, e nada no payload denunciaria.
            sobrando = sorted(cobertas - declaradas)
            if sobrando:
                raise ValueError(
                    f"`criterios` traz {len(sobrando)} positiva(s) que não estão "
                    f"na estrutura do brief: {sobrando[:5]}"
                    f"{'…' if len(sobrando) > 5 else ''}. Keyword que não foi "
                    "declarada em `keywords`/`sub_intencoes` entraria no ad "
                    "group sem ninguém ter pedido."
                )

        # Positivas: só derivadas do contrato antigo se o novo não as trouxe.
        if not tem_pos:
            for sub in self.grupos():
                grupo = None if sub.nome == SEM_SUB_INTENCAO else sub.nome
                saida.extend(
                    de_lista(
                        sub.keywords,
                        match_type=self.match_type,
                        negativa=False,
                        nivel="AD_GROUP",
                        grupo=grupo,
                    )
                )

        # Negativas do contrato antigo. BROAD porque era o que o construtor
        # aplicava: mudar o default aqui alteraria em silêncio o alcance das
        # negativas de toda campanha já em produção que ainda usa `list[str]`.
        if legado_neg:
            saida.extend(
                de_lista(
                    self.negativas_campanha,
                    match_type="BROAD", negativa=True, nivel="CAMPAIGN",
                )
            )
            saida.extend(
                de_lista(
                    self.negativas_adgroup,
                    match_type="BROAD", negativa=True, nivel="AD_GROUP",
                )
            )
            for sub in self.sub_intencoes:
                saida.extend(
                    de_lista(
                        sub.negativas,
                        match_type="BROAD", negativa=True,
                        nivel="AD_GROUP", grupo=sub.nome,
                    )
                )

        # Um critério de grupo tem de apontar para um grupo que existe. Sem
        # esta checagem, um nome com erro de digitação vira negativa que não
        # entra em ad group nenhum e some do payload sem uma linha de aviso.
        nomes = {s.nome.strip().casefold() for s in self.grupos()}
        for c in saida:
            if c.grupo is not None and c.grupo.strip().casefold() not in nomes:
                raise ValueError(
                    f"critério {c.texto!r} aponta para o grupo {c.grupo!r}, que "
                    f"não existe neste brief (grupos: {sorted(nomes)})"
                )

        # A doutrina do leilão vale POR KEYWORD, e não só pelo default do
        # brief. O portão acima checa `self.match_type`; sem esta segunda
        # passagem, uma positiva BROAD declarada individualmente entraria sob
        # MANUAL_CPC pela porta dos fundos — comprando consulta larga com lance
        # cego, que é exatamente o que aquele portão existe para impedir.
        #
        # Só as POSITIVAS: negativa BROAD não compra consulta nenhuma, ela
        # bloqueia — e o alcance largo de uma negativa é escolha legítima.
        if self.estrategia_lance == "MANUAL_CPC":
            largas = [
                c.texto for c in saida if not c.negativa and c.match_type == "BROAD"
            ]
            if largas:
                raise ValueError(
                    f"{len(largas)} keyword(s) em BROAD com MANUAL_CPC "
                    f"({largas[:3]}): broad sem Smart Bidding não tem sinal de "
                    "leilão que filtre a consulta. Use PHRASE agora e libere "
                    "BROAD na graduação para MAXIMIZE_CONVERSIONS."
                )

        self.criterios = saida

    def criterios_do_grupo(self, nome: str) -> list[Criterio]:
        """Critérios de ad group que valem no grupo `nome`.

        Inclui os que não declaram grupo — eles valem em todos, que é a
        semântica histórica de `negativas_adgroup`.
        """
        return [c for c in self.criterios if c.em_grupo(nome)]

    def _checar_keywords_ou_sub_intencoes(self) -> None:
        """As duas formas de declarar keywords são EXCLUSIVAS.

        Aceitar as duas ao mesmo tempo criaria duas fontes de verdade com
        precedência silenciosa: uma keyword que estivesse só em `keywords` não
        entraria em ad group nenhum, a campanha subiria sem ela e nada no
        payload denunciaria a falta. Barrar na construção custa uma linha.
        """
        if self.keywords and self.sub_intencoes:
            raise ValueError(
                "declare `keywords` OU `sub_intencoes`, nunca os dois: com os "
                "dois preenchidos, keyword fora de qualquer sub-intenção seria "
                "descartada em silêncio. Para um ad group só, use `keywords`; "
                "para um ad group por sub-intenção, mova TODAS para lá e deixe "
                "`keywords=[]`."
            )
        if not self.keywords and not self.sub_intencoes and self.demand_gen is None:
            raise ValueError(
                "brief sem keyword: preencha `keywords`/`sub_intencoes` ou o "
                "contrato `demand_gen`; ausência não escolhe um canal"
            )

        vistos: set[str] = set()
        for s in self.sub_intencoes:
            # Nome duplicado daria dois ad groups homônimos na mesma campanha:
            # legais para a API, indistinguíveis em qualquer relatório depois.
            chave = s.nome.strip().casefold()
            if chave in vistos:
                raise ValueError(f"sub-intenção {s.nome!r} declarada duas vezes")
            vistos.add(chave)
            if not s.keywords:
                raise ValueError(f"sub-intenção {s.nome!r} sem keyword")

    def grupos(self) -> list[SubIntencao]:
        """Os ad groups que este brief pede — sempre pelo menos um.

        Brief sem sub-intenção declarada continua produzindo UM ad group com
        todas as keywords, exatamente como antes — `SEM_SUB_INTENCAO` é o sinal
        para `search.py` manter o nome histórico (`AdGroup_{carimbo}`).
        """
        if self.sub_intencoes:
            return list(self.sub_intencoes)
        return [SubIntencao(nome=SEM_SUB_INTENCAO, keywords=list(self.keywords))]

    @property
    def geo_id(self) -> int:
        return self._pais.criterio_id

    @property
    def idioma_id(self) -> int:
        return self._idioma.criterio_id

    @property
    def nome_pais(self) -> str:
        return self._pais.nome

    def micros(self, valor: float) -> int:
        return int(round(valor * 1_000_000))
