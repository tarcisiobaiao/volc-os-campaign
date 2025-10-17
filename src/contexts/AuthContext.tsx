import { createContext, useContext, useEffect, useState } from "react";
import { User, Session } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";

export interface UserProfile {
  id?: string; // UUID
  name?: string;
  email?: string;
  role?: 'ADMIN' | 'OPERATOR';
  needs_password_change?: boolean;
  created_at?: string;
  updated_at?: string;
}

interface AuthContextType {
  user: User | null;
  session: Session | null;
  userProfile: UserProfile | null;
  loading: boolean;
  unauthorizedUser: string | null; // Email do usuário não autorizado
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  clearUnauthorizedUser: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};

interface AuthProviderProps {
  children: React.ReactNode;
}

export const AuthProvider = ({ children }: AuthProviderProps) => {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [unauthorizedUser, setUnauthorizedUser] = useState<string | null>(null);

  const fetchUserProfile = async (user: User | null): Promise<boolean> => {
    if (!user) {
      setUserProfile(null);
      return false;
    }

    try {
      // Use REST API directly as Supabase JS client has connection issues
      const response = await fetch(`${import.meta.env.VITE_SUPABASE_URL}/rest/v1/users?select=*&email=eq.${user.email}`, {
        headers: {
          'apikey': import.meta.env.VITE_SUPABASE_ANON_KEY,
          'Authorization': `Bearer ${import.meta.env.VITE_SUPABASE_ANON_KEY}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const profiles = await response.json();
        if (profiles && profiles.length > 0) {
          setUserProfile(profiles[0]);
          return true;
        }
      }

      // User not found
      console.warn('User not authorized - email not found in users table:', user.email);
      setUserProfile(null);
      setUnauthorizedUser(user.email || 'Email não disponível');
      await supabase.auth.signOut();
      return false;
    } catch (error) {
      console.error('Error fetching user profile:', error);
      setUserProfile(null);
      setUnauthorizedUser(user.email || 'Email não disponível');
      await supabase.auth.signOut();
      return false;
    }
  };

  useEffect(() => {
    // Get initial session
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (session?.user) {
        const isAuthorized = await fetchUserProfile(session.user);
        if (isAuthorized) {
          setSession(session);
          setUser(session.user);
        } else {
          setSession(null);
          setUser(null);
        }
      } else {
        setSession(null);
        setUser(null);
        setUserProfile(null);
      }
      setLoading(false);
    });

    // Listen for auth changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (session?.user) {
        const isAuthorized = await fetchUserProfile(session.user);
        if (isAuthorized) {
          setSession(session);
          setUser(session.user);
        } else {
          setSession(null);
          setUser(null);
        }
      } else {
        setSession(null);
        setUser(null);
        setUserProfile(null);
      }
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);

  const signIn = async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    if (error) {
      throw error;
    }
  };

  const signInWithGoogle = async () => {
    // Detecta automaticamente o ambiente e URL de redirecionamento
    const isLocalhost = window.location.hostname === 'localhost'
    const redirectUrl = isLocalhost
      ? window.location.origin + '/'  // Usar localhost em desenvolvimento
      : (import.meta.env.VITE_SITE_URL || window.location.origin) + '/'  // Usar produção em produção

    console.log('🔐 Google OAuth redirect URL:', redirectUrl)
    console.log('🌍 Environment:', isLocalhost ? 'Development (localhost)' : 'Production')

    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: redirectUrl
      }
    });
    if (error) {
      throw error;
    }
  };

  const signOut = async () => {
    const { error } = await supabase.auth.signOut();
    if (error) {
      throw error;
    }
  };

  const clearUnauthorizedUser = () => {
    setUnauthorizedUser(null);
  };

  const value = {
    user,
    session,
    userProfile,
    loading,
    unauthorizedUser,
    signIn,
    signInWithGoogle,
    signOut,
    clearUnauthorizedUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};