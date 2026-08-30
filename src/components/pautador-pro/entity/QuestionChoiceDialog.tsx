import React, { useEffect, useState } from 'react';
import { HelpCircle, Loader2 } from 'lucide-react';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import type { EntityCard, QuestionChoicePayload } from '@/types/pautadorEntity';

/** Nível -> texto humano. A tela NUNCA mostra o código (`dado_unico`), porque
 *  quem decide aqui é uma pessoa lendo, não um parser. */
const ENGAJAMENTO_PT: Record<string, string> = {
  sustenta: 'há o que ler',
  dado_unico: 'esgota em segundos',
  // Os quatro do meio, aposentados por medição (concentraram 62,5% e 76,2% em
  // dois lotes). Ficam para ler card antigo sem mostrar código na tela.
  diagnostico: 'há o que ler',
  condicional: 'há o que ler',
  sequencial: 'há o que ler',
  comparativo: 'há o que ler',
};

const IGNORANCIA_PT: Record<string, string> = {
  nao_sei_se_existe: 'não sei nem que existe',
  nao_sei_se_sirvo: 'não sei se me encaixo',
  nao_sei_por_que_falhou: 'não sei por que não deu',
  so_falta_um_dado: 'só falta um dado',
  sei_o_que_fazer: 'sei o que fazer, quero executar',
  nao_preciso_de_nada: 'curiosidade pura',
};

interface QuestionChoiceDialogProps {
  card: EntityCard | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Registra e SEMPRE move o card — inclusive ao pular ou fechar. */
  onResolve: (card: EntityCard, payload: QuestionChoicePayload | null) => void;
}

/**
 * Qual pergunta vamos atacar? (arraste DESCOBERTAS -> EM VALIDAÇÃO)
 *
 * A entidade não tem UMA pergunta — tem várias, todas legítimas. "CDB" carrega
 * uma comparativa, uma condicional e uma de dado único. Rotular a ENTIDADE não
 * funcionou (33,3% de estabilidade entre rodadas contra 23,5% de acaso); aqui o
 * objeto é a PERGUNTA, que é a unidade do gerador de funil.
 *
 * Esta tela NÃO pontua, NÃO ordena e NÃO bloqueia. Toda saída move o card: um
 * registro que trava o trabalho deixa de ser preenchido em uma semana.
 */
export const QuestionChoiceDialog: React.FC<QuestionChoiceDialogProps> = ({
  card, open, onOpenChange, onResolve,
}) => {
  const [selected, setSelected] = useState<number | 'custom' | null>(null);
  const [customFrase, setCustomFrase] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) { setSelected(null); setCustomFrase(''); setNotes(''); setSaving(false); }
  }, [open, card?.id]);

  if (!card) return null;

  const candidatas = card.respostas ?? [];
  const titulo = card.display_title || card.entity?.canonical_name || 'Entidade';
  const podeEscolher = selected === 'custom' ? customFrase.trim().length > 0 : selected !== null;

  const finalizar = (payload: QuestionChoicePayload | null) => {
    setSaving(true);
    onResolve(card, payload);   // move o card e fecha; o registro é best-effort
    onOpenChange(false);
  };

  const escolher = () => {
    const nota = notes.trim() || null;
    if (selected === 'custom') {
      finalizar({ outcome: 'custom', custom_frase: customFrase.trim(), notes: nota });
    } else if (typeof selected === 'number') {
      finalizar({ outcome: 'chosen', chosen_index: selected, notes: nota });
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o && !saving) finalizar({ outcome: 'skipped' }); else onOpenChange(o); }}>
      <DialogContent className="sm:max-w-[620px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="rounded-md bg-info/10 text-info p-1.5"><HelpCircle className="h-4 w-4" /></span>
            Qual pergunta vamos atacar?
          </DialogTitle>
          <DialogDescription>
            {titulo}
            {card.entity?.full_name && card.entity.full_name !== titulo
              ? ` · ${card.entity.full_name}` : ''}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          {candidatas.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Esta entidade foi descoberta antes das perguntas candidatas existirem.
              Escreva a pergunta abaixo, ou pule.
            </p>
          )}

          {candidatas.map((q, i) => {
            const eng = ENGAJAMENTO_PT[q.engajamento_level] ?? q.engajamento_level;
            const ign = q.ignorancia_level ? IGNORANCIA_PT[q.ignorancia_level] : null;
            return (
              <label
                key={i}
                className={`flex gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                  selected === i ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/40'
                }`}
              >
                <input
                  type="radio" name="pergunta" className="mt-1 shrink-0"
                  checked={selected === i} onChange={() => setSelected(i)}
                />
                <span className="space-y-1">
                  <span className="block text-sm">"{q.frase}"</span>
                  <span className="block text-xs text-muted-foreground">
                    {eng}{ign ? ` · ${ign}` : ''}
                  </span>
                  {/* Informativo, NÃO bloqueio: diz o que a literatura interna
                      aponta e deixa a decisão com quem lê. */}
                  {q.engajamento_level === 'dado_unico' && (
                    <span className="block text-xs text-warning">
                      ⚠ resposta curta — o leitor sai antes do anúncio
                    </span>
                  )}
                </span>
              </label>
            );
          })}

          {/* Sempre visível, nunca escondido atrás de "outras opções": é o
              registro que aponta onde o gerador não viu a pergunta que importa. */}
          <label
            className={`flex gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
              selected === 'custom' ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/40'
            }`}
          >
            <input
              type="radio" name="pergunta" className="mt-1 shrink-0"
              checked={selected === 'custom'} onChange={() => setSelected('custom')}
            />
            <span className="flex-1 space-y-2">
              <span className="block text-sm">Nenhuma destas. A pergunta é:</span>
              <Input
                value={customFrase}
                onChange={(e) => { setCustomFrase(e.target.value); setSelected('custom'); }}
                placeholder="Escreva a pergunta que o funil vai responder"
              />
            </span>
          </label>

          <Textarea
            value={notes} onChange={(e) => setNotes(e.target.value)}
            placeholder="Observação (opcional)"
            className="min-h-[60px] text-sm"
          />
        </div>

        <DialogFooter className="gap-2 sm:justify-between">
          <Button
            variant="ghost" size="sm" disabled={saving}
            onClick={() => finalizar({ outcome: 'entity_rejected', notes: notes.trim() || null })}
          >
            Recusar a entidade
          </Button>
          <span className="flex gap-2">
            <Button variant="outline" disabled={saving} onClick={() => finalizar({ outcome: 'skipped' })}>
              Pular por agora
            </Button>
            <Button disabled={!podeEscolher || saving} onClick={escolher}>
              {saving && <Loader2 className="h-4 w-4 animate-spin mr-2" />}Escolher
            </Button>
          </span>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
