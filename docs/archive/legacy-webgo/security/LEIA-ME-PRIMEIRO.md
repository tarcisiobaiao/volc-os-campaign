# 🚨 LEIA-ME PRIMEIRO - Atualização de Segurança

> **ARQUIVADO:** instruções do WebGo/Supabase hospedado anterior. A fonte atual é `CLAUDE.md`.

## ⚠️ AÇÃO IMEDIATA NECESSÁRIA

Implementamos proteção de segurança para suas credenciais do banco de dados. O sistema está **pronto**, mas precisa de **1 configuração** antes de funcionar.

## 🔐 O QUE FOI FEITO

Suas credenciais do Supabase estavam expostas no código JavaScript do navegador. Agora elas estão protegidas em um backend seguro.

```
ANTES: Frontend → Supabase (credenciais expostas ❌)
AGORA:  Frontend → Backend Seguro → Supabase (credenciais protegidas ✅)
```

## ✅ 3 PASSOS PARA ATIVAR

### PASSO 1: Obter Service Role Key (2 minutos)

1. Abra: https://supabase.com/dashboard/project/txvvzpstquqmbhljudfn/settings/api
2. Encontre a seção "Project API keys"
3. Copie a chave **"service_role"** (não a "anon")

### PASSO 2: Configurar Backend (1 minuto)

Abra o arquivo `.env.server` e cole a chave:

```bash
nano .env.server

# Cole a chave na linha:
SUPABASE_SERVICE_ROLE_KEY=sua-chave-aqui
```

Salve e feche (Ctrl+X, depois Y, depois Enter).

### PASSO 3: Testar (2 minutos)

```bash
# Executar frontend e backend juntos
npm run dev:all

# Abrir no navegador
open http://localhost:5173

# Fazer login e verificar se funciona ✅
```

**Pronto! Sistema seguro e funcionando.**

## 📚 DOCUMENTAÇÃO COMPLETA

Leia nesta ordem:

1. **[README_SECURITY_UPDATE.md](README_SECURITY_UPDATE.md)** - Resumo geral
2. **[MIGRATION_SECURITY.md](MIGRATION_SECURITY.md)** - O que mudou e porquê
3. **[SECURITY_GUIDE.md](SECURITY_GUIDE.md)** - Guia técnico completo
4. **[N8N_INTEGRATION_GUIDE.md](N8N_INTEGRATION_GUIDE.md)** - Como N8N continua funcionando
5. **[SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md)** - Checklist completo

## ❓ PERGUNTAS FREQUENTES

### O N8N vai parar de funcionar?
**NÃO!** O N8N pode continuar funcionando exatamente como está. A migração é opcional.

### Preciso mudar tudo agora?
**NÃO!** Apenas configure a service role key e teste. O resto pode ser feito gradualmente.

### Quanto tempo leva?
- Configuração inicial: **5 minutos**
- Ler documentação: **30 minutos**
- Deploy em produção: **1-2 horas** (quando estiver pronto)

### Isso é urgente?
**SIM** para desenvolvimento local (para você testar).
**IMPORTANTE** mas não urgente para produção (pode planejar o deploy).

## 🚀 PRÓXIMOS PASSOS

Depois de testar localmente:

1. **Ler documentação** (recomendado)
2. **Planejar deploy do backend** (Railway, Heroku, etc.)
3. **Atualizar variáveis de ambiente no Vercel**
4. **Decidir sobre migração do N8N** (opcional)

## 🆘 PRECISA DE AJUDA?

- **Não consegue encontrar a service role key?** → Veja [SECURITY_GUIDE.md](SECURITY_GUIDE.md) seção "Configuração Inicial"
- **Erro ao rodar o backend?** → Veja [SECURITY_GUIDE.md](SECURITY_GUIDE.md) seção "Troubleshooting"
- **Dúvidas sobre N8N?** → Veja [N8N_INTEGRATION_GUIDE.md](N8N_INTEGRATION_GUIDE.md)

## 📋 ARQUIVOS IMPORTANTES

### NÃO COMMITAR (já protegido):
- `.env.server` ← Contém service role key

### PODE COMMITAR:
- `.env.local` ← Só tem anon key (pública)
- `.env.server.example` ← Template sem credenciais
- Toda documentação

## ✨ BENEFÍCIOS

- ✅ Credenciais protegidas no backend
- ✅ Código mais seguro
- ✅ Pronto para auditoria
- ✅ N8N compatível
- ✅ Fácil de escalar

---

**Configure agora e teste em 5 minutos!**

Depois, leia a documentação com calma para entender todo o sistema.
