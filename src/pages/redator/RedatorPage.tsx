/**
 * /redator — o posto de comando do motor de redação.
 *
 * ## O que estava errado na primeira versão desta tela
 *
 * Ela abria direto num funil específico, com uma lista lateral de execuções. Ou
 * seja: era a tela de UM funil se passando pela tela do módulo. Faltava o nível
 * de cima — de onde se dispara, se acompanha e se configura.
 *
 * O ciclo do negócio é PAUTA → FUNIL → CAMPANHA → RESULTADO. O Pautador cobre a
 * PAUTA e entrega cards aprovados e arquitetados. Este quadro cobre o FUNIL: ele
 * pega esses cards, manda escrever, mostra o que está sendo escrito e entrega
 * rascunhos prontos para revisão. O detalhe de cada funil mora em
 * `/redator/funil/:runId`, com endereço próprio — um trabalho de US$ 2 precisa
 * poder ser mandado para alguém revisar por link.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { PenLine, RefreshCw, SlidersHorizontal } from 'lucide-react';

import { Layout } from '@/components/layout/Layout';
import { Button } from '@/components/ui/button';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { DispararRedatorDialog } from '@/components/pautador-pro/entity/DispararRedatorDialog';
import { QuadroDeFunis } from '@/components/redator/QuadroDeFunis';
import { pautadorApi } from '@/lib/pautadorApi';
import { cn } from '@/lib/utils';
import type { EntityCard } from '@/types/pautadorEntity';
import type { CardPronto, FunilNoQuadro, QuadroDoRedator } from '@/types/redatorQuadro';

/** Enquanto houver funil sendo escrito, o quadro se atualiza sozinho. Cadência
 *  de 8s e não 3s: aqui a granularidade é "quantas páginas", que muda a cada
 *  poucos minutos — o segundo a segundo mora na página do funil. */
const CADENCIA_VIVA_MS = 8000;

function moeda2(v: number): string {
  return `US$ ${v.toFixed(2).replace('.', ',')}`;
}

const RedatorPage: React.FC = () => {
  const [quadro, setQuadro] = useState<QuadroDoRedator | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [disparando, setDisparando] = useState<CardPronto | null>(null);
  const [excluindo, setExcluindo] = useState<FunilNoQuadro | null>(null);
  const [apagando, setApagando] = useState(false);

  const buscar = useCallback(async () => {
    try {
      setQuadro(await pautadorApi.quadroDoRedator());
      setErro(null);
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falhei ao ler o quadro.');
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => { void buscar(); }, [buscar]);

  const temVivo = !!quadro?.escrevendo.length;
  useEffect(() => {
    if (!temVivo) return;
    const id = window.setInterval(() => void buscar(), CADENCIA_VIVA_MS);
    return () => window.clearInterval(id);
  }, [temVivo, buscar]);

  // O diálogo de disparo é o MESMO do Pautador — ele já valida credencial do
  // site, arquitetura do card e duplicata antes de gastar um centavo. Ter dois
  // caminhos de disparo com regras diferentes seria a forma mais cara possível
  // de descobrir uma divergência entre eles.
  const cardParaODialogo = disparando
    ? ({ id: disparando.opportunity_id, display_title: disparando.titulo } as unknown as EntityCard)
    : null;

  return (
    <Layout>
      <div className="space-y-6 p-4 md:p-6">
        <header className="flex flex-wrap items-start justify-between gap-3 reveal" style={{ ['--i' as never]: 0 }}>
          <div className="min-w-0">
            <div className="kicker mb-2 flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary">
                <PenLine className="h-3.5 w-3.5" aria-hidden />
              </span>
              motor de redação
            </div>
            <h1 className="font-display text-3xl font-bold tracking-tight leading-[1.05] sm:text-4xl">
              Redator <span className="text-aurora">Editorial</span>
            </h1>
            <div className="mt-3 aurora-rule w-16" />
            <p className="mt-3 max-w-[62ch] text-pretty text-sm text-muted-foreground">
              O Pautador aprova a pauta e arquiteta o funil. Aqui ele vira texto,
              imagem e rascunho no WordPress — pronto para a campanha apontar.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="hover-lift" onClick={() => void buscar()}>
              <RefreshCw className={cn('h-4 w-4', carregando && 'animate-spin')} aria-hidden />
              atualizar
            </Button>
            <Link to="/redator/config">
              <Button variant="outline" size="sm" className="hover-lift">
                <SlidersHorizontal className="h-4 w-4" aria-hidden />
                configuração
              </Button>
            </Link>
          </div>
        </header>

        {/* Os três números que resumem o módulo. Uma superfície, não três
            cartões iguais com ícone em caixa — o pulso do QG é o padrão. */}
        {quadro && (
          <section
            aria-label="Pulso do Redator"
            className="overflow-hidden rounded-lg border border-border bg-card shadow-card"
          >
            <div className="grid gap-px bg-border sm:grid-cols-3">
              <div className="bg-card px-4 py-3">
                <p className="text-lg font-semibold tabular-nums text-foreground">
                  {moeda2(quadro.totais.gasto_usd)}
                </p>
                <p className="mt-1 text-xs leading-4 text-muted-foreground">
                  gasto acumulado · {quadro.totais.runs} execuç{quadro.totais.runs === 1 ? 'ão' : 'ões'}, inclusive as que falharam
                </p>
              </div>
              <div className="bg-card px-4 py-3">
                <p className="text-lg font-semibold tabular-nums text-foreground">
                  {quadro.totais.paginas_no_ar}
                </p>
                <p className="mt-1 text-xs leading-4 text-muted-foreground">
                  páginas no WordPress · como rascunho
                </p>
              </div>
              <div className="bg-card px-4 py-3">
                <p className="text-lg font-semibold tabular-nums text-foreground">
                  {quadro.prontos.length}
                </p>
                <p className="mt-1 text-xs leading-4 text-muted-foreground">
                  esperando escrita · cards aprovados no Pautador
                </p>
              </div>
            </div>
          </section>
        )}

        {erro && (
          <p className="max-w-[68ch] text-sm leading-relaxed text-destructive">{erro}</p>
        )}
        {carregando && !quadro && (
          <p className="text-sm text-muted-foreground">Lendo o quadro…</p>
        )}

        {quadro && (
          <QuadroDeFunis quadro={quadro} onDisparar={setDisparando} onExcluir={setExcluindo} />
        )}
      </div>

      {/* Confirmação, porque excluir não tem desfazer. O texto diz o que se
          perde de verdade: a linha some, os artefatos ficam na pasta do run.
          "Tem certeza?" sozinho não ajuda ninguém a decidir. */}
      <AlertDialog open={!!excluindo} onOpenChange={(v) => { if (!v) setExcluindo(null); }}>
        <AlertDialogContent className="rounded-lg">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-display">
              Excluir a execução #{excluindo?.id}?
            </AlertDialogTitle>
            <AlertDialogDescription className="space-y-2 text-left">
              <span className="block">
                <b>{excluindo?.titulo}</b> · {excluindo?.dominio || '—'} ·{' '}
                {moeda2(excluindo?.custo_usd ?? 0)} já gastos.
              </span>
              <span className="block">
                Ela some do quadro e do gasto acumulado. Como não publicou nada,
                não há rascunho no WordPress apontando para ela. Os arquivos que
                o motor chegou a gerar continuam na pasta do run, no servidor.
              </span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>manter</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={apagando}
              onClick={async (e) => {
                e.preventDefault();
                if (!excluindo) return;
                setApagando(true);
                try {
                  await pautadorApi.excluirRun(excluindo.id);
                  setExcluindo(null);
                  await buscar();
                } catch (err) {
                  setErro(err instanceof Error ? err.message : 'Não consegui excluir.');
                  setExcluindo(null);
                } finally {
                  setApagando(false);
                }
              }}>
              {apagando ? 'excluindo…' : 'excluir'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <DispararRedatorDialog
        card={cardParaODialogo}
        aberto={!!disparando}
        aoFechar={() => {
          setDisparando(null);
          // Recarrega ao fechar: se o disparo aconteceu, o card tem de sair da
          // coluna "prontos" e aparecer em "escrevendo" na hora — senão parece
          // que o clique não fez nada e alguém dispara de novo.
          void buscar();
        }}
      />
    </Layout>
  );
};

export default RedatorPage;
