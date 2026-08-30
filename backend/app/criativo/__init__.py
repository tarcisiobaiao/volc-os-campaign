"""O Estúdio Criativo — camada de aplicação e infraestrutura.

    dominio.py         regra pura: idempotência, formatos, estado, sanitização
    persistencia.py    PostgREST sobre o Supabase oficial, só transporte
    armazenamento.py   object storage e a URL assinada que substitui o caminho
    execucao.py        o executor de jobs, fora do request
    apresentacao.py    a última fronteira antes do browser
    video_observado.py leitura de um build da fábrica externa
    video_ponte.py     o build observado no contrato do Estúdio

Nenhum arquivo daqui publica, gasta mídia ou fala com Google e Meta.
"""
