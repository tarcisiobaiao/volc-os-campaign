import { useState, useEffect } from 'react';
import { User } from '@supabase/supabase-js';
import { supabase } from '@/lib/supabase';
import { useAuth } from '@/contexts/AuthContext';

export interface UserProfile {
  id?: number;
  name?: string;
  email?: string;
  role?: 'ADMIN' | 'OPERATOR' | 'VIEWER';
  created_at?: string;
  updated_at?: string;
}

export function useUserProfile() {
  const { user, userProfile: contextUserProfile } = useAuth();
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Use profile from context if available, otherwise use local state
  const currentProfile = contextUserProfile || userProfile;

  const getUserFirstName = (): string => {
    if (!user) return "Usuário";
    
    // First try to get name from users table
    if (currentProfile?.name) {
      return currentProfile.name.split(' ')[0];
    }
    
    // Try multiple possible fields for the name from auth
    const fullName = user.user_metadata?.full_name || 
                    user.user_metadata?.name || 
                    user.identities?.[0]?.identity_data?.name ||
                    user.identities?.[0]?.identity_data?.full_name;
    
    if (fullName) {
      return fullName.split(' ')[0]; // Get first name
    }
    
    // Fallback to email prefix if no name is available
    if (user.email) {
      return user.email.split('@')[0].charAt(0).toUpperCase() + user.email.split('@')[0].slice(1);
    }
    
    return "Usuário";
  };

  const fetchUserProfile = async () => {
    // If we already have profile from context, don't fetch again
    if (contextUserProfile || !user) return;

    setLoading(true);
    setError(null);

    try {
      console.log('Fetching user profile for ID:', user.id);
      
      // Try to get user profile from users table using auth.uid()
      const { data: profile, error: profileError } = await supabase
        .from('users')
        .select('*')
        .eq('id', user.id)
        .single();

      if (profileError) {
        console.log('Profile not found by ID, trying by email:', profileError);
        
        // Try alternative query by email
        const { data: profileAlt, error: errorAlt } = await supabase
          .from('users')
          .select('*')
          .eq('email', user.email)
          .single();
          
        if (errorAlt) {
          console.warn('Profile not found by email either:', errorAlt);
          setError('Perfil do usuário não encontrado na base de dados');
        } else if (profileAlt) {
          console.log('Found user profile by email:', profileAlt);
          setUserProfile(profileAlt);
        }
      } else if (profile) {
        console.log('Found user profile by ID:', profile);
        setUserProfile(profile);
      }
    } catch (error) {
      console.error('Error fetching user profile:', error);
      setError('Erro ao buscar perfil do usuário');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUserProfile();
  }, [user, contextUserProfile]);

  return {
    userProfile: currentProfile,
    loading,
    error,
    getUserFirstName,
    refetch: fetchUserProfile
  };
}
