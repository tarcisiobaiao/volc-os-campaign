import { useEffect, useState } from 'react';
import { supabase } from '@/lib/supabase';

export const SupabaseTest = () => {
  const [status, setStatus] = useState('Testando...');
  const [projects, setProjects] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const testConnection = async () => {
      try {
        console.log('Testando conexão com Supabase...');
        
        // Teste básico de conexão
        const { data, error } = await supabase
          .from('projects')
          .select('*')
          .limit(3);

        if (error) {
          console.error('Erro Supabase:', error);
          setError(error.message);
          setStatus('Erro na conexão');
        } else {
          console.log('Sucesso! Dados recebidos:', data);
          setProjects(data || []);
          setStatus('Conectado com sucesso');
        }
      } catch (err) {
        console.error('Erro geral:', err);
        setError(err instanceof Error ? err.message : 'Erro desconhecido');
        setStatus('Erro na conexão');
      }
    };

    testConnection();
  }, []);

  return (
    <div className="p-4 m-4 border rounded-lg bg-white">
      <h2 className="text-lg font-bold mb-4">Teste de Conexão Supabase</h2>
      
      <div className="mb-4">
        <strong>Status:</strong> {status}
      </div>
      
      {error && (
        <div className="mb-4 p-2 bg-red-100 border border-red-300 rounded text-red-700">
          <strong>Erro:</strong> {error}
        </div>
      )}
      
      <div className="mb-4">
        <strong>Projetos encontrados:</strong> {projects.length}
      </div>
      
      {projects.length > 0 && (
        <div>
          <h3 className="font-semibold mb-2">Primeiro projeto:</h3>
          <pre className="bg-gray-100 p-2 rounded text-sm overflow-auto">
            {JSON.stringify(projects[0], null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};