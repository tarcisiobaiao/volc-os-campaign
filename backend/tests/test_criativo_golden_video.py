"""A travessia produtiva de VÍDEO, do briefing ao pacote por destino.

## O que este arquivo prova, e por que ele existe separado

`test_criativo_golden_imagem.py` prova a mesma espinha para imagem, e prova bem.
Ele não podia provar vídeo por dois motivos que eram fatos, não escolhas: não
havia motor de vídeo — os dois motores registrados recusavam `midia != "imagem"`
— e `_MIMES_MENSURAVEIS` cobria só png/jpeg/gif, de modo que um mp4 caía em
`SKIPPED` não-bloqueante e chegava a `rendered` sem que ninguém abrisse o arquivo.

A travessia aqui é a inteira, e cada elo é afirmado sobre o objeto produtivo:

    briefing → job na fila → claim exclusivo → worker FORA do processo web
    → motor real (Remotion hermético) → bytes reais → medição por ffprobe
    → armazenamento → RELEITURA do armazenamento → conferência de bytes e sha256
    → validação por destino → aprovação humana → biblioteca → pacote de entrega

⚠️ O worker roda como SUBPROCESSO de verdade (`subprocess.run`), e não como
chamada de função com outro nome. O aceite de P17-T05 é sobre o trabalho sair do
processo web; um teste que chamasse `operario.executar()` no mesmo interpretador
provaria a função, não o aceite.

## Por que os `skip` são poucos e nomeados

Render de vídeo precisa de `node`, do runtime Remotion instalado e de `ffprobe`.
Onde faltarem, o teste pula com o motivo — e a ausência do motivo é o que
transforma um skip em silêncio. Não há caminho aqui em que a falta de uma
ferramenta produza VERDE.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

RAIZ_BACKEND = Path(__file__).resolve().parents[1]
RAIZ_REPO = RAIZ_BACKEND.parent
sys.path.insert(0, str(RAIZ_BACKEND))
sys.path.insert(0, str(RAIZ_REPO))

from app.criativo.bancada.adaptadores import remotion as adaptador_remotion  # noqa: E402
from app.criativo.bancada.contrato import (  # noqa: E402
    Ausencia,
    Encomenda,
    EstadoDoTrabalho,
    SaidaPedida,
)
import volc_ads.criativo.destinos as D  # noqa: E402
from volc_ads.criativo.contrato import NaturezaDaProcedencia  # noqa: E402

ENVELOPE = "organico-reels-video-9x16"

#: Briefing com material que NÃO pode sair pela API nem aparecer cru no recibo:
#: telefone, e-mail e valor. Ele atravessa a produção inteira, e o teste cobra as
#: duas metades — o hash do original preservado, e nenhum dos três no texto.
BRIEFING = (
    "Matriculas 2027 abertas no Colegio Positivo. "
    "Fale com o time pelo (41) 99999-8888 ou matriculas@exemplo.test. "
    "Mensalidade a partir de R$ 2.400,00 com bolsa por merito."
)


def _falta_ferramenta() -> str | None:
    if shutil.which("node") is None:
        return "node ausente nesta maquina"
    if shutil.which("ffprobe") is None or shutil.which("ffmpeg") is None:
        return "ffmpeg/ffprobe ausentes nesta maquina"
    runtime = adaptador_remotion.runtime()
    if not (runtime / "node_modules").is_dir():
        return f"runtime Remotion sem node_modules em {runtime}"
    return None


MOTIVO = _falta_ferramenta()
pytestmark = pytest.mark.skipif(MOTIVO is not None, reason=MOTIVO or "")


@dataclass
class Travessia:
    trabalho: object
    recibo: dict
    raiz: Path


def _encomenda(tenant: str = "positivo", seed: int = 20260902) -> Encomenda:
    return Encomenda(
        receita_id="reels-matricula-2027",
        tenant_id=tenant,
        motor_slug=adaptador_remotion.SLUG,
        modo_slug="video-vertical",
        finalidade_slug="captacao",
        seed=seed,
        saidas=(
            SaidaPedida(
                slot=D.envelope_de(ENVELOPE).slot,
                largura=1080, altura=1920, midia="video", mime="video/mp4",
            ),
        ),
        parametros={
            "insumo": BRIEFING,
            "apoio": "Turmas com vagas limitadas.",
            "assinatura": "COLEGIO POSITIVO",
            "duracao_s": 2.0,
            "fps": 24,
            "brand_pack_id": "positivo-2027",
            "canal": "organico",
        },
    )


@pytest.fixture(scope="module")
def travessia(tmp_path_factory) -> Travessia:
    """Enfileira, roda o worker EM OUTRO PROCESSO, e devolve o que sobrou.

    O ambiente do subprocesso aponta `CRIATIVO_BANCADA_DIR` e
    `CRIATIVO_STORAGE_DIR` para diretórios descartáveis desta sessão: o teste não
    escreve na bancada da máquina e não lê a de ninguém.
    """
    raiz = tmp_path_factory.mktemp("bancada-video")
    ambiente = dict(os.environ)
    ambiente.update({
        "CRIATIVO_BANCADA_DIR": str(raiz / "bancada"),
        "CRIATIVO_STORAGE_DIR": str(raiz / "storage"),
        "CRIATIVO_DEPOSITO": "sqlite",
        "PYTHONPATH": os.pathsep.join([str(RAIZ_BACKEND), str(RAIZ_REPO)]),
    })

    # 1. Enfileirar acontece NESTE processo, como a rota faria.
    from app.criativo.bancada.porta import escolher_deposito

    (raiz / "bancada").mkdir(parents=True, exist_ok=True)
    deposito = escolher_deposito(caminho_sqlite=raiz / "bancada" / "fila.db")
    trabalho, criado = deposito.enfileirar(_encomenda())
    assert criado is True, "a fila descartavel nasceu com o trabalho ja dentro"
    assert trabalho.estado is EstadoDoTrabalho.QUEUED

    # 2. O worker é OUTRO PROCESSO. `--ate-esvaziar` termina sozinho.
    saida = subprocess.run(
        [sys.executable, "-m", "app.criativo.bancada.worker", "--ate-esvaziar"],
        cwd=str(RAIZ_BACKEND), env=ambiente, capture_output=True, text=True,
        timeout=900,
    )
    feito = deposito.por_id(trabalho.id)
    if feito is None or feito.estado is not EstadoDoTrabalho.RENDERED:
        pytest.fail(
            "o worker nao levou o trabalho a rendered: "
            f"estado={getattr(feito, 'estado', None)} "
            f"falha={getattr(feito, 'falha', None)} "
            f"stderr={saida.stderr[-800:]}"
        )
    return Travessia(trabalho=feito, recibo=feito.recibo, raiz=raiz)


# ── o processo ───────────────────────────────────────────────────────────────


def test_o_worker_produziu_fora_do_processo_web(travessia):
    """Quem assinou o recibo é um `worker-<pid>`, e o pid não é o deste teste."""
    produzido_por = travessia.recibo["produzido_por"]
    assert produzido_por.startswith("worker-"), produzido_por
    pid = int(produzido_por.removeprefix("worker-"))
    assert pid != os.getpid(), "o recibo foi assinado dentro do processo do teste"


def test_o_artefato_existe_e_e_um_mp4_com_video_e_audio(travessia):
    artefatos = travessia.recibo["artefatos"]
    assert len(artefatos) == 1
    a = artefatos[0]
    assert a["mime"] == "video/mp4"
    assert a["bytes_"] > 10_000, "um mp4 de 2s nao cabe em 10 KB"
    caminho = Path(a["caminho"])
    assert caminho.is_file()
    assert caminho.stat().st_size == a["bytes_"]

    v = a["video"]
    assert v is not None, "o artefato de video chegou sem medida de video"
    assert v["codec_video"] == "h264"
    assert v["codec_audio"] == "aac", "peca muda: a faixa de audio nao entrou"
    assert (v["largura"], v["altura"]) == (1080, 1920)
    assert (v["fps_num"], v["fps_den"]) == (24, 1)
    # 2,0 s a 24 fps = 48 quadros CONTADOS, não estimados pelo cabeçalho.
    assert v["quadros"] == 48
    assert v["duracao_s"] > 1.9


def test_a_dimensao_foi_medida_do_arquivo_e_nao_declarada(travessia):
    """⚠️ Antes desta fatia `video/mp4` não estava em `_MIMES_MENSURAVEIS`, e o
    gate de dimensão saía `SKIPPED` — um mp4 de qualquer tamanho passava."""
    gates = {v["gate"]: v for v in travessia.recibo["validacoes"]}
    dimensao = gates["dimensao"]
    assert dimensao["resultado"] == "PASS"
    assert dimensao["detalhe"]["medido"] == [1080, 1920]
    assert "SKIPPED" not in dimensao["resultado"]


def test_os_gates_do_motor_entraram_no_recibo(travessia):
    gates = {v["gate"]: v for v in travessia.recibo["validacoes"]}
    assert "quadros_conferem" in gates
    assert gates["quadros_conferem"]["resultado"] == "PASS"
    assert gates["quadros_conferem"]["detalhe"]["contados_no_arquivo"] == 48
    assert gates["fps"]["resultado"] == "PASS"
    # A fração inteira, e não o float: `30000/1001` arredondado volta como outra
    # coisa, e é isso que dessincroniza áudio num corte longo.
    assert gates["fps"]["detalhe"]["fps_num"] == 24
    assert gates["fps"]["detalhe"]["fps_den"] == 1
    assert "safe_zone" in gates


def test_o_render_foi_hermetico_e_quem_disse_isso_foi_o_kernel(travessia):
    """⚠️ REESCRITO depois da revisão adversarial, e a versão anterior era um
    falso verde de dois jeitos.

    Primeiro: o gate saía `PASS` porque `/usr/bin/sandbox-exec` e o perfil
    EXISTEM no disco — afirmando que o sandbox foi APLICADO a partir de dois
    arquivos estarem lá. E este teste conferia a MESMA condição usada para
    produzir o gate, o que torna a asserção circular.

    Segundo: onde o sandbox não existe, o gate saía `SKIPPED` não-bloqueante e o
    trabalho chegava a `rendered` com rede liberada. Hermetismo deixava de ser
    invariante do motor para virar propriedade do sistema operacional de quem
    rodou.

    Agora o veredito vem do KERNEL, respondendo dentro do processo que
    renderizou, e o gate é BLOQUEANTE: sem prova de bloqueio o trabalho falha,
    a menos que alguém dispense o hermetismo por variável nomeada.
    """
    gate = {v["gate"]: v for v in travessia.recibo["validacoes"]}["render_sem_rede"]
    assert gate["resultado"] == "PASS", gate
    assert gate["bloqueante"] is True
    # `EPERM`/`EACCES` é o kernel dizendo "sem permissão". `ENETUNREACH` e
    # `ECONNREFUSED` uma máquina sem rede também produz, e provar hermetismo com
    # ausência de rede prova outra coisa.
    assert gate["detalhe"]["resposta_do_kernel"] in ("EPERM", "EACCES"), gate


def test_o_gate_de_hermetismo_reprova_quando_nao_ha_prova_de_bloqueio():
    """CONTRAPROVA VERMELHA do teste acima, e ela não precisa de render.

    Um relatório sem sonda — que é exatamente o que uma máquina sem
    `sandbox-exec` produz — tem de FALHAR o gate bloqueante, e não virar
    `SKIPPED`."""
    import json as _json
    import tempfile

    motor = adaptador_remotion.MotorRemotion()
    with tempfile.TemporaryDirectory() as d:
        Path(d, adaptador_remotion.RELATORIO).write_text(
            _json.dumps({"sandbox": False, "rede": None, "por_slot": {}}), "utf-8"
        )
        gates = {g.gate: g for g in motor.gates(_encomenda(), d)}
    assert gates["render_sem_rede"].resultado == "FAIL"
    assert gates["render_sem_rede"].bloqueante is True

    # E o escape existe, é explícito e fica NO RECIBO — não é um silêncio.
    with tempfile.TemporaryDirectory() as d:
        Path(d, adaptador_remotion.RELATORIO).write_text(
            _json.dumps({"sandbox": False,
                         "rede": {"saiu": True, "codigo": "CONECTOU"},
                         "por_slot": {}}), "utf-8"
        )
        os.environ["CRIATIVO_PERMITIR_RENDER_COM_REDE"] = "1"
        try:
            gates = {g.gate: g for g in motor.gates(_encomenda(), d)}
        finally:
            os.environ.pop("CRIATIVO_PERMITIR_RENDER_COM_REDE", None)
    assert gates["render_sem_rede"].resultado == "WARN"
    assert gates["render_sem_rede"].bloqueante is False
    assert "CRIATIVO_PERMITIR_RENDER_COM_REDE" in gates["render_sem_rede"].detalhe["motivo"]


def test_um_erro_de_rede_qualquer_nao_prova_bloqueio():
    """`ENETUNREACH` é o que uma máquina sem rede devolve. Aceitá-lo como prova
    de sandbox faria toda máquina offline parecer hermética."""
    import json as _json
    import tempfile

    motor = adaptador_remotion.MotorRemotion()
    with tempfile.TemporaryDirectory() as d:
        Path(d, adaptador_remotion.RELATORIO).write_text(
            _json.dumps({"sandbox": True,
                         "rede": {"saiu": False, "codigo": "ENETUNREACH"},
                         "por_slot": {}}), "utf-8"
        )
        gates = {g.gate: g for g in motor.gates(_encomenda(), d)}
    assert gates["render_sem_rede"].resultado == "FAIL", gates["render_sem_rede"]


# ── o recibo ─────────────────────────────────────────────────────────────────


def test_o_recibo_carrega_a_procedencia_inteira(travessia):
    p = travessia.recibo["procedencia"]
    assert p["receita_id"] == "reels-matricula-2027"
    assert p["tenant_id"] == "positivo"
    assert p["modo_slug"] == "video-vertical"
    assert p["finalidade_slug"] == "captacao"
    assert p["natureza"] == NaturezaDaProcedencia.LOCAL.value
    assert p["brand_pack"]["valor"] == "positivo-2027"
    # Provider e modelo NÃO existem para um motor local — e a ausência é nomeada,
    # não vazia: `nao_aplicavel` é uma resposta, `None` é a falta dela.
    assert p["provider"]["ausencia"] == Ausencia.NAO_APLICAVEL.value
    assert p["modelo"]["ausencia"] == Ausencia.NAO_APLICAVEL.value
    assert p["licenca"]["valor"]
    assert p["disclosure"]["valor"] is False


def test_o_insumo_no_recibo_e_sanitizado_e_auditavel(travessia):
    """Não é o texto cru e não é só um hash: é texto legível SEM os
    identificadores, mais o hash do original completo."""
    import hashlib

    insumo = travessia.recibo["insumo"]
    assert insumo["estado"] == "sanitizado"
    texto = insumo["texto"]
    assert texto, "o recibo interno ficou sem texto para auditar"
    # As três coisas que não podem sobreviver.
    assert "99999-8888" not in texto
    assert "matriculas@exemplo.test" not in texto
    assert "2.400,00" not in texto
    # E o que tem de sobreviver: o assunto, para o auditor saber do que se trata.
    assert "Colegio Positivo" in texto
    assert {"<telefone>", "<email>", "<valor>"} <= set(insumo["substituicoes"])
    # O hash é do ORIGINAL COMPLETO — é ele que responde "é o mesmo briefing?".
    assert insumo["hash_do_completo"] == hashlib.sha256(
        BRIEFING.encode("utf-8")
    ).hexdigest()


def test_os_hashes_de_entrada_cobrem_fonte_e_leito(travessia):
    """O que entrou no render e pode mudar o pixel sem mudar o pedido."""
    hashes = travessia.recibo["hashes_de_entrada"]
    assert any(k.startswith("fonte:") for k in hashes), hashes
    assert any(k.startswith("leito:") for k in hashes), hashes
    assert all(len(v) == 64 for v in hashes.values())


def test_o_custo_nao_apurado_nao_e_custo_zero(travessia):
    """⚠️ Os dois campos de custo eram literais `None` sem produtor nenhum.
    Agora têm produtor E razão nomeada — e a razão de um motor local não é a
    mesma de um motor pago que ninguém apurou."""
    custo = travessia.recibo["custo"]
    assert custo["estimado_usd"]["valor"] is None
    assert custo["estimado_usd"]["ausencia"] == Ausencia.SEM_CUSTO_DE_PROVIDER.value
    assert custo["real_usd"]["ausencia"] == Ausencia.SEM_CUSTO_DE_PROVIDER.value
    assert travessia.recibo["custo_estimado_usd"] is None
    assert travessia.recibo["custo_estimado_usd"] != 0


def test_o_audio_foi_medido_em_numeros_e_nao_em_pass_fail(travessia):
    """⚠️ `MedidaDeAudio` era estrutura MORTA: nenhum motor implementava
    `medir_audio`, e a v11_03 reservou colunas numéricas que nasceriam
    permanentemente nulas."""
    audio = travessia.recibo["audio"]
    assert audio is not None, "o áudio continua não medido"
    assert travessia.recibo["audio_ausente_porque"] is None
    assert isinstance(audio["lufs_integrado"], (int, float))
    assert isinstance(audio["true_peak_dbtp"], (int, float))
    assert audio["alvo_lufs"] is not None
    assert audio["tolerancia_lufs"] is not None
    assert "ebur128" in audio["fonte"]


def test_o_recibo_carrega_tentativa_duracao_e_enquadramento(travessia):
    r = travessia.recibo
    assert r["tentativa"] == 1
    assert r["duracao_do_trabalho_s"] > 0, "duração do trabalho não foi medida"
    enq = r["artefatos"][0]["enquadramento"]
    assert enq is not None
    # Dimensão NATIVA ao lado da ALVO: `1080x1920` significava a mesma coisa
    # quando o motor desenhou nesse tamanho e quando alguém esticou.
    assert (enq["largura_nativa"], enq["altura_nativa"]) == (1080, 1920)
    assert (enq["largura_alvo"], enq["altura_alvo"]) == (1080, 1920)
    assert enq["operacao"] == "nenhuma"


def test_o_recibo_nao_carrega_o_briefing_cru_em_lugar_nenhum(travessia):
    """SENTINELA. `parametros` continua completo dentro do recibo interno porque
    a idempotência e a assinatura dependem dele — então a pergunta certa não é
    "o texto sumiu?", e sim "o campo que se chama insumo ainda é o texto cru?"."""
    assert travessia.recibo["insumo"]["texto"] != BRIEFING
    # E o que a API pública devolve não pode ter nada disso.
    from app.criativo.bancada.fronteira_publica import resumo_publico

    publico = json.dumps(resumo_publico(travessia.recibo["parametros"]))
    assert "99999-8888" not in publico
    assert "matriculas@exemplo.test" not in publico
    assert BRIEFING not in publico


# ── armazenamento ────────────────────────────────────────────────────────────


def test_o_artefato_subiu_e_foi_RELIDO_do_armazenamento(travessia):
    """⚠️ `VERIFIED_OK` só existe DEPOIS de uma releitura que conferiu bytes E
    sha256. Nada aqui promove estado por ter feito upload."""
    storage = travessia.recibo["storage"]
    assert len(storage) == 1
    s = storage[0]
    assert s["estado"] == "VERIFIED_OK", s
    assert s["chave"]["valor"], "artefato verificado sem chave"
    assert s["sha256_relido"]["valor"] == travessia.recibo["artefatos"][0]["sha256"]
    assert s["bytes_relidos"]["valor"] == travessia.recibo["artefatos"][0]["bytes_"]
    assert s["lido_em"], "não há carimbo de quando a releitura aconteceu"


def test_a_chave_de_armazenamento_e_a_canonica_por_tenant(travessia):
    """`criativos/<tenant>/<job>/<slot>__<hash>.<ext>` — e o delimitador é DOIS
    underscores, que é o que `criativo_storage_chave_valida` da v11_03 exige.
    Com um só, o prefixo de um slot casaria com o objeto de outro."""
    import re

    chave = travessia.recibo["storage"][0]["chave"]["valor"]
    assert chave.startswith("criativos/positivo/")
    slot = D.envelope_de(ENVELOPE).slot
    prefixo = f"criativos/positivo/{travessia.trabalho.id}/{slot}__"
    assert chave.startswith(prefixo), chave
    sufixo = chave[len(prefixo):]
    assert re.fullmatch(r"[A-Za-z0-9_.-]+", sufixo), sufixo
    assert ".." not in chave and "//" not in chave and not chave.endswith("/")


def test_o_arquivo_no_armazenamento_tem_os_mesmos_bytes(travessia):
    """A releitura acima é do produto; esta é do teste, e as duas têm de
    concordar. Um `VERIFIED_OK` que só o produto consegue reproduzir não é
    verificação: é auto-declaração com outro nome."""
    import hashlib

    chave = travessia.recibo["storage"][0]["chave"]["valor"]
    guardado = travessia.raiz / "storage" / chave
    assert guardado.is_file(), guardado
    dados = guardado.read_bytes()
    assert hashlib.sha256(dados).hexdigest() == travessia.recibo["artefatos"][0]["sha256"]


# ── destino, aprovação e pacote ──────────────────────────────────────────────


def test_a_validacao_por_destino_saiu_do_arquivo_medido(travessia):
    destinos = {d["slug"]: d for d in travessia.recibo["destinos"]}
    assert set(destinos) == set(D.DESTINOS)
    # O vídeo 1080x1920 casa o envelope de vídeo do orgânico, e SÓ ele.
    # A peça casa o envelope de VÍDEO do orgânico. Ela não completa o lote —
    # falta a peça de imagem 9:16 — e as duas coisas são ditas separadamente.
    assert destinos["organico"]["veredito"] == "serve_parcialmente"
    # `asdict` transforma a tupla em lista no recibo serializado.
    assert list(destinos["organico"]["motivos"]) == [
        "envelope nao produzido: organico-reels-9x16",
    ]
    # E não casa envelope de imagem nenhum, mesmo com geometria igual.
    assert destinos["meta"]["veredito"] == "nao_serve"
    assert destinos["google"]["veredito"] == "nao_serve"
    assert destinos["google"]["motivos"]


def test_a_aprovacao_nasce_aguardando_e_nao_aprovada(travessia):
    """⚠️ Um recibo que nascesse `aprovado` faria o operário aprovar em nome de
    uma pessoa — e a aprovação humana existe porque a máquina não pode responder
    isso."""
    ap = travessia.recibo["aprovacao"]
    assert ap["estado"] == "aguardando"
    assert ap["por"] is None
    assert ap["em"] is None


def test_o_pacote_por_destino_se_monta_e_nao_publica(travessia):
    """O pacote é o último elo desta missão. Publicar é ato separado, e o campo
    `publicacao_automatica` existe para que a ausência de publicação seja um FATO
    conferível, e não uma propriedade do silêncio."""
    a = travessia.recibo["artefatos"][0]
    s = travessia.recibo["storage"][0]
    variante = D.VarianteEntregue(
        envelope_slug=ENVELOPE,
        conteudo_hash="sha256:" + a["sha256"],
        mime=a["mime"],
        largura=a["largura"],
        altura=a["altura"],
        bytes_totais=a["bytes_"],
        adaptacao=D.MESTRE,
        chave_de_armazenamento=s["chave"]["valor"],
        # O recibo guarda o hash puro; `VarianteEntregue` exige o algoritmo
        # declarado. A conversão é de uma linha e explícita — melhor do que duas
        # representações convivendo dentro do mesmo recibo.
        relido_hash="sha256:" + s["sha256_relido"]["valor"],
    )
    pacotes = {
        p.destino: p
        for p in D.montar_pacotes([variante], natureza=NaturezaDaProcedencia.LOCAL)
    }
    organico = pacotes[D.ORGANICO]
    assert variante.na_medida is True
    assert variante.armazenamento_verificado is True
    assert ENVELOPE in {v.envelope_slug for v in organico.variantes}
    # O pacote do orgânico ainda espera a peça de IMAGEM 9:16, e diz qual falta.
    assert organico.faltando == ("organico-reels-9x16",)
    # Peça de motor local não vira anúncio, e o pacote diz isso sem rodeio.
    assert organico.publicavel is False
    assert D.PacoteDeDestino.publicacao_automatica is False
    corpo = json.dumps([p.para_json() for p in pacotes.values()])
    assert '"publicacao_automatica": false' in corpo


def test_nenhum_caminho_desta_travessia_publica_em_plataforma(travessia):
    """SENTINELA. Nenhuma URL de plataforma aparece no recibo inteiro."""
    corpo = json.dumps(travessia.recibo).lower()
    for proibido in ("googleads.googleapis", "graph.facebook", "youtube.com/upload",
                     "business.instagram", "tiktokapis"):
        assert proibido not in corpo, proibido


# ── a fronteira pública ──────────────────────────────────────────────────────


def test_o_dto_publico_leva_a_procedencia_e_NAO_leva_o_texto_do_briefing(travessia):
    """SENTINELA DUPLA, e as duas metades importam.

    A primeira: o contrato produtivo tem de CHEGAR à tela — procedência, storage,
    destino, aprovação. Um recibo rico que morre no servidor não fecha lacuna
    nenhuma.

    A segunda: o texto sanitizado NÃO pode sair. Ele é conteúdo do cliente, e
    `fronteira_publica` já escreveu a regra — texto livre não sai "nem truncado:
    um prefixo de briefing ainda é briefing". Sanitizar muda o risco, não a
    categoria.
    """
    from app.routers.criativos_execucao import _recibo_dto

    dto = _recibo_dto(travessia.recibo)
    corpo = json.dumps(dto, default=str)

    # chegou
    assert dto["procedencia"]["tenant_id"] == "positivo"
    assert dto["storage"][0]["estado"] == "VERIFIED_OK"
    assert dto["aprovacao"]["estado"] == "aguardando"
    assert {d["slug"] for d in dto["destinos"]} == set(D.DESTINOS)
    assert dto["artefatos"][0]["video"]["codec_video"] == "h264"
    assert dto["artefatos"][0]["enquadramento"]["operacao"] == "nenhuma"
    assert dto["tentativa"] == 1
    assert dto["custo"]["estimado_usd"]["ausencia"] == Ausencia.SEM_CUSTO_DE_PROVIDER.value

    # e não vazou
    assert "texto" not in dto["insumo"], "o texto sanitizado saiu pela API"
    assert dto["insumo"]["hashDoCompleto"], "saiu sem a impressao digital"
    assert BRIEFING not in corpo
    assert "99999-8888" not in corpo
    assert "matriculas@exemplo.test" not in corpo
    assert "2.400,00" not in corpo
    # E o caminho de disco do servidor continua não saindo.
    assert str(travessia.raiz) not in corpo
