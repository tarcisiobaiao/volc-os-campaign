"""O CONTRATO do runtime de vídeo — provado sem renderizar nada.

## Por que este arquivo existe separado

`test_criativo_golden_video.py` prova a travessia executando: worker em outro
processo, render real, ffprobe, storage. Ele precisa de `node`, do runtime
instalado e de `ffprobe`, e onde eles faltam ele **pula**.

⚠️ ACHADO ADVERSARIAL. Esse `skipif` é de MÓDULO. Tirando `node` do `PATH`, o
arquivo inteiro sai `20 skipped` e o `pytest` termina com **exit 0** — verde. Um
CI sem `node` e sem `node_modules` (que não são versionados) reportaria sucesso
sobre um motor que nunca rodou, e ninguém veria a diferença entre "o vídeo
atravessou" e "ninguém tentou".

Este arquivo **não pula**. Ele não renderiza: afirma o que tem de ser verdade no
REPOSITÓRIO para que o render seja possível — e cada uma dessas coisas é um jeito
diferente de o motor quebrar em silêncio.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ_BACKEND = Path(__file__).resolve().parents[1]
RAIZ_REPO = RAIZ_BACKEND.parent
sys.path.insert(0, str(RAIZ_BACKEND))
sys.path.insert(0, str(RAIZ_REPO))

from app.criativo.bancada.adaptadores import remotion as R  # noqa: E402

RUNTIME = RAIZ_REPO / "deploy" / "creative-worker" / "remotion-runtime"

#: sha256 da Inter versionada. Ele entra em `versoes_congeladas` e daí na
#: assinatura determinista: uma fonte trocada muda o pixel sem mudar o pedido, e
#: sem este número a assinatura não acusaria.
SHA_DA_INTER = "29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031"


def test_o_runtime_esta_no_repositorio_e_nao_em_outra_frente():
    """A fábrica externa é outro repositório, com 15 composições e 11 fontes que
    não estão licenciadas aqui. Este runtime é do VOLC O.S., e o teste existe
    para que ninguém o troque por um caminho de máquina sem perceber."""
    assert (RUNTIME / "package.json").is_file()
    assert (RUNTIME / "package-lock.json").is_file()
    assert (RUNTIME / "renderizar.mjs").is_file()
    assert (RUNTIME / "src" / "entrada.ts").is_file()
    assert (RUNTIME / "src" / "Raiz.tsx").is_file()
    assert (RUNTIME / "src" / "Composicao.tsx").is_file()
    assert R.runtime() == RUNTIME


def test_as_versoes_do_remotion_estao_em_lockstep_pelo_LOCKFILE():
    """`package.json` pode dizer `^4.0.0`; o lockfile diz o que está instalado.
    Lockstep é afirmação sobre o que rodou, e só o segundo sabe."""
    lock = json.loads((RUNTIME / "package-lock.json").read_text("utf-8"))
    versoes = {
        caminho.removeprefix("node_modules/"): info.get("version")
        for caminho, info in (lock.get("packages") or {}).items()
        if caminho.removeprefix("node_modules/") == "remotion"
        or caminho.removeprefix("node_modules/").startswith("@remotion/")
    }
    assert versoes, "o lockfile nao declara nenhum pacote do Remotion"
    distintas = set(versoes.values())
    assert len(distintas) == 1, f"lockstep quebrado: {sorted(distintas)}"
    # E a versão é EXATA no package.json — `^` reintroduziria a deriva que o
    # lockfile acabou de fechar.
    manifesto = json.loads((RUNTIME / "package.json").read_text("utf-8"))
    for nome, faixa in manifesto["dependencies"].items():
        assert re.fullmatch(r"\d+\.\d+\.\d+", faixa), f"{nome} nao esta pinado: {faixa}"


def test_a_fonte_licenciada_esta_versionada_e_e_a_esperada():
    """Uma fonte resolvida por caminho de máquina faz o MESMO pedido produzir
    assinaturas diferentes em máquinas diferentes."""
    import hashlib

    fonte = R.fonte_licenciada()
    assert fonte.is_file(), f"a fonte licenciada nao esta no repositorio: {fonte}"
    assert hashlib.sha256(fonte.read_bytes()).hexdigest() == SHA_DA_INTER
    procedencia = (fonte.parent / "PROCEDENCIA.md").read_text("utf-8")
    assert "SIL Open Font License" in procedencia
    assert fonte.name in procedencia


def test_o_perfil_de_sandbox_nega_saida_e_libera_so_o_loopback():
    """Se este perfil for afrouxado, o render deixa de ser hermético e nada mais
    no sistema percebe — o gate confia no kernel, e o kernel confia neste arquivo."""
    perfil = R.perfil_de_sandbox()
    assert perfil.is_file()
    texto = perfil.read_text("utf-8")
    assert "(deny network-outbound)" in texto
    assert 'remote ip "localhost:*"' in texto
    # Nenhuma linha pode reabrir a saída externa depois do deny.
    depois_do_deny = texto.split("(deny network-outbound)", 1)[1]
    for linha in depois_do_deny.splitlines():
        limpa = linha.split(";;")[0].strip()
        if not limpa.startswith("(allow network"):
            continue
        assert "localhost" in limpa or "unix-socket" in limpa, (
            f"o perfil reabre a saida externa: {limpa}"
        )


def test_a_composicao_nao_busca_fonte_na_rede():
    """`@remotion/google-fonts` é a dependência de rede que o hermetismo remove.
    Uma única chamada sobrevivente no bundle faz o render inteiro voltar a pedir
    rede — e o ADR mediu que renderizar UMA composição baixa as fontes de TODAS."""
    # ⚠️ A busca é por IMPORT, e não pelo texto. Os dois arquivos CITAM
    # `@remotion/google-fonts` em comentário, explicando por que não o usam —
    # e uma varredura de substring transformaria a explicação no defeito.
    importa = re.compile(r"""^\s*(?:import|export)\s.*?from\s+['"]([^'"]+)['"]""", re.M)
    for arquivo in (RUNTIME / "src").glob("*.tsx"):
        for modulo in importa.findall(arquivo.read_text("utf-8")):
            assert modulo != "@remotion/google-fonts", f"{arquivo.name} importa {modulo}"
    raiz = (RUNTIME / "src" / "Raiz.tsx").read_text("utf-8")
    assert "@remotion/fonts" in raiz
    assert "staticFile(" in raiz


def test_a_composicao_nao_le_relogio_nem_aleatoriedade():
    """Determinismo é a promessa central do recibo. `Date.now()` e `Math.random()`
    a quebram sem mudar nenhum parâmetro do pedido."""
    for arquivo in (RUNTIME / "src").glob("*.tsx"):
        fonte = arquivo.read_text("utf-8")
        for proibido in ("Date.now(", "Math.random(", "new Date("):
            assert proibido not in fonte, f"{arquivo.name} usa {proibido}"


def test_o_renderizador_sonda_a_rede_antes_de_renderizar():
    """A sonda é o que sustenta o gate de hermetismo. Sem ela, o gate reprova —
    e é assim que tem de ser —, mas o motor deixaria de conseguir produzir."""
    fonte = (RUNTIME / "renderizar.mjs").read_text("utf-8")
    assert "sondarRede" in fonte
    assert "'1.1.1.1'" in fonte or '"1.1.1.1"' in fonte
    assert "rede: sonda" in fonte


def test_o_motor_declara_video_e_o_catalogo_pergunta_a_ele():
    """⚠️ O catálogo respondia o literal `["imagem"]` para TODOS os motores.
    Com o motor de vídeo registrado, ele passou a AFIRMAR que `remotion-local`
    produz imagem — e a tela decidiria botão a partir disso."""
    from app.criativo.bancada.servico import midias_do_motor

    assert R.MotorRemotion.midias == ("video",)
    assert midias_do_motor(R.MotorRemotion) == ["video"]

    class MotorMudo:
        slug = "mudo"

    # Ausência de declaração NÃO vira "imagem": vira ausência nomeada.
    assert midias_do_motor(MotorMudo()) == ["nao_declarada"]


def test_o_pedido_nao_viaja_em_argv():
    """`ps` é legível por qualquer processo da máquina, e o título de uma peça é
    material do cliente. O renderizador recebe UM caminho de arquivo."""
    fonte = (RUNTIME / "renderizar.mjs").read_text("utf-8")
    assert "process.argv[2]" in fonte
    assert "readFileSync(caminhoDoPedido" in fonte
    motor = (RAIZ_BACKEND / "app/criativo/bancada/adaptadores/remotion.py").read_text("utf-8")
    assert 'base = ["node", "renderizar.mjs", str(pedido_json)]' in motor


# ── o sanitizador, e o que ele NÃO promete ───────────────────────────────────


def test_o_sanitizador_cobre_as_classes_que_a_revisao_apontou():
    """⚠️ ACHADO ADVERSARIAL. As regras cobriam e-mail, URL COM esquema, CPF,
    telefone numérico e moeda — e deixavam intactos `@perfil`, `www.` sem
    esquema, placa Mercosul e passaporte. As quatro entraram."""
    from app.criativo.bancada.sanitizacao import sanitizar_insumo

    bruto = (
        "Fale com @joaosilva em www.exemplo.com.br/promo. "
        "Placa ABC1D23, passaporte AB123456, fone (41) 99999-8888, R$ 2.400,00, "
        "e-mail a@b.co e https://x.test/y"
    )
    i = sanitizar_insumo(bruto)
    for vazou in ("@joaosilva", "www.exemplo.com.br", "ABC1D23", "AB123456",
                  "99999-8888", "2.400,00", "a@b.co", "https://x.test"):
        assert vazou not in i.texto, vazou
    assert {"<perfil>", "<url>", "<placa>", "<documento>", "<telefone>",
            "<valor>", "<email>"} <= set(i.substituicoes)


def test_o_sanitizador_nao_promete_anonimizar_e_o_texto_nao_sai_pela_api():
    """A lista é uma allowlist invertida: remove o que reconhece. A garantia
    forte não vem dela — vem de o DTO público não devolver o texto."""
    from app.criativo.bancada.sanitizacao import sanitizar_insumo
    from app.routers.criativos_execucao import _insumo_publico

    i = sanitizar_insumo("Projeto secreto do Colegio Positivo para 2027")
    # O assunto SOBREVIVE — e isso é a promessa estreita, dita em voz alta.
    assert "Colegio Positivo" in i.texto
    # E é justamente por isso que ele não sai.
    publico = _insumo_publico({
        "estado": i.estado, "texto": i.texto,
        "hash_do_completo": i.hash_do_completo,
        "substituicoes": i.substituicoes,
        "versao_do_sanitizador": i.versao_do_sanitizador, "truncado": i.truncado,
    })
    assert "texto" not in publico
    assert "Colegio Positivo" not in json.dumps(publico)
    assert publico["hashDoCompleto"] == i.hash_do_completo


def test_a_ausencia_nao_vira_valor_no_pedido_do_motor():
    """⚠️ ACHADO ADVERSARIAL. `int(p.get("fps") or 30)` transformava `0` e `None`
    em 30, e `bool(p.get("com_audio", True))` lia `"false"` como verdadeiro."""
    import pytest

    from app.criativo.bancada.contrato import Encomenda, FalhaDoMotor, SaidaPedida

    def pedido(**extra):
        return Encomenda(
            receita_id="r", tenant_id="t", motor_slug=R.SLUG, modo_slug="m",
            finalidade_slug="f", seed=1,
            saidas=(SaidaPedida(slot="s", largura=1080, altura=1920,
                                midia="video", mime="video/mp4"),),
            parametros={"insumo": "x", **extra},
        )

    # Ausência usa o padrão declarado — isso continua sendo uma decisão.
    assert R._ler_pedido(pedido()).fps == 30
    # PRESENTE e inválido é recusado, e não substituído em silêncio.
    for invalido in ({"fps": 0}, {"fps": -1}, {"duracao_s": 0}, {"fps": "muitos"}):
        with pytest.raises(FalhaDoMotor):
            R._ler_pedido(pedido(**invalido))
    # `"false"` é falso; um valor que não é booleano é recusado.
    assert R._ler_pedido(pedido(com_audio="false")).com_audio is False
    assert R._ler_pedido(pedido(com_audio=True)).com_audio is True
    with pytest.raises(FalhaDoMotor):
        R._ler_pedido(pedido(com_audio="talvez"))


def test_as_versoes_congeladas_nao_guardam_o_basename_do_ffmpeg():
    """⚠️ ACHADO ADVERSARIAL. Gravava `"ffmpeg"` — a mesma string em qualquer
    máquina e em qualquer versão. Uma versão congelada que não distingue ffmpeg 6
    de ffmpeg 8 congela nada, e o ffmpeg encoda o vídeo."""
    v = R.MotorRemotion().versoes_congeladas()
    assert v["ffmpeg"] != "ffmpeg"
    assert v["ffmpeg"] in ("ausente", "nao_apurada") or "version" in v["ffmpeg"]
    # Plataforma e Chromium entram porque a equivalência macOS ↔ Linux é NÃO
    # PROVADA: sem eles, dois recibos de plataformas diferentes pareceriam
    # comparáveis.
    assert v["plataforma"]
    assert v["chrome_headless_shell"]
