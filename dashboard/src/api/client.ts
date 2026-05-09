/**
 * Singleton axios client used by every React Query hook.
 *
 * Base URL comes from `VITE_API_URL` (set via `.env.development` /
 * `.env.production` / `.env.development.local`). In Phase 6.4 the
 * production build is invoked with VITE_API_URL pointed at the AWS
 * load balancer's DNS name, and the bundle picks it up at build time.
 */

import axios, { type AxiosInstance } from "axios";

const baseURL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export const api: AxiosInstance = axios.create({
  baseURL,
  // The dashboard never needs cookies, but allowCredentials would be
  // wrong here even if it did — backend CORSMiddleware is configured
  // with credentials:true already, but the browser only sends credentials
  // when explicitly requested. Default omit keeps the surface lean.
  withCredentials: false,
  // 15s matches the backend httpx timeout used by the seed script —
  // anything longer than this is almost certainly a hung handler.
  timeout: 15_000,
  headers: { Accept: "application/json" },
});

/** Tiny convenience for components that just want the body.
 *
 * `params` is typed as `object | undefined` rather than
 * `Record<string, unknown>` so callers can pass typed interfaces
 * (e.g. `PlayerListParams`) without the index-signature dance. axios
 * serialises whatever shape we hand it.
 */
export async function getJson<T>(path: string, params?: object): Promise<T> {
  const res = await api.get<T>(path, { params });
  return res.data;
}
