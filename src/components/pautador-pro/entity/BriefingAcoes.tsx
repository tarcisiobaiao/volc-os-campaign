// ============================================
// PAUTADOR PRO — abrir o briefing do funil
//
// O briefing vive NO SISTEMA: página em nova aba (Ctrl+P vira PDF) e o
// .docx sob demanda para quem precisar do arquivo. O anexo automático no
// ClickUp saiu junto com a integração — documentação em cópia nasce
// desatualizada, e duas versões viram duas verdades.
//
// ---------------------------------------------------------------------------
// POR QUE NÃO É MAIS UM <a href> DIRETO
// ---------------------------------------------------------------------------
// Desde 24/08/2026 a rota do briefing exige identidade. Uma navegação de topo
// não carrega cabeçalho — o navegador não deixa —, então `<a href>` apontando
// para a API devolveria 401 numa aba em branco.
//
// O conteúdo passa a vir por `fetch` com Bearer e a aba abre um `blob:`, que
// existe só nesta sessão. O botão vira botão de verdade: ele trabalha antes de
// abrir, e por isso mostra estado de carregamento e de erro.
import React from 'react';
import { FileText, Loader2 } from 'lucide-react';

import { pautadorApi } from '@/lib/pautadorApi';
import { useToast } from '@/hooks/use-toast';
import type { EntityCard } from '@/types/pautadorEntity';

interface BriefingAcoesProps {
  card: EntityCard;
}

/** O briefing é feito do que está PERSISTIDO (funil + entidade). Card demo não
 *  tem linha no banco, e card sem funil renderizaria um documento que só diz
 *  que não há páginas — nos dois casos o botão não aparece. */
export function temBriefing(card: EntityCard): boolean {
  if (!card.id || card.ephemeral) return false;
  if (!pautadorApi.configured) return false;
  return (
    card.status === 'funnel' ||
    card.status === 'ready' ||
    (card.funnel_hypotheses?.length ?? 0) > 0
  );
}

export const BriefingAcoes: React.FC<BriefingAcoesProps> = ({ card }) => {
  const [abrindo, setAbrindo] = React.useState(false);
  const { toast } = useToast();

  if (!temBriefing(card)) return null;

  const abrir = async () => {
    if (abrindo) return;
    setAbrindo(true);
    try {
      const blob = await pautadorApi.entityBriefingBlobUrl(card.id as number);
      const aba = window.open(blob, '_blank', 'noreferrer');
      if (!aba) {
        toast({
          title: 'O navegador bloqueou a nova aba',
          description: 'Libere pop-ups para este site e tente de novo.',
          variant: 'destructive',
        });
      }
      // Revoga depois de dar tempo da aba carregar. Revogar no ato deixaria a
      // aba em branco; nunca revogar prenderia o documento inteiro na memória.
      window.setTimeout(() => URL.revokeObjectURL(blob), 60_000);
    } catch (erro) {
      toast({
        title: 'Não foi possível abrir o briefing',
        description: erro instanceof Error ? erro.message : 'Tente novamente.',
        variant: 'destructive',
      });
    } finally {
      setAbrindo(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => { void abrir(); }}
      disabled={abrindo}
      title="Abre o briefing do funil em nova aba (Ctrl+P vira PDF)"
      className="inline-flex items-center h-8 px-3 rounded-md border border-primary/40 text-sm text-primary hover:bg-primary/10 transition-colors disabled:opacity-60"
    >
      {abrindo
        ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" aria-hidden />
        : <FileText className="h-3.5 w-3.5 mr-1" aria-hidden />}
      {abrindo ? 'abrindo…' : 'Abrir briefing'}
    </button>
  );
};
