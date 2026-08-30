// @vitest-environment jsdom
/**
 * A mesa das palavras — o que ela deixa o operador fazer, e o que ela recusa.
 *
 * **Nada aqui fala com o Google.** A mesa é pura: ela recebe o que foi marcado,
 * devolve o que o operador escreveu, e não faz uma requisição. Se um dia ela
 * fizer, este arquivo quebra — é de propósito, porque uma tela de revisão que
 * consulta a conta transforma revisar em gastar quota.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';

import { MesaDeCriterios } from '../MesaDeCriterios';
import type { CriterioDeKeyword, MatchType } from '@/types/trafego';

afterEach(cleanup);

const GRUPOS = [
  { tipo: 'ACESSO', keywords: ['saque anual fgts'] },
  { tipo: 'VALOR', keywords: ['valor do saque anual'] },
];

function montar(over: Partial<React.ComponentProps<typeof MesaDeCriterios>> = {}) {
  const onNegativas = vi.fn();
  const onMatchPorKeyword = vi.fn();
  const props = {
    grupos: GRUPOS,
    volumePorKeyword: { 'saque anual fgts': 27100 },
    matchPadrao: 'PHRASE' as MatchType,
    permitirBroadPositivo: false,
    matchPorKeyword: {},
    onMatchPorKeyword,
    negativas: [] as CriterioDeKeyword[],
    onNegativas,
    ...over,
  };
  render(<MesaDeCriterios {...props} />);
  return { onNegativas, onMatchPorKeyword };
}

// ── as que ativam ───────────────────────────────────────────────────────────

describe('palavras que ativam', () => {
  it('lista cada keyword marcada com o grupo dela', () => {
    montar();
    const bloco = screen.getByLabelText('Palavras que ativam');
    expect(within(bloco).getByText('saque anual fgts')).toBeTruthy();
    expect(within(bloco).getByText('valor do saque anual')).toBeTruthy();
    expect(within(bloco).getByText('ACESSO')).toBeTruthy();
  });

  it('cada keyword tem seu PRÓPRIO seletor de correspondência', () => {
    montar();
    expect(screen.getByLabelText('Correspondência de saque anual fgts')).toBeTruthy();
    expect(screen.getByLabelText('Correspondência de valor do saque anual')).toBeTruthy();
  });

  it('trocar a correspondência de uma NÃO troca a da outra', () => {
    const { onMatchPorKeyword } = montar();
    fireEvent.change(screen.getByLabelText('Correspondência de saque anual fgts'),
                     { target: { value: 'EXACT' } });
    expect(onMatchPorKeyword).toHaveBeenCalledWith({ 'saque anual fgts': 'EXACT' });
  });

  it('ausência de volume fica AUSENTE — zero é uma medição', () => {
    montar();
    // a segunda keyword não tem volume no mapa
    expect(screen.getByText(/volume não medido/)).toBeTruthy();
    expect(screen.getByText(/27\.100 buscas\/mês/)).toBeTruthy();
  });

  it('sob CPC manual, Ampla não é oferecida nas positivas', () => {
    montar({ permitirBroadPositivo: false });
    const sel = screen.getByLabelText('Correspondência de saque anual fgts');
    const valores = Array.from(sel.querySelectorAll('option')).map((o) => o.textContent);
    expect(valores).toEqual(['Exata', 'Frase']);
    expect(screen.getByText(/Ampla não está disponível/)).toBeTruthy();
  });

  it('sob lance automático, Ampla aparece', () => {
    montar({ permitirBroadPositivo: true });
    const sel = screen.getByLabelText('Correspondência de saque anual fgts');
    const valores = Array.from(sel.querySelectorAll('option')).map((o) => o.textContent);
    expect(valores).toEqual(['Exata', 'Frase', 'Ampla']);
  });
});

// ── as que excluem ──────────────────────────────────────────────────────────

describe('palavras a excluir', () => {
  it('não sugere nenhuma exclusão por conta própria', () => {
    montar();
    expect(screen.getByText(/não sugere nenhuma por conta própria/)).toBeTruthy();
    // as listas "universais" que as ferramentas aplicam por bom senso
    expect(screen.queryByText('gratis')).toBeNull();
    expect(screen.queryByText('emprego')).toBeNull();
  });

  it('adiciona uma exclusão de campanha com o match type escolhido', () => {
    const { onNegativas } = montar();
    fireEvent.change(screen.getByLabelText('Termo a excluir'), {
      target: { value: 'simulador' },
    });
    fireEvent.change(screen.getByLabelText('Correspondência da exclusão'), {
      target: { value: 'EXACT' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Adicionar exclusão/ }));

    expect(onNegativas).toHaveBeenCalledTimes(1);
    const [lista] = onNegativas.mock.calls[0];
    expect(lista).toHaveLength(1);
    expect(lista[0]).toMatchObject({
      texto: 'simulador', match_type: 'EXACT', negativa: true,
      nivel: 'CAMPAIGN', grupo: null, origem: 'MANUAL',
    });
    // ausência continua ausência
    expect(lista[0].motivo).toBeNull();
    expect(lista[0].evidencia).toBeNull();
  });

  it('a exclusão de grupo preserva o NÍVEL e não vira de campanha', () => {
    const { onNegativas } = montar();
    fireEvent.change(screen.getByLabelText('Termo a excluir'), {
      target: { value: 'simulador' },
    });
    fireEvent.change(screen.getByLabelText('Onde vale'), {
      target: { value: 'AD_GROUP' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Adicionar exclusão/ }));

    const [lista] = onNegativas.mock.calls[0];
    expect(lista[0].nivel).toBe('AD_GROUP');
    // `grupo: null` porque a campanha nasce com UM conjunto (P7). O nível
    // continua sendo o que separa `AdGroupCriterion` de `CampaignCriterion`.
    expect(lista[0].grupo).toBeNull();
  });

  it('não oferece escolher o grupo enquanto a campanha nasce com um só', () => {
    // Oferecer "em qual grupo" com um ad group só seria uma distinção sem
    // diferença: as duas respostas produziriam o mesmo payload.
    montar();
    fireEvent.change(screen.getByLabelText('Onde vale'), {
      target: { value: 'AD_GROUP' },
    });
    expect(screen.queryByLabelText('Grupo')).toBeNull();
  });

  it('o motivo em branco fica null, não string vazia', () => {
    const { onNegativas } = montar();
    fireEvent.change(screen.getByLabelText('Termo a excluir'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: /Adicionar exclusão/ }));
    expect(onNegativas.mock.calls[0][0][0].motivo).toBeNull();
  });

  it('recusa a duplicata exata em vez de mandar duas operações', () => {
    montar({
      negativas: [{
        texto: 'simulador', match_type: 'PHRASE', negativa: true,
        nivel: 'CAMPAIGN', grupo: null, origem: 'MANUAL',
        motivo: null, evidencia: null, observado_em: null, aprovado_por: null,
      }],
    });
    fireEvent.change(screen.getByLabelText('Termo a excluir'), {
      target: { value: 'simulador' },
    });
    const botao = screen.getByRole('button', { name: /Adicionar exclusão/ });
    expect((botao as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/já está na lista/)).toBeTruthy();
  });

  it('separa o medido da hipótese, e mostra a janela do medido', () => {
    montar({
      negativas: [{
        texto: 'simulador', match_type: 'PHRASE', negativa: true,
        nivel: 'CAMPAIGN', grupo: null, origem: 'SEARCH_TERM',
        motivo: '312 impressões, 0 clique',
        evidencia: {
          tipo: 'MEDIDO', fonte: 'search_term_view',
          janela_inicio: '2026-08-01', janela_fim: '2026-08-27',
          metricas: { impressoes: 312 },
        },
        observado_em: null, aprovado_por: null,
      }],
    });
    expect(screen.getByText('medida na conta')).toBeTruthy();
    expect(screen.getByText(/2026-08-01 a 2026-08-27/)).toBeTruthy();
    expect(screen.getByText(/observada na conta/)).toBeTruthy();
  });

  it('marca como hipótese o que ninguém mediu', () => {
    montar({
      negativas: [{
        texto: 'simulador', match_type: 'PHRASE', negativa: true,
        nivel: 'CAMPAIGN', grupo: null, origem: 'MANUAL',
        motivo: null, evidencia: null, observado_em: null, aprovado_por: null,
      }],
    });
    expect(screen.getByText('hipótese')).toBeTruthy();
    expect(screen.queryByText('medida na conta')).toBeNull();
  });

  it('remove uma exclusão pelo nome acessível', () => {
    const { onNegativas } = montar({
      negativas: [{
        texto: 'simulador', match_type: 'PHRASE', negativa: true,
        nivel: 'CAMPAIGN', grupo: null, origem: 'MANUAL',
        motivo: null, evidencia: null, observado_em: null, aprovado_por: null,
      }],
    });
    fireEvent.click(screen.getByRole('button', { name: 'Remover a exclusão simulador' }));
    expect(onNegativas).toHaveBeenCalledWith([]);
  });
});

// ── a revisão ───────────────────────────────────────────────────────────────

describe('revisão', () => {
  it('conta cada nível separadamente', () => {
    montar({
      negativas: [
        { texto: 'a', match_type: 'PHRASE', negativa: true, nivel: 'CAMPAIGN',
          grupo: null, origem: 'MANUAL', motivo: null, evidencia: null,
          observado_em: null, aprovado_por: null },
        { texto: 'b', match_type: 'PHRASE', negativa: true, nivel: 'AD_GROUP',
          grupo: 'ACESSO', origem: 'MANUAL', motivo: null, evidencia: null,
          observado_em: null, aprovado_por: null },
      ],
    });
    const revisao = screen.getByLabelText('Revisão');
    expect(within(revisao).getByText('palavras ativam').nextSibling?.textContent).toBe('2');
    expect(within(revisao).getByText('excluídas na campanha').nextSibling?.textContent).toBe('1');
    expect(within(revisao).getByText('excluídas em grupo').nextSibling?.textContent).toBe('1');
  });

  it('denuncia a keyword que a exclusão ANULA', () => {
    montar({
      negativas: [{
        texto: 'saque', match_type: 'PHRASE', negativa: true, nivel: 'CAMPAIGN',
        grupo: null, origem: 'MANUAL', motivo: null, evidencia: null,
        observado_em: null, aprovado_por: null,
      }],
    });
    expect(screen.getByText(/2 keywords anuladas/)).toBeTruthy();
    // e a linha da keyword também é marcada, não só o resumo
    const ativam = screen.getByLabelText('Palavras que ativam');
    expect(within(ativam).getAllByText(/anulada por uma exclusão/).length).toBe(2);
  });

  it('a exclusão de um grupo não anula a keyword do outro', () => {
    montar({
      negativas: [{
        texto: 'saque', match_type: 'PHRASE', negativa: true, nivel: 'AD_GROUP',
        grupo: 'ACESSO', origem: 'MANUAL', motivo: null, evidencia: null,
        observado_em: null, aprovado_por: null,
      }],
    });
    expect(screen.getByText(/1 keyword anulada/)).toBeTruthy();
  });

  it('diz que a prova não cria nada', () => {
    montar();
    expect(screen.getByText(/valida o envio sem criar nada/)).toBeTruthy();
  });
});

// ── a promessa de não falar com o Google ────────────────────────────────────

describe('a mesa é pura', () => {
  it('renderizar não dispara nenhuma requisição', () => {
    // Troca direta em vez de `vi.spyOn(globalThis, 'fetch' as never)`: aquele
    // cast fazia o spy ser inferido como `never`, e `mockRestore` não existe em
    // `never` — erro de tipo num arquivo de teste é erro igual.
    const original = globalThis.fetch;
    const espiao = vi.fn();
    globalThis.fetch = espiao as unknown as typeof fetch;
    try {
      montar({
        negativas: [{
          texto: 'simulador', match_type: 'BROAD', negativa: true, nivel: 'CAMPAIGN',
          grupo: null, origem: 'MANUAL', motivo: null, evidencia: null,
          observado_em: null, aprovado_por: null,
        }],
      });
      expect(espiao).not.toHaveBeenCalled();
    } finally {
      globalThis.fetch = original;
    }
  });

  it('não expõe GAQL, nome de recurso da API nem enum cru', () => {
    montar({
      negativas: [{
        texto: 'simulador', match_type: 'BROAD', negativa: true, nivel: 'AD_GROUP',
        grupo: 'ACESSO', origem: 'MANUAL', motivo: null, evidencia: null,
        observado_em: null, aprovado_por: null,
      }],
    });
    const texto = document.body.textContent ?? '';
    for (const proibido of ['SELECT', 'AdGroupCriterion', 'CampaignCriterion',
                            'KeywordMatchTypeEnum', 'customers/', 'BROAD',
                            'PHRASE', 'EXACT', 'AD_GROUP', 'CAMPAIGN']) {
      expect(texto).not.toContain(proibido);
    }
  });
});

// ── teclado e nomes acessíveis ──────────────────────────────────────────────

describe('acessibilidade', () => {
  it('todo controle tem nome acessível — nenhum campo anônimo', () => {
    montar();
    const controles = Array.from(
      document.querySelectorAll('input, select, button'),
    ) as HTMLElement[];
    expect(controles.length).toBeGreaterThan(0);
    const anonimos = controles.filter((el) => {
      const porAria = el.getAttribute('aria-label');
      const id = el.getAttribute('id');
      const porLabel = id ? document.querySelector(`label[for="${id}"]`) : null;
      const porTexto = el.textContent?.trim();
      return !porAria && !porLabel && !porTexto;
    });
    expect(anonimos.map((el) => el.outerHTML.slice(0, 80))).toEqual([]);
  });

  it('a exclusão entra pelo teclado, sem passar pelo mouse', () => {
    // O formulário é um `<form>` de verdade: Enter num campo submete. Um `div`
    // com onClick só no botão obrigaria o mouse.
    const { onNegativas } = montar();
    const campo = screen.getByLabelText('Termo a excluir');
    fireEvent.change(campo, { target: { value: 'simulador' } });
    fireEvent.submit(campo.closest('form')!);
    expect(onNegativas).toHaveBeenCalledTimes(1);
    expect(onNegativas.mock.calls[0][0][0].texto).toBe('simulador');
  });

  it('cada bloco é uma região com nome — dá para navegar por landmarks', () => {
    montar();
    for (const nome of ['Palavras que ativam', 'Palavras a excluir', 'Revisão']) {
      const bloco = screen.getByLabelText(nome);
      expect(bloco.tagName).toBe('SECTION');
    }
  });

  it('empilha no mobile e alinha no desktop — mobile-first, sem largura fixa', () => {
    montar();
    const linha = screen.getByText('saque anual fgts').closest('li')!;
    // `flex-col` é o estado base (mobile); `md:flex-row` só a partir do breakpoint
    expect(linha.className).toContain('flex-col');
    expect(linha.className).toContain('md:flex-row');
    // nada de largura em pixel cravada dentro da mesa
    const comLarguraFixa = Array.from(
      document.querySelectorAll('[style*="width"]'),
    ).filter((el) => /width:\s*\d+px/.test(el.getAttribute('style') ?? ''));
    expect(comLarguraFixa).toEqual([]);
  });
});
