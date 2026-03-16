"use client";

import {
  App,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  Tabs,
  Typography,
  Upload,
} from "antd";
import type { UploadProps } from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  SyncOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useShallow } from "zustand/react/shallow";

import { useAdminStore } from "@/stores/adminStore";
import type {
  ParseStatusResponse,
  ReparseResponse,
  RouteBasicInfo,
  RouteCreateRequest,
  RouteCreateResponse,
  RouteDetail,
  RouteListItem,
  RouteListResponse,
  RouteUpdateRequest,
} from "@/types";

const { Text, Title } = Typography;
const { TextArea } = Input;

interface PreviewRow {
  row_num: number;
  name: string;
  supplier: string;
  summary: string;
  doc_url: string;
  price_min: string | null;
  price_max: string | null;
  currency: string;
  features: string | null;
  is_hot: boolean;
  sort_weight: number;
  error: string | null;
}

interface PreviewResponse {
  rows: PreviewRow[];
  valid_count: number;
  error_count: number;
}

interface BatchCreateResponse {
  created: RouteCreateResponse[];
  failed: { name: string; doc_url: string; error: string }[];
}

interface RouteEditFormValues {
  name?: string;
  supplier?: string;
  summary?: string;
  doc_url?: string;
  features?: string | null;
  is_hot?: boolean;
  sort_weight?: number;
  highlights?: string;
  base_info?: string;
  notice?: string;
  included?: string;
  cost_excluded?: string;
  age_limit?: string;
  certificate_limit?: string;
}

const formatPrice = (route: RouteListItem) => {
  if (!route.pricing) {
    return "待补充";
  }
  return `¥${route.pricing.price_min} - ¥${route.pricing.price_max}`;
};

const stringifyStructuredField = (value: unknown, fallback: unknown): string =>
  JSON.stringify(value ?? fallback, null, 2);

const parseStringArrayField = (raw: string | undefined, label: string): string[] => {
  const text = raw?.trim() ?? "";
  if (!text) {
    return [];
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error(`${label} 必须是合法的 JSON 数组`);
  }

  if (!Array.isArray(parsed)) {
    throw new Error(`${label} 必须是 JSON 数组`);
  }

  return parsed.map((item) => String(item ?? "").trim()).filter(Boolean);
};

const parseObjectField = (raw: string | undefined, label: string): RouteBasicInfo => {
  const text = raw?.trim() ?? "";
  if (!text) {
    return {};
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error(`${label} 必须是合法的 JSON 对象`);
  }

  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${label} 必须是 JSON 对象`);
  }

  return parsed as RouteBasicInfo;
};

export default function AdminRoutesPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const { authedFetch, authedUpload, logout } = useAdminStore(
    useShallow((s) => ({ authedFetch: s.authedFetch, authedUpload: s.authedUpload, logout: s.logout })),
  );

  const [routes, setRoutes] = useState<RouteListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(false);

  const [editOpen, setEditOpen] = useState(false);
  const [editingRoute, setEditingRoute] = useState<RouteListItem | null>(null);
  const [editForm] = Form.useForm<RouteEditFormValues>();
  const [editSubmitting, setEditSubmitting] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm<RouteCreateRequest>();
  const [createSubmitting, setCreateSubmitting] = useState(false);

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewRows, setPreviewRows] = useState<PreviewRow[]>([]);
  const [previewValidCount, setPreviewValidCount] = useState(0);
  const [previewErrorCount, setPreviewErrorCount] = useState(0);
  const [batchLoading, setBatchLoading] = useState(false);

  const [parsingIds, setParsingIds] = useState<Set<number>>(new Set());

  const handleAuthError = useCallback(
    (error: unknown) => {
      const text = error instanceof Error ? error.message : "请求失败";
      if (text.includes("登录已过期")) {
        logout();
        router.replace("/admin/login");
        return;
      }
      message.error(text);
    },
    [logout, message, router],
  );

  const loadRoutes = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      if (keyword.trim()) {
        params.set("keyword", keyword.trim());
      }

      const data = await authedFetch<RouteListResponse>(`/admin/routes/?${params.toString()}`);
      setRoutes(data.routes);
      setTotal(data.total);
    } catch (error) {
      handleAuthError(error);
    } finally {
      setLoading(false);
    }
  }, [authedFetch, handleAuthError, keyword, page, pageSize]);

  useEffect(() => {
    void loadRoutes();
  }, [loadRoutes]);

  useEffect(() => {
    if (parsingIds.size === 0) {
      return;
    }

    const interval = setInterval(async () => {
      const stillParsing = new Set<number>();

      for (const routeId of parsingIds) {
        try {
          const status = await authedFetch<ParseStatusResponse>(`/admin/routes/${routeId}/parse-status`);
          if (status.status === "parsing" || status.status === "retrying") {
            stillParsing.add(routeId);
          } else if (status.status === "done") {
            message.success(`线路 ${routeId} 解析完成`);
          } else if (status.status === "failed") {
            message.error(`线路 ${routeId} 解析失败：${status.message ?? "请稍后重试"}`);
          }
        } catch {
          // Ignore transient polling errors.
        }
      }

      setParsingIds(stillParsing);
      if (stillParsing.size === 0) {
        void loadRoutes();
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [authedFetch, loadRoutes, message, parsingIds]);

  const handleReparse = useCallback(
    async (routeId: number) => {
      try {
        const resp = await authedFetch<ReparseResponse>("/admin/routes/reparse", {
          method: "POST",
          body: JSON.stringify({ route_ids: [routeId] }),
        });
        if (resp.accepted.includes(routeId)) {
          message.success("已提交重新解析任务");
          setParsingIds((prev) => new Set(prev).add(routeId));
        } else {
          const skipped = resp.skipped.find((item) => item.route_id === routeId);
          message.warning(`已跳过：${skipped?.reason ?? "未知原因"}`);
        }
      } catch (error) {
        handleAuthError(error);
      }
    },
    [authedFetch, handleAuthError, message],
  );

  const openEdit = useCallback(
    (route: RouteListItem) => {
      setEditingRoute(route);
      editForm.setFieldsValue({
        name: route.name,
        supplier: route.supplier,
        summary: route.summary,
        doc_url: route.doc_url,
        features: route.features ?? undefined,
        is_hot: route.is_hot,
        sort_weight: route.sort_weight,
        highlights: stringifyStructuredField(route.highlights, []),
        base_info: stringifyStructuredField(route.base_info, {}),
        notice: stringifyStructuredField(route.notice, []),
        included: stringifyStructuredField(route.included, []),
        cost_excluded: stringifyStructuredField(route.cost_excluded, []),
        age_limit: route.age_limit ?? undefined,
        certificate_limit: route.certificate_limit ?? undefined,
      });
      setEditOpen(true);
    },
    [editForm],
  );

  const handleEditSubmit = async () => {
    if (!editingRoute) {
      return;
    }

    try {
      const values = await editForm.validateFields();
      setEditSubmitting(true);

      const body: RouteUpdateRequest = {
        name: values.name,
        supplier: values.supplier,
        summary: values.summary,
        doc_url: values.doc_url,
        features: values.features,
        is_hot: values.is_hot,
        sort_weight: values.sort_weight,
        highlights: parseStringArrayField(values.highlights, "亮点"),
        base_info: parseObjectField(values.base_info, "基本信息"),
        notice: parseStringArrayField(values.notice, "注意事项"),
        included: parseStringArrayField(values.included, "费用包含"),
        cost_excluded: parseStringArrayField(values.cost_excluded, "费用不含"),
        age_limit: values.age_limit?.trim() || "",
        certificate_limit: values.certificate_limit?.trim() || "",
      };

      await authedFetch<RouteDetail>(`/admin/routes/${editingRoute.id}`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      message.success("线路已更新");
      setEditOpen(false);
      setEditingRoute(null);
      void loadRoutes();
    } catch (error) {
      handleAuthError(error);
    } finally {
      setEditSubmitting(false);
    }
  };

  const handleDelete = useCallback(
    async (routeId: number) => {
      try {
        await authedFetch(`/admin/routes/${routeId}`, { method: "DELETE" });
        message.success("线路已删除");
        void loadRoutes();
      } catch (error) {
        handleAuthError(error);
      }
    },
    [authedFetch, handleAuthError, loadRoutes, message],
  );

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      setCreateSubmitting(true);
      const resp = await authedFetch<RouteCreateResponse>("/admin/routes/", {
        method: "POST",
        body: JSON.stringify(values),
      });
      message.success(`线路“${resp.name}”创建成功`);
      if (resp.parse_status === "pending") {
        setParsingIds((prev) => new Set(prev).add(resp.route_id));
      }
      setCreateOpen(false);
      createForm.resetFields();
      void loadRoutes();
    } catch (error) {
      handleAuthError(error);
    } finally {
      setCreateSubmitting(false);
    }
  };

  const uploadProps: UploadProps = {
    accept: ".xlsx,.xls",
    showUploadList: false,
    beforeUpload: async (file) => {
      setBatchLoading(true);
      try {
        const formData = new FormData();
        formData.append("file", file);
        const data = await authedUpload<PreviewResponse>("/admin/routes/batch/preview", formData, {
          method: "POST",
        });
        setPreviewRows(data.rows);
        setPreviewValidCount(data.valid_count);
        setPreviewErrorCount(data.error_count);
        setPreviewOpen(true);
      } catch (error) {
        handleAuthError(error);
      } finally {
        setBatchLoading(false);
      }
      return false;
    },
  };

  const handleBatchCreate = async () => {
    const validRows = previewRows.filter((row) => row.error === null);
    if (validRows.length === 0) {
      message.warning("没有可导入的有效数据");
      return;
    }

    setBatchLoading(true);
    try {
      const resp = await authedFetch<BatchCreateResponse>("/admin/routes/batch", {
        method: "POST",
        body: JSON.stringify({ rows: validRows }),
      });
      message.success(`批量导入完成：成功 ${resp.created.length} 条，失败 ${resp.failed.length} 条`);
      setPreviewOpen(false);
      setPreviewRows([]);
      const pendingIds = resp.created.filter((item) => item.parse_status === "pending").map((item) => item.route_id);
      if (pendingIds.length > 0) {
        setParsingIds((prev) => {
          const next = new Set(prev);
          pendingIds.forEach((id) => next.add(id));
          return next;
        });
      }
      void loadRoutes();
    } catch (error) {
      handleAuthError(error);
    } finally {
      setBatchLoading(false);
    }
  };

  const hotRoutesCount = useMemo(() => routes.filter((route) => route.is_hot).length, [routes]);
  const parsingCount = parsingIds.size;
  const missingDocCount = useMemo(() => routes.filter((route) => !route.doc_url?.trim()).length, [routes]);

  const columns: ColumnsType<RouteListItem> = useMemo(
    () => [
      {
        title: "ID",
        dataIndex: "id",
        key: "id",
        width: 72,
        sorter: (a, b) => a.id - b.id,
      },
      {
        title: "线路名称",
        dataIndex: "name",
        key: "name",
        width: 300,
        ellipsis: true,
        render: (_, row) => (
          <Space direction="vertical" size={2}>
            <Text strong>{row.name}</Text>
            <Text type="secondary">{row.summary || "暂无摘要"}</Text>
          </Space>
        ),
      },
      {
        title: "供应商",
        dataIndex: "supplier",
        key: "supplier",
        width: 160,
        ellipsis: true,
      },
      {
        title: "价格区间",
        key: "price",
        width: 180,
        render: (_, row) => <Text>{formatPrice(row)}</Text>,
      },
      {
        title: "状态",
        key: "status",
        width: 180,
        render: (_, row) => (
          <Space wrap size={[8, 8]}>
            {row.is_hot ? <Tag color="volcano">热门</Tag> : <Tag>常规</Tag>}
            {parsingIds.has(row.id) ? <Tag color="processing">解析中</Tag> : <Tag color="success">已完成</Tag>}
          </Space>
        ),
      },
      {
        title: "最近更新",
        dataIndex: "updated_at",
        key: "updated_at",
        width: 180,
        sorter: (a, b) => new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime(),
        render: (value: string) => (value ? new Date(value).toLocaleString("zh-CN") : "-"),
      },
      {
        title: "操作",
        key: "actions",
        width: 280,
        render: (_, row) => (
          <Space wrap>
            <Button
              size="small"
              icon={<SyncOutlined />}
              loading={parsingIds.has(row.id)}
              onClick={() => void handleReparse(row.id)}
            >
              {parsingIds.has(row.id) ? "解析中" : "重新解析"}
            </Button>
            <Button size="small" type="primary" ghost icon={<EditOutlined />} onClick={() => openEdit(row)}>
              编辑
            </Button>
            <Popconfirm
              title="确定删除这条线路？"
              description="删除后不可恢复，请确认。"
              onConfirm={() => void handleDelete(row.id)}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [handleDelete, handleReparse, openEdit, parsingIds],
  );

  const previewColumns: ColumnsType<PreviewRow> = [
    { title: "行号", dataIndex: "row_num", width: 72 },
    { title: "名称", dataIndex: "name", ellipsis: true },
    { title: "供应商", dataIndex: "supplier", width: 140, ellipsis: true },
    { title: "文档链接", dataIndex: "doc_url", width: 260, ellipsis: true },
    {
      title: "校验结果",
      width: 160,
      render: (_, row) => (row.error ? <Tag color="error">{row.error}</Tag> : <Tag color="success">有效</Tag>),
    },
  ];

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <Card
        style={{
          borderRadius: 28,
          borderColor: "rgba(125, 181, 211, 0.24)",
          background:
            "radial-gradient(circle at top right, rgba(249, 115, 22, 0.12), transparent 24%), linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(240,249,255,0.9) 100%)",
        }}
        styles={{ body: { padding: 20 } }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", marginBottom: 18 }}>
          <div>
            <Text type="secondary">线路展示管理</Text>
            <Title level={3} style={{ margin: "4px 0 8px" }}>
              管理解析结果、价格摘要和展示优先级
            </Title>
            <Text type="secondary">
              当前已切换为结构化字段模式，亮点、基本信息、费用说明和注意事项均按 JSON 保存。
            </Text>
          </div>

          <Space wrap>
            <Input.Search
              placeholder="搜索线路名称或供应商"
              allowClear
              onSearch={(value) => {
                setKeyword(value);
                setPage(1);
              }}
              style={{ width: 260 }}
            />
            <Upload {...uploadProps}>
              <Button icon={<UploadOutlined />} loading={batchLoading}>
                批量导入
              </Button>
            </Upload>
            <Button icon={<ReloadOutlined />} onClick={() => void loadRoutes()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建线路
            </Button>
          </Space>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
          <Card bordered={false} style={{ borderRadius: 22, background: "rgba(255,255,255,0.74)" }}>
            <Statistic title="缺少文档链接" value={missingDocCount} />
          </Card>
          <Card bordered={false} style={{ borderRadius: 22, background: "rgba(255,255,255,0.74)" }}>
            <Statistic title="热门线路数" value={hotRoutesCount} />
          </Card>
          <Card bordered={false} style={{ borderRadius: 22, background: "rgba(255,255,255,0.74)" }}>
            <Statistic title="解析中的线路" value={parsingCount} />
          </Card>
          <Card bordered={false} style={{ borderRadius: 22, background: "rgba(255,255,255,0.74)" }}>
            <Statistic title="总线路数" value={total} />
          </Card>
        </div>
      </Card>

      <Card title="线路列表" styles={{ body: { paddingTop: 8 } }} style={{ borderRadius: 28, borderColor: "rgba(125, 181, 211, 0.24)" }}>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={routes}
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (value) => `共 ${value} 条`,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage);
              setPageSize(nextPageSize);
            },
          }}
          scroll={{ x: 1280 }}
        />
      </Card>

      <Modal
        title={editingRoute ? `编辑线路：${editingRoute.name}` : "编辑线路"}
        open={editOpen}
        width={820}
        onCancel={() => {
          if (!editSubmitting) {
            setEditOpen(false);
            setEditingRoute(null);
          }
        }}
        onOk={() => void handleEditSubmit()}
        confirmLoading={editSubmitting}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical" style={{ maxHeight: "min(70vh, 620px)", overflowY: "auto", paddingRight: 8 }}>
          <Tabs
            destroyInactiveTabPane={false}
            items={[
              {
                key: "basic",
                label: "基本信息",
                children: (
                  <>
                    <Form.Item label="线路名称" name="name" rules={[{ required: true, message: "请输入线路名称" }]}>
                      <Input maxLength={200} />
                    </Form.Item>
                    <Form.Item label="供应商" name="supplier" rules={[{ required: true, message: "请输入供应商" }]}>
                      <Input maxLength={100} />
                    </Form.Item>
                    <Form.Item label="摘要" name="summary">
                      <TextArea rows={2} />
                    </Form.Item>
                    <Form.Item label="文档链接" name="doc_url" rules={[{ required: true, message: "请输入文档链接" }]}>
                      <Input maxLength={500} />
                    </Form.Item>
                    <Form.Item label="线路特色" name="features">
                      <Input maxLength={500} />
                    </Form.Item>
                    <Space style={{ width: "100%" }} wrap>
                      <Form.Item label="热门线路" name="is_hot" valuePropName="checked">
                        <Switch />
                      </Form.Item>
                      <Form.Item label="排序权重" name="sort_weight">
                        <InputNumber min={0} max={9999} />
                      </Form.Item>
                    </Space>
                  </>
                ),
              },
              {
                key: "parsed",
                label: "解析字段",
                children: (
                  <>
                    <Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
                      下列字段已改为结构化 JSON。数组字段请填写 `[]`，对象字段请填写 `{}`。
                    </Text>
                    <Form.Item label="亮点（JSON 数组）" name="highlights">
                      <TextArea rows={6} spellCheck={false} placeholder={`["亮点1", "亮点2"]`} />
                    </Form.Item>
                    <Form.Item label="基本信息（JSON 对象）" name="base_info">
                      <TextArea
                        rows={8}
                        spellCheck={false}
                        placeholder={`{\n  "destination_country": "中国-山西",\n  "total_days": 5,\n  "total_nights": 4\n}`}
                      />
                    </Form.Item>
                    <Form.Item label="注意事项（JSON 数组）" name="notice">
                      <TextArea rows={6} spellCheck={false} placeholder={`["注意事项1", "注意事项2"]`} />
                    </Form.Item>
                    <Form.Item label="费用包含（JSON 数组）" name="included">
                      <TextArea rows={6} spellCheck={false} placeholder={`["机票", "酒店", "导游"]`} />
                    </Form.Item>
                    <Form.Item label="费用不含（JSON 数组）" name="cost_excluded">
                      <TextArea rows={6} spellCheck={false} placeholder={`["单房差", "个人消费"]`} />
                    </Form.Item>
                    <Form.Item label="年龄限制" name="age_limit">
                      <Input />
                    </Form.Item>
                    <Form.Item label="证件要求" name="certificate_limit">
                      <Input />
                    </Form.Item>
                  </>
                ),
              },
            ]}
          />
        </Form>
      </Modal>

      <Modal
        title="新建线路"
        open={createOpen}
        width={640}
        onCancel={() => {
          if (!createSubmitting) {
            setCreateOpen(false);
            createForm.resetFields();
          }
        }}
        onOk={() => void handleCreate()}
        confirmLoading={createSubmitting}
        destroyOnClose
      >
        <Form form={createForm} layout="vertical">
          <Form.Item label="线路名称" name="name" rules={[{ required: true, message: "请输入线路名称" }]}>
            <Input maxLength={200} />
          </Form.Item>
          <Form.Item label="供应商" name="supplier" rules={[{ required: true, message: "请输入供应商" }]}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item label="摘要" name="summary">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item label="文档链接（PDF/Word）" name="doc_url" rules={[{ required: true, message: "请输入文档链接" }]}>
            <Input maxLength={500} placeholder="https://oss.example.com/route.pdf" />
          </Form.Item>
          <Form.Item label="线路特色" name="features">
            <Input />
          </Form.Item>
          <Space wrap>
            <Form.Item label="最低价" name="price_min">
              <InputNumber min={0} precision={2} />
            </Form.Item>
            <Form.Item label="最高价" name="price_max">
              <InputNumber min={0} precision={2} />
            </Form.Item>
          </Space>
          <Space wrap>
            <Form.Item label="热门线路" name="is_hot" valuePropName="checked" initialValue={false}>
              <Switch />
            </Form.Item>
            <Form.Item label="排序权重" name="sort_weight" initialValue={0}>
              <InputNumber min={0} max={9999} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      <Modal
        title={`批量导入预览（有效 ${previewValidCount} 条，异常 ${previewErrorCount} 条）`}
        open={previewOpen}
        width={860}
        onCancel={() => setPreviewOpen(false)}
        onOk={() => void handleBatchCreate()}
        okText="确认导入"
        confirmLoading={batchLoading}
        okButtonProps={{ disabled: previewValidCount === 0 }}
      >
        <Table<PreviewRow>
          rowKey="row_num"
          columns={previewColumns}
          dataSource={previewRows}
          size="small"
          pagination={false}
          scroll={{ y: 420 }}
        />
      </Modal>
    </div>
  );
}
