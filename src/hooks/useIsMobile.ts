import { useState, useEffect } from 'react';

/**
 * Hook para detectar se o viewport é mobile (< 768px)
 * Breakpoint: 768px (md em Tailwind)
 */
export function useIsMobile(breakpoint: number = 768): boolean {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < breakpoint);
    };

    // Check inicial
    checkMobile();

    // Listener para resize
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, [breakpoint]);

  return isMobile;
}
