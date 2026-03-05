/** Shared frontend types aligned with backend Pydantic schemas. */

/** JSON scalar type. */
export type JsonPrimitive = string | number | boolean | null;

/** JSON object type. */
export interface JsonObject {
  [key: string]: JsonValue;
}

/** JSON array type. */
export type JsonArray = JsonValue[];

/** Generic JSON value type. */
export type JsonValue = JsonPrimitive | JsonObject | JsonArray;

/** User profile fields shared across graph nodes. */
export interface UserProfile {
  origin_city: string | null;
  destinations: string[];
  depart_date_range: string | null;
  days_range: string | null;
  people: string | null;
  budget_range: string | null;
  style_prefs: string[];
}

/** Persisted session state payload in MySQL/Redis. */
export interface SessionState {
  stage: string;
  lead_status: string;
  lead_phone: string | null;
  active_route_id: number | null;
  candidate_route_ids: number[];
  excluded_route_ids: number[];
  /** Raw JSON dict in backend; keys should follow UserProfile naming convention. */
  user_profile: Record<string, unknown>;
  last_intent: string | null;
  followup_count: number;
  context_turns: Array<{ user: string; assistant: string }>;
  state_version: number;
}

/** Route card schema from backend RouteCard model. */
export interface RouteCard {
  id: number;
  name: string;
  tags: string[];
  summary: string;
  doc_url: string;
  sort_weight: number;
  price_min: number | null;
  price_max: number | null;
}

/** Full route detail schema. */
export interface RouteDetail {
  id: number;
  name: string;
  supplier: string;
  tags: string[];
  summary: string;
  highlights: string;
  base_info: string;
  itinerary_json: JsonValue;
  notice: string;
  included: string;
  doc_url: string;
  is_hot: boolean;
  sort_weight: number;
  created_at: string;
  updated_at: string;
}

/** Route pricing snapshot schema. */
export interface PricingInfo {
  price_min: number;
  price_max: number;
  currency: string;
  price_updated_at: string;
}

/** Route schedule snapshot schema. */
export interface ScheduleInfo {
  schedules_json: JsonValue;
  schedule_updated_at: string;
}

/** Route + pricing + schedule schema. */
export interface RoutePriceSchedule {
  route_id: number;
  pricing: PricingInfo | null;
  schedule: ScheduleInfo | null;
}

/** Route batch item schema used by compare/followup. */
export interface RouteBatchItem {
  id: number;
  name: string;
  supplier: string;
  tags: string[];
  summary: string;
  highlights: string;
  base_info: string;
  itinerary_json: JsonValue;
  notice: string;
  included: string;
  doc_url: string;
  is_hot: boolean;
  sort_weight: number;
  created_at: string;
  updated_at: string;
  pricing: PricingInfo | null;
  schedule: ScheduleInfo | null;
}

/** Compare price range block. */
export interface ComparePriceRange {
  min: number;
  max: number;
  currency: string;
  updated_at: string;
}

/** Compare next schedule block. */
export interface CompareNextSchedule {
  date: string | null;
  updated_at: string;
}

/** Single route row in compare payload. */
export interface CompareRouteItem {
  route_id: number;
  name: string;
  days: number;
  highlights: string[];
  itinerary_style: string;
  included_summary: string;
  notice_summary: string;
  price_range: ComparePriceRange;
  next_schedule: CompareNextSchedule;
  suitable_for: string[];
}

/** Compare payload schema. */
export interface CompareData {
  routes: CompareRouteItem[];
}

/** Lead create payload. */
export interface LeadCreate {
  session_id: string;
  phone: string;
}

/** Lead create response payload. */
export interface LeadResponse {
  success: boolean;
  message: string;
  phone_masked: string;
}

/** Lead list row schema. */
export interface LeadListItem {
  id: number;
  session_id: string;
  phone: string;
  source: string;
  active_route_id: number | null;
  status: string;
  created_at: string;
}

/** Route card shape produced by graph response cards. */
export interface GraphRouteCard {
  route_id: number | null;
  name: string;
  summary: string;
  tags: string[];
  doc_url: string | null;
  highlights: string;
}

/** UI action to show active route details. */
export interface ShowActiveRouteAction {
  action: "show_active_route";
  payload: { route_id: number };
}

/** UI action to show candidate route list. */
export interface ShowCandidatesAction {
  action: "show_candidates";
  payload: { route_ids: number[] };
}

/** UI action to collect phone number. */
export interface CollectPhoneAction {
  action: "collect_phone";
  payload: { reason: string };
}

/** UI action to show route comparison drawer. */
export interface ShowCompareAction {
  action: "show_compare";
  payload: CompareData;
}

/** Union type of backend-supported UI actions. */
export type UIAction =
  | ShowActiveRouteAction
  | ShowCandidatesAction
  | CollectPhoneAction
  | ShowCompareAction;

/** Chat request payload. */
export interface ChatSendRequest {
  session_id: string;
  user_message: string;
}

/** Chat response payload. */
export interface ChatSendResponse {
  session_id: string;
  trace_id: string;
  run_id: string;
  response_text: string;
  ui_actions: UIAction[];
  cards: GraphRouteCard[];
  state_patches: Record<string, unknown>;
}

/** SSE event type enum. */
export type SSEEventType = "token" | "ui_action" | "state_patch" | "done" | "error";

/** SSE event payload wrapper. */
export interface SSEEvent<T = unknown> {
  event: SSEEventType;
  data: T;
}

/** Health check response from backend /health. */
export interface HealthResponse {
  status: "ok" | "degraded";
  redis: "ok" | "error";
  mysql: "ok" | "error";
}
