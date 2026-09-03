#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prova ESTRUTURAL de que esta entrega não toca nada real.

    python3 scripts/provar_visual_proof_hermetico.py
    python3 scripts/provar_visual_proof_hermetico.py --json
    python3 scripts/provar_visual_proof_hermetico.py --autoteste

## Por que uma prova estrutural, e não "rodamos e nada aconteceu"

"Nenhuma chamada real aconteceu" é uma afirmação sobre uma execução; "nenhuma
chamada real PODE acontecer a partir deste código" é uma afirmação sobre o
repositório. A segunda é a que sobrevive ao próximo agente que rodar a suíte
sem ler o handoff, e é a que este script mede.

Ele lê os arquivos que esta entrega adicionou ou alterou e recusa se encontrar:

  1. endpoint de AdsPower fora de loopback (nuvem do fornecedor, `local.adspower.net`);
  2. driver de navegador real (puppeteer, playwright, selenium, webdriver);
  3. escrita no Supabase oficial (`database.agenciavolc.com.br`, RPC de escrita);
  4. migração SQL nova (esta missão não escreveu schema);
  5. caminho de publicação (Postiz, `publicacao_organica`, Meta/Facebook Graph);
  6. valor sentinela ou material de credencial no código versionado;
  7. `--no-masking` em qualquer lugar;
  8. arquivo fora da propriedade da missão.

⚠️ **Alcance honesto.** Isto é análise de texto e de AST sobre um conjunto
declarado de arquivos. Não prova que a suíte não abriu socket — quem prova isso
é o duplê em `127.0.0.1:0` e a ausência de driver real, que a checagem 2 cobre.
Também não substitui revisão humana do diff.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

#: ## Os dois escopos, e por que eles têm regras diferentes
#:
#: `PRODUCAO` é o código que roda: se um endereço de AdsPower na nuvem aparecer
#: aqui, alguém consegue chamá-lo. `PROVAS` são os testes e este próprio script:
#: eles CITAM as strings proibidas de propósito — um teste que afirma
#: `assert "op://" not in recibo` é prova de contenção, não vazamento dela.
#:
#: Aplicar as mesmas regras aos dois escopos produziria o pior tipo de gate: um
#: que acusa a própria evidência e que, para ficar verde, seria afrouxado até
#: não medir mais nada.
PRODUCAO: tuple[str, ...] = (
    "backend/app/visual_proof/__init__.py",
    "backend/app/visual_proof/dominio.py",
    "backend/app/visual_proof/aplicacao.py",
    "backend/app/visual_proof/infraestrutura.py",
    "backend/app/asset_vault/rotas.py",
    "tools/adspower-broker/broker/__init__.py",
    "tools/adspower-broker/broker/__main__.py",
    "tools/adspower-broker/broker/adspower.py",
    "tools/adspower-broker/broker/configuracao.py",
    "tools/adspower-broker/broker/execucao.py",
    "tools/adspower-broker/broker/segredo.py",
    "tools/adspower-broker/broker/servidor.py",
    "src/features/asset-vault/prontidao.ts",
    "src/features/asset-vault/ProntidaoVisual.tsx",
    "src/features/asset-vault/cofreApi.ts",
    "src/features/asset-vault/AssetVaultContent.tsx",
)

#: Duplês e testes. Rodam as checagens de CONTENÇÃO (sentinela, `op://` real),
#: não as de alcance externo.
PROVAS: tuple[str, ...] = (
    "tools/adspower-broker/fake/__init__.py",
    "tools/adspower-broker/fake/adspower.py",
    "tools/adspower-broker/fake/navegador.py",
    "backend/tests/test_visual_proof_dominio.py",
    "backend/tests/test_visual_proof_controle.py",
    "backend/tests/test_visual_proof_fronteira_cofre.py",
    "backend/tests/test_adspower_broker_hermetico.py",
    "backend/tests/test_cofre_prontidao_visual.py",
    "src/features/asset-vault/__tests__/prontidao.test.ts",
    "src/features/asset-vault/__tests__/prontidao-visual.test.tsx",
    "scripts/provar_visual_proof_hermetico.py",
)

ARQUIVOS_DA_ENTREGA: tuple[str, ...] = PRODUCAO + PROVAS

#: Caminhos que a missão NÃO pode ter tocado (Terminal 1, Terminal 2 e as
#: autoridades compartilhadas). Comparado contra o `git status`.
PROPRIEDADE_PROIBIDA: tuple[str, ...] = (
    "backend/app/criativo/bancada/", "backend/app/routers/criativos_execucao.py",
    "backend/tests/test_criativo_", "deploy/creative-worker/", "volc_ads/criativo/",
    "src/components/criativos/", "src/pages/criativos/",
    "backend/app/publicacao_organica/", "backend/app/routers/publicacao.py",
    "backend/tests/test_publicacao_organica", "src/components/publicacao/",
    "src/types/publicacao.ts", "deploy/postiz/", "infra/postiz/",
    "volc-os-workbook/ROADMAP-VIVO.json",
    "docs/volc-os-graph/curadoria-operacional.json",
    "docs/volc-os-graph/volc-os-graph.json", "graphify-out/",
    "supabase/migrations/",
)

# ── as oito checagens ───────────────────────────────────────────────────────

#: 1. AdsPower fora de loopback. `local.adspower.net` é endereço OFICIAL e
#: documentado — e é justamente por ser um NOME que ele está proibido: quem
#: editar `/etc/hosts` muda para onde a chave da Local API é enviada.
ADSPOWER_FORA_DE_LOOPBACK = re.compile(
    r"local\.adspower\.net"
    r"|https?://(?!127\.|\[?::1\]?|local_?host_?fake)[A-Za-z0-9.-]*adspower\.(?:com|net|io)"
)

#: 2. Driver de navegador real. Nenhum é importado nesta entrega: o único
#: caminho de captura implementado fala com o duplê, e o driver real recusa.
DRIVER_REAL = re.compile(
    r"^\s*(?:import|from)\s+(?:pyppeteer|playwright|selenium|undetected_chromedriver)\b"
    r"|require\(['\"](?:puppeteer|playwright|selenium-webdriver)['\"]\)"
    r"|from\s+['\"](?:puppeteer|playwright|selenium-webdriver)['\"]",
    re.MULTILINE,
)

#: 3. Supabase oficial. Nem host, nem cliente, nem RPC de escrita.
SUPABASE_OFICIAL = re.compile(
    r"database\.agenciavolc\.com\.br"
    r"|SUPABASE_SERVICE_ROLE_KEY"
    r"|rest/v1/rpc/cofre_(?:cadastrar|revisar|relacionar|aposentar|reativar|registrar|referenciar)"
)

#: 5. Caminho de publicação. Esta entrega não publica nada em lugar nenhum.
PUBLICACAO = re.compile(
    # Sem `\b` de fechamento: `PostizClient` e `postiz_adapter` também contam.
    r"\bpostiz"
    r"|publicacao_organica"
    r"|graph\.facebook\.com"
    r"|/me/feed"
    r"|\bmultipost",
    re.IGNORECASE,
)

#: 6. Material de credencial e sentinelas de teste no código versionado. As
#: sentinelas dos testes são declaradas como CONSTANTE nos próprios testes, e
#: por isso a checagem ignora a linha que as define — o que ela procura é a
#: sentinela ESCAPANDO para outro arquivo, e material de credencial de verdade.
MATERIAL_DE_CREDENCIAL = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY"
    # `eyJhbGciOiJIUzI1NiJ9` tem 17 caracteres depois de `eyJ`: exigir 20 fazia
    # a checagem perder o cabeçalho de JWT mais comum que existe.
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."
    r"|\b(?:sk|ghp|gho|xox[baprs])[-_][A-Za-z0-9]{20,}"
)

#: `op://` com CAMINHO de verdade — cofre e item de dois caracteres ou mais.
#:
#: A forma frouxa (`op://` puro) acusava o próprio código que trata o esquema:
#: o `re.compile("op://[^\\n\\r]*")` do sanitizador e o
#: `startswith(("op://", …))` do preflight são o oposto de um vazamento. O que
#: interessa é um ENDEREÇO, e endereço tem segmentos.
#: Os únicos endereços `op://` que podem aparecer no repositório. Todos apontam
#: para itens que não existem em cofre nenhum — são forma, não conteúdo.
#: `Pagina%20Piloto` é a forma percent-encoded, que é a que o placeholder do
#: formulário do Cofre já usava antes desta entrega.
_EXEMPLOS_DECLARADOS = (
    "op://VOLC/Perfil Piloto/",
    "op://VOLC/Pagina Piloto/",
    "op://VOLC/Pagina%20Piloto/",
    #: Vetor NEGATIVO do autoteste deste script: ele precisa de um endereço que
    #: a checagem PEGUE, para provar que a checagem não é vácua.
    "op://Producao/Conta Real/",
)
LOCALIZADOR_SUSPEITO = re.compile(r"op://[A-Za-z0-9._%~ -]{2,}/[A-Za-z0-9._%~ -]{2,}/")

#: 7. A flag que desliga o mascaramento do 1Password. Só pode aparecer como
#: item de uma lista de PROIBIDAS.
NO_MASKING = re.compile(r"--no-masking")

SENTINELAS_ESPERADAS = (
    "VOLC-SENTINELA-ADSPOWER-9f3c71b8d24e5a06",
    "VOLC-SENTINELA-SEGREDO-4c1f9a2b7e",
)

#: Arquivos onde a sentinela pode nascer. Fora deles, ela é vazamento.
DONOS_DE_SENTINELA = (
    "backend/tests/test_adspower_broker_hermetico.py",
    "backend/tests/test_visual_proof_dominio.py",
    "scripts/provar_visual_proof_hermetico.py",
)


class Achado(Exception):
    pass


def _linhas(texto: str, padrao: re.Pattern[str]) -> list[tuple[int, str]]:
    """Devolve `(numero, linha INTEIRA)`.

    ⚠️ A primeira versão já truncava aqui, em 120 caracteres — e o filtro de
    exemplos declarados rodava depois, sobre o texto cortado. O efeito era que
    `op://VOLC/Perfil Piloto/…`, no fim de uma linha longa, era acusado como
    localizador real: a parte que provava ser um exemplo tinha sido cortada
    antes de alguém olhar. Truncar é decisão de APRESENTAÇÃO, e agora acontece
    depois de filtrar.
    """
    return [
        (numero, linha.strip())
        for numero, linha in enumerate(texto.splitlines(), start=1)
        if padrao.search(linha)
    ]


def _sem_comentarios_python(fonte: str) -> str:
    """Tira docstrings e comentários: eles CITAM o que o código não faz.

    Sem isto, o docstring de `adspower.py` — que documenta a fonte oficial
    `local.adspower.net` para explicar por que ela é recusada — acusaria o
    próprio arquivo que a recusa.
    """
    try:
        arvore = ast.parse(fonte)
    except SyntaxError:
        return fonte
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            corpo = getattr(no, "body", [])
            if (corpo and isinstance(corpo[0], ast.Expr)
                    and isinstance(corpo[0].value, ast.Constant)
                    and isinstance(corpo[0].value.value, str)):
                corpo[0].value.value = ""
    limpo = ast.unparse(arvore)
    return "\n".join(l for l in limpo.splitlines() if not l.strip().startswith("#"))


def _sem_comentarios_ts(fonte: str) -> str:
    sem_bloco = re.sub(r"/\*.*?\*/", "", fonte, flags=re.DOTALL)
    return "\n".join(
        l for l in sem_bloco.splitlines() if not l.strip().startswith("//"))


def limpar(caminho: Path, fonte: str) -> str:
    if caminho.suffix == ".py":
        return _sem_comentarios_python(fonte)
    if caminho.suffix in (".ts", ".tsx"):
        return _sem_comentarios_ts(fonte)
    return fonte


def provar(raiz: Path = RAIZ) -> dict:
    """Roda as oito checagens e devolve o relatório. Levanta `Achado` se falhar."""
    relatorio: dict[str, object] = {"arquivos": 0, "checagens": {}, "falhas": []}
    falhas: list[str] = []
    codigo: dict[str, str] = {}

    for relativo in ARQUIVOS_DA_ENTREGA:
        caminho = raiz / relativo
        if not caminho.is_file():
            falhas.append(f"{relativo}: arquivo declarado na entrega não existe")
            continue
        codigo[relativo] = caminho.read_text(encoding="utf-8")
    relatorio["arquivos"] = len(codigo)

    def checar(nome: str, padrao: re.Pattern[str], escopo: tuple[str, ...], *,
               ignorar: tuple[str, ...] = (),
               permitidos: tuple[str, ...] = ()) -> None:
        atingidos: list[str] = []
        for relativo in escopo:
            fonte = codigo.get(relativo)
            if fonte is None or relativo in ignorar:
                continue
            alvo = limpar(raiz / relativo, fonte)
            for numero, linha in _linhas(alvo, padrao):
                # Filtra sobre a linha INTEIRA; trunca só para exibir.
                if any(exemplo in linha for exemplo in permitidos):
                    continue
                atingidos.append(f"{relativo} · linha {numero}: {linha[:120]}")
        relatorio["checagens"][nome] = {
            "escopo": "producao" if escopo is PRODUCAO else "provas",
            "arquivos": len(escopo),
            "ocorrencias": len(atingidos), "onde": atingidos[:8],
        }
        if atingidos:
            falhas.extend(f"[{nome}] {a}" for a in atingidos[:8])

    # ── alcance externo: só sobre código de PRODUÇÃO ────────────────────────
    checar("adspower_fora_de_loopback", ADSPOWER_FORA_DE_LOOPBACK, PRODUCAO)
    checar("driver_de_navegador_real", DRIVER_REAL, PRODUCAO)
    checar("supabase_oficial", SUPABASE_OFICIAL, PRODUCAO)
    checar("caminho_de_publicacao", PUBLICACAO, PRODUCAO)
    checar("material_de_credencial", MATERIAL_DE_CREDENCIAL, PRODUCAO)

    # ── contenção: vale nos DOIS escopos ────────────────────────────────────
    #
    # Um `op://` com caminho real não pode existir em lugar nenhum — nem num
    # teste. Os dois exemplos declarados (`VOLC/Perfil Piloto`, `VOLC/Pagina
    # Piloto`) apontam para itens que não existem em cofre nenhum.
    checar("localizador_real", LOCALIZADOR_SUSPEITO, PRODUCAO,
           permitidos=_EXEMPLOS_DECLARADOS)
    checar("localizador_real_nas_provas", LOCALIZADOR_SUSPEITO, PROVAS,
           permitidos=_EXEMPLOS_DECLARADOS)
    # `--no-masking` só é legítima na lista de PROIBIDAS do preflight.
    checar("no_masking", NO_MASKING, PRODUCAO,
           ignorar=("tools/adspower-broker/broker/configuracao.py",))

    # Sentinela escapando do arquivo que a define.
    escapou: list[str] = []
    for relativo, fonte in codigo.items():
        if relativo in DONOS_DE_SENTINELA:
            continue
        for sentinela in SENTINELAS_ESPERADAS:
            if sentinela in fonte:
                escapou.append(f"{relativo}: sentinela vazou para fora do teste que a define")
    relatorio["checagens"]["sentinela_contida"] = {
        "ocorrencias": len(escapou), "onde": escapou[:8]}
    falhas.extend(escapou)

    # 4. Nenhuma migração nova + 8. propriedade respeitada.
    tocados = _arquivos_tocados(raiz)
    relatorio["arquivos_tocados"] = len(tocados)
    invadidos = sorted(
        t for t in tocados if any(t.startswith(p) for p in PROPRIEDADE_PROIBIDA))
    relatorio["checagens"]["propriedade_respeitada"] = {
        "ocorrencias": len(invadidos), "onde": invadidos[:8]}
    falhas.extend(f"[propriedade] {i}" for i in invadidos)

    migracoes = sorted(t for t in tocados if t.startswith("supabase/migrations/"))
    relatorio["checagens"]["sem_migracao_nova"] = {
        "ocorrencias": len(migracoes), "onde": migracoes}
    falhas.extend(f"[migracao] {m}" for m in migracoes)

    # O driver real precisa CONTINUAR recusando. É a checagem que não é textual.
    relatorio["checagens"]["driver_real_recusa"] = {
        "ocorrencias": 0 if _driver_real_recusa(raiz) else 1, "onde": []}
    if not _driver_real_recusa(raiz):
        falhas.append("[driver] NavegadorNaoImplementado deixou de recusar")

    relatorio["falhas"] = falhas
    relatorio["veredito"] = "hermetico" if not falhas else "recusado"
    if falhas:
        raise Achado("\n".join(falhas))
    return relatorio


def _arquivos_tocados(raiz: Path) -> list[str]:
    try:
        saida = subprocess.run(  # noqa: S603
            ["git", "status", "--porcelain"], cwd=str(raiz),
            capture_output=True, text=True, timeout=60, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    tocados: list[str] = []
    for linha in saida.splitlines():
        caminho = linha[3:].strip().strip('"')
        if caminho.endswith("/"):
            tocados.append(caminho)
        elif caminho:
            tocados.append(caminho)
    return tocados


def _driver_real_recusa(raiz: Path) -> bool:
    """Importa o driver real e confirma que `capturar` levanta.

    Checagem de COMPORTAMENTO, não de texto: se alguém implementar a captura de
    verdade, nenhum regex pegaria — mas esta linha pega.
    """
    sys.path.insert(0, str(raiz / "backend"))
    sys.path.insert(0, str(raiz / "tools" / "adspower-broker"))
    try:
        from app.visual_proof import dominio as dom  # noqa: PLC0415
        from broker.adspower import (  # noqa: PLC0415
            CheckpointExterno, NavegadorNaoImplementado,
        )
    except ImportError:
        return False
    try:
        NavegadorNaoImplementado().capturar(
            ws_endpoint="ws://127.0.0.1:1/devtools/browser/x",
            url="https://exemplo.invalid/", viewport=dom.Viewport(largura=800, altura=600),
            timezone=None, timeout_s=1)
    except CheckpointExterno:
        return True
    except Exception:  # noqa: BLE001
        return False
    return False


# ── autoteste ───────────────────────────────────────────────────────────────


def autoteste() -> int:
    """Prova que as checagens NÃO são vácuas — cada uma pega o que promete."""
    casos = [
        ("adspower na nuvem", ADSPOWER_FORA_DE_LOOPBACK, "base = 'https://api.adspower.com'", True),
        ("adspower por nome", ADSPOWER_FORA_DE_LOOPBACK, "http://local.adspower.net:50325", True),
        ("adspower loopback", ADSPOWER_FORA_DE_LOOPBACK, "http://127.0.0.1:50325", False),
        ("puppeteer", DRIVER_REAL, "import pyppeteer", True),
        ("playwright js", DRIVER_REAL, "from 'playwright'", True),
        ("sem driver", DRIVER_REAL, "from broker.adspower import Navegador", False),
        ("supabase host", SUPABASE_OFICIAL, "https://database.agenciavolc.com.br", True),
        ("supabase rpc de escrita", SUPABASE_OFICIAL, "rest/v1/rpc/cofre_cadastrar_ativo", True),
        ("supabase leitura", SUPABASE_OFICIAL, "rest/v1/rpc/cofre_listar_ativos", False),
        ("postiz", PUBLICACAO, "adapter = PostizClient()", True),
        ("graph api", PUBLICACAO, "https://graph.facebook.com/v20.0/me/feed", True),
        ("sem publicacao", PUBLICACAO, "montar_prontidao(handoff=h)", False),
        (
            "pem",
            MATERIAL_DE_CREDENCIAL,
            "-----" + "BEGIN RSA " + "PRIVATE KEY" + "-----",
            True,
        ),
        ("jwt", MATERIAL_DE_CREDENCIAL,
         "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc", True),
        ("texto comum", MATERIAL_DE_CREDENCIAL, "o recibo nao carrega segredo", False),
        ("no-masking", NO_MASKING, "argv = ['op', 'run', '--no-masking']", True),
        # A regex pega QUALQUER endereço com caminho; quem separa exemplo de
        # endereço real é `_EXEMPLOS_DECLARADOS`, testado logo abaixo.
        ("localizador com caminho", LOCALIZADOR_SUSPEITO,
         "op://Producao/Conta Real/senha", True),
        ("esquema sem caminho não conta", LOCALIZADOR_SUSPEITO,
         're.compile("op://[^\\n\\r]*")', False),
        ("startswith do preflight não conta", LOCALIZADOR_SUSPEITO,
         "self.localizador.startswith(('op://', 'bw://'))", False),
    ]
    falhas = 0
    for nome, padrao, amostra, deve_pegar in casos:
        pegou = bool(padrao.search(amostra))
        if pegou != deve_pegar:
            print(f"  ✗ {nome}: esperava pegar={deve_pegar}, pegou={pegou}")
            falhas += 1
        else:
            print(f"  ✓ {nome}")

    # A allowlist de exemplos precisa deixar passar o exemplo E pegar o real —
    # senão ela vira um jeito silencioso de desligar a checagem.
    linha_de_exemplo = 'perfil = {"localizador": "op://VOLC/Perfil Piloto/ADSPOWER_API_KEY"}'
    # Montada em pedaços de propósito: escrita por extenso, ela seria um
    # endereço literal no repositório — e a própria checagem a acusaria, com
    # razão. Este script fica sujeito à regra que aplica.
    linha_real = 'segredo = "op://' + "Cofre Alheio/Conta do Cliente" + '/senha"'
    if not any(e in linha_de_exemplo for e in _EXEMPLOS_DECLARADOS):
        print("  ✗ a allowlist não reconhece o exemplo declarado")
        falhas += 1
    elif any(e in linha_real for e in _EXEMPLOS_DECLARADOS):
        print("  ✗ a allowlist deixaria passar um endereço real")
        falhas += 1
    elif not LOCALIZADOR_SUSPEITO.search(linha_real):
        print("  ✗ a checagem não pega um endereço real")
        falhas += 1
    else:
        print("  ✓ allowlist separa exemplo declarado de endereço real")

    # A limpeza de comentários não pode apagar código.
    limpo = _sem_comentarios_python(
        '"""doc que cita local.adspower.net"""\nbase = "http://127.0.0.1:50325"\n')
    if "local.adspower.net" in limpo:
        print("  ✗ limpeza de docstring não removeu a citação")
        falhas += 1
    elif "127.0.0.1:50325" not in limpo:
        print("  ✗ limpeza de docstring apagou o código")
        falhas += 1
    else:
        print("  ✓ limpeza de docstring preserva código e remove citação")

    print(f"\n{len(casos) + 2} provas, {falhas} falha(s).")
    return 1 if falhas else 0


def principal(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prova estrutural de hermetismo do plano de controle de prova visual.")
    parser.add_argument("--json", action="store_true", help="relatório em JSON")
    parser.add_argument("--autoteste", action="store_true",
                        help="prova que as checagens não são vácuas")
    args = parser.parse_args(argv)

    if args.autoteste:
        return autoteste()

    try:
        relatorio = provar()
    except Achado as achado:
        print("RECUSADO — a entrega não é hermética:\n", file=sys.stderr)
        print(str(achado), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    else:
        print(f"veredito: {relatorio['veredito']}")
        print(f"arquivos da entrega conferidos: {relatorio['arquivos']}")
        print(f"arquivos tocados na árvore: {relatorio['arquivos_tocados']}")
        for nome, dados in relatorio["checagens"].items():  # type: ignore[union-attr]
            print(f"  {nome}: {dados['ocorrencias']} ocorrência(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
