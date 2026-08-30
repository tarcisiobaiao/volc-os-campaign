import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DollarSign } from "lucide-react";

export const SimpleExchangeRate: React.FC = () => {
  const [rate, setRate] = useState<string>("5.50");

  return (
    <Card className="relative overflow-hidden shadow-card hover-lift reveal" style={{ ['--i' as any]: 0 }}>
      <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-success" />
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="rounded-md bg-success/10 text-success p-1.5">
            <DollarSign className="h-4 w-4" />
          </span>
          <span className="kicker">Taxa de Câmbio USD/BRL</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex gap-2">
          <Input
            type="number"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            placeholder="5.50"
            step="0.01"
            className="tabular"
          />
          <Button>
            Atualizar
          </Button>
        </div>
        <p className="text-sm text-muted-foreground mt-2">
          Taxa atual: <span className="font-display tabular text-foreground">R$ {rate}</span> por USD
        </p>
      </CardContent>
    </Card>
  );
};