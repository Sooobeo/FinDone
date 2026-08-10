import "server-only";

import type { User } from "@supabase/supabase-js";
import { runtimeMode, type RuntimeMode } from "@/lib/supabase/config";
import { getServerSupabase } from "@/lib/supabase/server";

export interface AdminContext {
  mode: RuntimeMode;
  user: User | null;
  isAdmin: boolean;
}

export async function getAdminContext(): Promise<AdminContext> {
  const mode = runtimeMode();
  if (mode !== "supabase") return { mode, user: null, isAdmin: mode === "demo" };

  const supabase = await getServerSupabase();
  if (!supabase) return { mode: "misconfigured", user: null, isAdmin: false };

  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) return { mode, user: null, isAdmin: false };

  const { data: membership, error: membershipError } = await supabase
    .from("admin_users")
    .select("user_id")
    .eq("user_id", data.user.id)
    .maybeSingle();

  return {
    mode,
    user: data.user,
    isAdmin: !membershipError && Boolean(membership),
  };
}
