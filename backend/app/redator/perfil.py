"""Monta o PERFIL DO RUN: o que o motor precisa saber e não tem como saber.

## O que é isto

O funnelforge tem um `config.yaml` com a doutrina dele — modelos por etapa,
forma do grafo, retentativas, âncoras de anúncio. Isso é do MOTOR e não muda
entre projetos.

Mas ele também precisa de duas coisas que são de OUTRA pessoa:

    do PROJETO  onde publicar (domínio, post types) e com que credencial
    do TEMA     qual o canal oficial preferido, e que termos identificam a pauta

Enquanto essas duas viviam no mesmo YAML, um segundo site exigia um segundo
arquivo e trocar de pauta exigia editar configuração à mão. Foi assim que um
funil de cartão para negativado ia sair citando a Caixa Econômica.

Aqui o VOLC O.S. monta esse pedaço, porque é ele quem tem o dado: o projeto está
em `project_wordpress` e o tema está no card.

## A senha

Sai daqui **decifrada**, porque o motor precisa dela para publicar. Duas
consequências que valem estar escritas:

1. O perfil é escrito em disco para o motor ler (ele roda como processo
   separado). Esse arquivo tem que ir para um diretório temporário com permissão
   restrita e ser apagado no fim — quem chama é responsável por isso, e é por
   isso que `montar_perfil` NÃO grava nada: ela devolve o dicionário e deixa a
   escrita para quem sabe onde ela pode acontecer.
2. Nada deste dicionário pode ser logado inteiro. Use `perfil_para_log`.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.seguranca import decifrar


class PerfilIncompleto(RuntimeError):
    """Falta algo sem o que o run não deve nem começar.

    Levantar aqui é barato; descobrir o mesmo problema no último passo de um run
    custa o run inteiro (~US$ 2 e ~45 min).
    """


# Declaração medida no tema público do Crédito Up. Ela é do SITE, não do tema
# do funil, e por isso entra no perfil apenas quando o destino é exatamente o
# domínio medido. Um segundo WordPress continua fail-closed até ter a própria
# declaração cadastrada — nunca herda a identidade do Crédito Up por acidente.
_RODAPE_CREDITOUP = (
    "Sobre o nosso site: o site se reserva unicamente a trazer conteúdos "
    "informativos e notícias de interesse social. Em hipótese alguma o site faz "
    "qualquer tipo de pedido de dados pessoais sem respeitar a LGPD e não solicita "
    "qualquer valor para mediar recebimentos de benefícios sociais. Os conteúdos "
    "aqui publicados são de caráter informativo e não possuem vínculo, parceria ou "
    "qualquer ligação com órgãos públicos ou entidades governamentais. O site é "
    "financiado por blocos de anúncios em parceria com o Google Adsense e não tem "
    "relação nenhuma com os anunciantes. Sobre Nós - Contato - Política de "
    "Privacidade - Termos."
)


def _termos_do_card(arquitetura: Dict[str, Any], entidade: Dict[str, Any] | None) -> List[str]:
    """Os termos que identificam esta pauta, para o desempate do cross-funnel.

    O motor, sozinho, teria só o H1 da landing page — três ou quatro palavras
    para representar um funil inteiro. Aqui juntamos o que o card já tem: as
    keywords de cada página (que a ponte recupera dos `writing_jobs`) e os
    apelidos da entidade.
    """
    termos: List[str] = []
    for job in arquitetura.get("writing_jobs") or []:
        brief = (job or {}).get("writer_briefing") or {}
        kw = brief.get("keywords")
        if isinstance(kw, str):
            termos += [p.strip() for p in kw.split(",") if p.strip()]
        elif isinstance(kw, list):
            termos += [str(p).strip() for p in kw if str(p).strip()]
    if entidade:
        for campo in ("canonical_name", "full_name"):
            v = entidade.get(campo)
            if isinstance(v, str) and v.strip():
                termos.append(v.strip())
        for a in entidade.get("aliases") or []:
            if isinstance(a, str) and a.strip():
                termos.append(a.strip())
    # dedup preservando ordem: os primeiros são as keywords, que pesam mais
    vistos: set[str] = set()
    saida: List[str] = []
    for t in termos:
        k = t.lower()
        if k not in vistos:
            vistos.add(k)
            saida.append(t)
    return saida


def _canal_oficial(entidade: Dict[str, Any] | None) -> List[str]:
    """A PREFERÊNCIA de canal oficial, vinda de `official_source` da entidade.

    É um NOME ("Serasa", "iFood", "Caixa Econômica Federal"), não uma URL — e o
    `official_preference` do motor aceita nome justamente por isso. Preferência
    não autoriza nada: um candidato que casa sobe na fila; não casar não reprova.
    A autorização continua vindo da pesquisa.
    """
    if not entidade:
        return []
    v = entidade.get("official_source")
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return []


def montar_perfil(
    *,
    perfil_wp: Dict[str, Any],
    arquitetura: Dict[str, Any],
    entidade: Dict[str, Any] | None = None,
    teto_usd: float | None = None,
    teto_pagina_usd: float | None = None,
    editorial_v2: bool = False,
    preset: str | None = None,
) -> Dict[str, Any]:
    """O dicionário que o motor recebe em `--perfil`.

    `perfil_wp` é a linha de `project_wordpress` (com o token AINDA cifrado).
    `arquitetura` é o `funnel_architecture` do card. `entidade` é opcional e
    entra só para enriquecer tema e canal oficial.

    `editorial_v2` liga o fluxo editorial novo NESTE funil (briefing, revisor,
    recibo — contrato entre trilhas, decisão 1). Vai na raiz do perfil, como
    `teto_usd`, e só quando é `True` de verdade: não enviar é o padrão, e o
    motor segue no fluxo atual com o perfil byte a byte igual ao de antes.
    """
    wp_url = (perfil_wp.get("wp_url") or "").rstrip("/")
    wp_user = (perfil_wp.get("wp_username") or "").strip()
    cifrado = perfil_wp.get("wp_app_password_enc")

    if not wp_url or not wp_user:
        raise PerfilIncompleto("Este projeto não tem URL ou usuário do WordPress cadastrados.")
    if not cifrado:
        raise PerfilIncompleto("Este projeto não tem Application Password cadastrado.")

    senha = decifrar(cifrado)
    if not senha:
        raise PerfilIncompleto("A credencial deste projeto está ilegível — recadastre.")

    if not (arquitetura.get("pages") or []):
        raise PerfilIncompleto("Este card não tem arquitetura de funil.")

    perfil: Dict[str, Any] = {
        "site": {
            # O domínio do funil é o do WordPress: é onde as páginas vão morar e
            # é contra ele que a lei de mesmo-domínio do motor decide o que é
            # link interno.
            "domain": wp_url,
            "post_type": perfil_wp.get("post_type") or "rec",
            "lp_post_type": perfil_wp.get("lp_post_type") or "r",
        },
        "wordpress": {"url": wp_url, "user": wp_user, "app_token": senha},
        "tema": {
            "termos": _termos_do_card(arquitetura, entidade),
            "official_preference": _canal_oficial(entidade),
        },
    }
    if wp_url == "https://creditoup.com.br":
        perfil["site"].update({
            "rodape_institucional": _RODAPE_CREDITOUP,
            "rodape_institucional_persistente": True,
        })
    if preset:
        perfil["preset"] = preset
    if teto_usd:
        perfil["teto_usd"] = float(teto_usd)
    if teto_pagina_usd:
        perfil["teto_pagina_usd"] = float(teto_pagina_usd)
    if editorial_v2 is True:
        perfil["editorial_v2"] = True
    return perfil


PRESET_CANONICO = "completo_chatgpt"


def card_do_motor(
    *,
    oportunidade: Dict[str, Any],
    entidade: Dict[str, Any] | None,
    arquitetura: Dict[str, Any],
) -> Dict[str, Any]:
    """O card que o motor usa para pesquisar ANTES de arquitetar.

    Sem ele, o disparo da interface entregava ao motor só o plano pronto: sem
    PAA, sem pesquisa antecipada, sem brief e sem os pacotes pré-redação que
    validam ferramentas e destinos antes da promessa. Os 8 runs disparados pelo
    worker em 08/10 não tinham brief nem pacotes. A arquitetura aprovada no
    Pautador segue como referência (`historico.arquitetura_referencia`), não
    como plano congelado: o arquiteto a revê com a pesquisa em mãos.
    """
    from app.data.countries import resolve_country

    ent = entidade or {}
    geo = resolve_country(ent.get("country"),
                          code=ent.get("country_code") or oportunidade.get("country_code")) or {}
    termos = _termos_do_card(arquitetura, entidade)
    paginas = arquitetura.get("pages") or [{}]
    tema = (ent.get("canonical_name") or ent.get("full_name")
            or (termos[0] if termos else "") or str((paginas[0] or {}).get("h1_title") or ""))
    card: Dict[str, Any] = {
        "main_keyword": tema,
        "keyword": tema,
        "entidade": ent.get("full_name") or tema,
        "country": geo.get("country_name") or ent.get("country") or "",
        "native_language": geo.get("native_language") or ent.get("language") or "",
        "location_code": geo.get("google_ads_geo_target"),
        "language_code": geo.get("language_code"),
        "description": ent.get("description") or "",
        "concrete_pain": oportunidade.get("concrete_pain") or "",
        "search_terms": termos,
        "expansion_hooks": [*(ent.get("related_systems") or []), *(ent.get("aliases") or [])],
        "historico": {"arquitetura_referencia": arquitetura},
    }
    for chave in ("contexto_de_leitura", "contexto_de_busca", "contexto_de_anuncio"):
        if isinstance(arquitetura.get(chave), dict):
            card[chave] = arquitetura[chave]
    if str(oportunidade.get("insights") or "").strip():
        card["editorial_context"] = str(oportunidade["insights"]).strip()
    return card


def perfil_para_log(perfil: Dict[str, Any]) -> Dict[str, Any]:
    """A mesma coisa, sem a senha. Use SEMPRE isto para logar ou devolver."""
    from app.seguranca import mascara

    copia = {k: (dict(v) if isinstance(v, dict) else v) for k, v in perfil.items()}
    wp = copia.get("wordpress")
    if isinstance(wp, dict) and wp.get("app_token"):
        wp["app_token"] = mascara(wp["app_token"])
    return copia
