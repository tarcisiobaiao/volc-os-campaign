"""Tradução de linha de banco para o contrato que o browser consome.

Camada de apresentação e nada mais: nenhuma regra, nenhuma consulta, nenhuma
decisão. Ela existe separada por um motivo prático e um de segurança.

O prático: o banco fala `snake_case` e o frontend fala `camelCase`, e espalhar
essa tradução por dentro do router faria cada endpoint reinventar a sua, com
divergências que só aparecem na tela.

O de segurança, que é o que importa: **esta é a última fronteira antes do
browser**, e é aqui que `storage_chave`, `insumo_sanitizado` e qualquer campo
interno param. Um `dict(linha)` devolvido direto de um `select *` publica a
chave de storage, o caminho e tudo que a tabela ganhar no futuro. As funções
abaixo montam o dicionário CAMPO A CAMPO de propósito: uma coluna nova não
vaza sozinha, ela precisa ser adicionada aqui por alguém.
"""

from __future__ import annotations

from typing import Any

from .armazenamento import Assinador
from .dominio import formato_de

# TTL curto: a URL só precisa viver o suficiente para a tag de mídia carregar e
# para um download começar. Cinco minutos é generoso para os dois e curto o
# bastante para um token copiado de um print não valer nada amanhã.
TTL_PREVIEW_S = 300


def _url(assinador: Assinador, chave: str | None) -> str | None:
    """URL assinada, ou `None`. Nunca o caminho, nunca a chave crua."""
    if not chave:
        return None
    return f"/api/criativos/arquivo/{assinador.assinar(chave, ttl_s=TTL_PREVIEW_S)}"


def _falha(bruta: Any) -> dict[str, Any] | None:
    if not bruta or not isinstance(bruta, dict):
        return None
    return {
        "codigo": bruta.get("codigo") or "MOTOR.desconhecido",
        "mensagem": bruta.get("mensagem") or "",
        "permanente": bool(bruta.get("permanente")),
        "em": bruta.get("em"),
    }


def _n(valor: Any) -> Any:
    """Passa `None` adiante como `None`. Existe para tornar a intenção visível.

    Sem esta função, o próximo a mexer aqui escreve `int(linha["largura"] or 0)`
    sem pensar, e a ausência de medida vira zero medido no contrato inteiro.
    """
    return valor


def rendition_dto(linha: dict[str, Any], assinador: Assinador) -> dict[str, Any]:
    slot = linha["slot"]
    try:
        rotulo = formato_de(slot).rotulo
    except Exception:  # noqa: BLE001 — slot histórico que saiu do catálogo
        rotulo = slot
    erro = None
    if linha.get("erro_codigo"):
        erro = {
            "codigo": linha["erro_codigo"],
            "mensagem": linha.get("erro_mensagem") or "",
            "permanente": bool(linha.get("erro_permanente")),
            "em": linha.get("erro_em"),
        }
    return {
        "id": str(linha["id"]),
        "slot": slot,
        "rotulo": rotulo,
        "estado": linha["estado"],
        "larguraPedida": linha["largura_pedida"],
        "alturaPedida": linha["altura_pedida"],
        "nativoLargura": _n(linha.get("nativo_largura")),
        "nativoAltura": _n(linha.get("nativo_altura")),
        "largura": _n(linha.get("largura")),
        "altura": _n(linha.get("altura")),
        "bytesTotais": _n(linha.get("bytes_totais")),
        "mime": _n(linha.get("mime")),
        "contentHash": _n(linha.get("content_hash")),
        "enquadramento": _n(linha.get("enquadramento")),
        "masterId": str(linha["master_id"]) if linha.get("master_id") else None,
        "previewUrl": _url(assinador, linha.get("storage_chave")),
        "erro": erro,
        "custoUsd": _n(linha.get("custo_usd")),
        "concluidaEm": _n(linha.get("concluida_em")),
    }


def job_dto(
    job: dict[str, Any],
    renditions: list[dict[str, Any]],
    assinador: Assinador,
    *,
    projeto_titulo: str = "",
    tipo: str = "imagem",
    modo: str = "full_llm",
    cursor: int = 0,
) -> dict[str, Any]:
    return {
        "id": str(job["id"]),
        "briefingId": str(job["briefing_id"]),
        "projetoId": str(job.get("projeto_id") or ""),
        "projetoTitulo": projeto_titulo,
        "tipo": tipo,
        "modo": modo,
        "motor": job["motor"],
        "motorVersao": job["motor_versao"],
        "estado": job["estado"],
        "tentativa": int(job.get("tentativa") or 1),
        "procedenciaExecucao": job.get("procedencia_execucao") or "volc_os",
        "origemExterna": job.get("origem_externa"),
        "custoEstimadoUsd": _n(job.get("custo_estimado_usd")),
        "custoRealUsd": _n(job.get("custo_real_usd")),
        "iniciadoEm": _n(job.get("iniciado_em")),
        "terminadoEm": _n(job.get("terminado_em")),
        # PEDIDO de cancelamento e CONFIRMAÇÃO são fatos diferentes, e a SPEC §16
        # pede que a interface os distinga. Sem estes dois campos o operador
        # clicava em interromper e nada na tela mudava: o `POST /cancel` devolvia
        # o job ainda em `running`, idêntico ao de antes.
        "canceladoPedidoEm": _n(job.get("cancelado_pedido_em")),
        "canceladoEm": _n(job.get("cancelado_em")),
        "criadoEm": job.get("criado_em"),
        "falha": _falha(job.get("falha")),
        "renditions": [rendition_dto(r, assinador) for r in renditions],
        "cursorEventos": cursor,
    }


def evento_dto(linha: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": int(linha["seq"]),
        "fase": linha["fase"],
        "mensagem": _n(linha.get("mensagem")),
        # Nunca `or 0`. Ausência de progresso medido é `null`, e é assim que a
        # interface sabe que deve mostrar a fase em vez de uma barra.
        "percentual": _n(linha.get("percentual")),
        "slot": _n(linha.get("slot")),
        "em": linha["em"],
    }


def aprovacao_dto(linha: dict[str, Any], nome: str | None = None) -> dict[str, Any]:
    return {
        "id": str(linha["id"]),
        "subjectTipo": linha["subject_tipo"],
        "subjectId": str(linha["subject_id"]),
        "versao": int(linha["versao"]),
        "finalidade": linha["finalidade"],
        "decisao": linha["decisao"],
        "atorId": str(linha["ator_id"]),
        "atorNome": nome,
        "decididoEm": linha["decidido_em"],
        "motivo": _n(linha.get("motivo")),
        "revogadaEm": _n(linha.get("revogada_em")),
    }


def master_dto(
    linha: dict[str, Any],
    assinador: Assinador,
    *,
    projeto_titulo: str = "",
    aprovacao: dict[str, Any] | None = None,
    # ⚠️ SEM DEFAULT, e isto e conserto de uma mentira medida em 28/08/2026.
    #
    # A versao anterior assumia `"volc_os"` por omissao, e tres dos quatro
    # chamadores omitiam. A tela transforma esse campo numa frase categorica:
    # "Produzida pelo motor do VOLC O.S." — a exata afirmacao que o modulo de
    # video inteiro foi escrito para impedir. Ausencia de leitura virava
    # afirmacao de autoria.
    #
    # `None` significa "nao apurei", e a apresentacao devolve `None`, nao
    # `volc_os`. Quem quiser afirmar autoria tem de ter lido o job.
    procedencia_execucao: str | None,
    poster_chave: str | None = None,
) -> dict[str, Any]:
    return {
        "id": str(linha["id"]),
        "jobId": str(linha["job_id"]),
        "projetoId": str(linha["projeto_id"]),
        "projetoTitulo": projeto_titulo,
        "slot": linha["slot"],
        "kind": linha["kind"],
        "mime": linha["mime"],
        "largura": _n(linha.get("largura")),
        "altura": _n(linha.get("altura")),
        "bytesTotais": _n(linha.get("bytes_totais")),
        "duracaoMs": _n(linha.get("duracao_ms")),
        "contentHash": linha["content_hash"],
        "versao": int(linha.get("versao") or 1),
        "raizId": str(linha["raiz_id"]) if linha.get("raiz_id") else None,
        "substituiId": str(linha["substitui_id"]) if linha.get("substitui_id") else None,
        "procedencia": {
            "motor": linha["motor"],
            "motorVersao": linha["motor_versao"],
            # O HASH do insumo, nunca o insumo. O prompt não atravessa esta
            # fronteira em nenhuma circunstância (SPEC §10).
            "insumoHash": linha["insumo_hash"],
            "brandPackId": str(linha["brand_pack_id"]) if linha.get("brand_pack_id") else None,
            "brandPackVersao": _n(linha.get("brand_pack_versao")),
            "criadoEm": linha["criado_em"],
            "custoUsd": _n(linha.get("custo_usd")),
            "licenca": _n(linha.get("licenca")),
            "credito": _n(linha.get("credito")),
            "disclosure": _n(linha.get("disclosure")),
            "sintetico": bool(linha.get("sintetico", True)),
        },
        "procedenciaExecucao": procedencia_execucao,
        "previewUrl": _url(assinador, linha.get("storage_chave")),
        "posterUrl": _url(assinador, poster_chave),
        "aprovacaoVigente": aprovacao,
        # Lista vazia mais `usoApurado: false` diz "ninguém apurou", que é
        # diferente de "não há uso". A apuração de uso é trabalho de C2 em
        # diante; declarar isso agora evita que a tela afirme o que não sabe.
        "usos": [],
        "usoApurado": False,
        "criadoEm": linha["criado_em"],
        "arquivadoEm": _n(linha.get("arquivado_em")),
    }


def brand_pack_dto(linha: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(linha["id"]),
        "slug": linha["slug"],
        "versao": int(linha["versao"]),
        "nome": linha["nome"],
        "tokens": linha.get("tokens") or {},
        "fontesHash": _n(linha.get("fontes_hash")),
        "ativo": bool(linha.get("ativo", True)),
        "criadoEm": linha["criado_em"],
    }

# ─────────────────────────────────────────────────────────────────────────────
# Parque criativo
# ─────────────────────────────────────────────────────────────────────────────

# O banco fala `snake_case` porque Postgres fala; a API fala `camelCase` porque o
# TypeScript fala. A tradução vive AQUI e em nenhum outro lugar — espalhá-la pelos
# consumidores é como o mesmo campo ganha dois nomes e depois dois significados.
_RENOMES = {
    "cofre_asset_id": "cofreAssetId",
    "versao_do_adaptador": "versaoDoAdaptador",
    "custo_referencia_usd": "custoReferenciaUsd",
    "custo_unidade": "custoUnidade",
    "custo_fonte": "custoFonte",
    "verificado_em": "verificadoEm",
    "exige_provider_de_imagem": "exigeProviderDeImagem",
    "estado_de_prova": "estadoDeProva",
    "saidas_no_snapshot": "saidasNoSnapshot",
    "tipo_de_asset": "tipoDeAsset",
    "destinos_tipicos": "destinosTipicos",
    "papeis_obrigatorios": "papeisObrigatorios",
    "motor_id": "motorId",
    "voice_id": "voiceId",
    "quantidade_minima": "quantidadeMinima",
    "quantidade_maxima": "quantidadeMaxima",
    "quantidade_recomendada": "quantidadeRecomendada",
    "proporcao_alvo": "proporcaoAlvo",
    "tolerancia_proporcao": "toleranciaProporcao",
    "largura_minima": "larguraMinima",
    "altura_minima": "alturaMinima",
    "largura_recomendada": "larguraRecomendada",
    "altura_recomendada": "alturaRecomendada",
    "bytes_maximos": "bytesMaximos",
    "mimes_aceitos": "mimesAceitos",
    "duracao_minima_s": "duracaoMinimaS",
    "duracao_maxima_s": "duracaoMaximaS",
    "caracteres_maximos": "caracteresMaximos",
    "caracteres_de_pelo_menos_um": "caracteresDePeloMenosUm",
    "fonte_dos_numeros": "fonteDosNumeros",
    "executavel_agora": "executavelAgora",
    "motivo_se_nao": "motivoSeNao",
}


def _camel(chave: str) -> str:
    return _RENOMES.get(chave, chave)


# Os campos que CADA coleção publica, nomeados um a um.
#
# ⚠️ S2. A primeira versão fazia `{_camel(k): _n(v) for k, v in linha.items()}` —
# publicava tudo o que viesse do banco. O docstring deste arquivo promete montagem
# campo a campo justamente para que uma coluna nova não vaze sozinha, e a
# compreensão de dicionário desfazia a promessa em uma linha. Hoje é inofensivo
# porque o `select` de `parque.py` é explícito; a barreira descrita é que não
# existia. Quem acrescentar coluna ao `select` E a esta lista publica de propósito.
_CAMPOS_DO_PARQUE: dict[str, tuple[str, ...]] = {
    "motores": (
        "id", "slug", "nome", "produz", "runtime", "cofre_asset_id", "provider",
        "modelo", "versao_do_adaptador", "custo_referencia_usd", "custo_unidade",
        "custo_fonte", "capacidades", "fonte", "verificado_em", "ativo",
    ),
    "modos": (
        "id", "slug", "nome", "descricao", "exige_provider_de_imagem", "renderer",
        "estado_de_prova", "prova", "saidas_no_snapshot", "fonte", "ordem",
    ),
    "formatos": (
        "id", "slot", "rotulo", "proporcao", "largura", "altura", "tipo_de_asset",
        "midia", "descricao", "destinos_tipicos", "fonte", "ativo", "ordem",
        "executavel_agora", "motivo_se_nao",
    ),
    "finalidades": ("id", "slug", "nome", "descricao", "classe", "ativo", "ordem"),
    "skins": (
        "id", "slug", "nicho", "arco", "papeis_obrigatorios", "elementos",
        "motor_id", "fonte", "ativo",
    ),
    "vozes": (
        "id", "slug", "voice_id", "fallbacks", "estilo", "idioma", "provider",
        "motor_id", "fonte", "ativo",
    ),
    "gates": ("id", "slug", "motor_id", "familia", "midia", "descricao",
              "bloqueante", "fonte"),
    "exigenciasDeCanal": (
        "id", "canal", "tipo_de_asset", "quantidade_minima", "quantidade_maxima",
        "quantidade_recomendada", "proporcao_alvo", "tolerancia_proporcao",
        "largura_minima", "altura_minima", "largura_recomendada",
        "altura_recomendada", "bytes_maximos", "mimes_aceitos", "duracao_minima_s",
        "duracao_maxima_s", "caracteres_maximos", "caracteres_de_pelo_menos_um",
        "provisorio", "fonte_dos_numeros", "verificado_em",
    ),
    "tetosCombinados": ("id", "canal", "rotulo", "tipos", "minimo", "maximo", "fonte"),
}


def parque_dto(leitura: Any) -> dict[str, Any]:
    """Serializa a leitura do parque preservando a diferença entre `[]` e ausência.

    ⚠️ Uma tabela que respondeu vazia vira `[]`. Uma tabela que NÃO respondeu vira
    `null` e o nome dela entra em `naoLidas`. A tela precisa das duas para não dizer
    "nenhum motor cadastrado" quando o banco caiu.
    """
    itens: dict[str, Any] = {}
    for chave, linhas in leitura.itens.items():
        if linhas is None:
            itens[chave] = None
            continue
        campos = _CAMPOS_DO_PARQUE.get(chave)
        if campos is None:
            # Coleção sem lista declarada não é publicada. Silêncio aqui é melhor
            # que vazamento: quem acrescentar coleção declara os campos dela.
            itens[chave] = []
            continue
        itens[chave] = [
            # `linha.get(c)` e não `linha[c]`: uma coluna que o `select` pediu e o
            # banco não devolveu vira `None` explícito, não KeyError na serialização.
            {_camel(c): _n(linha.get(c)) for c in campos}
            for linha in linhas
        ]

    return {
        **itens,
        "naoLidas": sorted(leitura.falhas),
        "divergencias": [
            {
                "onde": d.onde,
                "oQue": d.o_que,
                "banco": d.banco,
                "runtime": d.runtime,
            }
            for d in leitura.divergencias
        ],
        "lidoEm": leitura.lido_em,
        "completa": leitura.completa,
    }
