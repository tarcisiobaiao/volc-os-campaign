import { useRef, useState } from 'react';
import { Check, Globe, Loader2, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { analisarPaginaCriativa } from '../api';
import type { ContextoDaPagina } from '../tipos';

interface Props {
  url: string;
  contexto: ContextoDaPagina | null;
  onUrl: (url: string) => void;
  onContexto: (contexto: ContextoDaPagina | null) => void;
  onAplicar: (contexto: ContextoDaPagina, refs: string[]) => void;
}

const TIPOS_DE_MOTIVACAO = [
  { tipo: 'dor', rotulo: 'Dor' },
  { tipo: 'desejo', rotulo: 'Desejo' },
  { tipo: 'sonho', rotulo: 'Sonho' },
  { tipo: 'receio', rotulo: 'Receio' },
] as const;

export function ContextoDaLandingPage({ url, contexto, onUrl, onContexto, onAplicar }: Props) {
  const [lendo, setLendo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [selecionados, setSelecionados] = useState<string[]>([]);
  const [aplicado, setAplicado] = useState(false);
  const revisao = useRef(0);
  async function analisar() {
    const versao = ++revisao.current;
    setLendo(true); setErro(null); setAplicado(false); onContexto(null);
    try {
      const resultado = await analisarPaginaCriativa(url.trim());
      if (versao !== revisao.current) return;
      onContexto(resultado);
      setSelecionados(resultado.fatos.map(f => f.ref));
    } catch (e) {
      if (versao === revisao.current) setErro(e instanceof Error ? e.message : 'Não foi possível ler a página. Preencha o contexto abaixo.');
    } finally { if (versao === revisao.current) setLendo(false); }
  }
  return <section className="studio-surface" aria-labelledby="lp-contexto-titulo">
    <div className="studio-section-label"><Globe aria-hidden className="h-4 w-4 text-primary" /><h2 id="lp-contexto-titulo">Comece pela página</h2><span className="ml-auto normal-case tracking-normal text-muted-foreground">Opcional</span></div>
    <Label htmlFor="ac-url" className="mt-4 block text-base font-semibold">Qual página você quer divulgar?</Label>
    <p id="ac-url-ajuda" className="mt-1 text-sm text-muted-foreground">Cole a landing page ou matéria. Você revisa as sugestões antes de usá-las no briefing.</p>
    <div className="mt-3 flex flex-col gap-2 sm:flex-row">
      <Input id="ac-url" type="url" inputMode="url" autoComplete="url" value={url} aria-describedby="ac-url-ajuda" placeholder="https://seusite.com.br/materia" maxLength={2000} className="studio-input min-h-11 flex-1" onChange={e => {
        revisao.current++; setLendo(false); setErro(null); setAplicado(false); onContexto(null); onUrl(e.target.value);
      }} />
      <Button type="button" variant="secondary" className="min-h-11 shrink-0" disabled={lendo || !/^https:\/\/\S+$/i.test(url.trim())} onClick={() => void analisar()}>
        {lendo ? <Loader2 aria-hidden className="h-4 w-4 motion-safe:animate-spin" /> : <Search aria-hidden className="h-4 w-4" />}{lendo ? 'Analisando página…' : 'Analisar página'}
      </Button>
    </div>
    {lendo && <div role="status" className="mt-4 space-y-2 rounded-lg bg-muted/40 p-4"><p className="text-sm">Lendo o conteúdo e separando fatos de hipóteses…</p><div className="h-3 w-4/5 rounded bg-muted motion-safe:animate-pulse" /><div className="h-3 w-3/5 rounded bg-muted motion-safe:animate-pulse" /></div>}
    {erro && <p role="alert" className="mt-3 text-sm text-destructive">{erro} Você pode continuar preenchendo manualmente.</p>}
    {contexto && !lendo && <div className="mt-5 space-y-4 border-t border-border pt-4">
      <div><h3 className="text-base font-semibold">{contexto.titulo || contexto.assunto}</h3><p className="mt-1 text-sm text-muted-foreground">{contexto.proposta}</p><a className="mt-1 inline-block max-w-full break-all text-xs text-primary underline underline-offset-4" href={contexto.url_final} target="_blank" rel="noopener noreferrer">Ver página de origem</a></div>
      <div><h4 className="text-xs font-semibold text-primary">Assunto principal sugerido</h4><p className="mt-1 text-sm">{contexto.assunto_principal || 'O tema principal precisa da sua confirmação no briefing.'}</p><p className="mt-1 text-xs text-muted-foreground">Você pode ajustar o tema no briefing. Cada imagem deve deixar claro do que o anúncio trata.</p></div>
      {!!contexto.motivacoes_sugeridas?.length && <section aria-label="Motivações para o clique" className="space-y-4 border-y border-border py-5">
        <div><h4 className="text-lg font-semibold">Por que alguém clicaria?</h4><p className="mt-1 max-w-prose text-sm text-muted-foreground">Hipóteses criativas para testar, não um diagnóstico do público. O clique deve levar ao que a página realmente entrega.</p></div>
        <div className="grid gap-x-7 gap-y-5 sm:grid-cols-2">{TIPOS_DE_MOTIVACAO.map(({ tipo, rotulo }) => {
          const motivacoes = contexto.motivacoes_sugeridas!.filter(m => m.tipo === tipo);
          if (!motivacoes.length) return null;
          return <div key={tipo}><h5 className="text-xs font-semibold uppercase tracking-wide text-primary">{rotulo}</h5><ul className="mt-2 list-outside list-disc space-y-3 pl-4 text-sm">{motivacoes.map((m, indice) => {
            const fatosDeApoio = contexto.fatos.filter(f => m.fato_refs.includes(f.ref));
            return <li key={`${tipo}:${indice}`} className="pl-1"><p className="font-medium leading-relaxed">{m.hipotese}</p><p className="mt-1 leading-relaxed text-muted-foreground">{m.pergunta_latente}</p>{!m.fato_refs.every(ref => selecionados.includes(ref)) && <p className="mt-2 text-xs text-warning">Não vai orientar o briefing: fato de apoio desmarcado.</p>}<details className="mt-1 text-xs text-muted-foreground"><summary className="cursor-pointer py-2">O que a página entrega</summary><p className="leading-relaxed">{m.entrega_da_pagina}</p>{fatosDeApoio.length > 0 ? <div className="mt-2"><p className="font-medium text-foreground">Apoio encontrado na página</p><ul className="mt-1 list-inside list-disc space-y-1">{fatosDeApoio.map(f => <li key={f.ref}>{f.declaracao}</li>)}</ul></div> : <p className="mt-2">Sem fato vinculado. Revise a hipótese antes de usá-la.</p>}</details></li>;
          })}</ul></div>;
        })}</div>
      </section>}
      {contexto.referencias_visuais_sugeridas && <div><h4 className="text-xs font-semibold text-primary">Referências visuais sugeridas</h4><p className="mt-1 text-sm">{contexto.referencias_visuais_sugeridas}</p><p className="mt-1 text-xs text-muted-foreground">Direção editorial de cores e cenas, não identidade oficial de uma marca.</p></div>}
      <details className="border-b border-border py-2"><summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold">Revisar fatos da página <span className="font-normal text-muted-foreground">· {selecionados.length} de {contexto.fatos.length} selecionados</span></summary>
      <fieldset className="space-y-2 pt-2"><legend className="sr-only">Fatos encontrados · selecione o que faz sentido</legend>
        <p className="text-xs text-muted-foreground">Os fatos selecionados entram no briefing. Confira os trechos e desmarque o que não deve orientar a peça.</p>
        {contexto.fatos.map(f => <div key={f.ref} className="border-b border-border/60 py-3 last:border-0"><label className="flex min-h-11 cursor-pointer items-start gap-3 text-sm"><input type="checkbox" className="mt-1 h-4 w-4 shrink-0 accent-primary" checked={selecionados.includes(f.ref)} onChange={e => { setAplicado(false); setSelecionados(atual => e.target.checked ? [...atual, f.ref] : atual.filter(r => r !== f.ref)); }} /><span>{f.declaracao}</span></label><details className="pl-7 text-xs text-muted-foreground"><summary className="cursor-pointer py-1">Conferir trecho da página</summary><blockquote className="mt-1 break-words">“{f.trecho}”</blockquote></details></div>)}
        {contexto.fatos.length === 0 && <p className="text-sm text-muted-foreground">Nenhum fato suficientemente sustentado. Informe os fatos abaixo.</p>}
      </fieldset></details>
      <div className="grid gap-3 sm:grid-cols-2"><div><h4 className="text-xs font-semibold text-primary">Hipótese de público · revise</h4><p className="mt-1 text-sm">{contexto.publico_sugerido}</p></div><div><h4 className="text-xs font-semibold text-primary">Hipótese de momento · revise</h4><p className="mt-1 text-sm">{contexto.momento_sugerido}</p></div></div>
      {contexto.angulos_sugeridos.length > 0 && <p className="text-sm text-muted-foreground"><span className="font-medium text-foreground">Possíveis ângulos: </span>{contexto.angulos_sugeridos.join(' · ')}</p>}
      {[...contexto.informacoes_ausentes, ...contexto.avisos].length > 0 && <details className="text-sm text-muted-foreground"><summary className="cursor-pointer py-2">O que ainda precisa da sua atenção</summary><ul className="list-inside list-disc space-y-1">{[...contexto.informacoes_ausentes, ...contexto.avisos].map((a, i) => <li key={i}>{a}</li>)}</ul></details>}
      <div className="flex flex-wrap items-center gap-3"><Button type="button" variant="secondary" disabled={aplicado} className="min-h-11" onClick={() => { onAplicar(contexto, selecionados); setAplicado(true); }}><Check aria-hidden className="h-4 w-4" />{aplicado ? 'Sugestões adicionadas' : 'Adicionar ao briefing'}</Button><p role="status" className="text-xs text-muted-foreground">{aplicado ? 'Revise e edite nos campos abaixo.' : 'Seus textos atuais serão preservados.'}</p></div>
    </div>}
  </section>;
}
