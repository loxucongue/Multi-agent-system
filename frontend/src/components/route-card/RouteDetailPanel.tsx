"use client";

import {
  CalendarOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  EnvironmentOutlined,
  FileProtectOutlined,
  FireOutlined,
  InfoCircleOutlined,
  LinkOutlined,
  SafetyCertificateOutlined,
  TagOutlined,
} from "@ant-design/icons";
import { Button, Empty, Skeleton, Tag, Typography } from "antd";
import { useEffect, useRef } from "react";

import type { RouteFullDetail } from "@/types";

const { Paragraph, Text, Title } = Typography;

interface RouteDetailPanelProps {
  open: boolean;
  data: RouteFullDetail | null;
  loading: boolean;
  onClose: () => void;
}

interface DayPlanItem {
  title: string;
  subtitle?: string;
  content: string;
  meals?: string[];
  hotel?: string;
}

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

const toFeatureTags = (features: unknown, tags: string[]): string[] => {
  const featureTokens = ensureStringList(features).slice(0, 4);
  const tagTokens = Array.isArray(tags) ? tags.map((item) => item.trim()).filter(Boolean).slice(0, 6) : [];
  return Array.from(new Set([...featureTokens, ...tagTokens])).slice(0, 8);
};

const formatDateTime = (value: string | undefined): string => {
  if (!value) {
    return "暂无";
  }
  return value.replace("T", " ").replace("Z", "").slice(0, 19);
};

const toPriceText = (data: RouteFullDetail | null): string => {
  if (!data?.pricing) {
    return "暂无价格信息";
  }
  return `¥${data.pricing.price_min} - ¥${data.pricing.price_max} ${data.pricing.currency}`.trim();
};

const formatBaseInfo = (value: unknown): string => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return formatPlainText(value) || "待确认";
  }

  const info = value as Record<string, unknown>;
  const parts = [
    formatPlainText(info.destination_country),
    formatPlainText(info.title),
    typeof info.total_days === "number" ? `${info.total_days}天` : "",
    typeof info.total_nights === "number" ? `${info.total_nights}晚` : "",
  ].filter(Boolean);

  return parts.join(" / ") || "待确认";
};

const toScheduleDates = (value: unknown): string[] => {
  const result = new Set<string>();

  const pushDate = (raw: string) => {
    const text = raw.trim();
    if (!text) {
      return;
    }
    const match = text.match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
    if (match) {
      result.add(match[1].replaceAll("/", "-"));
      return;
    }
    result.add(text);
  };

  const walk = (input: unknown) => {
    if (Array.isArray(input)) {
      input.forEach((item) => walk(item));
      return;
    }
    if (typeof input === "object" && input !== null) {
      const record = input as Record<string, unknown>;
      const dateLike = formatPlainText(record.date ?? record.depart_date ?? record.departure_date ?? record.start_date);
      if (dateLike) {
        pushDate(dateLike);
      }
      Object.values(record).forEach((nested) => walk(nested));
      return;
    }
    if (typeof input === "string") {
      pushDate(input);
    }
  };

  walk(value);
  return Array.from(result).slice(0, 6);
};

const buildPoisSummary = (pois: unknown): string => {
  if (!Array.isArray(pois)) {
    return formatPlainText(pois);
  }

  return pois
    .map((item) => {
      if (!item || typeof item !== "object") {
        return formatPlainText(item);
      }
      const poi = item as Record<string, unknown>;
      const name = formatPlainText(poi.poi_name);
      const activity = formatPlainText(poi.activity);
      return [name, activity].filter(Boolean).join("：");
    })
    .filter(Boolean)
    .join("；");
};

const buildMeals = (value: unknown): string[] => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return ensureStringList(value);
  }
  const meals = value as Record<string, unknown>;
  const labels: Array<[string, string]> = [
    ["早餐", formatPlainText(meals.breakfast)],
    ["午餐", formatPlainText(meals.lunch)],
    ["晚餐", formatPlainText(meals.dinner)],
  ];
  return labels.filter(([, text]) => text && text !== "无" && text !== "未提及").map(([label, text]) => `${label}：${text}`);
};

const buildHotel = (value: unknown): string => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return formatPlainText(value);
  }
  const hotel = value as Record<string, unknown>;
  const parts = [formatPlainText(hotel.hotel_name), formatPlainText(hotel.hotel_level)].filter(
    (item) => item && item !== "未提及",
  );
  return parts.join(" / ");
};

const toDayPlans = (itinerary: unknown): DayPlanItem[] => {
  if (!Array.isArray(itinerary)) {
    return [];
  }

  return itinerary
    .map<DayPlanItem | null>((item, index) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const day = item as Record<string, unknown>;
      const dayNumber = formatPlainText(day.day) || `${index + 1}`;
      const subtitle = formatPlainText(day.day_title);
      const content = buildPoisSummary(day.pois) || formatPlainText(day.content) || "暂无行程描述";
      const meals = buildMeals(day.meals);
      const hotel = buildHotel(day.hotel);

      return {
        title: `第${dayNumber}天`,
        subtitle: subtitle || undefined,
        content,
        meals,
        hotel: hotel || undefined,
      };
    })
    .filter((item): item is DayPlanItem => item !== null);
};

const renderListSection = (items: string[], emptyText: string) => {
  if (items.length === 0) {
    return <Paragraph style={{ marginBottom: 0 }}>{emptyText}</Paragraph>;
  }

  return (
    <ul className="info-list">
      {items.map((item, index) => (
        <li key={`${item}-${index}`}>{item}</li>
      ))}
    </ul>
  );
};

export default function RouteDetailPanel({ open, data, loading, onClose }: RouteDetailPanelProps) {
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

  if (!open) {
    return null;
  }

  const body = (() => {
    if (loading) {
      return (
        <div className="panel-loading">
          <Skeleton active paragraph={{ rows: 10 }} />
        </div>
      );
    }

    if (!data) {
      return (
        <div className="panel-empty">
          <Empty description="暂无路线详情" />
        </div>
      );
    }

    const { route, pricing, schedule } = data;
    const dayPlans = toDayPlans(route.itinerary_json);
    const scheduleDates = toScheduleDates(schedule?.schedules_json);
    const featureTags = toFeatureTags(route.features, route.tags);
    const highlights = ensureStringList(route.highlights).slice(0, 8);
    const includedItems = ensureStringList(route.included);
    const excludedItems = ensureStringList(route.cost_excluded);
    const noticeItems = ensureStringList(route.notice);
    const ageLimit = formatPlainText(route.age_limit) || "未限制";
    const certificateLimit = formatPlainText(route.certificate_limit) || "待确认";

    return (
      <div className="panel-content">
        <section className="hero">
          <div className="hero-main">
            <div className="hero-tags">
              <Tag color="blue">路线 #{route.id}</Tag>
              <Tag icon={<ClockCircleOutlined />} color="default">
                更新于 {formatDateTime(route.updated_at)}
              </Tag>
              {route.is_hot ? <Tag color="red">热门路线</Tag> : null}
            </div>

            <Title level={3} className="title-main">
              {route.name}
            </Title>

            <div className="meta-row">
              <span className="route-chip">
                <EnvironmentOutlined />
                供应商：{route.supplier || "暂无"}
              </span>
              <span className="route-chip">
                <InfoCircleOutlined />
                行程信息：{formatBaseInfo(route.base_info)}
              </span>
            </div>

            <div className="feature-tags">
              {featureTags.length > 0 ? (
                featureTags.map((tag) => (
                  <Tag key={`f-${tag}`} className="route-detail-tag" icon={<TagOutlined />}>
                    {tag}
                  </Tag>
                ))
              ) : (
                <Text type="secondary">暂无特色标签</Text>
              )}
            </div>

            <div className="summary-card">
              <Text strong style={{ color: "#111827" }}>
                路线摘要
              </Text>
              <Paragraph style={{ margin: "8px 0 0", color: "#4b5563" }}>
                {formatPlainText(route.summary) || "暂无摘要"}
              </Paragraph>
            </div>
          </div>

          <div className="hero-side">
            <div id="route-detail-price" className="metric-card">
              <Text type="secondary">参考价格</Text>
              <Title level={4} style={{ margin: "4px 0", color: "#111827" }}>
                {toPriceText(data)}
              </Title>
              <Text type="secondary">价格更新时间：{formatDateTime(pricing?.price_updated_at)}</Text>
            </div>

            <div className="metric-card">
              <Text strong>
                <CalendarOutlined /> 最近团期
              </Text>
              <div className="schedule-tags">
                {scheduleDates.length > 0 ? (
                  scheduleDates.map((date) => (
                    <Tag key={date} color="blue">
                      {date}
                    </Tag>
                  ))
                ) : (
                  <Text type="secondary">暂无</Text>
                )}
              </div>
            </div>

            <div className="metric-card">
              <Text strong>
                <SafetyCertificateOutlined /> 出行要求
              </Text>
              <div className="requirement-list">
                <div>年龄要求：{ageLimit}</div>
                <div>证件要求：{certificateLimit}</div>
              </div>
              {route.doc_url ? (
                <a href={route.doc_url} target="_blank" rel="noreferrer" className="doc-link">
                  <LinkOutlined />
                  查看原始行程文档
                </a>
              ) : null}
            </div>
          </div>
        </section>

        <section className="content-grid">
          <div className="detail-box">
            <Title level={5} style={{ marginTop: 0 }}>
              每日行程安排
            </Title>
            {dayPlans.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无行程信息" />
            ) : (
              <div className="day-grid">
                {dayPlans.map((item, index) => (
                  <article key={`${item.title}-${index}`} className="day-card">
                    <div className="day-index">{index + 1}</div>
                    <div>
                      <Text strong>{item.title}</Text>
                      {item.subtitle ? (
                        <Paragraph style={{ margin: "6px 0 0", color: "#111827", fontWeight: 600 }}>
                          {item.subtitle}
                        </Paragraph>
                      ) : null}
                      <Paragraph style={{ margin: "8px 0 0", color: "#4b5563" }}>{item.content}</Paragraph>
                      {item.meals && item.meals.length > 0 ? (
                        <div className="day-meta">
                          <Text type="secondary">餐食：{item.meals.join(" / ")}</Text>
                        </div>
                      ) : null}
                      {item.hotel ? (
                        <div className="day-meta">
                          <Text type="secondary">住宿：{item.hotel}</Text>
                        </div>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>

          <div className="right-col">
            <section className="detail-box compact-box">
              <Title level={5} style={{ marginTop: 0 }}>
                亮点速览
              </Title>
              {renderListSection(highlights, "暂无亮点信息")}
            </section>

            <section className="detail-box compact-box">
              <Title level={5} style={{ marginTop: 0 }}>
                <FileProtectOutlined /> 费用包含
              </Title>
              {renderListSection(includedItems, "暂无费用包含说明")}
            </section>

            <section className="detail-box compact-box">
              <Title level={5} style={{ marginTop: 0 }}>
                <FireOutlined /> 费用不含
              </Title>
              {renderListSection(excludedItems, "暂无费用不含说明")}
            </section>

            <section className="detail-box compact-box">
              <Title level={5} style={{ marginTop: 0 }}>
                注意事项
              </Title>
              {renderListSection(noticeItems, "暂无注意事项")}
            </section>
          </div>
        </section>
      </div>
    );
  })();

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="route-detail-title" onClick={onClose} className="panel-mask">
      <div ref={shellRef} tabIndex={-1} onClick={(event) => event.stopPropagation()} className="panel-shell">
        <div className="panel-header">
          <div>
            <Text type="secondary">路线详情</Text>
            <Title id="route-detail-title" level={5} style={{ margin: "2px 0 0" }}>
              深入查看每日行程、费用说明和出行要求
            </Title>
          </div>
          <Button type="text" icon={<CloseOutlined />} onClick={onClose} aria-label="关闭详情" />
        </div>

        <div className="panel-body">{body}</div>
      </div>

      <style jsx>{`
        .panel-mask {
          position: fixed;
          inset: 0;
          z-index: 1400;
          background: rgba(15, 23, 42, 0.45);
          backdrop-filter: blur(8px);
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 20px;
        }

        .panel-shell {
          width: min(94vw, 1240px);
          height: min(90vh, 860px);
          border-radius: 24px;
          overflow: hidden;
          border: 1px solid #e6ebf2;
          background: #f8fafc;
          box-shadow: 0 24px 80px rgba(15, 23, 42, 0.18);
          display: flex;
          flex-direction: column;
        }

        .panel-header {
          padding: 16px 20px;
          border-bottom: 1px solid #e6ebf2;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          background: #ffffff;
          flex-shrink: 0;
        }

        .panel-body {
          min-height: 0;
          flex: 1;
          overflow: auto;
        }

        .panel-content {
          padding: 18px;
          display: grid;
          gap: 14px;
        }

        .panel-loading,
        .panel-empty {
          padding: 18px;
          height: 100%;
        }

        .hero {
          border-radius: 20px;
          border: 1px solid #e6ebf2;
          background: #ffffff;
          display: grid;
          grid-template-columns: 1fr;
          gap: 14px;
          padding: 18px;
        }

        .hero-tags,
        .feature-tags,
        .schedule-tags,
        .meta-row {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }

        .title-main {
          margin: 12px 0 10px;
          color: #111827;
          line-height: 1.2;
        }

        :global(.route-detail-tag) {
          margin-inline-end: 0;
          border-radius: 999px;
          padding-inline: 10px;
          background: #f8fafc;
          border-color: #dbe3ee;
          color: #475569;
        }

        .summary-card,
        .metric-card,
        .detail-box {
          border-radius: 18px;
          border: 1px solid #e6ebf2;
          background: #ffffff;
          padding: 16px;
        }

        .hero-side {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 12px;
        }

        .route-chip {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 6px 10px;
          border-radius: 999px;
          background: #f8fafc;
          color: #475569;
        }

        .requirement-list {
          margin-top: 8px;
          display: grid;
          gap: 6px;
          color: #4b5563;
        }

        .doc-link {
          margin-top: 10px;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          color: #2f80ed;
          font-weight: 600;
        }

        .content-grid {
          display: grid;
          grid-template-columns: 1.35fr 0.95fr;
          gap: 14px;
        }

        .day-grid {
          display: grid;
          gap: 10px;
        }

        .day-card {
          display: grid;
          grid-template-columns: 42px 1fr;
          gap: 12px;
          padding: 14px;
          border-radius: 16px;
          border: 1px solid #eef2f7;
          background: #f8fafc;
        }

        .day-index {
          width: 42px;
          height: 42px;
          border-radius: 14px;
          background: #2f80ed;
          color: #fff;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
        }

        .day-meta {
          margin-top: 6px;
        }

        .right-col {
          display: grid;
          gap: 10px;
          align-content: start;
        }

        .info-list {
          margin: 0;
          padding-left: 18px;
          display: grid;
          gap: 6px;
          color: #4b5563;
        }

        @media (max-width: 1024px) {
          .panel-shell {
            width: 100%;
            height: 94vh;
            border-radius: 20px;
          }

          .hero,
          .content-grid {
            grid-template-columns: 1fr;
          }
        }

        @media (max-width: 768px) {
          .panel-mask {
            padding: 10px;
          }

          .panel-content {
            padding: 12px;
          }

          .hero,
          .summary-card,
          .metric-card,
          .detail-box {
            padding: 14px;
          }

          .day-card {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
}
