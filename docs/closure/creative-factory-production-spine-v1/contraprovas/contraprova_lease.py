"""Contraprova: o deposito SQLite deixa avancar com lease VENCIDO.
O Postgres da v11_03 levanta excecao nesse caso (gatilho transicao_valida)."""
import sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, "backend"); sys.path.insert(0, ".")
from app.criativo.bancada.contrato import Encomenda, EstadoDoTrabalho, SaidaPedida
from app.criativo.bancada.deposito import DepositoDeTrabalhos

d = DepositoDeTrabalhos("/tmp/contraprova-lease.db")
e = Encomenda(receita_id="r", tenant_id="t", motor_slug="m", modo_slug="typography_only",
              finalidade_slug="f", seed=1, saidas=(SaidaPedida("a",10,10,"imagem","image/png"),))
t, criado = d.enfileirar(e)
t = d.reivindicar("op-1", lease_s=1)
print("reivindicado:", t.estado.value, "lease_ate:", t.lease_ate, "vivo:", t.vivo)
time.sleep(1.4)
t2 = d.por_id(t.id)
print("apos 1.4s -> vivo:", t2.vivo, "(lease VENCIDO)")
try:
    r = d.transicionar(t.id, EstadoDoTrabalho.RUNNING, exigir_operario="op-1")
    print("RESULTADO: avancou para", r.estado.value, "COM LEASE VENCIDO  <-- DEFEITO")
    r2 = d.transicionar(t.id, EstadoDoTrabalho.VALIDATING, exigir_operario="op-1")
    print("RESULTADO: avancou para", r2.estado.value, "COM LEASE VENCIDO  <-- DEFEITO")
except Exception as ex:
    print("RECUSOU (correto):", type(ex).__name__, ex)
