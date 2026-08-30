/**
 * O gatilho do redator — escolher o site e mandar escrever.
 *
 * ## Por que um popup e não o arraste
 *
 * As outras colunas disparam no arraste porque a escolha já está feita: medir é
 * medir, arquitetar é arquitetar. Escrever o funil precisa de um dado que o card
 * não tem — em QUAL site ele vai — e é a etapa mais cara da esteira. Um arraste
 * acidental que gasta dólar e escreve num site errado é um erro sem desfazer.
 *
 * ## O que a tela precisa deixar claro, e por quê
 *
 * 1. **O site inapto aparece, com o motivo.** Esconder o projeto sem credencial
 *    faria o operador procurar um site que sumiu. Dizer "falta o Application
 *    Password" manda ele para a página do projeto.
 * 2. **Só existe um caminho, e ele está escrito na tela.** Gerar sempre sobe o
 *    funil como RASCUNHO do WordPress. O antigo modo "só gerar" saiu porque
 *    custava o mesmo (o pipeline roda inteiro; `publish` só é consultado no fim)
 *    e entregava menos revisão — artefato em disco, sem tela. O rascunho do
 *    WordPress é a superfície de revisão de verdade.
 * 3. **O estado do motor é dito, não fingido.** Enquanto o funnelforge não
 *    estiver ligado à fila, a tela informa que o run ficou enfileirado. Uma
 *    barra de progresso que nunca anda seria pior.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { pautadorApi, PautadorApiError } from '@/lib/pautadorApi';
import {
  ROTULO_STATUS_RUN,
  type ProjetoDestino, type RunDoRedator,
} from '@/types/publicacao';
import type { EntityCard } from '@/types/pautadorEntity';
import { BriefingAcoes, temBriefing } from './BriefingAcoes';
import {
  AlertTriangle, Check, Globe, Loader2, PenLine, FileText, Send,
} from 'lucide-react';

interface Props {
  card: EntityCard | null;
  aberto: boolean;
  aoFechar: () => void;
}

export const DispararRedatorDialog: React.FC<Props> = ({ card, aberto, aoFechar }) => {
  const { toast } = useToast();
  const [destinos, setDestinos] = useState<ProjetoDestino[]>([]);
  const [escolhido, setEscolhido] = useState<number | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [runs, setRuns] = useState<RunDoRedator[]>([]);

  // A contagem de páginas NÃO vem do card: `funnel_architecture` não está
  // exposto no tipo do front (o card carrega só `funnel_hypotheses`). Quem tem
  // o dado é o backend, que valida a arquitetura no disparo e devolve
  // `paginas_planejadas` no run. Até existir um run, a tela não afirma número.
  const paginasConhecidas = runs.find((r) => r.paginas_planejadas)?.paginas_planejadas ?? null;

  const carregar = useCallback(async () => {
    if (!card?.id) return;
    setCarregando(true);
    try {
      const [d, r] = await Promise.all([
        pautadorApi.destinosPublicacao(),
        pautadorApi.runsDoRedator(card.id),
      ]);
      setDestinos(d);
      setRuns(r);
      // Pré-seleciona o único apto, quando há exatamente um: escolher entre uma
      // opção só não é escolha. Com dois ou mais, o operador decide.
      const aptos = d.filter((x) => x.apto);
      setEscolhido(aptos.length === 1 ? aptos[0].project_id : null);
    } catch (e) {
      toast({
        title: 'Não consegui listar os sites',
        description: e instanceof PautadorApiError ? e.message : 'Erro inesperado.',
        variant: 'destructive',
      });
    } finally {
      setCarregando(false);
    }
  }, [card?.id, toast]);

  useEffect(() => { if (aberto) void carregar(); }, [aberto, carregar]);

  const destinoEscolhido = useMemo(
    () => destinos.find((d) => d.project_id === escolhido) || null,
    [destinos, escolhido],
  );

  const disparar = async () => {
    if (!card?.id || !escolhido) return;
    setEnviando(true);
    try {
      const r = await pautadorApi.dispararRedator({
        opportunity_id: card.id,
        project_id: escolhido,
      });
      toast({
        title: r.aviso?.startsWith('Já existe') ? 'Já estava na fila' : 'Escrita enfileirada',
        description: r.aviso || `Funil de ${r.run.paginas_planejadas ?? '?'} páginas para ${destinoEscolhido?.nome}.`,
      });
      await carregar();
    } catch (e) {
      toast({
        title: 'Não consegui enfileirar',
        description: e instanceof PautadorApiError ? e.message : 'Erro inesperado.',
        variant: 'destructive',
      });
    } finally {
      setEnviando(false);
    }
  };

  const semAptos = !carregando && destinos.length > 0 && !destinos.some((d) => d.apto);

  return (
    <Dialog open={aberto} onOpenChange={(v) => !v && aoFechar()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <PenLine className="h-4 w-4 text-primary" />
            Escrever o funil
          </DialogTitle>
          <DialogDescription>
            {card?.display_title || card?.entity?.canonical_name || 'este card'}
            {paginasConhecidas ? <> · {paginasConhecidas} páginas</> : null}
          </DialogDescription>
        </DialogHeader>

        {carregando ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
            <Loader2 className="h-4 w-4 animate-spin" /> lendo os sites…
          </div>
        ) : (
          <div className="space-y-4">
            {/*
              Reusa `BriefingAcoes` em vez de montar a URL à mão. A versão
              anterior remontava o endereço inline, sem passar pelo helper — e
              por isso ficou para trás quando a rota ganhou portão de
              identidade. Dois caminhos para o mesmo recurso significam que
              corrigir um deixa o outro quebrado.
            */}
            {card && temBriefing(card) && <BriefingAcoes card={card} />}

            {/* ── site ── */}
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider">Publicar em</Label>
              {semAptos && (
                <div className="flex items-start gap-2 text-xs border border-destructive/30 bg-destructive/5 p-2.5">
                  <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-destructive" />
                  <span>
                    Nenhum site está pronto. Configure o WordPress na página do projeto
                    (<i>Publicação · onde o redator escreve</i>) e volte aqui.
                  </span>
                </div>
              )}
              <div className="flex flex-col gap-px bg-border border border-border">
                {destinos.map((d) => {
                  const ativo = d.project_id === escolhido;
                  return (
                    <button
                      key={d.project_id}
                      type="button"
                      disabled={!d.apto}
                      onClick={() => setEscolhido(d.project_id)}
                      className={[
                        'text-left bg-card px-3 py-2.5 transition-colors',
                        d.apto ? 'hover:bg-muted/50 cursor-pointer' : 'opacity-55 cursor-not-allowed',
                        ativo ? 'ring-1 ring-inset ring-primary' : '',
                      ].join(' ')}
                    >
                      <div className="flex items-center gap-2">
                        <Globe className={`h-3.5 w-3.5 shrink-0 ${d.apto ? 'text-primary' : 'text-muted-foreground'}`} />
                        <span className="text-sm font-medium truncate">{d.nome}</span>
                        {ativo && <Check className="h-3.5 w-3.5 text-primary ml-auto shrink-0" />}
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5 pl-5.5 truncate">{d.motivo}</div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Não há escolha de modo: gerar SEMPRE sobe como rascunho do
                WordPress. Em vez de um seletor de uma opção só, a tela diz o
                que vai acontecer — e onde revisar. */}
            <div className="text-xs text-muted-foreground border border-border p-2.5 leading-relaxed">
              O funil sobe para <b className="text-foreground">{destinoEscolhido?.nome || 'o site escolhido'}</b> como{' '}
              <b className="text-foreground">rascunho do WordPress</b>: LP em Elementor no{' '}
              <code>/r/</code> e as páginas de solução em Gutenberg no <code>/rec/</code>.
              Nada fica visível para o público até você publicar no WordPress.
            </div>

            {/* ── histórico ── */}
            {runs.length > 0 && (
              <div className="space-y-1.5">
                <Label className="text-xs uppercase tracking-wider">Execuções deste card</Label>
                <div className="text-xs space-y-1">
                  {runs.slice(0, 4).map((r) => {
                    const site = destinos.find((d) => d.project_id === r.project_id);
                    return (
                      <div key={r.id} className="flex items-center gap-2 text-muted-foreground">
                        <span className="truncate">{site?.nome || `projeto ${r.project_id}`}</span>
                        <span className="opacity-60">·</span>
                        <span>{ROTULO_STATUS_RUN[r.status]}</span>
                        {r.custo_usd != null && <><span className="opacity-60">·</span><span>US$ {r.custo_usd.toFixed(2)}</span></>}
                        {r.criado_em && (
                          <span className="ml-auto shrink-0 opacity-70">
                            {new Date(r.criado_em).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={aoFechar}>Fechar</Button>
          <Button onClick={disparar} disabled={!escolhido || enviando}>
            {enviando ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Send className="h-4 w-4 mr-1.5" />}
            Gerar funil
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
