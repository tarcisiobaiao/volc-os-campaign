"""O que `para_registro()` emite tem que caber nas colunas da v11_03.

## O defeito, e por que ele so aparecia no dia da aplicacao

`Publicacao.para_registro()` e um dos dois caminhos que escrevem
`criativo_render_artefato.storage_sha256_remoto`. O outro e o recibo do
operario. O recibo normalizava (`sha256:<hex>` -> `<hex>`), e o comentario dele
citava textualmente o CHECK da v11_03. `para_registro()` nao normalizava, e
escrevia na MESMA coluna.

Contraprova executada em PostgreSQL 17 com `v11_03_execucao_criativa.sql`
aplicada, em cluster descartavel:

    A) storage_sha256_remoto = 'sha256:20981c58…'   (o que o metodo emitia)
       ERROR: new row for relation "criativo_render_artefato" violates check
              constraint "criativo_render_artefato_hash_remoto_forma"
    B) storage_sha256_remoto = '20981c58…'          (o mesmo valor, puro)
       1 linha gravada

E o mesmo formato do defeito da chave canonica de UM underscore que a rodada
anterior fechou: duas metades da maquina descrevendo o mesmo valor de dois
jeitos, sem consequencia nenhuma enquanto ninguem liga as duas — e recusa total
no dia em que alguem liga.

## Por que este teste le o SQL em vez de repetir a regex

Uma copia da regex aqui envelheceria junto com a do documento que ja envelheceu
(`PACOTE-v11_03.md`). O CHECK e lido do arquivo da migration, entao mudar o CHECK
sem mudar o emissor deixa este teste vermelho — que e exatamente o momento em
que alguem precisa olhar.

⚠️ Ele NAO substitui o ciclo em Postgres (`scripts/provar-ciclo-v11_03.sh`), que
exerce o banco de verdade. Ele fecha a fronteira Python->coluna sem exigir
Postgres, para que a recusa apareca na suite comum e nao so em quem roda o ciclo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.criativo.armazenamento import sha256_de
from app.criativo.bancada.armazenamento_verificado import (
    EstadoDoArmazenamento,
    Publicacao,
    hash_puro,
)

RAIZ = Path(__file__).resolve().parents[2]
MIGRATION = RAIZ / "supabase/migrations/v11_03_execucao_criativa.sql"

BYTES = b"peca-canario-bytes"


def _sem_comentarios(sql: str) -> str:
    """Tira `--` ate o fim da linha e blocos de comentario.

    ⚠️ ACHADO ADVERSARIAL (Codex, 02/09/2026). Sem isto, um CHECK COMENTADO —
    isto e, uma protecao que o banco NAO aplica mais — continuava a ser lido, e
    esta suite seguia verde afirmando uma garantia que nao existe. Um leitor que
    aceita codigo morto como contrato mede o documento, nao o banco.
    """
    sem_bloco = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return "\n".join(re.sub(r"--.*$", "", linha) for linha in sem_bloco.splitlines())


def _check_da_migration(nome_do_check: str) -> str:
    """A regex do CHECK, lida do SQL VIVO — nunca copiada, nunca comentada."""
    sql = _sem_comentarios(MIGRATION.read_text("utf-8"))
    achado = re.search(
        rf"constraint\s+{nome_do_check}\s+check\s*\((.*?)\)\s*,?\s*\n",
        sql, re.IGNORECASE | re.DOTALL,
    )
    if achado is None:
        achado = re.search(rf"{nome_do_check}(.{{0,400}}?)'(\^[^']+)'", sql,
                           re.IGNORECASE | re.DOTALL)
        assert achado, f"nao achei o CHECK {nome_do_check} em {MIGRATION.name}"
        return achado.group(2)
    corpo = achado.group(1)
    regex = re.search(r"'(\^[^']+)'", corpo)
    assert regex, f"o CHECK {nome_do_check} mudou de forma: {corpo[:200]}"
    return regex.group(1)


def _publicacao(estado: EstadoDoArmazenamento) -> Publicacao:
    return Publicacao(
        estado=estado,
        chave="criativos/positivo/job1/2-imagem__20981c58f942b3ed0f5e41933d641b2",
        mime="image/png",
        bytes_local=len(BYTES),
        sha256_local=sha256_de(BYTES),
        bytes_remoto=len(BYTES),
        sha256_remoto=sha256_de(BYTES),
        conferido_em="2026-09-02T12:00:00+00:00",
        motivo=None,
    )


def test_a_maquina_de_armazenamento_fala_com_prefixo() -> None:
    """A premissa do defeito. Sem ela o resto deste arquivo nao faz sentido."""
    assert sha256_de(BYTES).startswith("sha256:"), (
        "se `sha256_de` deixou de prefixar, a normalizacao virou no-op e este "
        "arquivo inteiro precisa ser relido antes de continuar valendo"
    )


def test_o_hash_remoto_emitido_cabe_no_check_da_v11_03() -> None:
    """O caso A da contraprova: era isto que o banco recusava."""
    padrao = _check_da_migration("criativo_render_artefato_hash_remoto_forma")
    emitido = _publicacao(EstadoDoArmazenamento.VERIFIED_OK).para_registro()[
        "storage_sha256_remoto"
    ]
    assert re.fullmatch(padrao, emitido), (
        f"`para_registro()` emite {emitido!r}, e o CHECK "
        f"`criativo_render_artefato_hash_remoto_forma` exige {padrao!r}. "
        f"No dia da aplicacao da v11_03, toda gravacao de artefato com hash "
        f"remoto conferido seria recusada."
    )


def test_o_veredito_nao_muda_por_causa_da_normalizacao() -> None:
    """Normalizar so um dos lados da comparacao inverteria o veredito.

    `storage_hash_conferido` responde "bateu?" comparando as formas INTERNAS,
    que carregam as duas o mesmo prefixo. O que sai normalizado e o valor
    gravado, nao a comparacao.
    """
    r = _publicacao(EstadoDoArmazenamento.VERIFIED_OK).para_registro()
    assert r["storage_hash_conferido"] is True
    assert r["storage_sha256_remoto"] == hash_puro(sha256_de(BYTES))


def test_o_mismatch_continua_dizendo_que_nao_bateu() -> None:
    """Um mismatch grava o hash do que VOLTOU, puro, e o veredito `False`.

    E o caso em que a coluna mais importa: o booleano diz que nao bateu, e a
    coluna de texto diz o que chegou. As duas precisam caber no banco.
    """
    outro = sha256_de(b"outra-coisa")
    p = Publicacao(
        estado=EstadoDoArmazenamento.VERIFIED_MISMATCH,
        chave="criativos/positivo/job1/2-imagem__20981c58f942b3ed0f5e41933d641b2",
        mime="image/png", bytes_local=len(BYTES), sha256_local=sha256_de(BYTES),
        bytes_remoto=9, sha256_remoto=outro,
        conferido_em="2026-09-02T12:00:00+00:00", motivo="divergencia",
    )
    r = p.para_registro()
    padrao = _check_da_migration("criativo_render_artefato_hash_remoto_forma")
    assert r["storage_hash_conferido"] is False
    assert re.fullmatch(padrao, r["storage_sha256_remoto"])


@pytest.mark.parametrize(
    "estado", [EstadoDoArmazenamento.LOCAL, EstadoDoArmazenamento.UPLOADED_UNVERIFIED]
)
def test_quem_nao_conferiu_nao_grava_hash_nenhum(estado) -> None:
    """`NULL` e a forma de "nao conferi" que o CHECK aceita; nao um hash vazio."""
    r = _publicacao(estado).para_registro()
    assert r["storage_sha256_remoto"] is None
    assert r["storage_hash_conferido"] is None
    assert r["storage_conferido_em"] is None


def test_normalizar_duas_vezes_nao_estraga() -> None:
    assert hash_puro(hash_puro(sha256_de(BYTES))) == hash_puro(sha256_de(BYTES))
    assert hash_puro(None) is None


def test_o_recibo_e_o_registro_emitem_a_MESMA_forma() -> None:
    """A raiz do defeito era exatamente esta: dois caminhos, uma coluna.

    Se um dia alguem reintroduzir uma normalizacao local em `operario.py`, este
    teste continua verde — ele compara as SAIDAS. O que ele impede e a divergencia,
    que e o que causou dano.
    """
    from app.criativo.bancada import operario as O

    assert not hasattr(O, "_hash_puro"), (
        "voltou a existir uma copia local do normalizador em operario.py; "
        "duas copias ja divergiram uma vez"
    )
    do_registro = _publicacao(EstadoDoArmazenamento.VERIFIED_OK).para_registro()
    assert do_registro["storage_sha256_remoto"] == hash_puro(sha256_de(BYTES))


def test_o_leitor_aceita_o_par_misto_que_ele_recusava() -> None:
    """Uma metade do banco, a outra da memoria — e a linha esta CERTA.

    `estado_de` comparava as duas formas cruas. Depois de `para_registro()`
    passar a normalizar, a coluna sai `<hex>` e o `sha256_do_artefato` de quem
    ainda carrega a forma interna vem `sha256:<hex>`: o par diverge, o veredito
    diz `True`, e a funcao LEVANTAVA "veredito contradiz o hash remoto".

    Recusar a linha certa e pior que aceitar a errada: a forense de um mismatch
    de verdade comeca por conseguir ler a linha.
    """
    from app.criativo.bancada.armazenamento_verificado import estado_de

    puro = hash_puro(sha256_de(BYTES))
    com_prefixo = sha256_de(BYTES)

    for remoto, artefato in ((puro, com_prefixo), (com_prefixo, puro),
                             (puro, puro), (com_prefixo, com_prefixo)):
        assert estado_de(
            storage_chave="criativos/t/j/2-imagem__abc",
            storage_conferido_em="2026-09-02T12:00:00+00:00",
            storage_hash_conferido=True,
            storage_sha256_remoto=remoto,
            sha256_do_artefato=artefato,
        ) is EstadoDoArmazenamento.VERIFIED_OK, (remoto[:12], artefato[:12])


def test_o_leitor_continua_acusando_contradicao_de_verdade() -> None:
    """Normalizar nao pode ter apagado a guarda: hashes DIFERENTES ainda brigam."""
    import pytest as _pytest

    from app.criativo.bancada.armazenamento_verificado import estado_de

    with _pytest.raises(ValueError, match="contradiz"):
        estado_de(
            storage_chave="criativos/t/j/2-imagem__abc",
            storage_conferido_em="2026-09-02T12:00:00+00:00",
            storage_hash_conferido=True,
            storage_sha256_remoto=hash_puro(sha256_de(b"uma coisa")),
            sha256_do_artefato=hash_puro(sha256_de(b"outra coisa")),
        )


def test_um_check_comentado_nao_conta_como_protecao() -> None:
    """Codigo morto no SQL nao pode sustentar um teste verde."""
    vivo = "constraint c check (x ~ '^[0-9a-f]{64}$')"
    assert "c check" in _sem_comentarios(vivo)
    assert "c check" not in _sem_comentarios("-- " + vivo)
    assert "c check" not in _sem_comentarios("/* " + vivo + " */")


def test_o_check_que_este_arquivo_afirma_existe_de_verdade_no_sql() -> None:
    """Se o CHECK sumir da migration, esta suite fica vermelha em vez de vacua."""
    padrao = _check_da_migration("criativo_render_artefato_hash_remoto_forma")
    assert padrao == "^[0-9a-f]{64}$", (
        f"o CHECK mudou de forma: {padrao!r}. Releia este arquivo antes de "
        f"ajustar o valor esperado."
    )
