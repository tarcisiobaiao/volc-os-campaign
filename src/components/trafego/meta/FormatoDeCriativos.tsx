import { Button } from '@/components/ui/button';
import { type Draft, type ModoCriativo, variacoesEmitidas } from './rascunho';

/** The grouping decision is visible before any upload or approval. */
export function FormatoDeCriativos({ draft, onChange }: { draft: Draft; onChange: (mode: ModoCriativo) => void }) {
  const rows = variacoesEmitidas(draft);
  const flexible = draft.creativeMode === 'flexible';
  return <fieldset className="space-y-2 border-b border-border pb-4">
    <legend className="mb-2 text-sm font-semibold">Como estas peças serão publicadas?</legend>
    <div className="flex flex-wrap gap-2">
      <Button type="button" className="min-h-11 whitespace-normal text-left" variant={!flexible ? 'default' : 'outline'} aria-pressed={!flexible} onClick={() => onChange('batch')}>Uma peça por anúncio</Button>
      <Button type="button" className="min-h-11 whitespace-normal text-left" variant={flexible ? 'default' : 'outline'} aria-pressed={flexible} onClick={() => onChange('flexible')}>Flexível: agrupar por conjunto</Button>
    </div>
    <p className="max-w-prose text-sm text-muted-foreground" role="status">{flexible
      ? `${new Set(rows.map(v => v.adsetKey)).size} anúncio(s) flexível(is), com ${rows.length} imagem(ns). Cada conjunto terá seu próprio banco de textos, até 5 opções por tipo, e um único botão. O nome do anúncio vem da primeira peça. Disponível para Vendas, sujeito à validação da Meta.`
      : `${rows.length} anúncio(s), cada um com sua própria imagem e copy.`}</p>
    {flexible && draft.recipeId !== 'WEB_SALES_CONVERSION' && <p role="alert" className="text-sm text-warning">Para usar flexível, escolha Vendas na etapa Resultado. Suas peças continuam salvas.</p>}
  </fieldset>;
}
