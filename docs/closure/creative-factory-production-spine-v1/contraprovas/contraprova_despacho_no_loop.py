"""Contraprova dos dois defeitos criticos do despacho, pela FUNCAO REAL.

Antes da correcao, rodando de dentro de um event loop (que e onde a rota
`async def criar_job` roda):

    caminho 1 (DespachoSincronoLocal.despachar_job_do_estudio):
        NoEventLoopError: Not running inside an AnyIO worker thread
    caminho 2 (Executor._registrar_indisponibilidade, o fail-closed):
        RuntimeError: Already running asyncio in this thread

Depois, os dois completam.
"""
import asyncio, sys
sys.path.insert(0, "backend"); sys.path.insert(0, ".")


class ExecutorFalso:
    def __init__(self): self.vistos = []
    async def _executar_protegido(self, job_id):
        self.vistos.append(job_id)


async def main():
    from app.criativo.bancada.despacho import DespachoSincronoLocal, _rodar_corrotina_em_thread

    print("--- caminho 1: despachar de dentro da thread do event loop ---")
    ex = ExecutorFalso()
    try:
        DespachoSincronoLocal().despachar_job_do_estudio("job-1", ex)
        print(f"   OK: o executor recebeu {ex.vistos}")
    except BaseException as e:
        print(f"   ESTOUROU: {type(e).__name__}: {e}")

    print("--- caminho 2: marcar a indisponibilidade de dentro do loop ---")
    marcado = []
    async def marcar():
        marcado.append("failed")
    try:
        _rodar_corrotina_em_thread(marcar)
        print(f"   OK: o job foi marcado {marcado}")
    except BaseException as e:
        print(f"   ESTOUROU: {type(e).__name__}: {e}")

    print("--- caminho 3: a excecao do trabalho NAO e engolida ---")
    async def explode():
        raise ValueError("o motor recusou")
    try:
        _rodar_corrotina_em_thread(explode)
        print("   ENGOLIU (defeito): a rota responderia 201 sobre producao que falhou")
    except ValueError as e:
        print(f"   OK: subiu como {type(e).__name__}: {e}")

asyncio.run(main())
