"""O golden de P17-T08: uma peça real de imagem atravessando a cadeia inteira.

Rodar:
    .venv-worker/bin/python -m pytest backend/tests/test_criativo_golden_imagem.py \
        volc_ads/criativo -q -p no:cacheprovider

## O que este arquivo prova, e por que ele não é mais um teste da bancada

`test_criativo_bancada.py` prova o interior da fila. `test_criativo_producao_local.py`
prova o contrato com a tela. Nenhum dos dois responde a pergunta da fatia:

    uma peça REAL, com briefing, atravessa briefing → modo → engine → output →
    QA → recibo → storage relido → aprovação → biblioteca → pacote de destino,
    em VARIANTES POR DESTINO, sem provider pago e sem rede?

E a parte que costuma ser encenada é a última: "adaptação multidestino" quase
sempre é o mesmo PNG recortado, entregue com quatro nomes. Por isso aqui a
diferença entre **recompor** e **recortar** não é declarada — é MEDIDA, pixel a
pixel, por `volc_ads.criativo.destinos.classificar_adaptacao`.

## Sem rede, e isso é conferido e não prometido

`sem_rede` derruba `socket.socket` e `socket.create_connection` durante a
travessia inteira. Um provider pago que alguém acrescentasse por engano no
caminho não passaria despercebido: ele levantaria aqui, em vez de gastar.

## Dois sentinelas de divergência, e por que eles vivem neste arquivo

Dois defeitos apareceram enquanto este golden era escrito, e nenhum dos dois é
consertável daqui (`operario.py` e os adaptadores não são desta lane). Em vez de
silenciá-los, cada um virou um teste que AFIRMA o comportamento errado atual e
falha no dia em que alguém consertar — que é quando alguém precisa vir ler isto:

  1. `test_sentinela_o_gate_de_dimensao_do_operario_julga_a_declaracao`
     `Operario._validar` compara `Artefato.largura` com `SaidaPedida.largura`,
     e as duas são números que o MOTOR escreveu. Um motor que grava um PNG de
     64x64 e declara 1200x628 chega a `rendered`, com recibo e `dimensao PASS`.
     A mesma docstring do `_validar` conta que `bytes_` e `sha256` já foram
     movidos para a medida do disco pelo mesmo motivo — a dimensão ficou para
     trás.

  2. `test_sentinela_o_motor_tipografico_nao_declara_natureza`
     `MotorPngLocal` declara `NaturezaDaProcedencia.LOCAL`; `MotorTipografico`
     não declara nada. `servico.natureza_do_motor` devolve `NAO_DECLARADA`, e
     `criativo_ponte.NATUREZAS_ACEITAS[Destino.PRODUCAO]` aceita `NAO_DECLARADA`
     (dívida declarada lá). Resultado: a peça de um motor 100% local passa no
     portão de produção com um aviso, em vez de uma recusa.

## O que este golden NÃO alcança, dito antes que alguém leia demais

A aprovação HUMANA (`criativo_aprovacao`, com o gatilho
`criativo_aprovacao_peca_pronta_tg`) mora no Postgres, e o único Supabase
operacional é o de produção — que esta fatia não toca. A aprovação exercida aqui
é a de DESTINO: `criativo_ponte.Destino`, que decide se aquele lote pode ser
apresentado como produção. São coisas diferentes e não se substituem.
"""

from __future__ import annotations

import hashlib
import json
import socket
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from app.criativo.armazenamento import ArmazenamentoLocal
from app.criativo.bancada import armazenamento_verificado as armazem
from app.criativo.bancada import servico
from app.criativo.bancada.adaptadores.tipografico import MotorTipografico
from app.criativo.bancada.contrato import (
    Artefato,
    Encomenda,
    EstadoDoTrabalho,
    SaidaPedida,
    TERMINAIS,
)
from app.criativo.bancada.deposito import DepositoDeTrabalhos
from app.criativo.bancada.operario import Operario
from services.creative_engine.enquadramento import enquadrar, rotulo_de_proporcao
from volc_ads import criativo_ponte as ponte
from volc_ads.criativo import destinos as D
from volc_ads.criativo import requisitos
from volc_ads.criativo.adaptadores import medir_imagem
from volc_ads.criativo.adaptadores.png_local import desenhar
from volc_ads.criativo.catalogo import Catalogo
from volc_ads.criativo.contrato import (
    Asset,
    LoteDeAssets,
    NaturezaDaProcedencia,
    Origem,
    Procedencia,
    hash_de_conteudo,
)

# ─────────────────────────────────────────────────────────────────────────────
# O briefing — a peça é uma só, e ela é real
# ─────────────────────────────────────────────────────────────────────────────

TENANT = "volc"
CANAL = "DEMAND_GEN"
INTENCAO = "matriculas-2027-bolsa"
SEED = 20260901

BRIEFING = {
    "titulo": "Matricule-se ate 30 de setembro e garanta a bolsa",
    "apoio": "Colegio Positivo — bolsas de ate 40%",
    "insumo": "campanha de matriculas 2027, bolsa por antecipacao, prazo 30/09",
    "canal": CANAL,
    "intencao": INTENCAO,
}

MOTOR_SLUG = "tipografico-local"
MODO_SLUG = "ensaio-local"

GOLDEN = (
    Path(__file__).parent / "goldens" / "criativo-imagem" / "golden-p17-t08.json"
)


# ─────────────────────────────────────────────────────────────────────────────
# A travessia
# ─────────────────────────────────────────────────────────────────────────────


class RedeProibida(RuntimeError):
    """Alguém tentou abrir socket dentro do golden. Isso é o achado, não o erro."""


class _SemRede:
    """Derruba socket durante o bloco. Não é decoração: é o que separa "não
    usamos provider pago" de "não sabemos se usamos"."""

    def __enter__(self) -> _SemRede:
        self._socket = socket.socket
        self._conectar = socket.create_connection

        def recusar(*_a, **_k):
            raise RedeProibida(
                "o golden roda offline: nenhum provider pago no caminho"
            )

        socket.socket = recusar  # type: ignore[assignment]
        socket.create_connection = recusar  # type: ignore[assignment]
        return self

    def __exit__(self, *_: object) -> None:
        socket.socket = self._socket  # type: ignore[assignment]
        socket.create_connection = self._conectar  # type: ignore[assignment]


@dataclass(frozen=True)
class Travessia:
    """O que sobrou da cadeia, para os testes conferirem sem re-renderizar."""

    trabalho_id: str
    estado: EstadoDoTrabalho
    recibo: dict
    bytes_por_slot: dict[str, bytes]
    trilha: tuple[str, ...]
    natureza: NaturezaDaProcedencia
    motor_versoes: dict[str, str]


def _encomenda(*, seed: int, titulo: str | None = None) -> Encomenda:
    """Uma saída por envelope, com a geometria que o catálogo de destinos declara.

    O `slot` sai de `Envelope.slot` (`<ordem>-<tipo>`) e não de um nome livre:
    é ele que permite reconstruir o `TipoDeAsset` do artefato lá na frente, do
    mesmo jeito que `bancada/servico._saidas_da_receita` já faz.
    """
    parametros = dict(BRIEFING)
    if titulo is not None:
        parametros["titulo"] = titulo
    return Encomenda(
        receita_id="golden-p17-t08",
        tenant_id=TENANT,
        motor_slug=MOTOR_SLUG,
        modo_slug=MODO_SLUG,
        finalidade_slug=CANAL.lower(),
        seed=seed,
        saidas=tuple(
            SaidaPedida(
                slot=e.slot,
                largura=e.largura,
                altura=e.altura,
                midia="imagem",
                mime="image/png",
            )
            for e in D.ENVELOPES
        ),
        parametros=parametros,
    )


def _atravessar(
    raiz: Path, *, seed: int = SEED, titulo: str | None = None, nome: str = "golden"
) -> Travessia:
    """Briefing → fila → operário → recibo, offline, com o motor tipográfico.

    O motor é o TIPOGRÁFICO e não o `png-local` de propósito: ele é o único
    local que **recompõe** — quebra de linha, corpo da fonte e centralização
    saem do canvas. `png-local` desenha blocos derivados do hash, e blocos não
    respondem se a composição se adaptou ao formato.
    """
    raiz.mkdir(parents=True, exist_ok=True)
    deposito = DepositoDeTrabalhos(raiz / "fila.db")
    motor = MotorTipografico()
    operario = Operario(
        deposito, {MOTOR_SLUG: motor}, raiz / "trabalhos", nome=nome
    )

    trabalho, criado = deposito.enfileirar(_encomenda(seed=seed, titulo=titulo))
    assert criado, "a fila devolveu um trabalho que já existia; o golden começa limpo"
    assert trabalho.estado is EstadoDoTrabalho.QUEUED

    concluido = operario.trabalhar_uma_vez()
    assert concluido is not None, "a fila estava vazia logo depois de enfileirar"

    recibo = concluido.recibo or {}
    bytes_por_slot = {
        str(a["slot"]): Path(str(a["caminho"])).read_bytes()
        for a in recibo.get("artefatos") or []
    }
    trilha = tuple(
        str(p["para"]) for p in deposito.trilha(concluido.id, tenant_id=TENANT)
    )
    return Travessia(
        trabalho_id=concluido.id,
        estado=concluido.estado,
        recibo=recibo,
        bytes_por_slot=bytes_por_slot,
        trilha=trilha,
        natureza=servico.natureza_do_motor(motor),
        motor_versoes=motor.versoes_congeladas(),
    )


@pytest.fixture(scope="module")
def travessia(tmp_path_factory) -> Travessia:
    """Uma travessia por módulo: renderizar cinco peças custa ~1,5 s e nenhum
    teste daqui muda o resultado — todos leem os mesmos bytes."""
    with _SemRede():
        return _atravessar(tmp_path_factory.mktemp("golden"))


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    """Vale para todo teste deste arquivo, inclusive os que não renderizam."""

    def recusar(*_a, **_k):
        raise RedeProibida("o golden roda offline")

    monkeypatch.setattr(socket, "socket", recusar)
    monkeypatch.setattr(socket, "create_connection", recusar)


# ─────────────────────────────────────────────────────────────────────────────
# A cadeia
# ─────────────────────────────────────────────────────────────────────────────


def test_a_peca_atravessa_a_fila_com_os_estados_na_ordem(travessia):
    """`queued → claimed → running → validating → rendered`, e nenhum pulado.

    A ordem importa porque `validating` é o único estado em que o gate pode
    reprovar: se o trabalho já fosse `rendered` antes dele, o gate não decidiria
    nada — é o que a docstring do `Operario` chama de decoração.
    """
    assert travessia.estado is EstadoDoTrabalho.RENDERED
    assert travessia.estado in TERMINAIS
    assert travessia.trilha == ("claimed", "running", "validating", "rendered")


def test_o_recibo_carrega_o_que_permite_repetir(travessia):
    r = travessia.recibo
    assert r["chave_de_idempotencia"]
    assert r["motor_slug"] == MOTOR_SLUG
    assert r["seed"] == SEED
    assert r["parametros"]["insumo"] == BRIEFING["insumo"]
    assert r["parametros"]["titulo"] == BRIEFING["titulo"]
    # A versão do motor E o que participou do pixel. `fonte_sha256` está aqui
    # porque trocar o arquivo da fonte muda o desenho, e um recibo que não o
    # registrasse mentiria sobre reprodutibilidade.
    assert r["motor_versao"]
    assert set(r["versoes"]) >= {"adaptador", "pillow", "fonte_arquivo", "fonte_sha256"}
    assert r["assinatura_determinista"]
    assert len(r["artefatos"]) == len(D.ENVELOPES)


def test_cada_envelope_saiu_na_medida_com_mime_lido_do_magic_byte(travessia):
    """Dimensão exata, MIME dos BYTES e sha256 conferido contra o disco.

    ⚠️ O MIME sai de `medir_imagem.medir`, que lê a assinatura do arquivo. A
    extensão `.png` que o motor escolheu não é evidência de nada: quem escolhe o
    nome do arquivo é quem produziu, e é exatamente ele que está sendo auditado.
    """
    for envelope in D.ENVELOPES:
        dados = travessia.bytes_por_slot[envelope.slot]
        medida = medir_imagem.medir(dados)
        assert medida.mime == "image/png", envelope.slug
        assert (medida.largura, medida.altura) == (envelope.largura, envelope.altura)
        assert medida.bytes_totais == len(dados) > 0
        # O rótulo do catálogo bate com o que a régua de proporção da casa
        # deriva das mesmas dimensões — o rótulo não é decoração.
        assert rotulo_de_proporcao(envelope.largura, envelope.altura) == (
            envelope.proporcao
        ), envelope.slug

    por_slot = {a["slot"]: a for a in travessia.recibo["artefatos"]}
    for envelope in D.ENVELOPES:
        artefato = por_slot[envelope.slot]
        dados = travessia.bytes_por_slot[envelope.slot]
        assert artefato["sha256"] == hashlib.sha256(dados).hexdigest()
        assert artefato["bytes_"] == len(dados)


def test_o_gate_de_dimensao_do_operario_aprovou_cada_envelope(travessia):
    """Cada envelope tem um `dimensao PASS` com o par pedido/medido dele.

    O casamento é por `detalhe["pedido"]` porque a `Validacao` de dimensão NÃO
    carrega o slot — ver `precisa_de_terceiro` no relato desta lane. Aqui isso
    funciona só porque as cinco geometrias são distintas; com dois envelopes de
    mesma medida no mesmo pedido, nada diria qual arquivo o gate julgou.
    """
    dimensoes = [
        v for v in travessia.recibo["validacoes"] if v["gate"] == "dimensao"
    ]
    assert len(dimensoes) == len(D.ENVELOPES)
    pedidos = {tuple(v["detalhe"]["pedido"]) for v in dimensoes}
    assert pedidos == {(e.largura, e.altura) for e in D.ENVELOPES}
    for v in dimensoes:
        assert v["resultado"] == "PASS"
        assert v["bloqueante"] is True
        # ⚠️ `medido` e nao `produzido`: o gate passou a abrir o arquivo. O
        # `declarado` continua no detalhe como terceiro numero, para o recibo
        # guardar o que o motor AFIRMOU ao lado do que o disco TEM.
        assert v["detalhe"]["pedido"] == v["detalhe"]["medido"]
        assert v["detalhe"]["declarado"] == v["detalhe"]["medido"]

    # Os outros gates bloqueantes também passaram, e o de contraste trouxe o
    # NÚMERO — um gate que só diz "passou" impede a próxima pergunta.
    por_gate = {v["gate"] for v in travessia.recibo["validacoes"]}
    assert {"hash_confere", "arquivo_nao_vazio", "dimensao", "contraste"} <= por_gate
    contraste = next(
        v for v in travessia.recibo["validacoes"] if v["gate"] == "contraste"
    )
    assert contraste["resultado"] == "PASS"
    assert contraste["detalhe"]["razao"] >= contraste["detalhe"]["piso_aa"]


# ─────────────────────────────────────────────────────────────────────────────
# Recompor não é recortar — e a diferença é medida
# ─────────────────────────────────────────────────────────────────────────────


def test_cada_variante_por_destino_e_recomposicao_medida_e_nao_recorte(travessia):
    """O discriminante é físico: o desenho é mistura convexa de duas cores.

    Reamostrar (LANCZOS, que é o que `enquadrar` usa) produz overshoot fora do
    segmento fundo→tinta. Compor de novo, não. `fora_da_rampa == 0` em todas as
    variantes é a prova de que cada canvas foi DESENHADO, não esticado.
    """
    mestre = travessia.bytes_por_slot[D.ENVELOPES[0].slot]
    for envelope in D.ENVELOPES[1:]:
        veredito = D.classificar_adaptacao(
            mestre, travessia.bytes_por_slot[envelope.slot]
        )
        assert veredito.tipo == D.RECOMPOSICAO, (envelope.slug, veredito.motivo)
        assert veredito.recomposta is True
        assert veredito.evidencia["variante"]["fora_da_rampa"] == 0


def test_o_mesmo_png_recortado_e_classificado_como_recorte(travessia):
    """MUTANTE. Se o classificador aprovasse recorte como recomposição, o teste
    acima seria tautologia — ele passaria com a fábrica quebrada.

    Aqui o MESMO mestre é levado a cada envelope por `enquadrar`, que é o
    caminho de recorte real do repositório, e o veredito tem de virar.
    """
    mestre = travessia.bytes_por_slot[D.ENVELOPES[0].slot]
    for envelope in D.ENVELOPES[1:]:
        recortada = enquadrar(mestre, envelope.largura, envelope.altura)
        # `cover_crop` quando a proporção muda; `resize` quando só a escala muda
        # (o logo 1200x1200 é 1:1 como o mestre). As duas são reamostragem, e é
        # a reamostragem que o classificador tem de enxergar — não o rótulo.
        assert recortada.enquadramento in ("cover_crop", "resize"), envelope.slug
        # Mesma dimensão do envelope: pelo tamanho, as duas são indistinguíveis.
        assert (recortada.largura, recortada.altura) == (
            envelope.largura,
            envelope.altura,
        )
        veredito = D.classificar_adaptacao(mestre, recortada.conteudo)
        assert veredito.tipo == D.CROP_RESIZE, (envelope.slug, veredito.motivo)
        assert veredito.recomposta is False
        assert veredito.evidencia["variante"]["fora_da_rampa"] > 0


def test_o_recorte_come_a_margem_que_a_recomposicao_preserva(travessia):
    """Segunda medida, independente da primeira, e ela é a que dói.

    No 4:5 e no 9:16 o `cover` amplia a peça 1:1 em 25% e 78% e corta as
    laterais: a tinta passa a encostar na borda, ou seja, letra cortada. A
    recomposição mantém a margem que o motor calcula a partir do canvas.
    """
    mestre = travessia.bytes_por_slot[D.ENVELOPES[0].slot]
    perfil_mestre = D.perfilar(mestre)
    assert perfil_mestre.toca_a_borda() is False
    assert perfil_mestre.margem_esquerda is not None

    for slug in ("meta-feed-4x5", "organico-reels-9x16"):
        envelope = D.envelope_de(slug)
        recomposta = D.perfilar(travessia.bytes_por_slot[envelope.slot])
        recortada = D.perfilar(
            enquadrar(mestre, envelope.largura, envelope.altura).conteudo
        )

        assert recomposta.toca_a_borda() is False, slug
        assert recortada.toca_a_borda() is True, slug
        assert recomposta.margem_esquerda == perfil_mestre.margem_esquerda
        assert recortada.margem_esquerda == 0

        # E o corpo do texto: recompor mantém o tamanho do glifo que o canvas de
        # 1080 de largura pede; recortar o multiplica pelo fator de cover.
        assert recomposta.faixas == perfil_mestre.faixas, slug
        assert all(
            depois > antes
            for antes, depois in zip(recomposta.faixas, recortada.faixas)
        ), (slug, recomposta.faixas, recortada.faixas)


def test_a_largura_diferente_muda_o_corpo_da_fonte_e_nao_so_o_recorte(travessia):
    """O 1.91:1 tem 1200 de largura, e o motor recompõe com outro corpo.

    Se a "variante" fosse recorte, o corpo do glifo seria o do mestre escalado
    pelo cover. Aqui ele é o que o canvas de 1200 pede — margem e corpo saem da
    largura, não de um fator de escala.
    """
    mestre = D.perfilar(travessia.bytes_por_slot[D.ENVELOPES[0].slot])
    largo = D.perfilar(
        travessia.bytes_por_slot[D.envelope_de("google-display-191x1").slot]
    )
    assert largo.margem_esquerda != mestre.margem_esquerda
    assert largo.faixas != mestre.faixas
    assert len(largo.faixas) == len(mestre.faixas)


def test_sem_medir_pixel_nao_ha_veredito_de_adaptacao(travessia, monkeypatch):
    """Ausência de Pillow vira recusa nomeada, nunca "recomposicao" por omissão."""
    monkeypatch.setattr(D, "_pillow", lambda: None)
    mestre = travessia.bytes_por_slot[D.ENVELOPES[0].slot]
    outra = travessia.bytes_por_slot[D.ENVELOPES[1].slot]
    with pytest.raises(D.MedicaoDePixelsIndisponivel):
        D.classificar_adaptacao(mestre, outra)


# ─────────────────────────────────────────────────────────────────────────────
# Determinismo
# ─────────────────────────────────────────────────────────────────────────────


def test_mesma_semente_mesma_assinatura_e_mesmos_sha256(tmp_path):
    """Duas travessias independentes, mesma semente: recibo e pixels batem.

    Bancadas separadas de propósito — o mesmo depósito devolveria o mesmo
    trabalho por idempotência, e a igualdade provaria só que o SQLite lembra.
    """
    with _SemRede():
        um = _atravessar(tmp_path / "a", seed=SEED, nome="op-a")
        dois = _atravessar(tmp_path / "b", seed=SEED, nome="op-b")

    assert um.trabalho_id != dois.trabalho_id
    assert (
        um.recibo["assinatura_determinista"]
        == dois.recibo["assinatura_determinista"]
    )
    assert um.recibo["chave_de_idempotencia"] == dois.recibo["chave_de_idempotencia"]
    for envelope in D.ENVELOPES:
        assert (
            hashlib.sha256(um.bytes_por_slot[envelope.slot]).hexdigest()
            == hashlib.sha256(dois.bytes_por_slot[envelope.slot]).hexdigest()
        ), envelope.slug

    # `produzido_por` e os carimbos de tempo DIFEREM, e a assinatura não os vê —
    # é isso que a torna capaz de responder "o motor repetiu?".
    assert um.recibo["produzido_por"] != dois.recibo["produzido_por"]
    assert um.recibo["terminado_em"] != dois.recibo["terminado_em"]


def test_semente_diferente_muda_assinatura_e_pixel(tmp_path):
    """MUTANTE do teste acima. Uma assinatura que ignorasse a semente passaria
    lá e falharia aqui — sem este teste, "determinístico" poderia significar
    "constante"."""
    with _SemRede():
        um = _atravessar(tmp_path / "a", seed=SEED, nome="op-a")
        outro = _atravessar(tmp_path / "b", seed=SEED + 1, nome="op-b")

    assert (
        um.recibo["assinatura_determinista"]
        != outro.recibo["assinatura_determinista"]
    )
    assert um.recibo["chave_de_idempotencia"] != outro.recibo["chave_de_idempotencia"]
    # A semente escolhe a paleta: os bytes têm de mudar em todas as saídas.
    for envelope in D.ENVELOPES:
        assert (
            um.bytes_por_slot[envelope.slot] != outro.bytes_por_slot[envelope.slot]
        ), envelope.slug


def test_briefing_diferente_muda_o_pixel_e_a_assinatura(tmp_path):
    """E o insumo também entra. Um motor que ignorasse o título produziria a
    mesma peça para dois briefings, e o recibo diria que repetiu — corretamente,
    sobre uma peça que não representa o pedido."""
    with _SemRede():
        um = _atravessar(tmp_path / "a", seed=SEED, nome="op-a")
        outro = _atravessar(
            tmp_path / "b", seed=SEED, titulo="Ultimos dias de inscricao", nome="op-b"
        )
    assert (
        um.recibo["assinatura_determinista"]
        != outro.recibo["assinatura_determinista"]
    )
    for envelope in D.ENVELOPES:
        assert um.bytes_por_slot[envelope.slot] != outro.bytes_por_slot[envelope.slot]


# ─────────────────────────────────────────────────────────────────────────────
# Custo
# ─────────────────────────────────────────────────────────────────────────────


def test_custo_nao_apurado_nao_e_custo_zero(travessia):
    """`None` em toda parte, e `None` não é `0.0`.

    O motor é local e não custa dinheiro — e ainda assim o sistema não afirma
    que a peça saiu de graça, porque ninguém apurou. Um relatório de COGS que
    soma zeros inventados fecha bonito e está errado.
    """
    r = travessia.recibo
    assert r["custo_estimado_usd"] is None
    assert r["custo_real_usd"] is None
    # A distinção explicitada: se algum dia alguém trocar `None` por `0.0`, a
    # linha abaixo é a que acusa — `None != 0.0`, e `0.0 is None` é `False`.
    assert r["custo_real_usd"] != 0.0
    assert r["custo_real_usd"] is not False  # `0` e `False` colapsam em Python

    for asset in _assets(travessia):
        assert asset.procedencia.custo_usd is None
        assert asset.procedencia.custo_usd != 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Armazenamento — guardar não é verificar
# ─────────────────────────────────────────────────────────────────────────────


def _publicar(travessia: Travessia, raiz: Path) -> dict[str, armazem.Publicacao]:
    loja = ArmazenamentoLocal(raiz)
    saida: dict[str, armazem.Publicacao] = {}
    for envelope in D.ENVELOPES:
        dados = travessia.bytes_por_slot[envelope.slot]
        chave = armazem.chave_canonica(
            TENANT,
            travessia.trabalho_id,
            envelope.slot,
            armazem.sha256_de(dados),
            "png",
        )
        saida[envelope.slug] = armazem.publicar_artefato(
            loja, chave=chave, dados=dados, mime="image/png"
        )
    return saida


def test_o_armazenamento_e_verificado_relendo_os_bytes(travessia, tmp_path):
    publicacoes = _publicar(travessia, tmp_path / "storage")
    assert set(publicacoes) == {e.slug for e in D.ENVELOPES}
    for slug, pub in publicacoes.items():
        assert pub.estado is armazem.EstadoDoArmazenamento.VERIFIED_OK, slug
        assert pub.verificado is True
        assert pub.sha256_remoto == pub.sha256_local
        assert pub.bytes_remoto == pub.bytes_local
        assert pub.conferido_em is not None
        assert pub.exigir_verificado() is pub


def test_bytes_corrompidos_no_disco_derrubam_a_verificacao(travessia, tmp_path):
    """CONTRAPROVA VERMELHA do teste acima.

    Sem ela, `verificado is True` provaria só que dois `sha256` calculados sobre
    a MESMA variável em memória são iguais — o que é verdade mesmo quando o
    objeto remoto está truncado. Aqui o arquivo é adulterado entre o `guardar` e
    o `ler`, e o veredito tem de virar `VERIFIED_MISMATCH`.
    """
    raiz = tmp_path / "storage"
    loja = ArmazenamentoLocal(raiz)
    envelope = D.ENVELOPES[0]
    dados = travessia.bytes_por_slot[envelope.slot]
    chave = armazem.chave_canonica(
        TENANT, travessia.trabalho_id, envelope.slot, armazem.sha256_de(dados), "png"
    )

    class LojaQueGravaMenos:
        """Aceita o upload e guarda um byte a menos — o disco cheio clássico."""

        nome = "local-truncada"

        def conferir_bucket(self):
            return loja.conferir_bucket()

        def guardar(self, chave, dados, mime):
            return loja.guardar(chave, dados[:-1], mime)

        def ler(self, chave):
            return loja.ler(chave)

    pub = armazem.publicar_artefato(
        LojaQueGravaMenos(), chave=chave, dados=dados, mime="image/png"
    )
    assert pub.estado is armazem.EstadoDoArmazenamento.VERIFIED_MISMATCH
    assert pub.verificado is False
    assert pub.motivo
    with pytest.raises(armazem.ArtefatoNaoVerificado):
        pub.exigir_verificado()


# ─────────────────────────────────────────────────────────────────────────────
# Biblioteca, aprovação de destino e pacotes
# ─────────────────────────────────────────────────────────────────────────────


def _assets(travessia: Travessia) -> tuple[Asset, ...]:
    """Os artefatos viram `Asset` medidos DOS BYTES, como `servico` já faz.

    A natureza sai de `servico.natureza_do_motor(motor)` e não de uma constante
    escrita aqui: o golden precisa exibir o que o sistema declara, inclusive
    quando o que ele declara é "ninguém declarou".
    """
    quando = datetime.fromisoformat(travessia.recibo["terminado_em"])
    assets = []
    for envelope in D.ENVELOPES:
        dados = travessia.bytes_por_slot[envelope.slot]
        medida = medir_imagem.medir(dados)
        assets.append(
            Asset(
                tipo=envelope.tipo,
                procedencia=Procedencia(
                    motor=travessia.recibo["motor_slug"],
                    versao_do_motor=travessia.recibo["motor_versao"],
                    insumo=str(BRIEFING["insumo"]),
                    quando=quando,
                    pedido=travessia.trabalho_id,
                    custo_usd=None,
                    nota="`quando` é o `terminado_em` do recibo, não um relógio",
                    natureza=travessia.natureza,
                ),
                conteudo_hash=hash_de_conteudo(dados),
                origem=Origem.GERADO,
                bytes_totais=medida.bytes_totais,
                mime=medida.mime,
                largura=medida.largura,
                altura=medida.altura,
                rotulo=envelope.slug,
            )
        )
    return tuple(assets)


def test_a_biblioteca_registra_cada_peca_uma_vez_e_dedup_por_conteudo(travessia):
    """O catálogo é a biblioteca: identidade derivada do conteúdo, sem contador."""
    catalogo = Catalogo()
    assets = _assets(travessia)
    for asset in assets:
        registro = catalogo.registrar(asset)
        assert registro.novo is True
    assert len(catalogo) == len(D.ENVELOPES)

    # Registrar de novo não cria segunda linha: replay de lote não duplica peça.
    for asset in assets:
        assert catalogo.registrar(asset).novo is False
    assert len(catalogo) == len(D.ENVELOPES)

    # E cinco peças distintas têm cinco hashes distintos — se o motor tivesse
    # entregado o mesmo PNG cinco vezes, o catálogo teria colapsado para 1 e
    # este é o teste que veria.
    assert len({a.conteudo_hash for a in assets}) == len(D.ENVELOPES)


def test_a_aprovacao_de_destino_passa_em_ensaio_e_recusa_producao(travessia):
    """O lote é APROVADO pela régua do canal, e o portão de destino é outro.

    `veredito.ok` responde "os arquivos servem para o canal". `Destino` responde
    "este payload pode ir para uma conta real". As duas respostas são diferentes
    e o golden precisa das duas.
    """
    assets = _assets(travessia)
    conteudo = {
        a.identidade: travessia.bytes_por_slot[e.slot]
        for a, e in zip(assets, D.ENVELOPES)
    }
    lote = LoteDeAssets(canal=CANAL, assets=assets, intencao=INTENCAO)

    ensaio = ponte.imagens_de_demand_gen(
        lote, conteudo, destino=ponte.Destino.ENSAIO
    )
    assert ensaio.veredito.ok is True
    assert len(ensaio.veredito.aprovados) == len(D.ENVELOPES)
    assert ensaio.veredito.reprovados == ()
    assert ensaio.ok is True
    assert ensaio.recusas == ()
    # Linhagem por peça, com o hash conferido contra os bytes.
    assert len(ensaio.linhagem) == len(D.ENVELOPES)
    for linha in ensaio.linhagem:
        assert linha.conteudo_hash.startswith("sha256:")
        assert linha.custo_usd is None

    # A régua do canal é a mesma que `requisitos` publica — não uma lista local.
    exigencia = requisitos.exigencia_binaria_de(CANAL)
    assert ensaio.veredito.fonte == exigencia.fonte


def test_nao_ha_publicacao_automatica_em_lugar_nenhum(travessia):
    """Vínculo ao destino existe; chamada de API não.

    Três provas, e nenhuma delas é "não vi nenhuma chamada":
      1. `app.criativo.destino` continua sem implementação — importá-lo não faz
         nada, e o golden confere que ele não expõe função alguma;
      2. `sem_rede` está ligado neste teste: qualquer socket levantaria;
      3. o pacote de destino declara `publicacao_automatica is False`.
    """
    from app.criativo import destino as fronteira

    publicos = [
        nome
        for nome in dir(fronteira)
        if not nome.startswith("_") and callable(getattr(fronteira, nome))
    ]
    assert publicos == [], f"a fronteira de destino ganhou código: {publicos}"

    with pytest.raises(RedeProibida):
        socket.socket()

    for pacote in _pacotes(travessia):
        assert pacote.publicacao_automatica is False


def _pacotes(travessia: Travessia, raiz: Path | None = None):
    """Monta os pacotes por destino a partir da travessia.

    `relido_hash` só é preenchido quando houve releitura de verdade; sem `raiz`,
    ele fica `None` — e `armazenamento_verificado` responde `None`, que é
    "ninguém releu", não "releu e não bateu".
    """
    publicacoes = _publicar(travessia, raiz) if raiz is not None else {}
    variantes = []
    mestre = travessia.bytes_por_slot[D.ENVELOPES[0].slot]
    for indice, envelope in enumerate(D.ENVELOPES):
        dados = travessia.bytes_por_slot[envelope.slot]
        medida = medir_imagem.medir(dados)
        if indice == 0:
            adaptacao = D.MESTRE
        else:
            adaptacao = D.classificar_adaptacao(mestre, dados).tipo
        pub = publicacoes.get(envelope.slug)
        variantes.append(
            D.VarianteEntregue(
                envelope_slug=envelope.slug,
                conteudo_hash=hash_de_conteudo(dados),
                mime=medida.mime,
                largura=medida.largura,
                altura=medida.altura,
                bytes_totais=medida.bytes_totais,
                adaptacao=adaptacao,
                chave_de_armazenamento=pub.chave if pub else None,
                relido_hash=(
                    pub.sha256_remoto if pub and pub.verificado else None
                ),
            )
        )
    return D.montar_pacotes(variantes, natureza=travessia.natureza)


def test_os_pacotes_por_destino_ficam_completos_verificados_e_nao_publicaveis(
    travessia, tmp_path
):
    pacotes = {p.destino: p for p in _pacotes(travessia, tmp_path / "storage")}
    assert set(pacotes) == set(D.DESTINOS)

    for destino, pacote in pacotes.items():
        assert pacote.faltando == (), destino
        assert pacote.completo is True, destino
        assert pacote.verificado is True, destino
        # A peça é de motor local: ela não vira anúncio, e o pacote diz isso.
        assert pacote.publicavel is False, destino
        for variante in pacote.variantes:
            assert variante.na_medida is True
            assert variante.armazenamento_verificado is True
            assert variante.adaptacao in (D.MESTRE, D.RECOMPOSICAO)

    assert {v.envelope_slug for v in pacotes[D.META].variantes} == {
        "meta-feed-1x1",
        "meta-feed-4x5",
    }
    assert {v.envelope_slug for v in pacotes[D.GOOGLE].variantes} == {
        "google-display-191x1",
        "google-logo-1x1",
    }
    assert {v.envelope_slug for v in pacotes[D.ORGANICO].variantes} == {
        "organico-reels-9x16"
    }


def test_pacote_sem_releitura_nao_se_diz_verificado(travessia):
    """CONTRAPROVA VERMELHA do teste acima: sem releitura, `verificado` é `False`
    e cada variante responde `None` — que é "ninguém releu", não "não bateu"."""
    for pacote in _pacotes(travessia):
        assert pacote.verificado is False
        assert pacote.publicavel is False
        for variante in pacote.variantes:
            assert variante.armazenamento_verificado is None
            assert variante.armazenada is False


# ─────────────────────────────────────────────────────────────────────────────
# O golden versionado
# ─────────────────────────────────────────────────────────────────────────────


def _projecao(travessia: Travessia, pacotes) -> dict:
    """A projeção INDEPENDENTE DE MÁQUINA do golden.

    ⚠️ `sha256`, `bytes` e `assinatura_determinista` NÃO entram. Eles dependem
    da versão do Pillow, do FreeType e do arquivo da fonte — e as três entram no
    recibo de propósito, justamente para que uma divergência aponte a causa.
    Congelá-los num arquivo versionado transformaria "outra máquina" em
    "regressão", que é o jeito mais rápido de um golden ser desligado.

    O determinismo desses três é provado por COMPARAÇÃO entre duas execuções
    nesta mesma máquina (`test_mesma_semente_...`), que é o que se pode afirmar.
    """
    por_gate = {}
    for v in travessia.recibo["validacoes"]:
        if v["gate"] == "dimensao":
            por_gate[tuple(v["detalhe"]["pedido"])] = v["resultado"]

    mestre = travessia.bytes_por_slot[D.ENVELOPES[0].slot]
    envelopes = []
    for indice, envelope in enumerate(D.ENVELOPES):
        dados = travessia.bytes_por_slot[envelope.slot]
        medida = medir_imagem.medir(dados)
        if indice == 0:
            adaptacao, fora = D.MESTRE, D.perfilar(dados).fora_da_rampa
        else:
            veredito = D.classificar_adaptacao(mestre, dados)
            adaptacao = veredito.tipo
            fora = veredito.evidencia["variante"]["fora_da_rampa"]
        recorte = (
            None
            if indice == 0
            else D.classificar_adaptacao(
                mestre, enquadrar(mestre, envelope.largura, envelope.altura).conteudo
            ).tipo
        )
        envelopes.append({
            "envelope": envelope.slug,
            "destino": envelope.destino,
            "slot": envelope.slot,
            "tipo": envelope.tipo.value,
            "proporcao": envelope.proporcao,
            "largura": medida.largura,
            "altura": medida.altura,
            "mime": medida.mime,
            "gate_dimensao": por_gate[(envelope.largura, envelope.altura)],
            "adaptacao": adaptacao,
            "fora_da_rampa": fora,
            "adaptacao_se_fosse_recorte": recorte,
        })

    return {
        "_leia": (
            "GERADO por test_criativo_golden_imagem.py. Regravar com "
            "CRIATIVO_REGRAVAR_GOLDEN=1. Só entra aqui o que NÃO depende da "
            "máquina: sha256, bytes e assinatura_determinista ficam de fora "
            "porque Pillow, FreeType e o arquivo da fonte os mudam — o "
            "determinismo deles é provado por comparação entre duas execuções."
        ),
        "tarefa": "P17-T08",
        "seed": SEED,
        "motor_slug": travessia.recibo["motor_slug"],
        "modo_slug": MODO_SLUG,
        "canal": CANAL,
        "estados": list(travessia.trilha),
        "natureza_declarada_pelo_motor": travessia.natureza.value,
        "custo": {
            "custo_estimado_usd": travessia.recibo["custo_estimado_usd"],
            "custo_real_usd": travessia.recibo["custo_real_usd"],
            "estado": "nao_apurado",
        },
        "envelopes": envelopes,
        "pacotes": [
            {
                "destino": p.destino,
                "esperados": list(p.esperados),
                "faltando": list(p.faltando),
                "completo": p.completo,
                "verificado": p.verificado,
                "publicavel": p.publicavel,
                "publicacao_automatica": p.publicacao_automatica,
            }
            for p in pacotes
        ],
    }


def test_a_travessia_bate_com_o_golden_versionado(travessia, tmp_path):
    """O arquivo em `goldens/criativo-imagem/` é o contrato desta fatia.

    Para regravá-lo depois de uma mudança DELIBERADA:
        CRIATIVO_REGRAVAR_GOLDEN=1 pytest backend/tests/test_criativo_golden_imagem.py
    """
    import os

    obtido = _projecao(travessia, _pacotes(travessia, tmp_path / "storage"))
    if os.environ.get("CRIATIVO_REGRAVAR_GOLDEN"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(
            json.dumps(obtido, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        pytest.skip("golden regravado a pedido; rode de novo sem a variável")

    assert GOLDEN.is_file(), f"golden ausente: {GOLDEN}"
    esperado = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert obtido == esperado


# ─────────────────────────────────────────────────────────────────────────────
# Sentinelas de divergência — o comportamento errado, afirmado para não sumir
# ─────────────────────────────────────────────────────────────────────────────


class MotorQueMenteNaDimensao:
    """Grava 64x64 e declara o que foi pedido. Nada mais.

    Ele não é um dublê do motor: é o mínimo necessário para perguntar de quem o
    gate de dimensão acredita. `bytes_` e `sha256` são MEDIDOS do disco — sem
    isso o trabalho falharia nos outros gates e o achado ficaria escondido atrás
    de uma falha diferente.
    """

    slug = "mentiroso-na-dimensao"
    versao = "0.0.1"

    def versoes_congeladas(self) -> dict[str, str]:
        return {"adaptador": self.versao}

    def produzir(self, encomenda, dir_trabalho):
        artefatos = []
        for saida in encomenda.saidas:
            dados = desenhar(64, 64, hashlib.sha256(saida.slot.encode()).digest())
            caminho = Path(dir_trabalho) / f"{saida.slot}.png"
            caminho.write_bytes(dados)
            do_disco = caminho.read_bytes()
            artefatos.append(
                Artefato(
                    slot=saida.slot,
                    caminho=str(caminho),
                    mime="image/png",
                    bytes_=len(do_disco),
                    sha256=hashlib.sha256(do_disco).hexdigest(),
                    largura=saida.largura,   # ← a mentira
                    altura=saida.altura,     # ← a mentira
                    duracao_s=None,
                )
            )
        return tuple(artefatos)


def test_o_gate_de_dimensao_mede_o_arquivo_e_nao_acredita_no_motor(tmp_path):
    """DIVERGÊNCIA FECHADA em 01/09/2026 — esta prova era a sentinela dela.

    `Operario._validar` já movia `bytes_` e `sha256` para a medida do disco — a
    própria docstring conta por quê: "um motor que devolvesse `bytes_=4096,
    sha256='f'*64` sem escrever byte nenhum chegava a `rendered`". A DIMENSÃO
    ficou para trás: ela era `Artefato.largura` (declaração do motor)
    contra `SaidaPedida.largura` (o pedido), e o arquivo nunca era aberto.

    Consequência medida antes da correção, em
    `contraprovas/contraprova_dimensao_declarada.py`: um PNG de 64x64 chegava a
    `rendered`, com recibo e `dimensao PASS` dizendo
    `pedido == produzido == [1200, 628]`. A peça não servia a canal nenhum e
    nada acusava.

    Agora o gate abre o arquivo. Este teste é a prova de que ele abre: um motor
    que grava 64x64 e declara 1200x628 é recusado por DOIS gates bloqueantes, e
    não sai recibo nenhum.
    """
    envelope = D.envelope_de("google-display-191x1")
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    operario = Operario(
        deposito,
        {"mentiroso-na-dimensao": MotorQueMenteNaDimensao()},
        tmp_path / "trabalhos",
        nome="sentinela",
    )
    encomenda = Encomenda(
        receita_id="sentinela-dimensao",
        tenant_id=TENANT,
        motor_slug="mentiroso-na-dimensao",
        modo_slug=MODO_SLUG,
        finalidade_slug=CANAL.lower(),
        seed=SEED,
        saidas=(
            SaidaPedida(
                slot=envelope.slot,
                largura=envelope.largura,
                altura=envelope.altura,
                midia="imagem",
                mime="image/png",
            ),
        ),
        parametros=dict(BRIEFING),
    )
    deposito.enfileirar(encomenda)
    trabalho = operario.trabalhar_uma_vez()
    assert trabalho is not None

    # O trabalho é RECUSADO, e por dois gates diferentes.
    assert trabalho.estado is EstadoDoTrabalho.FAILED
    assert trabalho.recibo is None, "recibo sobre peça que não serve a canal nenhum"
    validacoes = trabalho.falha["validacoes"]

    dimensao = next(v for v in validacoes if v["gate"] == "dimensao")
    assert dimensao["resultado"] == "FAIL"
    assert dimensao["bloqueante"] is True
    # O gate agora traz os TRÊS números, e o `slot` junto — antes ele não trazia
    # o slot, e com dois envelopes de mesma medida nada diria qual arquivo ele
    # julgou.
    assert dimensao["detalhe"]["slot"] == envelope.slot
    assert dimensao["detalhe"]["pedido"] == [envelope.largura, envelope.altura]
    assert dimensao["detalhe"]["medido"] == [64, 64]
    assert dimensao["detalhe"]["declarado"] == [envelope.largura, envelope.altura]

    # E há um gate SÓ para a mentira: "produziu do tamanho errado" e "mentiu
    # sobre o tamanho" são coisas distintas, e o recibo distingue as duas.
    mentira = next(v for v in validacoes if v["gate"] == "dimensao_declarada_confere")
    assert mentira["resultado"] == "FAIL" and mentira["bloqueante"] is True
    assert mentira["detalhe"]["declarado"] == [envelope.largura, envelope.altura]
    assert mentira["detalhe"]["medido"] == [64, 64]

    # A medida REAL dos bytes é a mesma que o gate usou.
    caminho = next(Path(str(operario.raiz)).rglob("*.png"))
    medida = medir_imagem.medir(caminho.read_bytes())
    assert (medida.largura, medida.altura) == (64, 64)


def test_o_motor_tipografico_declara_natureza_local(travessia):
    """DIVERGÊNCIA FECHADA em 01/09/2026 — esta prova era a sentinela dela.

    `MotorPngLocal` declara `natureza = NaturezaDaProcedencia.LOCAL`.
    `MotorTipografico` não declarava nada, então `servico.natureza_do_motor`
    devolvia `NAO_DECLARADA` — que é a resposta correta da função, e a errada
    para este motor: ele é tão local quanto o outro.

    O custo aparece no portão de produção: `NATUREZAS_ACEITAS[Destino.PRODUCAO]`
    aceita `NAO_DECLARADA` como dívida declarada, então a peça de um motor local
    passa com AVISO onde o `png-local` recebe RECUSA. O aviso está lá e é
    conferido abaixo; a recusa é o que deveria estar.

    Falha quando o motor declarar. É para falhar.
    """
    # DIVERGÊNCIA FECHADA: o motor declara, e a resposta deixou de ser "não sei".
    assert travessia.natureza is NaturezaDaProcedencia.LOCAL
    assert travessia.natureza.publicavel is False

    assets = _assets(travessia)
    conteudo = {
        a.identidade: travessia.bytes_por_slot[e.slot]
        for a, e in zip(assets, D.ENVELOPES)
    }
    lote = LoteDeAssets(canal=CANAL, assets=assets, intencao=INTENCAO)
    producao = ponte.imagens_de_demand_gen(
        lote, conteudo, destino=ponte.Destino.PRODUCAO
    )
    # ⚠️ AGORA O PORTÃO RECUSA, que é o certo. Antes ele PASSAVA com aviso,
    # porque `NAO_DECLARADA` é aceita como dívida declarada — então a peça de um
    # motor 100% local passava em produção enquanto a do `png-local`, que declara
    # corretamente, era recusada. O incentivo estava invertido: não declarar
    # valia mais que declarar.
    assert producao.ok is False
    assert producao.recusas != (), "peça local passou no portão de produção"

    # Contraste: o MESMO caminho com natureza declarada RECUSA. Sem esta metade,
    # o teste acima provaria só que a ponte não recusa nada.
    from dataclasses import replace

    declarados = tuple(
        replace(
            a,
            procedencia=replace(
                a.procedencia, natureza=NaturezaDaProcedencia.LOCAL
            ),
        )
        for a in assets
    )
    lote_local = LoteDeAssets(canal=CANAL, assets=declarados, intencao=INTENCAO)
    conteudo_local = {
        a.identidade: travessia.bytes_por_slot[e.slot]
        for a, e in zip(declarados, D.ENVELOPES)
    }
    recusado = ponte.imagens_de_demand_gen(
        lote_local, conteudo_local, destino=ponte.Destino.PRODUCAO
    )
    assert recusado.ok is False
    assert len(recusado.recusas) >= len(D.ENVELOPES)
