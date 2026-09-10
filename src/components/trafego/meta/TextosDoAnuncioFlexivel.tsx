import { useId } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { pendenciasDosTextosFlexiveis, type TextosFlexiveisDraft } from './rascunho';

const campos = [
  { key: 'primary_text', label: 'Texto principal', plural: 'Textos principais', limite: 2200, minimo: 1, dica: 'Explore abordagens diferentes para o mesmo destino.' },
  { key: 'headline', label: 'Título', plural: 'Títulos', limite: 255, minimo: 1, dica: 'Frases curtas que funcionem com qualquer imagem selecionada.' },
  { key: 'description', label: 'Descrição', plural: 'Descrições', limite: 255, minimo: 0, dica: 'Opcional. Pode não aparecer em todos os posicionamentos.' },
] as const;

/** One text pool per ad set, shared by its images. Editing never mutates another set. */
export function TextosDoAnuncioFlexivel({ value, onChange, conjunto, imagens, disabled = false }: {
  value: TextosFlexiveisDraft;
  onChange: (value: TextosFlexiveisDraft) => void;
  conjunto: string;
  imagens: number;
  disabled?: boolean;
}) {
  const id = useId();
  const erros = pendenciasDosTextosFlexiveis(value);
  return <section aria-labelledby={`${id}-title`} className="space-y-6 rounded-xl border border-border bg-card p-4 sm:p-6">
    <header className="space-y-2">
      <p className="text-xs font-medium text-primary">1 anúncio flexível · {conjunto}</p>
      <h3 id={`${id}-title`} className="text-xl font-semibold">Variações de texto para suas imagens</h3>
      <p className="max-w-prose text-sm text-muted-foreground">As {imagens} imagens deste conjunto compartilham os textos abaixo. Você escolhe as opções; a Meta decide como combiná-las e exibi-las. Isso não garante entrega igual nem um teste A/B de todas as combinações.</p>
      <p className="text-sm font-medium" aria-live="polite">{value.primary_text.length} textos · {value.headline.length} títulos · {value.description.length} descrições</p>
    </header>
    {campos.map(c => <fieldset key={c.key} disabled={disabled} className="min-w-0 space-y-3 border-t border-border pt-5">
      <legend className="float-left mb-2 flex w-full items-center justify-between gap-2 text-base font-semibold"><span>{c.plural}</span><span className="text-xs font-normal tabular-nums text-muted-foreground">{value[c.key].length}/5</span></legend>
      <p className="clear-both max-w-prose text-sm text-muted-foreground">{c.dica}</p>
      {value[c.key].map((texto, index) => {
        const inputId = `${id}-${c.key}-${index}`;
        const alterar = (novo: string) => onChange({ ...value, [c.key]: value[c.key].map((v, i) => i === index ? novo : v) });
        return <div key={inputId} className="space-y-1.5">
          <label htmlFor={inputId} className="text-sm font-medium">{c.label} {index + 1}</label>
          <div className="flex items-start gap-2">
            {c.key === 'primary_text'
              ? <Textarea id={inputId} rows={3} value={texto} maxLength={c.limite} onChange={e => alterar(e.target.value)} aria-describedby={`${inputId}-count`} className="min-w-0 flex-1" />
              : <Input id={inputId} value={texto} maxLength={c.limite} onChange={e => alterar(e.target.value)} aria-describedby={`${inputId}-count`} className="min-h-11 min-w-0 flex-1" />}
            <Button type="button" size="icon" variant="ghost" className="h-11 w-11 shrink-0" aria-label={`Remover ${c.label.toLowerCase()} ${index + 1}`} disabled={value[c.key].length <= c.minimo} onClick={() => onChange({ ...value, [c.key]: value[c.key].filter((_, i) => i !== index) })}><Trash2 className="h-4 w-4" aria-hidden /></Button>
          </div>
          <p id={`${inputId}-count`} className="text-right text-xs tabular-nums text-muted-foreground">{Array.from(texto).length}/{c.limite} caracteres</p>
        </div>;
      })}
      <Button type="button" variant="outline" className="min-h-11" disabled={value[c.key].length >= 5} onClick={() => onChange({ ...value, [c.key]: [...value[c.key], ''] })}><Plus className="h-4 w-4" aria-hidden />Adicionar {c.label.toLowerCase()}</Button>
    </fieldset>)}
    {erros.length > 0 && <div role="status" className="space-y-1 text-sm text-warning">{erros.map(erro => <p key={erro}>{erro}</p>)}</div>}
    <p className="max-w-prose text-xs text-muted-foreground">Textos, imagens e botão devem fazer sentido juntos. Ao editar estas opções, as confirmações deste conjunto precisam ser refeitas. O outro conjunto mantém suas próprias variações.</p>
  </section>;
}
