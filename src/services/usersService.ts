import { supabase } from '@/lib/supabase';

export interface User {
  id: string; // UUID
  name: string;
  email: string;
  role: 'ADMIN' | 'OPERATOR';
  created_at?: string;
}

export interface CreateUserInput {
  name: string;
  email: string;
  role: 'ADMIN' | 'OPERATOR';
  password: string;
  project_ids?: number[];
  campaign_ids?: string[]; // Google Ads campaign IDs (varchar)
}

class UsersService {
  // Get all users
  async getAll(): Promise<User[]> {
    const { data, error } = await supabase
      .from('users')
      .select('id, name, email, role, created_at')
      .order('created_at', { ascending: false });

    if (error) throw error;
    return data || [];
  }

  // Get all projects
  async getAllProjects() {
    const { data, error } = await supabase
      .from('projects')
      .select('id, project_name')
      .order('project_name');

    if (error) throw error;
    return data || [];
  }

  // Get campaigns by project IDs
  async getCampaignsByProjects(projectIds: number[]) {
    if (!projectIds.length) return [];

    const { data, error } = await supabase
      .from('campaigns')
      .select('id, campaign_id, campaign_name, project_id')
      .in('project_id', projectIds)
      .order('campaign_name');

    if (error) throw error;
    return data || [];
  }

  // Get user projects
  async getUserProjects(userId: string): Promise<number[]> {
    const { data, error } = await supabase
      .from('user_projects')
      .select('project_id')
      .eq('user_id', userId);

    if (error) throw error;
    return data?.map(up => up.project_id) || [];
  }

  // Get user campaigns (returns Google Ads campaign IDs as strings)
  async getUserCampaigns(userId: string): Promise<string[]> {
    const { data, error } = await supabase
      .from('user_campaigns')
      .select('campaign_id')
      .eq('user_id', userId);

    if (error) throw error;
    return data?.map(uc => uc.campaign_id) || [];
  }

  // Create user with Supabase Auth
  async create(input: CreateUserInput): Promise<User> {
    // 1. Create auth user
    const { data: authData, error: authError } = await supabase.auth.signUp({
      email: input.email,
      password: input.password,
      options: {
        emailRedirectTo: window.location.origin,
        data: {
          name: input.name,
          role: input.role
        }
      }
    });

    if (authError) throw authError;
    if (!authData.user) throw new Error('Failed to create auth user');

    // 2. Create user in users table (with needs_password_change = true)
    // Nota: O ID do usuário na tabela users é o mesmo do auth.users (UUID)
    const { data: user, error: userError } = await supabase
      .from('users')
      .insert([{
        id: authData.user.id, // UUID do auth.users
        email: input.email,
        name: input.name,
        role: input.role,
        needs_password_change: true,
        first_login: true
      }])
      .select('id, name, email, role, created_at')
      .single();

    if (userError) {
      // Rollback: delete auth user
      console.error('Failed to create user in users table, rolling back...', userError);
      throw userError;
    }

    // 3. Se OPERATOR, associar projetos
    if (input.role === 'OPERATOR' && input.project_ids?.length) {
      const userProjects = input.project_ids.map(pid => ({
        user_id: user.id,
        project_id: pid
      }));

      const { error: projError } = await supabase
        .from('user_projects')
        .insert(userProjects);

      if (projError) {
        // Rollback: delete user
        await supabase.from('users').delete().eq('id', user.id);
        throw projError;
      }

      // 4. Se OPERATOR, associar campanhas
      if (input.campaign_ids?.length) {
        console.log('🎯 Associando campanhas ao novo usuário:', {
          user_id: user.id,
          campaign_ids: input.campaign_ids
        });
        
        const userCampaigns = input.campaign_ids.map(cid => ({
          user_id: user.id,
          campaign_id: cid
        }));

        const { error: campError } = await supabase
          .from('user_campaigns')
          .insert(userCampaigns);

        if (campError) {
          console.error('❌ Erro ao associar campanhas:', campError);
          // Rollback: delete user and projects
          await supabase.from('user_projects').delete().eq('user_id', user.id);
          await supabase.from('users').delete().eq('id', user.id);
          throw campError;
        }
        
        console.log('✅ Campanhas associadas com sucesso:', userCampaigns.length);
      }
    }

    return user;
  }

  // Update user
  async update(id: string, input: Partial<CreateUserInput>): Promise<User> {
    const updates: any = {
      name: input.name,
      email: input.email,
      role: input.role
    };

    const { data: user, error } = await supabase
      .from('users')
      .update(updates)
      .eq('id', id)
      .select('id, name, email, role, created_at')
      .single();

    if (error) throw error;

    // Atualizar projetos se OPERATOR
    if (input.role === 'OPERATOR' && input.project_ids !== undefined) {
      await supabase.from('user_projects').delete().eq('user_id', id);

      if (input.project_ids.length) {
        const userProjects = input.project_ids.map(pid => ({
          user_id: id,
          project_id: pid
        }));

        await supabase.from('user_projects').insert(userProjects);
      }

      // Atualizar campanhas se fornecidas
      if (input.campaign_ids !== undefined) {
        console.log('🎯 Atualizando campanhas do usuário:', {
          user_id: id,
          campaign_ids: input.campaign_ids
        });
        
        await supabase.from('user_campaigns').delete().eq('user_id', id);

        if (input.campaign_ids.length) {
          const userCampaigns = input.campaign_ids.map(cid => ({
            user_id: id,
            campaign_id: cid
          }));

          const { error: campError } = await supabase.from('user_campaigns').insert(userCampaigns);
          
          if (campError) {
            console.error('❌ Erro ao salvar campanhas:', campError);
            throw campError;
          }
          
          console.log('✅ Campanhas salvas com sucesso:', userCampaigns.length);
        } else {
          console.log('✅ Todas as campanhas removidas do usuário');
        }
      }
    }

    return user;
  }

  // Delete user
  async delete(id: string): Promise<void> {
    // Delete from user_campaigns
    await supabase.from('user_campaigns').delete().eq('user_id', id);

    // Delete from user_projects
    await supabase.from('user_projects').delete().eq('user_id', id);

    // Delete from users table
    const { error } = await supabase.from('users').delete().eq('id', id);
    if (error) throw error;

    // Note: Cannot delete auth.users via client, needs admin API
    // In production, use a server-side function or webhook
  }
}

export const usersService = new UsersService();
