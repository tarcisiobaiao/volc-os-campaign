import React, { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { pautadorApi } from '@/lib/pautadorApi';
import type { ConjuntoDraft } from './rascunho';

type Catalogo = Awaited<ReturnType<typeof pautadorApi.identidadesRegulatoriasMeta>>;

/** A saved selection is intent only. Backend re-resolves against this account. */
export function IdentidadeDoAnunciante({ accountRef, conjunto, onChange, demo = false, disabled = false, consultar = pautadorApi.identidadesRegulatoriasMeta }: {
  accountRef: string; conjunto: ConjuntoDraft;
  onChange: (ref: string) => void; demo?: boolean; disabled?: boolean;
  /** Page-owned reader, replaced whenever the authenticated owner/session changes. */
  consultar?: (accountRef: string) => Promise<Catalogo>;
}) {
  const [catalogo, setCatalogo] = useState<{account: string; reader: typeof consultar; data: Catalogo} | null>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState('');
  const [candidateRef, setCandidateRef] = useState('');
  const requestId = useRef(0);
  useEffect(() => { requestId.current++; setLoading(false); setErro('');
    return () => { requestId.current++; };
  }, [accountRef, consultar]);
  useEffect(() => { setCandidateRef(''); }, [accountRef, conjunto.key, consultar]);
  const data = catalogo?.account === accountRef && catalogo.reader === consultar ? catalogo.data : null;
  const selected = data?.items.find(item => item.reference === conjunto.regulatoryIdentityRef);
  const candidate = selected || data?.items.find(item => item.reference === candidateRef)
    || (data?.items.length === 1 ? data.items[0] : undefined);
  async function ler() {
    const ticket = ++requestId.current;
    setLoading(true); setErro(''); setCatalogo(null);
    try {
      const result = await consultar(accountRef);
      if (ticket !== requestId.current) return;
      if (!result.complete || !Array.isArray(result.items)) throw new Error('A consulta não terminou. Nenhuma identificação pode ser escolhida com uma lista incompleta.');
      setCatalogo({account: accountRef, reader: consultar, data: result});
    } catch (error) {
      if (ticket === requestId.current) setErro(error instanceof Error ? error.message : 'Não foi possível consultar as identificações desta conta.');
    } finally { if (ticket === requestId.current) setLoading(false); }
  }
  useEffect(() => {
    if (accountRef && !demo) void ler();
  }, [accountRef, demo, consultar]);
  const id = `meta-advertiser-${conjunto.key}`;
  return <section aria-labelledby={`${id}-title`} className="space-y-3 border-t border-border pt-5">
    <div>
      <h3 id={`${id}-title`} className="text-base font-semibold">Identificação do anunciante</h3>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">Confirme quem anuncia e quem paga pelos anúncios de {conjunto.nome}.</p>
    </div>
    {erro && <Button type="button" variant="secondary" disabled={loading || disabled || demo || !accountRef} onClick={() => void ler()}>Tentar consulta novamente</Button>}
    {demo && <p className="text-sm text-muted-foreground">Demonstração: nenhuma identificação real será consultada.</p>}
    {loading && <div role="status" aria-live="polite" className="rounded-md bg-muted p-4 text-sm">Consultando os responsáveis na Meta…</div>}
    {erro && <p role="alert" className="text-sm text-destructive">{erro}</p>}
    {data && data.items.length > 0 && <div className="space-y-2">
      {data.items.length > 1 && !selected && <><label htmlFor={id} className="block text-sm font-medium">Anunciante e pagador</label>
      <select id={id} className="min-h-11 w-full rounded-md border border-input bg-card px-3 text-sm" value={candidateRef}
        disabled={disabled || demo} onChange={event => setCandidateRef(event.target.value)} aria-describedby={`${id}-help`}>
        <option value="">Escolha os responsáveis</option>
        {data.items.map(item => <option key={item.reference} value={item.reference}>{item.label}</option>)}
      </select></>}
      {conjunto.regulatoryIdentityRef && !selected && <p role="alert" className="text-sm text-destructive">A identificação salva não está disponível nesta consulta. Confirme novamente os responsáveis.</p>}
      {candidate && <dl className="grid gap-4 rounded-md border border-border bg-card p-4 sm:grid-cols-2">
        <div><dt className="text-sm text-muted-foreground">Anunciante</dt><dd className="mt-1 break-words font-semibold">{candidate.beneficiary_name || 'Nome não disponibilizado pela Meta'}</dd></div>
        <div><dt className="text-sm text-muted-foreground">Pagador</dt><dd className="mt-1 break-words font-semibold">{candidate.payer_name || 'Nome não disponibilizado pela Meta'}</dd></div>
      </dl>}
      <p id={`${id}-help`} className="max-w-prose text-sm text-muted-foreground">Esta confirmação identifica os responsáveis. Não copia conjuntos, anúncios ou configurações. A elegibilidade será conferida ao validar o plano.</p>
      {candidate && !selected && <Button type="button" disabled={disabled || demo} onClick={() => onChange(candidate.reference)}>Confirmar anunciante e pagador</Button>}
      {selected && <Button type="button" variant="outline" disabled={disabled || demo} onClick={() => { setCandidateRef(''); onChange(''); }}>Alterar responsáveis</Button>}
    </div>}
    {data?.items.length === 0 && <p role="status" className="text-sm">Não encontramos um cadastro reutilizável nesta consulta. Confira a identificação de anunciante e pagador nas Configurações de publicidade da Meta.</p>}
    {conjunto.regulatoryIdentityRef && (!data || selected) && <p role="status" className="text-sm font-medium">Responsáveis confirmados neste conjunto. A escolha acompanha o salvamento do rascunho.</p>}
    <a href="https://adsmanager.facebook.com/adsmanager/manage/ad_account_settings" target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center text-sm text-primary underline underline-offset-4">Abrir configurações de publicidade na Meta (nova aba)</a>
  </section>;
}
