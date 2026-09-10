import { useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { Input } from '@/components/ui/input';

export function useBuscaPaginada() {
  const [texto, setTexto] = useState('');
  const [consulta, setConsulta] = useState({ q: '', offset: 0 });
  useEffect(() => {
    const timer = window.setTimeout(() => setConsulta({ q: texto.trim(), offset: 0 }), 300);
    return () => window.clearTimeout(timer);
  }, [texto]);
  return { texto, setTexto, consulta, setConsulta };
}
export function BuscaBiblioteca({ value, onChange, label = 'Buscar por nome' }: {
  value: string; onChange: (value: string) => void; label?: string;
}) {
  return <label className="relative block max-w-xl"><span className="sr-only">{label}</span>
    <Search className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-muted-foreground" aria-hidden />
    <Input type="search" value={value} onChange={e => onChange(e.target.value)} placeholder={label}
      maxLength={120} className="min-h-11 pl-10" />
  </label>;
}
