"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileText,
  Flame,
  Hash,
  Hotel,
  Info,
  Map,
  MapPin,
  Navigation,
  Utensils,
  XCircle,
} from "lucide-react";

import type { RouteFullDetail } from "@/types";

interface RouteDetailPanelProps {
  open: boolean;
  data: RouteFullDetail | null;
  loading: boolean;
  onClose: () => void;
}

interface DayItem {
  day: string;
  dayTitle: string;
  content: string;
  pois: Array<{ poiName: string; activity: string }>;
  meals: {
    breakfast: string;
    lunch: string;
    dinner: string;
  };
  hotel: {
    hotelName: string;
    hotelLevel: string;
  };
}

type ActiveTab = "itinerary" | "cost" | "notice";

const formatPlainText = (value: unknown, depth = 0): string => {
  if (value == null || depth > 4) {
    return "";
  }
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => formatPlainText(item, depth + 1))
      .filter(Boolean)
      .join("，");
  }
  if (typeof value === "object") {
    return Object.values(value as Record<string, unknown>)
      .map((item) => formatPlainText(item, depth + 1))
      .filter(Boolean)
      .join("，");
  }
  return "";
};

const ensureStringList = (value: unknown): string[] => {
  if (Array.isArray(value)) {
    return value.map((item) => formatPlainText(item)).filter(Boolean);
  }
  const text = formatPlainText(value);
  if (!text) {
    return [];
  }
  return text
    .split(/[，、；;|\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
};

const formatDateDisplay = (value?: string): string => {
  if (!value) {
    return "--";
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    return value;
  }
  return d.toLocaleDateString("zh-CN");
};

const formatPriceMin = (value: number | null | undefined): string => {
  if (typeof value !== "number") {
    return "--";
  }
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
};

const toScheduleDates = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }

  const out: string[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const dateText = formatPlainText((item as Record<string, unknown>).date);
    if (!dateText) {
      continue;
    }
    const normalized = dateText.includes("/") ? dateText.replaceAll("/", "-") : dateText;
    out.push(normalized);
  }
  return out;
};

const toDayItems = (value: unknown): DayItem[] => {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item, idx) => {
      const row = item as Record<string, unknown>;
      const poisRaw = Array.isArray(row.pois) ? row.pois : [];
      const pois = poisRaw
        .map((poi) => {
          const p = poi as Record<string, unknown>;
          return {
            poiName: formatPlainText(p.poi_name),
            activity: formatPlainText(p.activity),
          };
        })
        .filter((poi) => poi.poiName);

      const meals = (row.meals as Record<string, unknown>) || {};
      const hotel = (row.hotel as Record<string, unknown>) || {};

      return {
        day: formatPlainText(row.day) || String(idx + 1),
        dayTitle: formatPlainText(row.day_title) || "行程安排",
        content: formatPlainText(row.content) || "暂无行程描述",
        pois,
        meals: {
          breakfast: formatPlainText(meals.breakfast) || "-",
          lunch: formatPlainText(meals.lunch) || "-",
          dinner: formatPlainText(meals.dinner) || "-",
        },
        hotel: {
          hotelName: formatPlainText(hotel.hotel_name) || "-",
          hotelLevel: formatPlainText(hotel.hotel_level) || "",
        },
      };
    })
    .filter((item) => item.dayTitle || item.content);
};

const renderListSection = (items: string[], emptyText: string, variant: "normal" | "success" | "danger") => {
  if (items.length === 0) {
    return <p className="text-sm text-gray-400">{emptyText}</p>;
  }

  if (variant === "success") {
    return (
      <ul className="space-y-2">
        {items.map((item, i) => (
          <li key={`${item}-${i}`} className="flex items-start gap-2 text-sm text-gray-600">
            <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-green-400" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    );
  }

  if (variant === "danger") {
    return (
      <ul className="space-y-2">
        {items.map((item, i) => (
          <li key={`${item}-${i}`} className="flex items-start gap-2 text-sm text-gray-600">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-red-300" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <li key={`${item}-${i}`} className="flex items-start gap-2 text-sm text-gray-700">
          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-300" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
};

function TopTag({ children, type = "default" }: { children: string; type?: "default" | "primary" | "hot" }) {
  const styles: Record<string, string> = {
    default: "bg-gray-100 text-gray-600 border border-gray-200",
    primary: "bg-blue-50 text-blue-600 border border-blue-100",
    hot: "bg-orange-50 text-orange-600 border border-orange-200",
  };
  return <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs ${styles[type]}`}>{children}</span>;
}

function DayCard({ item }: { item: DayItem }) {
  return (
    <div className="relative border-l-2 border-gray-100 pb-8 pl-6 last:border-transparent last:pb-0">
      <div className="absolute -left-[9px] top-1 flex h-4 w-4 items-center justify-center rounded-full border-2 border-white bg-blue-100">
        <div className="h-1.5 w-1.5 rounded-full bg-blue-500" />
      </div>

      <div className="mb-2 flex items-center gap-2">
        <span className="text-lg font-bold text-gray-900">Day {item.day}</span>
        <span className="font-medium text-gray-800">{item.dayTitle}</span>
      </div>

      {item.pois.length > 0 ? (
        <div className="mb-3 flex flex-wrap gap-2">
          {item.pois.map((poi, idx) => (
            <div key={`${poi.poiName}-${idx}`} className="flex items-center gap-1 rounded bg-blue-50 px-2 py-1 text-xs text-blue-600">
              <Map size={12} />
              <span>{poi.poiName}</span>
              {poi.activity ? <span className="text-blue-400">· {poi.activity}</span> : null}
            </div>
          ))}
        </div>
      ) : null}

      <p className="mb-4 text-sm leading-relaxed text-gray-600">{item.content}</p>

      <div className="space-y-2 rounded-lg bg-gray-50 p-3 text-sm text-gray-600">
        <div className="flex items-start gap-2">
          <Utensils size={16} className="mt-0.5 shrink-0 text-gray-400" />
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            <span>早: {item.meals.breakfast}</span>
            <span>午: {item.meals.lunch}</span>
            <span>晚: {item.meals.dinner}</span>
          </div>
        </div>

        <div className="flex items-start gap-2">
          <Hotel size={16} className="mt-0.5 shrink-0 text-gray-400" />
          <div>
            <span className="font-medium text-gray-800">{item.hotel.hotelName}</span>
            {item.hotel.hotelLevel ? <span className="ml-2 text-gray-500">({item.hotel.hotelLevel})</span> : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function RouteDetailPanel({ open, data, loading, onClose }: RouteDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<ActiveTab>("itinerary");
  const shellRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    const shell = shellRef.current;
    const previousActive = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    shell?.focus();

    const handleKeydown = (event: KeyboardEvent) => {
      if (!open) {
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key !== "Tab") {
        return;
      }

      const focusable = shell?.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable || focusable.length === 0) {
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;

      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", handleKeydown);
    return () => {
      window.removeEventListener("keydown", handleKeydown);
      previousActive?.focus();
    };
  }, [onClose, open]);

  const view = useMemo(() => {
    if (loading) {
      return (
        <div className="flex h-full items-center justify-center p-8 text-sm text-gray-500">
          正在加载线路详情...
        </div>
      );
    }

    if (!data?.route) {
      return <div className="flex h-full items-center justify-center p-8 text-sm text-gray-500">暂无路线数据</div>;
    }

    const { route, pricing, schedule } = data;
    const dayItems = toDayItems(route.itinerary_json);
    const schedules = toScheduleDates(schedule?.schedules_json);
    const combinedTags = [...(Array.isArray(route.tags) ? route.tags : [])];
    if (route.features) {
      combinedTags.unshift(route.features);
    }

    const highlights = ensureStringList(route.highlights);
    const includedItems = ensureStringList(route.included);
    const excludedItems = ensureStringList(route.cost_excluded);
    const noticeItems = ensureStringList(route.notice);

    const baseInfo = route.base_info as Record<string, unknown>;
    const destination = formatPlainText(baseInfo?.destination_country) || "目的地待补充";
    const totalDays = formatPlainText(baseInfo?.total_days);
    const totalNights = formatPlainText(baseInfo?.total_nights);

    return (
      <div className="flex h-full flex-col overflow-hidden rounded-2xl bg-white">
        <div className="z-10 flex shrink-0 gap-5 border-b border-gray-100 bg-white px-6 py-6">
          <div className="relative aspect-[210/297] w-[130px] shrink-0 overflow-hidden rounded-xl bg-gray-100 shadow-md">
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 text-gray-400">
              <FileText size={18} />
              <span className="text-xs">封面预留</span>
            </div>
            {route.is_hot ? (
              <div className="absolute left-0 top-0 flex items-center gap-1 rounded-br-lg bg-gradient-to-r from-orange-500 to-red-500 px-2 py-1 text-xs font-medium text-white shadow-sm">
                <Flame size={12} /> 热门
              </div>
            ) : null}
            <div className="absolute bottom-2 left-2 right-2 flex items-center gap-1 text-[10px] text-gray-500">
              <Navigation size={10} className="shrink-0" />
              <span className="truncate">{route.supplier || "甄选供应商"}</span>
            </div>
          </div>

          <div className="flex min-w-0 flex-1 flex-col justify-between py-0.5">
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <div className="flex items-center gap-1.5 rounded-md bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                  <Hash size={12} /> ID: {route.id}
                </div>
                <div className="flex items-center gap-1 text-xs text-gray-400">
                  <Clock size={12} /> 更新于 {formatDateDisplay(route.updated_at)}
                </div>
              </div>

              <h1 className="mb-1.5 line-clamp-2 text-[1.15rem] font-bold leading-snug text-gray-900" title={route.name}>
                {route.name}
              </h1>

              <div className="mb-2 flex items-center gap-2 text-xs font-medium text-gray-600">
                <span className="flex items-center gap-1 rounded bg-blue-50 px-1.5 py-0.5 text-blue-600">
                  <MapPin size={12} /> {destination}
                </span>
                <span className="text-gray-300">|</span>
                <span>
                  {totalDays || "?"}天{totalNights || "?"}晚
                </span>
              </div>

              <div className="mb-1.5 flex flex-wrap gap-1.5">
                {combinedTags.map((tag, i) => (
                  <TopTag key={`${tag}-${i}`} type={i === 0 && route.features ? "primary" : "default"}>
                    {tag}
                  </TopTag>
                ))}
              </div>

              <p className="line-clamp-2 text-xs leading-relaxed text-gray-500">{route.summary}</p>
            </div>

            <div className="mt-2 flex items-end justify-between border-t border-gray-50 pt-2">
              <div className="flex-1 pr-2">
                {schedules.length > 0 ? (
                  <div className="flex flex-col gap-0.5">
                    <span className="flex items-center gap-1 text-[10px] text-gray-400">
                      <Calendar size={10} /> 最近团期
                    </span>
                    <span className="text-xs font-medium text-gray-700">
                      {schedules
                        .slice(0, 2)
                        .map((s) => (s.length >= 10 ? s.slice(5) : s))
                        .join(", ")}
                      {schedules.length > 2 ? " 等" : ""}
                    </span>
                  </div>
                ) : null}
              </div>

              <div className="shrink-0 text-right">
                <div id="route-detail-price" className="mb-1 flex items-baseline text-red-500">
                  <span className="mr-0.5 text-xs font-semibold">{pricing?.currency || "¥"}</span>
                  <span className="text-2xl font-bold leading-none tracking-tight">{formatPriceMin(pricing?.price_min)}</span>
                  <span className="ml-1 text-xs font-normal text-gray-500">起</span>
                </div>

                {route.doc_url ? (
                  <a
                    href={route.doc_url}
                    target="_blank"
                    rel="noreferrer"
                    className="group flex items-center gap-1 text-[11px] text-blue-600 transition-colors hover:text-blue-800"
                  >
                    <span className="border-b border-blue-600/30 group-hover:border-blue-800">查看详细行程原始文档</span>
                    <ExternalLink size={10} className="transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                  </a>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        <div className="flex shrink-0 border-b border-gray-100 bg-gray-50/50 px-6">
          {[
            { id: "itinerary" as const, label: "每日行程", icon: Navigation },
            { id: "cost" as const, label: "亮点与费用", icon: FileText },
            { id: "notice" as const, label: "预订须知", icon: AlertCircle },
          ].map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
                  active ? "border-blue-600 text-blue-600" : "border-transparent text-gray-500 hover:text-gray-800"
                }`}
              >
                <Icon size={16} />
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="custom-scrollbar relative flex-1 overflow-y-auto bg-white px-6 py-5">
          {activeTab === "itinerary" ? (
            dayItems.length > 0 ? (
              <div className="space-y-1">
                {dayItems.map((item, idx) => (
                  <DayCard key={`${item.day}-${idx}`} item={item} />
                ))}
              </div>
            ) : (
              <div className="flex h-full flex-col items-center justify-center py-10 text-gray-400">
                <Navigation size={32} className="mb-2 opacity-50" />
                <p className="text-sm">暂无行程详情</p>
              </div>
            )
          ) : null}

          {activeTab === "cost" ? (
            <div className="space-y-6">
              <section>
                <h3 className="mb-3 flex items-center gap-2 font-bold text-gray-900">
                  <Flame size={18} className="text-orange-500" /> 亮点速览
                </h3>
                {renderListSection(highlights, "暂无亮点信息", "normal")}
              </section>

              <section>
                <h3 className="mb-3 flex items-center gap-2 font-bold text-gray-900">
                  <CheckCircle2 size={18} className="text-green-500" /> 费用包含
                </h3>
                {renderListSection(includedItems, "暂无费用包含说明", "success")}
              </section>

              <section>
                <h3 className="mb-3 flex items-center gap-2 font-bold text-gray-900">
                  <XCircle size={18} className="text-red-400" /> 费用不含
                </h3>
                {renderListSection(excludedItems, "暂无费用不含说明", "danger")}
              </section>
            </div>
          ) : null}

          {activeTab === "notice" ? (
            <div className="space-y-6">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {route.age_limit ? (
                  <div className="rounded-lg bg-gray-50 p-3">
                    <div className="mb-1 flex items-center gap-1 text-xs text-gray-500">
                      <Info size={12} /> 年龄要求
                    </div>
                    <div className="text-sm font-medium text-gray-800">{route.age_limit}</div>
                  </div>
                ) : null}

                {route.certificate_limit ? (
                  <div className="rounded-lg bg-gray-50 p-3">
                    <div className="mb-1 flex items-center gap-1 text-xs text-gray-500">
                      <FileText size={12} /> 证件要求
                    </div>
                    <div className="truncate text-sm font-medium text-gray-800" title={route.certificate_limit}>
                      {route.certificate_limit}
                    </div>
                  </div>
                ) : null}
              </div>

              <section>
                <h3 className="mb-3 text-sm font-bold text-gray-900">重要提示</h3>
                <div className="space-y-3 rounded-lg bg-blue-50/50 p-4">
                  {noticeItems.length > 0 ? (
                    noticeItems.map((n, i) => (
                      <div key={`${n}-${i}`} className="flex items-start gap-2 text-sm text-gray-700">
                        <span className="mt-0.5 font-bold text-blue-500">{i + 1}.</span>
                        <p className="leading-relaxed">{n}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-gray-400">暂无注意事项</p>
                  )}
                </div>
              </section>
            </div>
          ) : null}
        </div>
      </div>
    );
  }, [activeTab, data, loading]);

  if (!open) {
    return null;
  }

  return (
    <div role="dialog" aria-modal="true" onClick={onClose} className="fixed inset-0 z-[1400] flex items-center justify-center bg-[rgba(15,23,42,0.45)] p-5 backdrop-blur-[8px]">
      <div
        ref={shellRef}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        className="relative h-[min(90vh,860px)] w-[min(94vw,1240px)] overflow-hidden rounded-2xl border border-gray-200 bg-[#f8fafc] shadow-[0_24px_80px_rgba(15,23,42,0.18)]"
      >
        {view}
      </div>

      <style jsx>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }

        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }

        .custom-scrollbar::-webkit-scrollbar-thumb {
          background-color: #e5e7eb;
          border-radius: 20px;
        }

        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background-color: #d1d5db;
        }
      `}</style>
    </div>
  );
}