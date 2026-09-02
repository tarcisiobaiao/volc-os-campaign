"""Contraprova: as rotas de leitura do Estudio ignoram o dono do job.

Achado do revisor adversarial (Codex gpt-5.6-sol), reproduzido aqui contra as
FUNCOES REAIS de `backend/app/routers/criativos.py`.

`obter_job` e `listar_jobs` ligam a identidade a `_` — literalmente descartam —
e chamam o repositorio sem filtro de dono. E o repositorio nao filtra sozinho:
`persistencia.buscar_job` consulta `id=eq.<uuid>` e `listar_jobs` nem tem
parametro de dono.

O comentario da rota IRMA, na bancada, ja tinha escrito a regra:
"O UUID nao e autorizacao: buscar sem o filtro faria esta rota diferir das rotas
de leitura/listagem". A bancada aplicou; o Estudio nao.
"""
import asyncio, sys
sys.path.insert(0, "backend"); sys.path.insert(0, ".")
from app.routers.criativos import listar_jobs, obter_job
from app.criativo.armazenamento import Assinador
from app.seguranca.identidade import Identidade

JOB_A = "11111111-1111-4111-8111-111111111111"
JOB_B = "22222222-2222-4222-8222-222222222222"


class RepoQueSeComportaComoOReal:
    """Devolve por id, sem olhar dono — que e o que `persistencia.py` faz."""

    def __init__(self):
        self.jobs = {
            JOB_A: {"id": JOB_A, "briefing_id": "b-a", "motor": "gemini",
                    "motor_versao": "1", "estado": "succeeded",
                    "criado_por": "usuario-A", "criado_em": "2026-09-01"},
            JOB_B: {"id": JOB_B, "briefing_id": "b-b", "motor": "gemini",
                    "motor_versao": "1", "estado": "succeeded",
                    "criado_por": "usuario-B", "criado_em": "2026-09-01"},
        }

    async def buscar_job(self, job_id, *, criado_por=None):
        job = self.jobs.get(job_id)
        # Espelha o `eq.` do PostgREST: com filtro, nao devolve linha de outro dono.
        if job is not None and criado_por is not None and job["criado_por"] != criado_por:
            return None
        return job

    async def listar_jobs(self, *, estados=None, limite=20, criado_por=None):
        linhas = list(self.jobs.values())
        if criado_por is not None:
            linhas = [j for j in linhas if j["criado_por"] == criado_por]
        return linhas[:limite]
    async def renditions_do_job(self, job_id): return []
    async def ultimo_seq(self, job_id): return 0
    async def buscar_briefing(self, briefing_id):
        return {"projeto_id": "p", "tipo": "imagem", "modo": "full_llm"}
    async def buscar_projeto(self, projeto_id):
        return {"titulo": "BRIEFING CONFIDENCIAL DO USUARIO A"}


async def main():
    repo, ass = RepoQueSeComportaComoOReal(), Assinador("s" * 32)
    b = Identidade(sub="usuario-B", email="b@x", papel="", origem="sessao")

    print("--- B pede o job de A pelo UUID ---")
    try:
        dto = await obter_job(JOB_A, b, repo, ass)
        print(f"   VAZOU: B recebeu o job de A -> projetoTitulo={dto.get('projetoTitulo')!r}")
    except Exception as e:
        print(f"   RECUSOU (correto): {type(e).__name__}: {e}")

    print("--- B lista os jobs ---")
    try:
        saida = await listar_jobs(identidade=b, repo=repo, assinador=ass, estado=None, limite=20)
        print(f"   B viu {len(saida['jobs'])} job(s)")
        print("   VAZOU: a listagem atravessa inquilino"
              if len(saida["jobs"]) > 1 else "   OK: so os proprios")
    except Exception as e:
        print(f"   RECUSOU: {type(e).__name__}: {e}")

asyncio.run(main())
