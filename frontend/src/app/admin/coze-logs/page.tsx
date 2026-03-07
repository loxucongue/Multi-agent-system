"use client";

import { App, Button, Card, DatePicker, Descriptions, Input, Modal, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs, { Dayjs } from "dayjs";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useShallow } from "zustand/react/shallow";

import { useAdminStore } from "@/stores/adminStore";

const { RangePicker } = DatePicker;
const { Text, Link } = Typography;

interface CozeLog {
  id: number;
  trace_id: string;
  session_id: string;
  call_type: string;
  tool_type: "workflow" | "agent" | "api" | string;
  workflow_id?: string | null;
  endpoint: string;
  request_params?: Record<string, unknown> | null;
  input_payload?: unknown;
  response_code?: number | null;
  response_data?: Record<string, unknown> | null;
  output_payload?: unknown;
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
  { label: "全部调用", value: "" },
  { label: "线路检索", value: "route_search" },
  { label: "签证检索", value: "visa_search" },
  { label: "外围信息", value: "external_info" },
  { label: "OAuth取Token", value: "oauth_token" },
];

const STATUS_OPTIONS = [
  { label: "全部状态", value: "" },
  { label: "成功", value: "success" },
  { label: "失败", value: "error" },
  { label: "中断", value: "interrupted" },
];

const STATUS_COLOR: Record<string, string> = {
  success: "green",
  error: "red",
  interrupted: "orange",
};

const TOOL_TYPE_LABEL: Record<string, string> = {
  workflow: "工作流",
  agent: "智能体",
  api: "OpenAPI",
};

const safePretty = (value: unknown): string => {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
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

  const [detailOpen, setDetailOpen] = useState(false);
  const [activeLog, setActiveLog] = useState<CozeLog | null>(null);

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
      {
        title: "工具类型",
        dataIndex: "tool_type",
        key: "tool_type",
        width: 100,
        render: (value: string) => TOOL_TYPE_LABEL[value] ?? value,
      },
      {
        title: "调用类型",
        dataIndex: "call_type",
        key: "call_type",
        width: 130,
      },
      {
        title: "状态",
        dataIndex: "status",
        key: "status",
        width: 90,
        render: (value: string) => <Tag color={STATUS_COLOR[value] || "default"}>{value}</Tag>,
      },
      {
        title: "耗时(ms)",
        dataIndex: "latency_ms",
        key: "latency_ms",
        width: 100,
      },
      {
        title: "Token",
        dataIndex: "token_count",
        key: "token_count",
        width: 80,
        render: (value: number | null | undefined) => value ?? "-",
      },
      {
        title: "trace_id",
        dataIndex: "trace_id",
        key: "trace_id",
        width: 220,
        ellipsis: true,
      },
      {
        title: "输入",
        dataIndex: "input_payload",
        key: "input_payload",
        render: (value: unknown) => {
          const text = safePretty(value);
          return <Text>{text.length > 60 ? `${text.slice(0, 60)}...` : text}</Text>;
        },
      },
      {
        title: "输出",
        dataIndex: "output_payload",
        key: "output_payload",
        render: (value: unknown) => {
          const text = safePretty(value);
          return <Text>{text.length > 60 ? `${text.slice(0, 60)}...` : text}</Text>;
        },
      },
      {
        title: "调试",
        dataIndex: "debug_url",
        key: "debug_url",
        width: 80,
        render: (value: string | null | undefined) =>
          value ? (
            <Link href={value} target="_blank" rel="noreferrer">
              查看
            </Link>
          ) : (
            "-"
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
          pagination={{
            current: page,
            pageSize: size,
            total,
            showSizeChanger: true,
            onChange: (nextPage, nextSize) => void loadLogs(nextPage, nextSize),
          }}
          scroll={{ x: 1600 }}
        />
      </Card>

      <Modal
        title={activeLog ? `Coze 日志详情 · ${activeLog.trace_id}` : "Coze 日志详情"}
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
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="id">{activeLog.id}</Descriptions.Item>
            <Descriptions.Item label="时间">{dayjs(activeLog.created_at).format("YYYY-MM-DD HH:mm:ss")}</Descriptions.Item>
            <Descriptions.Item label="trace_id">{activeLog.trace_id}</Descriptions.Item>
            <Descriptions.Item label="session_id">{activeLog.session_id}</Descriptions.Item>
            <Descriptions.Item label="工具类型">{TOOL_TYPE_LABEL[activeLog.tool_type] ?? activeLog.tool_type}</Descriptions.Item>
            <Descriptions.Item label="调用类型">{activeLog.call_type}</Descriptions.Item>
            <Descriptions.Item label="workflow_id">{activeLog.workflow_id ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="endpoint">{activeLog.endpoint}</Descriptions.Item>
            <Descriptions.Item label="status">{activeLog.status}</Descriptions.Item>
            <Descriptions.Item label="response_code">{activeLog.response_code ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="latency_ms">{activeLog.latency_ms}</Descriptions.Item>
            <Descriptions.Item label="token_count">{activeLog.token_count ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="coze_logid">{activeLog.coze_logid ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="debug_url">
              {activeLog.debug_url ? (
                <Link href={activeLog.debug_url} target="_blank" rel="noreferrer">查看</Link>
              ) : "-"}
            </Descriptions.Item>

            <Descriptions.Item label="输入(input_payload)" span={2}>
              <Text style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{safePretty(activeLog.input_payload)}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="输出(output_payload)" span={2}>
              <Text style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{safePretty(activeLog.output_payload)}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="原始请求(request_params)" span={2}>
              <Text style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{safePretty(activeLog.request_params)}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="原始响应(response_data)" span={2}>
              <Text style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{safePretty(activeLog.response_data)}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="错误信息(error_message)" span={2}>
              <Text type={activeLog.error_message ? "danger" : undefined} style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
                {safePretty(activeLog.error_message)}
              </Text>
            </Descriptions.Item>
          </Descriptions>
        ) : null}
      </Modal>
    </div>
  );
}
