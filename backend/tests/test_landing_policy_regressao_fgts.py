"""REGRESSÃO PERMANENTE — o funil FGTS que foi ao ar, medido pelo portão de hoje.

## Por que este arquivo existe

O incidente não é hipotético: o funil FGTS foi escrito, publicado e apontado por
campanha, e a conta que o anunciava está `SUSPENDED`. Os artefatos daquele run
estão no repositório (`funnelforge-migracao/referencia/**`) — plano, conteúdo da
LP e o inventário do que ficou no ar. Enquanto eles estiverem lá, o portão tem
como responder a única pergunta que importa para uma regressão:

    o portão de hoje teria barrado a página de ontem?

Se um dia a resposta virar "não", isso é uma regressão de verdade — alguém
afrouxou uma regra e não percebeu.

## Sanitização

Nada aqui lê credencial, `state.json`, `config_snapshot.json` ou qualquer
artefato de execução com segredo. Só entram o PLANO (`funnel_plan.json`), o
CONTEÚDO da LP (`*.lp_content.json`) e o texto publicado
(`funil-no-ar/texto/LP.md`) — texto que já está público no site. Nenhuma
identidade de conta Google, nenhum ID de campanha, nenhuma chave.

## Permanência

`_EXCERTO_SANITIZADO` é uma cópia REDUZIDA do artefato histórico, embutida aqui.
Ela existe para o caso de a pasta `referencia/` ser arquivada: a regressão
continua valendo mesmo sem os arquivos originais. Quando eles existem, os dois
caminhos rodam — o embutido prova a permanência, o real prova a fidelidade.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.landing_policy import (
    PaginaObservada,
    PapelDestino,
    PontoDePortao,
    avaliar,
    emitir_recibo,
)

RAIZ = Path(__file__).resolve().parents[2]
REFERENCIA = RAIZ / "funnelforge-migracao" / "referencia"
RUN_FGTS = REFERENCIA / "run-fgts-producao"
FUNIL_NO_AR = REFERENCIA / "funil-no-ar"

URL_HISTORICA = "https://creditoup.com.br/r/antecipacao-saque-aniversario-fgts"

#: Trechos LITERAIS do artefato histórico, reduzidos ao mínimo que carrega os
#: defeitos. Cada linha é copiada de `run-fgts-producao` / `funil-no-ar`; nenhuma
#: foi escrita para este teste. A proveniência de cada uma está no comentário.
_EXCERTO_SANITIZADO = """
<h1>Saque-Aniversário FGTS Liberado pelo Governo: Como Liberar e Sacar Seu Dinheiro em 2026</h1>
<p>Este guia prático mostra como adiantar esses valores de forma segura, com base
nas instruções oficiais da <strong>Caixa Econômica Federal (CAIXA)</strong> para este ano.</p>
<p>Pessoas com restrição no nome podem contratar normalmente, pois o processo não
realiza consultas ao <strong>SPC ou Serasa</strong> para a liberação do crédito.</p>
<p>Para ter acesso, basta possuir saldo disponível e autorizar um banco parceiro,
como o <strong>Banco Bmg</strong> ou o <strong>Santander</strong>, a consultar o seu fundo.</p>
<p><strong>Rapidez no Pix</strong>: a liberação do dinheiro costuma ocorrer em poucos
minutos após a contratação digital.</p>
<p>Você pode antecipar valores de <strong>R$ 100,00 a R$ 500,00</strong> por parcela anual.</p>
"""

#: Os defeitos que o funil histórico carregava e que o portão de hoje precisa
#: nomear. Não é "alguma coisa reprovou": é ESTE conjunto, por código.
DEFEITOS_HISTORICOS = {
    # "Liberado pelo Governo" no H1 do plano + "sem consulta SPC/Serasa" +
    # "liberação ... em poucos minutos" no corpo.
    "ALEGACAO_DE_RESULTADO_IMPROVAVEL",
    # "Banco Bmg"/"Santander" apresentados como banco parceiro, sem lastro.
    "MARCA_TERCEIRA_SEM_LASTRO",
    # Caixa/CAIXA/Receita Federal citados sem aviso de não-vínculo na página.
    "AVISO_NAO_OFICIAL_AUSENTE",
    "AFILIACAO_GOVERNAMENTAL_IMPLICITA",
}


def _pagina(html: str, **kwargs) -> PaginaObservada:
    padrao = {
        "url": URL_HISTORICA,
        "html": html,
        "cnpj_esperado": "42.724.548/0001-24",
        "origem": "historical_repository_artifact",
    }
    padrao.update(kwargs)
    return PaginaObservada(**padrao)


def _avaliar(html: str, **kwargs):
    return avaliar(
        _pagina(html, **kwargs),
        PapelDestino.PAID_DESTINATION,
        PontoDePortao.ARTEFATO_DE_GERACAO,
    )


def _codigos(avaliacao) -> set[str]:
    return {a.codigo for a in avaliacao.bloqueios}


# ── o caminho permanente: o excerto embutido ───────────────────────────────


def test_o_funil_fgts_historico_seria_barrado_hoje():
    av = _avaliar(_EXCERTO_SANITIZADO)
    faltando = DEFEITOS_HISTORICOS - _codigos(av)
    assert faltando == set(), f"o portão deixou de nomear: {sorted(faltando)}"
    assert av.paid_destination_ready is False


def test_o_recibo_do_funil_historico_registra_bloqueio_com_fonte():
    av = _avaliar(_EXCERTO_SANITIZADO)
    recibo = emitir_recibo(av, hash_do_conteudo="f" * 64)
    assert recibo["paid_destination_ready"] is False
    assert recibo["verdict"] == "blocked"
    codigos = {b["code"] for b in recibo["blockers"]}
    assert DEFEITOS_HISTORICOS <= codigos
    for bloqueio in recibo["blockers"]:
        assert bloqueio["policy"]["url"].startswith("https://support.google.com/")


def test_o_excerto_embutido_nao_carrega_segredo():
    """A regressão é PERMANENTE porque é sanitizada — a prova disso vai junto."""
    baixo = _EXCERTO_SANITIZADO.lower()
    for proibido in ("password", "senha=", "token", "api_key", "customer_id", "secret",
                     "bearer ", "service_role"):
        assert proibido not in baixo
    assert not any(ch.isdigit() and len(bloco) >= 9
                   for bloco in baixo.split() for ch in bloco if bloco.isdigit())


# ── o caminho de fidelidade: os artefatos reais, quando existem ────────────


@pytest.mark.skipif(not (RUN_FGTS / "funnel_plan.json").is_file(),
                    reason="artefato histórico arquivado; a regressão embutida continua valendo")
def test_o_plano_historico_real_carrega_a_alegacao_que_o_portao_barra():
    """O H1 do PLANO já trazia 'Liberado pelo Governo'.

    Aqui está o defeito de fundo do motor antigo: o portão de conteúdo olhava o
    CORPO escrito, e a alegação entrou pelo TÍTULO decidido uma etapa antes. Um
    portão que não vê o plano não vê o defeito na hora em que ele é barato.
    """
    plano = json.loads((RUN_FGTS / "funnel_plan.json").read_text(encoding="utf-8"))
    titulos = [p.get("h1_title", "") for p in plano.get("pages", [])]
    assert any("liberado pelo governo" in t.lower() for t in titulos), titulos

    lp = next(p for p in plano["pages"] if p.get("h1_title"))
    av = _avaliar(f"<h1>{lp['h1_title']}</h1>")
    assert "ALEGACAO_DE_RESULTADO_IMPROVAVEL" in _codigos(av)


@pytest.mark.skipif(
    not list(RUN_FGTS.glob("*.lp_content.json")),
    reason="artefato histórico arquivado; a regressão embutida continua valendo",
)
def test_o_conteudo_real_da_lp_historica_seria_barrado():
    arquivo = sorted(RUN_FGTS.glob("*.lp_content.json"))[0]
    conteudo = json.loads(arquivo.read_text(encoding="utf-8"))
    pedacos = [conteudo.get("intro", "")]
    pedacos += [s.get("body", "") for s in conteudo.get("sections", [])]
    pedacos += [f.get("answer", "") for f in conteudo.get("faq", []) if isinstance(f, dict)]
    av = _avaliar("".join(pedacos))
    assert av.paid_destination_ready is False
    assert _codigos(av) & DEFEITOS_HISTORICOS, sorted(_codigos(av))


@pytest.mark.skipif(not (FUNIL_NO_AR / "texto" / "LP.md").is_file(),
                    reason="artefato histórico arquivado; a regressão embutida continua valendo")
def test_o_texto_que_ficou_no_ar_seria_barrado():
    texto = (FUNIL_NO_AR / "texto" / "LP.md").read_text(encoding="utf-8")
    av = _avaliar(f"<div>{texto}</div>")
    assert av.paid_destination_ready is False
    assert av.bloqueios, "o texto publicado passaria pelo portão de hoje"


@pytest.mark.skipif(not (FUNIL_NO_AR / "INVENTARIO.md").is_file(),
                    reason="artefato histórico arquivado")
def test_o_inventario_do_funil_no_ar_ja_registrava_incongruencia_de_botao():
    """O defeito que o portão de hoje chama de `ANCORA_INCONGRUENTE_COM_DESTINO`
    já estava medido à mão em 11/08/2026 — e não tinha portão que o barrasse."""
    inventario = (FUNIL_NO_AR / "INVENTARIO.md").read_text(encoding="utf-8")
    assert "Promessa do botão ≠ conteúdo entregue" in inventario
