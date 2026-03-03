/** Shared frontend domain types. */

export interface SessionState {
  sessionId: string;
  traceId: string;
  status: "idle" | "collecting" | "processing" | "completed" | "error";
  lastUpdatedAt: string;
}

export interface RouteCard {
  routeId: string;
  title: string;
  destination: string;
  durationDays: number;
  price: number;
  currency: string;
  updatedAt: string;
}

export interface CompareData {
  left: RouteCard;
  right: RouteCard;
  summary: string;
}

export type LeadStatus = "idle" | "submitting" | "success" | "failed";

export interface SSEEvent<T = unknown> {
  event: string;
  traceId: string;
  data: T;
  timestamp: string;
}
