export const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim() ?? "";
export const supabasePublishableKey =
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim() ?? "";

export const hasSupabaseConfig = Boolean(supabaseUrl && supabasePublishableKey);
export const hasPartialSupabaseConfig = Boolean(supabaseUrl) !== Boolean(supabasePublishableKey);
export const explicitDemoMode = process.env.NEXT_PUBLIC_FINDONE_ADMIN_DEMO?.trim() === "1";

export type RuntimeMode = "demo" | "supabase" | "misconfigured";

export function resolveRuntimeMode(
  configured: boolean,
  partiallyConfigured: boolean,
  demoRequested: boolean,
  nodeEnv: string | undefined,
): RuntimeMode {
  if (partiallyConfigured || (configured && demoRequested)) return "misconfigured";
  if (configured) return "supabase";
  return demoRequested && nodeEnv !== "production" ? "demo" : "misconfigured";
}

export function runtimeMode(): RuntimeMode {
  return resolveRuntimeMode(
    hasSupabaseConfig,
    hasPartialSupabaseConfig,
    explicitDemoMode,
    process.env.NODE_ENV,
  );
}
