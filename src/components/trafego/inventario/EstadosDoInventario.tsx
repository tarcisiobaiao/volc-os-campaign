/**
 * Carregando, vazio, falhou, parcial e antigo — os cinco jeitos de a tela não
 * ter a resposta inteira.
 *
 * Todos eles são conteúdo, não decoração. Um giro no meio da tela informa que
 * algo acontece e mais nada; o esqueleto informa a FORMA do que vem, e o
 * operador já sabe onde vai olhar quando chegar.
 *
 * O vazio ensina porque um beco sem saída ("nenhum resultado") transfere para
 * o operador a tarefa de adivinhar se o problema é dele, da conta ou nosso.
 *
 * ## A falha não fala a língua da máquina
 *
 * Até esta revisão, `FalhaDoInventario` imprimia o `motivo` do jeito que ele
 * chegasse. Como as mensagens nascem no cliente HTTP e no backend, o que caía
 * ali era coisa como "Endpoint não encontrado (404) em https://…" ou o texto de
 * uma exceção do servidor recortada em 300 caracteres. O operador não tem o que
 * fazer com nenhuma dessas frases — e, o que é pior, sai da tela sem saber nem
 * o que aconteceu nem se pode mexer na campanha.
 *
 * Agora o texto passa por `erros.ts`, que só sabe dizer frases de um
 * vocabulário fechado, e a tela ganha o que faltava para a frase curta não
 * virar um beco sem saída: um CÓDIGO copiável, que é o que liga o que o
 * operador viu ao que ficou registrado do outro lado.
 *
 * ## Hierarquia de títulos
 *
 * Os títulos daqui são `h2`. A página monta um `h1` ("Tráfego") e nada entre
 * ele e este bloco; começar em `h3` pulava um nível, e quem navega por títulos
 * — o atalho mais usado de leitor de tela — perde a noção de onde está quando o
 * nível salta.
 */
import React from 'react';
import { Check, CircleHelp, Copy, Inbox, TriangleAlert, WifiOff } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import type { Faltou } from '@/types/trafego';

import { idade } from './formato';
import {
  type OcorrenciaOperacional,
  ocorrenciaDaFrase,
} from './erros';

/**
 * A tinta secundária destas caixas voltou a ser `--muted-foreground`.
 *
 * Ela tinha sido trocada por `--foreground/75` porque o token reprovava fora
 * do card — e o comentário original registrava a medição e dizia, com todas as
 * letras, que a troca era temporária: valia até `--muted-foreground` ser
 * corrigido em `src/index.css`. O teste `⚠️ registra o achado` existia
 * justamente para FALHAR nesse dia e avisar.
 *
 * Esse dia é agora. `--muted-foreground` foi de 45% para 40% de luminosidade,
 * e a tabela virou:
 *
 * | tinta / fundo                                  | antes  | depois |
 * |------------------------------------------------|--------|--------|
 * | `--muted-foreground` sobre `--card`            | 4,73:1 | 5,45:1 |
 * | `--muted-foreground` sobre `--background`      | 4,52:1 | 5,21:1 |
 * | `--muted-foreground` sobre o painel de falha   | 4,13:1 | 5,02:1 |
 * | `--muted-foreground` sobre o aviso parcial     | 4,12:1 | 4,98:1 |
 * | `--muted-foreground` sobre o aviso de antigo   | 4,23:1 | 5,36:1 |
 *
 * `--foreground/75` sobrava contraste (≥6,9:1), então trocar de volta REDUZ a
 * margem. Achado por revisão adversarial: a tabela acima trazia os números de 42%, um
 * passo intermediário. Ainda assim é a decisão certa: o produto passa a ter um jeito só de
 * escrever texto secundário, em vez de um token e uma exceção que só quem lê
 * este comentário conhece. O contrato é explícito sobre não manter dois
 * vocabulários para a mesma coisa, e 4,57:1 passa a AA com folga real.
 */
const TINTA_SECUNDARIA = 'text-muted-foreground';

/** O esqueleto tem a forma do inventário: cabeçalho de conta e linhas. */
export const EsqueletoDoInventario: React.FC<{ contas?: number; linhas?: number }> = ({
  contas = 2,
  linhas = 3,
}) => (
  <div role="status" aria-live="polite" className="rounded-md border border-border bg-card">
    <span className="sr-only">lendo o inventário das contas</span>
    {Array.from({ length: contas }).map((_, i) => (
      <div key={i} className="border-b border-border last:border-b-0">
        <div className="flex items-center justify-between gap-4 border-b border-border/60 px-3 py-3">
          <div className="space-y-2">
            <Skeleton className="h-4 w-40 motion-reduce:animate-none" />
            <Skeleton className="h-3 w-56 motion-reduce:animate-none" />
          </div>
          <Skeleton className="h-8 w-36 motion-reduce:animate-none" />
        </div>
        {Array.from({ length: linhas }).map((__, j) => (
          <div key={j} className="flex items-center gap-4 border-b border-border/40 px-3 py-3 last:border-b-0">
            <Skeleton className="h-4 w-4 shrink-0 rounded-sm motion-reduce:animate-none" />
            <Skeleton className="h-4 flex-1 motion-reduce:animate-none" />
            <Skeleton className="hidden h-4 w-20 md:block motion-reduce:animate-none" />
            <Skeleton className="hidden h-4 w-20 md:block motion-reduce:animate-none" />
            <Skeleton className="h-4 w-24 motion-reduce:animate-none" />
          </div>
        ))}
      </div>
    ))}
  </div>
);

/** Nenhuma conta no inventário — e o que fazer a respeito. */
export const InventarioVazio: React.FC = () => (
  <div className="rounded-md border border-border bg-card px-4 py-8 text-center">
    <Inbox className="mx-auto h-6 w-6 text-muted-foreground" aria-hidden />
    <h2 className="mt-3 font-display text-base font-semibold">Nenhuma conta no inventário</h2>
    <p className="mx-auto mt-2 max-w-[62ch] text-[13px] leading-relaxed text-muted-foreground">
      Este painel lista o que existe nas contas de anúncio da casa: cada campanha com o
      estado que a conta declara, quanto ela gastou e há quanto tempo esse número foi lido.
      Enquanto nenhuma conta tiver sido lida, não há o que comparar aqui — e ficar vazio
      não significa que as contas estejam vazias.
    </p>
  </div>
);

/** Há campanhas no universo, mas nenhuma neste recorte. */
export const RecorteVazio: React.FC = () => (
  <div className="rounded-md border border-dashed border-border bg-card px-4 py-8 text-center">
    <Inbox className="mx-auto h-6 w-6 text-muted-foreground" aria-hidden />
    <h2 className="mt-3 font-display text-base font-semibold">Nenhum resultado neste recorte</h2>
    <p className="mx-auto mt-2 max-w-[62ch] text-[13px] leading-relaxed text-muted-foreground">
      O registro foi lido, e nenhuma campanha combina com busca, conta, estado ou canal
      escolhidos. Isso é diferente de não conseguir ler: o que falta é o recorte, não a
      leitura. Limpe os filtros ou troque o canal para voltar ao que está no ar.
    </p>
  </div>
);

// ── o código da ocorrência ──────────────────────────────────────────────────

/**
 * Copia para a área de transferência pelo caminho que existir.
 *
 * `navigator.clipboard` não existe em contexto inseguro e pode ser negado por
 * permissão; `execCommand` está obsoleto mas ainda é o único plano B em alguns
 * navegadores. Devolve `false` em vez de lançar porque falhar em copiar não
 * pode derrubar a tela que está justamente relatando uma falha — e porque o
 * operador precisa SABER que não copiou, em vez de colar o que estava antes na
 * área de transferência achando que é o código.
 */
async function escreverNaAreaDeTransferencia(texto: string): Promise<boolean> {
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(texto);
      return true;
    }
  } catch {
    /* segue para o plano B */
  }
  try {
    if (typeof document === 'undefined' || typeof document.execCommand !== 'function') {
      return false;
    }
    const caixa = document.createElement('textarea');
    caixa.value = texto;
    // Fora da tela, mas NÃO `display:none`: elemento sem caixa não pode ser
    // selecionado, e sem seleção não há o que copiar.
    caixa.setAttribute('aria-hidden', 'true');
    caixa.style.position = 'fixed';
    caixa.style.opacity = '0';
    caixa.style.pointerEvents = 'none';
    document.body.appendChild(caixa);
    caixa.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(caixa);
    return ok;
  } catch {
    return false;
  }
}

/** Quanto tempo a confirmação de cópia fica na tela antes de sumir. */
const DURACAO_DO_RECADO_MS = 6000;

/**
 * O código, visível, com botão de copiar.
 *
 * ⚠️ O rótulo do botão NÃO muda para "copiado".
 *
 * É o padrão mais comum e o mais hostil a leitor de tela: trocar o texto do
 * botão troca o NOME ACESSÍVEL dele, e quem estiver com o foco ali ouve o
 * controle mudar de identidade debaixo da mão. A confirmação vive numa região
 * viva ao lado, que é onde uma mudança de estado é anunciada sem que o controle
 * deixe de ser o que era. O glifo acompanha, para quem lê com os olhos.
 *
 * O código também fica SEMPRE visível, e não só dentro do botão: se a cópia
 * falhar — contexto inseguro, permissão negada —, o operador ainda consegue
 * lê-lo e transcrevê-lo. Um botão que é o único caminho para o dado é um beco
 * sem saída disfarçado de conveniência.
 */
export const CodigoDaOcorrencia: React.FC<{ ocorrencia: OcorrenciaOperacional }> = ({
  ocorrencia,
}) => {
  const [recado, setRecado] = React.useState<'parado' | 'copiado' | 'falhou'>('parado');
  const relogio = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(
    () => () => {
      if (relogio.current) clearTimeout(relogio.current);
    },
    [],
  );

  const copiar = React.useCallback(() => {
    void escreverNaAreaDeTransferencia(ocorrencia.paraCopiar).then((ok) => {
      setRecado(ok ? 'copiado' : 'falhou');
      if (relogio.current) clearTimeout(relogio.current);
      relogio.current = setTimeout(() => setRecado('parado'), DURACAO_DO_RECADO_MS);
    });
  }, [ocorrencia]);

  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
        {/* O kicker se anuncia como rótulo pela FORMA — caixa alta, 11 px,
            0,1em de espaçamento. Ele não precisa de tinta apagada para isso, e
            aqui não pode: o fundo é tinta semântica e `--muted-foreground`
            reprova em contraste sobre ela. */}
        <span className={cn('kicker', TINTA_SECUNDARIA)}>código da ocorrência</span>
        {/* `select-all` para quem preferir selecionar; o botão é o caminho
            principal, não o único. */}
        <span className="tabular select-all rounded-sm border border-border bg-muted/50 px-1.5 py-0.5 text-[12px] font-medium">
          {ocorrencia.id}
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-9 gap-1.5 px-3 text-xs"
          onClick={copiar}
        >
          {recado === 'copiado' ? (
            <Check className="h-3 w-3" aria-hidden />
          ) : (
            <Copy className="h-3 w-3" aria-hidden />
          )}
          copiar código
        </Button>
      </div>

      {/* A região existe desde o primeiro render, vazia. Uma região viva criada
          no mesmo instante em que ganha texto costuma não ser anunciada: o
          leitor de tela precisa já estar observando o nó. */}
      <p role="status" className={cn('mt-2 text-[12px] leading-snug', TINTA_SECUNDARIA)}>
        {recado === 'copiado' &&
          'Código copiado. Envie-o junto do que você estava fazendo a quem cuida do sistema.'}
        {recado === 'falhou' &&
          'Não consegui copiar por este navegador. O código está aqui do lado e pode ser selecionado à mão.'}
      </p>
    </div>
  );
};

/**
 * Falhou e não há nada guardado para mostrar no lugar.
 *
 * Aceita a ocorrência pronta (caminho preferido) ou só a frase (caminho de hoje,
 * enquanto o painel passa `motivo`). No segundo caso o texto recebido é tratado
 * como NÃO CONFIÁVEL — se não for uma das frases que esta tela é dona de dizer,
 * ele é descartado inteiro. É o que impede um `detail` do servidor de chegar à
 * tela por dentro de um parâmetro chamado `motivo`.
 */
export const FalhaDoInventario: React.FC<{
  motivo?: string | null;
  ocorrencia?: OcorrenciaOperacional | null;
  aoTentarDeNovo?: () => void;
}> = ({ motivo, ocorrencia, aoTentarDeNovo }) => {
  // Memo pela frase: sem ele o código seria sorteado a cada render e o operador
  // veria um identificador diferente a cada piscada da tela — nenhum deles
  // servindo para achar nada.
  const oc = React.useMemo(
    () => ocorrencia ?? ocorrenciaDaFrase(motivo, 'inventario'),
    [ocorrencia, motivo],
  );

  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/[0.05] px-4 py-6">
      <div className="flex items-start gap-3">
        <WifiOff className="mt-0.5 h-5 w-5 shrink-0 text-destructive" aria-hidden />
        <div className="min-w-0">
          {/* `alert` e não `status`: o operador pediu uma leitura e ela não
              existe. É interrupção legítima — o contrário é ele conferir uma
              tela vazia sem saber que ela está vazia por falha. */}
          <div role="alert">
            <h2 className="font-display text-base font-semibold">
              Não consegui ler o inventário
            </h2>
            <p className="mt-1 max-w-[62ch] text-[13px] font-medium leading-relaxed">
              {oc.mensagem}
            </p>
            <p className={cn('mt-1 max-w-[62ch] text-[13px] leading-relaxed', TINTA_SECUNDARIA)}>
              {oc.proximoPasso}
            </p>
            {oc.complemento && (
              <p className={cn('mt-1 max-w-[62ch] text-[13px] leading-relaxed', TINTA_SECUNDARIA)}>
                {oc.complemento}
              </p>
            )}
            <p className={cn('mt-2 max-w-[62ch] text-[13px] leading-relaxed', TINTA_SECUNDARIA)}>
              O que está nas contas de anúncio não mudou por causa disto — o que faltou foi
              conseguir olhar.
            </p>
          </div>

          <CodigoDaOcorrencia ocorrencia={oc} />

          {aoTentarDeNovo && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-3 h-9 px-3 text-xs"
              onClick={aoTentarDeNovo}
            >
              tentar de novo
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

/**
 * Que PARTE da conta não voltou, no vocabulário desta tela.
 *
 * O mesmo padrão de `presencaLegivel` e `frescorLegivel`: mapa fechado, com
 * frase de reserva para o valor que o servidor ganhar antes deste pacote ser
 * publicado.
 */
const ESCOPO_QUE_FALTOU: Record<string, string> = {
  conta: 'não foi possível ler esta conta por inteiro',
  campanhas: 'não foi possível ler as campanhas desta conta',
  metricas: 'não foi possível ler as medidas desta conta',
};

function parteQueFaltou(escopo: string): string {
  const conhecida = ESCOPO_QUE_FALTOU[escopo];
  if (conhecida) return conhecida;
  // O valor cru só é ecoado se ele PARECER um termo de vocabulário. Um campo
  // curto costuma trazer um termo; se um dia trouxer outra coisa — um trecho de
  // exceção, uma frase de log —, ela não entra na tela por esta porta.
  const parece = /^[a-z_]{1,32}$/.test(escopo);
  return parece
    ? `uma parte desta conta (“${escopo}”) não pôde ser lida`
    : 'uma parte desta conta não pôde ser lida';
}

/**
 * A resposta veio pela metade — e diz exatamente qual metade.
 *
 * Sem esta lista, "parcial" seria um adjetivo: o operador saberia que algo
 * faltou, e não o quê. A falha de uma conta não contamina as outras, mas
 * precisa aparecer com nome.
 *
 * ## ⚠️ Por que o `motivo` do servidor NÃO é impresso
 *
 * `faltou[].motivo` é `str(linha["motivo"] or <frase padrão>)` no backend: uma
 * coluna de texto livre da tentativa de varredura, que pode guardar o que a
 * varredura tiver gravado ali. E a própria frase padrão do servidor diz "o dado
 * abaixo é o último snapshot bom" — ou seja, o vocabulário de máquina já estava
 * chegando à tela por aqui, todos os dias, sem ninguém reparar, porque o
 * caminho parecia inofensivo: é só um campo chamado "motivo".
 *
 * O que a tela precisa dizer está em `escopo`, que é campo estruturado de
 * vocabulário curto — e é ele que passa, traduzido. Se um dia houver motivos
 * que o operador precise distinguir, eles viram código de um vocabulário
 * combinado entre as duas pontas, do mesmo jeito que `frescor` já é.
 */
export const AvisoDeLeituraParcial: React.FC<{ faltou: Faltou[] }> = ({ faltou }) => {
  if (faltou.length === 0) return null;
  return (
    <div
      className="rounded-md border border-warning/40 bg-warning/[0.06] px-4 py-3"
      role="status"
    >
      <div className="flex items-start gap-2">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
        <div className="min-w-0">
          <p className="text-[13px] font-medium">
            Leitura parcial — {faltou.length === 1 ? 'uma parte não voltou' : `${faltou.length} partes não voltaram`}
          </p>
          <ul className={cn('mt-1 space-y-1 text-[12px] leading-snug', TINTA_SECUNDARIA)}>
            {faltou.map((f, i) => (
              <li key={`${f.customer_id ?? 'sem-conta'}-${f.escopo}-${i}`}>
                <span className="tabular font-medium text-foreground">
                  {f.customer_id ?? 'sem conta identificada'}
                </span>{' '}
                — {parteQueFaltou(f.escopo)}
              </li>
            ))}
          </ul>
          <p className={cn('mt-1.5 text-[12px]', TINTA_SECUNDARIA)}>
            O que estas contas tinham na última leitura boa continua abaixo, com a idade
            declarada. Nada foi apagado.
          </p>
        </div>
      </div>
    </div>
  );
};

/**
 * O que está na tela é o último dado bom, e ele tem idade.
 *
 * É o aviso que separa "não há problema" de "não consegui olhar de novo" — e,
 * desde a auditoria, também de "o servidor descreveu esta leitura com uma
 * palavra que eu não conheço". As três levam ao mesmo cuidado (confira antes
 * de gastar) por razões diferentes, e a razão precisa aparecer: silenciar a
 * terceira faria um estado novo do servidor chegar como se fosse normalidade.
 */
export const AvisoDeDadoAntigo: React.FC<{
  idadeSegundos: number | null;
  aAtualizacaoFalhou?: boolean;
  /** O valor cru que o servidor mandou, quando esta tela não o reconhece. */
  frescorNaoReconhecido?: string | null;
  className?: string;
}> = ({ idadeSegundos, aAtualizacaoFalhou, frescorNaoReconhecido, className }) => (
  <div
    className={cn('rounded-md border border-border bg-muted/40 px-4 py-3', className)}
    role="status"
  >
    <div className="flex items-start gap-2">
      <CircleHelp className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
      <p className={cn('max-w-[70ch] text-[12px] leading-snug', TINTA_SECUNDARIA)}>
        {/* As duas condições podem ser verdadeiras ao mesmo tempo, e por isso
            são duas frases e não um `if/else`: a releitura falhar e o estado
            devolvido ser desconhecido são fatos independentes, e engolir um
            deles porque o outro apareceu primeiro é como se perde metade da
            explicação exatamente no caso mais confuso. */}
        {aAtualizacaoFalhou && 'A atualização mais recente falhou. '}
        {frescorNaoReconhecido ? (
          <>
            O servidor descreveu esta leitura como{' '}
            <span className="font-medium text-foreground">“{frescorNaoReconhecido}”</span>, que
            esta versão da tela não conhece
            {idadeSegundos == null ? '. ' : `, ${idade(idadeSegundos)}. `}
            Trate os números abaixo como de idade desconhecida.{' '}
          </>
        ) : (
          <>
            {aAtualizacaoFalhou
              ? 'O que está na tela é a última leitura boa'
              : 'Estes números são da última leitura boa'}
            {idadeSegundos == null ? '.' : `, ${idade(idadeSegundos)}.`}{' '}
          </>
        )}
        Confira a idade de cada conta antes de decidir gasto.
      </p>
    </div>
  </div>
);
