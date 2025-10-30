#!/bin/bash

# Script para limpar todos os caches do projeto

echo "🧹 Limpando caches do Vite..."
rm -rf node_modules/.vite

echo "🧹 Limpando dist..."
rm -rf dist

echo "🧹 Limpando cache do navegador (localStorage)..."
cat > clear-cache.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>Clear Cache</title>
</head>
<body>
    <h1>Limpando cache...</h1>
    <script>
        localStorage.clear();
        sessionStorage.clear();
        console.log('Cache limpo!');
        alert('Cache do navegador limpo! Feche esta aba e recarregue o aplicativo.');
    </script>
</body>
</html>
EOF

echo "✅ Caches limpos!"
echo ""
echo "📋 Próximos passos:"
echo "1. Abra http://localhost:8081/clear-cache.html no navegador"
echo "2. Feche a aba do clear-cache"
echo "3. Recarregue http://localhost:8081/dashboard/projects"
echo ""












