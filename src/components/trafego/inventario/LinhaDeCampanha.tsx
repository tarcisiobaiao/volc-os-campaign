/**
 * A linha do inventário — a unidade de leitura desta tela.
 *
 * ## Duas marcações, um conteúdo
 *
 * No monitor a linha é uma linha de TABELA, porque a pergunta ali é
 * comparativa: "qual delas está gastando?" só se responde com colunas
 * alinhadas. No telefone a mesma campanha vira um bloco alto com rótulo ao
 * lado de cada valor, porque tabela de onze colunas em 380 px vira arrasto
 * lateral — e ninguém compara custo arrastando.
 *
 * O que NÃO muda entre as duas: nenhum campo desaparece. Na largura do meio as
 * colunas se FUNDEM (compra num bloco, entrega noutro); nunca se cortam.
 *
 * ## Onde cada fato mora, e por quê
 *
 * A tabela ampla dá coluna própria ao que se COMPARA de uma linha para a outra
 * — estado, canal, estratégia, os três valores de compra, os três de entrega e
 * a idade da medida. Estado e canal saíram de dentro da célula do nome por um
 * motivo de leitura, não de arrumação: dentro do nome eles começam num ponto
 * diferente em cada linha, e procurar "quais estão pausadas" numa lista de
 * quarenta campanhas vira leitura palavra por palavra. Em coluna, é uma descida
 * de olho só.
 *
 * O que qualifica a linha em vez de compará-la — procedência e vínculo — fica
 * colado ao nome, que é a identidade da campanha. O resto (identificação
 * externa, linhagem, ressalvas, para onde ir) abre embaixo, na expansão.
 *
 * ## O que a linha se recusa a fazer
 *
 * Não sugere lance, não recomenda verba, não conclui que a campanha "sumiu".
 * Ela mostra o que foi lido, quando foi lido, e o nome do estado observado.
 * Qualquer frase além disso seria diagnóstico — e diagnóstico sem sensor é
 * exatamente o defeito que este módulo existe para não repetir.
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, ChevronDown, ChevronRight, Gauge, TriangleAlert } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import type { CampanhaNoInventario, Leitura } from '@/types/trafego';
import { IdentidadeDeCanal } from '@/components/trafego/hub/IdentidadeDeCanal';

import {
  AUSENTE,
  SEM_MOEDA,
  contagem,
  dinheiro,
  horaDeLeitura,
  lidoHa,
  palavraDaEstrategia,
  palavraDaVeiculacao,
  palavraDoCanal,
} from './formato';
import {
  SeloDeEstadoExterno,
  SeloDePresenca,
  procedenciaLegivel,
} from './Selos';

/** Quantas instâncias da mesma intenção o inventário carregado conhece. */
export type ContagemDeLinhagem = Record<string, number>;

/**
 * O que a CONTA sabe e a linha herda.
 *
 * Uma campanha não tem idade própria: ela herda a idade da leitura que a
 * trouxe. Esse fato vive no cabeçalho do grupo, uma vez por conta, para não ser
 * repetido em cada linha — mas quem abre UMA campanha está justamente decidindo
 * se confia naqueles números, e aí a herança precisa estar dita ali, ao alcance
 * do olho, sem obrigar a subir a tela.
 *
 * Opcional porque a linha também é montada isolada (em prova, e em qualquer
 * superfície futura que mostre uma campanha só). Ausente, a expansão
 * simplesmente não afirma nada sobre a conta — o oposto de inventar um valor
 * padrão, que é como uma tela passa a declarar o que ninguém mediu.
 */
export interface HerancaDaConta {
  nome: string;
  /** Já mascarado pelo grupo: a tela de conferência não expõe o id inteiro. */
  identificacaoNaTela: string;
  ultimaLeituraBoa: Leitura | null;
}

export interface PropsDaLinha {
  campanha: CampanhaNoInventario;
  aberta: boolean;
  aoAlternar: () => void;
  /**
   * ⚠️ OBRIGATÓRIA, e era opcional.
   *
   * Sendo opcional, `linhagens?.[id] ?? 1` respondia "1 instância neste
   * inventário" para quem simplesmente não tinha passado o mapa — uma afirmação
   * de contagem construída a partir de nenhuma contagem. É o mesmo defeito que
   * `null` virando `0`, só que em prosa: a tela dizia saber que aquela intenção
   * foi lançada uma vez só, quando o que havia era ausência de dado.
   *
   * Agora quem monta a linha precisa entregar o mapa; e se ainda assim a chave
   * não estiver nele, a linha diz que não contou em vez de chutar um.
   */
  linhagens: ContagemDeLinhagem;
  /** O que a conta desta linha declarou. Ver `HerancaDaConta`. */
  conta?: HerancaDaConta;
}

const idDoDetalhe = (c: CampanhaNoInventario) => `detalhe-${c.volc_campaign_id}`;

// ── peças compartilhadas pelas três formas ──────────────────────────────────

export const Rotulo: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span className="kicker block text-[0.625rem] leading-none">{children}</span>
);

const Valor: React.FC<{ children: React.ReactNode; className?: string; titulo?: string }> = ({
  children,
  className,
  titulo,
}) => (
  <span className={cn('tabular text-sm font-semibold leading-tight text-foreground', className)} title={titulo}>
    {children}
  </span>
);

/**
 * O teto de cliques — e a diferença entre "não deu para calcular" e "não se
 * aplica".
 *
 * ⚠️ O travessão deste módulo significa UMA coisa: não foi possível medir. Com
 * lance automático não há lance fixo para dividir o orçamento, então o teto não
 * é um número que faltou — é um número que não existe. Imprimir `—` nos dois
 * casos faria a mesma marca responder a duas perguntas opostas, e o operador
 * que visse a coluna cheia de travessões concluiria que a leitura está furada
 * quando na verdade está completa.
 */
export function tetoDaCampanha(c: CampanhaNoInventario): { texto: string; explica: string } {
  if (c.teto_de_cliques != null) {
    return {
      texto: contagem(c.teto_de_cliques),
      explica: 'orçamento diário ÷ lance — divisão de dois números que a conta declarou',
    };
  }
  if (c.estrategia && c.estrategia !== 'MANUAL_CPC') {
    return {
      texto: 'não se aplica',
      explica:
        'com lance automático não há lance fixo para dividir o orçamento — ' +
        'qualquer número aqui seria ficção',
    };
  }
  if (c.lance_micros == null || c.verba_diaria_micros == null) {
    return {
      texto: AUSENTE,
      explica: 'falta o lance ou o orçamento desta campanha para calcular o teto',
    };
  }
  // Lance manual, os dois valores na mão, e mesmo assim sem teto: a tela não
  // faz a divisão por conta própria. O teto é responsabilidade de quem lê a
  // conta, e calcular aqui um número que a leitura não trouxe seria inventá-lo
  // com aparência de medido — o defeito exato que este módulo evita.
  return {
    texto: AUSENTE,
    explica: 'o teto não veio nesta leitura, e esta tela não o calcula por conta própria',
  };
}

/** Lance, orçamento e teto. Fundem-se num bloco só quando a largura aperta. */
export const BlocoDeCompra: React.FC<{
  campanha: CampanhaNoInventario;
  comRotulos?: boolean;
}> = ({ campanha: c, comRotulos }) => {
  const moeda = c.entrega.moeda;
  const teto = tetoDaCampanha(c);
  return (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
      <span className="min-w-0">
        {comRotulos && <Rotulo>lance</Rotulo>}
        <Valor>{dinheiro(c.lance_micros, moeda)}</Valor>
      </span>
      <span className="min-w-0">
        {comRotulos && <Rotulo>orçamento diário</Rotulo>}
        <Valor>{dinheiro(c.verba_diaria_micros, moeda)}</Valor>
      </span>
      <span className="min-w-0">
        {comRotulos && <Rotulo>teto estimado</Rotulo>}
        <Valor titulo={teto.explica}>{teto.texto}</Valor>
      </span>
    </div>
  );
};

/**
 * A REGRA A, num lugar só: medida sem data de leitura não é medida.
 *
 * ⚠️ Esta função nasceu porque a regra valia em duas das três formas. O bloco
 * de entrega (telefone e largura do meio) recusava o número sem data; a TABELA
 * AMPLA — a forma padrão no monitor, e a que `useDensidade` devolve quando não
 * há `window` — imprimia impressões, cliques e custo assim mesmo, com a legenda
 * "ainda não medida" logo abaixo. Número na tela e "não medida" embaixo dele,
 * na visão mais usada da tela cuja única promessa é procedência.
 *
 * A decisão de exibir ou recusar mora AQUI, e as três formas consultam a mesma
 * função. Uma regra que depende de cada componente lembrar dela já foi perdida.
 */
export function medidaSemData(c: CampanhaNoInventario): boolean {
  const { entrega } = c;
  const temNumero =
    entrega.impressoes != null || entrega.cliques != null || entrega.custo_micros != null;
  return temNumero && !entrega.leitura;
}

/** O que a tela diz quando chega número sem a hora em que ele foi lido. */
export const SEM_DATA = 'medida sem data de leitura — não exibida';

/** A frase da idade da medida, ou a razão de não haver idade. */
export function frescorDaEntrega(c: CampanhaNoInventario): string {
  if (medidaSemData(c)) return SEM_DATA;
  return c.entrega.leitura ? lidoHa(c.entrega.leitura.idade_s) : 'ainda não medida';
}

/** A recusa de exibir número sem data, dita com glifo e palavra. */
const MedidaRecusada: React.FC<{ className?: string }> = ({ className }) => (
  <p className={cn('flex items-start gap-1 text-[11px] font-medium leading-snug', className)}>
    <TriangleAlert className="mt-px h-3 w-3 shrink-0 text-warning" aria-hidden />
    {SEM_DATA}
  </p>
);

/**
 * Impressões, cliques e custo — sempre colados à data da leitura.
 *
 * Sem a data, um custo de ontem é indistinguível de um custo de agora, e é
 * olhando para ele que alguém decide mexer em dinheiro. Quando o servidor
 * manda número sem data (não deveria), a tela recusa o número em vez de
 * apresentá-lo como atual.
 */
export const BlocoDeEntrega: React.FC<{
  campanha: CampanhaNoInventario;
  comRotulos?: boolean;
}> = ({ campanha: c, comRotulos }) => {
  const { entrega } = c;

  if (medidaSemData(c)) return <MedidaRecusada />;

  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="min-w-0">
          {comRotulos && <Rotulo>impressões</Rotulo>}
          <Valor>{contagem(entrega.impressoes)}</Valor>
        </span>
        <span className="min-w-0">
          {comRotulos && <Rotulo>cliques</Rotulo>}
          <Valor>{contagem(entrega.cliques)}</Valor>
        </span>
        <span className="min-w-0">
          {comRotulos && <Rotulo>custo</Rotulo>}
          <Valor>{dinheiro(entrega.custo_micros, entrega.moeda)}</Valor>
        </span>
      </div>
      <p className="mt-0.5 text-[11px] leading-none text-muted-foreground">
        {frescorDaEntrega(c)}
      </p>
    </div>
  );
};

/**
 * A LINHA DE EVIDÊNCIA — o que qualifica a campanha, em texto e não em chips.
 *
 * ⚠️ **Isto era uma pilha de três chips e virou uma frase.**
 *
 * Medido em 27/08/2026: cada linha do inventário mostrava até três selos
 * arredondados aqui (canal, procedência, vínculo) e mais dois na coluna de
 * estado (estado externo, presença). Cinco etiquetas do mesmo tamanho e do
 * mesmo formato, para fatos de espécies diferentes — de onde a campanha veio,
 * o que o Google diz dela, se alguém já a vinculou.
 *
 * O `DESIGN.md` tem uma regra nomeada para isso, "One Dominant Signal": cada
 * linha tem UM estado primário, e os fatos de apoio nunca competem com ele. E
 * uma proibição explícita: "Do not repeat piles of tags when a single evidence
 * sentence is clearer". A SPEC §7.3 desenha o resultado — chip só para o estado
 * dominante, e a segunda linha concentrando `Google · Search · vínculo
 * pendente` em texto discreto.
 *
 * ⚠️ Cada fato continua num `span` próprio, separado por `·`, e não numa string
 * concatenada. Três razões: leitor de tela pausa entre eles; `getAllByText`
 * continua encontrando o fato exato que as provas cobram; e o dia em que um
 * deles precisar de `title` ou de cor, ele tem onde receber.
 */
export const SelosDaIdentidade: React.FC<{
  campanha: CampanhaNoInventario;
  className?: string;
}> = ({ campanha: c, className }) => {
  const { palavra: procedencia, descricao: oQueEhProcedencia } = procedenciaLegivel(c.procedencia);
  // Vínculo sem confirmação humana não existe — é a mesma regra de domínio que
  // o selo aplicava, dita agora em texto.
  const vinculado = Boolean(c.vinculo?.opportunity_id && c.vinculo?.confirmado_por);

  // ⚠️ CANAL NÃO ENTRA AQUI. Ele tem coluna própria, e repeti-lo na frase punha
  // a mesma palavra duas vezes na mesma linha — o olho lê duas, o leitor de
  // tela ouve duas, e as provas encontravam dois nós para o mesmo fato.
  const fatos: Array<{ chave: string; palavra: string; descricao: string }> = [
    {
      chave: 'rede',
      palavra: 'Google',
      descricao: 'a rede de anúncios em que esta campanha vive',
    },
    { chave: 'procedencia', palavra: procedencia, descricao: oQueEhProcedencia },
    vinculado
      ? {
          chave: 'vinculo',
          palavra: `funil ${c.vinculo?.opportunity_id}`,
          // ⚠️ QUANDO alguém confirmou faz parte do recibo, e ele sumiu do
          // produto inteiro quando esta frase substituiu o `SeloDeVinculo` —
          // que era o único lugar que lia `confirmado_em`. Um vínculo sem data
          // não dá para contestar: "quem" sem "quando" não reconstrói decisão
          // nenhuma. O DESIGN.md pede procedência e recibos preservados por
          // toda a interface.
          descricao: `confirmado por ${c.vinculo?.confirmado_por}${
            horaDeLeitura(c.vinculo?.confirmado_em) ? ` em ${horaDeLeitura(c.vinculo?.confirmado_em)}` : ''
          }`,
        }
      : {
          chave: 'vinculo',
          palavra: 'sem vínculo',
          descricao: 'nenhum funil confirmado por uma pessoa para esta campanha',
        },
  ];

  return (
    <p
      className={cn(
        'flex min-w-0 flex-wrap items-baseline gap-x-1.5 text-[11px] leading-snug text-muted-foreground',
        className,
      )}
    >
      {fatos.map((f, i) => (
        <React.Fragment key={f.chave}>
          {i > 0 && (
            <span aria-hidden className="text-border">
              ·
            </span>
          )}
          {/* ⚠️ A DESCRIÇÃO VIAJA JUNTO, e não só no `title`.
              O `PRODUCT.md` exige que todo estado combine glifo, palavra e
              descrição, e o chip que existia aqui cumpria isso: a palavra
              visível, a frase em `sr-only`. Ao trocar chip por texto eu quase
              deixei a descrição para trás — `title` não é lido por leitor de
              tela em todo contexto e não é encontrável por prova. A frase fica
              no DOM, como o chip fazia. */}
          <span title={`${f.palavra} — ${f.descricao}`}>
            {f.palavra}
            <span className="sr-only"> — {f.descricao}</span>
          </span>
        </React.Fragment>
      ))}
    </p>
  );
};

/**
 * O estado observado: o que o Google declara, se está entregando, e a presença.
 *
 * ⚠️ `presente` NÃO aparece. É o caso normal, e um selo repetido em toda linha
 * saudável treina o olho a ignorar a coluna inteira — inclusive nas duas linhas
 * onde ela diz "não encontrada". Ausência de selo de presença aqui significa
 * "a conta respondeu e a campanha estava lá", que é exatamente o que o selo
 * diria; o que muda é que a exceção volta a ser visível.
 */
export const EstadoDaCampanha: React.FC<{ campanha: CampanhaNoInventario }> = ({ campanha: c }) => {
  // ⚠️ Veiculação idêntica ao estado externo não é dita duas vezes.
  //
  // A conta manda `estado_externo: REMOVED` e `veiculacao: REMOVED` na mesma
  // campanha, e a célula saía "REMOVED / removida / removida" — três linhas
  // para um fato só. Repetição assim treina o olho a parar de ler a célula
  // inteira, inclusive nas linhas em que as duas palavras DIVERGEM — que é
  // justamente quando elas informam alguma coisa ("ENABLED" e "não entrega" na
  // mesma linha é a campanha que está ligada e fora do leilão).
  const repete = c.veiculacao != null && c.veiculacao === c.estado_externo;
  const veiculacao = repete ? null : palavraDaVeiculacao(c.veiculacao);
  return (
    <span className="flex flex-col items-start gap-1">
      <SeloDeEstadoExterno estado={c.estado_externo} />
      {veiculacao && (
        <span className="text-[11px] leading-tight text-muted-foreground">{veiculacao}</span>
      )}
      {c.presenca !== 'presente' && <SeloDePresenca presenca={c.presenca} />}
    </span>
  );
};

/**
 * Um fato da linha, com a fronteira que o separa do anterior.
 *
 * São dois separadores para dois sentidos. O ponto médio é `aria-hidden`
 * porque "ponto médio" lido em voz alta quarenta vezes é ruído; a vírgula é
 * `sr-only` porque um ponto médio a mais no meio de uma tabela densa é sujeira
 * visual. Sem a vírgula, o nome acessível sai emendado —
 * "Maquininha de CartãoENABLEDentregandobusca" — e quem ouve a linha perde a
 * fronteira entre o nome e o estado exatamente onde ela importa.
 *
 * A vírgula fica DENTRO do elemento da palavra, e não solta entre os dois,
 * porque o cálculo do nome acessível apara o espaço de cada nó isolado: solta,
 * ela viraria `,` sem respiro; junto da palavra, o par `, entregando`
 * atravessa inteiro.
 */
const Fato: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <>
    <span aria-hidden>·</span>
    <span>
      <span className="sr-only">, </span>
      {children}
    </span>
  </>
);

/**
 * Nome, estado, veiculação e canal numa coisa só.
 *
 * Continua sendo a forma certa nas larguras em que NÃO há coluna de estado nem
 * de canal — telefone e largura do meio. Ali, o nome é o único lugar onde esses
 * fatos cabem, e cabem junto porque a leitura é bloco a bloco, não coluna a
 * coluna.
 */
const Identidade: React.FC<{ campanha: CampanhaNoInventario }> = ({ campanha: c }) => {
  const veiculacao = palavraDaVeiculacao(c.veiculacao);
  const canal = palavraDoCanal(c.canal);
  return (
    <span className="flex min-w-0 flex-col gap-1">
      <span className="line-clamp-2 break-words text-sm font-semibold leading-snug text-foreground">{c.nome}</span>
      <span className="sr-only">, </span>
      <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-muted-foreground">
        <SeloDeEstadoExterno estado={c.estado_externo} />
        {veiculacao && <Fato>{veiculacao}</Fato>}
        {canal && <Fato>{canal}</Fato>}
      </span>
    </span>
  );
};

/**
 * Só o nome — a forma da tabela ampla, onde estado e canal têm coluna própria.
 *
 * `title` com o nome inteiro porque a coluna tem largura fixa e nomes de
 * campanha real são longos ("BR - Maquininha de Cartão - Teste 2 - Genérico").
 * A expansão repete o nome sem corte, para quem precisa copiar.
 */
const NomeDaCampanha: React.FC<{ campanha: CampanhaNoInventario }> = ({ campanha: c }) => (
  <span className="line-clamp-2 min-w-0 break-words text-sm font-semibold leading-snug text-foreground" title={c.nome}>
    {c.nome}
  </span>
);

const Estrategia: React.FC<{ campanha: CampanhaNoInventario }> = ({ campanha: c }) => (
  <span className="text-sm leading-tight">{palavraDaEstrategia(c.estrategia)}</span>
);

/**
 * O botão que abre a linha. Um só em qualquer forma — e é ele que carrega o
 * `aria-expanded`, para quem navega por teclado saber que ali há mais.
 *
 * ## Por que ele NÃO tem `aria-label`
 *
 * Tinha, e o `aria-label` era uma frase montada à mão com nome, estado,
 * veiculação e canal. O problema não é a frase estar errada: é que
 * `aria-label` SUBSTITUI o nome calculado a partir do conteúdo. Tudo que a
 * linha mostra e a frase não repetia — a descrição do chip de estado ("ligada
 * no Google"), o aviso de estado não lido, a palavra do estado que a tela não
 * reconheceu — sumia para quem usa leitor de tela. Duas fontes para o mesmo
 * rótulo divergem no primeiro dia em que alguém acrescenta um selo e esquece
 * de acrescentá-lo também na frase; e a versão que o leitor de tela ouve é
 * justamente a que ninguém vê para conferir.
 *
 * Agora o nome vem do conteúdo, e o conteúdo carrega os separadores
 * invisíveis que o mantêm legível. O que está na tela é o que se ouve.
 *
 * Na tabela ampla o conteúdo do botão é só o nome da campanha, e é assim que
 * tem de ser: a célula do nome é o `<th scope="row">` da linha, então TODA
 * célula da linha — estado, canal, custo — é anunciada com o nome da campanha
 * na frente. O estado não some do ouvido; ele passa a ser anunciado no lugar em
 * que está, com o rótulo da coluna junto.
 */
const Alternador: React.FC<{
  campanha: CampanhaNoInventario;
  aberta: boolean;
  aoAlternar: () => void;
  children: React.ReactNode;
  className?: string;
}> = ({ campanha, aberta, aoAlternar, children, className }) => {
  const Seta = aberta ? ChevronDown : ChevronRight;
  return (
    <button
      type="button"
      onClick={aoAlternar}
      aria-expanded={aberta}
      aria-controls={idDoDetalhe(campanha)}
      className={cn(
        'flex w-full min-h-11 items-center gap-2 rounded-sm text-left',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
        className,
      )}
    >
      <Seta className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
      {children}
    </button>
  );
};

// ── o detalhe, sempre embutido na própria lista ─────────────────────────────

const Campo: React.FC<{ rotulo: string; children: React.ReactNode }> = ({ rotulo, children }) => (
  <div className="min-w-0">
    <Rotulo>{rotulo}</Rotulo>
    <div className="mt-1 text-[13px] leading-snug">{children}</div>
  </div>
);

/**
 * As ressalvas desta linha — o que o operador precisa saber ANTES de decidir.
 *
 * Cada item nomeia um fato observado e a consequência dele para a decisão.
 * Nenhum item conclui causa: "não encontrada" não vira "foi apagada", e "sem
 * vínculo" não vira "está errada". A lista fica vazia quando não há ressalva
 * nenhuma, e vazia aqui é uma resposta boa — não um espaço a preencher.
 *
 * ⚠️ Só entra aqui o que NÃO tem campo próprio na expansão. Linhagem ausente e
 * painel ausente já são ditos, com a frase inteira, nos campos "linhagem" e
 * "onde continuar" — repeti-los na lista faria o operador ler a mesma falta
 * duas vezes e procurar a segunda achando que é outra.
 */
export function ressalvasDaCampanha(c: CampanhaNoInventario): string[] {
  const ressalvas: string[] = [];

  if (medidaSemData(c)) {
    ressalvas.push(
      'a medida de entrega chegou sem a hora em que foi lida, e por isso não foi exibida',
    );
  } else if (!c.entrega.leitura) {
    ressalvas.push('esta campanha ainda não teve entrega medida');
  }

  if (!c.estado_externo) {
    ressalvas.push('a conta não informou o estado desta campanha nesta leitura');
  }

  if (
    !c.entrega.moeda &&
    (c.lance_micros != null || c.verba_diaria_micros != null || c.entrega.custo_micros != null)
  ) {
    ressalvas.push(
      `os valores em dinheiro vieram sem unidade e aparecem marcados com ${SEM_MOEDA} — ` +
        'assumir real seria inventar a unidade',
    );
  }

  return ressalvas;
}

export const DetalheDaCampanha: React.FC<{
  campanha: CampanhaNoInventario;
  linhagens: ContagemDeLinhagem;
  conta?: HerancaDaConta;
}> = ({ campanha: c, linhagens, conta }) => {
  // `undefined` aqui não é `1`: é "esta linha foi montada sem o inventário em
  // volta e ninguém contou". A distinção existe pelo mesmo motivo que `—`
  // existe no lugar de `0`.
  const instancias = c.campaign_lineage_id ? linhagens[c.campaign_lineage_id] : undefined;
  const ressalvas = ressalvasDaCampanha(c);
  const boa = conta?.ultimaLeituraBoa;

  return (
    <div className="grid gap-4 border-l-2 border-border/60 pl-4 sm:grid-cols-2 lg:grid-cols-3">
      <Campo rotulo="campanha">
        {/* O nome inteiro, sem corte: na tabela a célula é estreita e trunca, e
            é justamente o nome completo que alguém precisa para procurar a
            campanha no painel do Google. */}
        <span className="break-words">{c.nome}</span>
      </Campo>

      <Campo rotulo="identificação">
        <span className="tabular">
          conta {c.externa.customer_id} · campanha {c.externa.campaign_id}
        </span>
        <span className="block text-[11px] text-muted-foreground">
          no nosso registro: {c.volc_campaign_id}
        </span>
      </Campo>

      <Campo rotulo="procedência">
        {/* Repetido aqui de propósito, e não só no selo ao lado do nome: o selo
            dá a palavra, este campo dá a frase inteira do que ela afirma sem
            depender de passar o ponteiro por cima. */}
        <SelosDaIdentidade campanha={c} />
      </Campo>

      <Campo rotulo="presença na conta">
        {/* ⚠️ Aqui a presença aparece SEMPRE, inclusive quando é `presente`.
            Na linha ela só aparece quando é exceção, porque um selo repetido em
            toda linha saudável treina o olho a pular a coluna; mas quem abriu
            esta campanha está conferindo justamente ela, e "a conta respondeu e
            esta campanha estava na resposta" é um fato que ele veio buscar —
            não um silêncio a deduzir. */}
        <SeloDePresenca presenca={c.presenca} />
      </Campo>

      <Campo rotulo="linhagem">
        {c.campaign_lineage_id ? (
          <>
            {instancias == null
              ? 'instâncias não contadas'
              : instancias === 1
                ? '1 instância neste inventário'
                : `${instancias} instâncias neste inventário`}
            <span className="block text-[11px] text-muted-foreground">
              {instancias == null
                ? 'esta linha tem linhagem registrada, mas o inventário desta tela não a contou'
                : 'mesma intenção operacional — testes e relançamentos contam juntos'}
            </span>
          </>
        ) : (
          <>
            sem linhagem registrada
            <span className="block text-[11px] text-muted-foreground">
              não dá para agrupar esta campanha com relançamentos anteriores
            </span>
          </>
        )}
      </Campo>

      <Campo rotulo="vínculo com o funil">
        {c.vinculo?.opportunity_id && c.vinculo?.confirmado_por ? (
          <>
            funil {c.vinculo.opportunity_id}
            {c.vinculo.project_id ? ` · projeto ${c.vinculo.project_id}` : ''}
            <span className="block text-[11px] text-muted-foreground">
              confirmado por {c.vinculo.confirmado_por}
            </span>
          </>
        ) : (
          <>
            sem vínculo
            <span className="block text-[11px] text-muted-foreground">
              nenhuma pessoa confirmou de qual funil esta campanha compra o clique
            </span>
          </>
        )}
      </Campo>

      {/* A herança de frescor, dita onde a decisão acontece. Sem a conta em
          volta o campo não aparece: uma linha isolada não sabe de que leitura
          veio, e afirmar uma seria o mesmo defeito de contar instâncias que
          ninguém contou. */}
      {conta && (
        <Campo rotulo="de onde vem este número">
          {conta.nome} · {conta.identificacaoNaTela}
          <span className="block text-[11px] text-muted-foreground">
            {boa
              ? `última leitura boa desta conta ${horaDeLeitura(boa.lido_em) ?? lidoHa(boa.idade_s)}`
              : 'não há leitura boa anterior guardada para esta conta'}
          </span>
        </Campo>
      )}

      <Campo rotulo="ressalvas">
        {ressalvas.length === 0 ? (
          <span className="text-muted-foreground">
            nenhuma — o que está na linha veio inteiro da última leitura
          </span>
        ) : (
          <ul className="space-y-1">
            {ressalvas.map((r) => (
              <li key={r} className="flex items-start gap-1.5">
                <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0 text-warning" aria-hidden />
                <span className="min-w-0">{r}</span>
              </li>
            ))}
          </ul>
        )}
      </Campo>

      <Campo rotulo="onde continuar">
        <span className="flex flex-wrap items-center gap-3">
          {/* ⚠️ `<Link>`, e não `<a href>`. Os dois endereços são rotas DESTE
              aplicativo — `/trafego/campanhas/:id` e `/dashboard/campaign/:id`,
              esta última montada pelo servidor em `inventario.py`. Uma âncora
              crua faz recarga de documento inteiro: perde o estado da SPA e
              refaz TODAS as leituras do Hub para abrir uma campanha. Era o
              único caminho de entrada da página canônica, e ele cobrava o
              inventário inteiro de novo a cada clique. */}
          <Button asChild className="min-h-11 font-semibold">
            <Link to={`/trafego/campanhas/${c.volc_campaign_id}`}>abrir no Hub</Link>
          </Button>
          {c.cockpit_href ? (
            <Link
              to={c.cockpit_href}
              className="inline-flex min-h-11 items-center gap-1 font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
            >
              <Gauge className="h-3.5 w-3.5" aria-hidden />
              abrir o painel desta campanha
            </Link>
          ) : (
            <span className="text-muted-foreground">
              sem painel próprio — esta campanha ainda não tem endereço interno seguro
            </span>
          )}
          {c.externa.campaign_id && c.externa.customer_id && (
            <a
              href={`https://ads.google.com/aw/campaigns?campaignId=${c.externa.campaign_id}&__c=${c.externa.customer_id}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-11 items-center gap-1 font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
            >
              abrir no Google Ads
              <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
            </a>
          )}
        </span>
      </Campo>
    </div>
  );
};

// ── forma de tabela (monitor e largura do meio) ─────────────────────────────

export const COLUNAS_AMPLAS = [
  'estado',
  'campanha',
  'canal',
  'estratégia',
  'lance',
  'orçamento diário',
  'teto estimado',
  'impressões',
  'cliques',
  'custo',
  'entrega lida',
] as const;

export const COLUNAS_MEDIAS = ['campanha', 'compra', 'entrega', 'situação'] as const;

/**
 * Largura de cada coluna, em porcentagem da tabela.
 *
 * ⚠️ Existem porque a tabela ampla é `table-fixed`, e ela é `table-fixed`
 * porque `auto` deixa a largura mínima ser decidida pelo conteúdo mais longo de
 * cada coluna. Com onze colunas, o nome de uma campanha real e a palavra
 * "maximizar conversões" empurram a soma para além do contêiner — e como esta
 * tela recusa rolagem lateral (comparar custo arrastando já é não conseguir
 * comparar), o que sobra é a tabela vazar da página. Com largura declarada, o
 * conteúdo quebra ou trunca dentro da célula e a página nunca rola de lado.
 *
 * A soma tem de dar 100.
 */
export const LARGURAS_AMPLAS: readonly string[] = [
  // Estado é largo por causa das palavras que ele precisa caber inteiras:
  // "não encontrada" e "sincronização falhou" são justamente as que não podem
  // chegar cortadas, porque são elas que mudam a decisão.
  // ⚠️ Rebalanceadas em 27/08/2026 contra a medição a 1440px.
  //
  // `estado` cedeu 2 pontos: desde que a linha passou a mostrar UM chip
  // dominante em vez de três, ela não precisa mais caber "sincronização falhou"
  // ao lado de mais dois selos. `campanha` recebeu 3: é ela que carrega o nome
  // legível E a linha de evidência ("Google · encontrada na conta · sem
  // vínculo"), que a 18% quebrava em três linhas e esticava a altura da linha
  // inteira. As colunas de número receberam 1 ponto cada, porque "IMPRESSÕES"
  // não cabia em 7% e encostava na vizinha.
  '11%', // estado
  '21%', // campanha
  '7%', // canal
  '8%', // estratégia
  '6%', // lance
  '7%', // orçamento diário
  '6%', // teto estimado
  '8%', // impressões
  '7%', // cliques
  '7%', // custo
  '12%', // entrega lida
];

/**
 * Altura do cabeçalho de coluna, e o deslocamento com que o cabeçalho da conta
 * gruda logo abaixo dele.
 *
 * Os dois andam juntos e por isso moram juntos: são a mesma medida vista de
 * dois lados. Se divergirem, o cabeçalho da conta gruda em cima do cabeçalho de
 * coluna (escondendo os rótulos) ou embaixo dele com uma faixa de fundo no
 * meio — e o defeito só aparece quando alguém rola uma lista longa.
 *
 * `h-12` e não `h-9` porque "orçamento diário" e "teto estimado" não cabem numa
 * linha só na largura que estas colunas têm; abreviá-los seria trocar clareza
 * por altura.
 */
export const ALTURA_DO_CABECALHO_DE_COLUNA = 'h-12';
export const TOPO_ABAIXO_DO_CABECALHO = 'top-12';

const celula = 'px-2 py-2.5 align-top';

/** Superfície da linha: hover e seleção por tinta, nunca por sombra que flutua. */
function classeDaLinha(aberta: boolean) {
  return cn(
    'border-t border-border/70',
    aberta
      ? 'bg-primary/[0.05] [box-shadow:inset_3px_0_0_hsl(var(--primary))]'
      : 'hover:bg-foreground/[0.035]',
  );
}

export const LinhaEmTabela: React.FC<PropsDaLinha & { fundida: boolean }> = ({
  campanha: c,
  aberta,
  aoAlternar,
  linhagens,
  conta,
  fundida,
}) => {
  const colunas = fundida ? COLUNAS_MEDIAS.length : COLUNAS_AMPLAS.length;
  // Uma decisão por linha, aplicada às TRÊS colunas de entrega juntas: elas
  // descrevem a mesma medida, e recusar só uma deixaria as outras duas na tela
  // como se tivessem data. A idade da medida — ou a recusa — fica na última
  // coluna, onde o olho já está quando termina de ler a linha.
  //
  // Lance, orçamento e teto não passam por aqui: são o que a conta declara, não
  // o que ela mediu, e a idade deles é a da leitura da conta — que vive no
  // cabeçalho do grupo, uma vez por conta, em vez de repetida em cada linha.
  const semData = medidaSemData(c);
  const teto = tetoDaCampanha(c);

  const detalhe = aberta && (
    <tr id={idDoDetalhe(c)} className="bg-muted/30">
      <td colSpan={colunas} className="px-3 pb-4 pt-1">
        <DetalheDaCampanha campanha={c} linhagens={linhagens} conta={conta} />
      </td>
    </tr>
  );

  if (fundida) {
    return (
      <>
        <tr className={classeDaLinha(aberta)}>
          <th scope="row" className={cn(celula, 'text-left font-normal')}>
            <Alternador campanha={c} aberta={aberta} aoAlternar={aoAlternar} className="pr-2">
              <Identidade campanha={c} />
            </Alternador>
          </th>
          <td className={celula}>
            <BlocoDeCompra campanha={c} comRotulos />
          </td>
          <td className={celula}>
            <BlocoDeEntrega campanha={c} comRotulos />
          </td>
          <td className={celula}>
            <div className="flex flex-wrap items-center gap-1.5">
              <SelosDaIdentidade campanha={c} />
              {c.presenca !== 'presente' && <SeloDePresenca presenca={c.presenca} />}
            </div>
          </td>
        </tr>
        {detalhe}
      </>
    );
  }

  return (
    <>
      <tr className={classeDaLinha(aberta)}>
        <td className={celula}>
          <EstadoDaCampanha campanha={c} />
        </td>

        {/* `th scope="row"`: é o nome da campanha que dá contexto a todas as
            outras células da linha. Com ele, o leitor de tela anuncia
            "Maquininha de Cartão, custo, R$ 0,00" em vez de "R$ 0,00" solto no
            meio de onze colunas. */}
        <th scope="row" className={cn(celula, 'text-left font-normal')}>
          <Alternador campanha={c} aberta={aberta} aoAlternar={aoAlternar} className="pr-1">
            <NomeDaCampanha campanha={c} />
          </Alternador>
          <SelosDaIdentidade campanha={c} className="mt-1 pl-6" />
        </th>

        <td className={celula}>
          <span className="text-sm leading-tight">{palavraDoCanal(c.canal) ?? AUSENTE}</span>
        </td>
        <td className={celula}>
          <Estrategia campanha={c} />
        </td>

        <td className={cn(celula, 'text-right')}>
          <Valor>{dinheiro(c.lance_micros, c.entrega.moeda)}</Valor>
        </td>
        <td className={cn(celula, 'text-right')}>
          <Valor>{dinheiro(c.verba_diaria_micros, c.entrega.moeda)}</Valor>
        </td>
        <td className={cn(celula, 'text-right')}>
          <Valor titulo={teto.explica}>{teto.texto}</Valor>
        </td>

        <td className={cn(celula, 'text-right')}>
          <Valor titulo={semData ? SEM_DATA : undefined}>
            {semData ? AUSENTE : contagem(c.entrega.impressoes)}
          </Valor>
        </td>
        <td className={cn(celula, 'text-right')}>
          <Valor titulo={semData ? SEM_DATA : undefined}>
            {semData ? AUSENTE : contagem(c.entrega.cliques)}
          </Valor>
        </td>
        <td className={cn(celula, 'text-right')}>
          <Valor titulo={semData ? SEM_DATA : undefined}>
            {semData ? AUSENTE : dinheiro(c.entrega.custo_micros, c.entrega.moeda)}
          </Valor>
        </td>

        <td className={celula}>
          {semData ? (
            <MedidaRecusada />
          ) : (
            <span className="text-[11px] leading-snug text-muted-foreground">
              {frescorDaEntrega(c)}
            </span>
          )}
        </td>
      </tr>
      {detalhe}
    </>
  );
};

// ── forma de lista (telefone) ───────────────────────────────────────────────

/**
 * No telefone a ordem é de PRIORIDADE, não a da tabela.
 *
 * Primeiro identidade e estado (o que é, e como está), depois entrega (o que
 * aconteceu com o dinheiro que já saiu), depois compra (o que está configurado)
 * e por último canal, estratégia e os selos de origem. É a ordem em que as
 * perguntas chegam quando alguém confere pelo telefone, e não a ordem em que as
 * colunas cabem num monitor.
 */
export const LinhaEmLista: React.FC<PropsDaLinha> = ({
  campanha: c,
  aberta,
  aoAlternar,
  linhagens,
  conta,
}) => (
  <li className={cn(classeDaLinha(aberta), 'px-3 py-2')}>
    <Alternador campanha={c} aberta={aberta} aoAlternar={aoAlternar}>
      <Identidade campanha={c} />
    </Alternador>

    <div className="mt-2 space-y-3 pl-6">
      <BlocoDeEntrega campanha={c} comRotulos />
      <BlocoDeCompra campanha={c} comRotulos />
      <div>
        <Rotulo>estratégia</Rotulo>
        <div className="mt-1">
          <Estrategia campanha={c} />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <SelosDaIdentidade campanha={c} />
        {c.presenca !== 'presente' && <SeloDePresenca presenca={c.presenca} />}
      </div>
    </div>

    {aberta && (
      <div id={idDoDetalhe(c)} className="mt-3 pl-6">
        <DetalheDaCampanha campanha={c} linhagens={linhagens} conta={conta} />
      </div>
    )}
  </li>
);
