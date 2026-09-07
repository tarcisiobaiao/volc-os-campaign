// @vitest-environment jsdom
/**
 * A porta de entrada no Hub e as garantias do painel de estratégia.
 */
import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PainelDeEstrategia } from '@/features/creative-studio/componentes/PainelDeEstrategia';
import { caminhoDe } from '@/features/creative-studio/api';
import type { PedidoDeDecisao, SaidaDoAgente } from '@/features/creative-studio/tipos';

afterEach(cleanup);

const RUN_REF = `crrun_${'b'.repeat(24)}`;

function saida(): SaidaDoAgente {
  return {
    schema_version: '1.0',
    project_ref: `crproj_${'a'.repeat(24)}`,
    fase_concluida: 'MATRIZ',
    diagnostico: {
      oferta_real: 'Curso preparatório independente.',
      promessa_maxima: 'Entender o edital sem depender de intermediário.',
      tensao_central: 'Medo de estudar o conteúdo errado.',
      desconhecidos: ['Taxa de aprovação não medida'],
      fato_refs: ['fact_lp_offer'],
    },
    jornada: [
      {
        ref: 'state_frio',
        nome: 'Nunca ouviu falar',
        ja_sabe: 'Sabe que existe a prova.',
        duvida: 'Não sabe por onde começar.',
        tensao: 'Tempo curto.',
        proximo_movimento: 'Ler a explicação.',
      },
    ],
    grupos: [
      {
        ref: 'group_frio',
        nome: 'Território do desconhecido',
        estado_mental_refs: ['state_frio'],
        funcao: 'Apresentar a oferta.',
        territorio: 'Quem ainda não conhece o material.',
        diferenca_material: 'Fala de processo, não de preço.',
      },
    ],
    copies_compartilhadas: [
      {
        ref: 'copy_frio',
        group_ref: 'group_frio',
        texto_principal: 'O edital explicado sem juridiquês.',
        titulo: 'Entenda o edital',
        descricao: 'Material independente',
        cta_nativa: 'LEARN_MORE',
        fato_refs: ['fact_lp_offer'],
      },
    ],
    pecas: [
      {
        ref: 'creative_hook_frio',
        group_ref: 'group_frio',
        shared_copy_ref: 'copy_frio',
        estado_mental_ref: 'state_frio',
        angulo: 'Clareza',
        subangulo: 'Passo a passo',
        hipotese: 'Quem não começou trava na primeira página.',
        hook: 'Você não precisa ler o edital inteiro',
        mecanismo_de_interrupcao: 'Contraste com o senso comum',
        formato: '4x5',
        headline_interna: 'Comece pela página 12',
        complemento_interno: null,
        cta_visual: 'Ver como',
        direcao_visual: 'Documento com uma página marcada.',
        fato_refs: ['fact_lp_offer'],
        rule_refs: [],
      },
    ],
    recibo: {
      valido: true,
      codigos: ['META_CREATIVE_SCHEMA_VALID'],
      avisos: [],
      knowledge_base_version: 'copiloto-meta-ads-v2-derived@1.0',
    },
    proximo_ato: 'Revisar e aprovar.',
  };
}

describe('aprovar endereça por ref, nunca por posição', () => {
  it('o caminho da decisão usa o ref do elemento', () => {
    const decisoes: PedidoDeDecisao[] = [];
    render(
      <PainelDeEstrategia
        saida={saida()}
        runRef={RUN_REF}
        aprovados={new Set()}
        ocupado={false}
        onDecidir={(p) => decisoes.push(p)}
        onRefinar={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /aprovar peça/i }));

    expect(decisoes).toHaveLength(1);
    // ⚠️ `/pecas/0` congelaria "seja lá o que estiver na primeira posição", e a
    // posição muda a cada geração.
    expect(decisoes[0].caminho).toBe('/pecas/creative_hook_frio');
    expect(decisoes[0].caminho).not.toMatch(/\/-?\d+(\/|$)/);
    expect(decisoes[0].run_ref).toBe(RUN_REF);
  });

  it('caminhoDe não produz segmento numérico', () => {
    expect(caminhoDe('grupos', 'group_frio')).toBe('/grupos/group_frio');
    expect(caminhoDe('grupos', 'group_frio', 'nome')).toBe('/grupos/group_frio/nome');
  });

  it('o que já foi aprovado aparece congelado e sem botão de aprovar de novo', () => {
    render(
      <PainelDeEstrategia
        saida={saida()}
        runRef={RUN_REF}
        aprovados={new Set(['/pecas/creative_hook_frio'])}
        ocupado={false}
        onDecidir={() => {}}
        onRefinar={() => {}}
      />,
    );
    expect(screen.getByText('Congelada')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /aprovar peça/i })).toBeNull();
  });
});

describe('o recibo não é promovido a aprovação', () => {
  it('separa contrato, decisão humana e elegibilidade Meta em três frases', () => {
    render(
      <PainelDeEstrategia
        saida={saida()}
        runRef={RUN_REF}
        aprovados={new Set()}
        ocupado={false}
        onDecidir={() => {}}
        onRefinar={() => {}}
      />,
    );
    const secao = screen.getByText(/O que este recibo prova/i).closest('section');
    expect(secao?.textContent).toMatch(/contraprovas determinísticas de contrato/i);
    expect(secao?.textContent).toMatch(/não.{0,3} é aprovação humana/i);
    expect(secao?.textContent).toMatch(/elegibilidade de mídia\s+paga na Meta/i);
    expect(secao?.textContent).toMatch(/a imagem ainda\s+não existe/i);
  });

  it('o texto do modelo é rotulado como proposta', () => {
    render(
      <PainelDeEstrategia
        saida={saida()}
        runRef={RUN_REF}
        aprovados={new Set()}
        ocupado={false}
        onDecidir={() => {}}
        onRefinar={() => {}}
      />,
    );
    expect(screen.getByText('Proposta do Assistente')).toBeTruthy();
  });

  it('o que o Assistente declarou não saber aparece como ausência, não como zero', () => {
    render(
      <PainelDeEstrategia
        saida={saida()}
        runRef={RUN_REF}
        aprovados={new Set()}
        ocupado={false}
        onDecidir={() => {}}
        onRefinar={() => {}}
      />,
    );
    expect(screen.getByText(/declarou não saber/i)).toBeTruthy();
    expect(screen.getByText('Taxa de aprovação não medida')).toBeTruthy();
  });
});

describe('refinar exige comentário e explica o congelamento', () => {
  it('o botão fica travado sem texto e diz que aprovado não muda', () => {
    render(
      <PainelDeEstrategia
        saida={saida()}
        runRef={RUN_REF}
        aprovados={new Set()}
        ocupado={false}
        onDecidir={() => {}}
        onRefinar={() => {}}
      />,
    );
    const botao = screen.getByRole('button', { name: /refinar estratégia/i }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
    expect(screen.getByText(/refinar não desfaz aprovação/i)).toBeTruthy();

    fireEvent.change(screen.getByLabelText('O que mudar'), {
      target: { value: 'Troque o hook da peça do frio.' },
    });
    expect((screen.getByRole('button', { name: /refinar estratégia/i }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('a entrada do Hub', () => {
  it('o botão do Assistente existe, é secundário e NÃO herda modo=demo', async () => {
    const fonte = await import('node:fs').then((fs) =>
      fs.readFileSync('src/pages/trafego/HubDeTrafegoPage.tsx', 'utf8'),
    );

    const linha = fonte.match(
      /<Link to="\/trafego\/meta\/assistente-criativo[^"]*">Assistente Criativo<\/Link>/,
    );
    expect(linha).not.toBeNull();
    // ⚠️ `?modo=demo` pertence à criação de campanha. Herdá-lo faria uma sala
    // que fala com o modelo de verdade parecer — ou ser tratada como — demo.
    expect(linha?.[0]).not.toContain('modo=demo');

    // secundário: variant outline, contra a primária que é a Nova campanha Meta
    const bloco = fonte.slice(
      fonte.indexOf('Nova campanha Meta'),
      fonte.indexOf('Assistente Criativo') + 200,
    );
    expect(bloco).toContain('variant="outline"');
    // a configuração continua ao lado da primária
    expect(bloco).toContain('MetaConfiguracaoLocal');
  });

  it('as rotas estáticas são declaradas antes da dinâmica /trafego/meta/:tipo/:objetoId', async () => {
    const app = await import('node:fs').then((fs) =>
      fs.readFileSync('src/App.tsx', 'utf8'),
    );
    const estatica = app.indexOf('path="/trafego/meta/assistente-criativo"');
    const comParam = app.indexOf('path="/trafego/meta/assistente-criativo/:projectRef"');
    const dinamica = app.indexOf('path="/trafego/meta/:tipo/:objetoId"');
    expect(estatica).toBeGreaterThan(-1);
    expect(comParam).toBeGreaterThan(-1);
    expect(estatica).toBeLessThan(dinamica);
    expect(comParam).toBeLessThan(dinamica);
  });
});

describe('a produção mostra o preço antes do botão', () => {
  const PLANO_SEM_PRECO = {
    conceitos: 2,
    formatos: 3,
    total_de_renders: 6,
    teto: 45,
    custo_estimado_usd: null,
    custo_e_estimado: true,
    modelo_de_imagem: 'gemini:gemini-3.1-flash-image',
    motor_configurado: true,
    pode_executar: true,
    bloqueios: [],
    briefings: [],
  };

  async function montarProducao(plano: typeof PLANO_SEM_PRECO | null, aprovadas: string[]) {
    const { PainelDeProducao } = await import(
      '@/features/creative-studio/componentes/PainelDeProducao'
    );
    const view = render(
      <PainelDeProducao
        saida={saida()}
        aprovados={new Set(aprovadas)}
        plano={plano}
        planejando={false}
        gerando={false}
        onPlanejar={() => {}}
        onGerar={() => {}}
      />,
    );
    if (aprovadas.length) {
      fireEvent.click(screen.getAllByRole('checkbox')[0]);
      fireEvent.click(screen.getByRole('button', { name: 'Conferir antes de gerar' }));
    }
    return view;
  }

  it('custo desconhecido vira ausência declarada, nunca US$ 0,00', async () => {
    await montarProducao(PLANO_SEM_PRECO, ['/pecas/creative_hook_frio']);
    expect(screen.getByText(/não publicado pelo motor/i)).toBeTruthy();
    // ⚠️ Zero é um preço. "Não sei" não é.
    expect(screen.queryByText(/US\$\s*0[.,]00/)).toBeNull();
  });

  it('mostra N x M e o teto antes de existir o botão de gerar', async () => {
    await montarProducao(PLANO_SEM_PRECO, ['/pecas/creative_hook_frio']);
    expect(screen.getByText('Conceitos')).toBeTruthy();
    expect(screen.getByText('Imagens')).toBeTruthy();
    expect(screen.getByText(/de 45 no teto/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /gerar 6 imagem/i })).toBeTruthy();
  });

  it('um pedido bloqueado explica o motivo e desabilita a geração', async () => {
    await montarProducao(
      {
        ...PLANO_SEM_PRECO,
        pode_executar: false,
        bloqueios: [
          {
            codigo: 'CRIATIVO_STUDIO_TETO_DE_RENDERS',
            mensagem: '12 conceito(s) × 4 formato(s) dão 48 imagens, acima do teto de 45 por pedido.',
          },
        ],
      },
      ['/pecas/creative_hook_frio'],
    );
    expect(screen.getByText(/acima do teto de 45/i)).toBeTruthy();
    expect(screen.getByText(/Nada foi criado e nada foi cobrado/i)).toBeTruthy();
    // `/^gerar/` e não `/gerar/`: "Conferir antes de gerar" também casaria,
    // e o teste passaria olhando para o botão errado.
    const botao = screen.getByRole('button', { name: /^gerar/i }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
  });

  it('sem peça aprovada não há produção, e a tela diz por quê', async () => {
    await montarProducao(null, []);
    expect(screen.getByText(/Nenhuma peça foi aprovada ainda/i)).toBeTruthy();
    expect(screen.getByText(/recibo de contrato do Assistente não substitui/i)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^gerar/i })).toBeNull();
  });
  it('mudar a seleção invalida o plano e retira o botão de gerar', async () => {
    await montarProducao(PLANO_SEM_PRECO, ['/pecas/creative_hook_frio']);
    expect(screen.getByRole('button', { name: /^gerar 6/i })).toBeTruthy();
    fireEvent.click(screen.getAllByRole('checkbox')[1]);
    expect(screen.queryByRole('button', { name: /^gerar 6/i })).toBeNull();
  });
});
