"""O cofre — cifra simétrica para credenciais de terceiros.

## Por que existe

O sistema precisa guardar o Application Password do WordPress de cada projeto
para o redator conseguir publicar. Isso é credencial de admin de um site em
produção: quem a tiver escreve, edita e apaga qualquer página.

A RLS da tabela já barra o browser (`project_wordpress` nega tudo para `anon` —
conferido: HTTP 401). Esta camada resolve um risco DIFERENTE, que a RLS não
cobre: o banco vazar inteiro. Backup mal guardado, réplica exposta, acesso ao
container do Postgres, `pg_dump` num laptop. Nesses casos a RLS não vale nada —
ela é regra de conexão, não de conteúdo.

Com a cifra, um dump do Postgres devolve isto:

    gAAAAABm...ZFQ==      (ilegível sem a chave)

## Onde a chave mora, e por que não no banco

`VOLC_SEGREDO_KEY`, no `backend/.env` — nunca no Postgres. É o ponto inteiro do
desenho: se a chave estivesse no banco, o dump traria a fechadura junto com o
cofre e a cifra viraria teatro.

Isso também é o motivo de NÃO usar `pgcrypto` aqui. Cifrar com
`pgp_sym_encrypt(token, chave)` faz a chave viajar dentro do texto do comando
SQL — e comando SQL vai para o log do Postgres, para o `pg_stat_statements` e
para qualquer proxy no caminho. A chave acabaria gravada em texto puro em três
lugares novos.

## Fail-closed

Sem `VOLC_SEGREDO_KEY` configurada, `cifrar()` e `decifrar()` levantam
`CofreSemChave`. Não há modo degradado que grave em texto puro: um fallback
silencioso é exatamente como uma credencial acaba legível sem ninguém perceber.
A rota que cadastra a credencial traduz essa exceção em 503 com instrução.

Gerar a chave (uma vez, e guardar no `backend/.env`):

    python -c "from app.seguranca import gerar_chave; print(gerar_chave())"

⚠️ Trocar a chave torna ilegível tudo que já foi cifrado com a anterior. Não há
recuperação — é o comportamento correto de um cofre, e significa que a troca
exige recadastrar as credenciais.
"""
from __future__ import annotations

import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

VARIAVEL_DA_CHAVE = "VOLC_SEGREDO_KEY"


class CofreSemChave(RuntimeError):
    """`VOLC_SEGREDO_KEY` ausente ou malformada — não há como cifrar."""


class SegredoCorrompido(ValueError):
    """O texto cifrado não abre com a chave atual.

    Quase sempre significa uma destas duas coisas: a chave foi trocada depois
    de o segredo ter sido gravado, ou a coluna foi editada à mão. Nos dois casos
    a saída é recadastrar a credencial — não existe conserto automático.
    """


def gerar_chave() -> str:
    """Uma chave Fernet nova (32 bytes urlsafe-base64). Uso manual, uma vez."""
    return Fernet.generate_key().decode("ascii")


def _chave_bruta() -> str:
    """A chave, das duas fontes possíveis — nessa ordem.

    O `backend/.env` é lido pelo pydantic-settings para dentro de `Settings`, e
    NÃO para `os.environ`. Ler só do ambiente faria o cofre nascer "não
    configurado" com a chave já gravada no arquivo — que foi exatamente o que
    aconteceu no primeiro teste. O ambiente continua valendo e vem primeiro,
    para um deploy poder injetar a chave sem tocar em arquivo.
    """
    do_ambiente = (os.getenv(VARIAVEL_DA_CHAVE) or "").strip()
    if do_ambiente:
        return do_ambiente
    try:
        from app.config import get_settings
        return (get_settings().volc_segredo_key or "").strip()
    except Exception:  # noqa: BLE001 — sem config utilizável, é o mesmo que sem chave
        return ""


def _cofre() -> Fernet:
    bruta = _chave_bruta()
    if not bruta:
        raise CofreSemChave(
            f"{VARIAVEL_DA_CHAVE} não está definida no backend/.env. "
            f"Gere uma com: python -c \"from app.seguranca import gerar_chave; "
            f"print(gerar_chave())\""
        )
    try:
        return Fernet(bruta.encode("ascii"))
    except Exception as exc:  # noqa: BLE001 — chave malformada é erro de setup
        raise CofreSemChave(
            f"{VARIAVEL_DA_CHAVE} existe mas não é uma chave Fernet válida "
            f"(esperado 32 bytes em urlsafe-base64): {exc}"
        ) from exc


def cofre_configurado() -> bool:
    """Há chave utilizável? Para a rota responder 'configure antes' sem estourar."""
    try:
        _cofre()
        return True
    except CofreSemChave:
        return False


def cifrar(texto: str) -> str:
    """Texto puro -> token Fernet. Levanta `CofreSemChave` se não houver chave."""
    if not texto:
        raise ValueError("nada a cifrar: o segredo veio vazio")
    return _cofre().encrypt(texto.encode("utf-8")).decode("ascii")


def decifrar(token: Optional[str]) -> Optional[str]:
    """Token Fernet -> texto puro. `None` entra e `None` sai.

    `None` significa credencial ainda não cadastrada, que é estado legítimo —
    projeto recém-criado. Diferente de token ilegível, que é `SegredoCorrompido`.
    """
    if token is None or token == "":
        return None
    try:
        return _cofre().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SegredoCorrompido(
            "o segredo não abre com a chave atual — a chave foi trocada ou a "
            "coluna foi editada à mão. Recadastre a credencial."
        ) from exc


def mascara(texto: Optional[str], visiveis: int = 4) -> str:
    """Como a credencial aparece em log e em tela. NUNCA devolve o valor.

    Application Password do WordPress vem no formato `abcd EFGH ijkl MNOP qrst
    UVWX`. Mostrar os últimos caracteres deixa o operador reconhecer QUAL
    credencial está lá sem que a tela chegue a exibi-la.
    """
    if not texto:
        return "—"
    limpo = texto.replace(" ", "")
    if len(limpo) <= visiveis:
        return "•" * len(limpo)
    return "•" * (len(limpo) - visiveis) + limpo[-visiveis:]
