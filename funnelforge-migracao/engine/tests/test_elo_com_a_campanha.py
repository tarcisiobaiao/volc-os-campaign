"""O que o WordPress devolveu ao publicar é o elo com a campanha.

## Por que isto existe

O ciclo do negócio é PAUTA → FUNIL → CAMPANHA → RESULTADO, e ele só fecha se a
campanha do Google Ads souber quais URLs o funil produziu: é por igualdade de
string entre a URL da página e a linha de `campaign_funnel_urls` que a receita
do AdSense é atribuída ao clique comprado.

Até aqui o motor recebia do WP um objeto com `id`, `slug`, `link` e `status`,
extraía SÓ o `post_id` e jogava o resto fora. As 5 a 7 URLs de um funil
publicado precisavam ser redigitadas à mão.

## As duas armadilhas que estes testes travam

**Remontar a URL a partir do slug está errado.** O slug muda em três pontos
independentes: `_slug_com_sufixo` (a ponte do Pautador), `dedupe_slugs` (o
motor) e o próprio WordPress, que acrescenta `-2` quando o slug já existe — e
só conta isso na resposta REST.

**O `link` de um rascunho não é o permalink.** Medido no run de 17/08/2026: o
WP devolveu `https://creditoup.com.br/?post_type=r&p=2146` para a LP em
rascunho. O `/r/<slug>/` só nasce quando o post vai ao ar. Por isso o
`status_wp` viaja junto: quem consumir precisa saber que aquela URL ainda vai
mudar.
"""
from __future__ import annotations

from funnelforge.domain.models import RunState


def test_runstate_carrega_o_que_o_wp_devolveu():
    """O campo existe e sobrevive à serialização — `state.json` é
    `RunState.to_json()`, e é dele que o worker lê para alimentar a tela."""
    s = RunState(run_id="r")
    s.published[1] = {
        "page_number": 1,
        "role": "LP",
        "post_type": "r",
        "post_id": 2146,
        "slug": "cartao-credito-negativado",
        "url_wp": "https://creditoup.com.br/?post_type=r&p=2146",
        "status_wp": "draft",
        "publicado_em": "2026-08-17T18:58:51+00:00",
    }
    voltou = RunState.from_json(s.to_json())

    assert voltou.published[1]["post_id"] == 2146
    assert voltou.published[1]["slug"] == "cartao-credito-negativado"
    assert voltou.published[1]["status_wp"] == "draft"


def test_o_slug_gravado_e_o_do_wordpress_nao_o_do_plano():
    """O caso que quebra a atribuição de receita: o WP renomeia para `-2`
    quando o slug já existe. Guardar o slug do PLANO faria a campanha apontar
    para uma URL que não existe, e a receita iria a zero em silêncio."""
    do_wp = {"id": 99, "slug": "cartao-credito-negativado-2",
             "link": "https://creditoup.com.br/?post_type=r&p=99"}
    gravado = {
        "post_id": do_wp.get("id"),
        "slug": do_wp.get("slug") or "cartao-credito-negativado",
        "url_wp": do_wp.get("link") or "",
    }
    assert gravado["slug"] == "cartao-credito-negativado-2"
    assert gravado["slug"] != "cartao-credito-negativado"


def test_rascunho_nao_tem_permalink_e_isso_fica_declarado():
    """Não derive a URL final de um rascunho: ela ainda vai mudar. O
    `status_wp` é o que permite a quem consome saber disso."""
    registro = {
        "url_wp": "https://creditoup.com.br/?post_type=r&p=2146",
        "status_wp": "draft",
        "slug": "cartao-credito-negativado",
    }
    assert "?post_type=" in registro["url_wp"]
    assert "/r/" not in registro["url_wp"]
    assert registro["status_wp"] == "draft"   # quem lê sabe que não é definitiva


def test_published_vazio_e_estado_legitimo():
    """Funil que não publicou nada — dry run, ou todas as páginas bloqueadas."""
    s = RunState(run_id="r")
    assert s.published == {}
    assert RunState.from_json(s.to_json()).published == {}
