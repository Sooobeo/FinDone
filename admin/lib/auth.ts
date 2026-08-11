import "server-only";

import type { User } from "@supabase/supabase-js";
import { parseAdminRole } from "@/lib/access";
import { runtimeMode, type RuntimeMode } from "@/lib/supabase/config";
import { getServerSupabase } from "@/lib/supabase/server";
import type { AdminRole } from "@/lib/types";

export interface AdminContext {
  mode: RuntimeMode;
  user: User | null;
  hasAccess: boolean;
  role: AdminRole | null;
}

export async function getAdminContext(): Promise<AdminContext> {
  const mode = runtimeMode();
  if (mode !== "supabase") {
    return { mode, user: null, hasAccess: mode === "demo", role: null };
  }

  const supabase = await getServerSupabase();
  if (!supabase) {
    return { mode: "misconfigured", user: null, hasAccess: false, role: null };
  }

  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) return { mode, user: null, hasAccess: false, role: null };

  const { data: membership, error: membershipError } = await supabase
    .from("admin_users")
    .select("role,is_active")
    .eq("user_id", data.user.id)
    .maybeSingle();
  const role = !membershipError && membership?.is_active
    ? parseAdminRole(membership.role)
    : null;

  return {
    mode,
    user: data.user,
    hasAccess: Boolean(role),
    role,
  };
}
