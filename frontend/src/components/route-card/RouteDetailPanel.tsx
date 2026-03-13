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
  content: string;
}

const toText = (value: unknown): string => String(value ?? "").trim();

const splitTokens = (value: unknown, max = 10): string[] => {
  const text = toText(value);
  if (!text) {
    return [];
  }

  const tokens = text
    .split(/[，、；;|/\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);

  return Array.from(new Set(tokens)).slice(0, max);
};

const flattenToText = (value: unknown, depth = 0): string => {
  if (depth > 2 || value == null) {
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
      .map((item) => flattenToText(item, depth + 1))
      .filter(Boolean)
      .join("，");
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return Object.entries(record)
      .filter(([key]) => !/(^day$|^title$|^date$|^index$)/i.test(key))
      .map(([, nested]) => flattenToText(nested, depth + 1))
      .filter(Boolean)
      .join("，");
  }
  return "";
};

const buildDayContent = (obj: Record<string, unknown>): string => {
  const direct = toText(
    obj.content ?? obj.description ?? obj.plan ?? obj.itinerary ?? obj.detail ?? obj.activities ?? obj.activity,
  );
  if (direct) {
    return direct;
  }

  const fromList = flattenToText(obj.spots ?? obj.pois ?? obj.scenes ?? obj.schedule ?? obj.arrangement);
  if (fromList) {
    return fromList;
  }

  return flattenToText(obj) || "暂无行程描述";
};

const toDayPlans = (itinerary: unknown): DayPlanItem[] => {
  if (typeof itinerary === "object" && itinerary !== null && !Array.isArray(itinerary)) {
    const dict = itinerary as Record<string, unknown>;

    if (Array.isArray(dict.days)) {
      return dict.days
        .map((item, index) => {
          if (typeof item === "string") {
            return { title: `第 ${index + 1} 天`, content: item.trim() || "暂无行程描述" };
          }
          if (typeof item === "object" && item !== null) {
            const obj = item as Record<string, unknown>;
            const day = toText(obj.day) || `${index + 1}`;
            const title = day.includes("天") ? day : `第 ${day} 天`;
            return { title, content: buildDayContent(obj) };
          }
          return null;
        })
        .filter((item): item is DayPlanItem => item !== null);
    }

    const keyedDays = Object.entries(dict)
      .filter(([key]) => /(第?\d+天|day\s*\d+)/i.test(key))
      .map(([key, value]) => {
        const dayNumber = key.match(/\d+/)?.[0] ?? "";
        const title = dayNumber ? `第 ${dayNumber} 天` : key;
        return { title, content: flattenToText(value) || "暂无行程描述" };
      });

    if (keyedDays.length > 0) {
      return keyedDays;
    }
  }

  if (Array.isArray(itinerary)) {
    return itinerary
      .map((item, index) => {
        if (typeof item === "string") {
          return { title: `第 ${index + 1} 天`, content: item.trim() || "暂无行程描述" };
        }
        if (typeof item === "object" && item !== null) {
          const obj = item as Record<string, unknown>;
          const titleRaw = toText(obj.day ?? obj.title ?? `${index + 1}`);
          const title = titleRaw.includes("天") ? titleRaw : `第 ${titleRaw} 天`;
          return { title, content: buildDayContent(obj) };
        }
        return null;
      })
      .filter((item): item is DayPlanItem => item !== null);
  }

  if (typeof itinerary === "string" && itinerary.trim()) {
    return [{ title: "行程概览", content: itinerary.trim() }];
  }

  return [];
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
      const dateLike = toText(record.date ?? record.depart_date ?? record.departure_date ?? record.start_date);
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

const formatDateTime = (value: string | undefined): string => {
  const text = toText(value);
  if (!text) {
    return "暂无";
  }
  return text.replace("T", " ").replace("Z", "").slice(0, 19);
};

const toHighlights = (value: unknown): string[] => {
  const text = toText(value);
  if (!text) {
    return [];
  }
  return text
    .split(/[。；;\n]+/)
    .map((item) => item.trim())
    .filter((item) => item.length > 1)
    .slice(0, 4);
};

const toFeatureTags = (features: unknown, tags: string[]): string[] => {
  const featureTokens = splitTokens(features, 6);
  const tagTokens = Array.isArray(tags) ? tags.map((item) => toText(item)).filter(Boolean).slice(0, 6) : [];
  return Array.from(new Set([...featureTokens, ...tagTokens])).slice(0, 8);
};

const toPriceText = (data: RouteFullDetail | null): string => {
  if (!data?.pricing) {
    return "暂无价格信息";
  }
  return `¥${data.pricing.price_min} - ¥${data.pricing.price_max} ${data.pricing.currency}`.trim();
};

export default function RouteDetailPanel({ open, data, loading, onClose }: RouteDetailPanelProps) {
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
    const highlights = toHighlights(route.highlights);
    const includedText = toText(route.included) || "暂无";
    const excludedText = toText(route.cost_excluded) || "暂无";
    const noticeText = toText(route.notice) || "暂无";
    const ageLimit = toText(route.age_limit) || "未限制";
    const certificateLimit = toText(route.certificate_limit) || "待顾问确认";

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
                行程信息：{toText(route.base_info) || "待确认"}
              </span>
            </div>

            <div className="feature-tags">
              {featureTags.length > 0 ? (
                featureTags.map((tag) => (
                  <Tag key={`f-${tag}`} className="detail-tag" icon={<TagOutlined />}>
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
              <Paragraph style={{ margin: "8px 0 0", color: "#4b5563" }}>{toText(route.summary) || "暂无摘要"}</Paragraph>
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
                      <Paragraph style={{ margin: "8px 0 0", color: "#4b5563" }}>{item.content}</Paragraph>
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
              <ul className="highlights-list">
                {highlights.length > 0 ? highlights.map((item) => <li key={item}>{item}</li>) : <li>暂无亮点信息</li>}
              </ul>
            </section>

            <section className="detail-box compact-box">
              <Title level={5} style={{ marginTop: 0 }}>
                <FileProtectOutlined /> 费用包含
              </Title>
              <Paragraph style={{ marginBottom: 0 }}>{includedText}</Paragraph>
            </section>

            <section className="detail-box compact-box">
              <Title level={5} style={{ marginTop: 0 }}>
                <FireOutlined /> 费用不含
              </Title>
              <Paragraph style={{ marginBottom: 0 }}>{excludedText}</Paragraph>
            </section>

            <section className="detail-box compact-box">
              <Title level={5} style={{ marginTop: 0 }}>
                注意事项
              </Title>
              <Paragraph style={{ marginBottom: 0 }}>{noticeText}</Paragraph>
            </section>
          </div>
        </section>
      </div>
    );
  })();

  return (
    <div role="dialog" aria-modal="true" onClick={onClose} className="panel-mask">
      <div onClick={(event) => event.stopPropagation()} className="panel-shell">
        <div className="panel-header">
          <div>
            <Text type="secondary">路线详情</Text>
            <Title level={5} style={{ margin: "2px 0 0" }}>
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
          grid-template-columns: 1.45fr 0.95fr;
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

        :global(.detail-tag) {
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

        .right-col {
          display: grid;
          gap: 10px;
          align-content: start;
        }

        .highlights-list {
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
