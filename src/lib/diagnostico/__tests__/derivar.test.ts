/**
 * A DERIVAÇÃO: da evidência crua ao diagnóstico, sem inventar nada.
 *
 * As três provas que importam aqui:
 *
 *  1. consulta que FALHOU vira `nao_apurado` — nunca `ok`;
 *  2. linha que VEIO com métrica omitida é ZERO MEDIDO — que é fato, não
 *     ausência (é a única exceção do repositório, e ela é local ao formato do
 *     serializador proto);
 *  3. a escada sai completa: nenhum eixo some por falta de dado, porque eixo
 *     que some da tela lê-se como eixo que está bem.
 */
import { describe, expect, it } from 'vitest';

import { EIXOS_DE_ENTREGA } from '@/types/diagnostico';
import { derivarDiagnostico, janelaLegivel, percentual, campanhasNaEvidencia } from '../derivar';
import { evidenciaDeProva, ID_FGTS, ID_MAQUININHA } from '../fixtureDeEvidencia';
import { vereditoDaEscada } from '../escada';

const AGORA = new Date('2026-08-26T18:10:11.000Z');

describe('a escada sai completa', () => {
  it('tem exatamente os nove eixos, na ordem causal, mesmo com consultas caídas', () => {
    const d = derivarDiagnostico(
      evidenciaDeProva({ derrubar: ['grupos', 'anuncios', 'keywords'] }),
      ID_FGTS,
      { agora: AGORA },
    );
    expect(d.degraus.map((x) => x.eixo)).toEqual([...EIXOS_DE_ENTREGA]);
  });

  it('carrega a moeda da conta e a janela em português', () => {
    const d = derivarDiagnostico(evidenciaDeProva(), ID_FGTS, { agora: AGORA });
    expect(d.moeda).toBe('BRL');
    expect(d.janela).toBe('últimos 30 dias');
  });
});

describe('consulta que falhou nunca vira "ok"', () => {
  it('a cobrança não lida deixa o degrau da conta em `nao_apurado`, com o motivo literal', () => {
    const d = derivarDiagnostico(evidenciaDeProva({ derrubar: ['faturamento'] }), ID_FGTS, {
      agora: AGORA,
    });
    const conta = d.degraus.find((x) => x.eixo === 'conta')!;
    expect(conta.estado).toBe('nao_apurado');
    expect(conta.impedimento).toContain('PERMISSION_DENIED');
    expect(d.parcial).toBe(true);
  });

  it('⚠️ conta ativa com cobrança não lida NÃO é "conta ativa"', () => {
    // O caminho fácil seria: status ENABLED, logo `ok`. Isso afirmaria sobre a
    // cobrança, que é justamente o que não foi lido — e conta sem cobrança não
    // veicula nem com tudo ligado.
    const d = derivarDiagnostico(evidenciaDeProva({ derrubar: ['faturamento'] }), ID_FGTS, {
      agora: AGORA,
    });
    expect(vereditoDaEscada(d.degraus)).toEqual({ tipo: 'nao_apurado', eixo: 'conta' });
  });

  it('métricas caídas deixam orçamento e leilão sem afirmação', () => {
    const d = derivarDiagnostico(evidenciaDeProva({ derrubar: ['metricas_campanha'] }), ID_FGTS, {
      agora: AGORA,
    });
    expect(d.degraus.find((x) => x.eixo === 'orcamento')!.estado).toBe('nao_apurado');
    expect(d.degraus.find((x) => x.eixo === 'leilao')!.estado).toBe('nao_apurado');
  });
});

describe('zero medido é fato, e não ausência', () => {
  it('a Maquininha pausada tem linha de métrica sem campos — e isso é zero, não "não sei"', () => {
    const d = derivarDiagnostico(evidenciaDeProva(), ID_MAQUININHA, { agora: AGORA });
    const leilao = d.degraus.find((x) => x.eixo === 'leilao')!;
    expect(leilao.estado).toBe('bloqueia');
    expect(leilao.palavra).toBe('não houve leilão');
    expect(leilao.frase).toContain('a conta respondeu e o número é zero');
    expect(leilao.evidencias.find((e) => e.campo === 'metrics.impressions')?.valor).toBe('0');
  });
});

describe('o caso real da Maquininha', () => {
  it('pausada bloqueia na campanha, e a escada para ali', () => {
    const d = derivarDiagnostico(evidenciaDeProva(), ID_MAQUININHA, { agora: AGORA });
    expect(vereditoDaEscada(d.degraus)).toEqual({ tipo: 'bloqueada', eixo: 'campanha' });
    const campanha = d.degraus.find((x) => x.eixo === 'campanha')!;
    expect(campanha.palavra).toBe('pausada');
    expect(campanha.motivo_da_conta).toContain('campaign paused');
  });

  it('ligada e sem impedimento, o veredito muda sozinho', () => {
    const d = derivarDiagnostico(
      evidenciaDeProva({ estadoDaMaquininha: 'ENABLED' }),
      ID_MAQUININHA,
      { agora: AGORA },
    );
    // Ligada, mas sem impressão medida: o leilão bloqueia, e é honesto.
    expect(vereditoDaEscada(d.degraus)).toEqual({ tipo: 'bloqueada', eixo: 'leilao' });
  });
});

describe('o caso real da FGTS', () => {
  it('entrega e é limitada pela verba', () => {
    const d = derivarDiagnostico(evidenciaDeProva(), ID_FGTS, { agora: AGORA });
    expect(vereditoDaEscada(d.degraus)).toEqual({ tipo: 'limitada', eixo: 'orcamento' });
    const orcamento = d.degraus.find((x) => x.eixo === 'orcamento')!;
    expect(orcamento.frase).toContain('38%');
    expect(
      orcamento.evidencias.find((e) => e.campo === 'campaign_budget.amount_micros')?.valor,
    ).toContain('20,00');
  });

  it('perda pequena por verba não vira alarme', () => {
    const d = derivarDiagnostico(evidenciaDeProva({ perdaPorVerba: 0.02 }), ID_FGTS, {
      agora: AGORA,
    });
    expect(d.degraus.find((x) => x.eixo === 'orcamento')!.estado).toBe('ok');
  });
});

describe('a campanha que a conta não tem', () => {
  it('é fato observado, e não falha de leitura', () => {
    const d = derivarDiagnostico(evidenciaDeProva(), 'id-que-nao-existe', { agora: AGORA });
    const campanha = d.degraus.find((x) => x.eixo === 'campanha')!;
    expect(campanha.estado).toBe('bloqueia');
    expect(campanha.frase).toContain('a conta foi lida e não a tem');
  });
});

describe('formatação', () => {
  it('janela vira português e valor desconhecido é dito, não escondido', () => {
    expect(janelaLegivel('LAST_30_DAYS')).toBe('últimos 30 dias');
    expect(janelaLegivel(undefined)).toBe('janela não declarada');
  });

  it('percentual de `null` continua `null` — não vira "0%"', () => {
    expect(percentual(null)).toBeNull();
    expect(percentual(0)).toBe('0%');
    expect(percentual(0.38)).toBe('38%');
  });

  it('lista as campanhas da evidência para a tela escolher', () => {
    expect(campanhasNaEvidencia(evidenciaDeProva()).map((c) => c.id)).toEqual([
      ID_MAQUININHA,
      ID_FGTS,
    ]);
  });
});
