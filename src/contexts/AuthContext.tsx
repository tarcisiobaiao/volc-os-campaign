import { createContext, useContext, useEffect, useState } from "react";
import { User, Session } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";

export interface UserProfile {
  id?: number;
  name?: string;
  email?: string;
  role?: 'ADMIN' | 'OPERATOR' | 'VIEWER';
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
      // Try to get user profile from users table
      const { data: profile, error } = await supabase
        .from('users')
        .select('*')
        .eq('id', user.id)
        .single();

      if (error) {
        // Try alternative query by email
        const { data: profileAlt, error: errorAlt } = await supabase
          .from('users')
          .select('*')
          .eq('email', user.email)
          .single();

        if (profileAlt) {
          setUserProfile(profileAlt);
          return true;
        } else {
          console.warn('❌ User not authorized - email not found in users table:', user.email);
          setUserProfile(null);
          setUnauthorizedUser(user.email || 'Email não disponível');
          // Sign out unauthorized user
          await supabase.auth.signOut();
          return false;
        }
      } else {
        setUserProfile(profile);
        return true;
      }
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
      console.log('🔐 Auth state changed:', event, session?.user?.email);

      if (session?.user) {
        const isAuthorized = await fetchUserProfile(session.user);
        if (isAuthorized) {
          setSession(session);
          setUser(session.user);
        } else {
          setSession(null);
          setUser(null);
          // unauthorizedUser já foi setado no fetchUserProfile
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
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/`
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