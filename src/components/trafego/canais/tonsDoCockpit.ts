/**
 * Como o tom semântico vira classe no cockpit de canais.
 *
 * ## O que este arquivo NÃO é
 *
 * ⚠️ Ele **não decide** qual estado tem qual tom. Essa correspondência é única e
 * mora em `src/components/trafego/bancada/paradas/portoesVisual.ts` —
 * `TOM_DO_ESTADO`, `TOM_DO_PORTAO_DE_CANAL` e companhia. Este arquivo só traduz
 * um `TomDoChip` já decidido para as classes de superfície que o cockpit usa, e
 * escreve as descrições que o `ChipDeEstado` exige e que a tabela canônica não
 * carrega.
 *
 * Duplicar a decisão aqui recriaria exatamente o defeito que `portoesVisual.ts`
 * existe para fechar: dois renderizadores discordando de cor sobre o MESMO
 * veredito (`PortoesDoCanal.tsx:57-62` pintava BLOQUEADO de âmbar enquanto
 * `PainelDaMensuracao.tsx:67-74` pintava de vermelho).
 *
 * ## Por que fio no TOPO, e não faixa lateral grossa
 *
 * `design.md:99` — "Status on a card: a 2px top hairline in the semantic color.
 * Never a left/right stripe thicker than 1px" — e a proibição dura de
 * `design.md:130`. As três faixas `border-l-2` coloridas que existiam nestes
 * arquivos (`PortoesDoCanal.tsx:100`, `PainelDaMensuracao.tsx:238,255`,
 * `PlanoDeMensuracao.tsx:188`) violavam a regra pela espessura.
 *
 * Item de LISTA continua com fio lateral, mas de **1px** — que é o que
 * `design.md:130` permite ("stripes >1px" é o que ele proíbe). Um fio de 2px no
 * topo de cada `<li>` de uma lista vertical seria lido como separador de linha,
 * não como estado: a mesma tinta diria duas coisas na mesma tela.
 */
import type { TomDoChip } from '@/components/trafego/bancada/ChipDeEstado';
import type {
  EstadoDePortao as EstadoDoCanal,
  TomDoBloqueio,
} from '@/lib/trafego/canais';
import type { EstadoDePortao as EstadoDaMensuracao } from '@/lib/trafego/portoes';

/**
 * O fio de 2px no topo de um cartão de estado.
 *
 * Vem em duas metades porque `overflow-hidden` e o pseudo-elemento são
 * geometria (iguais para todo cartão) e a tinta é semântica (varia com o tom).
 */
export const FIO_DE_CARTAO =
  'relative overflow-hidden before:absolute before:inset-x-0 before:top-0 before:h-[2px]';

export const FIO_DO_TOM: Record<TomDoChip, string> = {
  neutro: 'before:bg-border',
  bom: 'before:bg-success',
  verificado: 'before:bg-verified',
  atencao: 'before:bg-warning',
  ruim: 'before:bg-destructive',
  info: 'before:bg-info',
};

/**
 * O fio lateral de 1px de um bloqueador — que **não** é o tom do portão.
 *
 * ⚠️ "Não habilitado nesta versão" não é falha, não é ausência e não é zero: é
 * uma decisão registrada, com dono, data e reversão (`canais.ts:536`). Pintá-la
 * de vermelho de erro diria ao operador que algo quebrou quando alguém apenas
 * ainda não abriu uma porta. Por isso `decidido` é `info` — informação, não
 * veredito — e não `destructive`.
 *
 * ⚠️ `sem_prova` cobre as origens `mensuracao` e `observabilidade`
 * (`canais.ts:508-521`): "depende de medição comprovada antes de gastar". Ele é
 * `destructive` porque é EXATAMENTE a mesma classe de bloqueio que o painel
 * irmão já pintava de vermelho em `PainelDaMensuracao.tsx:231-241` — a
 * discordância entre violeta aqui e rosa lá era mais um caso do defeito que a
 * unificação de vocabulário existe para fechar.
 */
export const FIO_DO_BLOQUEIO: Record<TomDoBloqueio, string> = {
  decidido: 'border-l-info',
  permissao: 'border-l-warning',
  ausencia: 'border-l-border',
  sem_prova: 'border-l-destructive',
};

/**
 * O que cada estado de portão de canal AFIRMA, em uma frase.
 *
 * ⚠️ Estas frases moram aqui, e não em `portoesVisual.ts`, porque aquele arquivo
 * é propriedade da Bancada e exporta tom, glifo e palavra — não descrição. O
 * `ChipDeEstado` exige a descrição (`ChipDeEstado.tsx:67-68`) porque `title` não
 * é lido por leitor de tela em toque nem por teclado: sem ela o chip afirma
 * "bloqueado" e some com o motivo justamente para quem mais depende dele.
 *
 * Elas NÃO criam estado novo: são as quatro chaves de `EstadoDePortao` de
 * `lib/trafego/canais.ts:43-47`, e nada além.
 */
export const DESCRICAO_DO_PORTAO_DE_CANAL: Record<EstadoDoCanal, string> = {
  PERMITIDO: 'o servidor declarou que dá para atravessar este portão',
  BLOQUEADO: 'o servidor mediu e a resposta é não, com causa nomeada',
  INDETERMINADO: 'ninguém mediu este portão — não é uma recusa',
  NAO_APLICAVEL: 'a pergunta não cabe neste canal',
};

/**
 * O que cada estado de portão de mensuração AFIRMA, em uma frase.
 *
 * ⚠️ Nenhuma delas contém a palavra "exige": a exigência do portão é outra
 * coisa, aparece só quando o portão NÃO está pronto, e repeti-la dentro do chip
 * de um portão aberto viraria ruído — que é o que
 * `__tests__/painel-da-mensuracao.test.tsx:219-227` cobra.
 */
export const DESCRICAO_DA_MENSURACAO: Record<EstadoDaMensuracao, string> = {
  PRONTO: 'provado com evidência do servidor',
  PARCIAL: 'leitura verdadeira, e não o bastante',
  NAO_PRONTO: 'medido, e a resposta é não',
  INDETERMINADO: 'ninguém leu — não é uma recusa',
  NAO_APLICAVEL: 'a pergunta não cabe aqui',
};
