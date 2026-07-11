// create-team-member — cria um acesso real de atendente/gestor: confirma que
// quem chamou é gestor do tenant (via app_metadata do próprio JWT, mesmo
// padrão de current_tenant_id()/current_role() usado nas policies de RLS),
// convida o e-mail de verdade via supabase.auth.admin.inviteUserByEmail e
// grava a linha correspondente em user_profiles. A service role key só
// existe aqui (variável de ambiente injetada automaticamente pelo Supabase
// em toda Edge Function) — nunca no bundle do cliente.
//
// Cópia versionada deste arquivo mantida em amorim-crm-backend/edge-functions
// só para referência/histórico; o deploy real acontece via MCP do Supabase
// (não há CI ligado a este diretório).

import { createClient } from "jsr:@supabase/supabase-js@2";

// CORS restrito a uma allow-list explícita — nunca "*" (revisão de segurança
// pré-VPS, ver amorim-crm-deploy/README.md pro domínio real de produção).
// Sem variável de ambiente extra: os únicos secrets injetados automaticamente
// em toda Edge Function são SUPABASE_URL/ANON_KEY/SERVICE_ROLE_KEY, e esta
// lista não é sensível (é só quem tem permissão de origem, não um segredo).
const ALLOWED_ORIGINS = new Set([
  "https://app.amorimcrm.online",
  "http://localhost:5173",
]);

const AVATAR_COLORS = ["#4f46e5", "#0891b2", "#059669", "#d97706", "#dc2626", "#7c3aed"];
const ASSIGNABLE_ROLES = ["atendente", "gestor"];

function corsHeaders(req: Request): Record<string, string> {
  const origin = req.headers.get("Origin") ?? "";
  const headers: Record<string, string> = {
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    Vary: "Origin",
  };
  if (ALLOWED_ORIGINS.has(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
  }
  return headers;
}

function jsonResponse(req: Request, body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(req), "Content-Type": "application/json" },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders(req) });
  }
  if (req.method !== "POST") {
    return jsonResponse(req, { error: "Método não permitido." }, 405);
  }

  const authHeader = req.headers.get("Authorization");
  if (!authHeader) {
    return jsonResponse(req, { error: "Não autenticado." }, 401);
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY")!;
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

  // Client com o JWT de quem chamou — só pra descobrir quem é (id/app_metadata),
  // nunca usado pra escrever nada.
  const callerClient = createClient(supabaseUrl, anonKey, {
    global: { headers: { Authorization: authHeader } },
  });
  const { data: callerData, error: callerError } = await callerClient.auth.getUser();
  if (callerError || !callerData.user) {
    return jsonResponse(req, { error: "Sessão inválida." }, 401);
  }

  const callerRole = callerData.user.app_metadata?.role;
  const callerTenantId = callerData.user.app_metadata?.tenant_id;

  let body: { name?: string; email?: string; role?: string; tenant_id?: string };
  try {
    body = await req.json();
  } catch {
    return jsonResponse(req, { error: "Corpo da requisição inválido." }, 400);
  }

  // Client de service role — bypassa RLS, só existe dentro desta function.
  const adminClient = createClient(supabaseUrl, serviceRoleKey);

  // Um gestor convida sempre pro próprio tenant (do JWT). admin_saas nunca
  // tem tenant_id no próprio JWT (não pertence a loja nenhuma) — diferente
  // do backend FastAPI, que já resolve impersonação via header
  // X-Impersonate-Tenant (app/deps.py), esta function ainda lê o papel
  // direto do JWT real, que não muda durante "Entrar como gestor". Por isso
  // o frontend manda o tenant impersonado explícito no corpo quando quem
  // chama é admin_saas, e aqui validamos que corresponde a uma loja de
  // verdade antes de convidar nela — sem essa validação, um admin_saas
  // poderia convidar gente pra qualquer tenant_id arbitrário só mandando no
  // corpo da requisição.
  let targetTenantId: string;
  if (callerRole === "gestor" && callerTenantId) {
    targetTenantId = callerTenantId;
  } else if (callerRole === "admin_saas" && body.tenant_id) {
    const { data: tenant } = await adminClient.from("tenants").select("id").eq("id", body.tenant_id).maybeSingle();
    if (!tenant) {
      return jsonResponse(req, { error: "Loja não encontrada." }, 404);
    }
    targetTenantId = tenant.id;
  } else {
    return jsonResponse(req, { error: "Só gestores podem convidar membros da equipe." }, 403);
  }

  const name = body.name?.trim();
  const email = body.email?.trim();
  const role = body.role;
  if (!name || !email || !role || !ASSIGNABLE_ROLES.includes(role)) {
    return jsonResponse(req, { error: "Informe nome, e-mail e um papel válido (atendente ou gestor)." }, 400);
  }

  const { data: invited, error: inviteError } = await adminClient.auth.admin.inviteUserByEmail(email, {
    data: { name },
  });
  if (inviteError || !invited.user) {
    return jsonResponse(req, { error: inviteError?.message ?? "Não foi possível convidar este e-mail." }, 400);
  }

  // inviteUserByEmail não aceita app_metadata direto — precisa de um segundo
  // passo pra estampar tenant_id/role no JWT (mesmos claims que
  // current_tenant_id()/current_role() leem nas policies de RLS).
  const { error: metadataError } = await adminClient.auth.admin.updateUserById(invited.user.id, {
    app_metadata: { tenant_id: targetTenantId, role },
  });
  if (metadataError) {
    return jsonResponse(req, { error: metadataError.message }, 500);
  }

  const avatarColor = AVATAR_COLORS[Math.floor(Math.random() * AVATAR_COLORS.length)];
  const { error: profileError } = await adminClient.from("user_profiles").insert({
    id: invited.user.id,
    tenant_id: targetTenantId,
    role,
    name,
    avatar_color: avatarColor,
  });
  if (profileError) {
    return jsonResponse(req, { error: profileError.message }, 500);
  }

  // Mesmo padrão de log_audit_event() do backend Python (app/core/audit.py) —
  // essa Edge Function é a única mutação de user_profiles que não passa pelo
  // FastAPI, então precisa gravar o próprio registro de auditoria (revisão de
  // segurança pré-VPS, item 7). Falha aqui não desfaz o convite já enviado —
  // só loga, pra não deixar o gestor sem saber que o convite funcionou.
  const { error: auditError } = await adminClient.from("audit_log").insert({
    tenant_id: targetTenantId,
    user_id: callerData.user.id,
    action: "INSERT",
    table_name: "user_profiles",
    record_id: invited.user.id,
  });
  if (auditError) {
    console.error("Falha ao gravar audit_log:", auditError.message);
  }

  return jsonResponse(
    req,
    {
      id: invited.user.id,
      tenantId: targetTenantId,
      name,
      email,
      role,
      avatarColor,
      createdAt: new Date().toISOString(),
    },
    200,
  );
});
