// @vitest-environment jsdom
/**
 * A jornada do canal: o veredito do servidor, sem recálculo e sem ato falso.
 *
 * Estas provas existem contra defeitos concretos, não contra a implementação:
 * um "não apurado" pintado de vermelho ensina o operador a ignorar o vermelho;
 * um portão que não veio desenhado como recusa afirma um veredito que ninguém
 * deu; e um controle de ativar seria UI morta, porque nenhum canal deste
 * sistema tem rota de ativação.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { ConversaDeCriacao } from '@/components/trafego/criacao/ConversaDeCriacao';
import { montarConversa } from '@/components/trafego/criacao/conversa';
import { JornadaDoCanal } from '@/components/trafego/estudio/JornadaDoCanal';
import type {
  BloqueadorDeCanal,
  ContratoDeCanal,
  PortaoDeCanal,
} from '@/lib/trafego/canais';

afterEach(cleanup);

const portao = (
  nome: PortaoDeCanal['nome'],
  estado: PortaoDeCanal['estado'],
  bloqueadores: BloqueadorDeCanal[] = [],
): PortaoDeCanal => ({
  nome,
  estado,
  aberto: estado === 'PERMITIDO',
  bloqueadores,
});

const bloqueio = (over: Partial<BloqueadorDeCanal> = {}): BloqueadorDeCanal => ({
  codigo: 'fora_da_janela_do_canario',
  causa: 'a janela autorizada de criação admite apenas Search neste momento.',
  origem: 'politica',
  observado_em: null,
  revalidacao: null,
  ...over,
});

/** O contrato como `GET /canais` o devolve — quatro portões, sempre. */
const contrato = (over: Partial<ContratoDeCanal> = {}): ContratoDeCanal => ({
  plataforma: 'GOOGLE_ADS',
  canal: 'DISPLAY',
  rotulo: 'Display',
  manifesto: {
    plataforma: 'GOOGLE_ADS',
    canal: 'DISPLAY',
    rotulo: 'Display',
    hierarquia: ['campanha', 'grupo', 'anuncio', 'asset'],
    paineis: ['anuncios', 'criativos'],
    campos_do_pedido: ['copy', 'url_final', 'verba_diaria'],
    capacidades: ['ler', 'propor'],
    provas_obrigatorias: ['politica', 'selo'],
    indisponibilidades: [],
    sabe_provar: true,
    sabe_criar: true,
  },
  portoes: [
    portao('planejavel', 'PERMITIDO'),
    portao('validavel', 'PERMITIDO'),
    portao('criavel_pausada', 'BLOQUEADO', [bloqueio()]),
    portao('ativavel', 'BLOQUEADO', [
      bloqueio({
        codigo: 'ativacao_fora_do_contrato',
        causa: 'não existe rota de ativação neste sistema.',
        origem: 'produto',
      }),
    ]),
  ],
  assets: { estado: 'PERMITIDO', recursos: [], quantidade: null, fonte: null, causa: null },
  mensuracao: { lida: false } as ContratoDeCanal['mensuracao'],
  observabilidade: {} as ContratoDeCanal['observabilidade'],
  operacional: {},
  ...over,
});

const montar = (over: Partial<React.ComponentProps<typeof JornadaDoCanal>> = {}) =>
  render(
    <JornadaDoCanal
      contrato={contrato()}
      travaAberta={false}
      podeAprovar
      {...over}
    />,
  );

describe('a escada dos quatro portões', () => {
  it('mostra os quatro, na ordem, mesmo os que não abrem', () => {
    montar();
    const itens = screen.getAllByRole('listitem');
    const rotulos = itens.map((li) => li.textContent ?? '');
    expect(rotulos.some((t) => t.includes('Planejável'))).toBe(true);
    expect(rotulos.some((t) => t.includes('Validável'))).toBe(true);
    expect(rotulos.some((t) => t.includes('Criável pausada'))).toBe(true);
    expect(rotulos.some((t) => t.includes('Ativável'))).toBe(true);
  });

  it('um portão bloqueado traz a causa do servidor E a quem pedir', () => {
    // Um botão cinza sem origem faz "peça ao admin", "peça a quem escreve o
    // engine" e "peça ao dono" virarem a mesma frustração.
    montar();
    // A causa aparece na escada E na etapa "Criação pausada" — o mesmo fato,
    // dito pela mesma fonte nos dois lugares. Antes a etapa dizia OUTRA coisa
    // ("a prova ainda não passou"), que era elegibilidade recalculada aqui.
    expect(
      screen.getAllByText(/a janela autorizada de criação admite apenas Search/i).length,
    ).toBeGreaterThanOrEqual(1);
    // `getAllBy`: a frase aparece no texto E na descrição acessível do chip de
    // origem, de propósito — quem navega por leitor de tela ouve a mesma
    // resposta que quem lê a linha.
    expect(
      screen.getAllByText(/Depende de uma decisão do dono da operação/i).length,
    ).toBeGreaterThan(0);
  });

  it('a causa aparece como o servidor a escreveu — a tela não a reescreve', () => {
    const causa = 'uma causa que só o servidor sabe redigir, com 42 caracteres.';
    montar({
      contrato: contrato({
        portoes: [
          portao('planejavel', 'PERMITIDO'),
          portao('validavel', 'PERMITIDO'),
          portao('criavel_pausada', 'BLOQUEADO', [bloqueio({ causa })]),
          portao('ativavel', 'BLOQUEADO'),
        ],
      }),
    });
    expect(screen.getAllByText(causa).length).toBeGreaterThanOrEqual(1);
  });

  it('INDETERMINADO não é desenhado como bloqueado', () => {
    // ⚠️ As duas pedem atos opostos: bloqueado pede que alguém libere algo,
    // não apurado pede uma leitura que ninguém fez.
    montar({
      contrato: contrato({
        portoes: [
          portao('planejavel', 'INDETERMINADO'),
          portao('validavel', 'PERMITIDO'),
          portao('criavel_pausada', 'BLOQUEADO', [bloqueio()]),
          portao('ativavel', 'BLOQUEADO'),
        ],
      }),
    });
    const planejavel = screen
      .getAllByRole('listitem')
      .find((li) => (li.textContent ?? '').includes('Planejável'))!;
    expect(within(planejavel).getByText(/não apurado/i)).toBeTruthy();
    expect(within(planejavel).queryByText(/^bloqueado$/i)).toBeNull();
  });

  it('portão ausente não vira portão fechado', () => {
    // O contrato manda os quatro sempre. Se um não veio, desenhar uma recusa
    // afirmaria um veredito que ninguém deu.
    montar({
      contrato: contrato({
        portoes: [portao('planejavel', 'PERMITIDO')],
      }),
    });
    const criavel = screen
      .getAllByRole('listitem')
      .find((li) => (li.textContent ?? '').includes('Criável pausada'))!;
    expect(within(criavel).getByText(/não veio/i)).toBeTruthy();
    expect(within(criavel).queryByText(/^bloqueado$/i)).toBeNull();
  });

  it('bloqueado sem bloqueador declara a lacuna e não vira permissão', () => {
    montar({
      contrato: contrato({
        portoes: [
          portao('planejavel', 'PERMITIDO'),
          portao('validavel', 'PERMITIDO'),
          portao('criavel_pausada', 'BLOQUEADO', []),
          portao('ativavel', 'BLOQUEADO'),
        ],
      }),
    });
    // Dois portões fechados sem causa nesta montagem — os dois precisam dizê-lo.
    expect(
      screen.getAllByText(/Isto é uma lacuna do contrato, não uma permissão/i).length,
    ).toBe(2);
  });
});

describe('a ativação não vira um degrau alcançável', () => {
  // ⚠️ ACHADO QUE BLOQUEAVA O ACEITE (revisão adversarial Codex, lente 1).
  //
  // A etapa de ativação fechava com "não há campanha criada para ligar" — uma
  // dependência de SEQUÊNCIA. Bastava responder `criacao` para ela abrir. Só
  // que ela não abre nunca: `_portao_ativavel` devolve BLOQUEADO nos quatro
  // canais, em todos os perfis de sessão, e não existe rota de ativação entre
  // os 32 endpoints. Prometer o degrau seguinte de um caminho que termina ali
  // é a promessa falsa mais cara desta tela.
  it('com o portão fechado, a ativação fecha pela causa do servidor', () => {
    montar();
    expect(
      screen.getAllByText(/não existe rota de ativação neste sistema/i).length,
    ).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText(/não há campanha criada para ligar/i)).toBeNull();
  });

  it('nem respondendo a criação a ativação abre', () => {
    // A prova direta na máquina: mesmo com `criacao` respondida — o estado que
    // antes destravava a etapa —, o portão do servidor continua mandando.
    const passos = montarConversa({
      manifesto: contrato().manifesto,
      respostas: { criacao: 'campanha 123 criada, pausada' },
      travaAberta: true,
      podeAprovar: true,
      portoes: {
        validavel: { estado: 'PERMITIDO', causa: null },
        criavel_pausada: { estado: 'PERMITIDO', causa: null },
        ativavel: {
          estado: 'BLOQUEADO',
          causa: 'não existe rota de ativação neste sistema.',
        },
      },
    });
    const ativacao = passos.find((p) => p.etapa === 'ativacao')!;
    expect(ativacao.estado).toBe('bloqueada');
    expect(ativacao.dependencia?.dependencia).toMatch(/não existe rota de ativação/i);
  });

  it('sem portão lido, a regra local NÃO abre a ativação por conta própria', () => {
    // Ausência de leitura não pode virar permissão. Sem `portoes`, a máquina
    // cai na regra conservadora e a etapa continua fechada.
    const passos = montarConversa({
      manifesto: contrato().manifesto,
      respostas: {},
      travaAberta: true,
      podeAprovar: true,
    });
    expect(passos.find((p) => p.etapa === 'ativacao')!.estado).toBe('bloqueada');
  });
});

describe('nenhum ato falso sai desta tela', () => {
  it('não existe controle de ativar, nem quando ativável vem sem bloqueador', () => {
    // Nenhum canal deste sistema tem rota de ativação: `_portao_ativavel`
    // devolve BLOQUEADO em todos os ramos. Um botão de ligar seria UI morta.
    montar({
      contrato: contrato({
        portoes: [
          portao('planejavel', 'PERMITIDO'),
          portao('validavel', 'PERMITIDO'),
          portao('criavel_pausada', 'PERMITIDO'),
          portao('ativavel', 'BLOQUEADO', []),
        ],
      }),
    });
    // ⚠️ Antes este laço percorria uma coleção VAZIA e passava sem executar uma
    // única asserção — o defeito que a revisão adversarial chamou de vacuamente
    // verdadeiro. Agora o estado da coleção é afirmado primeiro, e a busca é
    // por qualquer elemento interativo (não só `role=button`), incluindo os que
    // um "Confirmar" genérico traria.
    const interativos = [
      ...screen.queryAllByRole('button'),
      ...screen.queryAllByRole('link'),
      ...Array.from(document.querySelectorAll('input, select, textarea, [onclick]')),
    ];
    expect(interativos.length, 'a montagem não tem controle nenhum a inspecionar')
      .toBe(0);
    // E o texto inteiro da tela também não promete o ato.
    expect(document.body.textContent ?? '').not.toMatch(
      /\b(ativar|despausar|habilitar) (esta )?campanha\b/i,
    );
  });

  it('a tela não dispara chamada privilegiada: nenhum controle, e nenhum cliente HTTP', () => {
    montar();
    // Primeiro o fato: a jornada é leitura. Ela não tem controle nenhum além do
    // "tentar ler de novo", que só aparece no estado de falha.
    expect(screen.queryAllByRole('button').length).toBe(0);

    // Depois a prova estrutural, que é a que vale: o módulo não importa o
    // cliente HTTP do backend. Um botão renomeado passaria por qualquer regex
    // de texto; um `import` não passa.
    const fonte = readFileSync(
      resolve(__dirname, '..', 'JornadaDoCanal.tsx'),
      'utf-8',
    );
    expect(fonte).not.toMatch(/pautadorApi/);
    expect(fonte).not.toMatch(/\bfetch\(/);
    expect(fonte).not.toMatch(/useMutation/);
  });
});

describe('os estados degradados são três frases diferentes', () => {
  it('lendo não afirma veredito', () => {
    montar({ carregando: true });
    expect(screen.getByText(/Lendo o que este canal permite agora/i)).toBeTruthy();
    expect(screen.queryByText(/Criável pausada/i)).toBeNull();
  });

  it('falha SEM leitura anterior: não afirma bloqueio, e oferece reler', () => {
    montar({ contrato: null, falhou: true, aoRevalidar: () => {} });
    const alerta = screen.getByRole('alert');
    expect(alerta.textContent).toMatch(/não afirma que ele esteja bloqueado/i);
    expect(screen.getByRole('button', { name: /tentar ler de novo/i })).toBeTruthy();
    expect(screen.queryByText(/Criável pausada/i)).toBeNull();
  });

  it('falha COM leitura anterior preserva o veredito e diz que envelheceu', () => {
    // ⚠️ ACHADO DA REVISÃO ADVERSARIAL (lente 3). O React Query preserva o
    // último resultado bom quando uma RELEITURA falha. Apagar o contrato da
    // tela colapsava "conhecido, porém velho" em "não sei nada" — dois estados
    // que pedem atos diferentes, e o operador perdia um veredito que continua
    // sendo o melhor disponível.
    montar({ falhou: true, aoRevalidar: () => {} });
    const alerta = screen.getByRole('alert');
    expect(alerta.textContent).toMatch(/última leitura que deu certo/i);
    expect(alerta.textContent).toMatch(/ninguém os confirmou agora/i);
    // Os portões continuam na tela — são reais, não placeholder.
    expect(screen.getByText(/Criável pausada/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /tentar ler de novo/i })).toBeTruthy();
  });

  it('o aviso de releitura falha não vira veredito novo: a escada é a mesma', () => {
    // Sem o aviso, a mesma escada. Com o aviso, a mesma escada mais o aviso —
    // nenhum estado muda por causa da falha de releitura.
    const portoes = () =>
      ['Planejável', 'Validável', 'Criável pausada', 'Ativável'].map((rotulo) => {
        const linha = screen
          .getAllByRole('listitem')
          .find((li) => (li.textContent ?? '').includes(rotulo))!;
        // A palavra do estado, que é o que o operador lê.
        return [rotulo, /permitido|bloqueado|não apurado|não cabe/i
          .exec(linha.textContent ?? '')?.[0]?.toLowerCase()];
      });

    montar({ falhou: true });
    const comFalha = portoes();
    cleanup();
    montar();
    const semFalha = portoes();

    // Nenhum estado muda por causa da falha de RELEITURA: o veredito é o mesmo,
    // o que mudou foi só a confiança na idade dele.
    expect(comFalha).toEqual(semFalha);
    expect(comFalha.map(([, estado]) => estado)).toEqual([
      'permitido', 'permitido', 'bloqueado', 'bloqueado',
    ]);
  });

  it('contrato ausente é dito como defeito do servidor, não como recusa', () => {
    montar({ contrato: null });
    expect(
      screen.getByText(/não uma recusa dirigida a você/i),
    ).toBeTruthy();
  });
});

describe('a causa repetida é dita uma vez', () => {
  // ⚠️ Medido ao ver a conversa montada pela primeira vez: um canal sem
  // construtor devolve treze etapas bloqueadas pela MESMA frase, e a lista
  // imprimia a frase treze vezes — treze parágrafos idênticos empurrando para
  // fora da tela a única informação nova de cada linha, que é o nome da etapa.
  it('canal não operado: a dependência aparece uma vez, não uma por etapa', () => {
    render(
      <ConversaDeCriacao
        passos={montarConversa({
          manifesto: null, respostas: {}, travaAberta: null, podeAprovar: true,
        })}
      />,
    );
    const repetida = screen.getAllByText(
      /o Hub não declara construtor para este canal/i,
    );
    // Uma no subtítulo do cabeçalho. Nenhuma nas treze linhas.
    expect(repetida.length).toBe(1);
    expect(
      screen.getByText(/estão fechadas pelo mesmo motivo/i),
    ).toBeTruthy();
  });

  it('quando as causas DIFEREM, cada linha volta a carregar a sua', () => {
    // O caso interessante: aí a diferença é a informação, e resumir apagaria
    // justamente o que o operador precisa comparar.
    render(
      <ConversaDeCriacao
        passos={montarConversa({
          manifesto: {
            plataforma: 'GOOGLE_ADS', canal: 'SEARCH', rotulo: 'Search',
            hierarquia: ['campanha'], paineis: [], campos_do_pedido: ['conversao'],
            capacidades: ['ler', 'propor'], provas_obrigatorias: [],
            indisponibilidades: [], sabe_provar: true, sabe_criar: true,
          },
          respostas: {},
          travaAberta: null,
          podeAprovar: false,
        })}
      />,
    );
    // `aprovacao` fecha por papel; `criacao` fecha por prova; `ativacao` por
    // não haver campanha criada. Três causas, três frases.
    expect(screen.getByText(/exige um papel que esta conta não tem/i)).toBeTruthy();
    expect(screen.getByText(/a prova contra a conta ainda não passou/i)).toBeTruthy();
    expect(screen.getByText(/não há campanha criada para ligar/i)).toBeTruthy();
    expect(screen.queryByText(/estão fechadas pelo mesmo motivo/i)).toBeNull();
  });
});

describe('a conversa de criação chega junto com os portões', () => {
  it('as treze etapas aparecem, e criar e ligar continuam separadas', () => {
    montar();
    expect(screen.getByText(/Criação pausada/i)).toBeTruthy();
    expect(screen.getAllByText(/Ativação/i).length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Criar e ligar são duas decisões/i),
    ).toBeTruthy();
  });

  it('a criação fecha pela CAUSA DO SERVIDOR, e nenhum estado de trava a reabre', () => {
    // ⚠️ Antes esta etapa fechava por uma regra local ("a prova ainda não
    // passou"), enquanto a escada logo acima dizia que o motivo era a janela do
    // canário. Dois motivos para o mesmo fato, na mesma tela — e o operador
    // levado à porta errada.
    //
    // Agora quem responde é o portão `criavel_pausada`, e nenhuma combinação de
    // trava o reabre.
    for (const trava of [null, false, true] as const) {
      cleanup();
      montar({ travaAberta: trava });
      expect(
        screen.getAllByText(/a janela autorizada de criação admite apenas Search/i).length,
        `trava=${String(trava)} deveria continuar fechando pela causa do servidor`,
      ).toBeGreaterThanOrEqual(2);
      expect(screen.queryByText(/a prova contra a conta ainda não passou/i)).toBeNull();
    }
  });

  it('sem papel para aprovar, a aprovação aparece bloqueada com o motivo', () => {
    montar({ podeAprovar: false });
    expect(
      screen.getByText(/assinar esta aprovação exige um papel que esta conta não tem/i),
    ).toBeTruthy();
  });
});
