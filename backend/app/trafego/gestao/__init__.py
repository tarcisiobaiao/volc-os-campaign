"""Gestão de campanhas que JÁ ESTÃO no ar, ligada ao ledger de autogestão v10_02.

O motor (`volc_ads.gestao`) sabe montar, ensaiar e desfazer cada ação; o banco
(`supabase/migrations/v10_02_autogestao.sql`) sabe o que é permitido. Este pacote
só costura os dois — e é por isso que ele é fino:

  application/     casos de uso (propor, aprovar, aplicar, verificar, reverter,
                   importar, recomendações) e as portas que eles pedem. Nenhum
                   HTTP, nenhum PostgREST, nenhum SDK do Google no import.
  infrastructure/  o repositório PostgREST das nove tabelas da v10_02 e o
                   adaptador do Google Ads sobre `volc_ads.gestao`.

O router (`app/routers/trafego_gestao.py`) só traduz HTTP ↔ caso de uso.

⚠️ A regra mora no banco. Toda recusa que este pacote faz ANTES de gravar
(limite, frescor, aprovação, carência) é espelho de um gatilho da v10_02, e
existe só para a recusa virar mensagem antes de deixar linha órfã. Quem garante
é o gatilho: um script solto que pule este pacote é recusado do mesmo jeito.
"""
