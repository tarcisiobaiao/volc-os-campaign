"""O que o motor diz, e com que ferramenta ele diz.

## As três coisas que se confundem quando ficam na mesma tela

**A doutrina** (`pipeline/doctrine.py`) é o que o motor NUNCA escreve e o que ele
sempre escreve: os termos de medo proibidos, os CTAs em primeira pessoa que não
passam, as âncoras de conformidade obrigatórias. Editar isso é decisão
editorial — e uma edição só muda quatro prompts, dois validadores, o portão da
LP e o rodapé, POR CONSTRUÇÃO, porque todos leem da mesma fonte.

**Os prompts** (`prompts/*.jinja`) são as instruções de cada agente. Editar isso
muda o que o modelo entende da tarefa.

**Os modelos** (`config.yaml → steps`) são com que ferramenta e a que preço. A
mesma instrução em `gpt-4.1` e em `gemini-3.5-flash` custa e rende diferente.

Misturar as três cria a ilusão de que trocar o modelo do juiz e renomear um
termo proibido são a mesma classe de escolha. Não são: a primeira muda a conta,
a segunda muda o produto.

## Somente leitura, hoje — e isso é uma decisão, não uma pendência

Nada aqui grava. Um prompt ruim salvo pela tela quebraria TODO run seguinte, e o
arquivo em disco não tem histórico: não há como voltar atrás. Enquanto não
existir versionamento e um ensaio barato, ver é o que se pode fazer com
segurança — e ver já é infinitamente mais do que existia, que era nada.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

# O que cada lista da doutrina governa, em português e com a consequência dita.
# Sem isto, a tela mostra sete listas de strings sem explicar o que muda ao
# mexer em cada uma.
O_QUE_GOVERNA: Dict[str, Dict[str, str]] = {
    "BANNED_FEAR": {
        "rotulo": "termos de medo proibidos",
        "efeito": "O redator não pode usá-los, e o validador `calm_utility` reprova a "
                  "página que os contiver. É o que impede o funil de virar alarmismo.",
    },
    "BANNED_OFFICIAL": {
        "rotulo": "termos que fingem ser oficiais",
        "efeito": "Bloqueia linguagem que faria o leitor achar que está num canal do "
                  "governo ou do banco. Reprova no gate da LP também.",
    },
    "BANNED_CTA_FIRST_PERSON": {
        "rotulo": "CTAs em primeira pessoa",
        "efeito": "\"Quero meu cartão\" sugere que o clique executa o pedido. O "
                  "validador `cta_style` reprova.",
    },
    "BANNED_CTA_EXECUTION": {
        "rotulo": "CTAs que prometem executar",
        "efeito": "O funil informa; quem executa é o canal oficial. Um CTA que promete "
                  "executar entrega o que a página não tem.",
    },
    "REQUIRED_COMPLIANCE_ANCHORS": {
        "rotulo": "âncoras de conformidade obrigatórias",
        "efeito": "Precisam aparecer na página. Faltando, o portão de conteúdo reprova.",
    },
    "APPROVED_CTA_EXEMPLARS": {
        "rotulo": "CTAs aprovados (exemplos)",
        "efeito": "Vão no prompt como referência do que É aceitável — sem eles o modelo "
                  "só sabe o que não pode.",
    },
}

# Quais passos do pipeline leem cada prompt. É o que responde "se eu mexer
# aqui, o que muda?" antes de mexer.
#
# ⚠️ Todo `.jinja` do motor tem de ter dono aqui — `test_configuracao` reprova
# prompt sem rótulo. Os do fluxo editorial v2 (`briefing`, `revisor` e os
# `*_v2`) só rodam com `run.editorial_v2` ligado (config ou perfil do funil).
QUEM_USA_O_PROMPT: Dict[str, str] = {
    "redator_p1.jinja": "a landing page (o JSON de slots)",
    "redator_pages.jinja": "as páginas de solução",
    "redator_presell.jinja": "os hubs de pré-venda",
    "redator_widget.jinja": "o widget interativo das soluções",
    "judge.jinja": "o juiz que reprova a redação (as interiores sempre; a landing "
                   "page só quando traz `editorial`)",
    "seo.jinja": "o título SEO (que vira o H1 visível das páginas interiores) e a "
                 "meta description",
    "extractor.jinja": "legado: só o comando `funnelforge run` (briefing em DOCX ou "
                       "texto). O disparo do VOLC O.S. usa `run-volc`, que chega com o "
                       "plano pronto e não passa por este prompt",
    "image_prompt.jinja": "a imagem das páginas interiores",
    "image_prompt_lp.jinja": "a imagem da landing page",
    "declarador_engajamento.jinja": "o arquétipo de engajamento de cada página",
    "blocks_gutenberg.jinja": "a montagem dos blocos do WordPress",
    # 17–18/09/2026
    "editorial_identity.jinja": "a identidade do publisher independente (não é "
                                "banco, órgão nem canal oficial), no topo dos prompts "
                                "dos redatores, do juiz, do SEO e do widget",
    "reader_contract.jinja": "o contrato editorial de cada página (dúvida do leitor, "
                             "entrega útil, rótulo do CTA e conexões), incluído nos "
                             "redatores da landing page, das soluções e dos hubs",
    "interior_editorial.jinja": "os dados e as regras de redação das páginas "
                                "interiores (base factual, links, anúncios), incluído "
                                "nos redatores das soluções e dos hubs",
    "image_review.jinja": "a revisão da imagem gerada (logos, insígnias oficiais, "
                          "dados pessoais, qualidade) antes de ela entrar na página",
    # fluxo editorial v2 — só roda com `run.editorial_v2` (config ou perfil do funil)
    "briefing.jinja": "o briefing de cada página no fluxo editorial v2 (intenção, "
                      "leitor, promessa e limites, com fato separado de hipótese), "
                      "antes da redação",
    "revisor.jinja": "o revisor contextual do fluxo editorial v2, que aponta e ajusta "
                     "com evidência (substitui o juiz)",
    "redator_p1_v2.jinja": "a landing page no fluxo editorial v2, escrita a partir do "
                           "briefing",
    "redator_pages_v2.jinja": "as páginas de solução no fluxo editorial v2",
    "redator_presell_v2.jinja": "os hubs de pré-venda no fluxo editorial v2",
    "reader_contract_v2.jinja": "o briefing da página e como escrever a partir dele, "
                                "incluído nos redatores do fluxo v2",
    "interior_editorial_v2.jinja": "os dados e as regras de redação das páginas "
                                   "interiores no fluxo v2 (base factual, links, "
                                   "anúncios), incluído nos redatores v2",
    "blocks_gutenberg_v2.jinja": "a biblioteca de blocos do WordPress no fluxo v2, sem "
                                 "cota de blocos",
    "seo_v2.jinja": "o título SEO (H1 visível das interiores) e a meta description no "
                    "fluxo v2, antes da revisão",
    "image_prompt_v2.jinja": "a imagem das páginas interiores no fluxo v2",
    "image_prompt_lp_v2.jinja": "a imagem da landing page no fluxo v2",
}


def _tupla_do_fonte(fonte: str, nome: str) -> List[str]:
    """Lê uma tupla de strings do `doctrine.py` sem importar o módulo.

    Ler o TEXTO e não `import doctrine` é deliberado: o backend e o motor rodam
    em ambientes Python separados (venvs diferentes), então o import nem sempre
    é possível — e mesmo quando é, ele executaria o módulo inteiro só para ler
    sete listas.
    """
    m = re.search(rf"^{nome}[^=]*=\s*\((.*?)\)\s*$", fonte, re.S | re.M)
    if not m:
        return []
    return re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))


def ler(raiz: Path) -> Dict[str, Any]:
    """Tudo que se pode dizer sobre a configuração do motor, sem executá-lo."""
    doutrina: List[Dict[str, Any]] = []
    fonte_doutrina = ""
    try:
        fonte_doutrina = (raiz / "src" / "funnelforge" / "pipeline"
                          / "doctrine.py").read_text(encoding="utf-8")
    except OSError:
        pass

    for nome, meta in O_QUE_GOVERNA.items():
        itens = _tupla_do_fonte(fonte_doutrina, nome)
        doutrina.append({"nome": nome, "itens": itens, "total": len(itens), **meta})

    aviso = ""
    m = re.search(r'^COMPLIANCE_NOTICE_TEXT[^=]*=\s*\((.*?)\)\s*$',
                  fonte_doutrina, re.S | re.M)
    if m:
        aviso = " ".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)))

    prompts: List[Dict[str, Any]] = []
    pasta = raiz / "src" / "funnelforge" / "prompts"
    if pasta.is_dir():
        for p in sorted(pasta.glob("*.jinja")):
            try:
                texto = p.read_text(encoding="utf-8")
            except OSError:
                continue
            prompts.append({
                "arquivo": p.name,
                "usado_por": QUEM_USA_O_PROMPT.get(p.name, ""),
                "linhas": texto.count("\n") + 1,
                "caracteres": len(texto),
                "conteudo": texto,
            })

    passos: List[Dict[str, Any]] = []
    try:
        import yaml
        bruto = yaml.safe_load((raiz / "config.yaml").read_text(encoding="utf-8")) or {}
        for chave, cfg in (bruto.get("steps") or {}).items():
            if not isinstance(cfg, dict):
                continue
            passos.append({
                "passo": chave,
                "modelo": cfg.get("model") or "",
                "reservas": cfg.get("fallbacks") or [],
                "temperatura": cfg.get("temperature"),
                "validadores": cfg.get("validators") or [],
            })
        corrida = bruto.get("run") or {}
    except Exception:  # noqa: BLE001 — sem config, a tela ainda tem de abrir
        corrida = {}

    return {
        "doutrina": doutrina,
        "aviso_de_conformidade": aviso,
        "prompts": prompts,
        "passos": passos,
        "corrida": {k: corrida.get(k) for k in (
            "publish", "publish_status", "featured_image", "official_screenshots",
            "widgets_enabled", "max_retries", "research_max_attempts")},
        # Dito em voz alta na resposta, não só na tela: quem consumir esta rota
        # não deve assumir que existe um PUT em algum lugar.
        "somente_leitura": True,
        "por_que": "Um prompt ruim salvo aqui quebraria todo run seguinte, e o "
                   "arquivo em disco não tem histórico — não haveria como voltar "
                   "atrás. Edição espera versionamento e um ensaio barato.",
    }
