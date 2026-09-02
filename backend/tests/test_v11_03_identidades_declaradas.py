"""As identidades que o pacote de aplicacao declara precisam ser as dos arquivos.

## O defeito que este arquivo fecha, e por que ele merece um teste

`PACOTE-v11_03.md` abre com uma instrucao ao operador: confira os `sha256` antes
de qualquer outra coisa, e **se um divergir, pare**. Essa e a unica guarda entre
"apliquei a migration provada" e "apliquei um arquivo que ninguem provou".

Medido em 02/09/2026, na integracao do last-mile: a tabela do passo 0 declarava
`33b55c52…` para `v11_03_execucao_criativa.sql`, e o arquivo sempre teve
`3aa77687…` — em `e273103`, em `fb0e227`, em `5235f0c`. O hash nunca esteve
certo, nem no commit que escreveu a tabela. O mesmo para `provas-v11_03.sql`
(`7a48fbea…` declarado, `5cae318a…` real).

O custo disso nao e o susto. E o segundo passo do operador: quem encontra uma
divergencia num documento que manda parar, e descobre que a divergencia e do
documento, aprende a ignorar o passo 0 — e ai a guarda deixa de existir para o
dia em que a divergencia for de verdade.

A contagem do ciclo ja tinha caido no mesmo buraco duas vezes: o README avisava
que "129 ja esteve errado aqui, ficou parado enquanto o ciclo crescia", e estava
errado de novo em 166 enquanto o ciclo dava 178.

Um numero copiado a mao para dentro de um documento envelhece sozinho. Este
teste e o que faz o envelhecimento doer na hora certa: quem mudar a migration,
as provas ou o ciclo ve vermelho aqui, na mesma entrega.

⚠️ Este teste NAO confere se a migration esta correta. Ele confere se o
documento diz a verdade sobre qual arquivo ele esta descrevendo. Sao perguntas
diferentes, e o ciclo em Postgres descartavel responde a primeira.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PACOTE = (RAIZ / "docs/closure/creative-factory-production-last-mile-v1"
          / "braco-a/PACOTE-v11_03.md")
AUTORIZACAO = (RAIZ / "docs/closure/creative-factory-production-last-mile-v1"
               / "AUTORIZACAO-EXTERNA.md")

# `| `caminho` | 905 | `sha` |` — o numero do meio e opcional porque a tabela da
# AUTORIZACAO nao tem coluna de linhas.
LINHA_COM_SHA = re.compile(
    r"^\|\s*`([^`]+\.(?:sql|sh))`\s*\|(?:\s*(\d+)\s*\|)?\s*`([0-9a-f]{64})`\s*\|",
    re.MULTILINE,
)


def _sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _declaracoes(documento: Path) -> list[tuple[str, str | None, str]]:
    return [(m.group(1), m.group(2), m.group(3))
            for m in LINHA_COM_SHA.finditer(documento.read_text("utf-8"))]


@pytest.mark.parametrize("documento", [PACOTE, AUTORIZACAO],
                         ids=lambda p: p.name)
def test_o_documento_declara_o_sha_do_arquivo_que_existe(documento: Path) -> None:
    """Cada `sha256` da tabela e o do arquivo, e cada arquivo citado existe."""
    declaracoes = _declaracoes(documento)
    assert declaracoes, (
        f"{documento.name} nao tem nenhuma linha `| caminho | sha |`. Ou a tabela "
        f"sumiu, ou o formato mudou — nos dois casos a guarda parou de guardar."
    )

    divergentes = []
    for caminho_declarado, _linhas, sha_declarado in declaracoes:
        arquivo = RAIZ / caminho_declarado
        if not arquivo.is_file():
            divergentes.append(f"{caminho_declarado}: declarado e NAO EXISTE")
            continue
        real = _sha256(arquivo)
        if real != sha_declarado:
            divergentes.append(
                f"{caminho_declarado}: documento diz {sha_declarado[:16]}…, "
                f"arquivo tem {real[:16]}…"
            )

    assert not divergentes, (
        f"{documento.name} descreve arquivos que nao sao os do repositorio:\n  "
        + "\n  ".join(divergentes)
        + "\n\nO passo 0 manda o operador PARAR quando um sha diverge. Se o "
          "documento e que esta velho, o operador aprende a ignorar o passo 0."
    )


@pytest.mark.parametrize("documento", [PACOTE, AUTORIZACAO],
                         ids=lambda p: p.name)
def test_a_contagem_de_linhas_declarada_e_a_do_arquivo(documento: Path) -> None:
    """Onde a tabela declara linhas, elas batem — mesma classe de defeito."""
    erradas = []
    for caminho_declarado, linhas, _sha in _declaracoes(documento):
        if linhas is None:
            continue
        arquivo = RAIZ / caminho_declarado
        if not arquivo.is_file():
            continue
        real = len(arquivo.read_text("utf-8").splitlines())
        if real != int(linhas):
            erradas.append(f"{caminho_declarado}: diz {linhas}, tem {real}")
    assert not erradas, f"{documento.name}: contagem de linhas velha:\n  " + "\n  ".join(erradas)


def test_o_pacote_cita_todos_os_arquivos_que_o_ciclo_executa() -> None:
    """Um passo 0 que omite um arquivo da prova da garantia onde nao conferiu nada.

    Foi assim que `provas-papeis-v11_03.sql` — de onde saem as 34 provas de RLS
    sob papeis — ficou de fora da tabela (achado A4-i).
    """
    citados = {c for c, _l, _s in _declaracoes(PACOTE)}
    obrigatorios = {
        "supabase/migrations/v11_03_execucao_criativa.sql",
        "supabase/migrations/v11_03_rollback.sql",
        "scripts/preflight-v11_03.sh",
        "scripts/provar-ciclo-v11_03.sh",
        "scripts/provas-v11_03.sql",
        "scripts/provas-papeis-v11_03.sql",
        "scripts/v11_03-provar-preflight.sh",
        "scripts/v11_03-provar-plano.sh",
    }
    faltando = sorted(obrigatorios - citados)
    assert not faltando, (
        "o passo 0 do PACOTE nao manda conferir estes arquivos, e o ciclo os "
        f"executa: {faltando}"
    )


def test_a_contagem_do_ciclo_e_a_mesma_nos_tres_lugares_que_a_declaram() -> None:
    """`166` esteve em tres documentos enquanto o ciclo dava `178`.

    O numero e copiado a mao para o PACOTE (esperado do passo 1 e o texto do
    fecho) e para o README da serie. Tres copias divergem sozinhas; este teste
    exige que elas concordem entre si.

    ⚠️ Ele NAO roda o ciclo — isso e `scripts/provar-ciclo-v11_03.sh`, que
    precisa de Postgres. Ele exige coerencia entre as copias, que e onde a
    mentira nasceu das duas vezes.
    """
    readme = (RAIZ / "supabase/migrations/README.md").read_text("utf-8")
    pacote = PACOTE.read_text("utf-8")

    do_readme = re.search(r"`scripts/provar-ciclo-v11_03\.sh`.*?\*\*(\d+) provas",
                          readme)
    assert do_readme, "o README perdeu a linha de contagem do ciclo"

    do_pacote = set(re.findall(r"passaram (\d+) · falharam 0", pacote))
    no_fecho = set(re.findall(r"\*\*(\d+)\*\* no ciclo", pacote))

    numero = do_readme.group(1)
    assert numero in do_pacote, (
        f"README diz {numero} provas no ciclo; o passo 1 do PACOTE espera "
        f"{sorted(do_pacote)}"
    )
    assert no_fecho == {numero}, (
        f"README diz {numero}; o fecho do PACOTE diz {sorted(no_fecho)}"
    )
