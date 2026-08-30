"""Extrai o corpus de política das contas acessíveis. SOMENTE LEITURA.

## O que este script é

O veredito do Google sobre cada anúncio já submetido — em arquivo versionado, em
vez de em script de pasta temporária. É o conjunto contra o qual qualquer
mudança no validador passa a ser medida, em vez de trocada no escuro.

## Por que ele não escreve nada

Usa exclusivamente `GoogleAdsService.search`, que em GAQL só tem `SELECT`. Não
existe verbo de escrita nesta superfície. Nenhuma `MutateOperation` é montada,
então a trava de `forge.gads.modo` nem chega a ser exercida — não há o que
travar. A saída vai para arquivo local no repositório; nada de Supabase.

## O que o corpus consegue responder, e o que NÃO consegue

CONSEGUE, porque os campos existem em `ad_group_ad.policy_summary`:

  · qual URL causa cada `DESTINATION_MISMATCH` — `evidences.destination_mismatch
    .url_types` nomeia o par em conflito (DISPLAY_URL, FINAL_URL, TRACKING_URL…).
    Era a maior classe de reprovação medida e a hipótese de que fosse problema de
    TEXTO estava errada: é política de URL.
  · quantos aprovados são aprovados de fato — `review_status`. Uma medição
    anterior filtrou só `approval_status` e pode ter contado anúncio ainda em
    revisão como aprovado.
  · qual texto exato o Google apontou — `evidences.text_list.texts`.
  · política de KEYWORD, que nunca tinha sido olhada —
    `ad_group_criterion.approval_status` e `disapproval_reasons`.

NÃO CONSEGUE:

  · `is_exemptible`. O campo não existe em `PolicyTopicEntry`; vive em
    `PolicyViolationDetails`, que só volta na resposta de ERRO de uma mutação.
    Descobrir o que é isentável exige reenviar cada anúncio em `validate_only`
    e ler o erro — outra operação, uma chamada por anúncio. Fica fora daqui.

## Colunas que nascem nulas, e por quê

O esquema de destino pede campos que o histórico não tem. Declarados aqui em voz
alta para que ninguém desenhe um benchmark supondo coluna cheia:

  landing_snapshot_hash   a LP como estava no dia da revisão não é recuperável
  expanded_final_url      a expansão que o Google executou não é recuperável;
                          só dá para recalcular localmente, e isso é estimativa
  prompt_version          nulo em 100%: o gerador nunca rodou em produção
  spec_version            idem
  publisher_revenue       vem do GAM, não do Ads — só existe para os nossos
                          sites, não para contas de terceiros

## Por que a saída é estratificada

A primeira rodada de teste, em duas contas, produziu 1,4 GB — e 99,3% disso era
anúncio APPROVED sem uma única entrada de política. Extrapolado para a operação
inteira daria ~20 GB de arquivo para carregar ~2.500 linhas de sinal.

Então: TODO anúncio com entrada de política é guardado, sempre. Os limpos entram
por amostra de controle — o benchmark precisa da classe negativa, mas precisa de
milhares, não de centenas de milhares. Em keywords, só as não-aprovadas e as
negativas; das aprovadas fica a contagem.

O manifesto registra quantos foram descartados por amostragem, para ninguém ler
o arquivo como se fosse censo.

Uso:
    .venv/bin/python scripts/extrair_corpus_politica.py --mcc 8696453882,6084143056,1081900905
    .venv/bin/python scripts/extrair_corpus_politica.py --limite 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]   # raiz do projeto Volc OS
sys.path.insert(0, str(RAIZ))

logging.disable(logging.CRITICAL)

from google.ads.googleads.client import GoogleAdsClient  # noqa: E402

from volc_ads.gads.client import buscar  # noqa: E402

SAIDA = Path(__file__).resolve().parents[1] / "dados" / "corpus"

# ── as consultas ─────────────────────────────────────────────────────────────
# Sem filtro de status: reprovação em anúncio pausado é dado tão bom quanto em
# anúncio ativo, e o viés de só olhar o que está no ar é exatamente o que
# contaminou a base anterior. REMOVED fica de fora só por volume.

Q_ANUNCIOS = """
SELECT
  customer.id, customer.descriptive_name, customer.currency_code,
  customer.time_zone, customer.auto_tagging_enabled,
  campaign.id, campaign.name, campaign.status,
  campaign.advertising_channel_type, campaign.tracking_url_template,
  campaign.final_url_suffix,
  ad_group.id, ad_group.name,
  ad_group_ad.resource_name, ad_group_ad.status, ad_group_ad.ad_strength,
  ad_group_ad.policy_summary.review_status,
  ad_group_ad.policy_summary.approval_status,
  ad_group_ad.policy_summary.policy_topic_entries,
  ad_group_ad.ad.id, ad_group_ad.ad.type,
  ad_group_ad.ad.final_urls, ad_group_ad.ad.final_mobile_urls,
  ad_group_ad.ad.tracking_url_template, ad_group_ad.ad.final_url_suffix,
  ad_group_ad.ad.display_url,
  ad_group_ad.ad.responsive_search_ad.headlines,
  ad_group_ad.ad.responsive_search_ad.descriptions,
  ad_group_ad.ad.responsive_search_ad.path1,
  ad_group_ad.ad.responsive_search_ad.path2,
  ad_group_ad.ad.responsive_display_ad.headlines,
  ad_group_ad.ad.responsive_display_ad.descriptions,
  ad_group_ad.ad.responsive_display_ad.long_headline,
  ad_group_ad.ad.expanded_text_ad.headline_part1,
  ad_group_ad.ad.expanded_text_ad.headline_part2,
  ad_group_ad.ad.expanded_text_ad.description
FROM ad_group_ad
WHERE ad_group_ad.status != 'REMOVED'
"""

Q_KEYWORDS = """
SELECT
  customer.id,
  campaign.id, campaign.name, campaign.advertising_channel_type,
  ad_group.id,
  ad_group_criterion.criterion_id, ad_group_criterion.status,
  ad_group_criterion.negative,
  ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type,
  ad_group_criterion.approval_status,
  ad_group_criterion.disapproval_reasons,
  ad_group_criterion.system_serving_status
FROM ad_group_criterion
WHERE ad_group_criterion.type = 'KEYWORD'
  AND ad_group_criterion.status != 'REMOVED'
"""


def _texto(x) -> str:
    return (x or "").strip()


def _hash(*partes: str) -> str:
    return hashlib.sha256("␟".join(partes).encode("utf-8")).hexdigest()[:20]


def _evidencia(ev) -> dict:
    """Achata uma PolicyTopicEvidence preservando QUAL das seis formas ela é.

    O `errors.py` do forge joga essa estrutura fora inteira ao classificar um
    erro — é por isso que a isenção de política nunca foi possível. Aqui ela é
    preservada campo a campo.
    """
    d: dict = {}
    if ev.text_list.texts:
        d["text_list"] = list(ev.text_list.texts)
    if ev.website_list.websites:
        d["website_list"] = list(ev.website_list.websites)
    if ev.destination_text_list.destination_texts:
        d["destination_text_list"] = list(ev.destination_text_list.destination_texts)
    if ev.destination_mismatch.url_types:
        d["destination_mismatch_url_types"] = [
            t.name for t in ev.destination_mismatch.url_types
        ]
    dnw = ev.destination_not_working
    if dnw.expanded_url or dnw.http_error_code or dnw.dns_error_type:
        d["destination_not_working"] = {
            "expanded_url": _texto(dnw.expanded_url),
            "device": dnw.device.name,
            "http_error_code": dnw.http_error_code or None,
            "dns_error_type": dnw.dns_error_type.name,
            "last_checked": _texto(dnw.last_checked_date_time),
        }
    if ev.language_code:
        d["language_code"] = _texto(ev.language_code)
    return d


def _restricao(c) -> dict:
    d: dict = {}
    for campo in ("country_constraint_list", "certificate_missing_in_country_list",
                  "certificate_domain_mismatch_in_country_list"):
        lista = getattr(c, campo)
        if lista.countries:
            d[campo] = {
                "total_alvo": lista.total_targeted_countries,
                "paises": [p.country_criterion for p in lista.countries],
            }
    if c.reseller_constraint:
        d["reseller_constraint"] = True
    return d


def _ativos(ad) -> list[dict]:
    """Um registro por asset. A política avalia a COMBINAÇÃO, mas a evidência
    aponta o texto — então os dois níveis precisam existir."""
    out: list[dict] = []

    def junta(itens, tipo):
        for i, a in enumerate(itens):
            t = _texto(getattr(a, "text", ""))
            if not t:
                continue
            out.append({
                "tipo": tipo,
                "posicao": i,
                "pinado": getattr(a, "pinned_field", None).name
                          if getattr(a, "pinned_field", None) else None,
                "texto": t,
                "texto_hash": _hash(t.lower()),
                "tem_dki": "{keyword" in t.lower() or "{KeyWord" in t,
            })

    rsa = ad.responsive_search_ad
    junta(rsa.headlines, "headline_rsa")
    junta(rsa.descriptions, "description_rsa")
    rda = ad.responsive_display_ad
    junta(rda.headlines, "headline_rda")
    junta(rda.descriptions, "description_rda")
    if _texto(rda.long_headline.text):
        out.append({"tipo": "long_headline_rda", "posicao": 0, "pinado": None,
                    "texto": _texto(rda.long_headline.text),
                    "texto_hash": _hash(rda.long_headline.text.lower()),
                    "tem_dki": False})
    eta = ad.expanded_text_ad
    for campo, tipo in (("headline_part1", "headline_eta"),
                        ("headline_part2", "headline_eta"),
                        ("description", "description_eta")):
        t = _texto(getattr(eta, campo, ""))
        if t:
            out.append({"tipo": tipo, "posicao": len(out), "pinado": None,
                        "texto": t, "texto_hash": _hash(t.lower()),
                        "tem_dki": False})
    return out


def contas(raiz: GoogleAdsClient,
           so_mccs: set[str] | None = None) -> dict[str, tuple[str, str]]:
    """{customer_id: (login_customer_id, nome)} — só contas operacionais.

    `so_mccs` restringe a varredura a MCCs nomeadas. Sem isso o script varre
    tudo que a credencial alcança, e "tudo" inclui operações de outro negócio,
    com outra vertical e outro perfil de política — misturar as duas coisas num
    corpus só é como treinar contra a média de duas populações diferentes.
    """
    ids = [r.split("/")[-1] for r in raiz.get_service("CustomerService")
           .list_accessible_customers().resource_names]
    if so_mccs:
        faltando = so_mccs - set(ids)
        if faltando:
            print(f"⚠️  MCC(s) fora do alcance da credencial: {sorted(faltando)}")
        ids = [i for i in ids if i in so_mccs]
    alvo: dict[str, tuple[str, str]] = {}
    for mcc in ids:
        try:
            linhas = buscar(mcc, """
                SELECT customer_client.id, customer_client.descriptive_name,
                       customer_client.status, customer_client.manager
                FROM customer_client
                WHERE customer_client.status = 'ENABLED'
                  AND customer_client.manager = FALSE""",
                login_customer_id=mcc)
            for l in linhas:
                cc = l.customer_client
                alvo.setdefault(str(cc.id), (mcc, cc.descriptive_name))
        except Exception:
            continue
    return alvo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=0,
                    help="processa só as N primeiras contas (teste)")
    ap.add_argument("--mcc", type=str, default="",
                    help="IDs de MCC separados por vírgula, só dígitos")
    ap.add_argument("--controle", type=int, default=400,
                    help="anúncios limpos guardados por conta (amostra de controle)")
    args = ap.parse_args()

    so_mccs = {c.strip().replace("-", "") for c in args.mcc.split(",") if c.strip()}

    SAIDA.mkdir(parents=True, exist_ok=True)
    capturado_em = datetime.now(timezone.utc).isoformat(timespec="seconds")

    raiz = GoogleAdsClient.load_from_storage(version="v25")
    alvo = contas(raiz, so_mccs or None)
    if args.limite:
        alvo = dict(list(alvo.items())[:args.limite])
    print(f"{len(alvo)} contas operacionais"
          f"{f' em {len(so_mccs)} MCC(s)' if so_mccs else ''}\n")

    f_anun = (SAIDA / "anuncios.jsonl").open("w", encoding="utf-8")
    f_ativ = (SAIDA / "ativos.jsonl").open("w", encoding="utf-8")
    f_pol = (SAIDA / "politica.jsonl").open("w", encoding="utf-8")
    f_kw = (SAIDA / "keywords.jsonl").open("w", encoding="utf-8")

    n_anun = n_ativ = n_pol = n_kw = 0
    n_anun_vistos = n_kw_vistos = 0     # antes da amostragem
    falhas: list[str] = []
    por_aprovacao: Counter = Counter()
    por_revisao: Counter = Counter()
    por_topico: Counter = Counter()
    url_types: Counter = Counter()
    kw_aprovacao: Counter = Counter()
    kw_motivo: Counter = Counter()

    for i, (cid, (login, nome)) in enumerate(sorted(alvo.items()), 1):
        print(f"[{i:>3}/{len(alvo)}] {cid} {nome[:44]:44}", end=" ", flush=True)
        a = p = k = 0

        controle = args.controle
        try:
            for l in buscar(cid, Q_ANUNCIOS, login_customer_id=login):
                ad, aga = l.ad_group_ad.ad, l.ad_group_ad
                ps = aga.policy_summary
                n_anun_vistos += 1
                # As distribuições contam TODOS os anúncios vistos, não só os
                # gravados — senão a amostragem apareceria no manifesto como se
                # fosse a realidade da conta.
                por_aprovacao[ps.approval_status.name] += 1
                por_revisao[ps.review_status.name] += 1

                # Todo anúncio com política entra. Os limpos entram por amostra:
                # o benchmark precisa da classe negativa, não do censo dela.
                tem_politica = bool(ps.policy_topic_entries)
                if not tem_politica:
                    if controle <= 0:
                        continue
                    controle -= 1

                urls = list(ad.final_urls)
                payload_hash = _hash(str(sorted(x["texto"] for x in _ativos(ad))),
                                     str(sorted(urls)))
                versao = _hash(str(cid), str(ad.id), payload_hash)

                f_anun.write(json.dumps({
                    "ad_version_id": versao,
                    "capturado_em": capturado_em,
                    "customer_id": str(cid), "mcc_id": str(login),
                    "conta": nome,
                    "moeda": l.customer.currency_code,
                    "fuso": l.customer.time_zone,
                    "auto_tagging": l.customer.auto_tagging_enabled,
                    "campaign_id": str(l.campaign.id),
                    "campanha": l.campaign.name,
                    "campanha_status": l.campaign.status.name,
                    "canal": l.campaign.advertising_channel_type.name,
                    "campanha_tracking_url_template":
                        _texto(l.campaign.tracking_url_template),
                    "campanha_final_url_suffix":
                        _texto(l.campaign.final_url_suffix),
                    "ad_group_id": str(l.ad_group.id),
                    "ad_group": l.ad_group.name,
                    "ad_id": str(ad.id),
                    "ad_type": ad.type_.name,
                    "ad_status": aga.status.name,
                    "ad_strength": aga.ad_strength.name,
                    "final_urls": urls,
                    "final_mobile_urls": list(ad.final_mobile_urls),
                    "tracking_url_template": _texto(ad.tracking_url_template),
                    "final_url_suffix": _texto(ad.final_url_suffix),
                    "display_url": _texto(ad.display_url),
                    "path1": _texto(ad.responsive_search_ad.path1),
                    "path2": _texto(ad.responsive_search_ad.path2),
                    "review_status": ps.review_status.name,
                    "approval_status": ps.approval_status.name,
                    "payload_hash": payload_hash,
                    # declarados nulos de propósito — ver docstring
                    "landing_snapshot_hash": None,
                    "expanded_final_url": None,
                    "prompt_version": None,
                    "spec_version": None,
                    "generator_source": "manual",
                }, ensure_ascii=False) + "\n")
                n_anun += 1
                a += 1

                for at in _ativos(ad):
                    at["ad_version_id"] = versao
                    at["asset_instance_id"] = _hash(versao, at["tipo"],
                                                    str(at["posicao"]))
                    f_ativ.write(json.dumps(at, ensure_ascii=False) + "\n")
                    n_ativ += 1

                for e in ps.policy_topic_entries:
                    evid = [_evidencia(x) for x in e.evidences]
                    evid = [x for x in evid if x]
                    rest = [_restricao(x) for x in e.constraints]
                    rest = [x for x in rest if x]
                    f_pol.write(json.dumps({
                        "ad_version_id": versao,
                        "customer_id": str(cid),
                        "ad_id": str(ad.id),
                        "observado_em": capturado_em,
                        "topico": e.topic,
                        "tipo": e.type_.name,
                        "review_status": ps.review_status.name,
                        "approval_status": ps.approval_status.name,
                        "evidencias": evid,
                        "restricoes": rest,
                        # não existe em PolicyTopicEntry — só na resposta de erro
                        "is_exemptible": None,
                    }, ensure_ascii=False) + "\n")
                    n_pol += 1
                    p += 1
                    por_topico[f"{e.topic}·{e.type_.name}"] += 1
                    for x in evid:
                        for t in x.get("destination_mismatch_url_types", []):
                            url_types[t] += 1
        except Exception as exc:
            falhas.append(f"{cid} anuncios: {str(exc)[:150]}")

        try:
            for l in buscar(cid, Q_KEYWORDS, login_customer_id=login):
                c = l.ad_group_criterion
                motivos = list(c.disapproval_reasons)
                n_kw_vistos += 1
                if not c.negative:
                    kw_aprovacao[c.approval_status.name] += 1
                    for m in motivos:
                        kw_motivo[m] += 1

                # Só o que informa: negativa (é a inteligência de exclusão da
                # operação) e positiva que NÃO passou. Keyword positiva aprovada
                # é 94% das linhas e não diz nada que a contagem não diga.
                interessante = (
                    bool(c.negative)
                    or c.approval_status.name != "APPROVED"
                    or bool(motivos)
                )
                if not interessante:
                    continue

                f_kw.write(json.dumps({
                    "capturado_em": capturado_em,
                    "customer_id": str(cid), "conta": nome,
                    "campaign_id": str(l.campaign.id),
                    "campanha": l.campaign.name,
                    "canal": l.campaign.advertising_channel_type.name,
                    "ad_group_id": str(l.ad_group.id),
                    "criterion_id": str(c.criterion_id),
                    "texto": _texto(c.keyword.text),
                    "texto_hash": _hash(_texto(c.keyword.text).lower()),
                    "match_type": c.keyword.match_type.name,
                    "negativa": bool(c.negative),
                    "status": c.status.name,
                    "approval_status": c.approval_status.name,
                    "system_serving_status": c.system_serving_status.name,
                    "disapproval_reasons": motivos,
                }, ensure_ascii=False) + "\n")
                n_kw += 1
                k += 1
        except Exception as exc:
            falhas.append(f"{cid} keywords: {str(exc)[:150]}")

        print(f"{a:>5} anúncios · {p:>4} política · {k:>5} kw")

    for f in (f_anun, f_ativ, f_pol, f_kw):
        f.close()

    manifesto = {
        "capturado_em": capturado_em,
        "versao_api": "v25",
        "contas_operacionais": len(alvo),
        "mccs": sorted(so_mccs) or "todas as acessíveis",
        "linhas": {"anuncios": n_anun, "ativos": n_ativ,
                   "politica": n_pol, "keywords": n_kw},
        # A amostragem é declarada porque um arquivo estratificado lido como
        # censo produz taxa de reprovação inflada por construção.
        "amostragem": {
            "anuncios_vistos": n_anun_vistos,
            "anuncios_gravados": n_anun,
            "regra": f"todos com entrada de política + até {args.controle} "
                     f"limpos por conta, como controle",
            "keywords_vistas": n_kw_vistos,
            "keywords_gravadas": n_kw,
            "regra_keywords": "negativas + positivas não-APPROVED; "
                              "positivas aprovadas só na contagem",
            "distribuicoes_sao_censo": True,
        },
        "distribuicao": {
            "approval_status": dict(por_aprovacao.most_common()),
            "review_status": dict(por_revisao.most_common()),
            "topicos": dict(por_topico.most_common(40)),
            "destination_mismatch_url_types": dict(url_types.most_common()),
            "keyword_approval_status": dict(kw_aprovacao.most_common()),
            "keyword_disapproval_reasons": dict(kw_motivo.most_common()),
        },
        "colunas_nulas_por_construcao": [
            "landing_snapshot_hash", "expanded_final_url",
            "prompt_version", "spec_version", "is_exemptible",
        ],
        "falhas": falhas,
        "escopo": "ad_group_ad e ad_group_criterion, status != REMOVED, "
                  "todas as contas operacionais acessíveis",
        "somente_leitura": True,
    }
    (SAIDA / "manifesto.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "═" * 74)
    print(f"anúncios {n_anun}  ·  ativos {n_ativ}  ·  política {n_pol}  ·  kw {n_kw}")
    print("═" * 74)
    print("\napproval_status:")
    for k_, v in por_aprovacao.most_common():
        print(f"   {v:>7}  {k_}")
    print("\nreview_status:")
    for k_, v in por_revisao.most_common():
        print(f"   {v:>7}  {k_}")
    print("\ntópicos de política (top 20):")
    for k_, v in por_topico.most_common(20):
        print(f"   {v:>7}  {k_}")
    if url_types:
        print("\nDESTINATION_MISMATCH — qual URL brigou com qual:")
        for k_, v in url_types.most_common():
            print(f"   {v:>7}  {k_}")
    if kw_aprovacao:
        print("\nkeywords positivas por approval_status:")
        for k_, v in kw_aprovacao.most_common():
            print(f"   {v:>7}  {k_}")
    if kw_motivo:
        print("\nmotivos de reprovação de keyword:")
        for k_, v in kw_motivo.most_common(15):
            print(f"   {v:>7}  {k_}")
    if falhas:
        print(f"\n{len(falhas)} falha(s):")
        for f_ in falhas[:10]:
            print(f"   {f_}")
    print(f"\nsaída: {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
