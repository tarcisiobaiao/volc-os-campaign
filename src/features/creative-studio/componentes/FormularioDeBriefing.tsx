/** Aprova's compact format → context → quantity composition, with VOLC contracts. */
import { useEffect, useRef, useState } from 'react';
import { AlertCircle, ArrowRight, Check, Layers, Megaphone, Plus, Sparkles, Target, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { MAX_PECAS } from '../api';
import type { ContextoDaPagina, EntradaNovaOperacao, FatoDaOferta, FormatoDisponivel } from '../tipos';
import { SeletorDeFormatos } from './SeletorDeFormatos';
import { ContextoDaLandingPage } from './ContextoDaLandingPage';

function contextoHerdado(nome: string): string {
  try { return window.frameElement?.getAttribute(nome) ?? ''; } catch { return ''; }
}

export interface FormularioDeBriefingProps {
  ocupado: boolean;
  erro?: string | null;
  /** O catálogo VEM DO SERVIDOR. Nenhuma lista de formatos mora nesta tela. */
  formatos: readonly FormatoDisponivel[];
  carregandoFormatos?: boolean;
  onEnviar: (entrada: EntradaNovaOperacao) => void;
}

export function FormularioDeBriefing({
  ocupado,
  erro,
  formatos: catalogo,
  carregandoFormatos = false,
  onEnviar,
}: FormularioDeBriefingProps) {
  const [nome, setNome] = useState('');
  const [assunto, setAssunto] = useState('');
  const [referenciasVisuais, setReferenciasVisuais] = useState('');
  const preenchidosPelaPagina = useRef({ nome: '', contexto: '', assunto: '', referenciasVisuais: '', fatos: new Map<string, string>() });
  const [url, setUrl] = useState(() => contextoHerdado('data-destination-url'));
  const [contextoDaPagina, setContextoDaPagina] = useState<ContextoDaPagina | null>(null);
  const [avisoDeOrigem, setAvisoDeOrigem] = useState(false);
  const [contexto, setContexto] = useState('');
  const [fatos, setFatos] = useState<Array<Omit<FatoDaOferta, 'ref'> & { ref?: string }>>([{ declaracao: '', origem: 'OPERADOR' }]);
  const [formatos, setFormatos] = useState<string[]>([]);
  // A pré-seleção espera o catálogo: escolher `4x5` antes de saber se ele
  // existe neste servidor produziria um pedido que o motor recusa depois.
  const preSelecionado = useRef(false);
  useEffect(() => {
    if (preSelecionado.current || catalogo.length === 0) return;
    preSelecionado.current = true;
    const padrao = catalogo.find(f => f.slot === '4x5') ?? catalogo[0];
    setFormatos([padrao.slot]);
  }, [catalogo]);
  const [quantidade, setQuantidade] = useState(4);
  const fatosValidos = fatos.filter(f => f.declaracao.trim().length >= 3);
  const nomeValido = nome.trim().length >= 3;
  const contextoValido = contexto.trim().length >= 3;
  const pendencias = [
    url.trim() && !/^https:\/\/[^\s]+$/i.test(url.trim()) ? 'informe uma página HTTPS ou deixe o campo vazio' : null,
    !nomeValido ? 'dê um nome ao trabalho' : null,
    assunto.trim().length < 2 || !/[\p{L}\p{N}]/u.test(assunto) ? 'defina o assunto principal' : null,
    !contextoValido ? 'descreva o público' : null,
    fatosValidos.length === 0 ? 'informe pelo menos um fato da oferta' : null,
    formatos.length === 0 ? 'selecione pelo menos um formato' : null,
  ].filter((item): item is string => Boolean(item));
  const pronto = pendencias.length === 0 && !ocupado;

  function enviar() {
    if (!pronto) return;
    onEnviar({
      nome_da_operacao: nome.trim(),
      assunto_principal: assunto.trim(),
      ...(referenciasVisuais.trim() ? { referencias_visuais: referenciasVisuais.trim() } : {}),
      objetivo_meta: contextoHerdado('data-campaign-objective') || null,
      url_destino: url.trim() || null,
      contexto_da_pagina: contextoDaPagina,
      contexto_do_publico: contexto.trim(), quantidade_de_pecas: quantidade, formatos_permitidos: formatos,
      fatos_da_oferta: fatosValidos.map((f, i) => ({
        ref: f.ref ?? `fact_declarado_${i + 1}`, declaracao: f.declaracao.trim(), origem: f.origem,
        ...(f.evidencia_ref ? { evidencia_ref: f.evidencia_ref } : {}),
      })),
    });
  }

  return <form className="studio-brief space-y-5" onSubmit={e => { e.preventDefault(); enviar(); }}>
    <fieldset disabled={ocupado} className="min-w-0 space-y-5">
      <ContextoDaLandingPage url={url} contexto={contextoDaPagina} onUrl={nova => {
        setUrl(nova);
        const automaticos = preenchidosPelaPagina.current;
        if (Object.values(automaticos).some(valor => typeof valor === 'string' && valor) || automaticos.fatos.size) setAvisoDeOrigem(true);
        setNome(atual => automaticos.nome && atual === automaticos.nome ? '' : atual);
        setContexto(atual => automaticos.contexto && atual === automaticos.contexto ? '' : atual);
        setAssunto(atual => automaticos.assunto && atual === automaticos.assunto ? '' : atual);
        setReferenciasVisuais(atual => automaticos.referenciasVisuais && atual === automaticos.referenciasVisuais ? '' : atual);
        setFatos(atuais => {
          const mantidos = atuais.filter(f => !f.ref || automaticos.fatos.get(f.ref) !== f.declaracao);
          return mantidos.length ? mantidos : [{ declaracao: '', origem: 'OPERADOR' }];
        });
        preenchidosPelaPagina.current = { nome: '', contexto: '', assunto: '', referenciasVisuais: '', fatos: new Map() };
      }} onContexto={novo => {
        setContextoDaPagina(novo);
        if (novo === null) {
          if (fatos.some(f => f.origem === 'LANDING_PAGE')) setAvisoDeOrigem(true);
          setFatos(atuais => atuais.map(f => f.origem === 'LANDING_PAGE' ? { ...f, origem: 'OPERADOR', evidencia_ref: undefined } : f));
        }
      }} onAplicar={(pagina, refs) => {
        const automaticos = preenchidosPelaPagina.current;
        if (!nome.trim()) { automaticos.nome = pagina.titulo.slice(0, 200); setNome(automaticos.nome); }
        if (!contexto.trim()) { automaticos.contexto = [pagina.publico_sugerido, pagina.momento_sugerido].filter(Boolean).join('\n').slice(0, 4000); setContexto(automaticos.contexto); }
        if (!assunto.trim()) { automaticos.assunto = (pagina.assunto_principal || '').slice(0, 160); setAssunto(automaticos.assunto); }
        if (!referenciasVisuais.trim()) { automaticos.referenciasVisuais = (pagina.referencias_visuais_sugeridas || '').slice(0, 1500); setReferenciasVisuais(automaticos.referenciasVisuais); }
        setFatos(atuais => {
          const existentes = atuais.filter(f => f.declaracao.trim());
          const novos = pagina.fatos.filter(f => refs.includes(f.ref) && !existentes.some(e => e.ref === f.ref || e.declaracao.trim() === f.declaracao.trim()));
          novos.forEach(f => automaticos.fatos.set(f.ref, f.declaracao));
          const todos = [...existentes, ...novos.map(f => ({ ref: f.ref, declaracao: f.declaracao, origem: 'LANDING_PAGE' as const, evidencia_ref: f.ref }))].slice(0, 80);
          return todos.length ? todos : atuais;
        });
      }} />
      {avisoDeOrigem && <p role="status" className="text-sm text-muted-foreground">A página ou sua leitura mudou. Revise o briefing: ao trocar a URL, sugestões automáticas anteriores são removidas e seus textos editados são preservados.</p>}
      <section className="studio-surface">
        <div className="studio-section-label"><Megaphone aria-hidden className="h-4 w-4" /><h2>Tipo de criação</h2><span className="ml-auto normal-case tracking-normal text-muted-foreground">Imagem estática</span></div>
        <div className="mt-4 flex items-center gap-4 rounded-xl border border-primary/40 bg-primary/5 p-4">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground"><Megaphone className="h-5 w-5" aria-hidden /></span>
          <div className="min-w-0 flex-1"><p className="text-sm font-semibold text-foreground">Meta Ads</p><p className="mt-1 text-xs text-muted-foreground">Conceitos e imagens para suas campanhas</p><p className="mt-1 text-[11px] text-primary">Feed · Stories · peças multiformato</p></div>
          <Check className="h-4 w-4 shrink-0 text-primary" aria-label="Selecionado" />
        </div>
      </section>

      <section className="studio-surface">
        <div className="studio-section-label"><Layers aria-hidden className="h-4 w-4" /><h2>Formato</h2><span className="ml-auto normal-case tracking-normal text-muted-foreground">{catalogo.length} formatos</span></div>
        <SeletorDeFormatos formatos={catalogo} selecionados={formatos} onChange={setFormatos} carregando={carregandoFormatos} />
      </section>

      <section className="studio-surface">
        <div className="studio-section-label"><Target aria-hidden className="h-4 w-4" /><h2>O que vamos comunicar?</h2><span className="ml-auto normal-case tracking-normal text-muted-foreground">4 informações obrigatórias</span></div>
        <div className="mt-4 space-y-4">
          <div>
            <div><Label htmlFor="ac-nome" className="studio-field-label">Nome do trabalho <span className="font-normal text-muted-foreground">· obrigatório</span></Label><Input id="ac-nome" required aria-required="true" value={nome} onChange={e => { preenchidosPelaPagina.current.nome = ''; setNome(e.target.value); }} maxLength={200} placeholder="Ex.: Encceja · conquista do certificado" className="studio-input mt-2" /><p className="mt-2 text-xs text-muted-foreground">Serve para encontrar este trabalho no histórico.</p></div>
          </div>
          <div><Label htmlFor="ac-assunto" className="studio-field-label">Assunto principal <span className="font-normal text-muted-foreground">· obrigatório</span></Label><Input id="ac-assunto" required aria-required="true" value={assunto} onChange={e => { preenchidosPelaPagina.current.assunto = ''; setAssunto(e.target.value); }} minLength={2} maxLength={160} placeholder="Ex.: Pé-de-Meia ou Encceja 2026" className="studio-input mt-2" aria-describedby="ac-assunto-ajuda" /><p id="ac-assunto-ajuda" className="mt-2 text-xs text-muted-foreground">Use o nome curto do programa, produto ou tema que aparecerá em cada imagem. Perguntas e objetivos entram no contexto, não neste nome.</p></div>
          <div><Label htmlFor="ac-contexto" className="studio-field-label">Público e momento <span className="font-normal text-muted-foreground">· obrigatório</span></Label><Textarea id="ac-contexto" required aria-required="true" value={contexto} onChange={e => { preenchidosPelaPagina.current.contexto = ''; setContexto(e.target.value); }} maxLength={4000} rows={3} placeholder="Quem queremos alcançar? O que essa pessoa já sabe, teme ou precisa entender antes de agir?" className="studio-input mt-2 min-h-28 resize-y" /><p className="mt-2 text-xs text-muted-foreground">Esse contexto orienta os ângulos, as mensagens e a direção visual.</p></div>
          <details className="border-t border-border pt-3"><summary className="cursor-pointer py-2 text-sm font-medium">Cores e cenas de referência · opcional{referenciasVisuais.trim() ? ' · preenchido' : ''}</summary><Label htmlFor="ac-referencias" className="mt-2 block text-sm">Referências visuais</Label><Textarea id="ac-referencias" value={referenciasVisuais} onChange={e => { preenchidosPelaPagina.current.referenciasVisuais = ''; setReferenciasVisuais(e.target.value); }} maxLength={1500} rows={3} className="studio-input mt-2" placeholder="Ex.: Azul-marinho, livros e uma pessoa consultando a página no celular." aria-describedby="ac-referencias-ajuda" /><p id="ac-referencias-ajuda" className="mt-2 text-xs text-muted-foreground">Sugestões editoriais, não cores oficiais ou autorização para usar marcas. Não inclua logotipos de terceiros sem direito de uso.</p></details>
          <div>
            <div className="flex items-center justify-between gap-2"><h3 className="studio-field-label">Fatos da oferta <span className="font-normal text-muted-foreground">· ao menos um</span></h3><Button type="button" variant="ghost" size="sm" disabled={fatos.length >= 80} onClick={() => setFatos(f => [...f, { declaracao: '', origem: 'OPERADOR' }])}><Plus className="h-3.5 w-3.5" aria-hidden />Adicionar fato</Button></div>
            <p className="mb-3 text-xs text-muted-foreground">Escreva somente informações que podem aparecer na peça sem inventar promessa.</p>
            <div className="space-y-3">{fatos.map((f, i) => <div key={i}>
              <div className="flex gap-2"><Textarea aria-label={i === 0 ? 'Declaração' : `Declaração ${i + 1}`} aria-required={i === 0 ? 'true' : undefined} value={f.declaracao} rows={2} maxLength={1200} placeholder="Ex.: A matéria explica as etapas para consultar as informações da prova." className="studio-input min-h-20" onChange={e => setFatos(a => a.map((v, n) => n === i ? { ...v, declaracao: e.target.value, origem: 'OPERADOR', evidencia_ref: undefined } : v))} />{fatos.length > 1 && <Button type="button" variant="ghost" size="icon" aria-label={`Remover o fato ${i + 1}`} onClick={() => setFatos(a => a.filter((_, n) => n !== i))}><X className="h-4 w-4" /></Button>}</div>
              <label className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">Fonte
                <span>{f.origem === 'LANDING_PAGE' ? 'Página analisada · revisado por você' : 'Informado por mim'}</span>
              </label>
            </div>)}</div>
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
      {pendencias.length > 0 && !ocupado && <p className="mx-auto mt-2 max-w-lg text-xs text-muted-foreground">Para continuar: {pendencias.join('; ')}.</p>}
    </section>
  </form>;
}
