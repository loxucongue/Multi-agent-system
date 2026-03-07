"use client";

import { App, Button, Card, DatePicker, Descriptions, Input, Modal, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs, { Dayjs } from "dayjs";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useShallow } from "zustand/react/shallow";

import { useAdminStore } from "@/stores/adminStore";

const { RangePicker } = DatePicker;
const { Text } = Typography;

interface AuditLog {
  id: number;
  trace_id: string;
  run_id: string;
  session_id: string;
  intent: string;
  search_query?: string | null;
  topk_results?: unknown;
  route_id?: number | null;
  db_query_summary?: string | null;
  api_params?: Record<string, unknown> | null;
  api_latency_ms?: number | null;
  final_answer_summary?: string | null;
  token_usage?: Record<string, unknown> | null;
  error_stack?: string | null;
  coze_logid?: string | null;
  coze_debug_url?: string | null;
  created_at: string;
}

interface LogsResponse {
  logs: AuditLog[];
  total: number;
  page: number;
  size: number;
}

const toDisplay = (value: unknown): string => {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
};

export default function AdminLogsPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const { authedFetch, logout } = useAdminStore(
    useShallow((state) => ({
      authedFetch: state.authedFetch,
      logout: state.logout,
    })),
  );

  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [traceId, setTraceId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [total, setTotal] = useState(0);

  const [detailOpen, setDetailOpen] = useState(false);
  const [activeLog, setActiveLog] = useState<AuditLog | null>(null);

  const handleAuthError = (error: unknown) => {
    const text = error instanceof Error ? error.message : "请求失败";
    if (text.includes("登录已过期")) {
      logout();
      router.replace("/admin/login");
      return;
    }
    message.error(text);
  };

  const loadLogs = async (nextPage = page, nextSize = size) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("page", String(nextPage));
      params.set("size", String(nextSize));

      if (traceId.trim()) {
        params.set("trace_id", traceId.trim());
      }
      if (sessionId.trim()) {
        params.set("session_id", sessionId.trim());
      }
      if (range) {
        params.set("start", range[0].toISOString());
        params.set("end", range[1].toISOString());
      }

      const result = await authedFetch<LogsResponse>(`/admin/logs?${params.toString()}`);
      setLogs(result.logs ?? []);
      setTotal(result.total ?? 0);
      setPage(nextPage);
      setSize(nextSize);
    } catch (error) {
      handleAuthError(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadLogs(1, size);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns: ColumnsType<AuditLog> = useMemo(
    () => [
      {
        title: "时间",
        dataIndex: "created_at",
        key: "created_at",
        width: 180,
        render: (value: string) => dayjs(value).format("YYYY-MM-DD HH:mm:ss"),
      },
      {
        title: "trace_id",
        dataIndex: "trace_id",
        key: "trace_id",
        width: 230,
        ellipsis: true,
      },
      {
        title: "session_id",
        dataIndex: "session_id",
        key: "session_id",
        width: 220,
        ellipsis: true,
      },
      {
        title: "意图",
        dataIndex: "intent",
        key: "intent",
        width: 120,
      },
      {
        title: "LLM调用",
        key: "llm_calls_count",
        width: 110,
        render: (_, record) => {
          const llmCalls = (record.api_params as { llm_calls?: unknown } | null | undefined)?.llm_calls;
          return Array.isArray(llmCalls) ? llmCalls.length : 0;
        },
      },
      {
        title: "耗时(ms)",
        dataIndex: "api_latency_ms",
        key: "api_latency_ms",
        width: 100,
        render: (value: number | null | undefined) => value ?? "-",
      },
      {
        title: "回答摘要",
        dataIndex: "final_answer_summary",
        key: "final_answer_summary",
        render: (value: string | null | undefined) => (
          <Text>{value ? `${value.slice(0, 80)}${value.length > 80 ? "..." : ""}` : "-"}</Text>
        ),
      },
      {
        title: "操作",
        key: "actions",
        width: 90,
        render: (_, record) => (
          <Button
            size="small"
            onClick={() => {
              setActiveLog(record);
              setDetailOpen(true);
            }}
          >
            详情
          </Button>
        ),
      },
    ],
    [],
  );

  const llmCalls = useMemo(() => {
    const value = (activeLog?.api_params as { llm_calls?: unknown } | undefined)?.llm_calls;
    return Array.isArray(value) ? value : [];
  }, [activeLog]);

  return (
    <Card title="审计日志">
      <Space wrap size={[8, 8]} style={{ marginBottom: 12 }}>
        <Input
          placeholder="trace_id"
          value={traceId}
          onChange={(event) => setTraceId(event.target.value)}
          style={{ width: 220 }}
        />
        <Input
          placeholder="session_id"
          value={sessionId}
          onChange={(event) => setSessionId(event.target.value)}
          style={{ width: 220 }}
        />
        <RangePicker
          showTime
          value={range}
          onChange={(value) => {
            if (!value || value[0] === null || value[1] === null) {
              setRange(null);
              return;
            }
            setRange([value[0], value[1]]);
          }}
        />
        <Button type="primary" onClick={() => void loadLogs(1, size)}>
          搜索
        </Button>
        <Button
          onClick={() => {
            setTraceId("");
            setSessionId("");
            setRange(null);
            void loadLogs(1, size);
          }}
        >
          重置
        </Button>
      </Space>

      <Table
        rowKey={(row) => `${row.trace_id}-${row.id}`}
        loading={loading}
        columns={columns}
        dataSource={logs}
        pagination={{
          current: page,
          pageSize: size,
          total,
          showSizeChanger: true,
          onChange: (p, s) => {
            void loadLogs(p, s);
          },
        }}
        scroll={{ x: 1200 }}
      />

      <Modal
        title={activeLog ? `日志详情 · ${activeLog.trace_id}` : "日志详情"}
        open={detailOpen}
        width={1000}
        footer={null}
        onCancel={() => {
          setDetailOpen(false);
          setActiveLog(null);
        }}
        destroyOnHidden
      >
        {activeLog ? (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="trace_id">{activeLog.trace_id}</Descriptions.Item>
              <Descriptions.Item label="run_id">{activeLog.run_id}</Descriptions.Item>
              <Descriptions.Item label="session_id">{activeLog.session_id}</Descriptions.Item>
              <Descriptions.Item label="intent">{activeLog.intent}</Descriptions.Item>
              <Descriptions.Item label="route_id">{activeLog.route_id ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="api_latency_ms">{activeLog.api_latency_ms ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="coze_logid">{activeLog.coze_logid ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="created_at">{dayjs(activeLog.created_at).format("YYYY-MM-DD HH:mm:ss")}</Descriptions.Item>

              <Descriptions.Item label="search_query" span={2}>
                <Text style={{ whiteSpace: "pre-wrap" }}>{toDisplay(activeLog.search_query)}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="final_answer_summary" span={2}>
                <Text style={{ whiteSpace: "pre-wrap" }}>{toDisplay(activeLog.final_answer_summary)}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="topk_results" span={2}>
                <Text style={{ whiteSpace: "pre-wrap" }}>{toDisplay(activeLog.topk_results)}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="db_query_summary" span={2}>
                <Text style={{ whiteSpace: "pre-wrap" }}>{toDisplay(activeLog.db_query_summary)}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="token_usage" span={2}>
                <Text style={{ whiteSpace: "pre-wrap" }}>{toDisplay(activeLog.token_usage)}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="error_stack" span={2}>
                <Text style={{ whiteSpace: "pre-wrap", color: "#cf1322" }}>{toDisplay(activeLog.error_stack)}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="api_params" span={2}>
                <Text style={{ whiteSpace: "pre-wrap" }}>{toDisplay(activeLog.api_params)}</Text>
              </Descriptions.Item>
            </Descriptions>

            <Card size="small" title={`大模型调用输入输出（${llmCalls.length}）`}>
              {llmCalls.length === 0 ? (
                <Text type="secondary">该条日志未记录 LLM 输入输出。</Text>
              ) : (
                llmCalls.map((call, index) => (
                  <Card key={index} size="small" style={{ marginBottom: 10 }} title={`调用 #${index + 1}`}>
                    <Text style={{ whiteSpace: "pre-wrap" }}>{toDisplay(call)}</Text>
                  </Card>
                ))
              )}
            </Card>
          </Space>
        ) : null}
      </Modal>
    </Card>
  );
}
