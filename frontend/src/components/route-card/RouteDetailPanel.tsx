"use client";

import {
  CalendarOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  EnvironmentOutlined,
  FileProtectOutlined,
  FireOutlined,
  InfoCircleOutlined,
  TagOutlined,
} from "@ant-design/icons";
import { Button, Empty, Skeleton, Space, Tag, Typography } from "antd";

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
    .split(/[，,、；;|/\n]+/)
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
      .join("；");
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return Object.entries(record)
      .filter(([key]) => !/(^day$|^title$|^date$|^index$)/i.test(key))
      .map(([, nested]) => flattenToText(nested, depth + 1))
      .filter(Boolean)
      .join("；");
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

  const fallback = flattenToText(obj);
  return fallback || "暂无行程描述";
};

const toDayPlans = (itinerary: unknown): DayPlanItem[] => {
  if (typeof itinerary === "object" && itinerary !== null && !Array.isArray(itinerary)) {
    const dict = itinerary as Record<string, unknown>;

    if (Array.isArray(dict.days)) {
      return dict.days
        .map((item, index) => {
          if (typeof item === "string") {
            return { title: `第${index + 1}天`, content: item.trim() || "暂无行程描述" };
          }
          if (typeof item === "object" && item !== null) {
            const obj = item as Record<string, unknown>;
            const day = toText(obj.day) || `${index + 1}`;
            const title = day.includes("天") ? day : `第${day}天`;
            const content = buildDayContent(obj);
            return { title, content };
          }
          return null;
        })
        .filter((item): item is DayPlanItem => item !== null);
    }

    const keyedDays = Object.entries(dict)
      .filter(([key]) => /(第?\d+天|day\s*\d+)/i.test(key))
      .map(([key, value]) => {
        const normalized = key.replace(/day\s*/i, "第").replace(/(\d+)$/, "$1天");
        const title = normalized.includes("天") ? normalized : `${normalized}天`;
        const content = flattenToText(value) || "暂无行程描述";
        return { title, content };
      });

    if (keyedDays.length > 0) {
      return keyedDays;
    }
  }

  if (Array.isArray(itinerary)) {
    return itinerary
      .map((item, index) => {
        if (typeof item === "string") {
          return { title: `第${index + 1}天`, content: item.trim() || "暂无行程描述" };
        }
        if (typeof item === "object" && item !== null) {
          const obj = item as Record<string, unknown>;
          const titleRaw = toText(obj.day ?? obj.title ?? `${index + 1}`);
          const title = titleRaw.includes("天") ? titleRaw : `第${titleRaw}天`;
          const content = buildDayContent(obj);
          return { title, content };
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
  const normalized = text.replace("T", " ").replace("Z", "");
  return normalized.slice(0, 19);
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
  return `${data.pricing.price_min} - ${data.pricing.price_max} ${data.pricing.currency}`;
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
          <Empty description="暂无线路详情" />
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

    return (
      <div className="panel-content">
        <section className="hero">
          <div className="hero-main">
            <Space size={8} wrap>
              <Tag color="blue">路线ID #{route.id}</Tag>
              <Tag icon={<ClockCircleOutlined />} color="cyan">
                更新 {formatDateTime(route.updated_at)}
              </Tag>
              {route.is_hot ? <Tag color="red">热门</Tag> : null}
            </Space>

            <Title level={3} className="title-main">
              {route.name}
            </Title>

            <div className="meta-row">
              <Text type="secondary">
                <EnvironmentOutlined /> 供应商：{route.supplier || "暂无"}
              </Text>
              <Text type="secondary">
                <InfoCircleOutlined /> 行程周期：{toText(route.base_info) || "待确认"}
              </Text>
            </div>

            <div className="feature-tags">
              {featureTags.length > 0 ? (
                featureTags.map((tag) => (
                  <Tag key={`f-${tag}`} className="glass-tag" icon={<TagOutlined />}>
                    {tag}
                  </Tag>
                ))
              ) : (
                <Text type="secondary">暂无特色标签</Text>
              )}
            </div>
          </div>

          <div className="hero-side">
            <div className="metric">
              <Text type="secondary">参考价格</Text>
              <Title level={4} style={{ margin: "4px 0" }}>
                {toPriceText(data)}
              </Title>
              <Text type="secondary">价格更新：{formatDateTime(pricing?.price_updated_at)}</Text>
            </div>
            <div className="schedule-row">
              <Text strong>
                <CalendarOutlined /> 最近团期
              </Text>
              <div className="schedule-tags">
                {scheduleDates.length > 0 ? (
                  scheduleDates.map((date) => (
                    <Tag key={date} color="geekblue">
                      {date}
                    </Tag>
                  ))
                ) : (
                  <Text type="secondary">暂无</Text>
                )}
              </div>
            </div>
          </div>
        </section>

        <section className="content-grid">
          <div className="left-col glass-box">
            <Title level={5} style={{ marginTop: 0 }}>
              每日行程
            </Title>
            {dayPlans.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无行程信息" />
            ) : (
              <div className="day-grid">
                {dayPlans.slice(0, 6).map((item) => (
                  <article key={`${item.title}-${item.content.slice(0, 12)}`} className="day-card">
                    <Text strong>{item.title}</Text>
                    <Paragraph className="line-clamp-4">{item.content}</Paragraph>
                  </article>
                ))}
                {dayPlans.length > 6 ? (
                  <div className="more-day">另有 {dayPlans.length - 6} 天行程，已为您省略展示</div>
                ) : null}
              </div>
            )}
          </div>

          <div className="right-col">
            <section className="glass-box compact-box">
              <Title level={5} style={{ marginTop: 0 }}>
                摘要与亮点
              </Title>
              <Paragraph className="line-clamp-3">{toText(route.summary) || "暂无摘要"}</Paragraph>
              <ul className="highlights-list">
                {highlights.length > 0 ? highlights.map((item) => <li key={item}>{item}</li>) : <li>暂无亮点信息</li>}
              </ul>
            </section>

            <section className="glass-box compact-box">
              <Title level={5} style={{ marginTop: 0 }}>
                <FileProtectOutlined /> 费用包含
              </Title>
              <Paragraph className="line-clamp-4">{includedText}</Paragraph>
            </section>

            <section className="glass-box compact-box">
              <Title level={5} style={{ marginTop: 0 }}>
                <FireOutlined /> 费用不含
              </Title>
              <Paragraph className="line-clamp-4">{excludedText}</Paragraph>
            </section>

            <section className="glass-box compact-box">
              <Title level={5} style={{ marginTop: 0 }}>
                注意事项
              </Title>
              <Paragraph className="line-clamp-4">{noticeText}</Paragraph>
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
          <Title level={5} style={{ margin: 0 }}>
            路线详情
          </Title>
          <Button type="text" icon={<CloseOutlined />} onClick={onClose} aria-label="关闭详情" />
        </div>
        <div className="panel-body">{body}</div>
      </div>

      <style jsx>{`
        .panel-mask {
          position: fixed;
          inset: 0;
          z-index: 1400;
          background:
            radial-gradient(circle at 20% 0%, rgba(59, 130, 246, 0.25), transparent 45%),
            radial-gradient(circle at 80% 100%, rgba(56, 189, 248, 0.2), transparent 40%),
            rgba(10, 18, 35, 0.56);
          backdrop-filter: blur(10px);
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 20px;
        }

        .panel-shell {
          width: min(94vw, 1180px);
          height: min(88vh, 780px);
          border-radius: 24px;
          overflow: hidden;
          border: 1px solid rgba(255, 255, 255, 0.3);
          background: rgba(247, 250, 255, 0.72);
          backdrop-filter: blur(20px);
          box-shadow:
            0 28px 80px rgba(8, 17, 40, 0.35),
            inset 0 1px 0 rgba(255, 255, 255, 0.65);
          animation: panel-pop 220ms ease-out;
          display: flex;
          flex-direction: column;
        }

        .panel-header {
          height: 58px;
          padding: 0 16px 0 20px;
          border-bottom: 1px solid rgba(148, 163, 184, 0.25);
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: linear-gradient(135deg, rgba(255, 255, 255, 0.84), rgba(241, 245, 255, 0.66));
          flex-shrink: 0;
        }

        .panel-body {
          min-height: 0;
          flex: 1;
          overflow: hidden;
        }

        .panel-content {
          height: 100%;
          padding: 14px;
          display: grid;
          grid-template-rows: auto 1fr;
          gap: 12px;
          overflow: hidden;
        }

        .panel-loading,
        .panel-empty {
          padding: 12px;
          height: 100%;
        }

        .hero {
          border-radius: 18px;
          border: 1px solid rgba(148, 163, 184, 0.28);
          background: linear-gradient(120deg, rgba(255, 255, 255, 0.75), rgba(232, 243, 255, 0.75));
          display: grid;
          grid-template-columns: 1.65fr 1fr;
          gap: 12px;
          padding: 14px;
          overflow: hidden;
        }

        .title-main {
          margin: 10px 0 8px;
          color: #0f172a;
          line-height: 1.2;
        }

        .meta-row {
          display: flex;
          gap: 14px;
          flex-wrap: wrap;
        }

        .feature-tags {
          margin-top: 10px;
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          max-height: 70px;
          overflow: hidden;
        }

        :global(.glass-tag) {
          background: rgba(255, 255, 255, 0.65);
          border-color: rgba(59, 130, 246, 0.22);
        }

        .hero-side {
          display: grid;
          grid-template-rows: 1fr auto;
          gap: 10px;
        }

        .metric,
        .schedule-row {
          border-radius: 14px;
          border: 1px solid rgba(147, 197, 253, 0.36);
          background: rgba(255, 255, 255, 0.78);
          padding: 10px;
        }

        .schedule-tags {
          margin-top: 6px;
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          max-height: 60px;
          overflow: hidden;
        }

        .content-grid {
          min-height: 0;
          display: grid;
          grid-template-columns: 1.45fr 1fr;
          gap: 12px;
          overflow: hidden;
        }

        .left-col,
        .right-col {
          min-height: 0;
        }

        .glass-box {
          border-radius: 14px;
          border: 1px solid rgba(148, 163, 184, 0.22);
          background: rgba(255, 255, 255, 0.74);
          backdrop-filter: blur(6px);
          padding: 12px;
          overflow: hidden;
        }

        .day-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 8px;
          max-height: 100%;
        }

        .day-card {
          border: 1px solid rgba(203, 213, 225, 0.6);
          background: rgba(248, 250, 255, 0.9);
          border-radius: 10px;
          padding: 8px;
          min-height: 88px;
        }

        .more-day {
          grid-column: 1 / -1;
          font-size: 12px;
          color: #64748b;
        }

        .right-col {
          display: grid;
          grid-template-rows: repeat(4, minmax(0, 1fr));
          gap: 8px;
        }

        .compact-box :global(.ant-typography) {
          margin-bottom: 0;
        }

        .line-clamp-3,
        .line-clamp-4 {
          display: -webkit-box;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }

        .line-clamp-3 {
          -webkit-line-clamp: 3;
        }

        .line-clamp-4 {
          -webkit-line-clamp: 4;
        }

        .highlights-list {
          margin: 8px 0 0 18px;
          padding: 0;
          display: grid;
          gap: 4px;
          font-size: 13px;
        }

        @media (max-width: 1024px) {
          .panel-shell {
            height: min(90vh, 840px);
          }

          .hero {
            grid-template-columns: 1fr;
          }

          .content-grid {
            grid-template-columns: 1fr;
          }

          .right-col {
            grid-template-rows: repeat(4, minmax(88px, auto));
          }
        }

        @keyframes panel-pop {
          from {
            transform: translateY(8px) scale(0.985);
            opacity: 0;
          }
          to {
            transform: translateY(0) scale(1);
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}
