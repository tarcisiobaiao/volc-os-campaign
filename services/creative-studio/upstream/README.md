# Aprova Concursos — Estúdio de Criativos

Gerador de criativos com IA para campanhas Aprova Concursos.

## Desenvolvimento

```bash
npm install
npm run dev
```

Configure `VITE_API_URL` no `.env` para apontar o front para o backend FastAPI
(veja `.env.example`).

## Backend local

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

Copie `backend/.env.example` para `backend/.env` e preencha as chaves reais.

## Deploy na Vercel

Use um único repositório GitHub e crie dois Vercel Projects apontando para ele:

1. `aprova-ad-studio-web`
   - Root Directory: `.`
   - Framework Preset: Vite
   - Build Command: `npm run build`
   - Output Directory: `dist`
   - Env: `VITE_API_URL=https://<api-project>.vercel.app/generate`

2. `aprova-ad-studio-api`
   - Root Directory: `backend`
   - Framework Preset: Other
   - Python entrypoint: `app.main:app` via `backend/pyproject.toml`
   - Env: variáveis de `backend/.env.example`, incluindo:
     - `OPENAI_API_KEY`
     - `GEMINI_API_KEY`
     - `CORS_ORIGINS=https://<web-project>.vercel.app,http://localhost:8089,http://localhost:3000`

Depois do primeiro deploy, teste:

```bash
curl https://<api-project>.vercel.app/health
```
