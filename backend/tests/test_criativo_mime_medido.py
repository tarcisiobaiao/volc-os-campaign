"""O MIME que o motor DECLARA e o MIME que o arquivo E sao perguntas diferentes.

## O defeito, reproduzido antes do conserto

O MIME atravessava o sistema inteiro declarado pelo motor e nunca era medido —
com o medidor pronto ao lado: `medir_imagem.mime_de` le a assinatura do arquivo,
e `Medida.mime` ja vinha preenchido e era descartado.

Um motor que grava PNG e declara `image/jpeg` chegava a `rendered`:

    gate dimensao ................ PASS   {"medido": [1200,628], "declarado": [1200,628]}
    recibo.mime .................. image/jpeg
    chave de storage ............. ...jpg
    Content-Type do upload ....... image/jpeg
    storage ...................... VERIFIED_OK

Todos verdes, e nenhum errado no que afirma: a dimensao bate mesmo, e a
releitura confere BYTES — que estavam certos. O gate `dimensao` nao podia pegar
isto, porque `_dimensao_do_artefato` escolhe o medidor PELO MIME DECLARADO, e um
PNG declarado JPEG cai no leitor de imagem, que le PNG sem reclamar.

O dano nao e interno. Um endereco terminado em `.jpg`, servido com
`Content-Type: image/jpeg` sobre bytes PNG, e o que chega ao navegador do
cliente e ao upload para o destino.

## Por que um gate, e nao uma correcao silenciosa do campo

Reescrever `a.mime` com o valor medido faria o recibo dizer a verdade sobre o
arquivo e apagar a mentira do motor. Um motor que mente sobre a propria saida e
um motor que nao serve para decidir mais nada — e isso precisa aparecer, e nao
ser costurado. E o mesmo raciocinio do gate `dimensao_declarada_confere`, que ja
existia por essa razao.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from app.criativo.bancada.adaptadores.tipografico import MotorTipografico
from app.criativo.bancada.contrato import Artefato, Encomenda, SaidaPedida
from app.criativo.bancada.deposito import DepositoDeTrabalhos
from app.criativo.bancada.operario import Operario


class MotorQueMenteOMime(MotorTipografico):
    """Grava PNG de verdade e declara `image/jpeg`. Os bytes estao certos."""

    slug = "mente-o-mime"

    def produzir(self, encomenda: Encomenda, dir_trabalho: str):
        return tuple(
            Artefato(**{**{f.name: getattr(a, f.name) for f in fields(a)},
                        "mime": "image/jpeg"})
            for a in super().produzir(encomenda, dir_trabalho)
        )


def _encomenda(motor: str) -> Encomenda:
    return Encomenda(
        receita_id="receita-1", tenant_id="tenant-A", motor_slug=motor,
        modo_slug="typography_only", finalidade_slug="google_display", seed=7,
        saidas=(SaidaPedida("2-imagem_marketing", 1200, 628, "imagem", "image/png"),),
        parametros={"titulo": "Inscricoes abertas", "apoio": "ate 30 de setembro"},
    )


def _gates(recibo, nome):
    return [v for v in (recibo or {}).get("validacoes", []) if v["gate"] == nome]


@pytest.fixture
def bancada(tmp_path: Path):
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    operario = Operario(
        deposito,
        {"tipografico-local": MotorTipografico(), "mente-o-mime": MotorQueMenteOMime()},
        tmp_path / "trabalhos",
    )
    return deposito, operario


def test_o_motor_que_mente_o_mime_nao_chega_a_rendered(bancada) -> None:
    deposito, operario = bancada
    e = _encomenda("mente-o-mime")
    # o pedido pede PNG; o motor grava PNG e DECLARA jpeg
    trabalho, _ = deposito.enfileirar(e)
    final = operario.executar(deposito.reivindicar(operario.nome, lease_s=300))

    assert final.estado.value == "failed", (
        f"um motor que descreve errado o proprio arquivo chegou a "
        f"{final.estado.value}"
    )
    assert final.falha["codigo"] == "gate_reprovou"
    assert "mime_declarado_confere" in final.falha["mensagem"]

    reprovado = _gates({"validacoes": final.falha["validacoes"]},
                       "mime_declarado_confere")
    assert reprovado and reprovado[0]["resultado"] == "FAIL"
    assert reprovado[0]["bloqueante"] is True
    assert reprovado[0]["detalhe"]["declarado"] == "image/jpeg"
    assert reprovado[0]["detalhe"]["medido"] == "image/png"


def test_o_gate_de_dimensao_sozinho_NAO_pegava_isto(bancada) -> None:
    """A razao de o gate novo existir: o antigo aprova este caso, e com razao.

    `dimensao` mede o ARQUIVO e compara com o PEDIDO. O arquivo tem mesmo
    1200x628. O gate esta certo; ele so responde outra pergunta.
    """
    deposito, operario = bancada
    deposito.enfileirar(_encomenda("mente-o-mime"))
    final = operario.executar(deposito.reivindicar(operario.nome, lease_s=300))
    dim = _gates({"validacoes": final.falha["validacoes"]}, "dimensao")
    assert dim and dim[0]["resultado"] == "PASS", (
        "se a dimensao tambem reprovasse, este teste estaria provando outra coisa"
    )


def test_o_motor_honesto_continua_passando(bancada) -> None:
    """O gate nao pode ter fechado a porta para quem descreve certo."""
    deposito, operario = bancada
    deposito.enfileirar(_encomenda("tipografico-local"))
    final = operario.executar(deposito.reivindicar(operario.nome, lease_s=300))
    assert final.estado.value == "rendered", final.falha
    ok = _gates(final.recibo, "mime_declarado_confere")
    assert ok and ok[0]["resultado"] == "PASS"
    assert ok[0]["detalhe"]["declarado"] == ok[0]["detalhe"]["medido"] == "image/png"


def test_formato_cuja_assinatura_o_medidor_nao_le_sai_SKIPPED_nao_FAIL() -> None:
    """Ausencia de medicao nao e reprovacao — seria recusar a midia que produzimos.

    `mime_de` so conhece assinaturas de imagem. Um mp4 legitimo cai aqui, e
    reprova-lo tiraria o video da linha.
    """
    from app.criativo.bancada.operario import _mime_medido

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        # cabecalho de mp4: `ftyp` no offset 4
        f.write(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 32)
        caminho = Path(f.name)
    try:
        assert _mime_medido(caminho) is None, (
            "se o medidor passar a ler mp4, o ramo SKIPPED deste gate precisa "
            "ser revisto — ele existe porque a assinatura nao era legivel"
        )
    finally:
        caminho.unlink(missing_ok=True)


def test_arquivo_ilegivel_nao_derruba_a_medicao() -> None:
    from app.criativo.bancada.operario import _mime_medido

    assert _mime_medido(Path("/caminho/que/nao/existe.png")) is None


# ═══════════════════════════════════════════════════════════════════════════
# A sentinela do arranjo — risco FUTURO, e nao defeito de hoje
# ═══════════════════════════════════════════════════════════════════════════
#
# A revisao adversarial levantou a fragilidade do reconhecimento de MIME:
# `mime_de` conhece TRES assinaturas, e a de JPEG tem DOIS bytes. Foi medido, com
# cinco ataques executados contra o contrato atual, e nenhum passou:
#
#   bytes Mach-O declarados `image/webp`      -> mime_gate FAIL      bloqueado
#   lixo comecando com \xff\xd8 como JPEG     -> mime_gate PASS, dim FAIL
#   PNG 64x64 com pedido de 1200x628          -> mime_gate PASS, dim FAIL
#   PNG real declarado `image/gif`            -> mime_gate FAIL      bloqueado
#   bytes arbitrarios declarados `video/mp4`  -> mime_gate SKIP, dim FAIL
#
# Ou seja: NAO ha defeito executavel hoje. Os dois gates sao complementares —
# onde a assinatura rasa deixa passar, o leitor profundo (o mesmo que mede a
# dimensao) recusa; e onde a assinatura nao existe, o outro instrumento mede.
#
# O problema e que essa complementaridade e EMERGENTE: ela vale por causa da
# relacao entre tres conjuntos, e nenhum deles sabe dos outros. Basta alguem
# acrescentar `image/webp` a `_MIMES_MENSURAVEIS` — um gesto razoavel, para o
# gate de dimensao passar a cobrar webp — sem ensinar a assinatura ao `mime_de`,
# e o par volta a somar dois SKIPPED, que foi exatamente o bloqueante que a
# revisao pegou.
#
# Estas provas nao mudam comportamento nenhum. Elas transformam o risco futuro
# em vermelho no dia em que ele nascer, em vez de em bloqueante na revisao
# seguinte.


def test_todo_mime_que_pula_o_gate_e_medido_por_outro_instrumento() -> None:
    """INVARIANTE 1. `SKIPPED` so e seguro se o gate `dimensao` for BLOQUEANTE ali.

    Um MIME dispensado do gate de assinatura e que o gate de dimensao tambem nao
    cobre nao e conferido por ninguem — e dois `SKIPPED` nao-bloqueantes somam um
    caminho verde sem leitura, que foi o bloqueante da revisao.
    """
    from app.criativo.bancada.operario import (
        _MIMES_MENSURAVEIS,
        _MIMES_VERIFICADOS_POR_OUTRO_INSTRUMENTO,
    )

    orfaos = _MIMES_VERIFICADOS_POR_OUTRO_INSTRUMENTO - _MIMES_MENSURAVEIS
    assert not orfaos, (
        f"{sorted(orfaos)} pulam o gate de assinatura e NAO estao em "
        f"`_MIMES_MENSURAVEIS`: nenhum gate bloqueante abre o arquivo."
    )


def test_todo_mime_mensuravel_sem_assinatura_tem_dispensa_declarada() -> None:
    """INVARIANTE 2. O contrario: nao reprovar formato legitimo que so o ffprobe le.

    Um MIME que o sistema mede por outro instrumento, mas cuja assinatura
    `mime_de` nao le, precisa estar na lista de dispensa — senao toda peca
    legitima daquele formato sai `FAIL` no gate de MIME.
    """
    from volc_ads.criativo.adaptadores.medir_imagem import FORMATOS_RECONHECIDOS

    from app.criativo.bancada.operario import (
        _MIMES_MENSURAVEIS,
        _MIMES_VERIFICADOS_POR_OUTRO_INSTRUMENTO,
    )

    sem_assinatura = _MIMES_MENSURAVEIS - FORMATOS_RECONHECIDOS
    sem_dispensa = sem_assinatura - _MIMES_VERIFICADOS_POR_OUTRO_INSTRUMENTO
    assert not sem_dispensa, (
        f"{sorted(sem_dispensa)} sao medidos pelo gate de dimensao, `mime_de` nao "
        f"le a assinatura deles, e nao ha dispensa declarada: toda peca legitima "
        f"desses formatos seria reprovada no gate de MIME."
    )


def test_toda_assinatura_reconhecida_tambem_e_medida() -> None:
    """INVARIANTE 3. Reconhecer o formato e nao medir a dimensao e meia conferencia.

    Se `mime_de` aprender uma assinatura nova sem que o medidor aprenda o
    formato, o gate de MIME sai `PASS` e o de dimensao sai `SKIPPED` — e a peca
    chega a `rendered` com a geometria nunca conferida.
    """
    from volc_ads.criativo.adaptadores.medir_imagem import FORMATOS_RECONHECIDOS

    from app.criativo.bancada.operario import _MIMES_MENSURAVEIS

    meio_conferidos = FORMATOS_RECONHECIDOS - _MIMES_MENSURAVEIS
    assert not meio_conferidos, (
        f"{sorted(meio_conferidos)} tem assinatura lida e dimensao NAO medida: "
        f"o gate de MIME passa e o de dimensao pula."
    )
