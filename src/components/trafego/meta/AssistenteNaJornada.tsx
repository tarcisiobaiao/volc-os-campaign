import React, { forwardRef, useState } from 'react';

/** Keep the live studio URL stable while it reports its newly created project.
 * On re-entry, resume the durable project instead of creating a second one. */
export const AssistenteNaJornada = forwardRef<HTMLIFrameElement, { projeto: string | null }>(
  function AssistenteNaJornada({ projeto }, ref) {
    const [url] = useState(() => projeto
      ? `/trafego/meta/assistente-criativo/${projeto}?view=assets`
      : '/trafego/meta/assistente-criativo?view=briefing');
    return <iframe ref={ref} title="Assistente Criativo da campanha" data-meta-assistant="true"
      src={url} className="meta-journey-assistant" />;
  },
);
