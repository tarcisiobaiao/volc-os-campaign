/**
 * A fila de atenção — o que pede algo de mim hoje, agrupado por SINTOMA.
 *
 * ## Por que por sintoma, e não por conta
 *
 * A pergunta do operador não é "quais contas têm problema": é "o que eu faço
 * agora". Campanhas com o mesmo sintoma pedem a mesma revisão, na mesma ordem;
 * campanhas da mesma conta com sintomas diferentes pedem coisas opostas. Por
 * isso o título do grupo é a condição, a frase abaixo dele é o que a condição
 * AFIRMA, e a próxima ação segura vem junto de cada item.
 *
 * ## Por que ela bebe da MESMA projeção que o sino
 *
 * Porque duas derivações para a mesma pergunta divergem exatamente quando
 * importa: uma atualizou, a outra não, e o operador fica com dois números para
 * o mesmo fato sem saber qual obedecer. O sino é projeção; a lista completa
 * mora aqui; a derivação é uma só, em `atencao/projecao.ts`.
 *
 * ## ⚠️ INDISPONIBILIDADE NÃO É ALERTA
 *
 * "Não consegui perguntar" e "perguntei e há três problemas" levam a ações
 * opostas. Conta que não pôde ser lida aparece num bloco próprio, com palavras
 * próprias, e NUNCA soma ao contador de condições ativas.
 *
 * ## E por que "sem vínculo" não está aqui
 *
 * Porque é verdade sobre quase todo o registro no primeiro dia. Uma fila que
 * acende para tudo é uma fila que ninguém lê na segunda semana. Vínculo e
 * procedência continuam visíveis onde pertencem: no inventário, como selo da
 * linha.
 */
import React from 'react';
import { CircleCheck, TriangleAlert, WifiOff } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import ItemDeAtencao from '@/components/trafego/atencao/ItemDeAtencao';
import { visualDoSintoma } from '@/components/trafego/atencao/visual';
import { useAtencao } from '@/components/trafego/atencao/useAtencao';
import {
  DECISOES_SEM_SENSOR,
  FAMILIAS,
  familiaDoSintoma,
  type GrupoDeSintoma,
} from '@/components/trafego/atencao/projecao';

import { EsqueletoDoInventario, FalhaDoInventario } from './EstadosDoInventario';

export interface PropsDaFila {
  /**
   * Item a revelar e focar ao abrir. `{conta}-{campanha}` quando o fato é de
   * uma campanha, `{conta}` quando é da leitura da conta inteira.
   */
  foco?: string | null;
}

const plural = (n: number, um: string, muitos: string) =>
  n === 1 ? `1 ${um}` : `${n} ${muitos}`;

export const FilaDeAtencao: React.FC<PropsDaFila> = ({ foco }) => {
  const atencao = useAtencao();

  /**
   * O sino manda para cá com o item no endereço. Focar (e não só rolar)
   * importa para quem chegou pelo teclado: sem foco, o Tab seguinte voltaria ao
   * começo da página e o motivo da vinda se perderia.
   *
   * ⚠️ MAS SÓ UMA VEZ POR CHEGADA. O efeito dependia do objeto da consulta, e o
   * React Query devolve um OBJETO NOVO a cada releitura — releitura que
   * acontece sozinha, no intervalo e ao voltar o foco para a aba. Na prática o
   * efeito reexecutava a cada poucos minutos e arrancava o cursor de onde o
   * operador estivesse: no meio de outro item, num botão, num campo. Roubar o
   * foco de quem está trabalhando é o oposto de ajudar quem acabou de chegar.
   *
   * A dependência agora é a EXISTÊNCIA da projeção (um booleano, estável entre
   * releituras) e o `foco` pedido; e a trava guarda qual foco já foi atendido,
   * para que só uma vinda nova do sino mova o cursor.
   */
  const focoAtendido = React.useRef<string | null>(null);
  const temProjecao = !atencao.carregando && !atencao.indisponivel;

  React.useEffect(() => {
    if (!foco || !temProjecao) return;
    if (focoAtendido.current === foco) return;
    const alvo = document.getElementById(`alerta-${foco}`);
    if (!alvo) return;
    focoAtendido.current = foco;
    // O foco é o que importa; a rolagem é conforto e nem todo ambiente a
    // implementa. Perder a rolagem não pode custar o foco.
    alvo.scrollIntoView?.({ block: 'center' });
    alvo.focus({ preventScroll: true });
  }, [foco, temProjecao]);

  if (atencao.carregando) return <EsqueletoDoInventario contas={1} linhas={2} />;

  if (atencao.indisponivel) {
    return (
      // A ocorrência (frase, próximo passo e código copiável) vem pronta da
      // leitura; sem ela o componente monta uma `nao_prevista` com código
      // próprio, que continua sendo o que liga a tela ao log.
      <FalhaDoInventario
        ocorrencia={atencao.ocorrencia}
        aoTentarDeNovo={atencao.conferirDeNovo}
      />
    );
  }

  const total = atencao.itens.length;

  return (
    <div className="space-y-5">
      {atencao.ultimoEstadoConhecido && (
        <p
          className="rounded-md border border-warning/40 bg-warning/[0.06] px-4 py-3 text-[12px] leading-snug text-muted-foreground"
          role="status"
        >
          A atualização mais recente falhou. O que está abaixo é a última leitura boa.
        </p>
      )}

      {atencao.semLeitura.length > 0 && (
        <section
          aria-label="contas que não puderam ser lidas"
          className="rounded-md border border-destructive/40 bg-destructive/[0.05] px-4 py-3"
        >
          <div className="flex items-start gap-2">
            <WifiOff className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
            <div className="min-w-0">
              <h3 className="text-[13px] font-semibold">
                {atencao.semLeitura.length === 1
                  ? '1 conta não pôde ser lida'
                  : `${atencao.semLeitura.length} contas não puderam ser lidas`}
              </h3>
              <ul className="mt-1 space-y-1 text-[12px] leading-snug text-muted-foreground">
                {atencao.semLeitura.map((c) => (
                  <li key={c.contaId}>
                    <span className="font-medium text-foreground">{c.conta}</span>{' '}
                    <span className="tabular">{c.contaId}</span> — {c.motivo}
                    {c.ultimaLeituraBoa ? ` (${c.ultimaLeituraBoa})` : ''}
                  </li>
                ))}
              </ul>
              {/* ⚠️ Esta frase é a regra inteira em uma linha, e por isso ela
                  não sai daqui: ausência de leitura não é ausência de problema,
                  e as duas produzem a mesma tela silenciosa quando ninguém
                  escreve a diferença. */}
              <p className="mt-1.5 text-[12px] text-muted-foreground">
                Sobre estas contas não há condição ativa nem ausência de condição: há ausência
                de leitura.
              </p>
            </div>
          </div>
        </section>
      )}

      {total === 0 ? (
        <div className="rounded-md border border-border bg-card px-4 py-8 text-center">
          <CircleCheck className="mx-auto h-6 w-6 text-muted-foreground" aria-hidden />
          <h3 className="mt-3 font-display text-base font-semibold">
            Nenhuma condição ativa entre o que foi lido
          </h3>
          <p className="mx-auto mt-2 max-w-[62ch] text-[13px] leading-relaxed text-muted-foreground">
            {atencao.verificadas == null
              ? 'A conferência de entrega não respondeu nesta leitura, então este vazio vale só para o registro de campanhas.'
              : `${plural(atencao.verificadas, 'campanha ligada foi conferida', 'campanhas ligadas foram conferidas')}${
                  atencao.horasAteAlertar == null
                    ? ''
                    : ` e nenhuma delas está ligada há mais de ${atencao.horasAteAlertar} h sem gastar`
                }.`}{' '}
            Esta fila enche sozinha quando alguma entrar nessa condição.
          </p>
          {/* ⚠️ O aviso do que a fila NÃO cobre aparece TAMBÉM aqui — e aqui é
              onde ele mais importa. Achado por revisão adversarial em
              27/08/2026: ele existia só no ramo com condições, e sumia
              justamente na tela vazia, que é onde o operador conclui "está tudo
              bem". Uma fila vazia sem esta ressalva afirma silenciosamente que
              não há problema de política, de orçamento nem de rastreamento —
              três coisas que nenhum sensor mediu. */}
          <div className="mx-auto mt-5 max-w-[62ch] text-left">
            <OQueEstaFilaNaoCobre />
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          <p className="text-[12px] text-muted-foreground" role="status">
            {atencao.parcial
              ? `${plural(total, 'condição ativa encontrada', 'condições ativas encontradas')} até agora — a lista pode estar incompleta.`
              : `${plural(total, 'condição ativa', 'condições ativas')}.`}
          </p>

          {/* ⚠️ Agrupado por DECISÃO, e não pela origem técnica da condição.
              A SPEC §11 pede a fila organizada pela decisão que o operador
              precisa tomar. Os sintomas continuam sendo os mesmos e a
              autoridade de contagem não muda — o sino e a aba leem a mesma
              projeção. O que muda é que "sincronização falhou" e "leitura
              desatualizada" param de aparecer como assuntos diferentes: são o
              mesmo, a conta não está confiável agora. */}
          {/* ⚠️ A ordem das famílias segue a ORDEM DA PROJEÇÃO, e não uma lista
              fixa aqui. `SINTOMAS[].ordem` é a autoridade de severidade e a
              projeção já entrega os grupos ordenados por ela. Achado por
              revisão adversarial: uma lista fixa de famílias reordenava por
              cima — `campanha_nao_encontrada` (ordem 5) passava a renderizar
              DEPOIS de `conta_nao_identificada` (ordem 7). Duas ordenações
              sobre o mesmo conjunto, e a que ninguém declarou vencia. */}
          {[...new Set(atencao.grupos.map((g) => familiaDoSintoma(g.sintoma)))].map((chave) => {
            const familia = FAMILIAS.find((f) => f.chave === chave)!;
            const grupos = atencao.grupos.filter((g) => familiaDoSintoma(g.sintoma) === chave);
            if (grupos.length === 0) return null;
            return (
              <section key={familia.chave} aria-labelledby={`fam-${familia.chave}`} className="space-y-2">
                <div className="border-b border-border pb-1.5">
                  <h3
                    id={`fam-${familia.chave}`}
                    className="font-display text-[13px] font-semibold tracking-tight"
                  >
                    {familia.titulo}
                  </h3>
                  <p className="text-[11px] leading-snug text-muted-foreground">
                    {familia.pergunta}
                  </p>
                </div>
                {grupos.map((grupo) => (
                  <Grupo key={grupo.sintoma} grupo={grupo} foco={foco ?? null} />
                ))}
              </section>
            );
          })}

          <OQueEstaFilaNaoCobre />
        </div>
      )}

      {atencao.parcial && atencao.motivos.length > 0 && (
        <p
          className="rounded-md border border-border bg-muted/40 px-4 py-3 text-[12px] leading-snug text-muted-foreground"
          role="status"
        >
          Esta lista está incompleta: {atencao.motivos.join('; ')}. O contador acima é o que
          deu para ver, não um total.
        </p>
      )}

      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
        <p className="max-w-[70ch] text-[12px] leading-snug text-muted-foreground">
          Esta fila é a projeção do que a última varredura viu. Ela ainda não agrupa
          reincidência, não registra quem assumiu o caso e não fecha sozinha quando a causa
          some — isso vem depois, e omitir a frase faria a fila parecer mais completa do que é.
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={cn('h-9 shrink-0 px-3 text-xs')}
          disabled={atencao.atualizando}
          onClick={atencao.conferirDeNovo}
        >
          {atencao.atualizando ? 'conferindo…' : 'conferir de novo'}
        </Button>
      </footer>
    </div>
  );
};

/**
 * O que esta fila NÃO cobre — nas duas telas, cheia e vazia.
 *
 * ⚠️ Silêncio sobre política, orçamento e rastreamento lê-se como "não há
 * problema de política". A SPEC §11 lista sete famílias de decisão e só três
 * têm sensor hoje; declarar as outras quatro é a diferença entre uma fila
 * incompleta e uma fila que parece completa.
 */
const OQueEstaFilaNaoCobre: React.FC = () => (
  <details className="rounded-md border border-border bg-muted/30 px-3 py-2">
    <summary className="cursor-pointer text-[12px] font-medium">
      Decisões que esta fila ainda não cobre
    </summary>
    <ul className="mt-2 space-y-1.5 text-[11px] leading-snug text-muted-foreground" role="list">
      {DECISOES_SEM_SENSOR.map((d) => (
        <li key={d.titulo}>
          <strong className="font-medium text-foreground">{d.titulo}</strong> — {d.porque}
        </li>
      ))}
    </ul>
  </details>
);

/** Um sintoma, o que ele afirma, e as campanhas que estão nele. */
const Grupo: React.FC<{ grupo: GrupoDeSintoma; foco: string | null }> = ({ grupo, foco }) => {
  const { glifo: Glifo, tom } = visualDoSintoma(grupo.sintoma);

  // As palavras cruas que o servidor mandou e esta tela não sabe ler. Elas
  // aparecem porque "condição não reconhecida" sozinha é um beco: o operador
  // sabe que há algo e não tem o que dizer a quem pode consertar.
  const crus = [...new Set(grupo.itens.map((i) => i.sintomaCru).filter(Boolean))] as string[];

  return (
    <section aria-label={grupo.descricao.titulo} className="space-y-2">
      <header className="flex items-start gap-2">
        <Glifo
          className={cn(
            'mt-0.5 h-4 w-4 shrink-0',
            tom === 'ruim' ? 'text-destructive' : tom === 'neutro' ? 'text-muted-foreground' : 'text-warning',
          )}
          aria-hidden
        />
        <div className="min-w-0">
          <h3 className="font-display text-[0.9375rem] font-semibold leading-tight">
            {grupo.descricao.titulo}
            <span className="ml-2 font-sans text-[11px] font-normal text-muted-foreground">
              {grupo.descricao.escopo === 'conta'
                ? plural(grupo.itens.length, 'conta', 'contas')
                : plural(grupo.itens.length, 'campanha', 'campanhas')}
            </span>
          </h3>
          <p className="mt-1 max-w-[74ch] text-[12px] leading-snug text-muted-foreground">
            {grupo.descricao.afirma}
          </p>
          {crus.length > 0 && (
            <p className="mt-1 max-w-[74ch] text-[12px] leading-snug text-muted-foreground">
              O servidor chamou isto de{' '}
              {crus.map((c, i) => (
                <React.Fragment key={c}>
                  {i > 0 && ', '}
                  <span className="font-medium text-foreground">“{c}”</span>
                </React.Fragment>
              ))}
              . A condição é real; o que falta aqui é a frase, não o fato.
            </p>
          )}
        </div>
      </header>

      <ul className="rounded-md border border-border bg-card">
        {grupo.itens.map((item) => (
          <ItemDeAtencao key={item.chave} item={item} indicado={foco === item.chave} />
        ))}
      </ul>
    </section>
  );
};

export default FilaDeAtencao;
