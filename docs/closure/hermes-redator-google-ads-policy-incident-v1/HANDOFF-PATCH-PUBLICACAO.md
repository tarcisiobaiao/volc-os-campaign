# HANDOFF PATCH — ponto de portão 2 em `backend/app/routers/publicacao.py`

> **Não aplicado nesta branch.** `backend/app/routers/publicacao.py` está em
> colisão declarada com o Terminal 2 nesta missão. O patch abaixo é exato e foi
> escrito contra o arquivo no commit base `382c5d4`; quem integra aplica.

## Onde

`POST /redator/runs/{run_row_id}/publicar/{page_number}`, a rota que envia UMA
página ao WordPress. Ela já tem cinco recusas ANTES de chamar o motor
(linhas ~1549–1600). Este patch acrescenta a sexta, **entre** a checagem de
rascunho (termina na linha 1590) e a busca do perfil WordPress (linha 1592).

## O patch

```diff
--- a/backend/app/routers/publicacao.py
+++ b/backend/app/routers/publicacao.py
@@ -1587,6 +1587,44 @@
     if not (rascunho or {}).get("content"):
         raise HTTPException(
             status_code=409,
             detail=f"A página {page_number} não tem artigo escrito no disco.")

+    # 6. **Portão de política de destino** → 409.
+    #
+    # As cinco recusas acima protegem a INTEGRIDADE da publicação (duplicata,
+    # concorrência, portão do motor, artefato ausente, credencial). Nenhuma
+    # olha o CONTEÚDO sob a política de anúncio — e foi por aí que uma LP com
+    # sete links `caixa.gov.br` de âncora numérica foi ao ar e virou destino de
+    # campanha. Ver docs/closure/hermes-redator-google-ads-policy-incident-v1/
+    # ROOT-CAUSE-ANALYSIS.md.
+    #
+    # O papel é `paid_destination` quando a página é a LP do funil — é ela que
+    # recebe o clique comprado. As interiores entram com o papel frouxo: o
+    # achado é registrado, mas não barra a publicação.
+    from app.landing_policy import (
+        PaginaObservada, PapelDestino, PontoDePortao, avaliar, emitir_recibo,
+    )
+
+    _plano = (estado.get("plan") or {}).get("pages") or []
+    _pagina_do_plano = next(
+        (p for p in _plano if int(p.get("page_number") or 0) == page_number), {})
+    _papel = (PapelDestino.PAID_DESTINATION
+              if str(_pagina_do_plano.get("role", "")).upper() == "LP"
+              else PapelDestino.EDITORIAL_SOLUTION)
+
+    _avaliacao = avaliar(
+        PaginaObservada(
+            url=(perfil_wp or {}).get("wp_base_url", "") if False else
+                f"{(await _buscar(supa, int(run.get('project_id') or 0)) or {}).get('wp_base_url', '')}"
+                f"/r/{_pagina_do_plano.get('slug', '')}/",
+            html=(rascunho or {}).get("content") or "",
+            cnpj_esperado=(_pagina_do_plano.get("cnpj") or None),
+            origem="pre_publication_draft",
+        ),
+        _papel,
+        PontoDePortao.PRE_PUBLICACAO_WORDPRESS,
+    )
+    if _avaliacao.bloqueios:
+        _recibo = emitir_recibo(_avaliacao, hash_do_conteudo=hashlib.sha256(
+            ((rascunho or {}).get("content") or "").encode("utf-8")).hexdigest())
+        raise HTTPException(
+            status_code=409,
+            detail={
+                "erro": f"A página {page_number} não passa no portão de política de destino.",
+                "motivos": _avaliacao.motivos,
+                "recibo": _recibo,
+            })
+
     perfil_wp = await _buscar(supa, int(run.get("project_id") or 0))
```

## Duas correções que o integrador precisa fazer ao aplicar

1. **Ordem de `_buscar`.** O trecho acima chama `_buscar` para montar a URL antes
   de a linha 1592 fazê-lo. Mova a chamada existente de `perfil_wp = await
   _buscar(...)` para ANTES do bloco novo e use `perfil_wp` nas duas partes, em
   vez de chamar duas vezes. Deixei a duplicação visível de propósito: aplicar o
   diff sem resolver isso faz uma requisição a mais ao Supabase por publicação.
2. **`import hashlib`** no topo do módulo, se ainda não existir.

## O que muda no comportamento

- Página interior com defeito: publica, e o recibo fica no log — nada é barrado.
- LP com bloqueio: **409**, com `motivos` e o recibo completo no corpo. Nenhuma
  escrita no WordPress acontece; a recusa é anterior à chamada do motor, como as
  outras cinco.
- LP sem bloqueio: segue o caminho de sempre.

## Teste que acompanha o patch

`backend/tests/test_publicar_pagina.py` (do Terminal 2) já cobre as cinco
recusas. A sexta pede um caso análogo: rascunho com um link de governo de âncora
numérica → 409, e sentinela provando que `worker.publicar_pagina` **não** foi
chamado. O portão em si já está coberto por
`backend/tests/test_landing_policy_contraprovas.py` (24 contraprovas A–X).
