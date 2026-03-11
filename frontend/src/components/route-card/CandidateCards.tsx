"use client";

import { Button, Card, Checkbox, Empty, Skeleton, Space, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";

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

const deriveDays = (summary: string): number => {
  const match = summary.match(/(\d{1,2})\s*天/);
  if (!match) {
    return 0;
  }
  return Number(match[1]);
};

const deriveHighlights = (summary: string): string[] => {
  const parts = summary
    .split(/[，。；,;.!?\n]+/)
    .map((item) => item.trim())
    .filter((item) => item.length >= 3);
  if (parts.length === 0) {
    return ["行程亮点待确认"];
  }
  return parts.slice(0, 5);
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
  const currentSelectedRouteIds = isControlled ? selectedRouteIds : internalSelectedRouteIds;

  const setSelectedRouteIds = (updater: (prev: number[]) => number[]) => {
    if (isControlled) {
      const next = updater(currentSelectedRouteIds);
      const sameLength = next.length === currentSelectedRouteIds.length;
      const sameItems = sameLength && next.every((id, index) => id === currentSelectedRouteIds[index]);
      if (!sameItems) {
        onSelectedRouteIdsChange?.(next);
      }
      return;
    }
    setInternalSelectedRouteIds(updater);
  };

  useEffect(() => {
    const validIds = new Set(cards.map((card) => card.id));
    setSelectedRouteIds((prev) => prev.filter((id) => validIds.has(id)));
  }, [cards, isControlled, currentSelectedRouteIds]);

  const selectedCount = currentSelectedRouteIds.length + Math.max(0, extraSelectedCount);
  const canCompare = selectedCount >= 2;

  const cardsById = useMemo(() => {
    const map = new Map<number, RouteCard>();
    cards.forEach((card) => {
      map.set(card.id, card);
    });
    return map;
  }, [cards]);

  const toggleSelection = (routeId: number, checked: boolean) => {
    setSelectedRouteIds((prev) => {
      if (checked) {
        return prev.includes(routeId) ? prev : [...prev, routeId];
      }
      return prev.filter((id) => id !== routeId);
    });
  };

  if (loading) {
    return (
      <div style={{ marginTop: 12 }}>
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          {[0, 1, 2].map((index) => (
            <Card key={index} style={{ width: "100%" }}>
              <Skeleton active paragraph={{ rows: 4 }} />
            </Card>
          ))}
        </Space>
      </div>
    );
  }

  if (cards.length === 0) {
    return (
      <Card style={{ marginTop: 12 }}>
        <Empty description="当前没有符合条件的候选线路" />
        {onGuideRematch ? (
          <div style={{ marginTop: 8, textAlign: "center" }}>
            <Button onClick={onGuideRematch}>重新引导匹配需求</Button>
          </div>
        ) : null}
      </Card>
    );
  }

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingBottom: 72 }}>
        {cards.map((card) => {
          const checked = currentSelectedRouteIds.includes(card.id);
          const days = deriveDays(card.summary);
          const highlights = deriveHighlights(card.summary);
          return (
            <Card key={card.id} style={{ width: "100%" }}>
              <Space direction="vertical" size={10} style={{ width: "100%" }}>
                <Space size={8} align="center">
                  <Checkbox checked={checked} onChange={(event) => toggleSelection(card.id, event.target.checked)} />
                  <Text>加入对比</Text>
                </Space>

                <Space size={8} align="start" style={{ justifyContent: "space-between", width: "100%" }}>
                  <Title level={5} style={{ margin: 0, maxWidth: "78%" }}>
                    {card.name}
                  </Title>
                  <Tag color="blue">候选方案</Tag>
                </Space>

                <Text type="secondary">供应商：平台精选 · 天数：{days}天</Text>

                <div style={{ borderTop: "1px solid #f0f0f0", paddingTop: 8 }}>
                  <Text strong>亮点</Text>
                  <ul style={{ margin: "8px 0 0 18px", padding: 0 }}>
                    {highlights.map((highlight) => (
                      <li key={`${card.id}-${highlight}`} style={{ marginBottom: 4 }}>
                        {highlight}
                      </li>
                    ))}
                  </ul>
                </div>

                <div>
                  <Text strong>标签</Text>
                  <div style={{ marginTop: 8 }}>
                    {card.tags.map((tag) => (
                      <Tag key={`${card.id}-${tag}`}>{tag}</Tag>
                    ))}
                  </div>
                </div>

                <div>
                  <Text strong>摘要</Text>
                  <Paragraph ellipsis={{ rows: 3, tooltip: card.summary }} style={{ marginBottom: 0, marginTop: 8 }}>
                    {card.summary}
                  </Paragraph>
                </div>

                <Button block onClick={() => onSelect(card.id)}>
                  查看详情
                </Button>
              </Space>
            </Card>
          );
        })}
      </div>

      <div
        style={{
          position: "sticky",
          bottom: 0,
          zIndex: 10,
          background: "#f5f7fb",
          borderTop: "1px solid #dbe3f3",
          paddingTop: 10,
          paddingBottom: 8,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <Text type="secondary">已选 {selectedCount} 条线路</Text>
        <Button
          type="primary"
          disabled={!canCompare}
          onClick={() => {
            const finalIds = currentSelectedRouteIds.filter((id) => cardsById.has(id));
            onCompare(finalIds);
          }}
        >
          对比选中线路
        </Button>
      </div>
    </div>
  );
}
