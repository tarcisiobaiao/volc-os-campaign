import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { BootSplash } from './components/BootSplash'
import './index.css'

createRoot(document.getElementById("root")!).render(
  <>
    <App />
    <BootSplash />
  </>
);
