"""O contrato de medição que um funil com jornada emite (`medicao.json`).

Diz O QUE medir e de que contrato existente o dado sairia. Não diz que o dado
existe: nenhum coletor desta lista foi provado ativo para as URLs do funil
(P08-T07 tem o sensor, mas o fluxo agregador está inativo; P08-T02 tem receita
por URL, não por sessão). Por isso todo sinal nasce `nao_implantada` — o campo
só muda quando um coletor for provado, nunca por suposição.
"""
from __future__ import annotations

from funnelforge.domain.medicao import (
    ContratoDeMedicao,
    MudancaSugerida,
    PropostaDeNovaVersao,
    SinalPrevisto,
)
from funnelforge.domain.models import FunnelPlan, PageRole, effective_role
from funnelforge.pipeline.jornada._comum import (
    classificar_saida_oficial,
    justificado,
    links,
    por_slug,
)

_FONTE_CTA = "telemetria comportamental: clique em CTA (P08-T07; agregador inativo)"
_FONTE_ENGAJ = ("telemetria comportamental: scroll/engagement como PROXY de resolução "
                "(P08-T07; agregador inativo)")
_FONTE_SAIDA = "clique de saída para a fonte oficial (P08-T07; agregador inativo)"
_FONTE_RECEITA = ("receita AdSense/GAM por URL do funil (P08-T02); por sessão exige "
                  "sessão, que não é coletada")
_FONTE_CHEGADA = "vínculo campanha → funil → URLs e UTM do clique (P08-T02, parcial)"
_FONTE_SESSAO = "sequência de pageviews na sessão — não coletada"
_FONTE_CWV = "CrUX/PageSpeed por URL publicada — não automatizado"


def contrato_de_medicao(plan: FunnelPlan, run_id: str,
                        achados: list[dict] | None = None) -> ContratoDeMedicao:
    sinais: list[SinalPrevisto] = []
    s = sinais.append
    slugs = por_slug(plan)
    fj = plan.jornada
    if fj is not None:
        for c in fj.coortes:
            s(SinalPrevisto(sinal="chegada_lp", escopo=f"coorte:{c.canal}->{c.entrada}",
                            hipotese=c.promessa, fonte_prevista=_FONTE_CHEGADA))
    for p in plan.pages:
        if p.jornada is None:
            continue
        j = p.jornada
        for link in links(p):
            alvo = slugs.get(link.target)
            if alvo is None or alvo.jornada is None:
                continue
            sinal = "escolha_de_ramo" if effective_role(p) is PageRole.LP else "progressao"
            aresta = f"aresta:{j.duvida_id}->{alvo.jornada.duvida_id}"
            s(SinalPrevisto(sinal=sinal, escopo=aresta, hipotese=link.reason,
                            fonte_prevista=_FONTE_CTA))
            motivo = justificado(p, alvo)
            if motivo:
                s(SinalPrevisto(sinal="loop_revisita", escopo=aresta,
                                hipotese=f"retorno justificado: {motivo}",
                                fonte_prevista=_FONTE_SESSAO))
        s(SinalPrevisto(sinal="resolucao", escopo=f"pagina:{j.duvida_id}",
                        hipotese=j.condicao_terminal or j.resposta_imediata or j.pergunta_principal,
                        fonte_prevista=_FONTE_ENGAJ))
        s(SinalPrevisto(sinal="abandono", escopo=f"pagina:{j.duvida_id}",
                        hipotese=(j.hipotese_de_medicao
                                  or "abandono depois da resposta é sucesso; antes dela é falha"),
                        fonte_prevista=_FONTE_ENGAJ))
        classe = classificar_saida_oficial(p)
        if classe != "nao_aplicavel":
            s(SinalPrevisto(sinal=f"saida_oficial_{classe}", escopo=f"pagina:{j.duvida_id}",
                            hipotese=j.saida_oficial.condicao or f"saída oficial {classe}",
                            fonte_prevista=_FONTE_SAIDA))
        s(SinalPrevisto(sinal="core_web_vitals", escopo=f"pagina:{j.duvida_id}",
                        hipotese="anúncio, widget e print não atrasam a resposta (LCP/INP/CLS)",
                        fonte_prevista=_FONTE_CWV))
    s(SinalPrevisto(sinal="loop_revisita", escopo="funil",
                    hipotese="nenhuma revisita sem ganho: retornos só onde justificados",
                    fonte_prevista=_FONTE_SESSAO))
    s(SinalPrevisto(sinal="receita_por_sessao", escopo="funil",
                    hipotese=(fj.hipotese_de_medicao if fj and fj.hipotese_de_medicao
                              else "monetização sem destruir clareza nem velocidade"),
                    fonte_prevista=_FONTE_RECEITA))
    s(SinalPrevisto(sinal="rpm_valor_de_sessao", escopo="funil",
                    hipotese="valor de sessão vem de progressão útil, não de páginas extras",
                    fonte_prevista=_FONTE_RECEITA))

    premissas = list(fj.evidencias) if fj else []
    for p in plan.pages:
        if p.jornada is not None:
            premissas.extend(p.jornada.evidencias)
    hipoteses = [f"{e.natureza}: {e.afirmacao}" + (f" ({e.fonte})" if e.fonte else "")
                 for e in premissas if e.natureza != "observacao_real"]
    hipoteses += [f"hipotese: {p.jornada.hipotese_de_medicao}"
                  for p in plan.pages if p.jornada and p.jornada.hipotese_de_medicao]
    mudancas = [MudancaSugerida(alvo=x.get("duvida_id") or "funil",
                                proposta=x["proposta"],
                                motivo=f"[{x['regra']}] {x['evidencia']}",
                                natureza_da_base="hipotese")
                for x in (achados or []) if x.get("severidade") in ("bloqueio", "material")]
    return ContratoDeMedicao(
        run_id=run_id, sinais=sinais,
        saidas_oficiais={p.jornada.duvida_id: classificar_saida_oficial(p)
                         for p in plan.pages if p.jornada is not None},
        premissas=premissas,
        proposta=PropostaDeNovaVersao(hipoteses_a_testar=hipoteses,
                                      mudancas_sugeridas=mudancas),
    )
