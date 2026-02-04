# ✅ Checklist de Segurança - WebGo v5.1

## 🎯 Configuração Inicial (URGENTE)

- [ ] **Obter service role key do Supabase**
  - Acessar: https://supabase.com/dashboard/project/txvvzpstquqmbhljudfn/settings/api
  - Copiar chave "service_role" (não a "anon")

- [ ] **Configurar `.env.server`**
  ```bash
  nano .env.server
  # Colar a service role key
  ```

- [ ] **Testar localmente**
  ```bash
  npm run dev:all
  # Abrir http://localhost:5173
  # Fazer login e verificar se funciona
  ```

- [ ] **Verificar que credenciais não estão no Git**
  ```bash
  git status
  # .env.server NÃO deve aparecer na lista
  ```

## 📚 Documentação (RECOMENDADO)

- [ ] Ler [MIGRATION_SECURITY.md](MIGRATION_SECURITY.md) (5 min)
- [ ] Ler [SECURITY_GUIDE.md](SECURITY_GUIDE.md) (15 min)
- [ ] Ler [N8N_INTEGRATION_GUIDE.md](N8N_INTEGRATION_GUIDE.md) (10 min)
- [ ] Guardar documentação em local seguro

## 🔐 Validação de Segurança

- [ ] **Service role key protegida**
  - Abrir DevTools → Sources
  - Buscar por "service" nos arquivos JS
  - ✅ Service role key NÃO deve aparecer

- [ ] **Anon key visível (OK)**
  - Abrir DevTools → Sources
  - Buscar por "anon" nos arquivos JS
  - ✅ Anon key PODE aparecer (é segura)

- [ ] **Backend respondendo**
  ```bash
  curl http://localhost:3001/health
  # Deve retornar: {"status":"ok","message":"Server is running"}
  ```

- [ ] **AuthContext usando API segura**
  - Login deve funcionar normalmente
  - Sem erros no console do navegador

## 🚀 Deploy Produção (QUANDO PRONTO)

### Backend

- [ ] **Escolher plataforma de hosting**
  - [ ] Railway (recomendado)
  - [ ] Heroku
  - [ ] DigitalOcean
  - [ ] Outro: __________

- [ ] **Criar conta na plataforma**

- [ ] **Deploy do backend**
  - [ ] Conectar repositório
  - [ ] Configurar variáveis de ambiente:
    ```
    SUPABASE_URL=https://txvvzpstquqmbhljudfn.supabase.co
    SUPABASE_SERVICE_ROLE_KEY=sua-chave-aqui
    SERVER_PORT=3001
    ALLOWED_ORIGINS=https://seu-dominio-frontend.com
    ```
  - [ ] Deploy
  - [ ] Anotar URL pública: __________

- [ ] **Testar backend em produção**
  ```bash
  curl https://seu-backend.com/health
  ```

### Frontend (Vercel)

- [ ] **Atualizar variável de ambiente**
  - Dashboard Vercel → Settings → Environment Variables
  - Adicionar/Atualizar:
    ```
    VITE_API_URL=https://seu-backend.com
    ```

- [ ] **Rebuild e deploy**
  - Dashboard Vercel → Deployments → Redeploy

- [ ] **Testar em produção**
  - Abrir site
  - Fazer login
  - Verificar funcionalidades

## 🔄 N8N (OPCIONAL)

- [ ] **Decidir estratégia**
  - [ ] Manter N8N chamando Supabase diretamente (recomendado inicialmente)
  - [ ] Migrar N8N para usar backend

- [ ] **Se migrar N8N**:
  - [ ] Configurar `N8N_WEBHOOK_SECRET` no `.env.server`
  - [ ] Adicionar middleware de autenticação
  - [ ] Atualizar workflows N8N um por um
  - [ ] Testar cada workflow
  - [ ] Desativar workflows antigos

## 🔍 Monitoramento Contínuo

- [ ] **Configurar logs**
  - [ ] Backend logando requisições
  - [ ] Frontend logando erros (Sentry?)
  - [ ] N8N logando execuções

- [ ] **Configurar alertas**
  - [ ] Alertas de erro no backend
  - [ ] Alertas de autenticação falhada
  - [ ] Alertas de downtime

- [ ] **Auditoria regular**
  - [ ] Revisar logs semanalmente
  - [ ] Verificar acessos suspeitos
  - [ ] Atualizar dependências mensalmente

## 🔄 Manutenção (PERIÓDICO)

### Mensal
- [ ] Verificar vulnerabilidades
  ```bash
  npm audit
  npm update
  ```

- [ ] Revisar logs de acesso
- [ ] Verificar performance do backend
- [ ] Backup de configurações

### Trimestral
- [ ] Rotacionar `N8N_WEBHOOK_SECRET`
- [ ] Revisar políticas RLS no Supabase
- [ ] Atualizar documentação
- [ ] Audit de segurança completo

### Anual
- [ ] Rotacionar service role key (se necessário)
- [ ] Revisar arquitetura de segurança
- [ ] Treinar equipe em boas práticas
- [ ] Penetration test (se orçamento permitir)

## 🎓 Boas Práticas

- [ ] **Backup de credenciais**
  - [ ] Service role key salva em gerenciador de senhas
  - [ ] `.env.server` em backup seguro (encrypted)
  - [ ] Documentação salva em local seguro

- [ ] **Equipe treinada**
  - [ ] Toda equipe leu documentação
  - [ ] Processos de deploy documentados
  - [ ] Contatos de emergência definidos

- [ ] **Plano de recuperação**
  - [ ] Processo de rollback documentado
  - [ ] Backups testados
  - [ ] Contatos de suporte definidos

## 🆘 Troubleshooting Checklist

Se algo der errado:

- [ ] **Backend não inicia**
  - [ ] Verificar se todas variáveis estão no `.env.server`
  - [ ] Verificar se porta 3001 está livre
  - [ ] Verificar logs de erro

- [ ] **Login não funciona**
  - [ ] Verificar se backend está rodando
  - [ ] Verificar se `VITE_API_URL` está correto
  - [ ] Verificar console do navegador
  - [ ] Verificar logs do backend

- [ ] **CORS error**
  - [ ] Adicionar origin do frontend em `ALLOWED_ORIGINS`
  - [ ] Reiniciar backend
  - [ ] Limpar cache do navegador

- [ ] **N8N não funciona**
  - [ ] Se não migrado: deve funcionar normal
  - [ ] Se migrado: verificar autenticação
  - [ ] Verificar logs do N8N
  - [ ] Testar endpoint com curl

## 📊 Status Tracking

### Progresso Geral

```
[✅] Arquitetura implementada
[✅] Código atualizado
[✅] Dependências instaladas
[✅] Documentação criada
[⏳] Service role key configurada
[⏳] Testes locais realizados
[⏳] Backend em produção
[⏳] Frontend em produção
[⏳] N8N migrado (opcional)
```

### Ambiente

| Ambiente | Frontend | Backend | Status |
|----------|----------|---------|--------|
| Local    | ✅ Pronto | ⏳ Precisa key | 🟡 Parcial |
| Staging  | ⏳ Pendente | ⏳ Pendente | 🔴 Não iniciado |
| Produção | ⏳ Pendente | ⏳ Pendente | 🔴 Não iniciado |

## 🎯 Próximas Ações (Prioridade)

1. **HOJE**:
   - [ ] Configurar service role key
   - [ ] Testar localmente
   - [ ] Ler documentação básica

2. **ESTA SEMANA**:
   - [ ] Escolher plataforma de hosting para backend
   - [ ] Fazer deploy do backend
   - [ ] Atualizar frontend em produção

3. **ESTE MÊS**:
   - [ ] Decidir sobre migração N8N
   - [ ] Configurar monitoramento
   - [ ] Treinar equipe

## ✨ Conclusão

Quando todos os itens acima estiverem marcados:
- ✅ Sistema 100% seguro
- ✅ Credenciais protegidas
- ✅ Pronto para produção
- ✅ Equipe treinada

---

**Data de início**: _________
**Data de conclusão**: _________
**Responsável**: _________
