"""HTTP da importação privada de mídia. Duas rotas, e nenhuma delas fala com a Meta.

    POST /api/criativos/importacoes            multipart: arquivo(s) OU um ZIP
    GET  /api/criativos/importacoes/{ref}      status e preview, por dono

`SPEC.json → proposed_routes` declara o efeito das duas em uma linha cada:
*"importação privada; não chama Meta"* e *"status/preview por owner"*. Este
arquivo existe para que as duas frases sejam verdade por CONSTRUÇÃO, e não por
disciplina: o domínio (`app/criativo/importacao.py`) não tem transporte, e este
router não importa nenhum módulo de `app/trafego/meta_*`. Quem quiser registrar
mídia na plataforma usa `POST /api/trafego/meta/assets/registrar`, que é outra
rota, com outra confirmação e outro efeito externo.

## Por que o multipart é lido aqui, e não por `File(...)` do FastAPI

`python-multipart` **não está instalado neste backend** e não está declarado em
`backend/requirements.txt`, cujo primeiro comentário é "Keep this lean: Vercel
installs it for the serverless build". `fastapi` levanta
`RuntimeError: Form data requires "python-multipart" to be installed` ao MONTAR
uma rota com `File(...)`/`Form(...)` — ou seja, o backend inteiro deixaria de
subir em produção por causa de uma rota nova. O modo de falha não seria "upload
não funciona": seria 500 em tudo.

A saída é ler o corpo aqui. O `multipart/form-data` é um formato de fronteira e
concatenação; a leitura abaixo é conservadora (recusa o que não entende em vez
de adivinhar) e o teto agregado corta ANTES de o corpo inteiro existir na
memória — que é o que `SPEC.json → media_contract.zip.rules` pede na primeira
linha.

## O portão é `exigir_admin`, e não `exigir_usuario`

Mesma razão escrita em `routers/criativos.py:326-336` para `POST /jobs`: esta
rota ESCREVE no acervo. Ela não gasta com provider, mas aceita bytes de fora,
grava em armazenamento privado e cria patrimônio com dono. Uma sessão com papel
vazio não deveria poder encher o acervo de outra pessoa.

## O 404 é o MESMO para "não existe" e "não é seu"

Distinguir os dois é um oráculo de existência: quem tem uma referência válida de
outro operador descobre que ela existe pelo código de status. `_uuid_ou_404`
fecha a mesma porta um passo antes, para id malformado.

## A política roda, e o resultado é EXIBIDO — inclusive quando bloqueia

Toda entrada aceita passa por `politica.avaliar` com
`procedencia="HUMAN_UPLOAD"` e `natureza` EXPLÍCITA. Sem `licenca_ref`, o gate
responde `BLOCKED_BY_POLICY` com o motivo `RIGHTS_UNKNOWN`
(`politica/gate.py:105-108, 168-170`) — e quando não há detector de pixel
registrado, `GATE_UNAVAILABLE` chega antes (`gate.py:158-160`). **Os dois são o
comportamento correto e viajam no DTO.** A entrada fica em `POLICY_PENDING`: o
arquivo está guardado, com dono e hash, e não está liberado para mídia paga.
Contornar isso aqui seria reintroduzir o defeito que o portão inteiro existe
para fechar.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Protocol

from fastapi import APIRouter, Depends, Request, Response

from app.criativo import importacao as imp
from app.criativo.armazenamento import (
    ArmazenamentoDeObjetos,
    ArquivoRecusado,
    ArmazenamentoIndisponivel,
    Assinador,
    armazenamento_padrao,
    chave_de_asset,
)
from app.criativo.persistencia import (
    ConflitoDeChave,
    ErroDePersistencia,
    ReferenciaInvalida,
    Repositorio,
    agora,
)
from app.routers.criativos import (
    _falha,
    _ou_503,
    _uuid_ou_404,
    obter_assinador,
    obter_repo,
)
from app.seguranca.identidade import Identidade, exigir_admin

log = logging.getLogger("volc.criativo.importacao")

router = APIRouter(prefix="/api/criativos/importacoes", tags=["criativos"])

_TABELA_LOTE = "criativo_importacao_lote"
_TABELA_ENTRADA = "criativo_importacao_entrada"
_TABELA_MASTER = "criativo_master"

#: Mesmo TTL de `apresentacao.TTL_PREVIEW_S` (apresentacao.py:28). Curto o
#: bastante para um token copiado de um print não valer nada amanhã.
TTL_PREVIEW_S = 300

#: Folga sobre o teto comprimido da SPEC para os cabeçalhos do multipart. O
#: envelope não é payload, mas viaja no mesmo corpo; sem a folga, um ZIP
#: exatamente no limite seria recusado pelo enquadramento e a mensagem falaria
#: do arquivo.
_FOLGA_DE_ENVELOPE = 1024 * 1024


# ─────────────────────────────────────────────────────────────────────────────
# Leitura do corpo, com teto ANTES da alocação
# ─────────────────────────────────────────────────────────────────────────────


async def _corpo_com_teto(request: Request, teto: int) -> bytes:
    """Consome o stream e aborta no bloco que passa do teto.

    ⚠️ `await request.body()` bufferiza tudo e SÓ DEPOIS devolve. Um corpo de
    2 GB derruba o processo antes de qualquer validação — a alocação é o ataque.
    """
    pedacos: list[bytes] = []
    total = 0
    async for bloco in request.stream():
        if not bloco:
            continue
        total += len(bloco)
        if total > teto:
            raise _falha(
                "ESTUDIO.importacao_grande_demais",
                "O envio passou do limite desta importação. "
                f"O máximo é {imp.TETO_COMPRIMIDO_BYTES // (1024 * 1024)} MB.",
                413,
            )
        pedacos.append(bloco)
    return b"".join(pedacos)


# ─────────────────────────────────────────────────────────────────────────────
# multipart/form-data, lido à mão
# ─────────────────────────────────────────────────────────────────────────────

_FRONTEIRA = re.compile(r'boundary="?([^";,]+)"?', re.IGNORECASE)
_NOME = re.compile(r'name="([^"]*)"', re.IGNORECASE)
_ARQUIVO = re.compile(r'filename="([^"]*)"', re.IGNORECASE)


class _Parte:
    __slots__ = ("nome", "arquivo", "conteudo")

    def __init__(self, nome: str, arquivo: str | None, conteudo: bytes) -> None:
        self.nome = nome
        self.arquivo = arquivo
        self.conteudo = conteudo


def _ler_multipart(corpo: bytes, content_type: str) -> list[_Parte]:
    """As partes do formulário. Recusa fechada em vez de adivinhação.

    O que este leitor NÃO faz, de propósito: não aceita `multipart/mixed`
    aninhado, não decodifica `Content-Transfer-Encoding` e não interpreta
    `filename*=`. Cada um desses seria uma superfície a mais para um formato que
    aqui só precisa carregar bytes crus. O que ele não entende, ele recusa.
    """
    achado = _FRONTEIRA.search(content_type or "")
    if not achado:
        raise _falha(
            "ESTUDIO.importacao_pedido_invalido",
            "Envie os arquivos como multipart/form-data.",
            400,
        )
    delimitador = b"--" + achado.group(1).encode("latin-1", "ignore")
    partes: list[_Parte] = []
    for bruto in corpo.split(delimitador)[1:]:
        if bruto[:2] == b"--":  # delimitador de fechamento: acabou
            break
        if bruto.startswith(b"\r\n"):
            bruto = bruto[2:]
        elif bruto.startswith(b"\n"):
            bruto = bruto[1:]
        else:
            continue
        if bruto.endswith(b"\r\n"):
            bruto = bruto[:-2]
        elif bruto.endswith(b"\n"):
            bruto = bruto[:-1]
        cabecalho, separador, conteudo = bruto.partition(b"\r\n\r\n")
        if not separador:
            cabecalho, separador, conteudo = bruto.partition(b"\n\n")
            if not separador:
                continue
        texto = cabecalho.decode("latin-1", "replace")
        disposicao = ""
        for linha in texto.splitlines():
            if linha.lower().startswith("content-disposition:"):
                disposicao = linha
                break
        if not disposicao:
            continue
        nome = _NOME.search(disposicao)
        arquivo = _ARQUIVO.search(disposicao)
        partes.append(_Parte(
            nome=nome.group(1) if nome else "",
            # `filename=""` é uma parte de arquivo VAZIA que alguns clientes
            # mandam; ela continua sendo parte de arquivo, e vira `ENTRADA_VAZIA`
            # na inspeção em vez de sumir aqui.
            arquivo=arquivo.group(1) if arquivo else None,
            conteudo=conteudo,
        ))
    return partes


# ─────────────────────────────────────────────────────────────────────────────
# Persistência das duas tabelas novas
# ─────────────────────────────────────────────────────────────────────────────


class PortaDeImportacao(Protocol):
    """O que esta lane precisa do banco. Nada além disso.

    Existe como Protocol para que o teste da rota seja HERMÉTICO: um dublê em
    memória implementa estes sete métodos e a suíte inteira roda sem Supabase,
    sem rede e sem `.env`.
    """

    async def criar_projeto(self, titulo: str, objetivo: str | None,
                            brand_pack_id: str | None, dono_id: str | None,
                            origem: str = "standalone") -> dict[str, Any]: ...

    async def criar_briefing(self, linha: dict[str, Any]) -> dict[str, Any]: ...

    async def criar_job_idempotente(
        self, linha: dict[str, Any]) -> tuple[dict[str, Any], bool]: ...

    async def criar_master(self, linha: dict[str, Any]) -> dict[str, Any]: ...

    async def master_do_dono_por_hash(
        self, content_hash: str, *, criado_por: str) -> dict[str, Any] | None: ...

    async def criar_lote(self, linha: dict[str, Any]) -> dict[str, Any]: ...

    async def criar_entradas(
        self, linhas: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

    async def lote_do_dono(
        self, lote_id: str, *, criado_por: str) -> dict[str, Any] | None: ...

    async def entradas_do_lote(self, lote_id: str) -> list[dict[str, Any]]: ...

    async def buscar_job(self, job_id: str, *,
                         criado_por: str | None = None) -> dict[str, Any] | None: ...

    async def masters_do_job(self, job_id: str) -> list[dict[str, Any]]: ...


class RepositorioDeImportacao:
    """Adaptador sobre `Repositorio`, com as duas tabelas que a v11_04 criou.

    ⚠️ Ele usa `Repositorio._inserir`/`_get` — os helpers de transporte, que são
    privados por convenção. A alternativa seria acrescentar métodos a
    `persistencia.py`, e esta task não tem posse daquele arquivo. Envolver o
    transporte aqui é preferível a abrir um SEGUNDO caminho até o mesmo banco:
    o tratamento de 23505/23503, o timeout e a política de erro continuam sendo
    os do `Repositorio`, e não uma cópia que diverge na primeira correção.
    """

    def __init__(self, repo: Repositorio) -> None:
        self.repo = repo

    # ── delegações puras ────────────────────────────────────────────────────
    async def criar_projeto(self, *a: Any, **kw: Any) -> dict[str, Any]:
        return await self.repo.criar_projeto(*a, **kw)

    async def criar_briefing(self, linha: dict[str, Any]) -> dict[str, Any]:
        return await self.repo.criar_briefing(linha)

    async def criar_job_idempotente(
        self, linha: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        return await self.repo.criar_job_idempotente(linha)

    async def criar_master(self, linha: dict[str, Any]) -> dict[str, Any]:
        return await self.repo.criar_master(linha)

    async def buscar_job(self, job_id: str, *,
                         criado_por: str | None = None) -> dict[str, Any] | None:
        return await self.repo.buscar_job(job_id, criado_por=criado_por)

    async def masters_do_job(self, job_id: str) -> list[dict[str, Any]]:
        return await self.repo.masters_do_job(job_id)

    # ── dedup por hash, SEM atravessar o dono ───────────────────────────────
    async def master_do_dono_por_hash(
        self, content_hash: str, *, criado_por: str
    ) -> dict[str, Any] | None:
        """O master que já tem estes MESMOS bytes — e só se ele for do dono.

        ⚠️ `Repositorio._EMBED_DONO` com `!inner`, e o filtro no SERVIDOR. Sem o
        `!inner` o PostgREST devolveria a linha alheia com o embed nulo, que é
        pior que o vazamento original porque PARECE filtrada
        (`persistencia.py:437-444`).

        É esta função que implementa a metade honesta de *"hash idêntico reusa
        master autorizado, mas política/referência de outra conta não é
        automaticamente válida"*: os bytes de outra conta simplesmente não
        aparecem aqui, e a política é reavaliada NESTA requisição de qualquer
        forma — o recibo antigo não é herdado.
        """
        linhas = await self.repo._get(
            _TABELA_MASTER,
            {
                "content_hash": f"eq.{content_hash}",
                "select": Repositorio._EMBED_DONO,
                "criativo_job.criado_por": f"eq.{criado_por}",
                "order": "criado_em.desc",
                "limit": 1,
            },
        )
        if not linhas:
            return None
        limpa = dict(linhas[0])
        limpa.pop("criativo_job", None)
        return limpa

    # ── as tabelas da v11_04 ────────────────────────────────────────────────
    async def criar_lote(self, linha: dict[str, Any]) -> dict[str, Any]:
        return await self.repo._inserir(_TABELA_LOTE, linha)

    async def criar_entradas(
        self, linhas: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return await self.repo._inserir_muitos(_TABELA_ENTRADA, linhas)

    async def lote_do_dono(
        self, lote_id: str, *, criado_por: str
    ) -> dict[str, Any] | None:
        linhas = await self.repo._get(
            _TABELA_LOTE,
            {"id": f"eq.{lote_id}", "criado_por": f"eq.{criado_por}",
             "select": "*", "limit": 1},
        )
        return linhas[0] if linhas else None

    async def entradas_do_lote(self, lote_id: str) -> list[dict[str, Any]]:
        return await self.repo._get(
            _TABELA_ENTRADA,
            {"lote_id": f"eq.{lote_id}", "select": "*", "order": "indice.asc"},
        )


def obter_porta(repo: Repositorio = Depends(obter_repo)) -> PortaDeImportacao:
    return RepositorioDeImportacao(repo)


def obter_armazenamento() -> ArmazenamentoDeObjetos:
    """A porta de storage como DEPENDÊNCIA, e não como chamada direta.

    ⚠️ `armazenamento_padrao()` é um singleton de processo com raiz no `$HOME`.
    Chamá-lo dentro do handler faria o teste da rota escrever no diretório real
    do desenvolvedor — e um teste que suja a máquina de quem o roda acaba sendo
    desligado. Como dependência, `dependency_overrides` troca por um
    `ArmazenamentoLocal(tmp_path)`.
    """
    return armazenamento_padrao()


# ─────────────────────────────────────────────────────────────────────────────
# Política
# ─────────────────────────────────────────────────────────────────────────────


def _avaliar_politica(
    entrada: imp.EntradaInspecionada, *, asset_ref: str, identity_ref: str,
) -> dict[str, Any] | None:
    """Um recibo por entrada. NUNCA levanta: bloqueio é resultado, não erro.

    `natureza` vai EXPLÍCITA. O default de `avaliar` é `"producao"`, e depender
    de default aqui esconderia a decisão mais consequente da chamada: qualquer
    coisa diferente de `producao` bloqueia por `NATURE_NOT_PRODUCTION`
    (`gate.py:155-157`). Mídia importada é declarada como produção porque é para
    isso que ela é importada — e é justamente por isso que ela tem de encarar o
    portão de direitos em vez de contorná-lo.
    """
    from app.criativo import politica as pol  # noqa: PLC0415 — import tardio

    if not (entrada.content_hash and entrada.mime_detectado and entrada.conteudo):
        return None
    try:
        recibo = pol.avaliar(
            asset_ref=asset_ref,
            content_sha256=entrada.content_hash.removeprefix("sha256:"),
            bytes_da_peca=entrada.conteudo,
            mime=entrada.mime_detectado,
            copy=None,
            # O nome do arquivo entra no léxico: "banco-do-brasil.jpg" é uma
            # afirmação de vínculo tão real quanto o logotipo dentro da imagem.
            nome_do_arquivo=entrada.nome_normalizado,
            prompt=None,
            identity_ref=identity_ref,
            identidade_propria=None,
            # Arquivo que um humano subiu. Sem `licenca_ref` isto sai
            # `BLOCKED_BY_POLICY`/`RIGHTS_UNKNOWN`, e sair assim é o certo:
            # ninguém provou que temos direito sobre estes bytes.
            procedencia="HUMAN_UPLOAD",
            licenca_ref=None,
            natureza="producao",
        )
    except Exception as e:  # noqa: BLE001 — sem segredo de assinatura, p.ex.
        log.warning("portão de política indisponível: %s", e)
        return {
            "decisao": "GATE_UNAVAILABLE",
            "motivos": ["POLICY_RECEIPT_UNAVAILABLE"],
            "liberaMidiaPaga": False,
            "reciboRef": None,
        }
    return {
        "decisao": recibo.decisao,
        "motivos": list(recibo.motivos),
        "liberaMidiaPaga": recibo.libera_midia_paga(),
        "reciboRef": recibo.policy_receipt_ref,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DTO
# ─────────────────────────────────────────────────────────────────────────────


def _preview_url(assinador: Assinador, chave: str | None) -> str | None:
    """URL assinada, ou `None`. Nunca o caminho, nunca a chave crua.

    Mesma forma de `apresentacao._url` (apresentacao.py:31-35): `<img src>` não
    manda header, e a saída barata para isso — deixar o bucket público — é
    exatamente como um bucket privado deixa de ser privado.
    """
    if not chave:
        return None
    return f"/api/criativos/arquivo/{assinador.assinar(chave, ttl_s=TTL_PREVIEW_S)}"


#: O que esta lane afirma sobre a plataforma: NADA foi enviado.
#:
#: O campo existe no DTO para que a tela possa dizê-lo em vez de o operador
#: supor. `SPEC.json → proposed_routes` separa a importação privada do
#: `POST /api/trafego/meta/assets/registrar`, que é "UPLOAD REAL DE MÍDIA por
#: confirmação" — dois atos, duas autorizações.
_REGISTRO_REMOTO = {
    "estado": "NAO_INICIADO",
    "explicacao": (
        "Importar arquivo não envia nada para a Meta. O registro na conta é um "
        "ato separado, com confirmação própria."
    ),
}


def _entrada_dto(linha: dict[str, Any], assinador: Assinador) -> dict[str, Any]:
    politica = linha.get("politica")
    if isinstance(politica, str):
        politica = json.loads(politica) if politica else None
    return {
        "indice": int(linha["indice"]),
        "nome": linha.get("nome_normalizado"),
        "estado": linha["estado"],
        "mime": linha.get("mime_detectado"),
        # `_n` da casa: ausência é `None`, nunca 0.
        "bytes": linha.get("bytes") or None,
        "contentHash": linha.get("content_hash"),
        "masterId": str(linha["master_id"]) if linha.get("master_id") else None,
        "motivoRecusa": linha.get("motivo_recusa"),
        "detalhe": linha.get("detalhe"),
        "largura": linha.get("largura") or None,
        "altura": linha.get("altura") or None,
        "duracaoMs": linha.get("duracao_ms") or None,
        "previewUrl": _preview_url(assinador, linha.get("storage_chave")),
        "politica": politica,
    }


def _lote_dto(
    lote: dict[str, Any], entradas: list[dict[str, Any]], assinador: Assinador,
) -> dict[str, Any]:
    return {
        "referencia": str(lote["id"]),
        "origem": lote["origem"],
        "estado": lote["estado"],
        "nomeArquivoOriginal": lote.get("nome_arquivo_original"),
        "bytesComprimidos": lote.get("bytes_comprimidos") or None,
        "entradasTotal": lote.get("entradas_total"),
        "motivoRecusa": lote.get("motivo_recusa"),
        "detalhe": lote.get("detalhe"),
        "criadoEm": lote.get("criado_em"),
        "entradas": [_entrada_dto(e, assinador) for e in entradas],
        "registroRemoto": _REGISTRO_REMOTO,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST — recebe, inspeciona, guarda, avalia. Nada sai daqui.
# ─────────────────────────────────────────────────────────────────────────────


@router.post("")
@router.post("/")
async def importar(
    request: Request,
    resposta: Response,
    identidade: Identidade = Depends(exigir_admin),
    porta: PortaDeImportacao = Depends(obter_porta),
    assinador: Assinador = Depends(obter_assinador),
    loja: ArmazenamentoDeObjetos = Depends(obter_armazenamento),
) -> dict[str, Any]:
    """`201` importou · `200` reenvio reconhecido · `400` nada entrou.

    ⚠️ O corpo é o MESMO DTO nos três casos, e carrega `referencia` mesmo na
    recusa: a tentativa recusada está registrada, e o operador precisa poder
    abri-la. Devolver 200 para um ZIP com traversal faria um cliente ingênuo
    ler "deu certo"; devolver 400 sem corpo tiraria dele a única prova do que
    aconteceu. Os dois juntos dizem a verdade inteira.

    O par 200/201 é o mesmo de `POST /jobs` (criativos.py:392-403): 200 com
    `X-Criativo-Importacao: replay` significa que nada novo foi produzido.
    """
    dono = identidade.sub
    corpo = await _corpo_com_teto(
        request, imp.TETO_COMPRIMIDO_BYTES + _FOLGA_DE_ENVELOPE
    )
    partes = _ler_multipart(corpo, request.headers.get("content-type", ""))
    arquivos = [p for p in partes if p.arquivo is not None]
    campos = {p.nome: p.conteudo.decode("utf-8", "replace")
              for p in partes if p.arquivo is None}

    if not arquivos:
        raise _falha(
            "ESTUDIO.importacao_sem_arquivo",
            "Nenhum arquivo veio no envio.",
            400,
        )

    # ZIP é decidido pelos BYTES, nunca pela extensão. Um `.zip` que não é ZIP
    # cai na lane individual e é recusado por MIME; um `.bin` que é ZIP não
    # escapa da expansão controlada.
    zips = [p for p in arquivos if imp.e_zip(p.conteudo)]
    if zips and len(arquivos) > 1:
        raise _falha(
            "ESTUDIO.importacao_pedido_invalido",
            "Envie um ZIP sozinho ou arquivos individuais — não os dois juntos.",
            400,
        )

    origem = imp.ORIGEM_ZIP if zips else imp.ORIGEM_INDIVIDUAL
    nome_original = arquivos[0].arquivo if len(arquivos) == 1 else None
    bytes_recebidos = sum(len(p.conteudo) for p in arquivos)

    try:
        if zips:
            lote = imp.importar_zip(zips[0].conteudo, nome_arquivo=zips[0].arquivo)
        else:
            lote = imp.importar_individual(
                imp.ArquivoRecebido(nome=p.arquivo or "arquivo", dados=p.conteudo)
                for p in arquivos
            )
    except imp.ArchiveMalicioso as e:
        # ⚠️ O ARCHIVE inteiro cai, e a tentativa É REGISTRADA. Recusar em
        # silêncio deixaria o operador sem saber o que aconteceu, e a auditoria
        # sem a linha mais importante que este lote produziu.
        lote = imp.lote_recusado(origem, nome_original, bytes_recebidos, e)
        gravado = await _gravar_lote_recusado(porta, lote, dono=dono)
        resposta.status_code = 400
        return _lote_dto(gravado, [], assinador)

    if lote.estado == imp.REJECTED and lote.motivo_recusa:
        gravado = await _gravar_lote_recusado(porta, lote, dono=dono)
        resposta.status_code = 400
        return _lote_dto(gravado, [], assinador)

    aceitas = lote.aceitas
    if not aceitas:
        # Nenhuma entrada serviu, mas cada uma tem motivo PRÓPRIO. Sem job, sem
        # master: não há patrimônio, só a trilha.
        gravado = await _gravar_lote_recusado(porta, lote, dono=dono)
        entradas = [
            _linha_de_entrada(e, master_id=None, storage_chave=None, politica=None)
            for e in lote.entradas
        ]
        await _ou_503(porta.criar_entradas(
            [{**l, "lote_id": gravado["id"]} for l in _persistivel(entradas)]))
        resposta.status_code = 400
        return _lote_dto(gravado, entradas, assinador)

    # ── o ciclo canônico: projeto → briefing → job → master ─────────────────
    projeto = await _ou_503(porta.criar_projeto(
        _titulo(campos.get("projetoTitulo"), lote),
        "Importação privada de mídia.",
        None,
        dono,
        # `criativo_projeto.origem` JÁ aceita `importado` desde a v11_01:186.
        "importado",
    ))
    briefing = await _ou_503(porta.criar_briefing({
        "projeto_id": projeto["id"],
        "tipo": "video" if any(
            e.mime_detectado in ("video/mp4",) for e in aceitas) else "imagem",
        # A v11_04 acrescentou `importado` ao vocabulário de modo E à exceção de
        # `formatos_pedidos`: quem importa não PEDE formato, recebe o que o
        # arquivo é.
        "modo": imp.MODO_DE_PRODUCAO,
        "objetivo": "Importação privada de mídia.",
        "formatos_pedidos": [],
        "destinos_pretendidos": [],
        "criado_por": dono,
    }))

    quando = agora()
    chave_idem = _chave_de_idempotencia(dono, lote)
    job, criado = await _ou_503(porta.criar_job_idempotente({
        "briefing_id": briefing["id"],
        "motor": imp.MOTOR,
        "motor_versao": imp.MOTOR_VERSAO,
        "estado": "succeeded",
        "idempotency_key": chave_idem,
        "insumo_hash": _hash_do_lote(lote),
        # ⚠️ Nem `volc_os` nem `observado`. Ver o cabeçalho da v11_04.
        "procedencia_execucao": imp.PROCEDENCIA_EXECUCAO,
        # NOT NULL para `importado` por `criativo_job_importado_com_origem`.
        "origem_externa": {
            "tipo": lote.origem,
            "nomeArquivoOriginal": lote.nome_arquivo_original,
            "bytesRecebidos": lote.bytes_comprimidos,
            "recebidoEm": quando,
            "operador": dono,
        },
        # `custo_real_usd` NÃO é enviado: `criativo_job_importado_sem_custo_proprio`
        # o proíbe, e mandar 0 seria "rodou e não custou" — uma medida, não uma
        # ausência (regra B da v11_01).
        "iniciado_em": quando,
        "terminado_em": quando,
        "criado_por": dono,
    }))

    identity_ref = f"volc:operador:{dono}"
    linhas: list[dict[str, Any]] = []
    for entrada in lote.entradas:
        if not entrada.aceita:
            linhas.append(_linha_de_entrada(entrada, None, None, None))
            continue
        try:
            master, chave = await _guardar_e_registrar(
                porta, loja, entrada,
                projeto_id=str(projeto["id"]), job_id=str(job["id"]), dono=dono,
            )
        except ArquivoRecusado as e:
            # O armazenamento tem política PRÓPRIA (`armazenamento.py:124-137`,
            # teto de 25 MB aplicado dentro de `guardar`). Quando ele recusa, a
            # entrada cai sozinha e diz por quê — em vez de o lote inteiro virar
            # 500 e o operador ficar sem saber qual arquivo travou.
            linhas.append(_linha_de_entrada(
                entrada, None, None, None,
                sobrescreve_motivo="ARMAZENAMENTO_RECUSOU", detalhe=str(e)))
            continue
        except ArmazenamentoIndisponivel as e:
            raise _falha(
                "ESTUDIO.indisponivel",
                "O armazenamento de criativos não respondeu agora.",
                503,
            ) from e
        politica = _avaliar_politica(
            entrada, asset_ref=f"criativo:master:{master['id']}",
            identity_ref=identity_ref,
        )
        linhas.append(_linha_de_entrada(
            entrada, str(master["id"]), chave, politica))

    # ⚠️ O estado do LOTE é DERIVADO das linhas — e derivado UMA VEZ, aqui, que é
    # o único instante em que ele é calculável. Ele é gravado porque o lote é um
    # fato histórico: recalculá-lo na leitura devolveria vazio para o archive
    # recusado, que não produz entrada nenhuma (v11_04 seção 4).
    estado = _estado_do_lote(linhas)
    lote_linha = await _ou_503(porta.criar_lote({
        "job_id": job["id"],
        "criado_por": dono,
        "origem": lote.origem,
        "nome_arquivo_original": lote.nome_arquivo_original,
        "bytes_comprimidos": lote.bytes_comprimidos or None,
        "entradas_total": lote.entradas_total,
        "estado": estado,
        "motivo_recusa": _motivo_do_lote(linhas) if estado == imp.REJECTED else None,
    }))
    await _ou_503(porta.criar_entradas(
        [{**l, "lote_id": lote_linha["id"]} for l in _persistivel(linhas)]))

    if estado == imp.REJECTED:
        # Todas as entradas caíram DEPOIS do job existir (armazenamento recusou,
        # por exemplo). O pedido não produziu patrimônio: 400, com a trilha.
        resposta.status_code = 400
    elif criado:
        resposta.status_code = 201
    else:
        resposta.status_code = 200
        resposta.headers["X-Criativo-Importacao"] = "replay"
    return _lote_dto(
        {**lote_linha,
         "detalhe": None if criado else "reenvio reconhecido: mesmo job"},
        linhas, assinador)


# ─────────────────────────────────────────────────────────────────────────────
# GET — status e preview, por dono
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{referencia}")
async def ver_importacao(
    referencia: str,
    identidade: Identidade = Depends(exigir_admin),
    porta: PortaDeImportacao = Depends(obter_porta),
    assinador: Assinador = Depends(obter_assinador),
) -> dict[str, Any]:
    """404 idêntico para "não existe" e "não é seu". Ver o cabeçalho."""
    lote_id = _uuid_ou_404(referencia, "importacao")
    dono = identidade.sub
    lote = await _ou_503(porta.lote_do_dono(lote_id, criado_por=dono))
    if lote is None:
        raise _falha("ESTUDIO.importacao_inexistente", "Este item não existe.", 404)

    # ⚠️ A posse resolve pelo JOB, e a coluna `criado_por` do lote é a cópia.
    # Quando há job, ele é a autoridade — é a mesma doutrina de
    # `persistencia.buscar_master_do_dono` (persistencia.py:447-460). Quando não
    # há (lote recusado, que nunca gerou execução), a coluna é tudo que existe,
    # e o filtro acima já a aplicou.
    if lote.get("job_id"):
        job = await _ou_503(porta.buscar_job(str(lote["job_id"]), criado_por=dono))
        if job is None:
            raise _falha("ESTUDIO.importacao_inexistente", "Este item não existe.", 404)

    entradas = await _ou_503(porta.entradas_do_lote(lote_id))
    # A chave de storage não vem da tabela de entradas (ela não a guarda): ela é
    # derivada do master, que é quem tem endereço. Sem master, sem preview.
    masters = {}
    if lote.get("job_id"):
        masters = {
            str(m["id"]): m
            for m in await _ou_503(porta.masters_do_job(str(lote["job_id"])))
        }
    enriquecidas = []
    for e in entradas:
        master = masters.get(str(e.get("master_id") or ""))
        enriquecidas.append({
            **e,
            "storage_chave": (master or {}).get("storage_chave"),
            "largura": (master or {}).get("largura"),
            "altura": (master or {}).get("altura"),
            "duracao_ms": (master or {}).get("duracao_ms"),
        })
    return _lote_dto(lote, enriquecidas, assinador)


# ─────────────────────────────────────────────────────────────────────────────
# Auxiliares
# ─────────────────────────────────────────────────────────────────────────────


def _titulo(pedido: str | None, lote: imp.LoteInspecionado) -> str:
    bruto = (pedido or "").strip()
    if bruto:
        return bruto[:200]
    if lote.nome_arquivo_original:
        return f"Importação — {lote.nome_arquivo_original}"[:200]
    return "Importação de mídia"


def _hash_do_lote(lote: imp.LoteInspecionado) -> str:
    """A identidade do INSUMO: os bytes finais de todas as entradas aceitas.

    `criativo_job.insumo_hash` pergunta "o que foi mandado para o motor?"
    (v11_01:256-259). Numa importação o insumo é o próprio conjunto de arquivos,
    e ordenar os hashes torna o valor estável contra a ordem de chegada.
    """
    partes = sorted(e.content_hash or "" for e in lote.aceitas)
    return "sha256:" + hashlib.sha256("|".join(partes).encode()).hexdigest()


def _chave_de_idempotencia(dono: str, lote: imp.LoteInspecionado) -> str:
    """O mesmo envio do mesmo operador é o MESMO job, não um segundo.

    Derivada do CONTEÚDO e não sorteada — camada 1 da idempotência descrita no
    cabeçalho da v11_01. `criativo_job_idem_forma` exige >= 16 caracteres; um
    sha256 hex tem 64.
    """
    material = f"importacao:v1:{dono}:{lote.origem}:{_hash_do_lote(lote)}"
    return hashlib.sha256(material.encode()).hexdigest()


def _linha_de_entrada(
    entrada: imp.EntradaInspecionada,
    master_id: str | None,
    storage_chave: str | None,
    politica: dict[str, Any] | None,
    *,
    sobrescreve_motivo: str | None = None,
    detalhe: str | None = None,
) -> dict[str, Any]:
    """A entrada como linha — com o estado do PIPELINE, não o da inspeção.

    A inspeção só sabe dizer `INSPECTED`/`REJECTED`. Quem sabe se os bytes foram
    guardados é este router, e quem sabe se a política liberou é o portão. O
    estado final é a composição dos três, e é ele que vai para o banco.
    """
    if sobrescreve_motivo:
        estado, motivo = imp.REJECTED, sobrescreve_motivo
    elif not entrada.aceita:
        estado, motivo = imp.REJECTED, entrada.motivo_recusa
    elif politica is None:
        estado, motivo = imp.IMPORTED_PRIVATE, None
    elif politica.get("liberaMidiaPaga"):
        estado, motivo = imp.READY_FOR_REGISTRATION, None
    else:
        # Guardado, com dono e hash — e NÃO liberado para mídia paga.
        estado, motivo = imp.POLICY_PENDING, None
    return {
        "indice": entrada.indice,
        "nome_normalizado": entrada.nome_normalizado,
        "estado": estado,
        "mime_detectado": entrada.mime_detectado,
        "bytes": entrada.bytes,
        "content_hash": entrada.content_hash,
        "master_id": master_id,
        "motivo_recusa": motivo,
        # Campos que a TELA usa e a tabela não guarda. `_persistivel` os tira
        # antes do INSERT — mandar coluna inexistente devolve 400 do PostgREST.
        "detalhe": detalhe or entrada.detalhe,
        "storage_chave": storage_chave,
        "largura": entrada.largura,
        "altura": entrada.altura,
        "duracao_ms": entrada.duracao_ms,
        "politica": politica,
    }


#: As colunas que `criativo_importacao_entrada` realmente tem (v11_04 seção 5).
_COLUNAS_DE_ENTRADA = (
    "indice", "nome_normalizado", "estado", "mime_detectado", "bytes",
    "content_hash", "master_id", "motivo_recusa",
)


def _persistivel(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{c: l.get(c) for c in _COLUNAS_DE_ENTRADA} for l in linhas]


def _estado_do_lote(linhas: list[dict[str, Any]]) -> str:
    recusadas = sum(1 for l in linhas if l["estado"] == imp.REJECTED)
    if recusadas == len(linhas):
        return imp.REJECTED
    if recusadas:
        return imp.PARTIAL_BATCH
    if any(l["estado"] == imp.POLICY_PENDING for l in linhas):
        return imp.POLICY_PENDING
    if all(l["estado"] == imp.READY_FOR_REGISTRATION for l in linhas):
        return imp.READY_FOR_REGISTRATION
    return imp.IMPORTED_PRIVATE


def _motivo_do_lote(linhas: list[dict[str, Any]]) -> str:
    """O motivo do LOTE quando todas as entradas caíram: o da primeira recusa.

    Ele não substitui o motivo POR ENTRADA — as entradas continuam com o seu.
    Ele existe porque `criativo_importacao_lote_recusado_com_motivo` (v11_04
    seção 4) exige que um lote `REJECTED` diga alguma coisa, e "nenhuma das N
    entradas serviu" precisa de um representante nomeado.
    """
    for l in linhas:
        if l["estado"] == imp.REJECTED and l.get("motivo_recusa"):
            return str(l["motivo_recusa"])
    return "LOTE_SEM_ENTRADA_UTIL"


def _motivo_das_entradas(lote: imp.LoteInspecionado) -> str:
    for e in lote.entradas:
        if e.motivo_recusa:
            return e.motivo_recusa
    return "LOTE_SEM_ENTRADA_UTIL"


async def _gravar_lote_recusado(
    porta: PortaDeImportacao, lote: imp.LoteInspecionado, *, dono: str,
) -> dict[str, Any]:
    """O lote que não gerou patrimônio, gravado assim mesmo.

    `job_id` fica NULL de propósito (v11_04 seção 4): não houve execução, e
    fabricar um job para satisfazer a coluna colocaria uma execução inexistente
    no ledger que a v11_01 usa justamente para contar execuções.
    """
    linha = await _ou_503(porta.criar_lote({
        "job_id": None,
        "criado_por": dono,
        "origem": lote.origem,
        "nome_arquivo_original": lote.nome_arquivo_original,
        "bytes_comprimidos": lote.bytes_comprimidos or None,
        "entradas_total": lote.entradas_total,
        "estado": imp.REJECTED,
        "motivo_recusa": lote.motivo_recusa or _motivo_das_entradas(lote),
    }))
    # `detalhe` é a frase que explica o CÓDIGO, e vive só nesta resposta: a
    # tabela guarda o código, que é o que uma consulta agrega. A prosa mudaria
    # com a versão do software e envelheceria na linha.
    return {**linha, "detalhe": lote.detalhe}


async def _guardar_e_registrar(
    porta: PortaDeImportacao,
    loja: ArmazenamentoDeObjetos,
    entrada: imp.EntradaInspecionada,
    *,
    projeto_id: str,
    job_id: str,
    dono: str,
) -> tuple[dict[str, Any], str]:
    """Grava os bytes FINAIS no acervo privado e registra o master.

    Reusa um master do MESMO dono quando o hash já existe: os bytes são os
    mesmos, e um segundo master criaria duas identidades para um arquivo só.
    O que NÃO é reusado é a decisão de política — ela é reavaliada nesta
    requisição, porque o recibo antigo descreve outra avaliação, em outro
    instante, possivelmente com outro léxico.
    """
    assert entrada.content_hash and entrada.mime_detectado and entrada.conteudo

    existente = await _ou_503(porta.master_do_dono_por_hash(
        entrada.content_hash, criado_por=dono))
    if existente is not None:
        return existente, str(existente.get("storage_chave") or "")

    chave = chave_de_asset(
        projeto_id, job_id, f"importado-{entrada.indice:03d}",
        entrada.content_hash, imp.extensao_do_mime(entrada.mime_detectado),
    )
    loja.guardar(chave, entrada.conteudo, entrada.mime_detectado)

    linha = {
        "job_id": job_id,
        "projeto_id": projeto_id,
        "slot": f"importado-{entrada.indice:03d}",
        "kind": "video" if entrada.mime_detectado in ("video/mp4",) else "imagem",
        "storage_chave": chave,
        "content_hash": entrada.content_hash,
        "mime": entrada.mime_detectado,
        "bytes_totais": entrada.bytes,
        "largura": entrada.largura,
        "altura": entrada.altura,
        "duracao_ms": entrada.duracao_ms,
        "motor": imp.MOTOR,
        "motor_versao": imp.MOTOR_VERSAO,
        "insumo_hash": entrada.insumo_hash,
        "insumo_sanitizado": None,
        # ⚠️ `False` com evidência ausente, e não `True` por precaução.
        #
        # A coluna é NOT NULL, então "não sei" não cabe. `video_observado.
        # _sintetico` (video_observado.py:718-734) já escreveu a doutrina: só
        # afirmar `True` com evidência POSITIVA. O erro possível aqui é deixar
        # de marcar um sintético, que um humano corrige revisando; o erro
        # oposto — carimbar de "gerado por IA" a foto que um fornecedor real
        # produziu — é acusação falsa contra terceiro.
        "sintetico": False,
        "versao": 1,
    }
    try:
        master = await porta.criar_master(linha)
    except ConflitoDeChave:
        # Corrida com outra requisição do mesmo job/slot. O master que venceu é
        # o que vale — gravar um segundo daria duas identidades ao mesmo arquivo.
        existentes = [m for m in await _ou_503(porta.masters_do_job(job_id))
                      if m.get("slot") == linha["slot"]]
        if not existentes:
            raise
        master = existentes[0]
    except ReferenciaInvalida as e:
        raise _falha(
            "ESTUDIO.importacao_pedido_invalido",
            "A importação cita um registro que não existe.",
            400,
        ) from e
    except ErroDePersistencia as e:
        raise _falha(
            "ESTUDIO.indisponivel",
            "Não foi possível registrar a mídia importada agora.",
            503,
        ) from e
    return master, chave
