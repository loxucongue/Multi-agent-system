"use client";

import { App, Button, Card, DatePicker, Descriptions, Input, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs, { Dayjs } from "dayjs";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { useAdminStore } from "@/stores/adminStore";

const { RangePicker } = DatePicker;
const { Text } = Typography;

interface AuditLog {
  id: number;
  trace_id: string;
  run_id: string;
  session_id: string;
  intent: string;
  route_id?: number | null;
  api_latency_ms?: number | null;
  final_answer_summary?: string | null;
  token_usage?: number | null;
  error_stack?: string | null;
  created_at: string;
  [key: string]: unknown;
}

interface LogsResponse {
  logs: AuditLog[];
  total: number;
  page: number;
  size: number;
}

export default function AdminLogsPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const { authedFetch, logout } = useAdminStore((state) => ({
    authedFetch: state.authedFetch,
    logout: state.logout,
  }));

  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [traceId, setTraceId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [expandedRowKeys, setExpandedRowKeys] = useState<React.Key[]>([]);

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
        title: "intent",
        dataIndex: "intent",
        key: "intent",
        width: 120,
      },
      {
        title: "route_id",
        dataIndex: "route_id",
        key: "route_id",
        width: 90,
        render: (value: number | null | undefined) => value ?? "-",
      },
      {
        title: "耗时(ms)",
        dataIndex: "api_latency_ms",
        key: "api_latency_ms",
        width: 100,
        render: (value: number | null | undefined) => value ?? "-",
      },
      {
        title: "answer_summary",
        dataIndex: "final_answer_summary",
        key: "final_answer_summary",
        render: (value: string | null | undefined) => (
          <Text>{value ? `${value.slice(0, 80)}${value.length > 80 ? "..." : ""}` : "-"}</Text>
        ),
      },
    ],
    [],
  );

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
        <Button
          type="primary"
          onClick={() => {
            void loadLogs(1, size);
          }}
        >
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
        expandable={{
          expandedRowKeys,
          onExpandedRowsChange: (keys) => setExpandedRowKeys([...keys]),
          expandedRowRender: (record) => (
            <Descriptions column={2} size="small" bordered>
              {Object.entries(record).map(([k, v]) => (
                <Descriptions.Item key={k} label={k} span={k === "error_stack" || k === "db_query_summary" ? 2 : 1}>
                  <Text style={{ whiteSpace: "pre-wrap" }}>
                    {typeof v === "object" && v !== null ? JSON.stringify(v, null, 2) : String(v ?? "-")}
                  </Text>
                </Descriptions.Item>
              ))}
            </Descriptions>
          ),
        }}
        pagination={{
          current: page,
          pageSize: size,
          total,
          showSizeChanger: true,
          onChange: (p, s) => {
            void loadLogs(p, s);
          },
        }}
        scroll={{ x: 1100 }}
      />
    </Card>
  );
}
