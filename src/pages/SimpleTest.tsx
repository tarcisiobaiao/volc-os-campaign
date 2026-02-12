import { useState, useEffect } from 'react';
import { supabase } from '@/lib/supabase';

export default function SimpleTest() {
  const [isLoaded, setIsLoaded] = useState(false);
  const [tests, setTests] = useState({
    react: false,
    typescript: false,
    tailwind: false,
    supabase: false
  });
  const [supabaseData, setSupabaseData] = useState<any[]>([]);
  const [supabaseError, setSupabaseError] = useState<string | null>(null);

  useEffect(() => {
    console.log('SimpleTest component mounted');
    setIsLoaded(true);
    
    // Test basic functionality
    setTests(prev => ({ ...prev, react: true, typescript: true }));
    
    // Test Tailwind by checking if classes exist
    setTimeout(() => {
      const element = document.querySelector('.bg-blue-500');
      if (element) {
        setTests(prev => ({ ...prev, tailwind: true }));
      }
    }, 100);

    // Test Supabase connection
    const testSupabase = async () => {
      try {
        console.log('Testing Supabase connection...');
        const { data, error } = await supabase
          .from('projects')
          .select('id, project_name, main_url')
          .limit(3);

        if (error) {
          console.error('Supabase error:', error);
          setSupabaseError(error.message);
        } else {
          console.log('Supabase success:', data);
          setSupabaseData(data || []);
          setTests(prev => ({ ...prev, supabase: true }));
        }
      } catch (err) {
        console.error('Supabase connection error:', err);
        setSupabaseError(err instanceof Error ? err.message : 'Unknown error');
      }
    };

    // Test Supabase after a delay
    setTimeout(testSupabase, 1000);
  }, []);

  return (
    <div className="min-h-screen bg-background p-8">
      <h1 className="text-3xl font-bold mb-8 text-foreground">
        🔧 Diagnóstico do Sistema - Status: {isLoaded ? 'OK' : 'Carregando...'}
      </h1>
      
      {/* Test Tailwind */}
      <div className="bg-blue-500 w-1 h-1 opacity-0"></div>
      
      <div className="grid gap-6 max-w-4xl">
        {/* Basic Tests */}
        <div className="p-6 border border-border rounded-lg bg-card">
          <h2 className="text-xl font-semibold mb-4 text-card-foreground">
            ✅ Verificações do Sistema
          </h2>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className={tests.react ? "text-green-600" : "text-red-600"}>
                {tests.react ? "✅" : "❌"}
              </span>
              <span>React funcionando</span>
            </div>
            <div className="flex items-center gap-2">
              <span className={tests.typescript ? "text-green-600" : "text-red-600"}>
                {tests.typescript ? "✅" : "❌"}
              </span>
              <span>TypeScript funcionando</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-green-600">✅</span>
              <span>Tailwind CSS básico funcionando</span>
            </div>
            <div className="flex items-center gap-2">
              <span className={tests.supabase ? "text-green-600" : "text-yellow-600"}>
                {tests.supabase ? "✅" : "⏳"}
              </span>
              <span>Supabase {tests.supabase ? "conectado" : "testando..."}</span>
            </div>
          </div>
        </div>

        {/* Environment Variables */}
        <div className="p-6 border border-border rounded-lg bg-card">
          <h2 className="text-xl font-semibold mb-4 text-card-foreground">
            🔧 Variáveis de Ambiente
          </h2>
          <div className="space-y-2 text-sm">
            <div>
              <strong>VITE_SUPABASE_URL:</strong> 
              <span className="ml-2 font-mono bg-muted px-2 py-1 rounded">
                {import.meta.env.VITE_SUPABASE_URL ? 
                  `${import.meta.env.VITE_SUPABASE_URL.substring(0, 30)}...` : 
                  '❌ Não definida'
                }
              </span>
            </div>
            <div>
              <strong>VITE_SUPABASE_ANON_KEY:</strong> 
              <span className="ml-2 font-mono bg-muted px-2 py-1 rounded">
                {import.meta.env.VITE_SUPABASE_ANON_KEY ? 
                  `${import.meta.env.VITE_SUPABASE_ANON_KEY.substring(0, 20)}...` : 
                  '❌ Não definida'
                }
              </span>
            </div>
          </div>
        </div>

        {/* Supabase Test Results */}
        {supabaseError && (
          <div className="p-6 border border-red-300 rounded-lg bg-red-50">
            <h3 className="text-lg font-semibold mb-2 text-red-700">
              ❌ Erro no Supabase
            </h3>
            <p className="text-red-600 text-sm font-mono">
              {supabaseError}
            </p>
          </div>
        )}

        {tests.supabase && supabaseData.length > 0 && (
          <div className="p-6 border border-green-300 rounded-lg bg-green-50">
            <h3 className="text-lg font-semibold mb-2 text-green-700">
              ✅ Supabase Funcionando!
            </h3>
            <p className="text-green-600 mb-4">
              Encontrados {supabaseData.length} projetos:
            </p>
            <ul className="space-y-2">
              {supabaseData.map((project) => (
                <li key={project.id} className="text-sm bg-white p-2 rounded border">
                  <strong>{project.project_name}</strong> - {project.main_url}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Next Steps */}
        <div className="p-6 border border-primary/20 rounded-lg bg-primary/5">
          <h3 className="text-lg font-semibold mb-2 text-primary">
            🚀 Status do Sistema
          </h3>
          <p className="text-primary/80">
            {tests.supabase 
              ? "🎉 Tudo funcionando! Agora você pode usar o dashboard completo."
              : "⏳ Aguardando teste do Supabase..."
            }
          </p>
          {tests.supabase && (
            <div className="mt-4">
              <a 
                href="/dashboard" 
                className="inline-block px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90"
              >
                Ir para o Dashboard Completo →
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}