"use client";

import { Button, Card, Checkbox, Skeleton, Space, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";

import type { RouteCard } from "@/types";

const { Paragraph, Text, Title } = Typography;

interface CandidateCardsProps {
  cards: RouteCard[];
  onSelect: (routeId: number) => void;
  onCompare: (routeIds: number[]) => void;
  loading?: boolean;
}

const formatPriceRange = (card: RouteCard): string => {
  if (card.price_min === null && card.price_max === null) {
    return "价格待更新";
  }
  if (card.price_min !== null && card.price_max !== null) {
    return `¥${card.price_min} - ¥${card.price_max}`;
  }
  if (card.price_min !== null) {
    return `¥${card.price_min} 起`;
  }
  return `最高 ¥${card.price_max}`;
};

export default function CandidateCards({
  cards,
  onSelect,
  onCompare,
  loading = false,
}: CandidateCardsProps) {
  const [selectedRouteIds, setSelectedRouteIds] = useState<number[]>([]);

  useEffect(() => {
    if (cards.length === 0) {
      setSelectedRouteIds([]);
      return;
    }
    const validIds = new Set(cards.map((card) => card.id));
    setSelectedRouteIds((prev) => prev.filter((id) => validIds.has(id)));
  }, [cards]);

  const selectedCount = selectedRouteIds.length;
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
        if (prev.includes(routeId)) {
          return prev;
        }
        return [...prev, routeId];
      }
      return prev.filter((id) => id !== routeId);
    });
  };

  if (loading) {
    return (
      <div style={{ marginTop: 12 }}>
        <Space wrap size={[12, 12]} style={{ width: "100%" }}>
          {[0, 1, 2].map((index) => (
            <Card key={index} style={{ width: 280 }}>
              <Skeleton active paragraph={{ rows: 4 }} />
            </Card>
          ))}
        </Space>
      </div>
    );
  }

  if (cards.length === 0) {
    return null;
  }

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        {cards.map((card) => {
          const checked = selectedRouteIds.includes(card.id);
          return (
            <Card
              key={card.id}
              style={{ width: 280 }}
              title={
                <Space size={8}>
                  <Checkbox
                    checked={checked}
                    onChange={(event) => toggleSelection(card.id, event.target.checked)}
                  />
                  <Title level={5} style={{ margin: 0, maxWidth: 200 }}>
                    {card.name}
                  </Title>
                </Space>
              }
            >
              <Space direction="vertical" size={10} style={{ width: "100%" }}>
                <Paragraph
                  ellipsis={{ rows: 2, tooltip: card.summary }}
                  style={{ minHeight: 44, marginBottom: 0 }}
                >
                  {card.summary}
                </Paragraph>

                <div>
                  {card.tags.map((tag) => (
                    <Tag key={`${card.id}-${tag}`}>{tag}</Tag>
                  ))}
                </div>

                <Text strong>{formatPriceRange(card)}</Text>

                <Button
                  block
                  onClick={() => {
                    onSelect(card.id);
                  }}
                >
                  查看详情
                </Button>
              </Space>
            </Card>
          );
        })}
      </div>

      <div
        style={{
          marginTop: 12,
          borderTop: "1px solid #f0f0f0",
          paddingTop: 12,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <Text type="secondary">已选 {selectedCount} 条路线</Text>
        <Button
          type="primary"
          disabled={!canCompare}
          onClick={() => {
            const finalIds = selectedRouteIds.filter((id) => cardsById.has(id));
            onCompare(finalIds);
          }}
        >
          对比选中线路
        </Button>
      </div>
    </div>
  );
}
