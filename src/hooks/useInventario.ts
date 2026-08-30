/**
 * A leitura do inventário — uma só, compartilhada, e que nunca perde o último
 * dado bom.
 *
 * ## Por que cursor e não deslocamento
 *
 * Entre uma página e a seguinte o inventário muda: uma campanha é pausada,
 * outra é lida pela primeira vez. Com deslocamento, um item pula ou aparece
 * duas vezes. O cursor descreve uma POSIÇÃO, não uma contagem.
 *
 * ## Por que o hook devolve vocabulário de operação, e não o objeto do React
 * ## Query
 *
 * Quem consome isto é uma tela, e a tela pergunta "estou carregando?", "o que
 * está na mão?", "falhou?". Devolver `isLoading`/`isFetching`/`isPending` crus
 * espalharia a semântica da biblioteca por dentro dos componentes — e trocá-la
 * um dia obrigaria a reescrever a tela junto. Aqui a fronteira custa dez
 * linhas.
 *
 * ## As três regras, do lado do cliente
 *
 *  A. o envelope carrega o frescor do conjunto e cada conta carrega o seu — a
 *     mescla de páginas preserva o PIOR, porque uma conta velha não fica nova
 *     por estar ao lado de uma recente, e a DATA viaja junto com a palavra:
 *     frescor de uma página com a hora de outra é um carimbo que não descreve
 *     nada;
 *  B. nada aqui converte `null` em `0`; a mescla só concatena;
 *  C. falha de atualização NÃO apaga a tela. O último inventário bom continua
 *     disponível com `falhou` aceso ao lado — a interface mostra o dado antigo
 *     dizendo que é antigo, que é o oposto de mostrar vazio;
 *  D. o que sai daqui para a tela é frase de OPERAÇÃO. `motivoDaFalha` já foi
 *     `error.message`, e as mensagens desse `message` nascem no cliente HTTP
 *     para quem conserta o sistema: URL do backend, nome de variável de
 *     ambiente, `detail` do servidor com exceção recortada. O operador não age
 *     sobre nada disso. A tradução acontece AQUI, na fronteira, e não em cada
 *     componente que resolver mostrar um erro — regra que depende de cada
 *     consumidor lembrar dela já foi perdida.
 */
import React from 'react';
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';

import { pautadorApi } from '@/lib/pautadorApi';
import {
  type OcorrenciaOperacional,
  descreverFalha,
  registrarDetalhe,
} from '@/components/trafego/inventario/erros';
import type {
  ContaNoInventario,
  Faltou,
  FiltrosDoInventario,
  Frescor,
  Inventario,
  Leitura,
} from '@/types/trafego';

export const CHAVE_INVENTARIO = ['trafego', 'inventario'] as const;

/**
 * Ritmo de reconsulta ao NOSSO registro, não à conta de anúncio.
 *
 * A tela lê o que o sincronizador gravou; abrir o painel não custa cota do
 * Google. O intervalo existe só para o número na tela não envelhecer calado
 * enquanto alguém deixa a aba aberta a tarde inteira.
 */
export const INTERVALO_INVENTARIO_MS = 5 * 60 * 1000;

/** Do melhor para o pior. A mescla escolhe sempre o pior: otimismo aqui vira
 *  número velho apresentado como atual. */
const ORDEM_DO_FRESCOR: Frescor[] = [
  'recente',
  'vazio_confirmado',
  'velho',
  'parcial',
  'nunca_lido',
  'falhou',
];

export function piorFrescor(a: Frescor, b: Frescor): Frescor {
  return ORDEM_DO_FRESCOR.indexOf(a) >= ORDEM_DO_FRESCOR.indexOf(b) ? a : b;
}

/**
 * A idade mais VELHA entre duas leituras — e `null` quando alguma não tem data.
 *
 * ⚠️ `null` aqui não é "sem informação a acrescentar": é "há um pedaço deste
 * conjunto cuja idade eu não conheço". Escolher a idade conhecida da outra
 * página carimbaria o conjunto inteiro com uma data que não vale para tudo que
 * ele contém, e o carimbo seria sempre o mais novo dos dois — a direção errada.
 * Sem data, a tela diz "sem data de leitura", que é a verdade.
 */
export function leituraMaisVelha(a: Leitura | null, b: Leitura | null): Leitura | null {
  if (!a || !b) return null;
  return a.idade_s >= b.idade_s ? a : b;
}

/**
 * Junta as páginas já carregadas num envelope só.
 *
 * Contas repetidas entre páginas têm as campanhas concatenadas — nunca
 * substituídas. `quantidade` fica com o maior valor visto: é o total do grupo
 * segundo o servidor, e um total que encolhesse ao paginar mentiria sobre o
 * que ainda falta carregar.
 *
 * ## ⚠️ O frescor e a data andam JUNTOS, e por um tempo não andavam
 *
 * A mescla escolhia o pior frescor e ficava com a `leitura` da PRIMEIRA página.
 * O resultado era um envelope que dizia "leitura antiga" carimbado com a hora
 * da leitura recente, ou "sincronização falhou" ao lado de "lido há 2 min" — a
 * palavra vinha de uma página e o número de outra. A idade impressa deixava de
 * descrever o dado que estava embaixo dela, que é a única coisa que ela existe
 * para fazer.
 *
 * Aqui o descritor de uma conta é adotado INTEIRO — frescor, leitura, última
 * leitura boa e motivo saem todos da mesma página, a de pior estado. Só
 * `campanhas` e `quantidade` são somadas, porque essas sim são a união do que
 * as páginas trouxeram.
 */
function piorDescritorDaConta(
  a: ContaNoInventario,
  b: ContaNoInventario,
): ContaNoInventario {
  const pior = piorFrescor(a.frescor, b.frescor);
  if (a.frescor !== b.frescor) return pior === a.frescor ? a : b;
  // Empate de estado: manda a leitura mais velha, porque é ela que descreve o
  // pedaço menos confiável do que está na tela.
  return (a.leitura?.idade_s ?? Infinity) >= (b.leitura?.idade_s ?? Infinity) ? a : b;
}

export function mesclarPaginas(paginas: Inventario[]): Inventario | null {
  if (paginas.length === 0) return null;
  const primeira = paginas[0];
  const ultima = paginas[paginas.length - 1];

  const porConta = new Map<string, ContaNoInventario>();
  for (const pagina of paginas) {
    for (const conta of pagina.contas) {
      const jaVista = porConta.get(conta.customer_id);
      if (!jaVista) {
        porConta.set(conta.customer_id, { ...conta, campanhas: [...conta.campanhas] });
        continue;
      }
      const conhecidas = new Set(jaVista.campanhas.map((c) => c.volc_campaign_id));
      const campanhas = [
        ...jaVista.campanhas,
        ...conta.campanhas.filter((c) => !conhecidas.has(c.volc_campaign_id)),
      ];
      const descritor = piorDescritorDaConta(jaVista, conta);
      porConta.set(conta.customer_id, {
        ...descritor,
        quantidade: Math.max(jaVista.quantidade, conta.quantidade),
        campanhas,
      });
    }
  }

  const faltou: Faltou[] = [];
  const vistos = new Set<string>();
  for (const pagina of paginas) {
    for (const f of pagina.faltou) {
      const chave = `${f.customer_id ?? ''}|${f.escopo}|${f.motivo}`;
      if (vistos.has(chave)) continue;
      vistos.add(chave);
      faltou.push(f);
    }
  }

  return {
    ...primeira,
    frescor: paginas.map((p) => p.frescor).reduce(piorFrescor),
    // A data do conjunto acompanha o pior caso do conjunto: a mais velha entre
    // as páginas, e nenhuma quando alguma delas veio sem data.
    leitura: paginas.map((p) => p.leitura).reduce(leituraMaisVelha),
    parcial: paginas.some((p) => p.parcial),
    faltou,
    contas: [...porConta.values()],
    proximo_cursor: ultima.proximo_cursor,
  };
}

export interface LeituraDoInventario {
  /** O último inventário utilizável. `null` só quando nunca houve nenhum. */
  inventario: Inventario | null;
  /** Primeira leitura desta sessão, ainda sem nada na mão. */
  carregando: boolean;
  /** Há uma leitura em curso por cima de dado que já está na tela. */
  atualizando: boolean;
  /** A última tentativa falhou. Não implica ausência de dado. */
  falhou: boolean;
  /**
   * A falha em uma frase — SEMPRE do vocabulário fechado de `erros.ts`.
   *
   * Nunca `error.message`. Ver a regra D no topo do arquivo.
   */
  motivoDaFalha: string | null;
  /**
   * A mesma falha com o próximo passo e o código copiável.
   *
   * Opcional na assinatura porque quem monta a tela hoje ainda passa só
   * `motivoDaFalha` adiante; quando o painel passar a ocorrência inteira, o
   * código que o operador vê passa a ser este — o mesmo que foi registrado no
   * console no instante da falha.
   */
  ocorrencia?: OcorrenciaOperacional | null;
  temMais: boolean;
  carregandoMais: boolean;
  carregarMais: () => void;
  recarregar: () => void;
}

export function useInventario(
  filtros?: FiltrosDoInventario,
  opcoes?: { habilitado?: boolean },
): LeituraDoInventario {
  const habilitado = opcoes?.habilitado ?? true;
  const consulta = useInfiniteQuery({
    queryKey: [...CHAVE_INVENTARIO, filtros ?? null],
    queryFn: ({ pageParam }) => pautadorApi.inventario(filtros, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (ultima: Inventario) => ultima.proximo_cursor,
    staleTime: INTERVALO_INVENTARIO_MS,
    refetchInterval: habilitado ? INTERVALO_INVENTARIO_MS : false,
    refetchOnWindowFocus: habilitado,
    enabled: habilitado,
    // Trocar de filtro não deve piscar esqueleto por cima de dado bom: o que
    // já estava lido continua na tela enquanto a resposta nova não chega.
    placeholderData: keepPreviousData,
    retry: 1,
  });

  const inventario = React.useMemo(
    () => mesclarPaginas(consulta.data?.pages ?? []),
    [consulta.data],
  );

  // Memo pela identidade do erro: sem ele o código da ocorrência seria sorteado
  // a cada render e o operador veria um identificador diferente a cada piscada
  // da tela — nenhum deles servindo para achar nada.
  const ocorrencia = React.useMemo(
    () => (consulta.error ? descreverFalha(consulta.error, 'inventario') : null),
    [consulta.error],
  );

  // O detalhe técnico não é jogado fora: ele vai para o console, que é onde
  // quem depura já olha, e fora do alcance de quem só quer saber se pode mexer
  // na campanha.
  React.useEffect(() => {
    if (ocorrencia && consulta.error) registrarDetalhe(consulta.error, ocorrencia);
  }, [ocorrencia, consulta.error]);

  return {
    inventario,
    carregando: consulta.isLoading && inventario == null,
    atualizando: consulta.isFetching,
    falhou: consulta.isError,
    motivoDaFalha: ocorrencia?.mensagem ?? null,
    ocorrencia,
    temMais: Boolean(consulta.hasNextPage),
    carregandoMais: consulta.isFetchingNextPage,
    carregarMais: () => { void consulta.fetchNextPage(); },
    recarregar: () => { void consulta.refetch(); },
  };
}

export interface PedidoDeLeitura {
  pedir: (customerId: string) => void;
  /** Qual conta está sendo lida agora, se alguma. */
  contaEmLeitura: string | null;
  /**
   * O que aconteceu com o pedido, por conta, já em linguagem de operação.
   *
   * Quando dá errado o recado traz o código da ocorrência dentro do texto: o
   * cabeçalho da conta imprime uma frase só, e um código que não viajasse junto
   * dela simplesmente não chegaria ao operador.
   */
  recados: Record<string, string>;
  /**
   * A mesma coisa em forma de objeto, para quem quiser oferecer botão de copiar.
   *
   * Opcional na assinatura porque o cabeçalho da conta ainda imprime só a
   * frase; ver o pedido ao integrador.
   */
  ocorrencias?: Record<string, OcorrenciaOperacional>;
}

/** A frase inteira que cabe num `<p>`: o que houve, o que fazer, e o código. */
function recadoDe(ocorrencia: OcorrenciaOperacional): string {
  return [
    ocorrencia.mensagem,
    ocorrencia.complemento,
    ocorrencia.proximoPasso,
    `Código da ocorrência: ${ocorrencia.id}.`,
  ]
    .filter(Boolean)
    .join(' ');
}

/**
 * Pede uma leitura nova de UMA conta.
 *
 * Uma por vez de propósito: um botão de "atualizar tudo" é clicado três vezes
 * por quem achou que não funcionou, e cada clique custa cota da conta de
 * anúncio. O servidor pode recusar — e quando recusa, ele diz por quê; a tela
 * mostra o motivo em vez de fingir que aceitou.
 *
 * Isto LÊ a conta. Não altera lance, verba nem estado de campanha nenhuma.
 */
export function usePedirLeituraDaConta(): PedidoDeLeitura {
  const cliente = useQueryClient();
  const [recados, setRecados] = React.useState<Record<string, string>>({});
  const [ocorrencias, setOcorrencias] = React.useState<Record<string, OcorrenciaOperacional>>({});

  const mutacao = useMutation({
    mutationFn: (customerId: string) => pautadorApi.atualizarConta(customerId),
  });

  const anotar = React.useCallback(
    (customerId: string, ocorrencia: OcorrenciaOperacional) => {
      setRecados((antes) => ({ ...antes, [customerId]: recadoDe(ocorrencia) }));
      setOcorrencias((antes) => ({ ...antes, [customerId]: ocorrencia }));
    },
    [],
  );

  // `mutacao.mutate` é estável entre renders; `mutacao` (o objeto) não é. Com o
  // objeto na lista, `pedir` nascia de novo a cada render e qualquer memo do
  // lado de quem consome virava enfeite.
  const disparar = mutacao.mutate;

  const pedir = React.useCallback((customerId: string) => {
    disparar(customerId, {
      onSuccess: (resposta) => {
        // ⚠️ `aceito !== false`, e não `aceito === true`.
        //
        // O contrato do cliente HTTP promete `{aceito, motivo}`; a rota que
        // responde devolve `{escopo, custo, resultado, escrita_permitida}`. Com
        // o teste antigo (`if (resposta.aceito)`), `undefined` caía no ramo da
        // recusa — ou seja, TODA leitura bem-sucedida era anunciada ao operador
        // como "o servidor recusou o pedido e não disse por quê". O operador
        // conclui que o botão não funciona e clica de novo, e cada clique custa
        // cota da conta de anúncio do cliente: o defeito custava dinheiro.
        //
        // Uma resposta com sucesso HTTP é aceitação. Recusa é o servidor DIZER
        // que recusou, explicitamente.
        if (resposta?.aceito !== false) {
          setRecados((antes) => ({
            ...antes,
            [customerId]: 'leitura pedida — o número desta conta se atualiza quando ela responder',
          }));
          setOcorrencias((antes) => {
            const proximo = { ...antes };
            delete proximo[customerId];
            return proximo;
          });
          void cliente.invalidateQueries({ queryKey: CHAVE_INVENTARIO });
          return;
        }
        // Recusa declarada. O `motivo` do servidor NÃO é impresso: é texto livre
        // vindo de fora e o caminho por onde a exceção do backend voltaria à
        // tela por uma porta lateral. Se um dia houver motivos de recusa que o
        // operador precise distinguir, eles viram código de um vocabulário
        // combinado entre as duas pontas — não frase solta.
        anotar(customerId, descreverFalha({ status: 409 }, 'leitura_de_conta'));
      },
      onError: (erro) => {
        const ocorrencia = descreverFalha(erro, 'leitura_de_conta');
        registrarDetalhe(erro, ocorrencia);
        anotar(customerId, ocorrencia);
      },
    });
  }, [anotar, cliente, disparar]);

  return {
    pedir,
    contaEmLeitura: mutacao.isPending ? (mutacao.variables ?? null) : null,
    recados,
    ocorrencias,
  };
}
