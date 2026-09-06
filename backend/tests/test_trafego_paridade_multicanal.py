"""As contraprovas estruturais da missão multicanal — por ÁRVORE, não por dublê.

## Por que por árvore sintática

Três das contraprovas desta missão são sobre a FORMA do código, e não sobre o
comportamento de uma chamada:

  * `/provar` e `/subir` usam o MESMO montador por canal;
  * o portão criativo roda ANTES do segredo, do ledger e da rede;
  * nenhuma peça sem recibo atravessa.

Um teste de comportamento provaria isso para o caminho que ele exercita, e
seguiria verde no dia em que alguém acrescentasse um segundo caminho ao lado.
`test_trafego_plataforma.py` já usa a mesma técnica pela mesma razão — e com a
vantagem extra de não precisar do SDK do Google instalado.

⚠️ Nenhuma linha deste arquivo importa `volc_ads.campanha.*` nem toca rede.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
ROTA = RAIZ / "backend" / "app" / "routers" / "trafego.py"


def _funcao(nome: str) -> ast.FunctionDef:
    arvore = ast.parse(ROTA.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no.name == nome:
            return no
    raise AssertionError(f"função {nome!r} não existe em {ROTA}")


def _chamadas(no: ast.AST) -> list[str]:
    """Os nomes chamados DENTRO deste nó, na ORDEM em que aparecem no arquivo."""
    fora: list[tuple[int, str]] = []
    for filho in ast.walk(no):
        if not isinstance(filho, ast.Call):
            continue
        alvo = filho.func
        nome = (alvo.attr if isinstance(alvo, ast.Attribute)
                else getattr(alvo, "id", ""))
        if nome:
            fora.append((filho.lineno, nome))
    return [n for _, n in sorted(fora)]


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 3 — /provar e /subir usam o MESMO builder, canal a canal
# ═══════════════════════════════════════════════════════════════════════════


MONTADOR_POR_CANAL = {
    "DEMAND_GEN": "_montar_plano_demand_gen",
    "DISPLAY": "_montar_plano_display",
    "PERFORMANCE_MAX": "_montar_plano_pmax",
}


@pytest.mark.parametrize("canal,montador", sorted(MONTADOR_POR_CANAL.items()))
def test_provar_e_subir_chamam_o_mesmo_montador(canal: str, montador: str):
    """⚠️ Uma SEGUNDA montagem "que faz quase o mesmo" é o defeito.

    `_montar_plano_display` aplica país de origem, idioma, vertical, filtro de
    bloqueadores do cockpit e a recusa dos campos que o canal não opera.
    Remontar por `montar_brief` e remendar depois reproduziria parte disso e
    perderia o resto — e o plano que `/subir` sela deixaria de ser o plano que
    `/provar` aprovou. A divergência só apareceria na conta.
    """
    provar = set(_chamadas(_funcao("provar")))
    subir = set(_chamadas(_funcao("subir")))
    assert montador in provar, f"/provar não monta {canal} pelo montador comum"
    assert montador in subir, f"/subir não monta {canal} pelo montador comum"


def test_nenhuma_rota_monta_canal_por_um_caminho_proprio():
    """Só existe UM montador por canal no arquivo inteiro.

    Se alguém escrever `_montar_plano_display_v2`, este teste cai — e é para
    cair: dois montadores para o mesmo canal é a divergência que T02 fechou.
    """
    arvore = ast.parse(ROTA.read_text(encoding="utf-8"))
    montadores = sorted(
        no.name for no in ast.walk(arvore)
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
        and no.name.startswith("_montar_plano_")
    )
    assert montadores == sorted(MONTADOR_POR_CANAL.values()), montadores


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 4 — o portão criativo roda ANTES de segredo, ledger e rede
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("montador", sorted(MONTADOR_POR_CANAL.values()))
def test_o_portao_criativo_roda_antes_da_ponte_em_todo_canal(montador: str):
    """Em cada montador, `_recibos_de_politica_das_pecas` vem antes da ponte.

    A ponte (`criativo_ponte.imagens_de_*`) é o que transforma as peças no
    objeto que o builder consome. Rodar o portão depois dela deixaria uma peça
    recusada já convertida — e a recusa passaria a depender de quem chama na
    ordem certa, que não é uma trava.
    """
    ordem = _chamadas(_funcao(montador))
    # ⚠️ Display delega as duas etapas a `_imagens_de_display`, que é onde o
    # portão e a ponte moram juntos — e a ordem entre eles é o que importa.
    # Seguir a delegação é ler o caminho REAL; exigir que todo montador chame o
    # portão diretamente cobraria uma forma, não a propriedade.
    if "_recibos_de_politica_das_pecas" not in ordem:
        delegados = [n for n in ordem if n.startswith("_imagens_de_")]
        assert delegados, (
            f"{montador} não chama o portão nem delega a um ajudante que o chame")
        ordem = _chamadas(_funcao(delegados[0]))

    assert "_recibos_de_politica_das_pecas" in ordem, montador
    portao = ordem.index("_recibos_de_politica_das_pecas")
    pontes = [i for i, n in enumerate(ordem) if n.startswith("imagens_de_")]
    assert pontes, f"{montador} não chama a ponte do Estúdio"
    assert portao < min(pontes), (
        f"{montador}: o portão de política roda DEPOIS da ponte")


def test_o_portao_criativo_roda_antes_do_ledger_e_da_rede_em_subir():
    """Em `/subir`, a ordem é: portão → mensuração → ledger → mutate.

    ⚠️ O portão vive dentro do montador, que roda em `_provar_de_novo`, que roda
    ANTES de `ledger.abrir` e antes de `sb.subir`. Um recibo aberto para uma
    chamada que nunca sai fica `em_voo` órfão, e a camada 4 passa a bloquear o
    item até alguém reconciliar uma tentativa que não existiu.
    """
    no = _funcao("subir")
    ordem = _chamadas(no)

    def _primeiro(nome: str) -> int:
        assert nome in ordem, f"/subir não chama {nome}"
        return ordem.index(nome)

    montagem = min(_primeiro(m) for m in MONTADOR_POR_CANAL.values())
    medicao = _primeiro("exigir_para_criacao")
    abertura = _primeiro("abrir")

    # ⚠️ O mutate NÃO é uma chamada direta: ele viaja como ARGUMENTO de
    # `asyncio.to_thread(sb.subir, …)`. Procurar `subir` entre os nomes chamados
    # não o encontraria — e um teste que não encontra o mutate provaria a ordem
    # de tudo, menos da coisa que importa.
    linhas = [
        c.lineno for c in ast.walk(no)
        if isinstance(c, ast.Call)
        and getattr(c.func, "attr", "") == "to_thread"
        and c.args
        and getattr(c.args[0], "attr", "") == "subir"
    ]
    assert linhas, "/subir não despacha `sb.subir` numa thread"
    ordenadas = sorted(
        (c.lineno, (c.func.attr if isinstance(c.func, ast.Attribute)
                    else getattr(c.func, "id", "")))
        for c in ast.walk(no) if isinstance(c, ast.Call)
    )
    mutate = [i for i, (ln, _) in enumerate(ordenadas) if ln == min(linhas)][0]

    assert montagem < medicao < abertura < mutate, (
        f"a ordem de /subir mudou: montagem={montagem}, medição={medicao}, "
        f"ledger={abertura}, mutate={mutate}")


def test_o_portao_de_canal_roda_antes_de_a_ponte_ser_importada():
    """⚠️ `_ponte()` importa o SDK do Google. A recusa de canal vem antes.

    `test_http_subir_demand_gen_valido_recusa_operacional_antes_de_efeitos` já
    prova isso por comportamento, com `_ponte` dublado para falhar. Aqui a
    mesma propriedade é lida na FORMA: `plat.exigir_construtor` aparece antes de
    qualquer `_ponte` no corpo da rota.
    """
    ordem = _chamadas(_funcao("subir"))
    assert "exigir_construtor" in ordem
    assert "_ponte" in ordem
    assert ordem.index("exigir_construtor") < ordem.index("_ponte")


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVA 6 — vídeo do YouTube sem bytes, hash e recibo é RECUSADO
# ═══════════════════════════════════════════════════════════════════════════


def test_pmax_recusa_video_do_youtube_por_referencia():
    """Um `resource name` não tem bytes: o portão não julga o que não leu.

    ⚠️ A recusa acontece ANTES do portão e antes da ponte — anexar os vídeos ao
    asset group depois do portão deixaria passar, por outra porta, exatamente a
    peça de terceiro que o portão existe para barrar. A revisão adversarial
    reproduziu isso.
    """
    fonte = ROTA.read_text(encoding="utf-8")
    for montador in ("_montar_plano_pmax", "_brief_pmax_offline"):
        no = _funcao(montador)
        trecho = ast.get_source_segment(fonte, no) or ""
        assert "videos_youtube" in trecho, montador
        assert "não tem hash" in trecho or "não tem hash, inspeção nem recibo" in trecho, (
            f"{montador} não explica por que recusa vídeo por referência")
        # A recusa é uma exceção, e não um aviso.
        assert any(isinstance(f, ast.Raise) for f in ast.walk(no)), montador


def test_a_recusa_de_video_vem_antes_do_portao_em_pmax():
    ordem = _chamadas(_funcao("_montar_plano_pmax"))
    fonte = ROTA.read_text(encoding="utf-8")
    no = _funcao("_montar_plano_pmax")
    linhas_de_raise = [
        f.lineno for f in ast.walk(no)
        if isinstance(f, ast.Raise)
        and "videos_youtube" in (ast.get_source_segment(fonte, no) or "")
    ]
    assert linhas_de_raise
    assert "_recibos_de_politica_das_pecas" in ordem
