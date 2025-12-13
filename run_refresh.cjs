const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');

const supabaseUrl = 'https://mmnwlheukncqabsdrrby.supabase.co';
const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1tbndsaGV1a25jcWFic2RycmJ5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTczMzUxODYyMywiZXhwIjoyMDQ5MDk0NjIzfQ.d5cn7CCOdQQOEq_8YScAOEedmYdl1TcKGKuzXzU0r0F68';

const supabase = createClient(supabaseUrl, supabaseKey);

(async () => {
  try {
    const today = new Date().toISOString().split('T')[0];

    console.log('🗑️ 1. Limpando dados de hoje...');
    try {
      const { error: delError } = await supabase
        .from('campaign_highlights')
        .delete()
        .eq('highlighted_at', today);

      if (delError) {
        console.warn('⚠️ Erro ao limpar:', delError.message);
      } else {
        console.log('✅ Dados limpos');
      }
    } catch (delErr) {
      console.warn('⚠️ Não foi possível limpar dados. Continuando...');
    }

    console.log('\n📝 2. Aplicando nova função via migration...');
    const sql = fs.readFileSync('./src/sql/refresh_campaign_highlights.sql', 'utf-8');

    try {
      const { data: migData, error: migError } = await supabase.rpc('apply_migration', {
        name: 'update_refresh_v4_' + Date.now(),
        query: sql
      });

      if (migError) {
        console.warn('⚠️ Migration não disponível, tentando direto...');
        console.log(migError.message);
      } else {
        console.log('✅ Migration aplicada');
      }
    } catch (err) {
      console.warn('⚠️ Erro ao aplicar, tentando executar função existente...');
    }

    console.log('\n▶️ 3. Executando refresh_campaign_highlights...');
    const { data, error } = await supabase.rpc('refresh_campaign_highlights');

    if (error) {
      console.error('❌ Erro ao executar:', error);
      process.exit(1);
    }

    console.log('✅ Refresh executado!');
    console.log('Primeiros resultados:', JSON.stringify(data.slice(0, 3), null, 2));
    console.log(`\nTotal inserido: ${data.length} campanhas`);

    // Verificar distribuição
    console.log('\n📊 Verificando distribuição...');
    const { data: dist, error: distError } = await supabase
      .from('campaign_highlights')
      .select('category')
      .eq('highlighted_at', today);

    if (distError) throw distError;

    const counts = {};
    dist.forEach(row => {
      counts[row.category] = (counts[row.category] || 0) + 1;
    });

    console.log('Distribuição por categoria:');
    console.log(JSON.stringify(counts, null, 2));

  } catch (err) {
    console.error('❌ Erro fatal:', err.message || err);
    process.exit(1);
  }
})();
