#!/usr/bin/env python3
"""Gera o dossiê canônico do canário v10 — e NÃO cria campanha nenhuma.

    backend/.venv/bin/python scripts/dossie_canario_v10.py [--repeticoes 3]

## Por que este arquivo existe

O payload exato do futuro `POST /api/trafego/subir` vivia num script em `/tmp`.
O que autoriza uma escrita real precisa ser lido, revisado e diferenciado — e
`/tmp` some no reboot. O corpo agora é
`docs/closure/search-production-closure-v1/canario-v10-payload.json`, versionado,
e este script apenas o lê, roda `validate_only` e escreve o dossiê.

## O que ele faz, e o que ele nunca faz

FAZ: lê a conta (GAQL), roda `validate_only` N vezes, prova que a identidade é
estável, confere duplicidade por marca e por destino, e emite um JSON canônico
com hash próprio.

NUNCA: `mutate`. Nenhuma operação de escrita é construída em lugar nenhum deste
arquivo. `validate_only` não cria recurso em desfecho nenhum.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = RAIZ / "docs" / "closure" / "search-production-closure-v1" / "canario-v10-payload.json"
SAIDA = RAIZ / "docs" / "closure" / "search-production-closure-v1" / "DOSSIE-CANARIO-V10.json"


def _ambiente() -> None:
    """Carrega SUPABASE_* do `.env.server` sem imprimir nada."""
    for base in (RAIZ, pathlib.Path("/Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign")):
        env = base / ".env.server"
        if not env.exists():
            continue
        for linha in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", linha)
            if m:
                os.environ.setdefault(m.group(1), m.group(2).strip().strip('"').strip("'"))
        return


def principal() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repeticoes", type=int, default=3,
                    help="quantas vezes rodar o validate_only (default 3)")
    args = ap.parse_args()

    _ambiente()
    sys.path.insert(0, str(RAIZ))
    sys.path.insert(0, str(RAIZ / "backend"))
    import asyncio

    from app.routers import trafego
    from app.seguranca.identidade import Identidade
    from app.trafego import canario, contas as ct

    pedido = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    corpo_http = {k: v for k, v in pedido.items() if not k.startswith("_")}
    identidade = Identidade(sub="dossie", email="tarcisio@agenciavolc.com.br",
                            papel="ADMIN", origem="dossie-canario-v10")

    async def rodar():
        execucoes = []
        operacoes = None
        for i in range(args.repeticoes):
            corpo = trafego.ProvarEntrada(**corpo_http)
            cid, mid = trafego._no_escopo(corpo.customer_id, corpo.login_customer_id)
            corpo.carimbo_nome = canario.carimbo_do_nome(corpo.carimbo_nome)
            chave = trafego._impressao_aprovavel(corpo, cid=cid, mid=mid)
            plano_ledger = trafego.plano_do_ledger(corpo, cid=cid, mid=mid)

            if operacoes is None:
                import volc_ads.subir as sbm
                original = sbm.validar_mutacoes
                capturado: dict = {}

                def espiao(customer_id, ops, *, login_customer_id):
                    capturado["ops"] = list(ops)
                    return original(customer_id, ops, login_customer_id=login_customer_id)

                sbm.validar_mutacoes = espiao
                r = await trafego.provar(corpo, identidade=identidade)
                sbm.validar_mutacoes = original
                operacoes = capturado.get("ops", [])
            else:
                r = await trafego.provar(corpo, identidade=identidade)

            execucoes.append({
                "carimbo_nome": corpo.carimbo_nome,
                "chave_intencao": chave,
                "marca_remota": canario.prefixo_da_marca(chave),
                # ⚠️ NOMES SEPARADOS PORQUE SÃO COISAS DIFERENTES.
                # `blueprint_sha256` é o hash do plano canônico do ledger, que
                # NÃO contém o carimbo: mesma intenção → mesmo blueprint, sempre.
                # `selo_do_executor` é o hash do protobuf, e ele VARIA por
                # execução porque o nome da campanha carrega o carimbo. Chamar
                # os dois de "fingerprint" faria um deles parecer instável.
                "blueprint_sha256": hashlib.sha256(json.dumps(
                    trafego.plano_do_ledger(corpo, cid=cid, mid=mid),
                    sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False).encode("utf-8")).hexdigest(),
                "selo_do_executor": (r["preparo"].get("selo") or {}).get("impressao"),
                "n_operacoes": r["preparo"]["n_operacoes"],
                "aprovado": r["preparo"]["aprovado"],
                "recusa_local": r["preparo"].get("recusa_local"),
                "falha_validacao": r["preparo"].get("falha_validacao"),
                "avisos": r.get("avisos"),
            })
            ultimo = r
        return execucoes, operacoes, ultimo, plano_ledger

    execucoes, operacoes, ultimo, plano_ledger = asyncio.run(rodar())

    chaves = {e["chave_intencao"] for e in execucoes}
    marcas = {e["marca_remota"] for e in execucoes}
    carimbos = {e["carimbo_nome"] for e in execucoes}
    n_ops = {e["n_operacoes"] for e in execucoes}
    if len(chaves) != 1 or len(marcas) != 1:
        print("FALHOU: a identidade variou entre execuções", file=sys.stderr)
        return 1

    # ⚠️ `pop()` esvaziaria o conjunto antes do relatório e faria
    # `marca_estavel` sair False logo depois de a checagem acima ter passado.
    marca = next(iter(marcas))
    cid, mid = "5478096539", "6016739364"
    url = next(o.ad_group_ad_operation.create.ad.final_urls[0] for o in operacoes
               if o._pb.WhichOneof("operation") == "ad_group_ad_operation")

    por_marca = canario.campanhas_com_marca(customer_id=cid, login_customer_id=mid,
                                            marca=marca)
    por_destino = canario.campanhas_com_destino(customer_id=cid, login_customer_id=mid,
                                                url_final=url)
    try:
        metas = ct.meta_de_conversao(cid, login_customer_id=mid)
    except Exception as exc:  # noqa: BLE001
        metas = {"_erro": str(exc)[:200]}

    camp = next(o.campaign_operation.create for o in operacoes
                if o._pb.WhichOneof("operation") == "campaign_operation")
    tipos = collections.Counter(o._pb.WhichOneof("operation") for o in operacoes)
    keywords = [o.ad_group_criterion_operation.create.keyword
                for o in operacoes
                if o._pb.WhichOneof("operation") == "ad_group_criterion_operation"
                and o.ad_group_criterion_operation.create.keyword.text]

    dossie = {
        "versao_do_dossie": "canario-v10.2",
        "gerado_por": "scripts/dossie_canario_v10.py",
        # ⚠️ Este é o SHA do commit ANTERIOR ao que versiona este dossiê — o
        # gerador roda antes do commit que o carrega, e não existe forma de um
        # arquivo conter o hash do commit que o contém. `arvore_suja` diz se
        # havia mudança não commitada no instante da geração: `true` significa
        # que o código exercitado NÃO é exatamente o de `sha_do_codigo`.
        "sha_do_codigo": os.popen("git -C %s rev-parse HEAD" % RAIZ).read().strip(),
        "arvore_suja": bool(os.popen("git -C %s status --porcelain" % RAIZ).read().strip()),
        "sha_nota": (
            "sha_do_codigo é o HEAD no momento da geração. O commit que versiona "
            "este arquivo é o seguinte. Se arvore_suja=true, havia mudança local "
            "não commitada quando o validate_only rodou."),
        "qualificacao_historica": (
            "Este é o primeiro canário COM O LEDGER v10 COMPLETO. O primeiro "
            "canário Google da casa foi em 28/08/2026, campanha 24183717006, "
            "sem ledger. Chamar este de 'primeiro canário Search' seria falso."),
        "conta": {"customer_id": cid, "formatado": "547-809-6539",
                  "label": "Portal Mundo Mais", "login_customer_id": mid,
                  "mcc_formatado": "601-673-9364"},
        "payload_humano": corpo_http,
        "keywords": [{"texto": k.text, "match_type": k.match_type.name} for k in keywords],
        "negative_keywords": [],
        "negatives_assessed": False,
        "negatives_nota": (
            "Nenhuma negativa foi inventada. Elas dependem de search terms reais "
            "e de avaliação de sobrebloqueio, que só existem depois de veicular."),
        "rede": {"google_search": camp.network_settings.target_google_search,
                 "search_partners": camp.network_settings.target_search_network,
                 "display_expansion": camp.network_settings.target_content_network},
        "orcamento": {"diario_brl": "10.00", "micros": plano_ledger["budget_diario_micros"],
                      "teto_politica_brl": "20.00"},
        "cpc": {"brl": "1.00", "micros": plano_ledger["cpc_inicial_micros"],
                "teto_politica_brl": "1.00"},
        "estrategia_lance": "MANUAL_CPC",
        "status_inicial": camp.status.name,
        "nome_campanha": camp.name,
        "url_final": url,
        "chave_intencao": execucoes[0]["chave_intencao"],
        "marca_remota": marca,
        "blueprint_sha256": execucoes[0]["blueprint_sha256"],
        "selo_do_executor_por_execucao": [e["selo_do_executor"] for e in execucoes],
        "operacoes": {"total": sum(tipos.values()), "por_tipo": dict(tipos)},
        "validate_only": {
            "execucoes": len(execucoes),
            "aprovado_em_todas": all(e["aprovado"] for e in execucoes),
            "chave_estavel": len(chaves) == 1,
            "marca_estavel": len(marcas) == 1,
            "carimbos_distintos": len(carimbos) == len(execucoes),
            "n_operacoes_estavel": len(n_ops) == 1,
            "blueprint_estavel": len({e["blueprint_sha256"] for e in execucoes}) == 1,
            "selo_varia_por_carimbo": len({e["selo_do_executor"] for e in execucoes}) == len(execucoes),
            "detalhe": execucoes,
        },
        "duplicidade": {"por_marca": len(por_marca), "por_destino": len(por_destino),
                        "veredito": "LIVRE" if not por_marca and not por_destino else "JA EXISTE"},
        "conversion_goals_observados": metas,
        "conversion_goals_aplicados": None,
        "conversion_goals_nota": (
            "NENHUMA meta foi aplicada nem alterada. A campanha HERDA os "
            "CustomerConversionGoal da conta. Sobrescrever exige "
            "CampaignConversionGoal, que é ato separado — e a API só ATUALIZA "
            "goals, nunca cria nem remove. Ver evidence/GOOGLE-ADS-DOCS-2026-09-01.md"),
        "prontidao": ultimo.get("prontidao"),
        "rollback": (
            "A campanha nasce PAUSED e não gasta. Reversão: definir REMOVED na "
            "conta, ou reconciliar o recibo por POST /api/trafego/reconciliar. "
            "Migrations: v10_04_rollback -> v10_03_rollback -> v10_01_rollback."),
        "plano_de_readback": [
            "1. ler campaign.id/status/serving_status/advertising_channel_type",
            "2. ler campaign.network_settings (os três campos)",
            "3. ler campaign_budget.amount_micros e ad_group.cpc_bid_micros",
            "4. ler ad_group_criterion (as duas keywords e o match type)",
            "5. ler ad_group_ad.policy_summary (o veredito que o canário existe para colher)",
            "6. ler campaign_conversion_goal + conversion_goal_campaign_config.goal_config_level",
            "7. fechar o recibo por trafego_ledger_fechar e conferir volc_campaign_id",
            "8. reconciliar por POST /api/trafego/reconciliar se o recibo ficar em voo",
        ],
        "ativacao_impossivel": (
            "inclui_ativacao=false na política do canário, cria_pausada=true, e "
            "nenhuma das operações altera status de campanha."),
        "diferencas_do_canario_de_28_08": [
            "ledger v10 completo aplicado (v10_01, v10_03, v10_04) — antes não havia",
            "rede declarada: Search Partners OFF (antes ligado por literal invisível)",
            "seleção de keywords é autoridade (antes o grupo inteiro entrava)",
            "assets sem marca de terceiro (antes 10 marcas em headlines e snippet)",
            "recibo atômico antes da rede e reconciliação com saída provada",
        ],
    }
    # ⚠️ AS PROVAS DECLARADAS SÃO GATES, E NÃO CAMPOS DECORATIVOS.
    #
    # A primeira versão só falhava quando chave ou marca variavam; o resto era
    # gravado mesmo `false` e o processo saía 0. Um gerador que escreve
    # "aprovado_em_todas: false" e devolve sucesso produz um dossiê que parece
    # aprovado para quem lê o exit code.
    v = dossie["validate_only"]
    exigidas = {
        "aprovado_em_todas": v["aprovado_em_todas"],
        "chave_estavel": v["chave_estavel"],
        "marca_estavel": v["marca_estavel"],
        "carimbos_distintos": v["carimbos_distintos"],
        "n_operacoes_estavel": v["n_operacoes_estavel"],
        "blueprint_estavel": v["blueprint_estavel"],
        "selo_varia_por_carimbo": v["selo_varia_por_carimbo"],
        "sem_duplicidade": dossie["duplicidade"]["veredito"] == "LIVRE",
        "nasce_pausada": dossie["status_inicial"] == "PAUSED",
        "parceiros_desligados": dossie["rede"]["search_partners"] is False,
        "display_desligado": dossie["rede"]["display_expansion"] is False,
        "sem_negativas_inventadas": dossie["negative_keywords"] == [],
    }
    reprovadas = [k for k, ok in exigidas.items() if not ok]
    dossie["gates_do_dossie"] = exigidas
    dossie["gates_reprovados"] = reprovadas

    texto = json.dumps(dossie, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    dossie["dossie_id"] = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    SAIDA.write_text(json.dumps(dossie, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    print(f"dossie_id: {dossie['dossie_id']}")
    print(f"chave_intencao: {dossie['chave_intencao']}")
    print(f"marca: {marca} · operações: {dossie['operacoes']['total']} · "
          f"duplicidade: {dossie['duplicidade']['veredito']}")
    print(f"→ {SAIDA.relative_to(RAIZ)}")
    if reprovadas:
        print("GATES REPROVADOS: " + ", ".join(reprovadas), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
