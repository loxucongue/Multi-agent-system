/** 用户画像 */
export interface UserProfile {
  origin_city: string | null;
  destinations: string[];
  depart_date_range: string | null;
  days_range: string | null;
  people: string | null;
  budget_range: string | null;
  style_prefs: string[];
}

/** 会话状态（对应后端 SessionState） */
export interface SessionState {
  stage: "init" | "collecting" | "recommended" | "comparing" | "rematch_collecting";
  lead_status: "none" | "triggered" | "captured";
  lead_phone: string | null;
  active_route_id: number | null;
  candidate_route_ids: number[];
  excluded_route_ids: number[];
  user_profile: UserProfile;
  last_intent: string | null;
  followup_count: number;
  context_turns: Array<{ user: string; assistant: string }>;
  state_version: number;
}

/** 路线卡片（精简字段） */
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

/** 路线详情（完整字段） */
export interface RouteDetail {
  id: number;
  name: string;
  supplier: string;
  tags: string[];
  summary: string;
  highlights: string;
  base_info: string;
  itinerary_json: unknown;
  notice: string;
  included: string;
  doc_url: string;
  is_hot: boolean;
  sort_weight: number;
  created_at: string;
  updated_at: string;
}

/** 价格信息 */
export interface PricingInfo {
  price_min: number;
  price_max: number;
  currency: string;
  price_updated_at: string;
}

/** 排期信息 */
export interface ScheduleInfo {
  schedules_json: unknown;
  schedule_updated_at: string;
}

/** 对比线路单项 */
export interface CompareRouteItem {
  route_id: number;
  name: string;
  days: number;
  highlights: string[];
  itinerary_style: string;
  included_summary: string;
  notice_summary: string;
  price_range: { min: number; max: number; currency: string; updated_at: string };
  next_schedule: { date: string | null; updated_at: string };
  suitable_for: string[];
}

/** 对比数据 */
export interface CompareData {
  routes: CompareRouteItem[];
}

/** Lead 提交响应 */
export interface LeadResponse {
  success: boolean;
  message: string;
  phone_masked: string;
}

/** Chat API 请求 */
export interface ChatSendRequest {
  session_id: string;
  message: string;
}

/** Chat API 响应 */
export interface ChatSendResponse {
  run_id: string;
  trace_id: string;
}

/** Session 创建响应 */
export interface SessionCreateResponse {
  session_id: string;
}

/** Session 详情响应 */
export interface SessionDetailResponse {
  session_id: string;
  stage: string;
  lead_status: string;
  active_route_id: number | null;
  candidate_route_ids: number[];
  user_profile: UserProfile;
  followup_count: number;
  active_card: RouteCard | null;
  candidate_cards: RouteCard[];
}

/** SSE 事件类型 */
export type SSEEventType = "token" | "ui_action" | "cards" | "state_patch" | "done" | "error";

/** SSE 事件 */
export interface SSEEvent<T = unknown> {
  event: SSEEventType;
  data: T;
}

/** UI Action 指令 */
export interface UIAction {
  action: "show_active_route" | "show_candidates" | "show_compare" | "collect_phone";
  payload: Record<string, unknown>;
}

/** 聊天消息 */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
  cards?: RouteCard[];
  ui_actions?: UIAction[];
}

/** Admin 登录请求/响应 */
export interface AdminLoginRequest {
  username: string;
  password: string;
}

export interface AdminLoginResponse {
  access_token: string;
  token_type: string;
}
