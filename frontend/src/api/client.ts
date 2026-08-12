import type {
  AnswerResponse,
  CardResponse,
  LoginResponse,
  ProfilePublic,
  ProgressOut,
  RateResponse,
  RatingResult,
} from "../types";

// Vite only exposes VITE_-prefixed vars, read at build time. See
// frontend/.env.example. No hardcoded URL/port — this must be set.
const API_URL = import.meta.env.VITE_API_URL as string;

const TOKEN_KEY = "lingua_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    throw new ApiError("Session expired — please log in again.", 401);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: undefined }));
    throw new ApiError(body.detail ?? `Request failed (${res.status})`, res.status);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listProfiles: () => request<ProfilePublic[]>("/api/profiles"),

  login: (profile_slug: string, pin: string) =>
    request<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ profile_slug, pin }),
    }),

  nextCard: () => request<CardResponse>("/api/cards/next"),

  rateCard: (wordPairId: number, result: RatingResult) =>
    request<RateResponse>(`/api/cards/${wordPairId}/rate`, {
      method: "POST",
      body: JSON.stringify({ result }),
    }),

  answerCard: (wordPairId: number, selectedWordPairId: number) =>
    request<AnswerResponse>(`/api/cards/${wordPairId}/answer`, {
      method: "POST",
      body: JSON.stringify({ selected_word_pair_id: selectedWordPairId }),
    }),

  getProgress: () => request<ProgressOut>("/api/progress"),

  updateSettings: (settings: { fluency_threshold?: number; daily_goal?: number }) =>
    request<ProfilePublic>("/api/profiles/me", {
      method: "PATCH",
      body: JSON.stringify(settings),
    }),
};
