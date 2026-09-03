#!/usr/bin/env python3
"""Roda o portão de destino pago sobre a EVIDÊNCIA PRESERVADA e emite recibos.

## O que este script é

O ponto de entrada operacional do `backend/app/landing_policy`. Ele não decide
nada: quem decide é o portão. Aqui só se resolve qual HTML corresponde a qual
URL, se monta a `PaginaObservada` com o que a preservação registrou, e se grava
o recibo — o artefato que sobrevive à sessão.

## Três modos, e por que separados

    --evidencia   avalia o HTML já preservado no pacote de fechamento. É o modo
                  padrão: roda offline, é determinístico e pode ser repetido por
                  qualquer pessoa sem tocar no site.
    --matriz      escreve a cópia da matriz de política no pacote de fechamento
                  a partir da fonte canônica que vive junto do código.
    --ao-vivo     lê UMA url pública duas vezes (usuário e rastreador), preserva
                  a cadeia de redirecionamento e avalia. É o único modo que fala
                  com a rede, e é o único que consegue responder cloaking e
                  deriva — as duas verificações que o modo offline declara
                  honestamente como `unavailable`.

Nenhum modo escreve no site, na conta do Google ou em qualquer lugar fora de
`docs/closure/...`. Não há caminho de mutação neste arquivo.

Uso:
    python3 scripts/auditar_landing_policy.py --evidencia
    python3 scripts/auditar_landing_policy.py --matriz
    python3 scripts/auditar_landing_policy.py --ao-vivo https://exemplo.com.br/r/x/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

FECHAMENTO = RAIZ / "docs" / "closure" / "hermes-redator-google-ads-policy-incident-v1"
EVIDENCIA = FECHAMENTO / "evidence-public"
RECIBOS = FECHAMENTO / "GATE-RECEIPTS.json"
MATRIZ = FECHAMENTO / "GOOGLE-POLICY-MATRIX.json"

CNPJ_DO_OPERADOR = "42.724.548/0001-24"
PAUSA_S = 3.0

#: A preservação nomeia os arquivos de duas formas. `public-lp-snapshot.json`
#: guarda a URL das três primeiras variantes; os arquivos `r-<slug>-<sha>.html`
#: carregam o slug no nome. Resolver isso aqui evita repetir o mapa em prosa.
_ARQUIVO_R_RE = re.compile(r"^r-(?P<slug>.+)-(?P<sha>[0-9a-f]{12})\.html$")


def _sha(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _url_das_variantes() -> tuple[str | None, dict[str, str]]:
    """URL e mapa `rótulo de user-agent -> sha256`, do snapshot preservado."""
    arquivo = EVIDENCIA / "public-lp-snapshot.json"
    if not arquivo.is_file():
        return None, {}
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    variantes = {
        rotulo: (v.get("html_sha256") or "")
        for rotulo, v in (dados.get("variants") or {}).items()
        if v.get("html_sha256")
    }
    return dados.get("requested_url"), variantes


def _alvos() -> list[dict]:
    """Cada HTML preservado, com a URL que ele representa."""
    url_snapshot, variantes = _url_das_variantes()
    alvos: list[dict] = []
    for arquivo in sorted(EVIDENCIA.glob("*.html")):
        nome = arquivo.name
        casamento = _ARQUIVO_R_RE.match(nome)
        if casamento:
            url = f"https://creditoup.com.br/r/{casamento.group('slug')}/"
            vars_ = {}
        elif url_snapshot:
            url = url_snapshot
            # As três variantes do snapshot são a MESMA url lida com user-agents
            # diferentes: é isso que torna a comparação de cloaking possível.
            vars_ = variantes
        else:
            continue
        alvos.append({"arquivo": arquivo, "url": url, "variantes": vars_})
    return alvos


def auditar_evidencia() -> dict:
    from app.landing_policy import (
        PaginaObservada,
        elegibilidade_de_destino_de_campanha,
        emitir_recibo,
        sem_fonte_oficial,
        versao_da_fonte,
    )

    # (url, sha) -> recibo. Dois arquivos preservados podem ser o MESMO conteúdo
    # — `common_desktop` e `googlebot` saíram byte a byte iguais, que é justamente
    # a evidência de ausência de cloaking. Emitir o recibo duas vezes não
    # acrescenta evidência; acrescenta ruído que parece contagem.
    por_conteudo: dict[tuple[str, str], dict] = {}
    for alvo in _alvos():
        arquivo: Path = alvo["arquivo"]
        sha = _sha(arquivo)
        referencia = str(arquivo.relative_to(RAIZ))
        chave = (alvo["url"], sha)
        if chave in por_conteudo:
            por_conteudo[chave]["evidence_refs"] = sorted(
                set(por_conteudo[chave]["evidence_refs"]) | {referencia}
            )
            continue
        pagina = PaginaObservada(
            url=alvo["url"],
            html=arquivo.read_text(encoding="utf-8", errors="replace"),
            status_http=200,
            # A preservação registrou que não houve salto; sem essa afirmação o
            # portão trataria redirecionamento como não observado, e é isso que
            # ele deve fazer quando ninguém mediu.
            saltos_redirecionamento=[],
            variantes_sha256=alvo["variantes"],
            sha256_observado=sha,
            cnpj_esperado=CNPJ_DO_OPERADOR,
            origem="preserved_public_artifact",
        )
        avaliacao = elegibilidade_de_destino_de_campanha(pagina)
        orfaos = sem_fonte_oficial(avaliacao)
        if orfaos:
            raise SystemExit(f"regra sem fonte oficial: {orfaos}")
        por_conteudo[chave] = emitir_recibo(
            avaliacao, hash_do_conteudo=sha, referencias_de_evidencia=[referencia]
        )

    recibos = list(por_conteudo.values())
    return {
        "schema": "LandingPolicyGateReceipts.v1",
        "generated_by": "scripts/auditar_landing_policy.py --evidencia",
        "policy_source_version": versao_da_fonte(),
        "source": "preserved public HTML only — no live read in this mode",
        "external_mutation": {
            "google_ads_mutate": False,
            "wordpress_write": False,
            "appeal_submitted": False,
            "deploy": False,
        },
        "counts": {
            "receipts": len(recibos),
            "ready": sum(1 for r in recibos if r["paid_destination_ready"]),
            "blocked": sum(1 for r in recibos if r["verdict"] == "blocked"),
        },
        "receipts": sorted(recibos, key=lambda r: (r["url"], r["content_sha256"])),
    }


def escrever_matriz() -> dict:
    """Cópia da matriz canônica para o pacote de fechamento.

    A fonte é `backend/app/landing_policy/fontes_politica.json`, que vive junto
    do código que a aplica — editar a cópia é trabalho perdido, e o cabeçalho
    diz isso para quem abrir o arquivo daqui a seis semanas.
    """
    from app.landing_policy import carregar_fontes, codigos_conhecidos, versao_da_fonte

    fontes = carregar_fontes()
    conhecidos = codigos_conhecidos()
    faltando = sorted(c for c in conhecidos if c not in fontes["rules"])
    sobrando = sorted(set(fontes["rules"]) - conhecidos)
    if faltando or sobrando:
        raise SystemExit(f"matriz fora de sincronia · faltando={faltando} sobrando={sobrando}")
    return {
        "_generated": {
            "by": "scripts/auditar_landing_policy.py --matriz",
            "from": "backend/app/landing_policy/fontes_politica.json",
            "do_not_edit_here": "edit the canonical file next to the code; this copy is rewritten",
            "policy_source_version": versao_da_fonte(fontes),
            "rule_count": len(fontes["rules"]),
        },
        **fontes,
    }


def auditar_ao_vivo(url: str) -> dict:
    """Duas leituras públicas da MESMA url, com user-agents diferentes."""
    from app.landing_policy import (
        PaginaObservada,
        elegibilidade_de_destino_de_campanha,
        emitir_recibo,
    )
    from app.publisher_quality.fetch import USER_AGENT_PADRAO, fetch_public_https_chain

    UA_RASTREADOR = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    leituras = {}
    for rotulo, ua in (("user", USER_AGENT_PADRAO), ("googlebot", UA_RASTREADOR)):
        leituras[rotulo] = fetch_public_https_chain(url, user_agent=ua)
        time.sleep(PAUSA_S)

    principal = leituras["user"]
    pagina = PaginaObservada(
        url=principal["final_url"],
        html=principal["html"],
        status_http=int(principal["status"]),
        saltos_redirecionamento=list(principal["hops"]),
        cabecalhos=dict(principal["headers"]),
        variantes_sha256={k: v["sha256"] for k, v in leituras.items()},
        sha256_observado=principal["sha256"],
        cnpj_esperado=CNPJ_DO_OPERADOR,
        origem="live_public_read",
        observado_em=datetime.now(timezone.utc).isoformat(),
    )
    avaliacao = elegibilidade_de_destino_de_campanha(pagina)
    return emitir_recibo(
        avaliacao,
        hash_do_conteudo=principal["sha256"],
        carimbo=pagina.observado_em,
        referencias_de_evidencia=[f"live read {rotulo}" for rotulo in sorted(leituras)],
    )


def _gravar(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evidencia", action="store_true", help="avalia o HTML preservado")
    ap.add_argument("--matriz", action="store_true", help="escreve a cópia da matriz de política")
    ap.add_argument("--ao-vivo", metavar="URL", help="lê uma url pública e avalia")
    ap.add_argument("--saida", type=Path)
    args = ap.parse_args()

    if not (args.evidencia or args.matriz or args.ao_vivo):
        args.evidencia = args.matriz = True

    if args.matriz:
        # ⚠️ `--saida` com `--matriz` E `--evidencia` juntos é ambíguo: são dois
        # artefatos e um destino só. Recusar é mais honesto que escolher por
        # conta própria — foi exatamente a escolha implícita que apagava a
        # evidência antes.
        if args.saida and args.evidencia:
            print(
                "erro · --saida não pode servir a --matriz e --evidencia na mesma "
                "chamada: são dois artefatos e um destino. Rode duas vezes.",
                file=sys.stderr,
            )
            return 2
        matriz = escrever_matriz()
        destino_matriz = args.saida or MATRIZ
        _gravar(destino_matriz, matriz)
        print(f"ok · matriz com {matriz['_generated']['rule_count']} regras → {destino_matriz}")

    if args.evidencia:
        # ⚠️ ISTO ERA UM BUG DESTRUTIVO DE PRECEDÊNCIA, e ele apagava evidência.
        #
        # A expressão anterior era
        #     args.saida or RECIBOS if not args.matriz else RECIBOS
        # que o Python lê como
        #     (args.saida or RECIBOS) if (not args.matriz) else RECIBOS
        # — ou seja, `--matriz --evidencia --saida X` escrevia a MATRIZ em X e
        # sobrescrevia `GATE-RECEIPTS.json` IN PLACE, sem backup. Esse arquivo é
        # citado como evidência E6 pelo pacote de apelação; perdê-lo por uma
        # combinação de flags seria destruir prova com um comando de leitura.
        #
        # `--saida`, quando dado, manda. Sempre. Um destino explícito não pode
        # ser silenciosamente ignorado por causa de outra flag.
        recibos = auditar_evidencia()
        destino_recibos = args.saida or RECIBOS
        _gravar(destino_recibos, recibos)
        c = recibos["counts"]
        # E o caminho impresso é o caminho ESCRITO. Antes ele dizia sempre
        # `RECIBOS`, mesmo tendo escrito noutro lugar — um relatório que mente
        # sobre onde pôs o arquivo é como se descobre o arquivo errado depois.
        print(f"ok · {c['receipts']} recibos · {c['blocked']} bloqueados · "
              f"{c['ready']} prontos → {destino_recibos}")

    if args.ao_vivo:
        recibo = auditar_ao_vivo(args.ao_vivo)
        print(json.dumps(recibo, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
