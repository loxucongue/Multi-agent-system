"use client";

import { App, Button, Card, DatePicker, Descriptions, Input, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs, { Dayjs } from "dayjs";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useShallow } from "zustand/react/shallow";

import { useAdminStore } from "@/stores/adminStore";

const { RangePicker } = DatePicker;
const { Text } = Typography;

interface CozeLog {
  id: number;
  trace_id: string;
  session_id: string;
  call_type: string;
  workflow_id?: string | null;
  endpoint: string;
  request_params?: Record<string, unknown> | null;
  response_code?: number | null;
  response_data?: Record<string, unknown> | null;
  coze_logid?: string | null;
  debug_url?: string | null;
  token_count?: number | null;
  latency_ms: number;
  status: string;
  error_message?: string | null;
  created_at: string;
}

interface CozeLogsResponse {
  logs: CozeLog[];
  total: number;
  page: number;
  size: number;
}

interface CozeStats {
  total_calls: number;
  success_count: number;
  error_count: number;
  success_rate: number;
  avg_latency_ms: number;
  total_tokens: number;
}

const CALL_TYPE_OPTIONS = [
  { label: "全部", value: "" },
  { label: "线路检索", value: "route_search" },
  { label: "签证检索", value: "visa_search" },
  { label: "外围信息", value: "external_info" },
  { label: "OAuth取Token", value: "oauth_token" },
];

const STATUS_OPTIONS = [
  { label: "全部", value: "" },
  { label: "成功", value: "success" },
  { label: "失败", value: "error" },
  { label: "中断", value: "interrupted" },
];

const STATUS_COLOR: Record<string, string> = {
  success: "green",
  error: "red",
  interrupted: "orange",
};

export default function AdminCozeLogsPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const { authedFetch, logout } = useAdminStore(
    useShallow((state) => ({ authedFetch: state.authedFetch, logout: state.logout })),
  );

  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<CozeLog[]>([]);
  const [stats, setStats] = useState<CozeStats | null>(null);
  const [traceId, setTraceId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [callType, setCallType] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
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
      if (traceId.trim()) params.set("trace_id", traceId.trim());
      if (sessionId.trim()) params.set("session_id", sessionId.trim());
      if (callType) params.set("call_type", callType);
      if (statusFilter) params.set("status", statusFilter);
      if (range) {
        params.set("start", range[0].toISOString());
        params.set("end", range[1].toISOString());
      }
      const result = await authedFetch<CozeLogsResponse>(`/admin/coze-logs?${params.toString()}`);
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

  const loadStats = async () => {
    try {
      const result = await authedFetch<CozeStats>("/admin/coze-logs/stats");
      setStats(result);
    } catch {
      return;
    }
  };

  useEffect(() => {
    void loadLogs(1, size);
    void loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns: ColumnsType<CozeLog> = useMemo(
    () => [
      {
        title: "时间",
        dataIndex: "created_at",
        key: "created_at",
        width: 170,
        render: (value: string) => dayjs(value).format("MM-DD HH:mm:ss"),
      },
      { title: "类型", dataIndex: "call_type", key: "call_type", width: 120 },
      {
        title: "状态",
        dataIndex: "status",
        key: "status",
        width: 90,
        render: (value: string) => <Tag color={STATUS_COLOR[value] || "default"}>{value}</Tag>,
      },
      { title: "耗时(ms)", dataIndex: "latency_ms", key: "latency_ms", width: 100 },
      {
        title: "token",
        dataIndex: "token_count",
        key: "token_count",
        width: 80,
        render: (value: number | null | undefined) => value ?? "-",
      },
      { title: "trace_id", dataIndex: "trace_id", key: "trace_id", width: 220, ellipsis: true },
      { title: "session_id", dataIndex: "session_id", key: "session_id", width: 200, ellipsis: true },
      {
        title: "debug",
        dataIndex: "debug_url",
        key: "debug_url",
        width: 80,
        render: (value: string | null | undefined) =>
          value ? (
            <a href={value} target="_blank" rel="noreferrer">
              查看
            </a>
          ) : (
            "-"
          ),
      },
      {
        title: "错误",
        dataIndex: "error_message",
        key: "error_message",
        render: (value: string | null | undefined) => (value ? <Text type="danger">{value.slice(0, 60)}</Text> : "-"),
      },
    ],
    [],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {stats && (
        <Card size="small" title="调用统计">
          <Space size={24} wrap>
            <span>总调用: <strong>{stats.total_calls}</strong></span>
            <span>成功率: <strong>{stats.success_rate}%</strong></span>
            <span>平均耗时: <strong>{stats.avg_latency_ms}ms</strong></span>
            <span>总Token: <strong>{stats.total_tokens}</strong></span>
          </Space>
        </Card>
      )}

      <Card title="Coze 调用日志">
        <Space wrap size={[8, 8]} style={{ marginBottom: 12 }}>
          <Input placeholder="trace_id" value={traceId} onChange={(event) => setTraceId(event.target.value)} style={{ width: 200 }} />
          <Input placeholder="session_id" value={sessionId} onChange={(event) => setSessionId(event.target.value)} style={{ width: 200 }} />
          <Select options={CALL_TYPE_OPTIONS} value={callType} onChange={setCallType} style={{ width: 150 }} />
          <Select options={STATUS_OPTIONS} value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }} />
          <RangePicker
            showTime
            value={range}
            onChange={(value) => {
              if (!value || !value[0] || !value[1]) {
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
              setCallType("");
              setStatusFilter("");
              setRange(null);
              void loadLogs(1, size);
              void loadStats();
            }}
          >
            重置
          </Button>
        </Space>

        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={logs}
          expandable={{
            expandedRowKeys,
            onExpandedRowsChange: (keys) => setExpandedRowKeys([...keys]),
            expandedRowRender: (record) => (
              <Descriptions column={2} size="small" bordered>
                <Descriptions.Item label="workflow_id">{record.workflow_id ?? "-"}</Descriptions.Item>
                <Descriptions.Item label="endpoint">{record.endpoint}</Descriptions.Item>
                <Descriptions.Item label="coze_logid">{record.coze_logid ?? "-"}</Descriptions.Item>
                <Descriptions.Item label="response_code">{record.response_code ?? "-"}</Descriptions.Item>
                <Descriptions.Item label="请求参数" span={2}>
                  <Text style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
                    {record.request_params ? JSON.stringify(record.request_params, null, 2) : "-"}
                  </Text>
                </Descriptions.Item>
                <Descriptions.Item label="响应数据" span={2}>
                  <Text style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
                    {record.response_data ? JSON.stringify(record.response_data, null, 2) : "-"}
                  </Text>
                </Descriptions.Item>
              </Descriptions>
            ),
          }}
          pagination={{
            current: page,
            pageSize: size,
            total,
            showSizeChanger: true,
            onChange: (nextPage, nextSize) => void loadLogs(nextPage, nextSize),
          }}
          scroll={{ x: 1200 }}
        />
      </Card>
    </div>
  );
}
