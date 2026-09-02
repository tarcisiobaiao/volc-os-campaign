"""Contraprova 2: SQLite aceita `rendered` com recibo SEM artefato.
Postgres v11_03: 'nao se conclui sem recibo COM artefato'."""
import sys
sys.path.insert(0, "backend"); sys.path.insert(0, ".")
from app.criativo.bancada.contrato import Encomenda, EstadoDoTrabalho, SaidaPedida
from app.criativo.bancada.deposito import DepositoDeTrabalhos

d = DepositoDeTrabalhos("/tmp/contraprova-recibo.db")
e = Encomenda(receita_id="r", tenant_id="t", motor_slug="m", modo_slug="typography_only",
              finalidade_slug="f", seed=2, saidas=(SaidaPedida("a",10,10,"imagem","image/png"),))
d.enfileirar(e)
t = d.reivindicar("op-1", lease_s=600)
d.transicionar(t.id, EstadoDoTrabalho.RUNNING, exigir_operario="op-1")
d.transicionar(t.id, EstadoDoTrabalho.VALIDATING, exigir_operario="op-1")
try:
    r = d.transicionar(t.id, EstadoDoTrabalho.RENDERED,
                       recibo={"assinatura_determinista": "x", "artefatos": []},
                       exigir_operario="op-1")
    print("RESULTADO: concluiu como", r.estado.value, "com recibo de ZERO artefatos <-- DEFEITO")
    print("           recibo gravado:", r.recibo)
except Exception as ex:
    print("RECUSOU (correto):", type(ex).__name__, ex)
