import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, getToken, setToken, formatApiErrorDetail } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  // undefined = checking; null = anonymous; object = authenticated
  const [user, setUser] = useState(undefined);

  const refresh = useCallback(async () => {
    const t = getToken();
    if (!t) { setUser(null); return; }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch (_) {
      setToken(null);
      setUser(null);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const login = useCallback(async (email, password) => {
    try {
      const { data } = await api.post("/auth/login", { email, password });
      setToken(data.token);
      setUser({ ...data.user, must_change_password: !!data.must_change_password });
      return { ok: true, user: data.user, must_change_password: !!data.must_change_password };
    } catch (e) {
      return { ok: false, error: formatApiErrorDetail(e.response?.data?.detail) || e.message,
               locked: e.response?.status === 423 };
    }
  }, []);

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout"); } catch (_) { /* logout best-effort */ }
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthCtx.Provider value={{ user, login, logout, refresh }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
