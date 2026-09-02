"""As provas do armazenamento conferido — P17-T06.

Nenhum teste daqui fala com `database.agenciavolc.com.br`, com o Storage do
Supabase nem com a rede. O adaptador remoto é exercido por um duplo de
transporte em memória (`TransporteEmMemoria`), que responde exatamente como o
Storage responde nos quatro casos que importam: bucket ausente, objeto ausente,
leitura divergente e rede caída.

## O que estes testes existem para impedir

A máquina `LOCAL -> UPLOADED_UNVERIFIED -> VERIFIED_OK | VERIFIED_MISMATCH`
existia só no gatilho `criativo_render_artefato_imutavel` de
`supabase/migrations/v11_03_execucao_criativa.sql` — uma migração que ainda não
foi aplicada. Medido em 01/09/2026, `rg "UPLOADED_UNVERIFIED|VERIFIED_MISMATCH"`
não devolvia nenhuma linha de `.py` ou `.ts`. Uma regra que só existe em SQL não
aplicado não protege nada em produção, e mesmo aplicada ela nunca leria um byte
de volta do object storage.

## O mutante que estes testes matam

Uma implementação preguiçosa de `publicar_artefato` faria: upload, hash local de
novo, `VERIFIED_OK`. Ela passa em qualquer teste de caminho feliz que use um
armazenamento honesto. `test_bytes_diferentes_na_releitura_sao_mismatch` e
`test_objeto_ausente_na_releitura_e_divergencia` usam armazenamentos que MENTEM
— um devolve outros bytes, o outro engole a escrita — e só uma implementação que
lê de verdade sobrevive aos dois.
"""

from __future__ import annotations

import json

import dataclasses
import os
from datetime import datetime, timezone

import pytest

from app.criativo import dominio
from app.criativo.armazenamento import (
    ArmazenamentoIndisponivel,
    ArmazenamentoLocal,
    ArmazenamentoSupabase,
    ArquivoRecusado,
    BucketAusente,
    EscritaNaoConferida,
    FalhaDeTransporte,
    ObjetoNaoEncontrado,
    RespostaHTTP,
    chave_de_asset,
    sha256_de,
)
from app.criativo.bancada.armazenamento_verificado import (
    TERMINAIS,
    TRANSICOES,
    ArtefatoNaoVerificado,
    EstadoDoArmazenamento,
    MaquinaDeArmazenamento,
    Publicacao,
    TransicaoDeArmazenamentoProibida,
    chave_canonica,
    estado_de,
    pode_ir,
    publicar_artefato,
)

E = EstadoDoArmazenamento

PNG = b"\x89PNG\r\n\x1a\n" + b"conteudo de uma peca 1x1" * 8


# ═══════════════════════════════════════════════════════════════════════════
# 0. DUPLOS
# ═══════════════════════════════════════════════════════════════════════════


class TransporteEmMemoria:
    """Um Storage do Supabase de mentira, com os mesmos códigos e corpos.

    Os dois 404 são diferentes de propósito: o Storage real responde 404 tanto
    para bucket inexistente quanto para objeto inexistente, e a única coisa que
    os separa é o corpo. Um duplo que devolvesse o mesmo 404 nos dois casos
    esconderia exatamente o defeito que o adaptador precisa não ter.
    """

    def __init__(self, *, buckets: tuple[str, ...] = ("criativos",)) -> None:
        self.buckets = set(buckets)
        self.objetos: dict[str, bytes] = {}
        self.rede_caida = False
        self.engolir_upload = False
        self.corromper_leitura: bytes | None = None
        self.chamadas: list[tuple[str, str]] = []

    # a API que o adaptador usa
    def requisitar(self, metodo: str, url: str, *, headers: dict[str, str],
                   corpo: bytes | None = None, timeout_s: float) -> RespostaHTTP:
        self.chamadas.append((metodo, url))
        if self.rede_caida:
            raise FalhaDeTransporte(f"{metodo} {url} falhou: ConnectError: rede caida")

        caminho = url.split("/storage/v1/", 1)[1]
        if caminho.startswith("bucket/"):
            nome = caminho.removeprefix("bucket/")
            if nome not in self.buckets:
                return RespostaHTTP(404, b'{"error":"Bucket not found"}')
            return RespostaHTTP(200, b'{"name":"criativos"}')

        _, bucket, chave = caminho.split("/", 2)
        if bucket not in self.buckets:
            return RespostaHTTP(404, b'{"error":"Bucket not found"}')

        if metodo == "POST":
            if not self.engolir_upload:
                self.objetos[chave] = corpo or b""
            return RespostaHTTP(200, b'{"Key":"' + chave.encode() + b'"}')

        if chave not in self.objetos:
            return RespostaHTTP(404, b'{"error":"not_found","message":"Object not found"}')
        return RespostaHTTP(200, self.corromper_leitura or self.objetos[chave])

    @property
    def uploads(self) -> list[tuple[str, str]]:
        return [c for c in self.chamadas if c[0] == "POST"]


class LojaQueMente:
    """Armazenamento que aceita a escrita e devolve outra coisa na leitura.

    É o disco cheio, o proxy que trunca e o retry que grava metade — os três com
    a mesma assinatura observável: `guardar` volta sem exceção e o objeto remoto
    não é o objeto local.
    """

    nome = "mentirosa"

    def __init__(self, *, devolve: bytes | None = None, some: bool = False,
                 cai_na_leitura: Exception | None = None) -> None:
        self._devolve = devolve
        self._some = some
        self._cai = cai_na_leitura
        self.guardados: dict[str, bytes] = {}
        self.leituras: list[str] = []

    def conferir_bucket(self) -> None:
        return None

    def guardar(self, chave: str, dados: bytes, mime: str) -> EscritaNaoConferida:
        self.guardados[chave] = dados
        return EscritaNaoConferida(chave, mime, len(dados), sha256_de(dados))

    def ler(self, chave: str) -> bytes:
        self.leituras.append(chave)
        if self._cai is not None:
            raise self._cai
        if self._some:
            raise ObjetoNaoEncontrado(chave)
        return self._devolve if self._devolve is not None else self.guardados[chave]


# ═══════════════════════════════════════════════════════════════════════════
# 1. A MÁQUINA — as mesmas setas do gatilho, e só elas
# ═══════════════════════════════════════════════════════════════════════════

#: Transcrito à mão de `supabase/migrations/v11_03_execucao_criativa.sql`
#: (gatilho `criativo_render_artefato_imutavel`, bloco "A MAQUINA DE ESTADOS DO
#: ARMAZENAMENTO"). Se o gatilho mudar, este literal e o módulo divergem e o
#: teste cai — que é o único jeito de a divergência aparecer sem alguém reler o SQL.
SETAS_DO_GATILHO = {
    E.LOCAL: {E.UPLOADED_UNVERIFIED, E.VERIFIED_OK, E.VERIFIED_MISMATCH},
    E.UPLOADED_UNVERIFIED: {E.VERIFIED_OK, E.VERIFIED_MISMATCH},
    E.VERIFIED_OK: set(),
    E.VERIFIED_MISMATCH: set(),
}


def test_as_setas_sao_exatamente_as_do_gatilho():
    assert {de: set(para) for de, para in TRANSICOES.items()} == SETAS_DO_GATILHO


def test_verified_e_terminal_nos_dois_vereditos():
    """Reescrever o veredito apagaria a auditoria de uma divergência."""
    assert TERMINAIS == {E.VERIFIED_OK, E.VERIFIED_MISMATCH}
    for de in TERMINAIS:
        for para in E:
            assert not pode_ir(de, para), f"{de.value} -> {para.value} deveria ser proibido"


def _maquina_em(estado: EstadoDoArmazenamento) -> MaquinaDeArmazenamento:
    """Leva a máquina até `estado` só por setas legítimas.

    De propósito: um teste que atribuísse `_estado` na mão provaria a recusa de
    uma máquina que nunca existe em produção.
    """
    maquina = MaquinaDeArmazenamento()
    if estado is E.LOCAL:
        return maquina
    maquina.avancar(E.UPLOADED_UNVERIFIED)
    if estado is not E.UPLOADED_UNVERIFIED:
        maquina.avancar(estado)
    return maquina


@pytest.mark.parametrize(
    "de,para",
    [
        (E.UPLOADED_UNVERIFIED, E.LOCAL),          # não volta
        (E.VERIFIED_OK, E.UPLOADED_UNVERIFIED),    # não "desconfere"
        (E.VERIFIED_MISMATCH, E.VERIFIED_OK),      # não vira sucesso
        (E.VERIFIED_OK, E.VERIFIED_MISMATCH),      # nem o contrário
        (E.LOCAL, E.LOCAL),                        # transição que não avança nada
    ],
)
def test_a_maquina_recusa_as_setas_proibidas(de, para):
    maquina = _maquina_em(de)
    assert maquina.estado is de
    with pytest.raises(TransicaoDeArmazenamentoProibida):
        maquina.avancar(para)


def test_o_historico_prova_a_passagem_pelo_nao_conferido():
    maquina = MaquinaDeArmazenamento()
    maquina.avancar(E.UPLOADED_UNVERIFIED)
    maquina.avancar(E.VERIFIED_OK)
    assert maquina.historico == (E.LOCAL, E.UPLOADED_UNVERIFIED, E.VERIFIED_OK)


# ═══════════════════════════════════════════════════════════════════════════
# 2. estado_de — a MESMA regra que o banco aplica sobre as mesmas colunas
# ═══════════════════════════════════════════════════════════════════════════

SHA = sha256_de(PNG)
CARIMBO = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def test_estado_de_classifica_as_quatro_linhas():
    assert estado_de(storage_chave=None, storage_conferido_em=None,
                     storage_hash_conferido=None, sha256_do_artefato=SHA) is E.LOCAL
    assert estado_de(storage_chave="criativos/t/j/1x1_a.png", storage_conferido_em=None,
                     storage_hash_conferido=None,
                     sha256_do_artefato=SHA) is E.UPLOADED_UNVERIFIED
    assert estado_de(storage_chave="criativos/t/j/1x1_a.png", storage_conferido_em=CARIMBO,
                     storage_hash_conferido=SHA,
                     sha256_do_artefato=SHA) is E.VERIFIED_OK
    assert estado_de(storage_chave="criativos/t/j/1x1_a.png", storage_conferido_em=CARIMBO,
                     storage_hash_conferido=sha256_de(b"outra coisa"),
                     sha256_do_artefato=SHA) is E.VERIFIED_MISMATCH


def test_conferencia_sem_endereco_e_linha_impossivel():
    """Regra 3 do gatilho, do lado de cá: não se confere o que não subiu."""
    with pytest.raises(ValueError, match="conferencia sem endereco"):
        estado_de(storage_chave=None, storage_conferido_em=CARIMBO,
                  storage_hash_conferido=SHA, sha256_do_artefato=SHA)


def test_hash_sem_carimbo_e_meia_conferencia_e_levanta():
    with pytest.raises(ValueError, match="carimbo"):
        estado_de(storage_chave="criativos/t/j/1x1_a.png", storage_conferido_em=None,
                  storage_hash_conferido=SHA, sha256_do_artefato=SHA)


def test_carimbo_com_hash_nulo_e_divergencia_e_nao_sucesso():
    """Conferiu e não havia o que hashear: o objeto não estava lá."""
    assert estado_de(storage_chave="criativos/t/j/1x1_a.png", storage_conferido_em=CARIMBO,
                     storage_hash_conferido=None,
                     sha256_do_artefato=SHA) is E.VERIFIED_MISMATCH


# ═══════════════════════════════════════════════════════════════════════════
# 3. publicar_artefato — a releitura é real
# ═══════════════════════════════════════════════════════════════════════════


def test_o_caminho_feliz_passa_por_nao_conferido_antes_de_verificado(tmp_path):
    loja = ArmazenamentoLocal(tmp_path)
    pub = publicar_artefato(loja, chave="criativos/t/j/1x1_a.png", dados=PNG,
                            mime="image/png")
    assert pub.estado is E.VERIFIED_OK
    assert pub.verificado is True
    assert pub.historico == (E.LOCAL, E.UPLOADED_UNVERIFIED, E.VERIFIED_OK)
    assert pub.sha256_remoto == pub.sha256_local == sha256_de(PNG)
    assert pub.bytes_remoto == pub.bytes_local == len(PNG)
    assert pub.conferido_em is not None


def test_a_releitura_acontece_de_verdade():
    """Sem `ler`, não há conferência — e o teste exige a chamada, não o resultado."""
    loja = LojaQueMente()
    pub = publicar_artefato(loja, chave="criativos/t/j/1x1_a.png", dados=PNG,
                            mime="image/png")
    assert loja.leituras == ["criativos/t/j/1x1_a.png"]
    assert pub.verificado is True


def test_bytes_diferentes_na_releitura_sao_mismatch_terminal():
    """MATA O MUTANTE: quem só re-hasheia os bytes locais passa aqui como OK."""
    loja = LojaQueMente(devolve=PNG[:20])
    pub = publicar_artefato(loja, chave="criativos/t/j/1x1_a.png", dados=PNG,
                            mime="image/png")
    assert pub.estado is E.VERIFIED_MISMATCH
    assert pub.verificado is False
    assert pub.bytes_remoto == 20 and pub.bytes_local == len(PNG)
    assert pub.sha256_remoto != pub.sha256_local
    assert "divergencia" in (pub.motivo or "")
    with pytest.raises(ArtefatoNaoVerificado):
        pub.exigir_verificado()


def test_bytes_iguais_com_hash_diferente_seria_impossivel_mas_o_gate_e_duplo():
    """Tamanho igual e conteúdo trocado — o caso que um gate só de bytes perde."""
    trocado = b"X" * len(PNG)
    pub = publicar_artefato(LojaQueMente(devolve=trocado),
                            chave="criativos/t/j/1x1_a.png", dados=PNG, mime="image/png")
    assert pub.estado is E.VERIFIED_MISMATCH
    assert pub.bytes_remoto == pub.bytes_local


def test_objeto_ausente_na_releitura_e_divergencia_sem_hash_inventado():
    pub = publicar_artefato(LojaQueMente(some=True), chave="criativos/t/j/1x1_a.png",
                            dados=PNG, mime="image/png")
    assert pub.estado is E.VERIFIED_MISMATCH
    assert pub.sha256_remoto is None and pub.bytes_remoto is None
    assert "ausente na releitura" in (pub.motivo or "")


def test_rede_caida_na_releitura_nao_vira_mismatch_nem_verificado():
    """A confusão proibida, do lado do veredito: falha não é divergência.

    `VERIFIED_MISMATCH` é terminal. Carimbá-lo por causa de um timeout condenaria
    para sempre um artefato possivelmente íntegro.
    """
    loja = LojaQueMente(cai_na_leitura=ArmazenamentoIndisponivel("timeout"))
    pub = publicar_artefato(loja, chave="criativos/t/j/1x1_a.png", dados=PNG,
                            mime="image/png")
    assert pub.estado is E.UPLOADED_UNVERIFIED
    assert pub.verificado is False
    assert pub.conferido_em is None
    assert pub.sha256_remoto is None
    assert "releitura nao concluida" in (pub.motivo or "")
    with pytest.raises(ArtefatoNaoVerificado):
        pub.exigir_verificado()


def test_o_registro_de_nao_conferido_nao_carimba_conferencia():
    loja = LojaQueMente(cai_na_leitura=ArmazenamentoIndisponivel("timeout"))
    pub = publicar_artefato(loja, chave="criativos/t/j/1x1_a.png", dados=PNG,
                            mime="image/png")
    registro = pub.para_registro()
    assert registro["storage_chave"] == "criativos/t/j/1x1_a.png"
    assert registro["storage_conferido_em"] is None
    assert registro["storage_hash_conferido"] is None


@pytest.mark.parametrize(
    "loja,esperado",
    [
        (LojaQueMente(), E.VERIFIED_OK),
        (LojaQueMente(devolve=b"outra coisa qualquer"), E.VERIFIED_MISMATCH),
        (LojaQueMente(some=True), E.VERIFIED_MISMATCH),
        (LojaQueMente(cai_na_leitura=ArmazenamentoIndisponivel("x")), E.UPLOADED_UNVERIFIED),
    ],
)
def test_o_registro_reclassifica_no_mesmo_estado(loja, esperado):
    """Ida e volta: o que a publicação grava, `estado_de` lê de volta igual.

    É este teste que impede a aplicação e o banco de terem duas noções de
    "verificado" — a dupla verdade que a fila de trabalhos já pagou para matar.
    """
    pub = publicar_artefato(loja, chave="criativos/t/j/1x1_a.png", dados=PNG,
                            mime="image/png")
    assert pub.estado is esperado
    assert estado_de(**pub.para_registro(), sha256_do_artefato=pub.sha256_local) is esperado


def test_publicacao_montada_a_mao_nao_consegue_mentir():
    """`verificado` exige releitura, carimbo e hashes — não um campo `estado`."""
    falsa = Publicacao(estado=E.VERIFIED_OK, chave="criativos/t/j/1x1_a.png",
                       mime="image/png", bytes_local=len(PNG), sha256_local=SHA)
    assert falsa.verificado is False


# ═══════════════════════════════════════════════════════════════════════════
# 4. PREFLIGHT DE BUCKET — recusa fechada, nunca queda para local
# ═══════════════════════════════════════════════════════════════════════════


def test_bucket_ausente_recusa_antes_de_qualquer_upload():
    transporte = TransporteEmMemoria(buckets=())
    loja = ArmazenamentoSupabase("https://exemplo.invalido", "k" * 40,
                                 transporte=transporte)
    with pytest.raises(BucketAusente, match="criativos"):
        publicar_artefato(loja, chave="criativos/t/j/1x1_a.png", dados=PNG,
                          mime="image/png")
    # ⚠️ A parte que importa: nenhum byte foi enviado. Um preflight que recusa
    # DEPOIS do upload já gravou o objeto num bucket que não existe.
    assert transporte.uploads == []


def test_guardar_sozinho_tambem_faz_preflight_antes_de_enviar_bytes(tmp_path):
    """Falhar fechado é a diferença entre "não publiquei" e "publiquei em outro lugar".

    ⚠️ O preflight tem de estar em `guardar()`, e não só em `publicar_artefato`:
    `execucao.py` chama `guardar()` direto. Sem ele, o adaptador só descobriria o
    bucket ausente pelo 404 do PRÓPRIO upload — os bytes já teriam ido para a
    rede, e um dia de retry contra um destino inexistente pareceria "instável".
    """
    transporte = TransporteEmMemoria(buckets=())
    loja = ArmazenamentoSupabase("https://exemplo.invalido", "k" * 40,
                                 transporte=transporte)
    with pytest.raises(BucketAusente):
        loja.guardar("criativos/t/j/1x1_a.png", PNG, "image/png")
    assert transporte.uploads == []
    assert ("GET", "https://exemplo.invalido/storage/v1/bucket/criativos") \
        in transporte.chamadas
    assert list(tmp_path.iterdir()) == []


def test_o_preflight_local_tambem_existe_e_recusa(tmp_path):
    raiz = tmp_path / "sumida"
    loja = ArmazenamentoLocal(raiz)
    raiz.rmdir()
    with pytest.raises(BucketAusente, match="não existe"):
        publicar_artefato(loja, chave="criativos/t/j/1x1_a.png", dados=PNG,
                          mime="image/png")


def test_o_preflight_bem_sucedido_nao_se_repete():
    """Só o SUCESSO é memorizado — memorizar o fracasso recusaria um bucket criado depois."""
    transporte = TransporteEmMemoria()
    loja = ArmazenamentoSupabase("https://exemplo.invalido", "k" * 40,
                                 transporte=transporte)
    loja.conferir_bucket()
    loja.conferir_bucket()
    assert [c for c in transporte.chamadas if "/bucket/" in c[1]] == [
        ("GET", "https://exemplo.invalido/storage/v1/bucket/criativos")
    ]


def test_sem_credencial_o_preflight_nao_afirma_nada():
    loja = ArmazenamentoSupabase("https://exemplo.invalido", "")
    with pytest.raises(ArmazenamentoIndisponivel, match="credencial"):
        loja.conferir_bucket()


# ═══════════════════════════════════════════════════════════════════════════
# 5. O ADAPTADOR REMOTO, EXERCIDO SEM REDE
# ═══════════════════════════════════════════════════════════════════════════


def test_o_adaptador_remoto_completo_verifica():
    transporte = TransporteEmMemoria()
    loja = ArmazenamentoSupabase("https://exemplo.invalido", "k" * 40,
                                 transporte=transporte)
    pub = publicar_artefato(loja, chave="criativos/t/j/1x1_a.png", dados=PNG,
                            mime="image/png")
    assert pub.estado is E.VERIFIED_OK and pub.verificado is True
    assert transporte.uploads  # subiu de verdade
    assert ("GET", "https://exemplo.invalido/storage/v1/object/criativos/criativos/t/j/1x1_a.png") \
        in transporte.chamadas  # e leu de volta


def test_upload_engolido_pelo_remoto_termina_em_mismatch():
    """200 no POST e nada guardado — o 200 que não prova nada, medido."""
    transporte = TransporteEmMemoria()
    transporte.engolir_upload = True
    loja = ArmazenamentoSupabase("https://exemplo.invalido", "k" * 40,
                                 transporte=transporte)
    pub = publicar_artefato(loja, chave="criativos/t/j/1x1_a.png", dados=PNG,
                            mime="image/png")
    assert pub.estado is E.VERIFIED_MISMATCH
    assert "ausente na releitura" in (pub.motivo or "")


def test_releitura_corrompida_no_remoto_termina_em_mismatch():
    transporte = TransporteEmMemoria()
    transporte.corromper_leitura = PNG[:-5]
    loja = ArmazenamentoSupabase("https://exemplo.invalido", "k" * 40,
                                 transporte=transporte)
    pub = publicar_artefato(loja, chave="criativos/t/j/1x1_a.png", dados=PNG,
                            mime="image/png")
    assert pub.estado is E.VERIFIED_MISMATCH
    assert pub.bytes_remoto == len(PNG) - 5


def test_404_de_bucket_nao_e_lido_como_objeto_ausente():
    """Os dois 404 do Storage: só o corpo os separa, e confundi-los é fatal.

    Ler "Bucket not found" como ausência de objeto faria o produto concluir
    "ainda não subiu" e tentar de novo, para sempre, contra um bucket que não
    existe.
    """
    transporte = TransporteEmMemoria(buckets=())
    loja = ArmazenamentoSupabase("https://exemplo.invalido", "k" * 40,
                                 transporte=transporte)
    with pytest.raises(BucketAusente):
        loja.ler("criativos/t/j/1x1_a.png")


def test_objeto_ausente_continua_sendo_objeto_ausente():
    loja = ArmazenamentoSupabase("https://exemplo.invalido", "k" * 40,
                                 transporte=TransporteEmMemoria())
    with pytest.raises(ObjetoNaoEncontrado):
        loja.ler("criativos/t/j/1x1_a.png")
    assert loja.existe("criativos/t/j/1x1_a.png") is False


# ═══════════════════════════════════════════════════════════════════════════
# 6. CONTRAPROVA VERMELHA: rede caída não é ausência
# ═══════════════════════════════════════════════════════════════════════════


def test_rede_caida_nao_vira_objeto_ausente_em_existe():
    """CONTRAPROVA VERMELHA registrada em 01/09/2026, contra o código de HEAD.

        loja = ArmazenamentoSupabase(...)   # com httpx.get levantando ConnectError
        loja.existe("criativos/t/j/1x1_abc.png")
        → VERMELHO: devolveu False — ausencia inventada

    O `except (ObjetoNaoEncontrado, Exception): return False` colapsava falha de
    rede em ausência de objeto. A cláusula era, além de perigosa, inerte:
    `Exception` já cobre `ObjetoNaoEncontrado`, então o primeiro nome só fazia o
    colapso parecer revisado.
    """
    transporte = TransporteEmMemoria()
    transporte.rede_caida = True
    loja = ArmazenamentoSupabase("https://exemplo.invalido", "k" * 40,
                                 transporte=transporte)
    with pytest.raises(ArmazenamentoIndisponivel):
        loja.existe("criativos/t/j/1x1_abc.png")


def test_falha_de_transporte_nao_e_objeto_nao_encontrado():
    """E o tipo prova a distinção: quem trata ausência não pega falha por acidente."""
    assert not issubclass(FalhaDeTransporte, ObjetoNaoEncontrado)
    assert issubclass(FalhaDeTransporte, ArmazenamentoIndisponivel)
    assert not issubclass(ArmazenamentoIndisponivel, KeyError)


def test_chave_invalida_continua_devolvendo_falso_em_existe():
    """A única ausência que `existe()` pode afirmar sem consultar ninguém."""
    loja = ArmazenamentoSupabase("https://exemplo.invalido", "k" * 40,
                                 transporte=TransporteEmMemoria())
    assert loja.existe("../fora.png") is False


def test_erro_5xx_nao_acusa_o_arquivo_do_operador():
    """5xx é falha do servidor; virar `ArquivoRecusado` daria 400 para o operador."""

    class ServidorQuebrado(TransporteEmMemoria):
        def requisitar(self, metodo, url, *, headers, corpo=None, timeout_s):
            if metodo == "POST":
                return RespostaHTTP(503, b"upstream unavailable")
            return super().requisitar(metodo, url, headers=headers, corpo=corpo,
                                      timeout_s=timeout_s)

    loja = ArmazenamentoSupabase("https://exemplo.invalido", "k" * 40,
                                 transporte=ServidorQuebrado())
    with pytest.raises(ArmazenamentoIndisponivel):
        loja.guardar("criativos/t/j/1x1_a.png", PNG, "image/png")


# ═══════════════════════════════════════════════════════════════════════════
# 7. `guardar()` NÃO PODE AFIRMAR CONFERÊNCIA — no tipo, não no comentário
# ═══════════════════════════════════════════════════════════════════════════


def test_guardar_devolve_uma_escrita_que_nao_afirma_conferencia(tmp_path):
    escrita = ArmazenamentoLocal(tmp_path).guardar("criativos/t/j/1x1_a.png", PNG,
                                                   "image/png")
    assert isinstance(escrita, EscritaNaoConferida)
    assert escrita.conferido is False
    assert escrita.sha256_local == sha256_de(PNG)


def test_nao_existe_construtor_capaz_de_afirmar_conferencia():
    """`conferido` é propriedade, não campo: ninguém consegue passá-lo como True."""
    campos = {c.name for c in dataclasses.fields(EscritaNaoConferida)}
    assert "conferido" not in campos
    escrita = EscritaNaoConferida("criativos/t/j/1x1_a.png", "image/png", 10, SHA)
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        escrita.conferido = True  # type: ignore[misc]


def test_o_remoto_tambem_devolve_escrita_nao_conferida():
    loja = ArmazenamentoSupabase("https://exemplo.invalido", "k" * 40,
                                 transporte=TransporteEmMemoria())
    escrita = loja.guardar("criativos/t/j/1x1_a.png", PNG, "image/png")
    assert escrita.conferido is False


# ═══════════════════════════════════════════════════════════════════════════
# 8. A CHAVE CANÔNICA — tenant / job / slot
# ═══════════════════════════════════════════════════════════════════════════


def test_a_chave_e_por_tenant_job_e_slot():
    chave = chave_canonica("tenant-01", "job-77", "9x16", SHA, "png")
    assert chave.startswith("criativos/tenant-01/job-77/9x16_")
    assert chave.endswith(".png")


def test_tenants_diferentes_nunca_compartilham_chave():
    a = chave_canonica("tenant-a", "job-77", "1x1", SHA, "png")
    b = chave_canonica("tenant-b", "job-77", "1x1", SHA, "png")
    assert a != b


def test_identificador_fora_do_alfabeto_e_recusado_e_nao_normalizado():
    """Normalizar identificador de dono cria colisão silenciosa entre tenants.

    O defeito é observável na função antiga, que segue servindo o Estúdio e não
    foi alterada nesta rodada: `chave_de_asset` aplica `.lower()` na chave
    inteira, então `Cliente` e `cliente` caem no MESMO endereço. A chave nova
    recusa em vez de colapsar.
    """
    assert chave_de_asset("Cliente", "job", "1x1", SHA, "png") == \
        chave_de_asset("cliente", "job", "1x1", SHA, "png")
    with pytest.raises(ArquivoRecusado, match="tenant_id"):
        chave_canonica("Cliente", "job-77", "1x1", SHA, "png")


@pytest.mark.parametrize("tenant", ["..", "a/b", "tenant 01", "", "a.b"])
def test_a_chave_canonica_recusa_travessia_e_separador(tenant):
    with pytest.raises(ArquivoRecusado):
        chave_canonica(tenant, "job-77", "1x1", SHA, "png")


def test_a_chave_canonica_recusa_extensao_inventada():
    with pytest.raises(ArquivoRecusado, match="extensao"):
        chave_canonica("tenant-01", "job-77", "1x1", SHA, "png/../x")


def test_a_mesma_peca_ocupa_uma_chave_so():
    assert chave_canonica("t", "j", "1x1", SHA, "png") == \
        chave_canonica("t", "j", "1x1", SHA, "png")
    assert chave_canonica("t", "j", "1x1", SHA, "png") != \
        chave_canonica("t", "j", "1x1", sha256_de(b"outro"), "png")


# ═══════════════════════════════════════════════════════════════════════════
# 9. POLÍTICA ANTES DE ESCRITA, E A GUARDA CONTRA DERIVA DE HASH
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "dados,mime",
    [
        (b"", "image/png"),                     # vazio
        (PNG, "application/x-msdownload"),      # MIME fora da allowlist
        (b"x" * (25 * 1024 * 1024 + 1), "image/png"),  # acima do teto
    ],
)
def test_a_politica_recusa_antes_de_tocar_no_destino(dados, mime):
    transporte = TransporteEmMemoria()
    loja = ArmazenamentoSupabase("https://exemplo.invalido", "k" * 40,
                                 transporte=transporte)
    with pytest.raises(ArquivoRecusado):
        publicar_artefato(loja, chave="criativos/t/j/1x1_a.png", dados=dados,
                          mime=mime)
    assert transporte.chamadas == []  # nem o preflight precisou acontecer


def test_chave_invalida_recusada_antes_do_preflight():
    transporte = TransporteEmMemoria()
    loja = ArmazenamentoSupabase("https://exemplo.invalido", "k" * 40,
                                 transporte=transporte)
    with pytest.raises(ArquivoRecusado):
        publicar_artefato(loja, chave="../fora.png", dados=PNG, mime="image/png")
    assert transporte.chamadas == []


def test_sha256_de_nao_deriva_de_hash_de_conteudo():
    """As duas funções são cópias declaradas; este teste é a guarda contra deriva."""
    assert sha256_de(PNG) == dominio.hash_de_conteudo(PNG)
    assert sha256_de(PNG).startswith("sha256:")


def test_o_arquivo_local_realmente_tem_os_bytes_conferidos(tmp_path):
    """A conferência não é só sobre o objeto na memória do teste."""
    loja = ArmazenamentoLocal(tmp_path)
    pub = publicar_artefato(loja, chave="criativos/t/j/1x1_a.png", dados=PNG,
                            mime="image/png")
    em_disco = (tmp_path / "criativos/t/j/1x1_a.png").read_bytes()
    assert sha256_de(em_disco) == pub.sha256_remoto
    assert not any(p.suffix == ".parcial" for p in tmp_path.rglob("*"))
    assert os.access(tmp_path, os.R_OK)


# ─────────────────────────────────────────────────────────────────────────────
# O Estúdio não diz "pronta" sobre bytes que ninguém releu
# ─────────────────────────────────────────────────────────────────────────────


def test_o_estudio_publica_relendo_e_nao_apenas_guardando(tmp_path) -> None:
    """⚠️ Achado do revisor adversarial: o Executor marcava peça `pronta` e job
    `succeeded` depois de três `guardar()`, com ZERO `ler()`.

    "Voltou sem exceção" virava "está lá, íntegro" — o colapso de
    `arquivo escrito` em `arquivo verificado` que este projeto proíbe. Um 200
    prova que o servidor ACEITOU os bytes, não que os guardou inteiros.

    Esta prova é sobre a CHAMADA: o caminho de publicação do Executor tem de
    passar por `publicar_artefato`, que sobe E relê. Ela mede contando as
    leituras, e não lendo o código.
    """
    import inspect

    from app.criativo import execucao

    fonte = inspect.getsource(execucao)
    assert "publicar_artefato(" in fonte, (
        "o Executor voltou a guardar sem reler"
    )
    # E `guardar()` sozinho não pode mais decidir nada: o que ele devolve não
    # sabe afirmar conferência.
    assert "publicacao.estado is not EstadoDoArmazenamento.VERIFIED_OK" in fonte, (
        "o Executor não checa o veredito da conferência"
    )


def test_uma_loja_que_devolve_bytes_diferentes_impede_o_pronta(tmp_path) -> None:
    """A releitura precisa PODER reprovar — senão ela é cerimônia.

    Uma loja que aceita o upload e devolve outra coisa na leitura leva a
    publicação a `VERIFIED_MISMATCH`, que é terminal e não é `pronta`.
    """
    from app.criativo.bancada.armazenamento_verificado import (
        EstadoDoArmazenamento,
        publicar_artefato,
    )

    class LojaQueDevolveOutraCoisa:
        nome = "traiçoeira"

        def __init__(self) -> None:
            self.leituras = 0

        def conferir_bucket(self) -> None:
            return None

        def guardar(self, chave: str, dados: bytes, mime: str):
            from app.criativo.armazenamento import EscritaNaoConferida
            import hashlib

            return EscritaNaoConferida(
                chave=chave, mime=mime, bytes_escritos=len(dados),
                sha256_local=hashlib.sha256(dados).hexdigest(),
            )

        def ler(self, chave: str) -> bytes:
            self.leituras += 1
            return b"outra coisa completamente"

    loja = LojaQueDevolveOutraCoisa()
    dados = b"\x89PNG\r\n\x1a\n" + b"conteudo real" * 8
    pub = publicar_artefato(
        loja, chave="criativos/p/j/1x1_abc.png", dados=dados, mime="image/png"
    )
    assert loja.leituras == 1, "não houve releitura: o veredito seria vazio"
    assert pub.estado is EstadoDoArmazenamento.VERIFIED_MISMATCH
    assert pub.sha256_remoto is not None and pub.sha256_remoto != pub.sha256_local
    assert pub.motivo, "um estado ruim sem motivo obriga quem lê a adivinhar"


# ─────────────────────────────────────────────────────────────────────────────
# A fronteira pública: o insumo cru não sai (bloqueador 2)
# ─────────────────────────────────────────────────────────────────────────────

_SENTINELA = "SEGREDO-DO-CLIENTE-QUE-NAO-PODE-SAIR-7f3a"


def test_a_sentinela_atravessa_a_producao_e_some_de_todo_json_publico(tmp_path) -> None:
    """⚠️ Bloqueador 2. `parametros` e `insumo` saíam CRUS pelo recibo público.

    A prova não olha campo por campo: ela põe uma sentinela no briefing, deixa a
    produção acontecer de verdade, e depois procura a sentinela no JSON
    serializado INTEIRO. Conferir campos nomeados deixaria passar o campo que
    ninguém lembrou de nomear.

    E ela exige as duas metades: a sentinela tem de estar DENTRO (senão a prova
    passaria porque o material nunca chegou lá) e FORA (que é o que se quer).
    """
    import hashlib
    import json

    from app.criativo.bancada.contrato import Encomenda, EstadoDoTrabalho, SaidaPedida
    from app.criativo.bancada.deposito import DepositoDeTrabalhos
    from app.criativo.bancada.operario import Operario
    from app.criativo.bancada.adaptadores.png_local import MotorPngLocal
    from app.routers.criativos_execucao import _recibo_dto, _trabalho_dto

    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    encomenda = Encomenda(
        receita_id="r", tenant_id="t", motor_slug=MotorPngLocal.slug,
        modo_slug="ensaio-local", finalidade_slug="google_display", seed=3,
        saidas=(SaidaPedida("1x1", 64, 64, "imagem", "image/png"),),
        parametros={"insumo": _SENTINELA, "titulo": _SENTINELA, "canal": "meta"},
    )
    deposito.enfileirar(encomenda)
    op = Operario(deposito, {MotorPngLocal.slug: MotorPngLocal()},
                  tmp_path / "t", nome="op-sentinela")
    final = op.trabalhar_uma_vez()
    assert final.estado is EstadoDoTrabalho.RENDERED, final.falha

    # METADE 1 — a sentinela ATRAVESSOU a produção. Sem isto, o resto é vazio.
    assert _SENTINELA in json.dumps(final.recibo, default=str), (
        "a sentinela nem chegou ao recibo interno: a prova não prova nada"
    )
    assert final.encomenda.parametros["insumo"] == _SENTINELA

    # METADE 2 — e some de todo JSON público.
    publico = json.dumps(
        {"trabalho": _trabalho_dto(final), "recibo": _recibo_dto(final.recibo)},
        default=str, ensure_ascii=False,
    )
    assert _SENTINELA not in publico, "o insumo cru saiu pela API"

    # E o que saiu no lugar identifica sem revelar.
    dto = _recibo_dto(final.recibo)
    assert dto["parametros"]["hash"].startswith("sha256:")
    assert dto["parametros"]["campos"] == {"canal": "meta"}
    assert dto["parametros"]["retidos"]["insumo"] == "retido_texto_livre"
    assert dto["parametros"]["retidos"]["titulo"] == "retido_texto_livre"


def test_a_idempotencia_e_a_assinatura_nao_mudam_com_a_fronteira(tmp_path) -> None:
    """A sanitização é da SAÍDA. Ela não pode tocar a identidade do trabalho.

    Se o hash público fosse calculado de um dicionário já podado, dois pedidos
    diferentes colidiriam; e se a assinatura determinista visse o resumo em vez
    dos parâmetros, ela deixaria de responder "o motor repetiu?".
    """
    from app.criativo.bancada.contrato import Encomenda, SaidaPedida
    from app.criativo.bancada.fronteira_publica import hash_dos_parametros

    def pedido(insumo: str) -> Encomenda:
        return Encomenda(
            receita_id="r", tenant_id="t", motor_slug="m", modo_slug="mo",
            finalidade_slug="f", seed=1,
            saidas=(SaidaPedida("1x1", 10, 10, "imagem", "image/png"),),
            parametros={"insumo": insumo, "canal": "meta"},
        )

    a, b = pedido("briefing A"), pedido("briefing B")
    # A identidade interna continua distinguindo os dois.
    assert a.chave_de_idempotencia() != b.chave_de_idempotencia()
    # E o hash público também — ele deriva do pedido INTEIRO, não do resumo.
    assert hash_dos_parametros(a.parametros) != hash_dos_parametros(b.parametros)
    # Mesmo pedido, mesmo hash: ele identifica.
    assert hash_dos_parametros(a.parametros) == hash_dos_parametros(pedido("briefing A").parametros)


def test_ausencia_nao_vira_string_vazia_nem_hash_vira_prompt_sanitizado() -> None:
    """Três estados de ausência, e eles não se confundem."""
    from app.criativo.bancada.fronteira_publica import resumo_do_insumo, resumo_publico

    assert resumo_do_insumo(None) == {"estado": "ausente", "hash": None}
    assert resumo_do_insumo("   ") == {"estado": "vazio", "hash": None}
    retido = resumo_do_insumo("tem conteudo")
    assert retido["estado"] == "retido" and retido["hash"].startswith("sha256:")
    # Nenhum dos três devolve string vazia fingindo de texto.
    assert all(r.get("texto") is None for r in
               (resumo_do_insumo(None), resumo_do_insumo(""), retido))

    r = resumo_publico({"insumo": "x", "titulo": "", "apoio": None, "canal": "meta"})
    assert r["retidos"] == {
        "apoio": "ausente", "insumo": "retido_texto_livre", "titulo": "vazio",
    }
    # O hash não se chama "prompt sanitizado" nem finge ser legível.
    assert "prompt" not in json.dumps(r) and "sanitizado" not in json.dumps(r)
