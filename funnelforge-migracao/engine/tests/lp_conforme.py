# funnel-forge/tests/lp_conforme.py
"""A LP que PASSA no portão do destino pago — fixture compartilhada.

Ela existe porque a LP deixou de ser isenta do portão de conteúdo. Antes, um
artefato de brinquedo (`content="markers"`, quatro seções de uma linha) bastava
para exercitar a mecânica de publicação, porque nada olhava o conteúdo da LP.
Agora olha: um teste de mecânica que use artefato de brinquedo reprova por
tamanho e por identidade ausente antes de chegar à mecânica que ele quer medir.

O que faz esta fixture ser "conforme" é o que a política mede, e nada além:
600 palavras visíveis de piso, CTA cujo texto descreve o caminho do destino,
nenhum hyperlink externo, e a identidade/divulgação declaradas em
`site.rodape_institucional` (ver `config/settings.py` para por que a declaração
existe e por que vazio é fail-closed).
"""
from __future__ import annotations

#: O rodapé institucional MEDIDO na captura preservada de
#: `docs/closure/hermes-redator-google-ads-policy-incident-v1/evidence-public/
#: common_desktop-7c674d1d7daf.html` — a LP `/r/fgts-saque-aniversario/`, deste
#: motor e deste tema. É a mesma URL cujos bloqueios em `GATE-RECEIPTS.json`
#: NÃO incluem `IDENTIDADE_*`, `AVISO_NAO_OFICIAL_AUSENTE` nem
#: `DIVULGACAO_DE_MONETIZACAO_AUSENTE`: o rodapé existe, e foi medido.
RODAPE_INSTITUCIONAL = (
    "Sobre o nosso site: o site se reserva unicamente a trazer conteudos "
    "informativos e noticias de interesse social. Em hipotese alguma o site faz "
    "pedido de dados pessoais sem respeitar a LGPD e nao solicita qualquer valor. "
    "Os conteudos aqui publicados sao de carater informativo e nao possuem "
    "vinculo, parceria ou qualquer ligacao com orgaos publicos ou entidades "
    "governamentais. O site e financiado por blocos de anuncios em parceria com o "
    "Google Adsense e nao tem relacao com os anunciantes. Sobre Nos - Contato - "
    "Politica de Privacidade. Projeto da Volc Negocios Digitais 42.724.548/0001-24."
)


def corpo_com_palavras(tema: str, n: int = 160) -> str:
    """Um parágrafo com `n` palavras próprias.

    O piso de conteúdo original do portão é 600 palavras VISÍVEIS. Encher com
    palavras únicas por tema (em vez de repetir uma frase) mantém o texto também
    fora do radar do guarda de unicidade dos testes de funil.
    """
    palavras = " ".join(f"{tema}{i:03d}" for i in range(n))
    return f"<p>Orientacao pratica sobre {tema}. {palavras}</p>"


def conteudo_da_lp(**troca) -> dict:
    """O JSON estruturado que o redator devolve para a LP.

    ⚠️ A ORDEM de `cta_texts` é medida: `cta_texts[i]` é renderizado no botão
    cujo destino é `funnel_hrefs[i]` (ver `lp_template._BUTTON_HREF`). Trocar
    dois de lugar produz `ANCORA_INCONGRUENTE_COM_DESTINO` — um botão que
    promete um assunto e leva a outro.
    """
    base = {
        "hero_title": "Saque-Aniversario do FGTS: regras e simulacao",
        "hero_subtitle": "Regras e prazos para 2026 - toque abaixo e veja como avaliar",
        "article_title": "Saque-Aniversario do FGTS em 2026",
        "intro": corpo_com_palavras("intro"),
        "sections": [
            {"title": "O que e o saque-aniversario", "body": corpo_com_palavras("secaoum")},
            {"title": "Quem tem direito", "body": corpo_com_palavras("secaodois")},
            {"title": "Como avaliar as vantagens", "body": corpo_com_palavras("secaotres")},
            {"title": "Prazos e cuidados", "body": corpo_com_palavras("secaoquatro")},
        ],
        "faq": [{"q": "Posso desistir?", "a": "Sim, com carencia."}],
        "transition": "<p>Veja nos botoes abaixo o caminho do seu caso.</p>",
        "cta_texts": ["Ver quem tem direito", "Ver as regras do saque", "Ver os prazos"],
    }
    base.update(troca)
    return base
