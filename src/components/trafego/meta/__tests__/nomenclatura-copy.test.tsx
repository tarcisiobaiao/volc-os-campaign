// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { aplicarNomenclatura, gerarNomenclatura, novaNomenclatura, tipoDoDestino } from '../nomenclatura';
import { NomenclaturaAutomatica } from '../NomenclaturaAutomatica';
import { VarinhaDeCopy } from '../VarinhaDeCopy';
import { conjuntoInicial, variacaoInicial, type Draft } from '../rascunho';
const api=vi.hoisted(()=>({readMetaCampaignDraft:vi.fn(),reserveMetaNaming:vi.fn(),suggestMetaCopy:vi.fn(),analyze:vi.fn()}));
vi.mock('@/lib/metaCampaignDraftApi',()=>api);
vi.mock('@/features/creative-studio/api',()=>({analisarPaginaCriativa:api.analyze}));
afterEach(cleanup);
beforeEach(()=>vi.resetAllMocks());
function draft():Draft {
  const d:Draft={accountRef:'account-A',pageRef:'page-A',instagramActorRef:'',campaignName:'CNH do Brasil',destinationUrl:'https://www.technews.com.br/r/renovacao',recipeId:'TRAFFIC_WEBSITE_LPV_STATIC',nivelDeOrcamento:'ADSET',periodoDeOrcamento:'DAILY',budgetBrl:'10',categoryConfirmed:true,creativeMode:'flexible',conjuntos:[conjuntoInicial('A','ABO',''),conjuntoInicial('B','CBO','')],variations:[variacaoInicial('a',1,'A'),variacaoInicial('b',2,'A'),variacaoInicial('c',3,'B')]};
  d.variations[0].assetRef='asset-A';d.naming={...novaNomenclatura(d),topicSourceUrl:d.destinationUrl,campaignNumber:37,accountRef:d.accountRef};return d;
}
const deferred=<T,>()=>{let resolve!:(value:T)=>void;const promise=new Promise<T>(r=>{resolve=r;});return {promise,resolve};};
const suggestions={primary_text:['Nova abordagem'],headline:['Novo título'],description:['Nova descrição'],model:'hermetic-model',context_sha256:'fixture'};

it('reserva números por identidade, mantendo ordem e exclusões sem reciclar números',()=>{
  const original=aplicarNomenclatura(draft(),draft().naming!);
  const reordered={...original,conjuntos:[...original.conjuntos].reverse(),variations:[...original.variations].reverse()};
  const output=aplicarNomenclatura(reordered,reordered.naming!);
  for(const ad of original.variations)expect(output.variations.find(x=>x.key===ad.key)?.adName).toBe(ad.adName);
  const deleted={...output,variations:[...output.variations.filter(a=>a.key!=='b'),variacaoInicial('d',4,'A')]};
  const next=aplicarNomenclatura(deleted,deleted.naming!);
  expect(next.naming!.adNumbers['A:b']).toBe(2);expect(next.naming!.adNumbers['A:d']).toBe(3);
  const deletedSet={...next,conjuntos:[next.conjuntos.find(s=>s.key==='B')!,conjuntoInicial('C','novo','')],variations:next.variations.filter(a=>a.adsetKey==='B')};
  expect(aplicarNomenclatura(deletedSet,deletedSet.naming!).naming!.adsetNumbers.C).toBe(3);
});

it('mover anúncio cria numeração do novo pai sem alterar IDs e preserva reserva anterior',()=>{
  const d=aplicarNomenclatura(draft(),draft().naming!);d.variations=d.variations.map(a=>a.key==='a'?{...a,adsetKey:'B'}:a);
  const moved=aplicarNomenclatura(d,d.naming!);
  expect(moved.variations.find(a=>a.key==='a')?.adName).toContain('CP0037_CJ002_AN002');
  expect(moved.naming!.adNumbers['A:a']).toBe(1);expect(moved.naming!.adNumbers['B:a']).toBe(2);
});

it('preserva nomes editados manualmente após geração e recusa reserva de outra conta',()=>{
  const d=aplicarNomenclatura(draft(),draft().naming!);d.campaignName='Nome manual';d.conjuntos[0].nome='Conjunto manual';d.variations[0].adName='Anúncio manual';d.variations[0].creativeName='Criativo manual';
  const changed=aplicarNomenclatura(d,{...d.naming!,topic:'Novo assunto'});
  expect([changed.campaignName,changed.conjuntos[0].nome,changed.variations[0].adName,changed.variations[0].creativeName]).toEqual(['Nome manual','Conjunto manual','Anúncio manual','Criativo manual']);
  expect(aplicarNomenclatura(d,{...d.naming!,accountRef:'outra'})).toBe(d);
});

it('LP_R depende do segmento r do caminho, não domínio/query/outros prefixos',()=>{
  expect(tipoDoDestino('https://site.com/r/guia')).toBe('LP_R');
  for(const url of ['https://site.com/renovacao','https://site.com/rota/r/','https://r.site.com/?rota=/r/','invalid','https://site.com/R/guia'])expect(tipoDoDestino(url)).toBe('');
});

it('tags condicionais refletem orçamento, plataforma, idade, quiz, conversão e tamanho',()=>{
  const d=draft();d.nivelDeOrcamento='CAMPAIGN';d.conjuntos[0].publico.idadeMin=25;d.conjuntos[0].publico.idadeMax=54;d.conjuntos[0].posicionamentoModo='MANUAL';d.conjuntos[0].posicionamentoValores=['facebook','instagram'];d.conjuntos[0].mensuracao.proposito='OPTIMIZE';d.conjuntos[0].mensuracao.eventoPadrao='CONTENT_VIEW';
  const {names}=gerarNomenclatura(d,{...d.naming!,quiz:true},{'asset-A':'1080x1350'});
  expect(names.campaign).toContain('[CBO]');expect(names['set:A']).toBe('CP0037_CJ001 [IMG] [FB + IG] [25-54] [LP_R] [QUIZ] [VIEW_CONTENT]');
  expect(names['creative:a']).toContain('1080x1350');expect(names['ad:a']).toContain('[FLEX]');
  const simple=gerarNomenclatura(draft(),{...draft().naming!,landingType:''});
  expect(simple.names['set:A']).not.toContain('QUIZ');expect(simple.names['set:A']).not.toContain('18-65');
});

it('conversão personalizada não herda o nome do evento padrão oculto',()=>{
  const d=draft(); d.conjuntos[0].mensuracao={...d.conjuntos[0].mensuracao, proposito:'OPTIMIZE',conversaoRef:'custom',eventoPadrao:'CONTENT_VIEW'};
  const names=gerarNomenclatura(d,d.naming!,{}, {'custom':'RewardedAdView'}).names;
  expect(names['set:A']).toContain('[REWARDEDADVIEW]');expect(names['set:A']).not.toContain('[VIEW_CONTENT]');
  expect(gerarNomenclatura(d,d.naming!).names['set:A']).toContain('[CONVERSAO_PERSONALIZADA]');
});

it('varinha exige geração explícita e mostra preview sem sobrescrever; aplicar acrescenta',async()=>{
  const d=draft(),save=vi.fn().mockResolvedValue(true),apply=vi.fn();api.readMetaCampaignDraft.mockResolvedValue({draft:d,version:9});api.suggestMetaCopy.mockResolvedValue(suggestions);
  render(<VarinhaDeCopy draft={d} draftRef="ref" adsetKey="A" save={save} onApply={apply} demo={false}/>);
  expect(api.suggestMetaCopy).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Sugerir copies com IA'}));expect(api.suggestMetaCopy).not.toHaveBeenCalled();
  await screen.findByText('Sugestões para revisar');expect(apply).not.toHaveBeenCalled();expect(save).toHaveBeenCalledOnce();
  expect(api.suggestMetaCopy).toHaveBeenCalledWith('ref',9,'A',3,'',expect.any(AbortSignal));
  fireEvent.click(screen.getByRole('button',{name:'Acrescentar ao banco'}));expect(apply).toHaveBeenCalledWith({primary_text:[d.variations[0].message,'Nova abordagem'],headline:[d.variations[0].headline,'Novo título'],description:[d.variations[0].description,'Nova descrição']});
});

it('um clique sugere sem pedir novo briefing e informa as fontes efetivamente recuperadas',async()=>{
  const d=draft(),apply=vi.fn();api.readMetaCampaignDraft.mockResolvedValue({draft:d,version:9});
  api.suggestMetaCopy.mockResolvedValue({...suggestions,context_summary:{mode:'MIXED',facts_count:2,
    sources:[{kind:'LP_SNAPSHOT',name:'Guia de renovação',item_count:1}],
    warnings:['Uma peça não tem contexto de origem confirmado.']}});
  render(<VarinhaDeCopy draft={d} draftRef="ref" adsetKey="A" save={vi.fn().mockResolvedValue(true)} onApply={apply} demo={false}/>);
  expect(screen.queryByRole('textbox')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Sugerir copies com IA'}));
  await screen.findByText('Contexto conectado · 2 fatos disponíveis');
  expect(api.suggestMetaCopy).toHaveBeenCalledOnce();
  expect(screen.getByText('Guia de renovação · 1 item(ns)')).toBeTruthy();
  expect(screen.getByText('Uma peça não tem contexto de origem confirmado.')).toBeTruthy();
  expect(apply).not.toHaveBeenCalled();
});

it('trocar a origem do pack invalida sugestões mesmo preservando imagem e textos',async()=>{
  const d=draft(),apply=vi.fn();api.readMetaCampaignDraft.mockResolvedValue({draft:d,version:9});api.suggestMetaCopy.mockResolvedValue(suggestions);
  const view=render(<VarinhaDeCopy draft={d} draftRef="ref" adsetKey="A" save={vi.fn().mockResolvedValue(true)} onApply={apply} demo={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Sugerir copies com IA'}));await screen.findByText('Sugestões para revisar');
  const changed={...d,variations:d.variations.map((v,i)=>i===0?{...v,packOrigin:{packId:'pack-new',masterRef:'master-new',manifestHash:'hash-new',selectionVersion:2,accountRef:d.accountRef}}:v)};
  view.rerender(<VarinhaDeCopy draft={changed} draftRef="ref" adsetKey="A" save={vi.fn().mockResolvedValue(true)} onApply={apply} demo={false}/>);
  expect((screen.getByRole('button',{name:'Substituir textos atuais'}) as HTMLButtonElement).disabled).toBe(true);
  expect(apply).not.toHaveBeenCalled();
});

it('mudança de contexto após preview bloqueia aplicação e geração em voo é descartada',async()=>{
  const d=draft(),save=vi.fn().mockResolvedValue(true),apply=vi.fn();api.readMetaCampaignDraft.mockResolvedValue({draft:d,version:1});api.suggestMetaCopy.mockResolvedValue(suggestions);
  const view=render(<VarinhaDeCopy draft={d} draftRef="ref" adsetKey="A" save={save} onApply={apply} demo={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Sugerir copies com IA'}));await screen.findByText('Sugestões para revisar');
  view.rerender(<VarinhaDeCopy draft={{...d,destinationUrl:'https://site.com/outro'}} draftRef="ref" adsetKey="A" save={save} onApply={apply} demo={false}/>);
  expect((screen.getByRole('button',{name:'Substituir textos atuais'}) as HTMLButtonElement).disabled).toBe(true);expect(apply).not.toHaveBeenCalled();
  const pending=deferred<typeof suggestions>();api.readMetaCampaignDraft.mockResolvedValue({draft:{...d,destinationUrl:'https://site.com/outro'},version:2});api.suggestMetaCopy.mockReturnValue(pending.promise);fireEvent.click(screen.getByRole('button',{name:'Sugerir copies com IA'}));await waitFor(()=>expect(api.suggestMetaCopy).toHaveBeenCalledTimes(2));
  view.rerender(<VarinhaDeCopy draft={d} draftRef="ref" adsetKey="B" save={save} onApply={apply} demo={false}/>);
  await act(async()=>pending.resolve(suggestions));expect(screen.queryByText('Sugestões para revisar')).toBeNull();expect(screen.getByRole('alert').textContent).toMatch(/contexto mudou/);expect(apply).not.toHaveBeenCalled();
});

it('edição concorrente no servidor impede gerar para contexto diferente mesmo na mesma conta',async()=>{
  const d=draft();api.readMetaCampaignDraft.mockResolvedValue({draft:{...d,destinationUrl:'https://site.com/outra-lp'},version:10});
  render(<VarinhaDeCopy draft={d} draftRef="ref" adsetKey="A" save={vi.fn().mockResolvedValue(true)} onApply={vi.fn()} demo={false}/>);
  fireEvent.click(screen.getByRole('button',{name:'Sugerir copies com IA'}));
  expect((await screen.findByRole('alert')).textContent).toContain('contexto salvo mudou');
  expect(api.suggestMetaCopy).not.toHaveBeenCalled();
});

it('reserva numeração somente após salvar e rejeita mudança de conta enquanto consulta',async()=>{
  const d=draft();delete d.naming!.campaignNumber;const save=vi.fn().mockResolvedValue(true),onChange=vi.fn(),pending=deferred<{account_ref:string;campaign_number:number}>();api.readMetaCampaignDraft.mockResolvedValue({draft:d,version:4});api.reserveMetaNaming.mockReturnValue(pending.promise);
  const view=render(<NomenclaturaAutomatica draft={d} draftRef="ref" save={save} onChange={onChange} sizes={{}} demo={false}/>);
  await waitFor(()=>expect(api.reserveMetaNaming).toHaveBeenCalledWith('ref',4));
  expect(save).toHaveBeenCalledBefore(api.reserveMetaNaming);
  view.rerender(<NomenclaturaAutomatica draft={{...d,accountRef:'account-B'}} draftRef="ref" save={save} onChange={onChange} sizes={{}} demo={false}/>);
  await act(async()=>pending.resolve({account_ref:'account-A',campaign_number:38}));expect(onChange).not.toHaveBeenCalled();expect(screen.getByRole('alert').textContent).toMatch(/conta mudou/);
});

it('identifica o assunto da URL e dispara a organização sem botão intermediário',async()=>{
  const d=draft();delete d.naming!.campaignNumber;delete d.naming!.topicSourceUrl;d.naming!.topic='Assunto anterior';
  api.analyze.mockResolvedValue({assunto_principal:'Renovação da CNH no Brasil',titulo:'Guia',assunto:'CNH'});
  const onChange=vi.fn();
  render(<NomenclaturaAutomatica draft={d} draftRef="ref" save={vi.fn().mockResolvedValue(true)} onChange={onChange} sizes={{}} demo={false}/>);
  await waitFor(()=>expect(api.analyze).toHaveBeenCalledWith(d.destinationUrl),{timeout:1800});
  await waitFor(()=>expect(onChange).toHaveBeenCalled());
  const next=onChange.mock.calls[0][0] as Draft;
  expect(next.naming).toMatchObject({topic:'Renovação da CNH no Brasil',topicSourceUrl:d.destinationUrl,enabled:true});
  expect(screen.queryByRole('button',{name:/reservar número/i})).toBeNull();
});

it('ao trocar a URL atualiza site e tipo automáticos, mas preserva valor manual',async()=>{
  const original=draft(); delete original.naming!.campaignNumber;
  original.naming={...original.naming!,site:'TECHNEWS',landingType:'LP_R',topicSourceUrl:'https://technews.com.br/r/antiga'};
  original.destinationUrl='https://portalnovo.com.br/oferta';
  api.analyze.mockResolvedValue({assunto_principal:'Nova oferta',titulo:'Oferta',assunto:'Oferta'});
  const onChange=vi.fn();
  render(<NomenclaturaAutomatica draft={original} draftRef="ref" save={vi.fn().mockResolvedValue(true)} onChange={onChange} sizes={{}} demo={false}/>);
  await waitFor(()=>expect(onChange).toHaveBeenCalled(),{timeout:1800});
  expect((onChange.mock.calls[0][0] as Draft).naming).toMatchObject({site:'PORTALNOVO',landingType:'',topic:'Nova oferta'});
  cleanup(); onChange.mockClear();
  const manual={...original,naming:{...original.naming!,site:'MARCA_MANUAL',landingType:'LANDER_ESPECIAL'}};
  render(<NomenclaturaAutomatica draft={manual} draftRef="ref" save={vi.fn().mockResolvedValue(true)} onChange={onChange} sizes={{}} demo={false}/>);
  await waitFor(()=>expect(onChange).toHaveBeenCalled(),{timeout:1800});
  expect((onChange.mock.calls[0][0] as Draft).naming).toMatchObject({site:'MARCA_MANUAL',landingType:'LANDER_ESPECIAL'});
});

it('falha no salvamento impede reserva e geração; demo não chama APIs',async()=>{
  const d=draft();delete d.naming!.campaignNumber;const save=vi.fn().mockResolvedValue(false);render(<NomenclaturaAutomatica draft={d} draftRef="ref" save={save} onChange={vi.fn()} sizes={{}} demo={false}/>);await screen.findByRole('alert');expect(api.reserveMetaNaming).not.toHaveBeenCalled();cleanup();
  render(<VarinhaDeCopy draft={d} draftRef="ref" adsetKey="A" save={save} onApply={vi.fn()} demo={true}/>);fireEvent.click(screen.getByRole('button',{name:'Sugerir copies com IA'}));expect((screen.getByRole('button',{name:'Sugerir copies com IA'}) as HTMLButtonElement).disabled).toBe(true);expect(api.suggestMetaCopy).not.toHaveBeenCalled();
});

it('troca de conta invalida o preview da varinha mesmo mantendo textos e destino',async()=>{
  const d=draft(),save=vi.fn().mockResolvedValue(true),apply=vi.fn();api.readMetaCampaignDraft.mockResolvedValue({draft:d,version:1});api.suggestMetaCopy.mockResolvedValue(suggestions);
  const view=render(<VarinhaDeCopy draft={d} draftRef="ref" adsetKey="A" save={save} onApply={apply} demo={false}/>);fireEvent.click(screen.getByRole('button',{name:'Sugerir copies com IA'}));await screen.findByText('Sugestões para revisar');
  view.rerender(<VarinhaDeCopy draft={{...d,accountRef:'account-B'}} draftRef="ref" adsetKey="A" save={save} onApply={apply} demo={false}/>);
  expect((screen.getByRole('button',{name:'Substituir textos atuais'}) as HTMLButtonElement).disabled).toBe(true);
});

it('reserva da conta correta aplica nomes e reserva divergente nunca é aplicada',async()=>{
  const d=draft();delete d.naming!.campaignNumber;const save=vi.fn().mockResolvedValue(true),onChange=vi.fn();api.readMetaCampaignDraft.mockResolvedValue({draft:d,version:3});api.reserveMetaNaming.mockResolvedValue({account_ref:'account-A',campaign_number:48});
  render(<NomenclaturaAutomatica draft={d} draftRef="ref" save={save} onChange={onChange} sizes={{'asset-A':'1080x1350'}} demo={false}/>);await waitFor(()=>expect(onChange).toHaveBeenCalledOnce());
  const applied=onChange.mock.calls[0][0] as Draft;expect(applied.campaignName).toMatch(/^0048 -/);expect(applied.variations[0].creativeName).toContain('1080x1350');cleanup();onChange.mockClear();api.reserveMetaNaming.mockResolvedValue({account_ref:'account-B',campaign_number:99});
  render(<NomenclaturaAutomatica draft={d} draftRef="ref" save={save} onChange={onChange} sizes={{}} demo={false}/>);await screen.findByRole('alert');expect(onChange).not.toHaveBeenCalled();
});

it('varinha não excede cinco opções ao acrescentar e substituição exige clique próprio',async()=>{
  const d=draft(),apply=vi.fn();d.conjuntos[0].flexibleTexts={primary_text:['a','b','c','d','e'],headline:['h'],description:[]};api.readMetaCampaignDraft.mockResolvedValue({draft:d,version:2});api.suggestMetaCopy.mockResolvedValue(suggestions);
  render(<VarinhaDeCopy draft={d} draftRef="ref" adsetKey="A" save={vi.fn().mockResolvedValue(true)} onApply={apply} demo={false}/>);fireEvent.click(screen.getByRole('button',{name:'Sugerir copies com IA'}));await screen.findByText('Sugestões para revisar');expect(apply).not.toHaveBeenCalled();expect((screen.getByRole('button',{name:'Acrescentar ao banco'}) as HTMLButtonElement).disabled).toBe(true);fireEvent.click(screen.getByRole('button',{name:'Substituir textos atuais'}));expect(apply).toHaveBeenCalledWith({primary_text:suggestions.primary_text,headline:suggestions.headline,description:suggestions.description});
});

it('rascunho não salvo impede chamada paga e divergência da conta persistida impede reserva',async()=>{
  const d=draft();render(<VarinhaDeCopy draft={d} draftRef="ref" adsetKey="A" save={vi.fn().mockResolvedValue(false)} onApply={vi.fn()} demo={false}/>);fireEvent.click(screen.getByRole('button',{name:'Sugerir copies com IA'}));await screen.findByRole('alert');expect(api.readMetaCampaignDraft).not.toHaveBeenCalled();expect(api.suggestMetaCopy).not.toHaveBeenCalled();cleanup();
  delete d.naming!.campaignNumber;api.readMetaCampaignDraft.mockResolvedValue({draft:{...d,accountRef:'account-B'},version:2});render(<NomenclaturaAutomatica draft={d} draftRef="ref" save={vi.fn().mockResolvedValue(true)} onChange={vi.fn()} sizes={{}} demo={false}/>);await screen.findByRole('alert');expect(api.reserveMetaNaming).not.toHaveBeenCalled();
});

it('varinha recusa conta ou Página persistida diferente antes da chamada de texto',async()=>{
  for(const mismatch of [{accountRef:'account-B'},{pageRef:'page-B'}]){
    const d=draft();api.readMetaCampaignDraft.mockResolvedValue({draft:{...d,...mismatch},version:7});
    render(<VarinhaDeCopy draft={d} draftRef="ref" adsetKey="A" save={vi.fn().mockResolvedValue(true)} onApply={vi.fn()} demo={false}/>);fireEvent.click(screen.getByRole('button',{name:'Sugerir copies com IA'}));await screen.findByRole('alert');expect(api.suggestMetaCopy).not.toHaveBeenCalled();cleanup();
  }
});
