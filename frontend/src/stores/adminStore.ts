"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

import { API_BASE_URL } from "@/services/api";
import type { AdminLoginResponse } from "@/types";

interface AdminStore {
  token: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  authedFetch: <T = unknown>(path: string, options?: RequestInit) => Promise<T>;
  authedUpload: <T = unknown>(path: string, formData: FormData, options?: RequestInit) => Promise<T>;
}

const toError = async (response: Response): Promise<Error> => {
  try {
    const data = (await response.json()) as { detail?: string; message?: string };
    return new Error(data.detail ?? data.message ?? `request failed: ${response.status}`);
  } catch {
    return new Error(`request failed: ${response.status}`);
  }
};

const normalizePath = (path: string): string => {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
};

export const useAdminStore = create<AdminStore>()(
  persist(
    (set, get) => ({
      token: null,
      isAuthenticated: false,

      login: async (username: string, password: string) => {
        const response = await fetch(`${API_BASE_URL}/admin/login`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ username, password }),
        });

        if (!response.ok) {
          throw await toError(response);
        }

        const data = (await response.json()) as AdminLoginResponse;
        set({
          token: data.access_token,
          isAuthenticated: Boolean(data.access_token),
        });
      },

      logout: () => {
        set({
          token: null,
          isAuthenticated: false,
        });
      },

      authedFetch: async <T = unknown>(path: string, options: RequestInit = {}) => {
        const token = get().token;
        if (!token) {
          throw new Error("未登录");
        }

        const response = await fetch(normalizePath(path), {
          ...options,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
            ...(options.headers ?? {}),
          },
        });

        if (response.status === 401) {
          get().logout();
          throw new Error("登录已过期，请重新登录");
        }

        if (!response.ok) {
          throw await toError(response);
        }

        if (response.status === 204) {
          return undefined as T;
        }

        return (await response.json()) as T;
      },

      authedUpload: async <T = unknown>(path: string, formData: FormData, options: RequestInit = {}) => {
        const token = get().token;
        if (!token) {
          throw new Error("未登录");
        }

        const response = await fetch(normalizePath(path), {
          ...options,
          method: options.method ?? "POST",
          body: formData,
          headers: {
            Authorization: `Bearer ${token}`,
            ...(options.headers ?? {}),
          },
        });

        if (response.status === 401) {
          get().logout();
          throw new Error("登录已过期，请重新登录");
        }

        if (!response.ok) {
          throw await toError(response);
        }

        if (response.status === 204) {
          return undefined as T;
        }

        return (await response.json()) as T;
      },
    }),
    {
      name: "travel_admin_store",
      partialize: (state) => ({
        token: state.token,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);
