# 🔐 Guia de Migração para Arquitetura Segura

> **ARQUIVADO:** migração histórica; não representa sozinho a arquitetura self-hosted atual.

## ✅ O que foi feito

### 1. Servidor Backend Seguro
- ✅ Criado servidor Express em `/server/index.js`
- ✅ Endpoints proxy para operações do Supabase
- ✅ Proteção de credenciais sensíveis

### 2. Cliente API Seguro
- ✅ Criado `/src/lib/secureApi.ts`
- ✅ Métodos para query, insert, update, delete e RPC
- ✅ TypeScript com tipos seguros

### 3. Atualização do AuthContext
- ✅ [AuthContext.tsx:48-84](src/contexts/AuthContext.tsx#L48-L84) agora usa `secureApi.queryUsers()`
- ✅ Removida exposição direta das credenciais

### 4. Variáveis de Ambiente
- ✅ `.env.local` - Configuração pública segura
- ✅ `.env.server` - Credenciais privadas (não commitado)
- ✅ `.env.server.example` - Template para equipe

### 5. Proteção Git
- ✅ `.gitignore` atualizado para bloquear arquivos sensíveis
- ✅ `.env.server` protegido

## 🚀 Próximos Passos

### Passo 1: Configurar Service Role Key

Você precisa obter a **service role key** do Supabase:

1. Acesse: https://supabase.com/dashboard/project/txvvzpstquqmbhljudfn/settings/api
2. Copie a chave **service_role** (não a anon key)
3. Edite o arquivo `.env.server`:
   ```bash
   nano .env.server
   ```
4. Cole a service role key:
   ```env
   SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...sua-chave-aqui
   ```

### Passo 2: Testar o Sistema

```bash
# Terminal 1 - Iniciar backend
npm run dev:server

# Terminal 2 - Iniciar frontend
npm run dev

# Ou executar ambos juntos:
npm run dev:all
```

### Passo 3: Verificar Funcionamento

1. Abra http://localhost:5173
2. Tente fazer login
3. Verifique no console do navegador se não há erros
4. Verifique no terminal do servidor se as requisições estão chegando

### Passo 4: Migrar Outros Serviços (Opcional)

Se você quiser migrar outros serviços que fazem chamadas diretas ao Supabase:

#### Exemplo - Antes (Inseguro):
```typescript
const { data } = await supabase
  .from('campaigns')
  .select('*')
  .eq('status', 'Active');
```

#### Exemplo - Depois (Seguro):
```typescript
import { secureApi } from '@/lib/secureApi';

const data = await secureApi.query({
  table: 'campaigns',
  select: '*',
  filters: [
    { field: 'status', operator: 'eq', value: 'Active' }
  ]
});
```

## ⚠️ IMPORTANTE: Para Produção

### 1. Deploy do Backend

O backend precisa estar rodando em um servidor. Opções:

- **Railway**: Deploy com 1 clique
- **Heroku**: Plataforma tradicional
- **DigitalOcean**: Mais controle
- **AWS/GCP**: Para escala maior

### 2. Atualizar Variável de Ambiente

No Vercel (ou onde seu frontend está):

```env
VITE_API_URL=https://seu-backend-api.railway.app
```

### 3. Configurar CORS

No `.env.server` de produção:

```env
ALLOWED_ORIGINS=https://seu-dominio-frontend.vercel.app
```

## 🔍 Verificando Segurança

### Antes (INSEGURO) ❌
Abra DevTools → Network → Inspecione qualquer arquivo JS:
```javascript
// Credenciais VISÍVEIS no código do navegador
const supabaseKey = "eyJhbG...service-role-key..."
```

### Depois (SEGURO) ✅
Abra DevTools → Network → Inspecione qualquer arquivo JS:
```javascript
// Apenas anon key visível (segura para expor)
const supabaseAnonKey = "eyJhbG...anon-key..."
// Service role key NUNCA aparece no frontend
```

## 🔐 Compatibilidade com N8N

O N8N pode continuar chamando o Supabase diretamente (ele roda no servidor), MAS recomendamos também passar pelo backend para:

1. **Logs centralizados**: Todas operações em um lugar
2. **Controle de acesso**: Validação adicional
3. **Rate limiting**: Prevenir abuso

### Exemplo de Webhook N8N Seguro

```javascript
// No N8N, ao invés de chamar Supabase diretamente:
// POST https://txvvzpstquqmbhljudfn.supabase.co/rest/v1/...

// Chame seu backend:
// POST https://seu-backend.com/api/supabase/insert
{
  "table": "daily_campaign_metrics",
  "data": { ... }
}
```

## 📊 Status Atual

| Componente | Status | Notas |
|-----------|--------|-------|
| Backend API | ✅ Criado | Precisa rodar em produção |
| Frontend | ✅ Atualizado | AuthContext usando API segura |
| Variáveis de Ambiente | ✅ Configurado | Precisa service role key |
| .gitignore | ✅ Protegido | Credenciais não vão para Git |
| Documentação | ✅ Completa | Ver SECURITY_GUIDE.md |
| Testes | ⏳ Pendente | Testar após configurar keys |
| Deploy Produção | ⏳ Pendente | Backend precisa ser hospedado |

## 🆘 Troubleshooting

### Erro: "Cannot find module 'express'"
```bash
npm install
```

### Erro: "Missing Supabase environment variables"
Configure o `.env.server` com a service role key.

### Erro: "CORS blocked"
Adicione o origin do frontend em `ALLOWED_ORIGINS` no `.env.server`.

### Frontend não conecta ao backend
1. Verifique se o backend está rodando (porta 3001)
2. Verifique se `VITE_API_URL` está correto no `.env.local`
3. Reinicie ambos os servidores

## 📞 Próximo Passo Imediato

**AÇÃO NECESSÁRIA**: Configure a service role key no `.env.server` para poder testar o sistema.

```bash
# 1. Obter a key do Supabase dashboard
# 2. Editar .env.server
# 3. Executar: npm run dev:all
# 4. Testar login em http://localhost:5173
```

## 🎯 Benefícios da Migração

✅ **Segurança**: Credenciais protegidas no backend
✅ **Controle**: Centralização de acesso ao banco
✅ **Auditoria**: Logs de todas operações
✅ **Flexibilidade**: Fácil adicionar validações
✅ **Escalabilidade**: Rate limiting e caching futuros
