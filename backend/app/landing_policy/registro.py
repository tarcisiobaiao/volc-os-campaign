"""O REGISTRO de aprovação — onde o recibo do portão 2 fica, e como o portão 3 o acha.

## Por que NÃO existe tabela nova aqui

O buraco que este módulo fecha é real e foi medido: `sha256_aprovado` não era
gravado por nada fora dos testes, então `DERIVA_AO_VIVO` saiu `unavailable` nos
cinco recibos preservados, e a própria matriz de fontes registra o achado como
*"NOT MEASURABLE ... That gap is itself the finding."* Sem o lado esquerdo da
comparação, o portão 3 não tem o que comparar.

A resposta óbvia seria uma tabela de aprovações por URL. Ela não é necessária:

    public.pautador_funnel_runs.paginas_publicadas  jsonb not null default '[]'

já existe (`src/sql/pautador/04_matriz_do_redator.sql:60`), já é o CONTRATO
declarado com o módulo de campanha, e já viaja verbatim do motor para o Supabase
— `worker.resumo_do_estado` faz `publicadas = [p for p in state.published.values()]`
sem filtrar chave nenhuma. Um recibo colocado em `state.published[n]` chega ao
banco inteiro, sem migration, sem coluna nova e sem uma segunda autoridade sobre
o mesmo fato.

Inventar tabela antes de provar que o schema existente não serve é como duas
fontes de verdade nascem — e a de baixo é sempre a que sobrevive ao script de
manutenção das três da manhã.

## O que este módulo NÃO faz

Ele não abre conexão, não escreve no Supabase e não conhece o cliente HTTP. Ele
resolve e monta ESTRUTURAS. Quem tem a linha do run entrega o `paginas_publicadas`
e recebe o recibo; quem grava, grava pelo caminho que já existe. Manter I/O fora
daqui é o que deixa o portão inteiro ser testado sem rede.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CHAVE_DO_RECIBO = "landing_policy_receipt"


#: Parâmetros que a plataforma de anúncio, o e-mail e a rede social GRUDAM na
#: URL. Eles não mudam a página; nenhum deles chega a um `WP_Query`.
_PARAMETROS_DE_RASTREIO = frozenset({
    "gclid", "gbraid", "wbraid", "dclid", "gad_source", "gclsrc",
    "fbclid", "msclkid", "ttclid", "twclid", "igshid", "mc_eid", "mc_cid",
    "_ga", "_gl", "yclid", "ref", "referrer",
})
_PREFIXOS_DE_RASTREIO = ("utm_",)


def url_canonica(url: str) -> str:
    """A forma pela qual duas URLs são consideradas o MESMO destino.

    ⚠️ SÓ O RASTREIO SAI DA QUERY, e essa distinção custou um achado.

    A primeira versão derrubava a query INTEIRA. Ela resolvia o problema real —
    um destino do Google chega com `gclid` grudado, e um recibo só encontrável
    com a query exata é um recibo que nunca é encontrado — e criava outro:
    `/r/x/?produto=cartao` e `/r/x/?produto=emprestimo` colidiam, e
    `recibo_da_url` devolvia o recibo da primeira. Duas páginas materialmente
    diferentes passavam a compartilhar uma aprovação.

    Agora saem apenas os parâmetros que a plataforma acrescenta e que não
    chegam a decidir conteúdo. O que sobra é ordenado, para que a ordem dos
    parâmetros não invente duas URLs de uma.

    O fragmento sai inteiro: ele nunca chega ao servidor. A barra final é
    normalizada porque o WordPress serve as duas formas. Esquema e host são
    PRESERVADOS — ali a diferença é o assunto, não ruído.
    """
    if not url:
        return ""
    partes = urlsplit(url.strip())
    caminho = partes.path or "/"
    if len(caminho) > 1:
        caminho = caminho.rstrip("/")
    mantidos = sorted(
        (chave, valor)
        for chave, valor in parse_qsl(partes.query, keep_blank_values=True)
        if chave.lower() not in _PARAMETROS_DE_RASTREIO
        and not chave.lower().startswith(_PREFIXOS_DE_RASTREIO)
    )
    return urlunsplit(
        (partes.scheme.lower(), partes.netloc.lower(), caminho, urlencode(mantidos), "")
    )


def recibo_da_url(
    paginas_publicadas: Iterable[dict[str, Any]] | None, url: str
) -> dict[str, Any] | None:
    """O recibo de aprovação daquela URL, ou `None`.

    `None` não é "está tudo bem": é exatamente o que `varrer_recibo` transforma
    em `RECIBO_DE_APROVACAO_AUSENTE`, que reprova destino pago. A ausência tem
    que chegar ao portão como ausência — devolver um recibo vazio aqui seria
    fabricar aprovação.
    """
    alvo = url_canonica(url)
    if not alvo:
        return None
    for pagina in paginas_publicadas or []:
        if not isinstance(pagina, dict):
            continue
        if url_canonica(str(pagina.get("url_wp") or "")) != alvo:
            continue
        recibo = pagina.get(CHAVE_DO_RECIBO)
        if isinstance(recibo, dict) and recibo:
            return recibo
    return None


def anexar_recibo(publicada: dict[str, Any], recibo: dict[str, Any]) -> dict[str, Any]:
    """Põe o recibo no registro que o motor devolve ao publicar.

    Devolve um dict NOVO: `state.published[n]` é lido por outros passos, e
    mutar em lugar transformaria um erro de ordem de execução em corrupção
    silenciosa do estado do run.
    """
    return {**publicada, CHAVE_DO_RECIBO: recibo}


# ── o recibo de RECUSA, quando não há banco ────────────────────────────────


def gravar_recibo_local(destino: Path, recibo: dict[str, Any]) -> Path:
    """Grava um recibo em disco, atomicamente.

    Existe para a RECUSA: quando o portão 2 barra, não há publicação, logo não
    há linha de `paginas_publicadas` onde pendurar o recibo — e uma recusa sem
    rastro é indistinguível de uma publicação que ninguém tentou.

    `tmp + fsync + os.replace` é o mesmo padrão de `app/work_road/inbox_store.py`,
    e pelo mesmo motivo: um recibo pela metade é pior que recibo nenhum, porque
    ele parece um recibo.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(recibo, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, caminho_tmp = tempfile.mkstemp(dir=str(destino.parent), prefix=".recibo-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            arquivo.write(texto)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(caminho_tmp, destino)
    except BaseException:
        try:
            os.unlink(caminho_tmp)
        except OSError:
            pass
        raise
    return destino


def nome_do_recibo(page_number: int | str, *, recusado: bool = False) -> str:
    """O nome do arquivo do recibo dentro da pasta do run.

    O sufixo distingue recusa de aprovação no `ls`. Guardar as duas com o mesmo
    nome faria a segunda tentativa apagar a prova da primeira, que é justamente
    a que explica por que houve segunda.
    """
    return f"p{page_number}.landing_policy{'.recusa' if recusado else ''}.json"
