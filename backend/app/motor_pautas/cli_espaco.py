"""CLI do motor de descoberta.

    python -m forge.mineracao.cli --smoke
    python -m forge.mineracao.cli --arquivo temas.json [--json]

O motor SUGERE pauta. Não decide verba, não sobe campanha, não tem stop-loss —
quem decide é o operador. Por isso ele entrega **posição no espaço e motivo**,
não probabilidade calibrada: o que serve a quem decide é saber por que um tema
está bem ou mal colocado, não um número com três casas.

Nenhum eixo é inferido de regex de idioma. Quem declara é quem julga — agente ou
humano — e o Python faz a aritmética. É o que faz o motor valer para tailandês
sem uma linha de tailandês no código.
"""

from __future__ import annotations

import argparse
import json

from .espaco import ESCALAS, FAMILIAS, PRIORES, ordenar, posicionar

# Casos de propósito espalhados por idioma, nicho e mercado — nenhum deles
# depende da operação-exemplo para ser pontuado.
CASOS = [
    dict(termo="cesantias", pais="CO",
         ignorancia="nao_sei_se_existe", engajamento="condicional", opacidade="fragmentada",
         reposicao="continua", volume="alto", spread="bom", densidade="densa",
         vacuo="disputado", producao="revisao_anual", formato_consumo="misto"),
    dict(termo="ประกันสังคม มาตรา 40", pais="TH",
         ignorancia="nao_sei_se_existe", engajamento="condicional", opacidade="ilegivel",
         reposicao="continua", volume="alto", spread="excelente", densidade="media",
         vacuo="virgem", producao="revisao_anual", formato_consumo="misto"),
    dict(termo="repartidor rappi", pais="CO",
         ignorancia="nao_sei_se_sirvo", engajamento="sequencial", opacidade="fragmentada",
         reposicao="continua", volume="alto", spread="bom", densidade="densa",
         vacuo="disputado", producao="revisao_mensal", formato_consumo="misto"),
    dict(termo="boligstotte", pais="DK",
         ignorancia="nao_sei_se_sirvo", engajamento="condicional", opacidade="ilegivel",
         reposicao="continua", volume="medio", spread="ruim", densidade="densa",
         vacuo="raso", producao="revisao_anual", formato_consumo="texto_busca"),
    dict(termo="medicare enrollment", pais="US",
         ignorancia="nao_sei_se_sirvo", engajamento="condicional", opacidade="fragmentada",
         reposicao="anual", volume="massivo", spread="ruim", densidade="densa",
         vacuo="saturado", producao="revisao_anual", formato_consumo="texto_busca"),
    dict(termo="simit consultar multas", pais="CO",
         ignorancia="so_falta_um_dado", engajamento="dado_unico", opacidade="clara",
         reposicao="mesma_gente", volume="massivo", spread="bom", densidade="rala",
         vacuo="saturado", producao="revisao_mensal", formato_consumo="misto"),
    dict(termo="melhor celular 2026", pais="BR",
         ignorancia="nao_preciso_de_nada", engajamento="comparativo", opacidade="clara",
         reposicao="unica", volume="massivo", spread="neutro", densidade="densa",
         vacuo="saturado", producao="acompanhamento", formato_consumo="texto_busca"),
    # o mesmo arquétipo forte, num país onde o canal não fecha o funil
    dict(termo="jaminan hari tua bpjs", pais="ID",
         ignorancia="nao_sei_se_existe", engajamento="condicional", opacidade="fragmentada",
         reposicao="continua", volume="massivo", spread="excelente", densidade="densa",
         vacuo="raso", producao="revisao_anual", formato_consumo="video_social"),
    # declaração parcial de propósito: o motor tem que lidar com o que falta
    dict(termo="kiedy wyplata 800 plus", pais="PL",
         ignorancia="so_falta_um_dado", engajamento="dado_unico", volume="massivo"),
]


def _tabela(ps) -> str:
    L = ["%-26s %4s %7s %7s %7s %7s  %-8s %s" % (
        "termo", "país", "ÍNDICE", "humana", "econom", "posiç", "cobert", "perfil"),
        "-" * 108]
    for p in ps:
        L.append("%-26s %4s %7s %7.3f %7.3f %7.3f  %6.0f%%  %s" % (
            p.termo[:26], p.pais,
            f"{p.indice:.3f}" if p.indice is not None else " s/base",
            p.familia("demanda_humana") or 0, p.familia("economia") or 0,
            p.familia("posicao") or 0, 100 * p.cobertura, p.perfil()))
    return "\n".join(L)


def smoke() -> int:
    print("MOTOR DE DESCOBERTA — espaço multidimensional")
    print("=" * 108)
    print(f"  {len(ESCALAS)} eixos em {len(FAMILIAS)} famílias · pesos são PRIORES "
          f"de princípio, não coeficientes ajustados")
    print("  nenhum eixo depende de spend, revenue ou de qualquer operação existente")
    print()

    ps = [posicionar(**{k: v for k, v in c.items() if k not in ("termo", "pais")},
                     termo=c["termo"], pais=c["pais"]) for c in CASOS]

    print("  RANQUEADOS (cobertura mínima 50%)")
    print("  " + _tabela(ordenar(ps)).replace("\n", "\n  "))

    fora = [p for p in ps if p not in ordenar(ps)]
    if fora:
        print()
        print("  FORA DO RANKING — declaração insuficiente, não avaliados")
        for p in fora:
            print(f"    · {p.termo[:30]:<30} cobertura {100*p.cobertura:.0f}%  "
                  f"faltam: {', '.join(p.faltando()[:4])}")

    print()
    print("  POR QUE CADA UM ESTÁ ONDE ESTÁ")
    print("  " + "-" * 106)
    for p in ordenar(ps):
        if p.perfil() == "alvo" and not [a for a in p.alertas if "não declarados" not in a]:
            continue
        print(f"  {p.termo[:30]:<30} {p.perfil()}")
        for a in p.alertas:
            if "não declarados" in a:
                continue
            print(f"  {'':30}   ⚠ {a[:88]}")

    print()
    print("  OS QUADRANTES — é o rótulo que orienta a ação, não a nota")
    print("    alvo                       lê e o mercado paga")
    print("    audiencia_pobre            lê muito, mercado não paga")
    print("    mercado_rico_sem_leitura   paga bem, mas a página não segura")
    print("    descartar                  nenhum dos dois")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="descoberta")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--arquivo", help="JSON: [{termo, pais, <eixos>}]")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--eixos", action="store_true", help="lista os eixos e níveis válidos")
    a = ap.parse_args(argv)

    if a.eixos:
        for fam, dims in FAMILIAS.items():
            print(f"\n{fam.upper()}")
            for nome, escala in dims.items():
                print(f"  {nome}  (prior {PRIORES[nome]:.2f})")
                for nivel, (v, desc) in sorted(escala.items(), key=lambda kv: -kv[1][0]):
                    print(f"      {nivel:<24} {v:.2f}  {desc}")
        return 0

    if a.smoke:
        return smoke()

    if not a.arquivo:
        ap.print_help()
        return 2

    bruto = json.loads(open(a.arquivo).read())
    ps = [posicionar(**{k: v for k, v in c.items() if k not in ("termo", "pais")},
                     termo=c["termo"], pais=c.get("pais", "??")) for c in bruto]
    ranked = ordenar(ps)

    if a.json:
        print(json.dumps([{
            "termo": p.termo, "pais": p.pais,
            "indice": round(p.indice, 4) if p.indice is not None else None,
            "perfil": p.perfil(), "cobertura": round(p.cobertura, 3),
            "familias": {f: (round(p.familia(f), 4) if p.familia(f) is not None else None)
                         for f in FAMILIAS},
            "eixos": {n: e.nivel for n, e in p.eixos.items()},
            "faltando": p.faltando(), "alertas": p.alertas,
        } for p in ranked], ensure_ascii=False, indent=1))
    else:
        print(_tabela(ranked))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
