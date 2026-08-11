import { useCallback, useState } from "react";
import { api, clearToken, getToken, setToken as persistToken } from "../api/client";
import type { ProfilePublic } from "../types";

const PROFILE_KEY = "lingua_profile";

function loadStoredProfile(): ProfilePublic | null {
  const raw = localStorage.getItem(PROFILE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as ProfilePublic;
  } catch {
    return null;
  }
}

export function useAuth() {
  const [profile, setProfile] = useState<ProfilePublic | null>(() =>
    getToken() ? loadStoredProfile() : null,
  );

  const login = useCallback(async (slug: string, pin: string) => {
    const res = await api.login(slug, pin);
    persistToken(res.access_token);
    localStorage.setItem(PROFILE_KEY, JSON.stringify(res.profile));
    setProfile(res.profile);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    localStorage.removeItem(PROFILE_KEY);
    setProfile(null);
  }, []);

  return { profile, login, logout, isAuthenticated: profile !== null };
}
