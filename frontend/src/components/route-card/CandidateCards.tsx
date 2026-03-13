"use client";

import { CheckCircleOutlined, CompassOutlined, SwapOutlined } from "@ant-design/icons";
import { Button, Card, Checkbox, Empty, Skeleton, Tag, Typography } from "antd";
import { useMemo, useState } from "react";

import type { RouteCard } from "@/types";

const { Paragraph, Text, Title } = Typography;

interface CandidateCardsProps {
  cards: RouteCard[];
  onSelect: (routeId: number) => void;
  onCompare: (routeIds: number[]) => void;
  onGuideRematch?: () => void;
  loading?: boolean;
  selectedRouteIds?: number[];
  onSelectedRouteIdsChange?: (routeIds: number[]) => void;
  extraSelectedCount?: number;
}

const getDays = (card: RouteCard): number => {
  if (typeof card.days === "number" && card.days > 0) {
    return card.days;
  }
  return 0;
};

const getHighlights = (card: RouteCard): string[] => {
  const tags = Array.isArray(card.highlight_tags) ? card.highlight_tags.filter(Boolean) : [];
  if (tags.length > 0) {
    return tags.slice(0, 3);
  }
  return ["亮点信息待补充"];
};

const formatPrice = (card: RouteCard) => {
  if (card.price_min == null || card.price_max == null) {
    return "待报价确认";
  }

  return `¥${card.price_min} - ¥${card.price_max}`;
};

export default function CandidateCards({
  cards,
  onSelect,
  onCompare,
  onGuideRematch,
  loading = false,
  selectedRouteIds,
  onSelectedRouteIdsChange,
  extraSelectedCount = 0,
}: CandidateCardsProps) {
  const [internalSelectedRouteIds, setInternalSelectedRouteIds] = useState<number[]>([]);
  const isControlled = Array.isArray(selectedRouteIds);
  const rawSelectedRouteIds = isControlled ? selectedRouteIds : internalSelectedRouteIds;

  const validRouteIds = useMemo(() => new Set(cards.map((card) => card.id)), [cards]);
  const currentSelectedRouteIds = useMemo(
    () => rawSelectedRouteIds.filter((id) => validRouteIds.has(id)),
    [rawSelectedRouteIds, validRouteIds],
  );

  const setSelectedRouteIds = (updater: (prev: number[]) => number[]) => {
    const next = updater(currentSelectedRouteIds);
    if (isControlled) {
      onSelectedRouteIdsChange?.(next);
      return;
    }

    setInternalSelectedRouteIds(next);
  };

  const selectedCount = currentSelectedRouteIds.length + Math.max(0, extraSelectedCount);
  const canCompare = selectedCount >= 2;

  if (loading) {
    return (
      <div className="loading-list">
        {[0, 1, 2].map((item) => (
          <Card key={item} className="candidate-loading-card">
            <Skeleton active paragraph={{ rows: 4 }} />
          </Card>
        ))}

        <style jsx>{`
          .loading-list {
            display: grid;
            gap: 12px;
          }

          :global(.candidate-loading-card) {
            border-radius: 18px;
          }
        `}</style>
      </div>
    );
  }

  if (!cards.length) {
    return (
      <div className="empty-card">
        <Empty description="当前没有符合条件的候选路线。" />
        {onGuideRematch ? (
          <Button onClick={onGuideRematch} className="rematch-button">
            重新引导匹配需求
          </Button>
        ) : null}

        <style jsx>{`
          .empty-card {
            display: grid;
            justify-items: center;
            gap: 12px;
            padding: 28px 18px;
            border-radius: 18px;
            border: 1px solid #e5ebf3;
            background: #ffffff;
          }

          .rematch-button {
            border-radius: 999px;
          }
        `}</style>
      </div>
    );
  }

  return (
    <div className="candidate-shell">
      <div className="candidate-head">
        <div>
          <Title level={5} style={{ margin: 0, color: "#111827" }}>
            候选方案
          </Title>
          <Text type="secondary">已整理 {cards.length} 条可进一步比较的路线。</Text>
        </div>
      </div>

      <div className="candidate-list">
        {cards.map((card, index) => {
          const checked = currentSelectedRouteIds.includes(card.id);
          const days = getDays(card);
          const highlights = getHighlights(card);

          return (
            <div key={card.id} className={`candidate-card ${checked ? "checked" : ""}`}>
              <div className="card-top">
                <label className="select-toggle">
                  <Checkbox
                    checked={checked}
                    onChange={(event) => {
                      setSelectedRouteIds((prev) => {
                        if (event.target.checked) {
                          return prev.includes(card.id) ? prev : [...prev, card.id];
                        }
                        return prev.filter((id) => id !== card.id);
                      });
                    }}
                  />
                  <span>加入对比</span>
                </label>

                <div className="badge-group">
                  <Tag color={index === 0 ? "blue" : "default"}>{index === 0 ? "优先候选" : "候选路线"}</Tag>
                  <Tag>{days > 0 ? `${days} 天` : "天数待确认"}</Tag>
                </div>
              </div>

              <div className="title-row">
                <div>
                  <Title level={5} style={{ margin: 0, color: "#111827" }}>
                    {card.name}
                  </Title>
                  <div className="tag-row">
                    {card.tags.map((tag) => (
                      <Tag key={`${card.id}-${tag}`} className="candidate-route-tag" icon={<CompassOutlined />}>
                        {tag}
                      </Tag>
                    ))}
                  </div>
                </div>

                <div className="price-box">
                  <span className="price-label">参考价格</span>
                  <span className="price-value">{formatPrice(card)}</span>
                </div>
              </div>

              <Paragraph className="summary" ellipsis={{ rows: 3, tooltip: card.summary }}>
                {card.summary}
              </Paragraph>

              <div className="highlight-list">
                {highlights.map((highlight) => (
                  <div key={`${card.id}-${highlight}`} className="highlight-item">
                    <CheckCircleOutlined />
                    <span>{highlight}</span>
                  </div>
                ))}
              </div>

              <Button block onClick={() => onSelect(card.id)} className="detail-button">
                查看详情与每日行程
              </Button>
            </div>
          );
        })}
      </div>

      <div className="compare-bar">
        <div>
          <Text strong style={{ color: "#111827" }}>
            已选 {selectedCount} 条路线
          </Text>
          <div className="compare-hint">至少选择 2 条路线后可发起对比。</div>
        </div>

        <Button
          type="primary"
          icon={<SwapOutlined />}
          disabled={!canCompare}
          onClick={() => {
            onCompare(currentSelectedRouteIds);
          }}
          className="compare-button"
        >
          开始对比
        </Button>
      </div>

      <style jsx>{`
        .candidate-shell {
          display: grid;
          gap: 12px;
        }

        .candidate-head {
          padding: 4px 2px 0;
        }

        .candidate-list {
          display: grid;
          gap: 12px;
        }

        .candidate-card {
          display: grid;
          gap: 14px;
          padding: 16px;
          border-radius: 18px;
          border: 1px solid #e5ebf3;
          background: #ffffff;
        }

        .candidate-card.checked {
          border-color: #bfd7ff;
          box-shadow: 0 10px 24px rgba(47, 128, 237, 0.08);
        }

        .card-top,
        .title-row,
        .compare-bar {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          align-items: flex-start;
          flex-wrap: wrap;
        }

        .select-toggle {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          color: #475569;
          cursor: pointer;
        }

        .badge-group {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
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

        .price-label,
        .compare-hint {
          font-size: 12px;
          color: #8a94a6;
        }

        .price-value {
          color: #111827;
          font-weight: 700;
        }

        .tag-row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 10px;
        }

        :global(.candidate-route-tag) {
          margin: 0;
          border-radius: 999px;
          color: #475569;
          background: #f8fafc;
          border-color: #dbe3ee;
        }

        .summary {
          margin: 0;
          color: #4b5563;
        }

        .highlight-list {
          display: grid;
          gap: 8px;
        }

        .highlight-item {
          display: flex;
          gap: 8px;
          align-items: flex-start;
          padding: 10px 12px;
          border-radius: 14px;
          background: #f8fafc;
          color: #475569;
        }

        .detail-button,
        .compare-button {
          height: 40px;
          border-radius: 12px;
          font-weight: 600;
        }

        .compare-bar {
          position: sticky;
          bottom: 0;
          padding: 14px 16px;
          border-radius: 18px;
          border: 1px solid #e5ebf3;
          background: rgba(255, 255, 255, 0.96);
          box-shadow: 0 -6px 20px rgba(15, 23, 42, 0.05);
          backdrop-filter: blur(8px);
        }
      `}</style>
    </div>
  );
}
