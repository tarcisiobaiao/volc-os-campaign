/**
 * O link de volta para o editor do WordPress.
 *
 * A origem sai da `url_wp` que o WP devolveu — e ela TROCA de forma na vida da
 * página: rascunho volta `?post_type=r&p=2163`, publicada volta `/r/slug/`.
 * As duas têm a mesma origem, e é por isso que se usa `URL.origin` em vez de
 * recortar string.
 */
import { describe, expect, it } from 'vitest';

import { estaNoAr, linkDeEdicao } from '../wordpress';

describe('linkDeEdicao', () => {
  it('monta o link do admin a partir da URL de rascunho', () => {
    expect(linkDeEdicao({
      post_id: 2163, status_wp: 'draft',
      url_wp: 'https://creditoup.com.br/?post_type=r&p=2163',
    })).toBe('https://creditoup.com.br/wp-admin/post.php?post=2163&action=edit');
  });

  it('monta o mesmo link a partir do permalink já publicado', () => {
    expect(linkDeEdicao({
      post_id: 2163, status_wp: 'publish',
      url_wp: 'https://creditoup.com.br/r/maquininha-de-cartao-menor-taxa/',
    })).toBe('https://creditoup.com.br/wp-admin/post.php?post=2163&action=edit');
  });

  it('devolve null em vez de um link quebrado', () => {
    // Link quebrado é pior que link nenhum: leva o operador ao painel do
    // WordPress com um erro, e ele não sabe se a culpa é da página ou dele.
    expect(linkDeEdicao(null)).toBeNull();
    expect(linkDeEdicao({ post_id: 0, status_wp: 'draft', url_wp: 'https://x.com/' })).toBeNull();
    expect(linkDeEdicao({ post_id: 1, status_wp: 'draft', url_wp: 'não é url' })).toBeNull();
  });
});

describe('estaNoAr', () => {
  it('só `publish` conta', () => {
    const base = { post_id: 1, url_wp: 'https://x.com/' };
    expect(estaNoAr({ ...base, status_wp: 'publish' })).toBe(true);
    // `draft` é o estado NORMAL logo após um run: o motor publica tudo como
    // rascunho de propósito. Não é defeito, e não pode parecer "no ar".
    expect(estaNoAr({ ...base, status_wp: 'draft' })).toBe(false);
    expect(estaNoAr({ ...base, status_wp: 'pending' })).toBe(false);
    expect(estaNoAr(null)).toBe(false);
  });
});
