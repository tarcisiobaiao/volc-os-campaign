/** Aprova's compact format → context → quantity composition, with VOLC contracts. */
import { useState } from 'react';
import { AlertCircle, ArrowRight, Check, Layers, Megaphone, Plus, Sparkles, Target, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { FORMATOS_DO_MOTOR, MAX_PECAS } from '../api';
import type { EntradaNovaOperacao, OrigemDoFato } from '../tipos';
import { SeletorDeFormatos } from './SeletorDeFormatos';

export interface FormularioDeBriefingProps {
  ocupado: boolean;
  erro?: string | null;
  onEnviar: (entrada: EntradaNovaOperacao) => void;
}

export function FormularioDeBriefing({ ocupado, erro, onEnviar }: FormularioDeBriefingProps) {
  const [nome, setNome] = useState('');
  const [destino, setDestino] = useState('');
  const [objetivo, setObjetivo] = useState('OUTCOME_TRAFFIC');
  const [contexto, setContexto] = useState('');
  const [fatos, setFatos] = useState<{ declaracao: string; origem: OrigemDoFato }[]>([{ declaracao: '', origem: 'OPERADOR' }]);
  const [formatos, setFormatos] = useState<string[]>(['4x5']);
  const [quantidade, setQuantidade] = useState(4);
  const [detalhes, setDetalhes] = useState(false);
  const fatosValidos = fatos.filter(f => f.declaracao.trim().length >= 3);
  const destinoValido = /^[A-Za-z0-9:_-]{3,180}$/.test(destino.trim());
  const pronto = nome.trim().length >= 3 && destinoValido && contexto.trim().length >= 3 && fatosValidos.length > 0 && formatos.length > 0 && !ocupado;

  function enviar() {
    if (!pronto) return;
    onEnviar({
      nome_da_operacao: nome.trim(), destination_ref: destino.trim(), objetivo_meta: objetivo,
      contexto_do_publico: contexto.trim(), quantidade_de_pecas: quantidade, formatos_permitidos: formatos,
      fatos_da_oferta: fatosValidos.map((f, i) => ({
        ref: `fact_declarado_${i + 1}`, declaracao: f.declaracao.trim(), origem: f.origem,
      })),
    });
  }

  return <form className="studio-brief space-y-5" onSubmit={e => { e.preventDefault(); enviar(); }}>
    <fieldset disabled={ocupado} className="min-w-0 space-y-5">
      <section className="studio-surface">
        <div className="studio-section-label"><Megaphone aria-hidden className="h-4 w-4" /><h2>Tipo de criação</h2><span className="ml-auto normal-case tracking-normal text-muted-foreground">Imagem estática</span></div>
        <div className="mt-4 flex items-center gap-4 rounded-xl border border-primary/40 bg-primary/5 p-4">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground"><Megaphone className="h-5 w-5" aria-hidden /></span>
          <div className="min-w-0 flex-1"><p className="text-sm font-semibold text-foreground">Meta Ads</p><p className="mt-1 text-xs text-muted-foreground">Conceitos e imagens para suas campanhas</p><p className="mt-1 text-[11px] text-primary">Feed · Stories · peças multiformato</p></div>
          <Check className="h-4 w-4 shrink-0 text-primary" aria-label="Selecionado" />
        </div>
      </section>

      <section className="studio-surface">
        <div className="studio-section-label"><Layers aria-hidden className="h-4 w-4" /><h2>Formato</h2><span className="ml-auto normal-case tracking-normal text-muted-foreground">{FORMATOS_DO_MOTOR.length} formatos</span></div>
        <SeletorDeFormatos selecionados={formatos} onChange={setFormatos} />
      </section>

      <section className="studio-surface">
        <div className="studio-section-label"><Target aria-hidden className="h-4 w-4" /><h2>O que vamos comunicar?</h2></div>
        <div className="mt-4 space-y-4">
          <div><Label htmlFor="ac-nome" className="studio-field-label">Nome da operação</Label><Input id="ac-nome" value={nome} onChange={e => setNome(e.target.value)} maxLength={200} placeholder="Ex.: Encceja · conquista do certificado" className="studio-input mt-2" /></div>
          <div><Label htmlFor="ac-contexto" className="studio-field-label">Contexto do público</Label><Textarea id="ac-contexto" value={contexto} onChange={e => setContexto(e.target.value)} maxLength={4000} rows={3} placeholder="Quem queremos alcançar? O que essa pessoa precisa entender, sentir ou fazer?" className="studio-input mt-2 min-h-28 resize-y" /><p className="mt-2 text-xs text-muted-foreground">Esse contexto orienta os ângulos, as mensagens e a direção visual.</p></div>
          <div>
            <div className="flex items-center justify-between gap-2"><h3 className="studio-field-label">Fatos da oferta</h3><Button type="button" variant="ghost" size="sm" disabled={fatos.length >= 80} onClick={() => setFatos(f => [...f, { declaracao: '', origem: 'OPERADOR' }])}><Plus className="h-3.5 w-3.5" aria-hidden />Adicionar fato</Button></div>
            <p className="mb-3 text-xs text-muted-foreground">Inclua apenas informações que podemos afirmar na peça.</p>
            <div className="space-y-3">{fatos.map((f, i) => <div key={i}>
              <div className="flex gap-2"><Textarea aria-label={i === 0 ? 'Declaração' : `Declaração ${i + 1}`} value={f.declaracao} rows={2} maxLength={1200} placeholder="Ex.: Guia informativo com as etapas para solicitar o certificado." className="studio-input min-h-20" onChange={e => setFatos(a => a.map((v, n) => n === i ? { ...v, declaracao: e.target.value } : v))} />{fatos.length > 1 && <Button type="button" variant="ghost" size="icon" aria-label={`Remover o fato ${i + 1}`} onClick={() => setFatos(a => a.filter((_, n) => n !== i))}><X className="h-4 w-4" /></Button>}</div>
              <label className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">Fonte
                <select aria-label={`Origem do fato ${i + 1}`} value={f.origem} onChange={e => setFatos(a => a.map((v, n) => n === i ? { ...v, origem: e.target.value as OrigemDoFato } : v))} className="rounded border border-border bg-card px-2 py-1 text-foreground"><option value="OPERADOR">Informado por mim</option><option value="LANDING_PAGE">Página de destino</option></select>
              </label>
            </div>)}</div>
          </div>
          <div className="border-t border-border pt-4">
            <button type="button" aria-expanded={detalhes} onClick={() => setDetalhes(!detalhes)} className="flex min-h-10 w-full items-center justify-between text-sm font-medium text-foreground">Destino e objetivo<span className="text-xs font-normal text-muted-foreground">{destinoValido ? 'Configurado' : 'Completar'} · {detalhes ? '−' : '+'}</span></button>
            <div hidden={!detalhes} className={`${detalhes ? 'grid' : 'hidden'} mt-3 gap-4 sm:grid-cols-2`}>
              <div><Label htmlFor="ac-destino" className="studio-field-label">Destino</Label><Input id="ac-destino" value={destino} onChange={e => setDestino(e.target.value)} maxLength={180} placeholder="Referência do destino" className="studio-input mt-2" /><p className="mt-2 text-xs text-muted-foreground">Use a referência do destino cadastrado. URLs ainda não são resolvidas nesta integração.</p>{destino && !destinoValido && <p className="mt-1 text-xs text-destructive">Este campo aceita uma referência, não uma URL.</p>}</div>
              <div><Label htmlFor="ac-objetivo" className="studio-field-label">Objetivo Meta</Label><select id="ac-objetivo" value={objetivo} onChange={e => setObjetivo(e.target.value)} className="studio-input mt-2 h-10 w-full px-3 text-sm"><option value="OUTCOME_TRAFFIC">Tráfego</option><option value="OUTCOME_LEADS">Leads</option><option value="OUTCOME_SALES">Vendas</option><option value="OUTCOME_AWARENESS">Reconhecimento</option><option value="OUTCOME_ENGAGEMENT">Engajamento</option></select><p className="mt-2 text-xs text-muted-foreground">Orienta a estratégia, sem configurar uma campanha.</p></div>
            </div>
          </div>
        </div>
      </section>

      <section className="studio-surface">
        <div className="studio-section-label"><Layers className="h-4 w-4" aria-hidden /><Label htmlFor="ac-quantidade">Quantidade de peças</Label><output htmlFor="ac-quantidade" className="ml-auto rounded-lg border border-border bg-muted/40 px-4 py-1 text-sm tabular-nums text-foreground">{quantidade}</output></div>
        <input id="ac-quantidade" type="range" min={1} max={MAX_PECAS} value={quantidade} onChange={e => setQuantidade(Number(e.target.value))} className="mt-5 h-5 w-full cursor-pointer accent-primary" />
        <div className="mt-2 flex justify-between text-xs text-muted-foreground"><span>{quantidade} conceitos criativos</span><span>Até {MAX_PECAS}</span></div>
      </section>
    </fieldset>

    {erro && <p role="alert" className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />{erro}</p>}
    <section className="pb-4 pt-2 text-center">
      <h2 className="sr-only">O que este clique faz</h2>
      <p className="mb-4 text-xs text-muted-foreground">{quantidade} conceitos · {formatos.length} formatos · até {quantidade * formatos.length} imagens depois da aprovação.</p>
      <Button type="submit" disabled={!pronto} className="min-h-12 w-full gap-2 rounded-xl px-8 sm:w-auto sm:min-w-72"><Sparkles className="h-4 w-4" aria-hidden />{ocupado ? 'Criando…' : 'Criar estratégia'}<ArrowRight className="ml-2 h-4 w-4" aria-hidden /></Button>
      <p className="mx-auto mt-3 max-w-sm text-xs leading-relaxed text-muted-foreground">Primeiro você revisa a estratégia. Nenhuma imagem é gerada agora e este ato não cria campanha.</p>
      {!pronto && !ocupado && <p className="mt-2 text-xs text-muted-foreground">Complete o contexto, um fato e o destino para continuar.</p>}
    </section>
  </form>;
}
