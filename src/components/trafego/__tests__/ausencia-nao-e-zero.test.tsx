// @vitest-environment jsdom
/**
 * A contraprova de que ausência NÃO vira zero na mesa de termos.
 *
 * ## Por que este arquivo precisa existir
 *
 * Em 03/09/2026 `Cpc.valor` e `volume` passaram a ser `number | null`: a
 * projeção do servidor parou de coagir ausência para `0`
 * (`backend/app/trafego/projecao.py:45` fazia `float(getattr(c,"valor",0) or 0)`,
 * e `volc_ads/pautador_ponte.py:451` fazia `round(float(valor or 0.0), 4)`).
 *
 * ⚠️ E O COMPILADOR NÃO PROTEGE ESSA MUDANÇA. `tsconfig.app.json` declara
 * `"strict": false` e o `tsconfig.json` da raiz declara
 * `"strictNullChecks": false` — para o `tsc` deste projeto, `number | null` é
 * indistinguível de `number`. `k.volume.toLocaleString()` sobre `null` compila
 * limpo e explode em runtime; `a + k.cpc.valor` sobre `null` compila limpo e
 * devolve `NaN`, que é pior, porque não explode: desenha.
 *
 * Logo o único gate possível é este. Se alguém reintroduzir `|| 0` ou
 * `?? 0` nestes caminhos, é aqui que aparece.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { ListaDeKeywords } from '../ListaDeKeywords';
import { medir } from '../ReguaDeLeilao';
import type { GrupoCandidato, KeywordCandidata } from '@/types/trafego';

const kw = (over: Partial<KeywordCandidata>): KeywordCandidata => ({
  texto: 'termo', volume: 100, cpc: null, competicao: 'MEDIUM', tendencia: null,
  tags: [], motivo: '', tambem_em_conteudo: false, ...over,
});

afterEach(() => cleanup());

const cpc = (valor: number | null) =>
  ({ valor, procedencia: 'n8n:dataforseo', moeda: 'BRL', medido_na_conta: false });

describe('a mesa de termos não transforma ausência em zero', () => {
  it('volume ausente é escrito como "não medido", e nunca como 0', () => {
    const grupo: GrupoCandidato = {
      tipo: 'ACESSO', descricao: '', volume: null,
      cpc_simples: null, cpc_ponderado: null,
      volume_declarado: null, keywords_declaradas: null, fora_da_fila: [],
      keywords: [
        kw({ texto: 'saque aniversario fgts', volume: 31_030, cpc: cpc(0.74) }),
        kw({ texto: 'termo sem medicao', volume: null, cpc: null }),
      ],
    };
    render(<ListaDeKeywords grupo={grupo} marcadas={new Set()} onAlternar={() => {}} />);

    expect(screen.getByText('31.030')).toBeTruthy();
    // O ramo de ausência existia no componente e era código morto, porque o
    // servidor nunca mandava null. Agora ele é o caminho real.
    expect(screen.getByText('não medido')).toBeTruthy();
    expect(screen.getByText('CPC não medido')).toBeTruthy();
    // E o zero NÃO pode aparecer em lugar nenhum da linha sem medição.
    expect(screen.queryByText('0')).toBeNull();
    expect(screen.queryByText('0,00')).toBeNull();
  });

  it('a linha sem volume não vira barra de largura zero — ela fica sem barra', () => {
    const grupo: GrupoCandidato = {
      tipo: 'ACESSO', descricao: '', volume: null,
      cpc_simples: null, cpc_ponderado: null,
      volume_declarado: null, keywords_declaradas: null, fora_da_fila: [],
      keywords: [kw({ texto: 'sem medicao', volume: null })],
    };
    const { container } = render(
      <ListaDeKeywords grupo={grupo} marcadas={new Set()} onAlternar={() => {}} />);
    // Desenhar 0,5% para quem não foi medido daria a mesma forma de quem foi
    // medido perto de zero — que é a confusão exata que a mudança fecha.
    expect(container.querySelectorAll('[aria-hidden][style*="width"]').length).toBe(0);
  });

  it('o leitor de tela ouve "não medido", não o literal null', () => {
    const grupo: GrupoCandidato = {
      tipo: 'ACESSO', descricao: '', volume: null,
      cpc_simples: null, cpc_ponderado: null,
      volume_declarado: null, keywords_declaradas: null, fora_da_fila: [],
      keywords: [kw({ texto: 'sem medicao', volume: null, cpc: cpc(null) })],
    };
    render(<ListaDeKeywords grupo={grupo} marcadas={new Set()} onAlternar={() => {}} />);
    const rotulo = screen.getByRole('button').getAttribute('aria-label') ?? '';
    expect(rotulo).toContain('volume não medido');
    expect(rotulo).toContain('CPC não medido');
    expect(rotulo).not.toContain('null');
    expect(rotulo).not.toContain('NaN');
  });
});

describe('a régua do leilão exclui a ausência do denominador', () => {
  it('CPC ausente NÃO puxa a média para baixo — ele fica de fora e é contado', () => {
    // ⚠️ O DEFEITO QUE ISTO IMPEDE: com `k.cpc!.valor` somando `null` como 0, a
    // média de duas keywords a R$ 1,00 mais uma sem medição daria R$ 0,67 — um
    // lance 33% mais barato do que a medição sustenta, sem nenhum aviso.
    const m = medir([
      { texto: 'a', volume: 100, cpc: cpc(1.0) },
      { texto: 'b', volume: 100, cpc: cpc(1.0) },
      { texto: 'c', volume: 100, cpc: cpc(null) },
    ] as never);
    expect(m.simples).toBe(1.0);
    expect(m.ponderado).toBe(1.0);
    expect(m.semCpc).toBe(1);
    expect(Number.isNaN(m.simples)).toBe(false);
  });

  it('volume ausente não entra na soma nem no peso, e é contado à parte', () => {
    const m = medir([
      { texto: 'a', volume: 1_000, cpc: cpc(2.0) },
      { texto: 'b', volume: null, cpc: cpc(10.0) },
    ] as never);
    // A soma é dos presentes. `1000 + null` seria NaN; `1000 + 0` afirmaria que
    // 'b' não tem busca nenhuma.
    expect(m.volume).toBe(1_000);
    expect(m.semVolume).toBe(1);
    // 'b' tem CPC medido, então entra na média SIMPLES...
    expect(m.simples).toBe(6.0);
    // ...e não entra na PONDERADA, porque não tem peso conhecido. Um CPC de
    // R$ 10,00 com peso inventado distorceria o número que dimensiona a aposta.
    expect(m.ponderado).toBe(2.0);
  });

  it('nenhuma medição presente devolve zeros de estrutura, não NaN', () => {
    const m = medir([{ texto: 'a', volume: null, cpc: null }] as never);
    expect(Number.isNaN(m.volume)).toBe(false);
    expect(Number.isNaN(m.ponderado)).toBe(false);
    expect(Number.isNaN(m.simples)).toBe(false);
    expect(m.semCpc).toBe(1);
    expect(m.semVolume).toBe(1);
  });
});
