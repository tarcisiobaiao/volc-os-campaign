"""A ponte entre um build OBSERVADO da fábrica e o contrato do Estúdio.

## Observado, não importado, e a diferença não é vocabulário

O VOLC O.S. **lê** um build que a fábrica externa produziu. Ele não copiou os
bytes, não os guardou no object storage e não os registrou como patrimônio
próprio. Por isso o `CreativeJob` e o `AssetMaster` desta rota são **montados na
leitura e nunca persistidos**: gravar uma linha em `criativo_master` faria o
arquivo da fábrica aparecer na biblioteca ao lado das peças que o Estúdio
realmente produziu, com o mesmo peso, e a diferença sumiria na primeira listagem.

A `migration` já prevê o caso em que a importação for desejada
(`criativo_job.procedencia_execucao = 'observado'` com a CHECK
`criativo_job_observado_com_origem`). Nesta rodada, nada é escrito: a leitura é o
produto, e ela é honesta sobre isso.

## O identificador que atravessa a fronteira

O frontend recebe `videoUrl` e `posterUrl` como URLs assinadas cujo alvo é uma
chave da forma `fabrica/<slug>/<arquivo>`. O prefixo `fabrica/` é o que faz o
endpoint de arquivo servir por streaming a partir do disco da fábrica em vez de
procurar no object storage do Estúdio. **Nenhum caminho absoluto atravessa**: o
mapeamento de chave para caminho acontece aqui, no servidor, e a fábrica sequer
precisa estar no mesmo disco amanhã.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from . import video_observado
from .armazenamento import Assinador

_CHAVE = re.compile(r"^fabrica/(?P<slug>[a-z0-9_-]{1,64})/(?P<arquivo>video\.mp4|poster\.jpg)$")

TTL_VIDEO_S = 900  # o player precisa da URL viva durante a reprodução inteira


def chave_do_video(slug: str) -> str:
    return f"fabrica/{slug}/video.mp4"


def chave_do_poster(slug: str) -> str:
    return f"fabrica/{slug}/poster.jpg"


# Cache de caminho por chave. ⚠️ Existe por uma medida, não por gosto.
#
# `ler_build` calcula o sha256 do MP4 inteiro (39 MB no `short_odete`), e
# `caminho_da_chave` era chamada a CADA requisição de faixa, dentro de uma
# corrotina, sem `to_thread`. Um player arrastando a barra dispara dezenas de
# ranges, e cada um bloqueava o event loop relendo e re-hasheando o arquivo
# inteiro — congelando junto todos os streams SSE e o resto da API.
#
# A chave já é derivada do slug e do nome do arquivo, e o build da fábrica é
# imutável por construção (`freeze.json` existe justamente para isso), então
# memorizar o caminho resolvido é seguro. O hash continua sendo calculado uma
# vez, na leitura do build, que é onde ele significa alguma coisa.
_CAMINHOS: dict[str, Path] = {}


def caminho_da_chave(chave: str) -> Path | None:
    """Resolve `fabrica/<slug>/<arquivo>` para um caminho real, ou `None`.

    A allowlist do regex é a defesa: o slug não pode conter `.`, `/` nem
    maiúscula, e o nome do arquivo é um de dois literais. Não há forma de
    construir uma chave que aponte para fora do build, mesmo que o token fosse
    forjado (e ele não pode ser, mas defesa em profundidade custa uma linha).
    """
    casou = _CHAVE.match(chave or "")
    if not casou:
        return None
    memorizado = _CAMINHOS.get(chave)
    if memorizado is not None and memorizado.is_file():
        return memorizado
    if not video_observado.disponivel():
        return None
    try:
        build = video_observado.ler_build(casou.group("slug"))
    except Exception:  # noqa: BLE001 — build sumiu entre a assinatura e o uso
        return None
    # `ler_build` distingue "não há de onde ler" de "este build não existe", e
    # devolve `FabricaIndisponivel` no primeiro caso em vez de levantar. Tratar
    # os dois como o mesmo `None` aqui é correto: o efeito para o cliente é
    # idêntico (não há arquivo), e é a rota de leitura que explica qual é o caso.
    if isinstance(build, video_observado.FabricaIndisponivel):
        return None
    alvo = (
        build.mp4_caminho
        if casou.group("arquivo") == "video.mp4"
        else build.poster_caminho
    )
    if alvo is None:
        return None
    caminho = Path(alvo).resolve()
    # ⚠️ Reusa a MESMA função do leitor, em vez de reler a variável com outra
    # semântica. Antes este arquivo fazia `os.environ.get(nome, default)` e o
    # leitor fazia `os.environ.get(nome) or default`: com a variável definida e
    # VAZIA, um caía no default e o outro em `Path("")`, que é o cwd. O catálogo
    # dizia que o build existia e todo byte respondia 404.
    raiz = video_observado.raiz()
    # Segunda barreira: mesmo que o leitor devolvesse um caminho inesperado, ele
    # tem de estar debaixo da raiz configurada da fábrica.
    if not caminho.is_relative_to(raiz) or not caminho.is_file():
        return None
    _CAMINHOS[chave] = caminho
    return caminho


def montar_resposta(build: Any, assinador: Assinador) -> dict[str, Any]:
    """O `VideoObservado` do contrato, montado na leitura e não persistido."""
    dicts = build.para_dicts()
    origem = dicts["origemExterna"]
    slug = origem["identificadorDoBuild"]

    job = {
        # O id é derivado do slug e estável, para que a rota possa ser recarregada
        # e compartilhada. Ele NÃO é um uuid de banco, porque não há linha:
        # inventar um uuid faria parecer que existe registro onde não existe.
        "id": f"observado:{slug}",
        "briefingId": f"observado:{slug}",
        "projetoId": f"observado:{slug}",
        "projetoTitulo": dicts["contrato"].get("titulo") or slug,
        "tipo": "video",
        "modo": "observado",
        # O motor é o da fábrica, e a versão é declaradamente desconhecida.
        "motor": "volc-factory",
        "motorVersao": origem.get("motorVersaoConhecida") or "desconhecida",
        "estado": "succeeded",
        "tentativa": 1,
        "procedenciaExecucao": "observado",
        "origemExterna": origem,
        # Nenhum custo NOSSO: não gastamos para produzir este build. O custo de
        # QA que a fábrica mediu viaja em `qa.custoQaUsd`, onde é atribuível.
        "custoEstimadoUsd": None,
        "custoRealUsd": None,
        "iniciadoEm": None,
        "terminadoEm": origem.get("congeladoEm"),
        "criadoEm": origem.get("congeladoEm") or origem.get("observadoEm"),
        "falha": None,
        "renditions": [],
        "cursorEventos": 0,
    }

    contrato = dicts["contrato"]
    master = {
        "id": f"observado:{slug}",
        "jobId": f"observado:{slug}",
        "projetoId": f"observado:{slug}",
        "projetoTitulo": contrato.get("titulo") or slug,
        "slot": "9x16",
        "kind": "video",
        "mime": build.mime or "video/mp4",
        "largura": build.largura,
        "altura": build.altura,
        "bytesTotais": build.bytes_totais,
        "duracaoMs": build.duracao_ms,
        "contentHash": build.content_hash,
        "versao": 1,
        "raizId": None,
        "substituiId": None,
        "procedencia": {
            "motor": "volc-factory",
            "motorVersao": origem.get("motorVersaoConhecida") or "desconhecida",
            "insumoHash": origem.get("hashDoArtefato", ""),
            "brandPackId": None,
            "brandPackVersao": None,
            "criadoEm": origem.get("congeladoEm") or origem.get("observadoEm"),
            "custoUsd": None,
            "licenca": None,
            "credito": None,
            "disclosure": _disclosure(dicts["ledger"]),
            "sintetico": _tem_sintetico(dicts["ledger"]),
        },
        "procedenciaExecucao": "observado",
        "previewUrl": _assinar(assinador, chave_do_video(slug), build.mp4_caminho),
        "posterUrl": _assinar(assinador, chave_do_poster(slug), build.poster_caminho),
        # Nenhuma aprovação: o Estúdio nunca decidiu nada sobre este ativo, e um
        # `aprovado` herdado do QA da fábrica confundiria gate técnico com
        # decisão humana, que são coisas diferentes (SPEC §5).
        "aprovacaoVigente": None,
        "usos": [],
        "usoApurado": False,
        "criadoEm": origem.get("congeladoEm") or origem.get("observadoEm"),
        "arquivadoEm": None,
    }

    return {
        "job": job,
        "master": master,
        "contrato": contrato,
        "ledger": dicts["ledger"],
        "qa": dicts["qa"],
        "videoUrl": master["previewUrl"],
        "posterUrl": master["posterUrl"],
        "limitacaoDeclarada": video_observado.LIMITACAO_DECLARADA,
    }


def _assinar(assinador: Assinador, chave: str, caminho: Any) -> str | None:
    if not caminho:
        return None
    return f"/api/criativos/arquivo/{assinador.assinar(chave, ttl_s=TTL_VIDEO_S)}"


def _tem_sintetico(ledger: list[dict[str, Any]]) -> bool:
    return any(item.get("sintetico") for item in ledger)


def _disclosure(ledger: list[dict[str, Any]]) -> str | None:
    """A disclosure que o ledger da fábrica declarou, ou ausência.

    Não é inventada a partir de `sintetico`: o ledger tem um campo próprio para
    isso, e derivar um texto de compliance de um booleano seria fabricar uma
    declaração legal que ninguém escreveu.
    """
    for item in ledger:
        if item.get("disclosure"):
            return str(item["disclosure"])
    return None
