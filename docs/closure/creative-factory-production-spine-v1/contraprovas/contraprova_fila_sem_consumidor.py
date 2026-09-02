"""Contraprova: em modo `fila`, o job do Estudio ficava enfileirado para sempre.

Achado do revisor adversarial. O defeito era do proprio conserto de P17-T05:
`DespachoDeFila.despachar_job_do_estudio` devolvia `None`, e a rota respondia 201.

Mas o worker reivindica do deposito da BANCADA (`fila.db` / `criativo_render_job`),
e o job do Estudio vive em `criativo_job` — outra tabela, sem consumidor.
"""
import os, sys
sys.path.insert(0, "backend"); sys.path.insert(0, ".")
os.environ["CRIATIVO_DESPACHO"] = "fila"
os.environ["CRIATIVO_AMBIENTE"] = "vercel"
from app.criativo.bancada.despacho import DespachoIndisponivel, escolher_despachante

d = escolher_despachante()
print("despachante:", d.nome, "| duravel:", d.duravel, "| sincrono:", d.sincrono)

print("--- caminho da BANCADA (o worker consome esta fila) ---")
print("   despachar() ->", d.despachar("trabalho-1"), "(no-op correto: ja esta durável)")

print("--- caminho do ESTUDIO (nenhum worker consome `criativo_job`) ---")
try:
    d.despachar_job_do_estudio("job-1", executor=None)
    print("   NO-OP SILENCIOSO: a rota responderia 201 e o job ficaria queued para sempre")
except DespachoIndisponivel as e:
    print(f"   RECUSOU (correto): {e.motivo[:110]}...")
