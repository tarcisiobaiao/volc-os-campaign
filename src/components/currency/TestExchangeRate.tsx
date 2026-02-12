import React from "react";

export const TestExchangeRate: React.FC = () => {
  return (
    <div className="w-full p-4 bg-red-100 border-2 border-red-500 rounded-lg">
      <h2 className="text-red-800 font-bold text-xl">🚨 TESTE - Taxa de Câmbio</h2>
      <p className="text-red-600">Se você está vendo isso, o componente está sendo renderizado!</p>
      <button 
        className="mt-2 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
        onClick={() => alert('Componente funcionando!')}
      >
        Testar Clique
      </button>
    </div>
  );
};