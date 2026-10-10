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

from funnelforge.config.settings import (
    OpenAIConfig,
    RunConfig,
    Secrets,
    Settings,
    SiteConfig,
    StepConfig,
    aplicar_modo_openai,
)


def _texto(valor: Any) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def _lista(valor: Any) -> list[str]:
    if isinstance(valor, str):
        return [p.strip() for p in valor.split(",") if p.strip()]
    if isinstance(valor, (list, tuple)):
        return [_texto(v) for v in valor if _texto(v)]
    return []


# O que o `config_snapshot.json` de um run fixa para a retomada. Site e
# credencial continuam vindo do perfil: são do projeto, não do run.
_CONFIG_DO_RUN = ("run", "steps", "routing", "ads", "index", "uniqueness",
                  "screenshot", "budget", "openai")


def configuracao_efetiva_do_run(settings: Settings, snapshot: dict[str, Any]) -> Settings:
    """As settings com que o run NASCEU, para retomá-lo igual.

    Inferir o preset pelo modo de autenticação errava em silêncio sempre que o
    run tinha outra combinação (workers, prints, modelos, tetos). O snapshot é
    o registro do que de fato rodou; os segredos continuam os do ambiente.
    """
    dados = settings.model_dump()
    for chave in _CONFIG_DO_RUN:
        if chave in snapshot:
            dados[chave] = snapshot[chave]
    return Settings.model_validate(dados)


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
    if _texto(site_in.get("rodape_institucional")):
        site_atual["rodape_institucional"] = _texto(site_in["rodape_institucional"])
    if isinstance(site_in.get("rodape_institucional_persistente"), bool):
        site_atual["rodape_institucional_persistente"] = site_in["rodape_institucional_persistente"]

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

    # Preset fechado e versionado para ChatGPT + concorrência entre páginas.
    # IMPORTANTE: o preset não escolhe um motor editorial reduzido. Há um único
    # pipeline de qualidade; velocidade vem de `page_workers`, cache e execução
    # concorrente de passos independentes. `rapido_chatgpt` e apenas o alias
    # legado para cards ja gravados; disparos novos usam `completo_chatgpt`.
    preset = _texto(perfil.get("preset"))
    if preset:
        if preset not in {"completo_chatgpt", "rapido_chatgpt"}:
            raise ValueError(f"preset de execução desconhecido: {preset}")
        novo.run = RunConfig(**{
            **novo.run.model_dump(),
            # O motor completo conserva as duas tentativas da doutrina. A
            # aceleracao vem de page_workers, nunca de retirar a chance de SEO,
            # briefing ou redacao corrigirem um gate objetivo.
            "max_retries": novo.run.max_retries,
            # Dossie orientado por requisitos + imagens/revisoes das cinco
            # paginas pode legitimamente passar de 40 chamadas. Continua
            # finito, mas sem cortar um funil saudavel na ultima etapa.
            "max_chamadas_llm": 60,
            # A LP sem hero não é um funil pronto. O build rápido agora falha
            # fechado quando o provider/ativo não entrega a imagem, em vez de
            # publicar silenciosamente um template incompleto.
            "imagens_habilitadas": True,
            "dossie_factual": True,
            "page_workers": 3,
            "perfil": "completo",
            "publish_status": "draft",
            "official_screenshots": True,
            "widgets_enabled": True,
            "editorial_v2": True,
        })
        passos = {
            nome: StepConfig(**{
                **passo.model_dump(),
                "model": ("chatgpt/gpt-6.1-sol"
                          if nome in {"judge", "revisor", "dossie"}
                          else "chatgpt/gpt-6-sol"),
                "fallbacks": [],
                **({"web_search": True, "reasoning_effort": "low"}
                   if nome == "dossie" else {}),
            })
            for nome, passo in novo.steps.items()
        }
        passos["dossie"] = StepConfig(
            model="chatgpt/gpt-6.1-sol", fallbacks=[], temperature=0.2,
            validators=[], web_search=True, reasoning_effort="low",
        )
        # A sessão ChatGPT usada para texto não aceita entrada de imagem. A
        # revisão visual é, portanto, a única etapa textual explicitamente
        # roteada à API Gemini multimodal. Isto não é fallback: o modelo é
        # fixo, auditável e a ausência da chave falha apenas essa etapa.
        passos["image_review"] = StepConfig(
            model="gemini/gemini-3.5-flash", fallbacks=[], temperature=0.0,
            validators=[],
        )
        novo.steps = passos
        novo.openai = OpenAIConfig(
            auth_mode="chatgpt_plan",
            writer_model="gpt-6-sol",
            judge_model="gpt-6.1-sol",
            reviewer_model="gpt-6.1-sol",
            reasoning_effort="high",
            allow_api_key_fallback=False,
            # `False` permite somente o passo Gemini declarado acima. Todos os
            # passos `chatgpt/*` continuam sem fallback faturado.
            somente_plano=False,
            armazenamento="keychain",
        )
        novo = aplicar_modo_openai(novo)
    # Only this typed routing choice is overridable, never the gate definitions.
    if "terminal_exit_policy" in tema_in:
        novo.run = RunConfig(**{
            **novo.run.model_dump(),
            "terminal_exit_policy": tema_in["terminal_exit_policy"],
        })
    # O RAMO EDITORIAL NOVO é escolha POR FUNIL (contrato entre as trilhas,
    # decisão 1): o backend liga no perfil do card, sem tocar no config.yaml.
    # Aceita `tema.editorial_v2` (o mesmo lugar do `terminal_exit_policy`) e
    # `editorial_v2` na raiz; o tema vence, por ser o mais específico. Só um
    # booleano DE VERDADE conta — "true" em texto não liga nada, porque ligar o
    # ramo por engano de serialização mudaria prompts e gasto sem ninguém ver.
    escolha = tema_in.get("editorial_v2", perfil.get("editorial_v2"))
    if isinstance(escolha, bool):
        novo.run = RunConfig(**{**novo.run.model_dump(), "editorial_v2": escolha})

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
