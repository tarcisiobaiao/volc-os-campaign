#!/usr/bin/env python3
"""Deriva o golden de atribuição conjunto/dia a partir do CSV real, sanitizado.

## Por que existe

A prova que fixou o grão canônico da Meta é um CSV de operação real: 64 linhas
campanha/dia, 62 com receita atribuída via conjunto e 2 sem UTM de conjunto no
GAM. Ele carrega ids de conta, de campanha, de conjunto e de projeto REAIS.
Esses ids não entram no repositório.

Este script converte aquele CSV em um golden versionado com três garantias:

1. **Sanitização estável.** Cada id real vira um id sintético por HMAC-SHA256
   com um sal fixo e público. A função é determinística (rodar duas vezes dá o
   mesmo golden), preserva CARDINALIDADE e MULTIPLICIDADE (dois ids reais
   diferentes nunca colidem; o mesmo id real sempre vira o mesmo sintético) e
   não é reversível sem o CSV original.

2. **Descida de grão exata.** O CSV é campanha/dia; o contrato é conjunto/dia.
   O valor de cada linha é distribuído entre os conjuntos listados em
   `adsets_encontrados` pelo método do MAIOR RESTO, em `Decimal`, de modo que a
   soma dos conjuntos seja EXATAMENTE o valor da campanha — sem centavo perdido
   nem inventado. É o que torna o golden capaz de provar o rollup.

3. **Procedência auditável sem o dado sensível.** O golden guarda o SHA-256 do
   CSV de origem, a contagem de linhas e os totais originais. Quem tiver o CSV
   pode reexecutar e comparar; quem não tiver ainda vê o que está sendo provado.

Uso:

    python3 scripts/gerar_golden_atribuicao_meta.py <caminho-do-csv> \\
        [--saida backend/tests/goldens/atribuicao-meta-adset-v1.json]

⚠️ O CSV de origem NÃO deve ser copiado para dentro do repositório.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import sys
from collections import OrderedDict
from decimal import Decimal
from pathlib import Path

#: Sal público e fixo. Ele não é segredo: sua função é tornar o mapeamento
#: estável entre execuções, não esconder o id de quem já tem o CSV.
SAL = b"volc-os-meta-atribuicao-adset-v1"

#: Prefixo dos ids sintéticos. Mantém o formato "só dígitos" que o contrato
#: exige (`atribuicao.id_meta_valido`), sem parecer um id real da Meta.
_LARGURA_ID = 15


def sintetizar_id(bruto: str, especie: str) -> str:
    """Id sintético determinístico, só dígitos, sem colisão prática.

    `especie` separa os espaços de nomes: um id de campanha e um id de conjunto
    com o mesmo valor bruto produzem sintéticos diferentes, como no mundo real.
    """
    assinatura = hmac.new(SAL, f"{especie}:{bruto}".encode("utf-8"), hashlib.sha256)
    numero = int.from_bytes(assinatura.digest()[:8], "big") % (10 ** (_LARGURA_ID - 1))
    return f"9{numero:0{_LARGURA_ID - 1}d}"


def distribuir(total: Decimal, pesos: list[Decimal], casas: Decimal) -> list[Decimal]:
    """Reparte `total` em len(pesos) parcelas cuja soma é EXATAMENTE `total`.

    Método do maior resto: cada parcela recebe o piso da sua fração, e as
    sobras de arredondamento vão, uma a uma, para quem tem o maior resto. É o
    único jeito de descer de grão sem que a soma deixe de fechar — e a soma
    fechar é justamente o que o golden precisa provar.
    """
    # ⚠️ PRECONDIÇÕES EXPLÍCITAS, por achado do revisor adversarial.
    #
    # A promessa "a soma das parcelas é EXATAMENTE o total" só vale para
    # entradas que o algoritmo sabe cumprir, e a versão anterior aceitava
    # calada entradas que ela não cumpria:
    #
    #   total=-0.01, pesos [1,1] -> AssertionError (ROUND_DOWN aproxima de zero
    #                               e o laço só corrige falta POSITIVA);
    #   total=0.001 com passo 0.01 -> AssertionError (o total não é
    #                               representável na granularidade pedida);
    #   pesos=[]   -> devolvia [] e soma 0, perdendo o total em silêncio.
    #
    # Nenhum desses casos ocorre no golden (todos os valores do CSV são não
    # negativos e alinhados ao passo), mas uma função cuja promessa é maior do
    # que sua garantia é uma armadilha para o próximo uso. Agora ela RECUSA em
    # vez de mentir.
    n = len(pesos)
    if n == 0:
        if total != 0:
            raise ValueError(
                f"não há como distribuir {total} entre zero parcelas sem perder o total")
        return []
    if total < 0:
        raise ValueError(
            "distribuir() só conserva a soma para totais não negativos; "
            f"recebeu {total}")
    if total != total.quantize(casas):
        raise ValueError(
            f"o total {total} não é representável na granularidade {casas}; "
            "distribuir() não pode fechar a soma")
    if total == 0:
        return [Decimal(0)] * n
    soma_pesos = sum(pesos)
    if soma_pesos == 0:
        pesos = [Decimal(1)] * n
        soma_pesos = Decimal(n)

    brutos = [total * p / soma_pesos for p in pesos]
    pisos = [b.quantize(casas, rounding="ROUND_DOWN") for b in brutos]
    falta = total - sum(pisos)
    passo = casas
    restos = sorted(range(n), key=lambda i: (brutos[i] - pisos[i]), reverse=True)
    i = 0
    while falta > 0 and i < 10 * n + 10:
        pisos[restos[i % n]] += passo
        falta -= passo
        i += 1
    if falta != 0:  # pragma: no cover - defesa; nunca observado
        raise AssertionError(f"distribuição não fechou: falta {falta}")
    return pisos


def gerar(csv_path: Path) -> dict:
    bytes_csv = csv_path.read_bytes()
    linhas = list(csv.DictReader(bytes_csv.decode("utf-8").splitlines()))

    contas: "OrderedDict[str, str]" = OrderedDict()
    registros = []
    tot_spend = tot_orig = tot_brl = Decimal(0)
    tot_imp_m = tot_clk_m = tot_imp_g = tot_clk_g = 0
    atribuidas = sem_utm = 0

    for linha in linhas:
        conjuntos_reais = json.loads(linha["adsets_encontrados"])
        campanha = sintetizar_id(linha["campaign_id"], "campaign")
        projeto = int(sintetizar_id(linha["project_id"], "project")[-4:])
        # A conta não vem no CSV; o golden preserva o fato de que TODAS as
        # linhas pertencem à mesma conta, que é o que o escopo precisa provar.
        conta = contas.setdefault("conta-unica", sintetizar_id("conta-unica", "account"))

        spend = Decimal(linha["investimento_meta"])
        imp_m = int(linha["impressoes_meta"])
        clk_m = int(linha["cliques_meta"])
        rev_o = Decimal(linha["faturamento_gam_original"])
        rev_b = Decimal(linha["faturamento_gam_brl"])
        imp_g = int(linha["impressoes_gam"])
        clk_g = int(linha["cliques_gam"])
        estado = linha["status_atribuicao"]

        tot_spend += spend
        tot_imp_m += imp_m
        tot_clk_m += clk_m
        tot_imp_g += imp_g
        tot_clk_g += clk_g
        tot_orig += rev_o
        tot_brl += rev_b

        if estado == "FATURAMENTO_ATRIBUIDO_VIA_ADSET":
            atribuidas += 1
        else:
            sem_utm += 1

        if not conjuntos_reais:
            # Campanha sem UTM de conjunto no GAM. Ela NÃO some do golden: ela
            # é justamente o caso que precisa continuar distinguível — sem
            # conjunto conhecido, sem entrega e sem receita, e ainda assim uma
            # campanha que existiu naquele dia.
            registros.append({
                "date": linha["date"],
                "account_ref": conta,
                "campaign_id": campanha,
                "adset_id": None,
                "project_id": projeto,
                "spend": str(spend),
                "impressions": imp_m,
                "clicks": clk_m,
                "gam_revenue_original": None,
                "gam_revenue_brl": None,
                "gam_impressions": None,
                "gam_clicks": None,
                "status_origem": estado,
            })
            continue

        conjuntos = [sintetizar_id(a, "adset") for a in conjuntos_reais]
        # Pesos iguais: o CSV não informa a repartição real entre conjuntos, e
        # inventar uma repartição desigual seria fingir uma medida que não
        # existe. O que o golden prova é o ROLLUP, e ele é exato com qualquer
        # repartição que feche.
        pesos = [Decimal(1)] * len(conjuntos)
        partes_spend = distribuir(spend, pesos, Decimal("0.000001"))
        partes_orig = distribuir(rev_o, pesos, Decimal("0.0001"))
        partes_brl = distribuir(rev_b, pesos, Decimal("0.01"))
        partes_imp_m = [int(x) for x in distribuir(Decimal(imp_m), pesos, Decimal(1))]
        partes_clk_m = [int(x) for x in distribuir(Decimal(clk_m), pesos, Decimal(1))]
        partes_imp_g = [int(x) for x in distribuir(Decimal(imp_g), pesos, Decimal(1))]
        partes_clk_g = [int(x) for x in distribuir(Decimal(clk_g), pesos, Decimal(1))]

        for i, conjunto in enumerate(conjuntos):
            registros.append({
                "date": linha["date"],
                "account_ref": conta,
                "campaign_id": campanha,
                "adset_id": conjunto,
                "project_id": projeto,
                "spend": str(partes_spend[i]),
                "impressions": partes_imp_m[i],
                "clicks": partes_clk_m[i],
                "gam_revenue_original": str(partes_orig[i]),
                "gam_revenue_brl": str(partes_brl[i]),
                "gam_impressions": partes_imp_g[i],
                "gam_clicks": partes_clk_g[i],
                "status_origem": estado,
            })

    return {
        "contrato": "meta-atribuicao-adset-v1",
        "procedencia": {
            "origem": "CSV de operação real Meta+GAM, campanha/dia",
            "csv_sha256": hashlib.sha256(bytes_csv).hexdigest(),
            "csv_linhas_de_dados": len(linhas),
            "sanitizacao": "HMAC-SHA256 com sal público fixo; ids reais não entram no repositório",
            "descida_de_grao": "campanha/dia -> conjunto/dia por maior resto, soma exata preservada",
        },
        "invariantes": {
            "linhas_campanha_dia": len(linhas),
            "campanha_dia_atribuidas": atribuidas,
            "campanha_dia_sem_utm": sem_utm,
            "linhas_conjunto_dia": len(registros),
            "total_spend": str(tot_spend),
            "total_revenue_original": str(tot_orig),
            "total_revenue_brl": str(tot_brl),
            "total_impressions_meta": tot_imp_m,
            "total_clicks_meta": tot_clk_m,
            "total_impressions_gam": tot_imp_g,
            "total_clicks_gam": tot_clk_g,
            "campanhas_distintas": len({r["campaign_id"] for r in registros}),
            "conjuntos_distintos": len({r["adset_id"] for r in registros if r["adset_id"]}),
            "datas_distintas": len({r["date"] for r in registros}),
        },
        "linhas": registros,
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv", type=Path)
    p.add_argument("--saida", type=Path,
                   default=Path("backend/tests/goldens/atribuicao-meta-adset-v1.json"))
    args = p.parse_args(argv)
    golden = gerar(args.csv)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(
        json.dumps(golden, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    inv = golden["invariantes"]
    print(f"golden escrito em {args.saida}")
    print(f"  campanha/dia: {inv['linhas_campanha_dia']} "
          f"({inv['campanha_dia_atribuidas']} atribuídas, {inv['campanha_dia_sem_utm']} sem UTM)")
    print(f"  conjunto/dia: {inv['linhas_conjunto_dia']}")
    print(f"  spend={inv['total_spend']}  revenue_brl={inv['total_revenue_brl']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
