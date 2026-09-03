#!/usr/bin/env python3
"""Nenhum arquivo fora da allowlist canônica alcança a criação de campanha.

    python3 scripts/gate_autoridade_de_nascimento.py

## Por que este gate existe

`scripts/gate_sem_mutacao_google.py` prova uma coisa estreita e verdadeira: na
ROTA TESTADA, nenhuma mutação sai sem recibo `em_voo` antes. Ele diz, no próprio
docstring, que não fala sobre caminhos fora dessa rota.

P09-T17 é exatamente sobre esses caminhos. Em 03/09/2026 a contraprova vermelha
mostrou que `volc_ads.subir.subir` escrevia com um selo forjado, conta
arbitrária e `status = ENABLED`, sem ledger, sem identidade, sem destino pago e
sem conjunto pago selado — porque os portões eram convenções DA ROTA. A correção
foi a `Autorizacao` assinada de `volc_ads/gads/autoridade.py`.

Mas uma capacidade só é única enquanto ninguém abre a segunda porta. Este gate é
essa guarda: ele varre a árvore por AST e derruba o build se um arquivo fora da
allowlist referenciar qualquer um dos símbolos que alcançam escrita de campanha.

## O que ele NÃO é

Não é análise de fluxo: ele não prova que um arquivo da allowlist usa o símbolo
corretamente — isso é o trabalho das contraprovas. Não é contenção de processo,
não inspeciona rede e não impede que alguém, dentro do mesmo processo, chame
`emitir()` com strings inventadas (ver REMAINING-RISKS.md). O que ele garante é
que **um caminho novo de escrita é uma falha de gate, não uma descoberta de
auditoria meses depois.**
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Os módulos que HOSPEDAM a fronteira de escrita. Um nome importado deles, ou
#: um atributo lido através de um alias deles, é uma referência à fronteira.
#:
#: ⚠️ A qualificação por módulo não é preciosismo. A primeira versão casava o
#: nome cru, e `mutar`/`emitir` são verbos comuns em português: ela acusou
#: `backend/app/trafego/capacidades.py` (que tem uma variável local `mutar =
#: admin and escrita_permitida`), `scripts/validar_postiz_pacote.py` (variável
#: de laço) e `backend/app/landing_policy/__init__.py` (um `emitir` de recibo de
#: landing page, outro assunto por completo). Um gate que acusa três inocentes
#: na primeira execução é um gate que alguém desliga na segunda.
MODULOS_DA_FRONTEIRA = ("gads.client", "gads.autoridade", "volc_ads.subir")

#: Os símbolos daqueles módulos que alcançam ou governam escrita.
SIMBOLOS_QUALIFICADOS = {
    "mutar": "o único writer do engine (volc_ads/gads/client.py)",
    "emitir": "a emissão da capacidade de nascimento",
    "conferir": "a verificação da capacidade",
    "exigir_e_consumir": "o consumo da capacidade na fronteira",
    "subir": "o executor que monta o pré-recibo e chama o writer",
}

#: Tokens do SDK do Google que não colidem com nada do domínio. Estes valem em
#: qualquer forma — nome, atributo ou string dentro de `get_type`/`get_service`.
SIMBOLOS_DO_SDK = {
    "mutate_campaigns": "CampaignService.mutate_campaigns, do SDK",
    "mutate_operations": "o campo repetido do MutateGoogleAdsRequest",
    "CampaignService": "o serviço de campanha do SDK",
    "CampaignOperation": "a operação de campanha do SDK",
}

#: Os arquivos que SÃO a fronteira. Eles definem os símbolos em vez de
#: importá-los, então nenhuma varredura de referência os encontraria — e uma
#: allowlist que não os contém estaria descrevendo outro sistema.
DEFINEM_A_FRONTEIRA = {
    "volc_ads/gads/autoridade.py": "define emitir/conferir/exigir_e_consumir",
    "volc_ads/gads/client.py": "define mutar",
    "volc_ads/subir.py": "define subir",
}

#: Só estes arquivos podem tocar a fronteira. Cada entrada declara POR QUÊ —
#: uma allowlist sem motivo é uma allowlist que ninguém consegue revisar.
#:
#: ⚠️ A lista é CURTA de propósito, e ela encurtou depois de a detecção passar a
#: ser qualificada por módulo. Construtores de payload (`campanha/comum.py`,
#: `campanha/plano.py`) montam `campaign_operation.create` e NÃO aparecem aqui:
#: montar payload não é escrever, e listá-los transformaria a allowlist num
#: inventário de quem fala do Google Ads — que é grande, muda toda semana e não
#: responde à pergunta deste gate.
ALLOWLIST: dict[str, str] = {
    # ── a autoridade canônica ─────────────────────────────────────────────
    "backend/app/routers/trafego.py":
        "a autoridade canônica: POST /api/trafego/subir emite a autorização e "
        "é a única porta de nascimento. Também hospeda POST /api/trafego/remover, "
        "que só emite CampaignOperation.remove (provado estaticamente aqui).",

    # ── este gate ─────────────────────────────────────────────────────────
    "scripts/gate_autoridade_de_nascimento.py":
        "ele precisa nomear os símbolos que vigia.",

    # ── testes e contraprovas: adapters falsos, zero credencial ───────────
    "volc_ads/testes_subir.py":
        "banco de provas do executor; emite autorização para provar a "
        "VERIFICAÇÃO, com sentinela no writer e zero rede.",
    "volc_ads/testes_entrega.py":
        "prova estática de que `entrega.py` não menciona escrita.",
    "volc_ads/campanha/testes_display.py":
        "prova de builder; cita `mutate_operations` ao descrever o payload.",
    "volc_ads/campanha/testes_demand_gen.py":
        "prova de que Demand Gen não alcança o executor.",
    "docs/closure/hermes-p09-t17-campaign-birth-authority-v1/contraprova-vermelha-bypass.py":
        "a contraprova vermelha desta entrega; adapter falso e contador.",
}

#: Prefixos de teste que podem tocar a fronteira sem entrada individual. Testes
#: usam adapters falsos e não carregam credencial; exigir uma linha por arquivo
#: transformaria a allowlist num arquivo que ninguém lê.
PREFIXOS_DE_TESTE = ("backend/tests/", "tools/agent-harness/tests/")

IGNORAR = (
    "node_modules", ".venv", ".git", "__pycache__", ".pytest_cache",
    ".graphify-cache", "graphify-out", "funnelforge-migracao", "testsprite_tests",
)


def _arquivos() -> list[Path]:
    saida = []
    for caminho in RAIZ.rglob("*.py"):
        rel = caminho.relative_to(RAIZ).as_posix()
        if any(parte in rel.split("/") for parte in IGNORAR):
            continue
        if any(rel.startswith(f"{p}/") or f"/{p}/" in f"/{rel}" for p in IGNORAR):
            continue
        saida.append(caminho)
    return sorted(saida)


def _e_da_fronteira(texto: str) -> bool:
    return any(alvo in texto for alvo in MODULOS_DA_FRONTEIRA)


def _aliases_da_fronteira(arvore: ast.AST, arquivo: Path) -> set[str]:
    """Os nomes locais que apontam para um módulo da fronteira.

    Cobre as quatro formas que aparecem de verdade no repositório:

        import volc_ads.subir as sbm          → {"sbm"}
        from volc_ads.gads import client      → {"client"}
        from .gads import autoridade as aut   → {"aut"}
        from . import subir                   → {"subir"}   (dentro de volc_ads)
    """
    dentro_do_engine = "volc_ads" in arquivo.parts
    aliases: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for alias in no.names:
                if _e_da_fronteira(alias.name):
                    aliases.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(no, ast.ImportFrom):
            base = no.module or ""
            for alias in no.names:
                inteiro = f"{base}.{alias.name}" if base else alias.name
                # Import relativo dentro do engine: `from . import subir` e
                # `from .gads import autoridade` resolvem para `volc_ads.*`.
                if no.level and dentro_do_engine:
                    inteiro = f"volc_ads.{inteiro}" if base else f"volc_ads.{alias.name}"
                if _e_da_fronteira(inteiro) or _e_da_fronteira(
                        f"{base}.{alias.name}"):
                    aliases.add(alias.asname or alias.name)
    return aliases


def _referencias(arquivo: Path) -> set[str]:
    """Os símbolos vigiados que este arquivo alcança, por AST.

    AST e não `grep`: um comentário que explica por que NÃO se usa `mutar` é
    exatamente o tipo de linha que este repositório escreve muito, e contá-la
    como referência faria o gate mentir na primeira execução.
    """
    rel = arquivo.relative_to(RAIZ).as_posix()
    if rel in DEFINEM_A_FRONTEIRA:
        return {f"define:{rel.rsplit('/', 1)[-1]}"}

    try:
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    aliases = _aliases_da_fronteira(arvore, arquivo)
    achados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom):
            base = no.module or ""
            relativo = bool(no.level) and "volc_ads" in arquivo.parts
            for alias in no.names:
                if alias.name not in SIMBOLOS_QUALIFICADOS:
                    continue
                if _e_da_fronteira(base) or (relativo and _e_da_fronteira(
                        f"volc_ads.{alias.name}")):
                    achados.add(alias.name)
        elif isinstance(no, ast.Attribute) and no.attr in SIMBOLOS_QUALIFICADOS:
            # `sb.subir`, `aut.emitir`, `cli.mutar` — só quando a base é um
            # alias que este arquivo ligou a um módulo da fronteira.
            base = no.value
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name) and base.id in aliases:
                achados.add(no.attr)
        elif isinstance(no, ast.Attribute) and no.attr in SIMBOLOS_DO_SDK:
            achados.add(no.attr)
        elif isinstance(no, ast.Name) and no.id in SIMBOLOS_DO_SDK:
            achados.add(no.id)
        elif isinstance(no, ast.Constant) and isinstance(no.value, str):
            # `get_service("CampaignService")` e `get_type("CampaignOperation")`
            # passam o nome como STRING: sem este ramo, o caminho que a rota
            # `/remover` usa não seria visto por este gate.
            if no.value in SIMBOLOS_DO_SDK:
                achados.add(no.value)
    return achados


def _permitido(rel: str) -> bool:
    return (rel in ALLOWLIST or rel in DEFINEM_A_FRONTEIRA
            or rel.startswith(PREFIXOS_DE_TESTE))


def _remover_so_remove() -> list[str]:
    """`POST /api/trafego/remover` muta — e só pode emitir `.remove`.

    Ela é a outra escrita de campanha do sistema, e P09-T17 a inventaria como
    mutação-que-não-nasce. A prova é estática porque a alternativa seria
    chamá-la contra a conta real.
    """
    rota = RAIZ / "backend/app/routers/trafego.py"
    arvore = ast.parse(rota.read_text(encoding="utf-8"), filename=str(rota))
    for no in ast.walk(arvore):
        if not isinstance(no, ast.AsyncFunctionDef) or no.name != "remover_campanha":
            continue
        verbos = {
            filho.attr
            for filho in ast.walk(no)
            if isinstance(filho, ast.Attribute)
            and filho.attr in {"create", "update", "remove"}
        }
        if verbos - {"remove"}:
            return [f"remover_campanha menciona os verbos {sorted(verbos)}; "
                    "só `remove` é aceito nessa rota"]
        if "remove" not in verbos:
            return ["remover_campanha não menciona `remove` — a prova estática "
                    "deixou de descrever a função"]
        return []
    return ["não encontrei `remover_campanha` em backend/app/routers/trafego.py"]


def _canais_coerentes() -> list[str]:
    """A capacidade não pode conhecer canais que o engine não sabe montar."""
    sys.path.insert(0, str(RAIZ))
    try:
        from volc_ads.campanha import perfil
        from volc_ads.gads import autoridade
    except Exception as exc:  # noqa: BLE001
        return [f"não consegui importar a capacidade para conferir canais ({exc}); "
                "ausência de leitura não vale como coerência"]
    engine = set(perfil.canais_que_criam())
    capacidade = set(autoridade.CANAIS_QUE_NASCEM)
    if engine != capacidade:
        return [f"canais divergentes: perfil cria {sorted(engine)}, a capacidade "
                f"autoriza {sorted(capacidade)}"]
    return []


def main() -> int:
    falhas: list[str] = []

    mortas = [rel for rel in ALLOWLIST if not (RAIZ / rel).exists()]
    if mortas:
        falhas.append(
            "entradas mortas na allowlist (o gate apodrece se elas ficarem): "
            + ", ".join(sorted(mortas)))

    fora: list[tuple[str, list[str]]] = []
    dentro = 0
    for arquivo in _arquivos():
        rel = arquivo.relative_to(RAIZ).as_posix()
        achados = _referencias(arquivo)
        if not achados:
            continue
        if _permitido(rel):
            dentro += 1
            continue
        fora.append((rel, sorted(achados)))

    if fora:
        falhas.append(
            f"{len(fora)} arquivo(s) fora da allowlist canônica tocam a "
            "fronteira de escrita de campanha")
        for rel, achados in fora:
            falhas.append(f"    {rel} → {', '.join(achados)}")
    else:
        print(f"ok · 1/4 nenhum arquivo fora da allowlist toca a fronteira "
              f"({dentro} arquivos permitidos a tocam, cada um com motivo "
              f"declarado)")

    inuteis = [rel for rel in ALLOWLIST if not _referencias(RAIZ / rel)]
    if inuteis:
        # Não é falha: um arquivo pode deixar de tocar a fronteira, e isso é
        # progresso. Mas a entrada precisa sair, ou a allowlist passa a
        # autorizar o que ninguém revisou.
        print(f"aviso · {len(inuteis)} entrada(s) da allowlist já não tocam a "
              f"fronteira e podem sair: {', '.join(sorted(inuteis))}")

    problemas_remover = _remover_so_remove()
    if problemas_remover:
        falhas.extend(problemas_remover)
    else:
        print("ok · 2/4 POST /api/trafego/remover só emite CampaignOperation."
              "remove — nunca create/update")

    problemas_canais = _canais_coerentes()
    if problemas_canais:
        falhas.extend(problemas_canais)
    else:
        print("ok · 3/4 os canais que a capacidade autoriza são exatamente os "
              "que o engine sabe montar")

    # A quarta: exatamente UM arquivo de produção cunha a capacidade.
    #
    # ⚠️ A varredura é sobre a árvore inteira, e não sobre a allowlist. Conferir
    # só a allowlist responderia "os autorizados são os autorizados" — verde
    # sempre. O que interessa é quem emite NO REPOSITÓRIO.
    sys.path.insert(0, str(RAIZ))
    try:
        from volc_ads.gads import autoridade
    except Exception as exc:  # noqa: BLE001
        falhas.append(f"não consegui ler a autoridade canônica ({exc})")
    else:
        emissores = sorted(
            arquivo.relative_to(RAIZ).as_posix()
            for arquivo in _arquivos()
            if "emitir" in _referencias(arquivo)
            and not arquivo.relative_to(RAIZ).as_posix().startswith(
                ("scripts/gate_", "docs/"))
            and "testes_" not in arquivo.name
            and not arquivo.relative_to(RAIZ).as_posix().startswith(
                PREFIXOS_DE_TESTE)
        )
        if emissores != ["backend/app/routers/trafego.py"]:
            falhas.append(
                f"os emissores de produção da capacidade são {emissores} e "
                "deveria ser exatamente ['backend/app/routers/trafego.py'] — "
                f"uma segunda autoridade paralela a "
                f"{autoridade.AUTORIDADE_CANONICA} é o que P09-T17 fechou")
        else:
            print(f"ok · 4/4 só {autoridade.AUTORIDADE_CANONICA} cunha a "
                  "capacidade em produção")

    if falhas:
        print()
        for f in falhas:
            print(f"gate: {f}", file=sys.stderr)
        return 1

    print("\na criação de campanha Google Ads é alcançável por UMA porta, e "
          "qualquer porta nova é uma falha deste gate.")
    print("este gate NÃO inspeciona rede, NÃO analisa fluxo dentro dos arquivos "
          "permitidos e NÃO impede forja in-process (ver REMAINING-RISKS.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
