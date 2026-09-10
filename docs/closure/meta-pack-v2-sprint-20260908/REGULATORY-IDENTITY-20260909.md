# Identificação regulatória e recuperação da tentativa parcial

Estado: LOCAL_VERIFIED_REMOTE_COMPLETION_PENDING. Roadmap P11-T09/P11-T11 partial; cap_meta_ads.

## Evidência observada

- Ledger do Supabase oficial e GET Meta confirmaram uma campanha raiz PAUSED, sem conjuntos.
- Business verificado não equivale ao vínculo regulatório exigido no conjunto.
- Catálogo completo da conta leu 32 conjuntos; quatro contêm a mesma identidade de beneficiário/pagador. A projeção pública oferece uma referência opaca, não seus IDs.
- Nenhum POST Meta, alteração de identidade/geografia, geração paga ou migration nesta correção.

## Alterações

Consulta explícita no estágio de revisão, seleção independente por conjunto e campo opcional no contrato do rascunho. Catálogo relido pelo backend, limitado à própria conta, paginação completa e sem escolha automática. Escopo inicial Brasil sem segmentação subnacional. Identidade selecionada participa do payload e hash do plano V2 e da conferência após criação; planos sem seleção mantêm o contrato anterior.

Código/subcódigo numérico do provedor não sofre máscara destinada a identificadores. Diagnóstico específico para anunciante ausente orienta a escolha sem prometer que histórico equivale a aprovação atual da Meta.

Nova aprovação passa a selecionar seu próprio recibo, preservando link da tentativa anterior. Recibo incluído no erro é preservado mesmo quando o GET posterior falha. Reutilização da campanha raiz depende de payload idêntico e das guardas duráveis existentes: não mudar nome, objetivo ou orçamento durante essa correção se pretende reaproveitar a raiz.

## Verificação

- Backend focal: 150 passed.
- Frontend focal: quatro arquivos, 59 passed.
- Build Vite passou; avisos herdados não representam aceite TypeScript global.
- Chrome isolado: 375/768/1440, claro/escuro, teclado, seleção por conjunto e nenhum overflow/erro. Usa catálogo fixture e bloqueia rede externa; não é QA autenticado.
- Frontend localhost HTTP200; nova rota sem autenticação HTTP401, preservando acesso restrito.

## Próximo teste humano

No mesmo rascunho, Revisão → Identificação do anunciante → Consultar identificações na Meta. Escolher apenas se anunciante e pagador são de fato os responsáveis por esta campanha. Conferir, validar e aprovar o plano atualizado antes da criação PAUSED. A aceitação remota de conjunto/anúncio continua pendente; ativação permanece proibida.

## Fontes

SDK oficial Meta: https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adaccount.py e https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/regionalregulationidentities.py. Campos corroborados por GET real da própria conta. Algumas páginas developers.facebook.com limitaram acesso; não se atribui a elas leitura integral.
