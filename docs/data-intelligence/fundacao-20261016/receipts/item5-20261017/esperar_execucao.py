"""Espera (polling de 20 s, máximo N minutos) uma execução do workflow iniciada depois de T terminar. Só GET.
Uso: esperar_execucao.py <workflow_id> <iso_inicio_minimo> <max_min>. Imprime id curto, status e horários."""
import sys, time, datetime as dt
sys.path.insert(0, __import__("os").path.dirname(__file__))
from n8n_cliente import chamar
wid, desde, maxmin = sys.argv[1], dt.datetime.fromisoformat(sys.argv[2].replace("Z", "+00:00")), float(sys.argv[3])
fim = time.time() + 60 * maxmin
while time.time() < fim:
    for e in chamar("GET", "/executions", consulta={"workflowId": wid, "limit": 5, "includeData": "false"}).get("data", []):
        ini = dt.datetime.fromisoformat(e["startedAt"].replace("Z", "+00:00"))
        if ini >= desde and e.get("stoppedAt"):
            print(e["id"], e["status"], e["startedAt"], e["stoppedAt"]); sys.exit(0 if e["status"] == "success" else 2)
    time.sleep(20)
print("timeout"); sys.exit(3)
