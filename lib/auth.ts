"use client";

import { createClient, type Session, type SupabaseClient, type User } from "@supabase/supabase-js";
import { useEffect, useState } from "react";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const supabase: SupabaseClient | null =
  url && anonKey ? createClient(url, anonKey) : null;

export const authConfigured = supabase !== null;

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return;
    }
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setUser(data.session?.user ?? null);
      setLoading(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
      setUser(s?.user ?? null);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  return {
    user,
    loading,
    token: session?.access_token ?? null,
    async signIn(email: string, password: string) {
      if (!supabase) throw new Error("Auth is not configured");
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw new Error(error.message);
    },
    async signUp(email: string, password: string) {
      if (!supabase) throw new Error("Auth is not configured");
      const { data, error } = await supabase.auth.signUp({ email, password });
      if (error) throw new Error(error.message);
      // when email confirmation is on, there is no session yet
      return { needsConfirmation: !data.session };
    },
    async signOut() {
      await supabase?.auth.signOut();
    },
  };
}
