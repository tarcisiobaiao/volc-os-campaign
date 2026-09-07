// @vitest-environment jsdom
/**
 * `A11` — os cinco estados de um catálogo não podem virar "nenhum resultado".
 *
 * O adaptador do backend é explícito sobre o que está em jogo: `[]` completo,
 * permissão negada, timeout e página truncada "NAO podem chegar iguais na UI",
 * porque as quatro pedem próximos passos diferentes. E existe um quinto estado
 * que não é nenhum dos quatro — NÃO TER LIDO — mais um eixo ORTOGONAL, o
 * frescor, que pode marcar uma lista cheia como vencida.
 *
 * Cada teste aqui fixa uma dessas distinções pela PALAVRA, não pela cor.
 */
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CatalogoDaConta } from '../CatalogoDaConta';
import type { EnvelopeDeCatalogoMeta } from '@/lib/pautadorApi';

afterEach(cleanup);

function envelope(
  troca: Partial<EnvelopeDeCatalogoMeta<{ nome: string }>> = {},
): EnvelopeDeCatalogoMeta<{ nome: string }> {
  return {
    ok: true,
    catalogo: 'custom_audiences',
    api_version: 'v26.0',
    referencia_opaca_da_conta: 'metaacct_conta',
    estado: 'COM_ITENS',
    motivo: null,
    retryable: false,
    items: [{ nome: 'Visitantes 30 dias' }],
    total: 1,
    invalidos: 0,
    desconhecidos: 0,
    completo: true,
    paginas_lidas: 1,
    observado_em: '2026-09-07T12:00:00+00:00',
    ttl_s: 300,
    expira_em: '2026-09-07T12:05:00+00:00',
    estado_do_catalogo: 'VIGENTE',
    ...troca,
  };
}

function desenhar(
  props: Partial<React.ComponentProps<typeof CatalogoDaConta<{ nome: string }>>> = {},
) {
  return render(
    <CatalogoDaConta<{ nome: string }>
      titulo="Públicos salvos desta conta"
      substantivo="públicos"
      envelope={null}
      carregando={false}
      erro={null}
      podeLer
      onLer={vi.fn()}
      {...props}
    />,
  );
}

describe('Os cinco estados de um catálogo', () => {
  it('NÃO LIDO não é vazio: a frase separa as duas coisas', () => {
    desenhar();
    expect(screen.getByText(/Ainda não lido\. Ausência de leitura não é ausência de públicos/i))
      .toBeTruthy();
    // E nenhuma das outras quatro frases aparece.
    expect(screen.queryByText(/A conta respondeu e não tem nenhum item/i)).toBeNull();
    expect(screen.queryByText(/Lista incompleta/i)).toBeNull();
  });

  it('VAZIO_COMPLETO diz que a resposta veio inteira e está vazia', () => {
    desenhar({ envelope: envelope({ estado: 'VAZIO_COMPLETO', items: [], total: 0 }) });
    expect(screen.getByText(/A conta respondeu e não tem nenhum item de públicos/i)).toBeTruthy();
    expect(screen.getByText(/diferente de não ter lido e diferente de a leitura ter falhado/i))
      .toBeTruthy();
    expect(screen.queryByText(/Ainda não lido/i)).toBeNull();
  });

  it('INDISPONIVEL carrega a causa e o próximo passo, sem virar "vazio"', () => {
    desenhar({
      envelope: envelope({
        ok: false, estado: 'INDISPONIVEL', items: [], total: 0,
        motivo: 'META_PERMISSION_DENIED', retryable: false, completo: false,
      }),
    });
    expect(screen.getByText(/A Meta não entregou públicos desta conta/i)).toBeTruthy();
    expect(screen.getAllByText(/META_PERMISSION_DENIED/).length).toBeGreaterThan(0);
    expect(screen.getByText(/alguém precisa liberar a permissão/i)).toBeTruthy();
    expect(screen.queryByText(/A conta respondeu e não tem nenhum item/i)).toBeNull();
  });

  it('INDISPONIVEL com retryable convida a tentar de novo, e não a pedir acesso', () => {
    desenhar({
      envelope: envelope({
        ok: false, estado: 'INDISPONIVEL', items: [], total: 0,
        motivo: 'META_TIMEOUT', retryable: true, completo: false,
      }),
    });
    expect(screen.getByText(/pode ser tentada de novo/i)).toBeTruthy();
    expect(screen.queryByText(/liberar a permissão/i)).toBeNull();
  });

  it('PARCIAL diz que existe mais do que você está vendo', () => {
    desenhar({
      envelope: envelope({
        estado: 'PARCIAL', completo: false, motivo: 'META_PAGINATION_LIMIT',
      }),
    });
    // O aviso longo e o selo do eixo de completude dizem a mesma coisa em dois
    // registros: um explica, o outro é varrível de olho.
    expect(screen.getAllByText(/Lista incompleta/i).length).toBeGreaterThan(1);
    expect(screen.getByText(/não pode ser concluído como inexistente/i)).toBeTruthy();
  });

  it('COM_ITENS conta o que veio, incluindo ilegíveis e sem estado', () => {
    desenhar({ envelope: envelope({ total: 7, invalidos: 2, desconhecidos: 1 }) });
    expect(screen.getByText('7 de públicos')).toBeTruthy();
    expect(screen.getByText('2 ilegível(is)')).toBeTruthy();
    expect(screen.getByText('1 sem estado')).toBeTruthy();
  });
});

describe('Frescor é um eixo ORTOGONAL', () => {
  it('uma lista COM ITENS pode estar vencida, e a tela diz as duas coisas', () => {
    desenhar({ envelope: envelope({ estado_do_catalogo: 'OBSOLETO', total: 3 }) });
    expect(screen.getByText('3 de públicos')).toBeTruthy();
    expect(screen.getByText('leitura vencida')).toBeTruthy();
    // ⚠️ E os itens continuam à vista: uma re-busca silenciosa trocaria a lista
    // debaixo de uma seleção já feita.
    expect(screen.queryByText(/A conta respondeu e não tem nenhum item/i)).toBeNull();
  });

  it('a leitura dentro do prazo é dita com todas as letras', () => {
    desenhar({ envelope: envelope() });
    expect(screen.getByText('leitura vigente')).toBeTruthy();
    expect(screen.getByText(/observada em 2026-09-07T12:00:00\+00:00/)).toBeTruthy();
  });
});

describe('A leitura é um ato', () => {
  it('não busca nada sozinha: o botão é o único caminho', () => {
    const onLer = vi.fn();
    desenhar({ onLer });
    expect(onLer).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /ler públicos desta conta/i })).toBeTruthy();
  });

  it('sem conta escolhida o botão fecha', () => {
    desenhar({ podeLer: false });
    expect(screen.getByRole('button', { name: /ler públicos desta conta/i }))
      .toHaveProperty('disabled', true);
  });

  it('uma falha de requisição não vira "nenhum item"', () => {
    desenhar({ erro: 'Sessão expirada. Faça login novamente.' });
    expect(screen.getByText(/Sessão expirada/i)).toBeTruthy();
    expect(screen.getByText(/falha de LEITURA, não a ausência de itens/i)).toBeTruthy();
    expect(screen.queryByText(/A conta respondeu e não tem nenhum item/i)).toBeNull();
  });
});
