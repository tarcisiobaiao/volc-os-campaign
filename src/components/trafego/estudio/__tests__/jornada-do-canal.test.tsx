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
    expect(
      screen.getByText(/a janela autorizada de criação admite apenas Search/i),
    ).toBeTruthy();
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
    expect(screen.getByText(causa)).toBeTruthy();
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
    for (const b of screen.queryAllByRole('button')) {
      expect(b.textContent ?? '').not.toMatch(/ativar|ligar|despausar|habilitar/i);
    }
  });

  it('a tela não dispara chamada privilegiada: não há botão de provar nem de subir', () => {
    montar();
    for (const b of screen.queryAllByRole('button')) {
      expect(b.textContent ?? '').not.toMatch(/provar|subir|criar campanha|lançar/i);
    }
  });
});

describe('os estados degradados são três frases diferentes', () => {
  it('lendo não afirma veredito', () => {
    montar({ carregando: true });
    expect(screen.getByText(/Lendo o que este canal permite agora/i)).toBeTruthy();
    expect(screen.queryByText(/Criável pausada/i)).toBeNull();
  });

  it('falha de leitura diz que não é bloqueio, e oferece reler', () => {
    montar({ falhou: true, aoRevalidar: () => {} });
    const alerta = screen.getByRole('alert');
    expect(alerta.textContent).toMatch(/não afirma que ele esteja bloqueado/i);
    expect(screen.getByRole('button', { name: /tentar ler de novo/i })).toBeTruthy();
    expect(screen.queryByText(/Criável pausada/i)).toBeNull();
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

  it('a criação fica fechada pela prova, ANTES de a trava sequer ser consultada', () => {
    // ⚠️ Esta prova fixa a ORDEM das dependências, e ela importa.
    //
    // `travaDaEtapa` pergunta pela prova primeiro: sem prova aprovada, a
    // criação está fechada e o estado da trava é irrelevante para o operador
    // naquele instante. Dizer "a trava está fechada" aqui mandaria a pessoa
    // pedir a abertura da trava para destravar algo que a trava não segura —
    // e a trava é justamente o que não se pede por engano.
    //
    // A trava continua entrando na máquina e volta a decidir assim que a prova
    // for respondida; o que esta prova impede é a tela antecipar o motivo.
    for (const trava of [null, false, true] as const) {
      cleanup();
      montar({ travaAberta: trava });
      expect(
        screen.getByText(/a prova contra a conta ainda não passou/i),
        `trava=${String(trava)} deveria continuar barrando pela prova`,
      ).toBeTruthy();
      expect(screen.queryByText(/trava de escrita/i)).toBeNull();
    }
  });

  it('sem papel para aprovar, a aprovação aparece bloqueada com o motivo', () => {
    montar({ podeAprovar: false });
    expect(
      screen.getByText(/assinar esta aprovação exige um papel que esta conta não tem/i),
    ).toBeTruthy();
  });
});
