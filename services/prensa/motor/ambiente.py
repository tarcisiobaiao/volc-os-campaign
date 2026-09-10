#!/usr/bin/env python3
"""AMBIENTE — a porta ÚNICA de credencial do PRENSA.

Antes desta peça, três runners do POC (`gen_bg.py`, `gen_kintsugi.py`,
`gen_planejado.py`) abriam **o `.env` de outro motor por caminho fixo**
(`AQUI.parent.parent.parent / "motor-video" / ".env"`) e liam a chave com um
`startswith("OPENAI_API_KEY=")`. Três consequências medidas na auditoria
(`../AUDITORIA-SEGREDOS.md`):

1. O PRENSA não se movia de pasta sem quebrar — subir um nível na árvore, ou
   empacotar o POC sozinho para o Volc OS, matava os três scripts.
2. Segredo de um motor circulava dentro de outro, sem que nenhum dos dois
   declarasse a dependência.
3. Falha silenciosa por precedência: uma chave exportada no shell era IGNORADA,
   porque o arquivo sempre ganhava. Trocar de conta exigia editar arquivo.

Agora vale a mesma doutrina do `motor-video/motor/ambiente.py`: **uma porta, e
só ela**. Nenhum outro arquivo do PRENSA pode ler `.env`, `os.environ` de chave
ou montar `Authorization` por conta própria.

    from ambiente import chave
    OPENAI = chave("OPENAI_API_KEY")     # str, ou RuntimeError acionável

## Precedência (a primeira que responder ganha)

1. variável já exportada no shell — **vence sempre**, e não lê arquivo nenhum
2. `VOLC_ENV_FILE` — caminho explícito para um `.env`; se apontar para arquivo
   inexistente, é ERRO (o operador pediu aquele arquivo, silêncio seria mentira)
3. `<prensa-poc>/.env` — a casa do próprio POC
4. `<RAIZ_VOLC>/.env` — raiz do workspace, resolvida por `VOLC_RAIZ` ou por
   traversal relativo (nunca caminho absoluto cravado)
5. `<RAIZ_VOLC>/motor-video/.env` — **PONTE LEGADA**, só enquanto a chave morar
   lá. Avisa em stderr toda vez que for usada. Apagar `PONTE_LEGADA` fecha.

## O que este módulo nunca faz

- **Nunca imprime valor de chave.** Diagnóstico e log só falam nomes e origem.
- **Nunca usa regex de formato** (`sk-[A-Za-z0-9_-]{20,}` e afins). O parse é
  `NOME=VALOR` estrito. Regex de formato acha a chave errada em silêncio, e o
  erro só aparece na fatura ou num 401 no meio do render.
- **Nunca devolve `None` para chave obrigatória.** Falta = exceção com receita.
"""

from __future__ import annotations

import os
import pathlib
import ssl
import sys

# ------------------------------------------------------------------ raízes

AQUI = pathlib.Path(__file__).resolve().parent

# Raiz do workspace Volc (a pasta que contém `motor-imagem` e `motor-video`).
# Descoberta por traversal relativo — prensa-poc/ → compartilhado/ →
# motor-imagem/ → <workspace>. `VOLC_RAIZ` sobrepõe quando o POC for empacotado
# sozinho. É UMA variável para virar depois, em vez de N caminhos cravados.
RAIZ_VOLC = pathlib.Path(os.environ.get("VOLC_RAIZ") or AQUI.parent.parent.parent)

# Ponte de compatibilidade: hoje a única cópia preenchida das chaves está no
# `.env` do motor-video. Continua sendo lida — mas por caminho DERIVADO da raiz,
# nunca absoluto, e com aviso alto. Quando as chaves subirem para
# `<RAIZ_VOLC>/.env`, apague esta linha e a ponte deixa de existir.
PONTE_LEGADA = RAIZ_VOLC / "motor-video" / ".env"

# ------------------------------------------------------------------ chaves

# Quem usa o quê no PRENSA:
#   OPENAI_API_KEY  gpt-image-2 — fundos (gen_bg / gen_kintsugi / gen_planejado)
#   GEMINI_API_KEY  juiz VLM (audita_video) e provider de fallback
#   PEXELS_API_KEY  provider_chain de foto do spec (opcional)
CHAVES = ("OPENAI_API_KEY", "GEMINI_API_KEY", "PEXELS_API_KEY")

# Nome da chave → arquivo de onde ela veio. Só para diagnóstico; sem valores.
_origem: dict[str, str] = {}
_carregado = False


def _candidatos() -> list[tuple[pathlib.Path, bool, str]]:
    """Ordem de busca. `(caminho, exigido, rótulo)`.

    `exigido=True` significa: se o operador apontou explicitamente e o arquivo
    não existe, isso é erro — não se cai calado para o próximo.
    """
    lista: list[tuple[pathlib.Path, bool, str]] = []
    explicito = os.environ.get("VOLC_ENV_FILE")
    if explicito:
        lista.append((pathlib.Path(explicito).expanduser(), True, "VOLC_ENV_FILE"))
    lista.append((AQUI / ".env", False, "prensa-poc/.env"))
    lista.append((RAIZ_VOLC / ".env", False, "<RAIZ_VOLC>/.env"))
    lista.append((PONTE_LEGADA, False, "PONTE LEGADA motor-video/.env"))
    return lista


def _le_env(caminho: pathlib.Path) -> dict[str, str]:
    """Parse estrito `NOME=VALOR`. Sem regex de formato de chave.

    Ignora linha vazia, comentário e linha sem `=`. Aceita o `export ` que
    aparece em `.env` copiado de shell.
    """
    pares: dict[str, str] = {}
    for linha in caminho.read_text(encoding="utf-8", errors="ignore").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        if linha.startswith("export "):
            linha = linha[7:].lstrip()
        nome, valor = linha.split("=", 1)
        nome = nome.strip()
        if not nome or not nome.replace("_", "").isalnum():
            continue
        pares[nome] = valor.strip().strip('"').strip("'")
    return pares


def _confere_permissao(caminho: pathlib.Path, rotulo: str) -> None:
    """Arquivo de segredo legível por grupo/outros é achado de auditoria.

    Não bloqueia — avisa. Bloquear travaria máquina com umask frouxo no meio de
    um render, e o objetivo aqui é o operador consertar, não perder a peça.
    """
    try:
        modo = caminho.stat().st_mode & 0o077
    except OSError:
        return
    if modo:
        print(f"⚠️  {rotulo}: {caminho} está legível por grupo/outros "
              f"(modo {oct(caminho.stat().st_mode & 0o777)}). Corrija: "
              f"chmod 600 '{caminho}'", file=sys.stderr)


def carregar(*, forcar: bool = False) -> dict[str, str]:
    """Popula `os.environ` sem sobrescrever o que o shell já exportou.

    Idempotente. Devolve `{NOME: origem}` — apenas nomes e procedência, NUNCA
    valores, para que este retorno possa ir para log sem vazar segredo.
    """
    global _carregado
    if _carregado and not forcar:
        return dict(_origem)

    # O que já veio do shell tem precedência absoluta e origem própria.
    for k in CHAVES:
        if os.environ.get(k):
            _origem.setdefault(k, "shell (os.environ)")

    for caminho, exigido, rotulo in _candidatos():
        if not caminho.exists():
            if exigido:
                raise RuntimeError(
                    f"VOLC_ENV_FILE aponta para um arquivo que não existe:\n"
                    f"  {caminho}\n"
                    f"  Corrija a variável ou remova-a para usar a busca padrão."
                )
            continue
        _confere_permissao(caminho, rotulo)
        avisou_ponte = False
        for nome, valor in _le_env(caminho).items():
            if not valor or os.environ.get(nome):
                continue  # shell venceu, ou valor vazio: não regride
            os.environ[nome] = valor
            _origem[nome] = rotulo
            if caminho == PONTE_LEGADA and nome in CHAVES and not avisou_ponte:
                avisou_ponte = True
                print(
                    f"⚠️  ponte legada: credencial lida de {caminho}.\n"
                    f"   O PRENSA não deve depender do .env de outro motor. "
                    f"Mova as chaves para {RAIZ_VOLC / '.env'} ou exporte no "
                    f"shell, e apague PONTE_LEGADA de ambiente.py.",
                    file=sys.stderr,
                )

    _carregado = True
    return dict(_origem)


def chave(nome: str, *, obrigatoria: bool = True) -> str | None:
    """Devolve a credencial. Falha ALTO, cedo e com instrução de conserto.

    `obrigatoria=False` só para quem sabe seguir sem a chave (provider opcional).
    """
    if not _carregado:
        carregar()
    valor = os.environ.get(nome)
    if valor:
        return valor
    if not obrigatoria:
        return None

    tentados = "\n".join(
        f"    {'✓' if c.exists() else '·'} {c}" + (f"   [{r}]" if r else "")
        for c, _, r in _candidatos()
    )
    raise RuntimeError(
        f"{nome} não está definida — o PRENSA não vai chamar a API sem ela.\n"
        f"  Conserte de UM destes jeitos:\n"
        f"    1) export {nome}='...'        (vence tudo, não toca em arquivo)\n"
        f"    2) escreva {nome}=... em {AQUI / '.env'}\n"
        f"    3) export VOLC_ENV_FILE=/caminho/para/.env\n"
        f"  Arquivos procurados (✓ = existe):\n{tentados}\n"
        f"  Chaves que o PRENSA conhece: {', '.join(CHAVES)}"
    )


def contexto_ssl() -> ssl.SSLContext:
    """Mesma política do motor-video: certifi quando houver, default se não."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def diagnostico() -> str:
    """Uma linha por item. Só nomes de chave e procedência — jamais valores."""
    carregar()
    linhas = [
        f"AQUI       {AQUI}",
        f"RAIZ_VOLC  {RAIZ_VOLC}{'' if RAIZ_VOLC.exists() else '   ← NÃO EXISTE'}",
        "",
        "arquivos .env procurados (na ordem):",
    ]
    for caminho, exigido, rotulo in _candidatos():
        marca = "✓" if caminho.exists() else "·"
        linhas.append(f"  {marca} {rotulo:32} {caminho}")
    linhas.append("")
    for k in CHAVES:
        estado = "ok" if os.environ.get(k) else "FALTANDO"
        linhas.append(f"  {k:16} {estado:9} {_origem.get(k, '—')}")
    return "\n".join(linhas)


if __name__ == "__main__":
    print(diagnostico())
