"""Transforma o texto que o operador digitou no que o recibo pode guardar.

## Por que isto NAO mora em `contrato.py`

Porque o contrato tem uma regra escrita e um teste que a cobra: ele so pode
importar a linguagem — `dataclasses`, `enum`, `hashlib`, `json`, `typing` — e
nada mais. Sanitizar exige casamento de padrao, e `re` nao passa nessa porta.

A regra e boa e nao vai ser afrouxada para caber uma funcao. `InsumoSanitizado`
continua no contrato porque e DADO — a forma do que o recibo carrega. A politica
de o que sai e o que fica e outra coisa, e mora aqui.

## Por que isto NAO mora em `fronteira_publica.py`

Porque aquele arquivo decide o que sai pela API, e a resposta dele e "o texto
nao sai, nem truncado". Este arquivo decide o que o recibo INTERNO guarda, e a
resposta e outra: guarda, legivel, sem os identificadores. Juntar os dois faria a
proxima pessoa achar que o texto sanitizado tambem e publico.

⚠️ Sanitizar NAO e anonimizar, e a promessa aqui e ESTREITA de proposito. Um
briefing sem e-mail, sem telefone e sem valor ainda identifica um cliente pelo
assunto — e nada neste modulo tenta resolver isso.

O que ele promete, e so isto: as classes de identificador LISTADAS em
`_REGRAS_DE_SANITIZACAO` saem, `substituicoes` diz quais casaram e quantas
vezes, o texto continua legivel por um auditor, e o hash do original continua
respondendo pela identidade.

⚠️ A lista e uma ALLOWLIST INVERTIDA, e por isso e incompleta por construcao: ela
remove o que reconhece, e reconhece o que alguem escreveu. Uma revisao
adversarial apontou `@perfil`, `www.` sem esquema, placa e passaporte passando
inteiros — as quatro entraram, e a proxima classe que ninguem pensou tambem vai
passar. Quem depender deste modulo para uma garantia mais forte que "os padroes
listados saem" vai se decepcionar, e a decepcao seria com a leitura, nao com o
codigo: e por isso que a fronteira publica NAO devolve este texto.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .contrato import InsumoSanitizado

#: Ordem importa: o telefone tem de sair antes do numero generico, senao o
#: generico o parte em pedacos e o resultado ainda parece um telefone.
_REGRAS_DE_SANITIZACAO: tuple[tuple[str, str], ...] = (
    (r"[\w.+-]+@[\w-]+\.[\w.-]+", "<email>"),
    (r"https?://\S+", "<url>"),
    # ⚠️ ACRESCENTADA. `https?://` deixava passar `www.exemplo.com` e
    # `exemplo.com.br/promo` — o mesmo endereco, sem o esquema.
    (r"\b(?:www\.)[\w-]+(?:\.[\w-]+)+(?:/\S*)?", "<url>"),
    # ⚠️ ACRESCENTADA. `@joao` e identificador de rede social, e sobrevivia
    # inteiro porque a regra de e-mail exige um dominio depois do `@`.
    (r"(?<![\w.])@[A-Za-z][\w.]{2,}", "<perfil>"),
    (r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", "<documento>"),
    # ⚠️ ACRESCENTADA. Documento com letras — passaporte, RG com digito, placa
    # Mercosul — nao casava nenhuma regra numerica.
    (r"\b[A-Z]{2,3}\d{4,8}\b", "<documento>"),
    (r"\b[A-Z]{3}\d[A-Z]\d{2}\b", "<placa>"),
    (r"\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}", "<telefone>"),
    (r"R\$\s?[\d.,]+", "<valor>"),
    (r"\b\d{3,}\b", "<numero>"),
)

#: Muda quando as regras mudam. Sem isto, dois recibos com sanitizacoes
#: diferentes pareceriam a mesma sanitizacao.
VERSAO_DO_SANITIZADOR = "1"

#: Teto do texto sanitizado. Existe porque um briefing inteiro, mesmo sem
#: numero e sem e-mail, ainda e o briefing — e o recibo interno guarda para
#: auditar, nao para republicar.
_TETO_DO_INSUMO = 600



def sanitizar_insumo(bruto: Any) -> InsumoSanitizado:
    """Transforma o briefing cru no que o recibo interno pode guardar."""
    if bruto is None:
        return InsumoSanitizado("ausente", None, None, {}, VERSAO_DO_SANITIZADOR, False)
    texto = str(bruto)
    if not texto.strip():
        return InsumoSanitizado("vazio", None, None, {}, VERSAO_DO_SANITIZADOR, False)

    completo = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    contagem: dict[str, int] = {}
    limpo = texto
    for padrao, marca in _REGRAS_DE_SANITIZACAO:
        limpo, n = re.subn(padrao, marca, limpo)
        if n:
            contagem[marca] = contagem.get(marca, 0) + n
    truncado = len(limpo) > _TETO_DO_INSUMO
    if truncado:
        limpo = limpo[:_TETO_DO_INSUMO]
    return InsumoSanitizado(
        estado="sanitizado",
        texto=limpo,
        hash_do_completo=completo,
        substituicoes=contagem,
        versao_do_sanitizador=VERSAO_DO_SANITIZADOR,
        truncado=truncado,
    )
