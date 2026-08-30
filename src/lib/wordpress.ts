/**
 * O caminho de volta para o WordPress.
 *
 * ## Por que a base sai da URL da página, e não de um campo novo
 *
 * `paginas_publicadas[].url_wp` é o que o WordPress DEVOLVEU, verbatim — é dele
 * que a atribuição de receita depende, por igualdade de string exata com
 * `campaign_funnel_urls`. Ele já carrega a origem do site, então derivar dali
 * não acrescenta nenhuma fonte da verdade nova nem exige o perfil do projeto na
 * tela.
 *
 * ⚠️ E a origem TROCA de forma ao longo da vida da página: rascunho volta
 * `https://site.com/?post_type=r&p=2163` e publicada volta
 * `https://site.com/r/slug/`. As duas têm a mesma origem — é justamente por
 * isso que se usa `URL.origin` e não um recorte de string.
 */

export interface PaginaNoWordPress {
  post_id: number;
  url_wp: string;
  status_wp: string;
}

/** `https://site.com/wp-admin/post.php?post=2163&action=edit`, ou `null`.
 *
 *  Devolve `null` quando a URL não é analisável ou falta o `post_id` — um link
 *  quebrado para o admin é pior que link nenhum: ele leva o operador ao painel
 *  do WordPress com um erro, e ele não sabe se a culpa é da página ou dele. */
export function linkDeEdicao(p: PaginaNoWordPress | null | undefined): string | null {
  if (!p?.post_id || !p.url_wp) return null;
  try {
    const { origin } = new URL(p.url_wp);
    return `${origin}/wp-admin/post.php?post=${p.post_id}&action=edit`;
  } catch {
    return null;
  }
}

/** `true` quando a página está no ar de verdade.
 *
 *  O motor publica tudo como rascunho de propósito
 *  (`engine/config.yaml: publish_status: draft` — "generate → draft → human
 *  reviews and clicks publish"), então `draft` é o estado NORMAL logo após um
 *  run, não um defeito. O que muda o mundo é este `publish`: é ele que troca a
 *  URL provisória pelo permalink e destrava o Hub de Tráfego. */
export function estaNoAr(p: PaginaNoWordPress | null | undefined): boolean {
  return p?.status_wp === 'publish';
}
