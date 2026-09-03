/**
 * A bancada visual — os componentes REAIS, em todos os estados obrigatórios.
 *
 * ## Por que ela existe
 *
 * O QA visual desta superfície tinha um problema circular: os estados que mais
 * precisam ser conferidos — leitura falhou, dado velho, portão bloqueado,
 * contrato ausente, prova recusada — são justamente os que uma conta saudável
 * não produz sob demanda. Conferir só o caminho feliz é conferir o caminho que
 * não dá trabalho.
 *
 * Esta página monta os componentes de verdade (não cópias, não mocks visuais)
 * contra fixtures tipadas, um estado por endereço. O que se vê aqui é o mesmo
 * JSX que o operador vê; o que muda é de onde vêm os dados.
 *
 * ## O que ela NÃO é
 *
 * Não é uma simulação de capacidade. Nenhuma fixture aqui declara um portão
 * aberto que o servidor fecha, nem um canal criável que o executor recusa — as
 * fixtures reproduzem respostas que o backend sabe emitir, e as recusas são as
 * recusas reais. Uma bancada que inventasse permissão viraria a mentira que o
 * resto deste domínio existe para impedir.
 *
 * ## Ela não pode chegar em produção
 *
 * A rota é registrada apenas sob `import.meta.env.DEV`, que o Vite substitui
 * pelo literal `false` no build — o ramo inteiro, inclusive o `import()`
 * dinâmico, sai na eliminação de código morto.
 *
 * Quem cobra isso é `src/pages/qa/__tests__/bancada-fora-de-producao.test.ts`,
 * em dois níveis: a prova rápida lê a fonte e exige o guarda e o import
 * preguiçoso; a prova cara roda `vite build` de verdade e procura o marcador
 * abaixo no bundle inteiro. A rápida sozinha não bastaria — ela prova o
 * mecanismo, não o resultado.
 *
 * Endereço: `/qa/trafego/:superficie/:estado`
 */

import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { JornadaDoCanal } from '@/components/trafego/estudio/JornadaDoCanal';
import { ConversaDeCriacao } from '@/components/trafego/criacao/ConversaDeCriacao';
import { montarConversa } from '@/components/trafego/criacao/conversa';
import type {
  BloqueadorDeCanal,
  ContratoDeCanal,
  PortaoDeCanal,
} from '@/lib/trafego/canais';
import type { ManifestoDeCanal } from '@/types/trafego';

/**
 * O marcador que a prova de bundle procura.
 *
 * Uma string improvável de aparecer por acidente. Se ela estiver no bundle de
 * produção, esta página inteira foi junto.
 */
export const MARCADOR_DA_BANCADA = 'volc-bancada-visual-somente-dev';

// ── fixtures: respostas que o backend SABE emitir ───────────────────────────

const portao = (
  nome: PortaoDeCanal['nome'],
  estado: PortaoDeCanal['estado'],
  bloqueadores: BloqueadorDeCanal[] = [],
): PortaoDeCanal => ({ nome, estado, aberto: estado === 'PERMITIDO', bloqueadores });

const ATIVACAO_FECHADA: BloqueadorDeCanal = {
  codigo: 'ativacao_fora_do_contrato',
  causa:
    'não existe rota de ativação neste sistema. Despausar é feito no painel do '
    + 'Google, por uma pessoa, depois de conferir o que foi criado.',
  origem: 'produto',
  observado_em: null,
  revalidacao: null,
};

const manifesto = (over: Partial<ManifestoDeCanal>): ManifestoDeCanal => ({
  plataforma: 'GOOGLE_ADS',
  canal: 'SEARCH',
  rotulo: 'Search',
  hierarquia: ['campanha', 'grupo', 'anuncio', 'keyword'],
  paineis: ['keywords', 'termos_de_busca', 'anuncios', 'negativas'],
  campos_do_pedido: ['grupos', 'keywords', 'negativas', 'copy', 'url_final',
                     'verba_diaria', 'estrategia_de_lance'],
  capacidades: ['ler', 'propor'],
  provas_obrigatorias: ['politica', 'duplicidade', 'selo'],
  indisponibilidades: [],
  sabe_provar: true,
  sabe_criar: true,
  ...over,
});

const base = (over: Partial<ContratoDeCanal>): ContratoDeCanal => ({
  plataforma: 'GOOGLE_ADS',
  canal: 'SEARCH',
  rotulo: 'Search',
  manifesto: manifesto({}),
  portoes: [],
  assets: { estado: 'PERMITIDO', recursos: ['texto', 'sitelink'], quantidade: 2,
            fonte: 'perfil do canal', causa: null },
  mensuracao: { lida: false } as ContratoDeCanal['mensuracao'],
  observabilidade: {} as ContratoDeCanal['observabilidade'],
  operacional: {},
  ...over,
});

/** SEARCH: o único canal que atravessa criação — e ainda assim pausado. */
const SEARCH = base({
  portoes: [
    portao('planejavel', 'PERMITIDO'),
    portao('validavel', 'PERMITIDO'),
    portao('criavel_pausada', 'PERMITIDO'),
    portao('ativavel', 'BLOQUEADO', [ATIVACAO_FECHADA]),
  ],
});

/** DISPLAY: sabe criar, e a janela do canário recusa. Política, não construtor. */
const DISPLAY = base({
  canal: 'DISPLAY',
  rotulo: 'Display',
  manifesto: manifesto({
    canal: 'DISPLAY', rotulo: 'Display',
    hierarquia: ['campanha', 'grupo', 'anuncio', 'asset'],
    paineis: ['anuncios', 'criativos'],
    campos_do_pedido: ['copy', 'url_final', 'verba_diaria'],
    indisponibilidades: [
      'sem segmentação por público na primeira fatia: a campanha compra '
      + 'inventário aberto escolhido pelo lance.',
    ],
  }),
  portoes: [
    portao('planejavel', 'PERMITIDO'),
    portao('validavel', 'PERMITIDO'),
    portao('criavel_pausada', 'BLOQUEADO', [{
      codigo: 'fora_da_janela_do_canario',
      causa: 'a janela autorizada de criação admite apenas Search neste momento.',
      origem: 'politica',
      observado_em: null,
      revalidacao: 'a janela é revista pelo dono da operação; não há releitura automática.',
    }]),
    portao('ativavel', 'BLOQUEADO', [ATIVACAO_FECHADA]),
  ],
});

/** DEMAND_GEN: prova atrás de porta estreita; criação recusada por manifesto. */
const DEMAND_GEN = base({
  canal: 'DEMAND_GEN',
  rotulo: 'Demand Gen',
  manifesto: manifesto({
    canal: 'DEMAND_GEN', rotulo: 'Demand Gen',
    hierarquia: ['campanha', 'grupo', 'anuncio', 'asset'],
    paineis: ['audiencias', 'criativos'],
    campos_do_pedido: ['copy', 'url_final', 'verba_diaria', 'audiencias'],
    sabe_criar: false,
    indisponibilidades: ['mutação real recusada pelo manifesto deste canal.'],
  }),
  portoes: [
    portao('planejavel', 'PERMITIDO'),
    portao('validavel', 'BLOQUEADO', [{
      codigo: 'demand_gen_experimental_desligado',
      causa: 'a prova de Demand Gen está desligada neste servidor.',
      origem: 'servidor',
      observado_em: null,
      revalidacao: 'quem administra o servidor liga a porta experimental e refaz a sondagem do SDK.',
    }]),
    portao('criavel_pausada', 'BLOQUEADO', [{
      codigo: 'mutacao_real_recusada',
      causa: 'o manifesto deste canal não autoriza mutação real.',
      origem: 'manifesto',
      observado_em: null,
      revalidacao: null,
    }]),
    portao('ativavel', 'BLOQUEADO', [ATIVACAO_FECHADA]),
  ],
});

/** PERFORMANCE_MAX: planeja; criação retida por decisão; observabilidade não apurada. */
const PMAX = base({
  canal: 'PERFORMANCE_MAX',
  rotulo: 'Performance Max',
  manifesto: manifesto({
    canal: 'PERFORMANCE_MAX', rotulo: 'Performance Max',
    hierarquia: ['campanha', 'asset_group', 'asset'],
    paineis: [], campos_do_pedido: [], capacidades: ['ler'],
    provas_obrigatorias: [],
    sabe_provar: false, sabe_criar: false,
    indisponibilidades: [
      'criar: Performance Max não está no registro do executor. O builder monta '
      + 'e serializa o plano offline; o que falta é uma decisão de produto.',
      'provar por validate_only: a prova externa exige o canal habilitado no executor.',
    ],
  }),
  portoes: [
    portao('planejavel', 'PERMITIDO'),
    portao('validavel', 'BLOQUEADO', [{
      codigo: 'PMAX_FORA_DO_EXECUTOR',
      causa: 'Performance Max não está no registro do executor: o plano é montado offline e não é submetido à conta.',
      origem: 'produto',
      observado_em: null,
      revalidacao: 'a reversão é uma mudança coordenada e registrada; não há releitura que a mude.',
    }]),
    portao('criavel_pausada', 'BLOQUEADO', [
      {
        codigo: 'PMAX_FORA_DO_EXECUTOR',
        causa: 'Performance Max não está no registro do executor.',
        origem: 'produto', observado_em: null, revalidacao: null,
      },
      {
        codigo: 'pmax_observabilidade_nao_provada',
        causa: 'não conseguimos reler a estrutura de Performance Max depois de criada.',
        origem: 'observabilidade',
        observado_em: null,
        revalidacao: 'a releitura do ledger prova a observabilidade; ela ainda não rodou.',
      },
    ]),
    portao('ativavel', 'BLOQUEADO', [ATIVACAO_FECHADA]),
  ],
});

/** Um canal cujo servidor não apurou o primeiro portão. Âmbar, nunca vermelho. */
const NAO_APURADO = base({
  portoes: [
    portao('planejavel', 'INDETERMINADO'),
    portao('validavel', 'INDETERMINADO'),
    portao('criavel_pausada', 'INDETERMINADO'),
    portao('ativavel', 'BLOQUEADO', [ATIVACAO_FECHADA]),
  ],
});

/** Um contrato truncado: o servidor mandou um portão só. Ausente ≠ fechado. */
const PARCIAL = base({ portoes: [portao('planejavel', 'PERMITIDO')] });

/** Fechado sem causa: lacuna do contrato, e a tela precisa dizer que é lacuna. */
const SEM_CAUSA = base({
  portoes: [
    portao('planejavel', 'PERMITIDO'),
    portao('validavel', 'PERMITIDO'),
    portao('criavel_pausada', 'BLOQUEADO', []),
    portao('ativavel', 'BLOQUEADO', []),
  ],
});

// ── o catálogo ──────────────────────────────────────────────────────────────

type Cena = {
  titulo: string;
  /** O que esta cena PROVA. Aparece na página e no manifesto de screenshots. */
  afirma: string;
  render: () => React.ReactNode;
};

const jornada = (
  contrato: ContratoDeCanal | null,
  over: Partial<React.ComponentProps<typeof JornadaDoCanal>> = {},
) => () => (
  <JornadaDoCanal
    contrato={contrato}
    travaAberta={false}
    podeAprovar
    {...over}
  />
);

const CENAS: Record<string, Record<string, Cena>> = {
  jornada: {
    'search-criavel': {
      titulo: 'Search — atravessa a criação, e nasce pausada',
      afirma: 'três portões abertos e o quarto fechado por decisão de produto; nenhum controle de ativar.',
      render: jornada(SEARCH),
    },
    'display-politica': {
      titulo: 'Display — sabe criar, e a política recusa',
      afirma: 'bloqueio de origem `politica` com revalidação declarada; o manifesto diz sabe_criar, o portão diz não.',
      render: jornada(DISPLAY),
    },
    'demand-gen-porta-estreita': {
      titulo: 'Demand Gen — prova desligada, criação recusada pelo manifesto',
      afirma: 'dois bloqueios independentes, com origens diferentes (`servidor` e `manifesto`).',
      render: jornada(DEMAND_GEN),
    },
    'pmax-retido': {
      titulo: 'Performance Max — planeja, e a criação é retida por decisão',
      afirma: 'bloqueio de `produto` somado a um de `observabilidade`; nenhum deles diz que falta código.',
      render: jornada(PMAX),
    },
    'nao-apurado': {
      titulo: 'Nada apurado — âmbar, nunca vermelho',
      afirma: 'INDETERMINADO tem tom próprio; pintar ignorância de vermelho ensina a ignorar o vermelho.',
      render: jornada(NAO_APURADO),
    },
    'contrato-parcial': {
      titulo: 'Contrato truncado — portão ausente não é portão fechado',
      afirma: 'os portões que não vieram dizem "não veio", e não desenham recusa.',
      render: jornada(PARCIAL),
    },
    'fechado-sem-causa': {
      titulo: 'Fechado sem causa — lacuna do contrato',
      afirma: 'BLOQUEADO sem bloqueador é declarado como lacuna, e nunca lido como permissão.',
      render: jornada(SEM_CAUSA),
    },
    carregando: {
      titulo: 'Lendo',
      afirma: 'enquanto lê, a tela não desenha nenhum veredito.',
      render: jornada(SEARCH, { carregando: true }),
    },
    'leitura-falhou': {
      titulo: 'A leitura falhou',
      afirma: 'falha de leitura não é bloqueio, e a frase diz isso; há caminho de releitura.',
      render: jornada(null, { falhou: true, aoRevalidar: () => undefined }),
    },
    'contrato-ausente': {
      titulo: 'O canal não veio na resposta',
      afirma: 'ausência é dita como defeito do servidor, não como recusa dirigida ao operador.',
      render: jornada(null),
    },
    'sem-papel': {
      titulo: 'Sessão sem papel para aprovar',
      afirma: 'a etapa de aprovação fecha com o motivo, e não some da lista.',
      render: jornada(SEARCH, { podeAprovar: false }),
    },
  },
  conversa: {
    'canal-nao-operado': {
      titulo: 'Canal que o Hub não opera',
      afirma: 'as treze etapas saem bloqueadas com a mesma dependência nomeada — não somem.',
      render: () => (
        <ConversaDeCriacao
          passos={montarConversa({
            manifesto: null, respostas: {}, travaAberta: null, podeAprovar: true,
          })}
        />
      ),
    },
    'sem-conversao': {
      titulo: 'Canal cujo pedido não tem conversão',
      afirma: '`não se aplica` é distinto de `pendente`: é uma pergunta que não existe aqui.',
      render: () => (
        <ConversaDeCriacao
          passos={montarConversa({
            manifesto: manifesto({ campos_do_pedido: ['copy', 'url_final'] }),
            respostas: {}, travaAberta: true, podeAprovar: true,
          })}
        />
      ),
    },
  },
};

// ── a moldura ───────────────────────────────────────────────────────────────

/**
 * Um `QueryClient` próprio, com `retry: false`.
 *
 * A bancada não fala com a rede — os componentes montados aqui recebem tudo por
 * prop. O provedor existe para o caso de um filho consultar o cache, e a
 * ausência de retentativa garante que nenhuma tela fique presa num spinner.
 */
const clienteDaBancada = new QueryClient({
  defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: Infinity } },
});

export const BancadaVisual: React.FC = () => {
  const { superficie, estado } = useParams<{ superficie: string; estado: string }>();
  const grupo = superficie ? CENAS[superficie] : undefined;
  const cena = grupo && estado ? grupo[estado] : undefined;

  return (
    <QueryClientProvider client={clienteDaBancada}>
      <main className="min-h-screen bg-background px-5 py-8 md:px-10">
        <header className="mb-8 max-w-[78ch]">
          <p className="kicker" data-marcador={MARCADOR_DA_BANCADA}>
            bancada visual — só em desenvolvimento
          </p>
          <h1 className="mt-1 font-display text-2xl font-semibold tracking-tight md:text-3xl">
            {cena ? cena.titulo : 'Escolha uma cena'}
          </h1>
          {cena && (
            <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
              <span className="font-medium text-foreground">Esta cena prova:</span>{' '}
              {cena.afirma}
            </p>
          )}
        </header>

        {cena ? (
          <div data-cena={`${superficie}/${estado}`}>{cena.render()}</div>
        ) : (
          <Indice />
        )}
      </main>
    </QueryClientProvider>
  );
};

const Indice: React.FC = () => (
  <div className="space-y-8">
    {Object.entries(CENAS).map(([superficie, grupo]) => (
      <section key={superficie}>
        <h2 className="font-display text-lg font-semibold tracking-tight">{superficie}</h2>
        <ul className="mt-2 space-y-1" role="list">
          {Object.entries(grupo).map(([estado, cena]) => (
            <li key={estado}>
              <Link
                className="text-[13px] text-primary underline underline-offset-2"
                to={`/qa/trafego/${superficie}/${estado}`}
              >
                {estado}
              </Link>
              <span className="ml-2 text-[12px] text-muted-foreground">{cena.titulo}</span>
            </li>
          ))}
        </ul>
      </section>
    ))}
  </div>
);

/** O catálogo, para o driver de captura montar o plano sem adivinhar rota. */
export const CENAS_DA_BANCADA = Object.entries(CENAS).flatMap(([superficie, grupo]) =>
  Object.entries(grupo).map(([estado, cena]) => ({
    id: `${superficie}__${estado}`,
    path: `/qa/trafego/${superficie}/${estado}`,
    titulo: cena.titulo,
    afirma: cena.afirma,
  })),
);

export default BancadaVisual;
