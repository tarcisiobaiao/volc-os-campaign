import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { ArrowLeft, Plus, Edit, Trash2, Save, BarChart3 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from '@/hooks/use-toast';

interface CostItem {
  id: string;
  name: string;
  amount: number;
  category: 'pessoas' | 'infraestrutura' | 'administrativo';
}

interface TaxHistory {
  month: string;
  percentage: number;
}

export default function CostsSettings() {
  const navigate = useNavigate();
  const [selectedMonth, setSelectedMonth] = useState('2025-08');
  const [currentTaxRate, setCurrentTaxRate] = useState(8.1);
  const [editingItem, setEditingItem] = useState<CostItem | null>(null);
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [newItemCategory, setNewItemCategory] = useState<'pessoas' | 'infraestrutura' | 'administrativo'>('pessoas');

  const [costItems, setCostItems] = useState<CostItem[]>([
    // Pessoas
    { id: '1', name: 'Salários Equipe', amount: 4500.00, category: 'pessoas' },
    { id: '2', name: 'FGTS', amount: 360.00, category: 'pessoas' },
    { id: '3', name: 'Benefícios', amount: 180.00, category: 'pessoas' },
    // Infraestrutura
    { id: '4', name: 'Servidor/Hosting', amount: 89.00, category: 'infraestrutura' },
    { id: '5', name: 'Domínios', amount: 45.00, category: 'infraestrutura' },
    { id: '6', name: 'Ferramentas', amount: 197.00, category: 'infraestrutura' },
    { id: '7', name: 'CDN/Performance', amount: 67.00, category: 'infraestrutura' },
    // Administrativo
    { id: '8', name: 'Aluguel Escritório', amount: 800.00, category: 'administrativo' },
    { id: '9', name: 'Viagens', amount: 300.00, category: 'administrativo' },
    { id: '10', name: 'Contabilidade', amount: 250.00, category: 'administrativo' },
  ]);

  const taxHistory: TaxHistory[] = [
    { month: 'Jul/25', percentage: 7.9 },
    { month: 'Jun/25', percentage: 7.7 },
    { month: 'Mai/25', percentage: 7.5 },
  ];

  const getCategoryTotal = (category: 'pessoas' | 'infraestrutura' | 'administrativo') => {
    return costItems
      .filter(item => item.category === category)
      .reduce((total, item) => total + item.amount, 0);
  };

  const getTotalCosts = () => {
    return costItems.reduce((total, item) => total + item.amount, 0);
  };

  const getCategoryTitle = (category: 'pessoas' | 'infraestrutura' | 'administrativo') => {
    switch (category) {
      case 'pessoas': return '👥 PESSOAS';
      case 'infraestrutura': return '🖥️ INFRAESTRUTURA';
      case 'administrativo': return '🏢 ADMINISTRATIVO';
    }
  };

  const handleSaveItem = (item: Partial<CostItem>) => {
    if (editingItem) {
      setCostItems(prev => prev.map(i => i.id === editingItem.id ? { ...i, ...item } : i));
      setEditingItem(null);
    } else {
      const newItem: CostItem = {
        id: Date.now().toString(),
        name: item.name || '',
        amount: item.amount || 0,
        category: newItemCategory,
      };
      setCostItems(prev => [...prev, newItem]);
      setIsAddDialogOpen(false);
    }
    toast({ title: "Item salvo com sucesso!" });
  };

  const handleDeleteItem = (id: string) => {
    setCostItems(prev => prev.filter(item => item.id !== id));
    toast({ title: "Item removido com sucesso!" });
  };

  const handleSaveChanges = () => {
    toast({ title: "Alterações salvas com sucesso!" });
  };

  const ItemDialog = ({ item, category }: { item?: CostItem; category?: 'pessoas' | 'infraestrutura' | 'administrativo' }) => {
    const [name, setName] = useState(item?.name || '');
    const [amount, setAmount] = useState(item?.amount || 0);

    return (
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{item ? 'Editar Item' : 'Adicionar Item'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label htmlFor="name">Nome do Item</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Digite o nome do item"
            />
          </div>
          <div>
            <Label htmlFor="amount">Valor (R$)</Label>
            <Input
              id="amount"
              type="number"
              value={amount}
              onChange={(e) => setAmount(parseFloat(e.target.value) || 0)}
              placeholder="0,00"
              step="0.01"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => { setEditingItem(null); setIsAddDialogOpen(false); }}>
              Cancelar
            </Button>
            <Button onClick={() => handleSaveItem({ name, amount })}>
              Salvar
            </Button>
          </div>
        </div>
      </DialogContent>
    );
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate('/settings')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="text-2xl font-bold">⚙️ Configurações &gt; Custos</h1>
        </div>
      </div>

      {/* Month Selector */}
      <div className="flex items-center gap-4">
        <Label htmlFor="month">📅 Mês de Referência:</Label>
        <Select value={selectedMonth} onValueChange={setSelectedMonth}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="2025-08">Agosto 2025</SelectItem>
            <SelectItem value="2025-07">Julho 2025</SelectItem>
            <SelectItem value="2025-06">Junho 2025</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Taxes Section */}
      <Card>
        <CardHeader>
          <CardTitle>💰 IMPOSTOS</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <Label>Percentual Atual:</Label>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  value={currentTaxRate}
                  onChange={(e) => setCurrentTaxRate(parseFloat(e.target.value) || 0)}
                  step="0.1"
                  className="w-20"
                />
                <span>% (Simples Nacional)</span>
              </div>
            </div>
            <div>
              <Label>Vigência:</Label>
              <p>Agosto/2025</p>
            </div>
            <div>
              <Label>Histórico:</Label>
              <p className="text-sm text-muted-foreground">
                {taxHistory.map(h => `${h.month}: ${h.percentage}%`).join(' | ')}
              </p>
            </div>
          </div>
          <Button variant="outline" size="sm">
            <Edit className="h-4 w-4 mr-2" />
            Alterar Percentual
          </Button>
        </CardContent>
      </Card>

      {/* Cost Categories */}
      {(['pessoas', 'infraestrutura', 'administrativo'] as const).map(category => (
        <Card key={category}>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>{getCategoryTitle(category)}</CardTitle>
            <Dialog open={isAddDialogOpen && newItemCategory === category} onOpenChange={(open) => {
              setIsAddDialogOpen(open);
              if (open) setNewItemCategory(category);
            }}>
              <DialogTrigger asChild>
                <Button variant="outline" size="sm" onClick={() => setNewItemCategory(category)}>
                  <Plus className="h-4 w-4 mr-2" />
                  Adicionar
                </Button>
              </DialogTrigger>
              <ItemDialog category={category} />
            </Dialog>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {costItems.filter(item => item.category === category).map(item => (
                <div key={item.id} className="flex items-center justify-between p-3 border rounded-lg">
                  <div className="flex items-center gap-3">
                    <span>•</span>
                    <span>{item.name}</span>
                    <span className="font-medium">R$ {item.amount.toFixed(2).replace('.', ',')}</span>
                  </div>
                  <div className="flex gap-2">
                    <Dialog open={editingItem?.id === item.id} onOpenChange={(open) => {
                      if (!open) setEditingItem(null);
                      else setEditingItem(item);
                    }}>
                      <DialogTrigger asChild>
                        <Button variant="ghost" size="sm">
                          <Edit className="h-4 w-4" />
                        </Button>
                      </DialogTrigger>
                      <ItemDialog item={editingItem!} />
                    </Dialog>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDeleteItem(item.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
              <div className="pt-3 border-t">
                <p className="font-semibold">
                  Subtotal {category.charAt(0).toUpperCase() + category.slice(1)}: R$ {getCategoryTotal(category).toFixed(2).replace('.', ',')}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}

      {/* Total Summary */}
      <Card className="border-2 border-primary">
        <CardContent className="p-6">
          <div className="text-center space-y-2">
            <h3 className="text-xl font-bold">💎 TOTAL CUSTOS OPERACIONAIS: R$ {getTotalCosts().toFixed(2).replace('.', ',')}</h3>
            <p className="text-sm text-muted-foreground">(Não inclui impostos - calculados automaticamente)</p>
          </div>
        </CardContent>
      </Card>

      {/* Action Buttons */}
      <div className="flex gap-4">
        <Button onClick={handleSaveChanges}>
          <Save className="h-4 w-4 mr-2" />
          💾 Salvar Alterações
        </Button>
        <Button variant="outline">
          <BarChart3 className="h-4 w-4 mr-2" />
          📊 Ver Histórico
        </Button>
      </div>
    </div>
  );
}