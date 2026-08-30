"""O PERFIL DO RUN — o que é do projeto e do tema, sobreposto à doutrina do motor.

## O problema que isto resolve

O `config.yaml` misturava três donos diferentes no mesmo arquivo:

    run/routing/steps/ads/screenshot   -> do MOTOR (doutrina)
    site.domain/post_type              -> do PROJETO (cada site é um)
    canal oficial, termos do tema      -> do TEMA (cada funil é um)

Enquanto os três moram juntos, um segundo site exige um segundo arquivo de
configuração, e trocar de pauta exige editar YAML à mão. Foi assim que um funil
de cartão para negativado ia sair citando a Caixa Econômica: o config era do
funil de FGTS e ninguém tinha onde escrever o dele.

Aqui o motor passa a receber, por RUN, um perfil montado por quem tem o dado:

    site       <- `project_wordpress` do VOLC O.S. (o projeto é o site)
    wordpress  <- a credencial daquele projeto, decifrada pelo backend
    tema       <- o card do Pautador (termos da pauta, canal oficial preferido)
    teto       <- decisão do disparo, não do arquivo

E o `config.yaml` fica só com o que é do motor.

## O que este módulo NÃO faz

Não valida credencial e não fala com rede. Ele só sobrepõe campos. Se a senha
estiver errada, quem descobre é o teste de conexão da tela do projeto, antes de
qualquer dólar ser gasto — e não este módulo, no fim de um run.
"""
from __future__ import annotations

from typing import Any

from funnelforge.config.settings import Secrets, Settings, SiteConfig


def _texto(valor: Any) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def _lista(valor: Any) -> list[str]:
    if isinstance(valor, str):
        return [p.strip() for p in valor.split(",") if p.strip()]
    if isinstance(valor, (list, tuple)):
        return [_texto(v) for v in valor if _texto(v)]
    return []


def aplicar_perfil(settings: Settings, perfil: dict[str, Any] | None) -> Settings:
    """Devolve uma `Settings` NOVA com o projeto e o tema por cima da doutrina.

    Perfil ausente ou vazio devolve as settings intactas — é o caminho do
    comando legado e dos testes, que continuam lendo tudo do YAML.

    Campo ausente no perfil também não sobrescreve: o padrão do `config.yaml`
    vale. Isso é deliberado — um perfil parcial (só a credencial, digamos) não
    deve zerar o `post_type` do site.
    """
    if not perfil:
        return settings

    site_in = perfil.get("site") or {}
    wp_in = perfil.get("wordpress") or {}
    tema_in = perfil.get("tema") or {}

    site_atual = settings.site.model_dump()

    for chave in ("domain", "post_type", "lp_post_type"):
        if _texto(site_in.get(chave)):
            site_atual[chave] = _texto(site_in[chave])

    # O canal oficial PREFERIDO é do tema, não do site: os canais de um funil de
    # FGTS não são os de um funil de cartão. O VOLC O.S. tem esse dado por
    # entidade, em `official_source` — e ele é um NOME ("Serasa", "iFood"), não
    # uma URL, que é justamente o que `official_preference` aceita.
    preferencia = _lista(tema_in.get("official_preference")) or _lista(
        site_in.get("official_preference"))
    if preferencia:
        site_atual["official_preference"] = preferencia

    bloqueados = _lista(tema_in.get("blocked_hosts")) or _lista(site_in.get("blocked_hosts"))
    if bloqueados:
        site_atual["blocked_hosts"] = bloqueados

    novo = settings.model_copy(deep=True)
    novo.site = SiteConfig(**site_atual)

    # A credencial do WordPress vem do PROJETO, não do `.env` do motor. É o que
    # torna o motor multi-site: dois projetos, dois destinos, um processo. As
    # chaves de LLM continuam vindo do ambiente — elas são do motor, não do
    # cliente.
    if any(_texto(wp_in.get(k)) for k in ("url", "user", "app_token")):
        segredos = novo.secrets.model_dump()
        for de, para in (("url", "wp_url"), ("user", "wp_user"), ("app_token", "wp_app_token")):
            if _texto(wp_in.get(de)):
                segredos[para] = _texto(wp_in[de])
        novo.secrets = Secrets(**segredos)

    teto = perfil.get("teto_usd")
    if isinstance(teto, (int, float)) and teto > 0:
        novo.budget.max_usd_per_run = float(teto)
    teto_pagina = perfil.get("teto_pagina_usd")
    if isinstance(teto_pagina, (int, float)) and teto_pagina > 0:
        novo.budget.max_usd_per_page = float(teto_pagina)

    return novo


def termos_do_tema(perfil: dict[str, Any] | None) -> list[str]:
    """Os termos que identificam ESTA pauta, para o desempate do cross-funnel.

    Vão para `sitemap.cross_funnel_targets(theme=...)`, que usa a sobreposição
    com eles para decidir o que é "a mesma pauta com outro título" (redundante)
    e o que é vizinha. Sem isto o motor só tem o H1 da landing page — três ou
    quatro palavras — para representar um funil inteiro.

    O VOLC O.S. tem material melhor: as keywords de cada página do card e os
    apelidos da entidade.
    """
    return _lista(((perfil or {}).get("tema") or {}).get("termos"))
