"""O que pode sair pela API, e o que fica dentro.

## O defeito que este modulo fecha

O recibo, o envelope e a procedencia devolviam `parametros` e `insumo` CRUS. O
insumo e o texto do briefing — nome de cliente, oferta, numero, o que o operador
digitou. Ele entrava em `Encomenda.parametros` porque participa da chave de
idempotencia e do render, e de la viajava inteiro ate qualquer consumidor da API
que conseguisse ler o trabalho.

O caminho do Estudio, na mesma casa, ja tinha decidido o contrario e gravado o
motivo: `"insumo_sanitizado": None`, com o comentario dizendo que duplica-lo num
campo que a API le seria mais um caminho de vazamento. A bancada nao seguiu.

## O que substitui o material cru

Tres coisas, e nenhuma delas e o texto:

1. **hash canonico** — deriva do MESMO `canonizar` que a chave de idempotencia
   usa, entao dois pedidos iguais tem o mesmo hash e um pedido diferente tem
   outro. Ele identifica sem revelar.
2. **resumo allowlisted** — so os campos CATEGORICOS passam. Texto livre nunca
   passa, nem truncado: um prefixo de briefing ainda e briefing.
3. **estados de ausencia distintos** — para cada campo retido, o consumidor
   recebe POR QUE ele nao esta la, e os motivos nao se confundem.

⚠️ `hash` NAO e "prompt sanitizado". Um hash nao e uma versao limpa do texto: ele
nao pode ser lido, e chamar a ele de resumo faria a proxima pessoa achar que ha
uma sanitizacao acontecendo onde so ha uma impressao digital.

⚠️ E ausencia nao vira string vazia. `""` significaria "o operador nao escreveu
nada", e o que aconteceu foi "escreveu e a API nao devolve". Sao fatos
diferentes.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .contrato import canonizar

#: Campos que podem sair inteiros. A lista e de CATEGORIAS — valores de um
#: conjunto fechado que a propria interface oferece — e nao de texto que o
#: operador digitou. Crescer esta lista e uma decisao de exposicao: quem
#: acrescentar um campo precisa poder dizer por que ele nao carrega dado de
#: cliente.
CAMPOS_PUBLICOS: frozenset[str] = frozenset({
    "canal", "intencao", "finalidade", "modo", "formato", "destino",
    "brand_pack_id", "brand_pack_versao", "slot", "largura", "altura", "mime",
})

#: Campos que carregam texto livre do operador. Nomeados de proposito: um
#: `else: retem` silencioso esconderia que estes existem.
CAMPOS_DE_TEXTO_LIVRE: frozenset[str] = frozenset({
    "insumo", "titulo", "apoio", "prompt", "briefing", "mensagem", "audiencia",
    "objetivo", "observacao", "copy", "legenda",
})


def hash_dos_parametros(parametros: dict[str, Any] | None) -> str:
    """A impressao digital canonica do pedido. `sha256:...`, sempre.

    ⚠️ Usa `canonizar`, o MESMO do `chave_de_idempotencia`. Duas serializacoes
    diferentes do mesmo pedido dariam dois hashes, e o hash deixaria de
    identificar — que e a unica coisa que ele sabe fazer.
    """
    corpo = canonizar(dict(parametros or {}))
    cru = json.dumps(corpo, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(cru.encode("utf-8")).hexdigest()


def _motivo_da_retencao(chave: str, valor: Any) -> str:
    """Por que este campo nao saiu. Tres motivos, e eles nao se confundem."""
    if valor is None:
        return "ausente"
    if isinstance(valor, str) and not valor.strip():
        # O operador deixou em branco. Isso e um FATO sobre o pedido, e nao a
        # mesma coisa que "tinha conteudo e nos retivemos".
        return "vazio"
    if chave in CAMPOS_DE_TEXTO_LIVRE:
        return "retido_texto_livre"
    return "retido_nao_allowlisted"


def resumo_publico(parametros: dict[str, Any] | None) -> dict[str, Any]:
    """O que a API devolve no lugar de `parametros`.

    Nunca levanta e nunca devolve `None`: um pedido sem parametros tem resumo
    vazio COM hash, e o hash de `{}` e um valor legitimo.
    """
    p = dict(parametros or {})
    publicos = {k: v for k, v in p.items() if k in CAMPOS_PUBLICOS}
    retidos = {
        k: _motivo_da_retencao(k, p[k])
        for k in sorted(p)
        if k not in CAMPOS_PUBLICOS
    }
    return {
        "hash": hash_dos_parametros(p),
        "campos": publicos,
        # Nomes, nunca valores. Saber QUE existe um `insumo` e diferente de saber
        # qual e — e o consumidor precisa do primeiro para nao achar que o campo
        # sumiu.
        "retidos": retidos,
    }


def resumo_do_insumo(insumo: Any) -> dict[str, Any]:
    """O lugar do texto do briefing na resposta publica.

    Devolve estado e impressao digital. NAO devolve prefixo, sufixo, nem
    comprimento em caracteres do conteudo — comprimento de briefing e um canal
    estreito, mas e um canal.
    """
    if insumo is None:
        return {"estado": "ausente", "hash": None}
    texto = str(insumo)
    if not texto.strip():
        return {"estado": "vazio", "hash": None}
    return {
        "estado": "retido",
        "hash": "sha256:" + hashlib.sha256(texto.encode("utf-8")).hexdigest(),
    }
