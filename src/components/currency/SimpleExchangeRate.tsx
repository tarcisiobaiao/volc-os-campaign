import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DollarSign } from "lucide-react";

export const SimpleExchangeRate: React.FC = () => {
  const [rate, setRate] = useState<string>("5.50");

  return (
    <Card className="shadow-lg bg-gradient-to-br from-green-50 to-emerald-50 border-green-200">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-green-800">
          <DollarSign className="h-5 w-5" />
          Taxa de Câmbio USD/BRL
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
          />
          <Button className="bg-green-600 hover:bg-green-700">
            Atualizar
          </Button>
        </div>
        <p className="text-sm text-green-700 mt-2">
          Taxa atual: R$ {rate} por USD
        </p>
      </CardContent>
    </Card>
  );
};