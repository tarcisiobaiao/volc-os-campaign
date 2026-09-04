/**
 * `/trafego` — o Hub: três perguntas, três abas, uma moldura só.
 *
 *   1. Campanhas     — "o que eu tenho, e em que estado?"   (padrão)
 *   2. Oportunidades — "o que posso anunciar agora?"
 *   3. Atenção       — "o que quer algo de mim hoje?"
 *
 * ## Por que Campanhas é a aba padrão
 *
 * Porque a pergunta que o operador traz ao abrir esta tela é sobre o que já
 * está gastando dinheiro. Abrir em Oportunidades — a tela de hoje — é o que
 * produz o convite ao segundo lançamento do mesmo termo: a lista de funis não
 * sabe o que já foi ao ar, então ela oferece "montar campanha" para algo que
 * já está no ar.
 *
 * ## Por que o contador vive no rótulo da aba
 *
 * Uma faixa de números grandes no topo consome a primeira olhada com um
 * agregado que ninguém pediu, e empurra o dado real para baixo da dobra. No
 * rótulo, o número é navegação: diz para onde ir, não finge ser resultado.
 *
 * ## Contador ausente ≠ contador zero
 *
 * Enquanto a leitura não chega, a aba não mostra número nenhum. Mostrar `0`
 * seria afirmar "não há nada", que é exatamente o que ainda não se sabe.
 *
 * ## O cabeçalho é o que mais se olha, e por isso ele fica parado
 *
 * Título, barra de situação, abas e largura do conteúdo não se mexem ao trocar
 * de aba. Conteúdo que salta entre abas obriga o olho a reencontrar a interface
 * a cada clique — e numa tela de conferência isso não é incômodo estético: é
 * tempo gasto reencontrando a linha que se estava lendo.
 */
import React from 'react';
import {
  Check,
  CircleAlert,
  CircleHelp,
  Clock,
  Copy,
  FlaskConical,
  RefreshCw,
  TriangleAlert,
  WifiOff,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import { type LeituraDoInventario } from '@/hooks/useInventario';
import { useEstadoDoHub } from '@/hooks/useEstadoDoHub';
import { useLeiturasDoHub } from '@/hooks/useLeiturasDoHub';
import { useNotificacoes } from '@/hooks/useNotificacoes';
import TrafegoPage from '@/pages/trafego/TrafegoPage';
import FilaDeAtencao from '@/components/trafego/inventario/FilaDeAtencao';
import { InventarioDeCampanhas } from '@/components/trafego/inventario/InventarioDeCampanhas';
import { Chip, type Tom } from '@/components/trafego/inventario/Selos';
import { useContadorDeAtencao } from '@/components/trafego/atencao/useAtencao';
import { PainelDeCanais } from '@/components/trafego/canais/PainelDeCanais';
import { EixosDoHub, SeletorDeCanal } from '@/components/trafego/hub/EixosDoHub';
// ⚠️ `EstudioLigado` SAIU DA MOLDURA em 03/09/2026 e o arquivo NÃO foi apagado.
//
// Ele derivava a capacidade de canal no cliente (`canal/jornada.ts`) sobre seis
// canais, sem consultar a janela do canário — e era essa derivação que produzia
// a simetria falsa de Display: `jornada.ts:644` liberava o cockpit porque
// `plataforma.py:373` declara `sabe_criar=True`, enquanto o servidor recusa
// `criavel_pausada` com `fora_da_janela_do_canario`. A aba passou a ler o
// veredito pronto do servidor.
//
// Ele fica como CANDIDATO A REMOÇÃO com evidência registrada, e não como
// exclusão silenciosa: dois testes de segurança varrem o ARQUIVO em busca de
// chamada de mutação (`estudio/__tests__/sem-mutate.test.ts:11` e
// `hub/__tests__/seguranca-hub.test.ts:12`), e apagá-lo junto com uma mudança
// funcional ampla misturaria dois lotes que precisam poder ser revertidos
// separadamente.
import { MetaNaoConfigurada } from '@/components/trafego/hub/MetaNaoConfigurada';
import { totaisHistoricas, totaisOperacionais } from '@/components/trafego/hub/adaptacao';
import type { AbaDoHub } from '@/components/trafego/hub/contrato';
import type { FiltrosDoInventario } from '@/types/trafego';
import {
  ehFrescorConhecido,
  horaExata,
  lidoHa,
} from '@/components/trafego/inventario/formato';

/** @deprecated use AbaDoHub. Mantido para testes que importam ABAS. */
export const ABAS = ['campanhas', 'preparar', 'atencao'] as const;
export type Aba = AbaDoHub;

export interface PropsDoHub {
  /**
   * Conteúdo da aba Oportunidades, JÁ SEM CABEÇALHO DE PÁGINA.
   *
   * ⚠️ Injetável de propósito, e o padrão é o caso degradado — não o normal.
   * O quadro de funis vive em `TrafegoPage`, que já montou o próprio cabeçalho
   * de página. Quando o Hub cai no padrão e a página injetada traz `<h1>`, o
   * operador vê o título "Tráfego" duas vezes na mesma tela: uma acima das
   * abas, outra abaixo. Para quem usa leitor de tela é pior que redundância
   * visual — são dois `<h1>`, ou seja, dois títulos de página numa página só, e
   * a estrutura do documento deixa de dizer onde ele está.
   *
   * Enquanto o corpo daquela página não for extraído, o integrador passa aqui
   * o conteúdo já sem moldura, e o Hub volta a ser o dono único do cabeçalho.
   */
  oportunidades?: React.ReactNode;
  /** Quantos funis estão prontos. `null` enquanto não se sabe. */
  contadorDeOportunidades?: number | null;
}

const RotuloDaAba: React.FC<{ texto: string; contador?: number | null }> = ({
  texto,
  contador,
}) => (
  <span className="flex items-baseline gap-1.5">
    {texto}
    {contador != null && (
      <span className="tabular text-[11px] font-normal text-muted-foreground">{contador}</span>
    )}
  </span>
);

/**
 * ⚠️ ABAS SEGMENTADAS, e não sublinhado.
 *
 * `design.md` §Surfaces é explícito: "**Segmented tabs**, not underlines" e
 * "Never recreate a third tab style (underline, contained pills outside the
 * well, equal-weight bars)". O Hub neutralizava o primitivo — `TabsList` com
 * `bg-transparent p-0 rounded-none border-b` e gatilho com
 * `data-[state=active]:border-primary` — e desenhava justamente o sublinhado
 * que o contrato proíbe. Era a terceira gramática de aba do produto.
 *
 * O poço é `bg-muted` SÓLIDO (não `/60`, senão ele some no canvas) e a pílula
 * selecionada é `bg-card` + `shadow-card`. **Nunca `bg-background`**: esse token
 * É o canvas (`#F3F5F7`), e a pílula pintada com ele mede 1,025:1 contra o poço
 * — indistinguível. Essa correção já foi feita no primitivo
 * (`src/components/ui/tabs.tsx:42`) depois de uma revisão adversarial; o Hub a
 * desfazia por cima.
 */
const gatilho = cn(
  'rounded-sm px-3 py-1.5 text-sm font-medium',
  'min-h-9 text-muted-foreground',
  'data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-card',
  'transition-[background-color,color] duration-[180ms]',
  'focus-visible:ring-offset-1',
);

// ── a barra de situação ─────────────────────────────────────────────────────

/**
 * O estado da sincronização do CONJUNTO — e por que ele não reusa o selo da
 * conta.
 *
 * ⚠️ O vocabulário de frescor de `formato.tsx` é escrito no singular da CONTA:
 * "a última tentativa de ler ESTA CONTA não deu certo". Colado no cabeçalho,
 * onde o assunto é o inventário inteiro, ele passa a descrever um objeto que
 * não existe ali — o operador lê "esta conta" olhando para uma tela que fala de
 * quatro. Aqui o mesmo eixo é dito no escopo certo, com glifo, palavra e
 * descrição, que é a regra que nenhum estado desta tela pode furar.
 *
 * A ordem das perguntas não é estética: primeiro o que compromete a confiança
 * no que vem abaixo (não consegui ler, falhou, não reconheço o estado), depois
 * o que a limita (parcial, antiga), e só então o caso normal.
 */
export interface SituacaoDoConjunto {
  palavra: string;
  descricao: string;
  tom: Tom;
  glifo: React.ComponentType<{ className?: string }>;
}

export function situacaoDoConjunto(leitura: LeituraDoInventario): SituacaoDoConjunto {
  const { inventario } = leitura;

  if (!inventario) {
    return leitura.falhou
      ? {
          palavra: 'não consegui ler',
          descricao:
            'a leitura do registro não voltou, e não há leitura boa anterior guardada nesta sessão',
          tom: 'ruim',
          glifo: WifiOff,
        }
      : {
          palavra: 'lendo o registro',
          descricao: 'a primeira leitura desta sessão ainda está em curso',
          tom: 'neutro',
          glifo: Clock,
        };
  }

  if (leitura.falhou) {
    return {
      palavra: 'atualização falhou',
      descricao:
        'a tentativa mais recente não voltou; o que está na tela é a última leitura boa',
      tom: 'ruim',
      glifo: WifiOff,
    };
  }

  if (!ehFrescorConhecido(inventario.frescor)) {
    return {
      palavra: 'leitura não reconhecida',
      descricao:
        `o servidor descreveu esta leitura como "${inventario.frescor}", que esta versão da tela ` +
        'não conhece — trate os números abaixo como de idade desconhecida',
      tom: 'atencao',
      glifo: CircleAlert,
    };
  }

  if (inventario.parcial) {
    return {
      palavra: 'leitura parcial',
      descricao: 'parte das contas não pôde ser lida nesta leitura',
      tom: 'atencao',
      glifo: TriangleAlert,
    };
  }

  if (inventario.frescor === 'velho') {
    return {
      palavra: 'leitura antiga',
      descricao: 'a última leitura boa já tem idade — confira antes de decidir gasto',
      tom: 'atencao',
      glifo: Clock,
    };
  }

  if (inventario.frescor === 'nunca_lido') {
    return {
      palavra: 'nunca lido',
      descricao:
        'nenhuma conta deste inventário foi lida ainda — o que não é o mesmo que estar vazio',
      tom: 'atencao',
      glifo: CircleHelp,
    };
  }

  return {
    palavra: 'registro lido',
    descricao: 'a leitura mais recente do registro voltou inteira',
    tom: 'neutro',
    glifo: Clock,
  };
}

/**
 * O detalhe que acompanha o estado: quantas contas, ou quantas faltaram.
 *
 * ⚠️ Nenhum ramo aqui devolve silêncio. Ausência de frase, numa tela cuja
 * promessa é procedência, lê-se como "está tudo bem" — e "ainda não sei" e
 * "está tudo bem" levam a decisões opostas quando o que vem a seguir é gasto.
 */
export function fraseDaSituacao(leitura: LeituraDoInventario): string {
  const { inventario } = leitura;

  if (!inventario) {
    return leitura.falhou
      ? 'nenhuma conta pôde ser mostrada nesta tentativa'
      : 'ainda não há o que mostrar — e isso é diferente de não haver campanha';
  }

  if (inventario.parcial) {
    // Contas distintas, não linhas de motivo: a mesma conta pode falhar em dois
    // escopos e virar duas entradas, e dizer "2 contas não responderam" quando
    // foi uma só é errar o tamanho do problema para mais.
    const contas = new Set(inventario.faltou.map((f) => f.customer_id ?? 'sem conta identificada'));
    const quantas = contas.size;
    return quantas === 1
      ? '1 conta não pôde ser lida nesta leitura — o que ela tinha antes continua abaixo'
      : `${quantas} contas não puderam ser lidas nesta leitura — o que elas tinham antes continua abaixo`;
  }

  const contas = inventario.totais.contas;
  return contas === 1 ? '1 conta neste inventário' : `${contas} contas neste inventário`;
}

/** Um código curto para o operador citar ao pedir ajuda sobre ESTA falha. */
function novoCodigoDeOcorrencia(): string {
  const sufixo = Math.random().toString(36).slice(2, 6).toUpperCase();
  const minuto = Math.floor(Date.now() / 1000)
    .toString(36)
    .toUpperCase();
  return `TRF-${minuto}-${sufixo}`;
}

/**
 * A falha da atualização geral, dita em operação e com uma referência copiável.
 *
 * ⚠️ O detalhe técnico NÃO vem para cá. A mensagem crua do servidor fala de
 * rota, status e biblioteca — vocabulário que não ajuda quem está decidindo se
 * mexe numa campanha, e que ainda pode carregar endereço interno. O que o
 * operador precisa é de uma frase curta e de algo que ele possa copiar e colar
 * numa mensagem para quem cuida do sistema.
 *
 * O código é gerado AQUI, nesta tela, e a frase diz isso: ele marca a
 * ocorrência para quem for procurar, junto com o instante exato. Um código que
 * fingisse vir do servidor prometeria uma busca que ninguém pode fazer.
 */
const FalhaDaAtualizacao: React.FC<{ codigo: string; quando: string | null }> = ({
  codigo,
  quando,
}) => {
  const [copiado, setCopiado] = React.useState(false);
  const referencia = quando ? `${codigo} · ${quando}` : codigo;

  const copiar = React.useCallback(() => {
    // `navigator.clipboard` não existe em todo contexto (e em nenhum que não
    // seja seguro). Quando falta, o código continua na tela e selecionável — o
    // botão é o atalho, nunca o único caminho.
    void navigator.clipboard
      ?.writeText(referencia)
      .then(() => setCopiado(true))
      .catch(() => setCopiado(false));
  }, [referencia]);

  return (
    <div
      className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border pt-2"
      role="status"
    >
      <p className="text-[12px] leading-snug">
        Não consegui atualizar agora. O que está na tela continua sendo a última leitura boa.
      </p>
      <span className="flex items-center gap-1.5">
        <span className="text-[11px] text-muted-foreground">código desta ocorrência</span>
        <code className="tabular select-all rounded-sm border border-border bg-muted/60 px-1.5 py-0.5 text-[11px]">
          {referencia}
        </code>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-11 gap-1 px-2 text-[11px] md:h-8"
          onClick={copiar}
        >
          {copiado ? (
            <Check className="h-3 w-3" aria-hidden />
          ) : (
            <Copy className="h-3 w-3" aria-hidden />
          )}
          {copiado ? 'copiado' : 'copiar'}
        </Button>
      </span>
    </div>
  );
};

/**
 * Quando foi lido, como está a sincronização, e a única ação global da moldura.
 *
 * ⚠️ **Isto era um bloco de 3 linhas abaixo do título e virou uma linha no alto.**
 *
 * Medido em 27/08/2026 no navegador autenticado: o cabeçalho do Hub terminava em
 * y=546px numa viewport de 900px, e a primeira campanha da conta Crédito Up
 * começava em y=1798px — duas telas de rolagem. O `DESIGN.md` pede que o
 * cabeçalho caiba em 220–280px "so the first operational content remains visible
 * without scrolling", e a SPEC §6.0 põe frescor e ação na MESMA linha do eyebrow.
 *
 * O que saiu do fluxo vertical: o parágrafo de 3 linhas alinhado à direita que
 * explicava a ação. Ele NÃO foi apagado — continua no DOM, ligado ao botão por
 * `aria-describedby`, e ganhou um resumo visível de uma linha. Quem usa leitor
 * de tela ouve a explicação inteira; quem enxerga lê a metade que tira o medo de
 * clicar ("não altera nenhuma campanha") sem pagar 60px por ela.
 *
 * Fica FORA do bloco de título de propósito. O título pode ser cedido para a
 * página injetada (ver `PropsDoHub.oportunidades`); a idade do dado, não — some
 * o cabeçalho e some junto a resposta para "quando isso foi lido?", que é a
 * pergunta que decide se o operador confia no resto.
 */
const FaixaDeSituacao: React.FC<{
  leitura: LeituraDoInventario;
  aoAtualizar: () => void;
  ocupado: boolean;
}> = ({ leitura, aoAtualizar, ocupado }) => {
  const { inventario } = leitura;
  const situacao = situacaoDoConjunto(leitura);
  const [ocorrencia, setOcorrencia] = React.useState<{ codigo: string; quando: string | null } | null>(
    null,
  );
  const falhouAntes = React.useRef(false);

  React.useEffect(() => {
    if (leitura.falhou && !falhouAntes.current) {
      setOcorrencia({
        codigo: novoCodigoDeOcorrencia(),
        quando: horaExata(new Date().toISOString()),
      });
    }
    if (!leitura.falhou) setOcorrencia(null);
    falhouAntes.current = leitura.falhou;
  }, [leitura.falhou]);

  return (
    <>
      <div className="flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-1.5">
        {/* A idade do que está na tela e o estado da leitura, lado a lado:
            "lido há 6 min" sem o estado não diz se aquela leitura voltou
            inteira, e o estado sem a idade não diz se ainda vale. */}
        <Chip
          glifo={situacao.glifo}
          palavra={situacao.palavra}
          descricao={situacao.descricao}
          tom={situacao.tom}
        />
        {inventario && (
          <span className="tabular text-[12px] leading-none text-muted-foreground">
            {lidoHa(inventario.leitura?.idade_s ?? null)}
          </span>
        )}

        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-11 gap-2 px-3 text-xs md:h-8"
          disabled={ocupado}
          aria-busy={ocupado || undefined}
          aria-describedby="o-que-faz-atualizar"
          onClick={aoAtualizar}
        >
          <RefreshCw
            className={cn('h-3 w-3', ocupado && 'animate-spin motion-reduce:animate-none')}
            aria-hidden
          />
          {ocupado ? 'atualizando…' : 'Atualizar dados'}
        </Button>
      </div>

      {/* ⚠️ UMA frase, VISÍVEL, e é ela que o botão descreve.
          Achado por revisão adversarial: havia um `span.sr-only` com a
          explicação longa MAIS um resumo visível. Quem usa leitor de tela ouvia
          o mesmo fato TRÊS vezes — como descrição do botão, de novo como texto
          estático (o `sr-only` não é `aria-hidden`), e ainda o resumo visível.
          Agora o `aria-describedby` aponta para o parágrafo que todos leem, e
          ele diz as duas metades: o custo e o que a ação NÃO faz. */}
      {/* ⚠️ Estes dois parágrafos são ITENS FLEX do contêiner que os envolve
          (`FaixaDeSituacao` devolve um fragmento). Soltos, eles disputavam a
          linha com o botão "Atualizar dados" dentro de um pai `shrink-0` — e
          como o pai não podia encolher, a frase saía pela direita da viewport
          e era cortada. Medido a 1440px: a frase terminava fora da tela.

          Envelopados num item `w-full`, o `flex-wrap` do pai os joga para a
          própria linha, e `min-w-0` devolve a eles o direito de quebrar. */}
      <div className="w-full min-w-0">
        <p
          id="o-que-faz-atualizar"
          className="mt-1 text-right text-[11px] leading-snug text-muted-foreground"
        >
          relê todas as contas e pode levar alguns instantes · não altera nenhuma campanha
        </p>

        <p className="mt-1 text-right text-[11px] leading-snug text-muted-foreground">
          {fraseDaSituacao(leitura)}
        </p>
      </div>

      {ocorrencia && <FalhaDaAtualizacao codigo={ocorrencia.codigo} quando={ocorrencia.quando} />}
    </>
  );
};

const HubDeTrafegoPage: React.FC<PropsDoHub> = ({
  oportunidades,
  contadorDeOportunidades = null,
}) => {
  // ⚠️ O recorte mora na URL, e é a PÁGINA que o guarda — não o inventário.
  // Rede, tarefa, canal e nível são eixos distintos; busca/conta/estado/
  // atenção continuam na barra. Limpar a barra não apaga o canal.
  const { estado, aplicar } = useEstadoDoHub();
  const leituras = useLeiturasDoHub(estado);
  const { recorte, consulta, consultaHistorico } = leituras;

  const aplicarRecorte = React.useCallback((proximos: FiltrosDoInventario) => {
    aplicar({ filtros: proximos });
  }, [aplicar]);

  const contadorDeAtencao = useContadorDeAtencao();
  const foco = estado.foco;
  const aba: Aba = estado.aba;

  const trocarAba = React.useCallback(
    (valor: string) => {
      const proxima = valor === 'oportunidades' ? 'preparar' : valor;
      aplicar({ aba: proxima as Aba, foco: proxima === 'atencao' ? estado.foco : null });
    },
    [aplicar, estado.foco],
  );

  const inventario = leituras.situacao;
  const operacional = leituras.operacional;
  const notificacoes = useNotificacoes();

  const atualizarTudo = React.useCallback(() => {
    leituras.recarregar();
    void notificacoes.refetch();
  }, [leituras, notificacoes]);

  /**
   * Quem é dono do TÍTULO desta tela.
   *
   * Só existe UM título de página, e ele pertence ao Hub — exceto quando o Hub
   * não recebeu o conteúdo de Oportunidades e precisa montar `TrafegoPage`
   * inteira. Se aquela página trouxer o cabeçalho dela, renderizar os dois
   * produziria dois `<h1>Tráfego</h1>` empilhados, e o operador leria o mesmo
   * título duas vezes com as abas no meio.
   *
   * Ceder é a degradação menos ruim das duas, não uma boa. O preço ficou menor
   * desde que a barra de situação saiu do bloco de título: hoje o que se perde
   * ao ceder é só o título, e não mais a resposta para "quando isso foi lido?".
   */
  const tituloEhDoHub = aba !== 'preparar' || oportunidades != null;
  const google = estado.rede === 'google';

  return (
    <Layout>
      <div className="overflow-x-clip p-4 md:p-8">
        {/* ── O CABEÇALHO, EM ORÇAMENTO DE ALTURA ─────────────────────────
            Medido antes: as abas terminavam em y=546px e a primeira campanha da
            Crédito Up começava em y=1798px, numa viewport de 900px. O DESIGN.md
            fixa 220–280px para que a primeira linha operacional continue
            visível sem rolar, e a SPEC §6.0 desenha a composição: eyebrow e
            frescor na MESMA linha, título, uma frase, rede, e as tarefas na
            borda de baixo.

            O que saiu daqui: a faixa "CANAL" de largura inteira, que empatava
            visualmente com "REDE" e com as abas — três barras equivalentes é
            exatamente o que a SPEC §5 proíbe. Canal desceu para a linha de
            filtros, onde ele é o que sempre foi: um recorte do inventário. */}
        <header className="border-b border-border pb-0">
          <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
            <div className="min-w-0">
              {tituloEhDoHub && (
                <>
                  <div className="kicker">compra de tráfego</div>
                  <h1 className="mt-0.5 text-balance font-display text-[28px] font-bold leading-tight tracking-tight md:text-[32px]">
                    Tráfego
                  </h1>
                </>
              )}
            </div>

            {/* Era `shrink-0`. Com isso a coluna se recusava a encolher, e a
                frase longa da faixa de situação empurrava a largura do bloco
                para 2218px numa viewport de 1440 — saindo pela direita e sendo
                cortada. `min-w-0` + `flex-1` devolvem o direito de encolher; os
                botões não colapsam porque têm `min-h-11 px-4` e `whitespace-nowrap`
                próprios. */}
            <div className="flex min-w-0 flex-1 flex-wrap items-start justify-end gap-3">
              {google && (
                <Button
                  type="button"
                  className="min-h-11 px-4 font-semibold shadow-sm"
                  onClick={() => aplicar({ aba: 'criar' })}
                >
                  Nova campanha
                </Button>
              )}
              <FaixaDeSituacao
                leitura={inventario}
                aoAtualizar={atualizarTudo}
                ocupado={inventario.atualizando || notificacoes.isFetching}
              />
            </div>
          </div>

          {tituloEhDoHub && (
            <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1.5">
              <p className="max-w-[70ch] text-pretty text-[13px] leading-snug text-muted-foreground">
                Controle campanhas, criação e decisões de mídia com evidência da conta. Todo
                número traz a hora em que foi lido.
              </p>
              <Link
                to="/trafego/laboratorio/inteligencia/new-no-delivery"
                className="inline-flex min-h-11 items-center gap-1.5 text-[11px] font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:min-h-8"
              >
                <FlaskConical className="h-3 w-3" aria-hidden />
                laboratório de decisão
              </Link>
            </div>
          )}

          {/* Rede define o ECOSSISTEMA — some quando não há segunda rede a
              escolher, e nunca ganha uma faixa própria de largura inteira. */}
          <div className="mt-3">
            <EixosDoHub
              rede={estado.rede}
              canal={estado.canal}
              nivel={estado.nivel}
              aoMudarRede={(rede) => aplicar({ rede })}
              aoMudarCanal={(canal) => aplicar({ canal })}
              aoMudarNivel={(nivel) => aplicar({ nivel })}
              mostrarCanal={false}
            />
          </div>
        </header>

        <Tabs value={aba} onValueChange={trocarAba} className="mt-0">
          <TabsList
            aria-label="seções do tráfego"
            className="h-auto w-full justify-start gap-1 rounded-lg border border-border bg-muted p-1"
          >
            <TabsTrigger value="campanhas" className={gatilho}>
              <RotuloDaAba
                texto="campanhas"
                contador={google ? totaisOperacionais(operacional.inventario?.totais) : null}
              />
            </TabsTrigger>
            <TabsTrigger value="preparar" className={gatilho}>
              <RotuloDaAba texto="preparar" contador={contadorDeOportunidades} />
            </TabsTrigger>
            <TabsTrigger value="criar" className={gatilho}>
              {/* Sem contador: "quantas campanhas dá para criar" não é um
                  número que exista. Um contador aqui teria de inventar um. */}
              <RotuloDaAba texto="criar" />
            </TabsTrigger>
            <TabsTrigger value="atencao" className={gatilho}>
              <RotuloDaAba
                texto="atenção"
                // ⚠️ O contador da aba vem da MESMA projeção que a fila e o
                // sino usam, e não de `alertas.length`. Aquele número contava
                // só os avisos de entrega; a fila mostra doze sintomas, então
                // o rótulo dizia "3" ao lado de uma lista com sete linhas — e
                // um contador que não bate com o que a aba mostra ensina o
                // operador a não confiar em contador nenhum.
                contador={contadorDeAtencao}
              />
            </TabsTrigger>
          </TabsList>

          <TabsContent value="campanhas" className="mt-6">
            {google ? (
              <>
                {/* Canal vive AQUI, e não no cabeçalho: ele recorta o
                    inventário desta aba, então pertence à linha de recorte. */}
                <div className="mb-3">
                  <SeletorDeCanal
                    valor={estado.canal}
                    aoMudar={(canal) => aplicar({ canal })}
                  />
                </div>
                <InventarioDeCampanhas
                recorte={recorte}
                consulta={consulta}
                aoMudarRecorte={aplicarRecorte}
                fraseOperacional
                situacao={leituras.situacao}
                operacional={leituras.operacional}
                universoFiltros={leituras.universoFiltros}
                leituraHistorico={leituras.historico}
                historico={{
                  aberto: estado.historico,
                  quantidade: totaisHistoricas(operacional.inventario?.totais),
                  consulta: consultaHistorico,
                  aoAbrir: () => aplicar({ historico: true }),
                  aoFechar: () => aplicar({ historico: false }),
                }}
                />
              </>
            ) : (
              <MetaNaoConfigurada nivel={estado.nivel} />
            )}
          </TabsContent>

          {/* ⚠️ `[&>div]:p-0` neutraliza o recuo que `TrafegoPage` herdou de
              quando era uma rota inteira (`p-4 md:p-8` no próprio corpo).
              Somado ao recuo do Hub, o quadro de funis ficava mais estreito e
              mais baixo que as outras duas abas — e a largura do conteúdo
              mudando a cada clique de aba é exatamente o salto que esta tela não
              pode ter. Quem manda no recuo é a moldura, uma vez só.

              O seletor some sozinho no dia em que aquela página deixar de trazer
              recuo próprio; enquanto ela trouxer, é aqui que a moldura se
              defende. */}
          <TabsContent value="preparar" className="mt-6 [&>div]:p-0">
            {google ? (oportunidades ?? <TrafegoPage />) : <MetaNaoConfigurada nivel={estado.nivel} />}
          </TabsContent>

          {/* ⚠️ A ANTESSALA MULTICANAL — uma aba só, e ela lê o SERVIDOR.
              Ver o comentário de `AbaDoHub` em `hub/contrato.ts`: esta aba e a
              extinta `canais` respondiam à mesma pergunta de fontes diferentes,
              e a derivação no cliente produzia simetria falsa em Display.

              ⚠️ O painel busca os PRÓPRIOS dados, e só quando esta aba é aberta.
              Buscá-los na moldura faria toda visita ao Hub pagar uma leitura que
              só esta aba usa. */}
          <TabsContent value="criar" className="mt-6">
            {google ? <PainelDeCanais /> : <MetaNaoConfigurada nivel={estado.nivel} />}
          </TabsContent>

          <TabsContent value="atencao" className="mt-6">
            {google ? <FilaDeAtencao foco={foco} /> : <MetaNaoConfigurada nivel={estado.nivel} />}
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
};

export default HubDeTrafegoPage;
