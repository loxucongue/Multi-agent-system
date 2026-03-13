"use client";

import { CompassOutlined, StarFilled } from "@ant-design/icons";
import { Button, Checkbox, Empty, Skeleton, Tag, Typography } from "antd";

import type { RouteCard } from "@/types";

const { Paragraph, Text, Title } = Typography;

export interface ActiveRouteCardData
  extends Pick<RouteCard, "id" | "name" | "tags" | "summary" | "price_min" | "price_max"> {
  supplier: string;
  days: number;
  highlights: string[];
}

interface ActiveRouteCardProps {
  activeRouteId: number | null;
  route: ActiveRouteCardData | null;
  loading?: boolean;
  compareChecked?: boolean;
  onCompareCheckedChange?: (checked: boolean) => void;
  onViewItinerary?: (route: ActiveRouteCardData) => void;
}

const formatPrice = (priceMin: number | null, priceMax: number | null) => {
  if (priceMin == null || priceMax == null) {
    return "待顾问确认";
  }

  return `¥${priceMin} - ¥${priceMax}`;
};

export default function ActiveRouteCard({
  activeRouteId,
  route,
  loading = false,
  compareChecked = false,
  onCompareCheckedChange,
  onViewItinerary,
}: ActiveRouteCardProps) {
  if (loading) {
    return (
      <div className="card">
        <Skeleton active paragraph={{ rows: 5 }} />
        <style jsx>{`
          .card {
            padding: 18px;
            border-radius: 18px;
            border: 1px solid #e5ebf3;
            background: #ffffff;
          }
        `}</style>
      </div>
    );
  }

  if (!activeRouteId || !route) {
    return (
      <div className="empty-card">
        <Empty description="还没有主推路线，先在聊天区补充目的地、预算或出行天数。" />

        <style jsx>{`
          .empty-card {
            padding: 24px 18px;
            border-radius: 18px;
            border: 1px solid #e5ebf3;
            background: #ffffff;
          }
        `}</style>
      </div>
    );
  }

  return (
    <div className="active-card">
      <div className="top-row">
        <div className="badge-row">
          <span className="featured-badge">
            <StarFilled />
            主推路线
          </span>
          <Tag bordered={false} className="active-supplier-tag">
            {route.supplier}
          </Tag>
        </div>

        <label className="compare-toggle">
          <Checkbox checked={compareChecked} onChange={(event) => onCompareCheckedChange?.(event.target.checked)} />
          <span>加入对比</span>
        </label>
      </div>

      <div className="title-row">
        <div>
          <Title level={5} style={{ margin: 0, color: "#111827" }}>
            {route.name}
          </Title>
          <Text type="secondary">
            {route.days > 0 ? `${route.days} 天行程` : "行程天数待确认"} · 推荐优先查看
          </Text>
        </div>

        <div className="price-box">
          <span className="label">参考价格</span>
          <span className="value">{formatPrice(route.price_min, route.price_max)}</span>
        </div>
      </div>

      <Paragraph className="summary">{route.summary}</Paragraph>

      <div className="metric-grid">
        <MetricCard label="主题偏好" value={route.tags[0] ?? "灵活匹配"} />
        <MetricCard label="供应商" value={route.supplier || "待确认"} />
        <MetricCard label="行程天数" value={route.days > 0 ? `${route.days} 天` : "待确认"} />
      </div>

      <div className="section">
        <Text strong style={{ color: "#111827" }}>
          推荐理由
        </Text>
        <div className="highlight-list">
          {route.highlights.slice(0, 4).map((highlight) => (
            <div key={highlight} className="highlight-item">
              <CompassOutlined />
              <span>{highlight}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="tag-row">
        {route.tags.map((tag) => (
          <Tag key={tag} className="active-route-tag">
            {tag}
          </Tag>
        ))}
      </div>

      <Button
        type="primary"
        block
        onClick={() => {
          onViewItinerary?.(route);
        }}
        className="detail-button"
      >
        查看路线详情
      </Button>

      <style jsx>{`
        .active-card {
          display: grid;
          gap: 16px;
          padding: 18px;
          border-radius: 18px;
          border: 1px solid #e5ebf3;
          background: #ffffff;
        }

        .top-row,
        .title-row {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
          flex-wrap: wrap;
        }

        .badge-row {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          align-items: center;
        }

        .featured-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 4px 10px;
          border-radius: 999px;
          background: #eff6ff;
          color: #2f80ed;
          font-size: 12px;
          font-weight: 600;
        }

        :global(.active-supplier-tag) {
          margin: 0;
          padding: 4px 10px;
          border-radius: 999px;
          color: #64748b;
          background: #f4f6f8;
        }

        .compare-toggle {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          color: #475569;
          cursor: pointer;
        }

        .price-box {
          min-width: 124px;
          padding: 10px 12px;
          border-radius: 14px;
          background: #f8fafc;
          border: 1px solid #e5ebf3;
          display: grid;
          gap: 4px;
        }

        .label {
          font-size: 12px;
          color: #8a94a6;
        }

        .value {
          font-size: 16px;
          font-weight: 700;
          color: #111827;
        }

        .summary {
          margin: 0;
          color: #4b5563;
          line-height: 1.8;
        }

        .metric-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 10px;
        }

        .section {
          display: grid;
          gap: 10px;
        }

        .highlight-list {
          display: grid;
          gap: 8px;
        }

        .highlight-item {
          display: flex;
          gap: 10px;
          align-items: flex-start;
          padding: 10px 12px;
          border-radius: 14px;
          background: #f8fafc;
          color: #475569;
        }

        .tag-row {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }

        :global(.active-route-tag) {
          margin: 0;
          border-radius: 999px;
          color: #475569;
          background: #f8fafc;
          border-color: #dbe3ee;
        }

        .detail-button {
          height: 42px;
          border-radius: 12px;
          font-weight: 600;
        }

        @media (max-width: 768px) {
          .metric-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <>
      <div className="metric-card">
        <span className="metric-label">{label}</span>
        <span className="metric-value">{value}</span>
      </div>

      <style jsx>{`
        .metric-card {
          display: grid;
          gap: 4px;
          padding: 12px;
          border-radius: 14px;
          border: 1px solid #e5ebf3;
          background: #f8fafc;
        }

        .metric-label {
          font-size: 12px;
          color: #8a94a6;
        }

        .metric-value {
          color: #111827;
          font-weight: 600;
        }
      `}</style>
    </>
  );
}
