import { useLocation } from "react-router-dom";
import { useEffect } from "react";

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    console.error("404 Error: User attempted to access non-existent route:", location.pathname);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="text-center space-y-4 animate-scale-in">
        <h1 className="text-6xl font-black text-primary/20">404</h1>
        <p className="text-lg text-muted-foreground">Página não encontrada</p>
        <a
          href="/"
          className="inline-block text-sm text-primary hover:text-primary/80 font-medium transition-colors"
        >
          Voltar ao início
        </a>
      </div>
    </div>
  );
};

export default NotFound;
