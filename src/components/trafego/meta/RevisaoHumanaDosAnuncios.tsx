import type { ReactNode } from 'react';
import type { Draft, VariacaoDraft } from './rascunho';
import { textosFlexiveisDoConjunto } from './rascunho';
import { Escolha } from './primitivas';

/** Campaign-context attestations. Pack approval is a separate stored decision. */
export function RevisaoHumanaDosAnuncios({ draft, anuncios, bloqueado, onCategoria, onAnuncio, preview }: {
  draft: Draft;
  anuncios: VariacaoDraft[];
  bloqueado: boolean;
  onCategoria: (value: boolean) => void;
  onAnuncio: (key: string, value: boolean) => void;
  preview: (anuncio: VariacaoDraft) => ReactNode;
}) {
  return <section aria-labelledby="meta-revisao-humana" className="space-y-4">
    <div>
      <h3 id="meta-revisao-humana" className="font-display text-xl font-semibold">Revise os anúncios desta campanha</h3>
      <p className="mt-2 max-w-[70ch] text-sm text-muted-foreground">
        A aprovação do pack cuida das imagens. Aqui você confirma seu uso com estes textos,
        neste destino e nesta campanha. As confirmações são humanas, sem análise de IA.
      </p>
    </div>
    {bloqueado ? <p className="text-sm text-warning">Conclua o envio e a montagem do pack antes de revisar os anúncios. Os anúncios anteriores não serão aprovados no lugar dele.</p>
      : <div className="divide-y divide-border">{anuncios.map((ad, index) => <article key={ad.key} className="grid gap-4 py-5 first:pt-0 sm:grid-cols-[136px_1fr]">
        <div>{preview(ad)}</div>
        <div className="min-w-0 space-y-3">
          <div>
            <p className="text-xs text-muted-foreground">Anúncio {index + 1} · {draft.conjuntos.find(c => c.key === ad.adsetKey)?.nome || 'Conjunto não encontrado'}</p>
            <h4 className="mt-1 font-semibold">{ad.adName || 'Anúncio sem nome'}</h4>
          </div>
          <div className="max-w-[65ch] space-y-1 break-words text-sm">
            {draft.creativeMode === 'flexible' ? <div className="space-y-3 rounded-lg border border-border bg-muted/30 p-3">
              <p className="font-semibold">Textos compartilhados deste anúncio flexível</p>
              <p className="text-muted-foreground">Esta imagem pode aparecer com qualquer uma das opções abaixo.</p>
              {(['primary_text', 'headline', 'description'] as const).map(tipo => {
                const textos = textosFlexiveisDoConjunto(draft, ad.adsetKey)[tipo];
                if (!textos.length && tipo === 'description') return null;
                return <div key={tipo}>
                  <p className="text-xs font-semibold text-muted-foreground">{tipo === 'primary_text' ? 'Textos principais' : tipo === 'headline' ? 'Títulos' : 'Descrições'}</p>
                  <ol className="mt-1 list-decimal space-y-1 pl-5">{textos.map((texto, i) => <li key={i}>{texto || 'Opção ainda não preenchida.'}</li>)}</ol>
                </div>;
              })}
            </div> : <>
              <p>{ad.message || 'Texto principal ainda não preenchido.'}</p>
              <p className="font-semibold">{ad.headline || 'Título ainda não preenchido.'}</p>
              {ad.description && <p className="text-muted-foreground">{ad.description}</p>}
            </>}
            <p className="text-muted-foreground">Destino: {draft.destinationUrl || 'Ainda não informado'}</p>
          </div>
          <Escolha marcado={ad.assetRightsConfirmed && ad.thirdPartyIdentityCleared}
            desabilitado={!ad.assetRef || ad.midia !== 'image'}
            onChange={value => onAnuncio(ad.key, value)}
            titulo={`Aprovo o uso da imagem no anúncio ${index + 1}`}>
            Revisei {draft.creativeMode === 'flexible' ? 'esta imagem com todas as opções de texto acima' : 'a combinação acima'}. A imagem é própria ou licenciada para mídia paga e não contém
            marcas, logos ou identidades de terceiros sem autorização. Ao mudar imagem ou texto, confirmarei novamente.
          </Escolha>
        </div>
      </article>)}</div>}
    <Escolha marcado={draft.categoryConfirmed} desabilitado={bloqueado} onChange={onCategoria}
      titulo="Esta campanha não é de crédito, emprego, moradia nem política">
      Confirme o enquadramento desta campanha. Aprovar um pack não faz essa declaração por você.
    </Escolha>
    <p className="max-w-[70ch] text-xs text-muted-foreground">Estas confirmações não publicam anúncios nem garantem aprovação pela Meta. O próximo passo confere o plano.</p>
  </section>;
}
