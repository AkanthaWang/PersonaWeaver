import { getSupabaseClient } from "../../lib/supabase";
import { uploadAvatarToOss } from "../oss/ossAvatar";
import {
  buildHeaders,
  buildOpenAIHeaders,
  createAuthError,
  createId,
  createShortId,
  formatUnknownError,
  isDisabledStatus,
  isOpenAIChatCompletionsUrl,
  normalizeOptionalText,
  proxyEcnuChatCompletionsUrl,
  resolveCurrentUserId,
  sha256,
  stripTrailingSlash,
  axios,
} from "../core";

export function createAuthApi() {
  function toHealthErrorMessage(error, url) {
    const code = String(error?.code || "").toUpperCase();
    const status = Number(error?.response?.status || 0);
    const serverMessage =
      typeof error?.response?.data === "string"
        ? error.response.data
        : error?.response?.data?.error?.message || error?.response?.data?.message || "";

    if (code === "ECONNABORTED") {
      return `连接超时: ${url}`;
    }

    if (code === "ERR_NETWORK") {
      return `网络连接失败: ${url}（可能是跨域 CORS 或地址不可达）`;
    }

    if (status > 0) {
      const detail = String(serverMessage || "").trim();
      return detail ? `请求失败(${status}): ${detail}` : `请求失败(${status}): ${url}`;
    }

    return formatUnknownError(error);
  }

  return {
    async register(payload) {
      const supabase = getSupabaseClient();
      const username = String(payload?.username || "").trim();
      const rawEmail = String(payload?.email || "").trim().toLowerCase();
      const password = String(payload?.password || "");
      const safeLocalPart = (username || "user")
        .toLowerCase()
        .replace(/[^a-z0-9._-]/g, "_")
        .replace(/^[_\.-]+|[_\.-]+$/g, "") || "user";
      const email = rawEmail || `${safeLocalPart}_${Date.now()}@example.com`;

      if (!username) {
        throw new Error("用户名不能为空");
      }
      if (!password) {
        throw new Error("密码不能为空");
      }

      const { data: existingUser, error: existingError } = await supabase
        .from("users")
        .select("user_id")
        .eq("username", username)
        .maybeSingle();

      if (existingError) {
        throw existingError;
      }
      if (existingUser?.user_id) {
        throw createAuthError("用户名已存在", "AUTH_USER_EXISTS");
      }

      const { data: signUpData, error: signUpError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: { username },
        },
      });

      if (signUpError) {
        throw signUpError;
      }

      const authUserId = signUpData?.user?.id;
      if (!authUserId) {
        throw new Error("注册成功但未返回用户ID");
      }

      const formattedUserId = `user_${authUserId}`;
      const now = new Date().toISOString();
      const passwordHash = await sha256(password);

      const { error: insertUserError } = await supabase.from("users").upsert({
        user_id: formattedUserId,
        username,
        email,
        password_hash: passwordHash,
        created_at: now,
        updated_at: now,
      }, { onConflict: "user_id" });

      if (insertUserError) {
        throw insertUserError;
      }

      return {
        user_id: formattedUserId,
        username,
        message: "User registered successfully",
      };
    },

    async login(payload) {
      const supabase = getSupabaseClient();
      const username = String(payload?.username || "").trim();
      const password = String(payload?.password || "");

      if (!username || !password) {
        throw createAuthError("账号或密码不能为空", "AUTH_INVALID_CREDENTIALS");
      }

      const { data: user, error: userError } = await supabase
        .from("users")
        .select("user_id, username, email, status")
        .eq("username", username)
        .maybeSingle();

      if (userError) {
        throw userError;
      }
      if (!user) {
        throw createAuthError("账号或密码错误", "AUTH_INVALID_CREDENTIALS");
      }
      if (isDisabledStatus(user.status)) {
        throw createAuthError("账号已被禁用", "AUTH_ACCOUNT_DISABLED");
      }
      if (!user.email) {
        throw createAuthError("该账号未绑定邮箱，无法使用标准登录", "AUTH_INVALID_CREDENTIALS");
      }

      const { data: signInData, error: signInError } = await supabase.auth.signInWithPassword({
        email: user.email,
        password,
      });

      if (signInError) {
        throw createAuthError("账号或密码错误", "AUTH_INVALID_CREDENTIALS");
      }

      const accessToken = signInData?.session?.access_token;
      const refreshToken = signInData?.session?.refresh_token;
      const expiresIn = Number(signInData?.session?.expires_in || 3600);
      const authUserId = user.user_id;

      if (!accessToken || !refreshToken) {
        throw createAuthError("登录失败，请稍后重试", "AUTH_INVALID_CREDENTIALS");
      }

      const now = new Date();
      const expiresAt = new Date(now.getTime() + expiresIn * 1000);
      const refreshTokenHash = await sha256(refreshToken);
      const authId = createShortId("auth");

      const { error: sessionError } = await supabase.from("auth_sessions").upsert({
        auth_id: authId,
        user_id: authUserId,
        access_token_jti: accessToken,
        refresh_token_hash: refreshTokenHash,
        expires_at: expiresAt.toISOString(),
        revoked_at: null,
        created_at: now.toISOString(),
        updated_at: now.toISOString(),
      }, { onConflict: "access_token_jti" });

      if (sessionError) {
        throw sessionError;
      }

      return {
        access_token: accessToken,
        token_type: "bearer",
        expires_in: expiresIn,
      };
    },

    async getCurrentUser(settings) {
      const supabase = getSupabaseClient();
      const token = String(settings?.auth_token || "").trim();
      if (!token) {
        throw createAuthError("登录凭证无效，请重新登录", "AUTH_INVALID_TOKEN");
      }

      const { data: authData, error: authError } = await supabase.auth.getUser(token);
      if (authError || !authData?.user?.id) {
        throw createAuthError("登录凭证无效，请重新登录", "AUTH_INVALID_TOKEN");
      }

      const { data: sessionRow, error: sessionError } = await supabase
        .from("auth_sessions")
        .select("expires_at, revoked_at, user_id")
        .eq("access_token_jti", token)
        .maybeSingle();

      if (sessionError) {
        throw sessionError;
      }

      if (sessionRow?.revoked_at) {
        throw createAuthError("登录凭证无效，请重新登录", "AUTH_INVALID_TOKEN");
      }
      if (sessionRow?.expires_at && new Date(sessionRow.expires_at).getTime() <= Date.now()) {
        throw createAuthError("登录已过期，请重新登录", "AUTH_TOKEN_EXPIRED");
      }

      const { data: user, error: userError } = await supabase
        .from("users")
        .select("user_id, username, email, status, avatar, prompt, created_at, updated_at")
        .eq("user_id", sessionRow?.user_id)
        .maybeSingle();

      if (userError) {
        throw userError;
      }
      if (!user) {
        throw createAuthError("用户不存在", "AUTH_INVALID_TOKEN");
      }

      return {
        user_id: user.user_id,
        username: user.username,
        email: user.email,
        status: user.status,
        avatar: user.avatar || null,
        prompt: user.prompt || null,
        created_at: user.created_at,
        updated_at: user.updated_at,
      };
    },

    async updateAccountProfile(payload, settings) {
      const supabase = getSupabaseClient();
      const userId = await resolveCurrentUserId(supabase, settings?.auth_token);
      const username = normalizeOptionalText(payload?.username);
      const email = normalizeOptionalText(payload?.email)?.toLowerCase() || null;

      if (!username && !email) {
        throw new Error("请至少填写用户名或邮箱");
      }

      if (username) {
        const { data: existingUser, error: existingError } = await supabase
          .from("users")
          .select("user_id")
          .eq("username", username)
          .neq("user_id", userId)
          .maybeSingle();

        if (existingError) {
          throw existingError;
        }
        if (existingUser?.user_id) {
          throw createAuthError("用户名已存在", "AUTH_USER_EXISTS");
        }
      }

      const userUpdates = {
        updated_at: new Date().toISOString(),
      };

      if (username) {
        userUpdates.username = username;
      }
      if (email) {
        userUpdates.email = email;
      }

      const { error: updateUserError } = await supabase
        .from("users")
        .update(userUpdates)
        .eq("user_id", userId);

      if (updateUserError) {
        throw updateUserError;
      }

      if (email) {
        const { error: authUpdateError } = await supabase.auth.updateUser({ email });
        if (authUpdateError) {
          throw authUpdateError;
        }
      }

      const { data: latestUser, error: latestUserError } = await supabase
        .from("users")
        .select("user_id, username, email, status, avatar, prompt, created_at, updated_at")
        .eq("user_id", userId)
        .maybeSingle();

      if (latestUserError) {
        throw latestUserError;
      }

      return {
        user_id: latestUser?.user_id || userId,
        username: latestUser?.username || username,
        email: latestUser?.email || email,
        status: latestUser?.status || null,
        avatar: latestUser?.avatar || null,
        prompt: latestUser?.prompt || null,
        created_at: latestUser?.created_at || null,
        updated_at: latestUser?.updated_at || null,
      };
    },

    async updateRoleSettings(payload, settings) {
      const supabase = getSupabaseClient();
      const userId = await resolveCurrentUserId(supabase, settings?.auth_token);

      const prompt = normalizeOptionalText(payload?.prompt);
      const avatar = normalizeOptionalText(payload?.avatar);

      const { data, error } = await supabase
        .from("users")
        .update({
          prompt,
          avatar,
          updated_at: new Date().toISOString(),
        })
        .eq("user_id", userId)
        .select("user_id, avatar, prompt")
        .maybeSingle();

      if (error) {
        throw error;
      }

      return {
        user_id: data?.user_id || userId,
        avatar: data?.avatar || null,
        prompt: data?.prompt || null,
      };
    },

    async updatePassword(newPassword, settings) {
      const supabase = getSupabaseClient();
      await resolveCurrentUserId(supabase, settings?.auth_token);

      const password = String(newPassword || "");
      if (password.length < 6) {
        throw new Error("新密码至少需要 6 位");
      }

      const { error } = await supabase.auth.updateUser({ password });
      if (error) {
        throw error;
      }

      return { ok: true };
    },

    async uploadAvatar(file, settings) {
      const supabase = getSupabaseClient();
      const userId = await resolveCurrentUserId(supabase, settings?.auth_token);

      const avatarUrl = await uploadAvatarToOss(userId, file);

      const now = new Date().toISOString();
      const { error } = await supabase
        .from("users")
        .update({
          avatar: avatarUrl,
          updated_at: now,
        })
        .eq("user_id", userId);

      if (error) {
        throw error;
      }

      return { avatar_url: avatarUrl };
    },

    async health(settings) {
      const backendUrl = stripTrailingSlash(settings?.backend_url);
      if (!backendUrl) {
        throw new Error("请先填写 Model API 地址");
      }

      if (isOpenAIChatCompletionsUrl(settings.backend_url)) {
        if (!settings.api_key) {
          throw new Error("请先填写 API Key");
        }
        if (!String(settings.model || "").trim()) {
          throw new Error("请先选择模型（如 Volc-DeepSeek-V3.2）");
        }

        // vivo 等 OpenAI 兼容接口没有 /models 端点，改为向 /chat/completions
        // 发一个最小请求探测可达性：只要拿到任意 HTTP 响应即视为连通
        // （鉴权/额度类错误也说明地址正确、服务可达）。
        const chatUrl = proxyEcnuChatCompletionsUrl(settings.backend_url);
        try {
          const res = await axios.post(
            chatUrl,
            {
              model: settings.model,
              messages: [{ role: "user", content: "ping" }],
              max_tokens: 1,
              stream: false,
            },
            {
              headers: {
                ...buildOpenAIHeaders(settings),
                "Content-Type": "application/json; charset=utf-8",
              },
              params: { request_id: createId("req") },
              timeout: 15000,
            },
          );
          return res.status >= 200 && res.status < 300;
        } catch (error) {
          // 有 HTTP 响应（4xx/5xx）说明地址可达，只是鉴权/参数问题 → 判为连通
          if (error?.response?.status) {
            return true;
          }
          throw new Error(toHealthErrorMessage(error, chatUrl));
        }
      }

      const normalized = backendUrl;
      const probeUrls = [normalized, `${normalized}/health`];
      const errors = [];

      for (const url of probeUrls) {
        try {
          const res = await axios.get(url, { timeout: 4000, headers: buildHeaders(settings) });
          if (res.status >= 200 && res.status < 300) {
            const statusText = String(res.data?.status ?? "").toLowerCase();
            if (!statusText || statusText === "ok" || statusText === "healthy") {
              return true;
            }
          }
        } catch (error) {
          errors.push(toHealthErrorMessage(error, url));
        }
      }

      throw new Error(errors.filter(Boolean).join("；") || "后端未响应");
    },
  };
}
