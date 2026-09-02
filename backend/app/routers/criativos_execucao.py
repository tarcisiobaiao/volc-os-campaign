"""HTTP da execução criativa local, separado do router de produto.

Esta fronteira conserva integralmente o contrato público existente em
``/api/criativos/bancada``. Ela ainda adapta a bancada SQLite local já existente;
não cria fila, worker, storage remoto, motor ou entrega a destino.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.criativo import dominio
from app.criativo.bancada import SaidaPedida
from app.criativo.bancada import Encomenda as EncomendaDaBancada
from app.criativo.bancada import fronteira_publica
from app.criativo.bancada import servico as bancada_servico
from app.seguranca.identidade import Identidade, exigir_usuario

router = APIRouter(prefix="/api/criativos", tags=["criativos"])


def _falha(codigo: str, mensagem: str, status: int) -> HTTPException:
    """Erro com a forma pública já usada pelo Estúdio."""
    return HTTPException(status_code=status, detail={"codigo": codigo, "mensagem": mensagem})


class PedidoDeProducao(BaseModel):
    """Um pedido de produção local. Não publica, não entrega, não sai daqui."""

    receitaId: str = Field(min_length=1, max_length=120)
    motorSlug: str = Field(min_length=1, max_length=64)
    modoSlug: str = Field(min_length=1, max_length=64)
    finalidadeSlug: str = Field(min_length=1, max_length=64)
    # ⚠️ Sem default. Um render sem semente não pode ser repetido, e um default
    # aqui faria metade dos pedidos nascer com a mesma semente por acidente.
    seed: int = Field(ge=0, le=2**31 - 1)
    slots: list[str] = Field(min_length=1, max_length=12)
    titulo: str = Field(min_length=1, max_length=280)
    apoio: Optional[str] = Field(default=None, max_length=280)


def _artefato_dto(a: dict[str, Any]) -> dict[str, Any]:
    """DTO público do artefato.

    ⚠️ `bytes_` é artefato de palavra reservada do Python e vazava para a UI, que
    escrevia `a.bytes_` num arquivo TypeScript. `caminho` é caminho de disco do
    servidor e não tem por que sair. A tradução mora aqui e em nenhum outro lugar.
    """
    return {
        "slot": a.get("slot"),
        "mime": a.get("mime"),
        "bytes": a.get("bytes_"),
        "sha256": a.get("sha256"),
        "largura": a.get("largura"),
        "altura": a.get("altura"),
        "duracaoS": a.get("duracao_s"),
    }


def _recibo_dto(r: dict[str, Any] | None) -> dict[str, Any] | None:
    if r is None:
        return None
    return {
        "trabalhoId": r.get("trabalho_id"),
        "produzidoPor": r.get("produzido_por"),
        "motorSlug": r.get("motor_slug"),
        "motorVersao": r.get("motor_versao"),
        "seed": r.get("seed"),
        "versoes": r.get("versoes"),
        # ⚠️ NAO `r.get("parametros")`. O insumo do briefing viajava aqui inteiro
        # — nome de cliente, oferta, o que o operador digitou — para qualquer
        # consumidor da API que conseguisse ler o trabalho. Vide
        # `bancada/fronteira_publica.py`.
        "parametros": fronteira_publica.resumo_publico(r.get("parametros")),
        "artefatos": [_artefato_dto(a) for a in r.get("artefatos") or []],
        "validacoes": [
            {
                "gate": v.get("gate"),
                "resultado": v.get("resultado"),
                "detalhe": v.get("detalhe"),
                "bloqueante": v.get("bloqueante"),
            }
            for v in r.get("validacoes") or []
        ],
        "audio": r.get("audio"),
        "iniciadoEm": r.get("iniciado_em"),
        "terminadoEm": r.get("terminado_em"),
        "custoEstimadoUsd": r.get("custo_estimado_usd"),
        "custoRealUsd": r.get("custo_real_usd"),
        "assinaturaDeterminista": r.get("assinatura_determinista"),
    }


def _trabalho_dto(t: Any) -> dict[str, Any]:
    """⚠️ `vivo` é calculado do lease, não assumido do estado. Um trabalho em
    `running` cujo lease venceu NÃO está rodando — tratar ausência de batimento
    como execução ativa é o defeito que este campo existe para impedir."""
    return {
        "id": t.id,
        "estado": t.estado.value,
        "tentativa": t.tentativa,
        "maxTentativas": t.max_tentativas,
        "operario": t.operario,
        "leaseAte": t.lease_ate.isoformat() if t.lease_ate else None,
        "batimentoEm": t.batimento_em.isoformat() if t.batimento_em else None,
        "vivo": t.vivo,
        "falha": t.falha,
        "recibo": _recibo_dto(t.recibo),
        "retomaDe": t.retoma_de,
        "retomadaN": t.retomada_n,
        "canceladoPor": t.cancelado_por,
        "canceladoMotivo": t.cancelado_motivo,
        "criadoEm": t.criado_em.isoformat() if t.criado_em else None,
        # Quais operacoes fazem sentido AGORA. A tela nao precisa reimplementar a
        # regra de transicao, e nao pode oferecer botao que o servidor recusa.
        "podeRetomar": t.estado.value in ("failed", "cancelled"),
        "podeCancelar": t.estado.value in ("queued", "claimed", "running", "validating"),
    }


@router.get("/bancada/motores")
async def bancada_motores(_: Identidade = Depends(exigir_usuario)) -> dict[str, Any]:
    """Quais motores ESTA máquina consegue rodar agora.

    ⚠️ Diferente de `criativo_motor`, que diz quais motores existem no patrimônio.
    A tela precisa dos dois: um motor registrado que esta máquina não roda não
    pode oferecer botão de produzir.
    """
    return {"motores": bancada_servico.motores_disponiveis()}


def _tenant(identidade: Identidade) -> str:
    """O dono do trabalho.

    ⚠️ Hoje é o `sub` da identidade: o Estúdio não tem conceito de conta acima do
    usuário, e inventar um `tenant_id` fixo agora criaria um isolamento que
    parece existir e não existe. Quando houver conta, este é o único lugar que
    muda — e a chave de idempotência já carrega o valor, então trabalhos antigos
    de um usuário não se misturam com os da conta dele.
    """
    return str(getattr(identidade, "sub", "") or "anonimo")


async def _despachar(despachante: Any, trabalho_id: str) -> None:
    """Despacha SEM segurar a thread do event loop, e pela fronteira certa.

    ## Os dois defeitos que esta função fecha

    1. **Fronteira contornada.** As rotas da bancada pegavam o `DespachanteLocal`
       direto do singleton (`bancada_servico.montar()`) e chamavam
       `despachar(...)`. `escolher_despachante()` — a porta fail-closed que
       recusa produção em ambiente sem processo de vida longa — não aparecia em
       lugar nenhum de `backend/app/routers/`. Ou seja: a mesma casa aplicava a
       fronteira no caminho do Estúdio e a ignorava no caminho da bancada, e na
       Vercel o render rodava dentro do request gravando num SQLite que a
       plataforma evapora.

    2. **Loop travado.** `bancada_criar` é `async def`, então roda NA THREAD DO
       EVENT LOOP; `DespachanteLocal.despachar` é inteiramente síncrono
       (`begin immediate`, `motor.produzir`, sha256 por artefato, `rmtree`).
       Durante todo o render, NENHUMA outra requisição do processo era atendida
       — /health, listagem, login, tudo enfileirado atrás. Não é lentidão da
       rota: é parada do servidor. `asyncio.to_thread` é o caminho que o próprio
       Estúdio já usava.
    """
    import asyncio  # noqa: PLC0415

    from app.criativo.bancada.despacho import (  # noqa: PLC0415
        DespachoIndisponivel,
        escolher_despachante,
    )

    try:
        escolhido = escolher_despachante()
    except DespachoIndisponivel as e:
        # ⚠️ 503 e NÃO 201. O trabalho fica `queued` — durável e visível — e a
        # resposta diz que ninguém vai executá-lo aqui. Um 201 sobre produção
        # que a plataforma vai congelar é a mentira que esta porta existe para
        # impedir.
        raise _falha("ESTUDIO.despacho_indisponivel", e.motivo, 503) from e

    if not escolhido.sincrono:
        # Modo fila: o worker externo reivindica. O request só devolve o id.
        return None
    await asyncio.to_thread(despachante.despachar, trabalho_id)
    return None


@router.post("/bancada/trabalhos", status_code=201)
async def bancada_criar(
    pedido: PedidoDeProducao,
    resposta: Response,
    identidade: Identidade = Depends(exigir_usuario),
) -> dict[str, Any]:
    deposito, _op, despachante = bancada_servico.montar()

    try:
        formatos = [dominio.formato_de(s) for s in pedido.slots]
    except dominio.SlotDesconhecido as e:
        raise _falha(
            "ESTUDIO.formato_invalido",
            f"O executor não conhece o formato `{e.args[0]}`.",
            400,
        ) from e

    encomenda = EncomendaDaBancada(
        receita_id=pedido.receitaId,
        tenant_id=_tenant(identidade),
        motor_slug=pedido.motorSlug,
        modo_slug=pedido.modoSlug,
        finalidade_slug=pedido.finalidadeSlug,
        seed=pedido.seed,
        saidas=tuple(
            SaidaPedida(f.slot, f.largura, f.altura, "imagem", "image/png")
            for f in formatos
        ),
        # ⚠️ `apoio` ausente e `apoio` vazio são o MESMO pedido: os dois produzem
        # uma peça sem linha de apoio. Colapsar aqui, no limite da API, é decisão
        # declarada; colapsar no meio do domínio seria acidente.
        parametros={"titulo": pedido.titulo, "apoio": (pedido.apoio or "").strip()},
    )
    trabalho, criado = deposito.enfileirar(encomenda)
    if not criado:
        # Idempotência: o mesmo pedido não produz de novo. 200, não 201, e a
        # marca no cabeçalho para a tela poder dizer que não houve gasto novo.
        resposta.status_code = 200
        resposta.headers["X-Criativo-Idempotente"] = "replay"
        return _trabalho_dto(trabalho)

    await _despachar(despachante, trabalho.id)
    # A leitura pós-despacho continua dentro da mesma fronteira de tenant da
    # criação. O UUID não é autorização: buscar sem o filtro faria esta rota
    # diferir das rotas de leitura/listagem e permitiria ao depósito devolver
    # uma linha fora do escopo autenticado.
    final = deposito.por_id(trabalho.id, tenant_id=_tenant(identidade))
    return _trabalho_dto(final if final is not None else trabalho)


@router.get("/bancada/trabalhos")
async def bancada_listar(
    identidade: Identidade = Depends(exigir_usuario),
    limite: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    deposito, _op, _d = bancada_servico.montar()
    trabalhos = deposito.listar(tenant_id=_tenant(identidade), limite=limite)
    return {"trabalhos": [_trabalho_dto(t) for t in trabalhos]}


@router.get("/bancada/trabalhos/{trabalho_id}")
async def bancada_ler(
    trabalho_id: str, identidade: Identidade = Depends(exigir_usuario)
) -> dict[str, Any]:
    deposito, _op, _d = bancada_servico.montar()
    # ⚠️ `tenant_id` na consulta, não conferido depois. Buscar sem filtro e
    # comparar em Python já teria lido a linha alheia.
    t = deposito.por_id(trabalho_id, tenant_id=_tenant(identidade))
    if t is None:
        # Mesmo 404 para "não existe" e "não é seu": responder diferente
        # confirmaria a existência de trabalho alheio a quem tem o UUID.
        raise _falha("ESTUDIO.trabalho_nao_encontrado", "Trabalho não encontrado.", 404)
    return _trabalho_dto(t)


class PedidoDeCancelamento(BaseModel):
    motivo: str = Field(min_length=3, max_length=280)


@router.post("/bancada/trabalhos/{trabalho_id}/cancelar")
async def bancada_cancelar(
    trabalho_id: str,
    pedido: PedidoDeCancelamento,
    identidade: Identidade = Depends(exigir_usuario),
) -> dict[str, Any]:
    from app.criativo.bancada import TransicaoProibida

    deposito, _op, _d = bancada_servico.montar()
    try:
        t = deposito.cancelar(
            trabalho_id,
            tenant_id=_tenant(identidade),
            por=_tenant(identidade),
            motivo=pedido.motivo,
        )
    except KeyError as e:
        raise _falha(
            "ESTUDIO.trabalho_nao_encontrado", "Trabalho não encontrado.", 404
        ) from e
    except TransicaoProibida as e:
        raise _falha(
            "ESTUDIO.nao_cancelavel",
            "Este trabalho já terminou e não pode ser cancelado.",
            409,
        ) from e
    return _trabalho_dto(t)


@router.post("/bancada/trabalhos/{trabalho_id}/retomar", status_code=201)
async def bancada_retomar(
    trabalho_id: str,
    resposta: Response,
    identidade: Identidade = Depends(exigir_usuario),
) -> dict[str, Any]:
    """Cria um trabalho NOVO a partir de um terminal, com linhagem.

    ⚠️ Não reabre o antigo. Um `failed` guarda o motivo de ter falhado, e reabrir
    apagaria essa história. Dois cliques na mesma retomada convergem para o mesmo
    trabalho novo, porque a chave é derivada da original mais o número da retomada.
    """
    from app.criativo.bancada import TransicaoProibida

    deposito, _op, despachante = bancada_servico.montar()
    try:
        novo, criado = deposito.retomar(trabalho_id, tenant_id=_tenant(identidade))
    except KeyError as e:
        raise _falha(
            "ESTUDIO.trabalho_nao_encontrado", "Trabalho não encontrado.", 404
        ) from e
    except TransicaoProibida as e:
        raise _falha(
            "ESTUDIO.nao_retomavel",
            "Só um trabalho que falhou ou foi cancelado pode ser retomado.",
            409,
        ) from e
    if not criado:
        resposta.status_code = 200
        resposta.headers["X-Criativo-Idempotente"] = "replay"
        return _trabalho_dto(novo)
    await _despachar(despachante, novo.id)
    # A retomada cria outro trabalho, mas não cria outra fronteira de acesso.
    # O recibo final só pode ser relido sob o tenant que autorizou a retomada.
    final = deposito.por_id(novo.id, tenant_id=_tenant(identidade))
    return _trabalho_dto(final if final is not None else novo)


@router.get("/bancada/trabalhos/{trabalho_id}/linhagem")
async def bancada_linhagem(
    trabalho_id: str, identidade: Identidade = Depends(exigir_usuario)
) -> dict[str, Any]:
    deposito, _op, _d = bancada_servico.montar()
    try:
        cadeia = deposito.linhagem(trabalho_id, tenant_id=_tenant(identidade))
    except KeyError as e:
        raise _falha(
            "ESTUDIO.trabalho_nao_encontrado", "Trabalho não encontrado.", 404
        ) from e
    return {"linhagem": [_trabalho_dto(t) for t in cadeia]}


@router.get("/bancada/arquivo/{trabalho_id}/{slot}")
async def bancada_arquivo(
    trabalho_id: str, slot: str, identidade: Identidade = Depends(exigir_usuario)
) -> Any:
    """Serve o artefato produzido localmente.

    ⚠️ O caminho vem do RECIBO, nunca da URL. Montar o caminho a partir do que o
    cliente mandou seria travessia de diretório com outro nome.
    """
    from fastapi.responses import FileResponse

    deposito, _op, _d = bancada_servico.montar()
    t = deposito.por_id(trabalho_id, tenant_id=_tenant(identidade))
    if t is None or not t.recibo:
        raise _falha("ESTUDIO.trabalho_nao_encontrado", "Trabalho não encontrado.", 404)
    for a in t.recibo.get("artefatos", []):
        if a.get("slot") == slot:
            caminho = Path(a["caminho"])
            raiz = bancada_servico.raiz_da_bancada().resolve()
            # Segunda barreira: mesmo vindo do recibo, o arquivo tem de estar
            # dentro da raiz da bancada. Um recibo adulterado não vira leitura
            # arbitrária de disco.
            if not caminho.resolve().is_relative_to(raiz) or not caminho.is_file():
                break
            return FileResponse(caminho, media_type=a.get("mime") or "image/png")
    raise _falha("ESTUDIO.arquivo_indisponivel", "Peça não disponível.", 404)
