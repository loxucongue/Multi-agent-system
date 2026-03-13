"use client";

import {
  App,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  Upload,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { UploadProps } from "antd";
import { UploadOutlined } from "@ant-design/icons";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useShallow } from "zustand/react/shallow";

import { useAdminStore } from "@/stores/adminStore";
import type {
  ParseStatusResponse,
  ReparseResponse,
  RouteCreateRequest,
  RouteCreateResponse,
  RouteDetail,
  RouteListItem,
  RouteListResponse,
  RouteUpdateRequest,
} from "@/types";

const { Text } = Typography;
const { TextArea } = Input;

/* ---------- batch preview types ---------- */

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

/* ------------------------------------------------------------------ */
/*  主页面                                                             */
/* ------------------------------------------------------------------ */

export default function AdminRoutesPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const { authedFetch, logout } = useAdminStore(
    useShallow((s) => ({ authedFetch: s.authedFetch, logout: s.logout })),
  );

  /* ---------- 列表状态 ---------- */
  const [routes, setRoutes] = useState<RouteListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(false);

  /* ---------- 编辑弹窗状态 ---------- */
  const [editOpen, setEditOpen] = useState(false);
  const [editingRoute, setEditingRoute] = useState<RouteListItem | null>(null);
  const [editForm] = Form.useForm<RouteUpdateRequest>();
  const [editSubmitting, setEditSubmitting] = useState(false);

  /* ---------- 创建弹窗状态 ---------- */
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm<RouteCreateRequest>();
  const [createSubmitting, setCreateSubmitting] = useState(false);

  /* ---------- 批量导入预览状态 ---------- */
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewRows, setPreviewRows] = useState<PreviewRow[]>([]);
  const [previewValidCount, setPreviewValidCount] = useState(0);
  const [batchLoading, setBatchLoading] = useState(false);

  /* ---------- 解析状态轮询 ---------- */
  const [parsingIds, setParsingIds] = useState<Set<number>>(new Set());
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  /* ================================================================ */
  /*  数据加载                                                         */
  /* ================================================================ */

  const loadRoutes = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      if (keyword.trim()) params.set("keyword", keyword.trim());

      const data = await authedFetch<RouteListResponse>(
        `/admin/routes/?${params.toString()}`,
      );
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

  /* ================================================================ */
  /*  解析状态轮询                                                     */
  /* ================================================================ */

  useEffect(() => {
    if (parsingIds.size === 0) return;

    const interval = setInterval(async () => {
      const stillParsing = new Set<number>();
      for (const rid of parsingIds) {
        try {
          const st = await authedFetch<ParseStatusResponse>(
            `/admin/routes/${rid}/parse-status`,
          );
          if (st.status === "parsing") {
            stillParsing.add(rid);
          } else if (st.status === "done") {
            message.success(`线路 ${rid} 解析完成`);
          } else if (st.status === "failed") {
            message.error(`线路 ${rid} 解析失败: ${st.message ?? ""}`);
          }
        } catch {
          /* 忽略轮询错误 */
        }
      }
      setParsingIds(stillParsing);
      if (stillParsing.size === 0) {
        void loadRoutes();
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [parsingIds, authedFetch, message, loadRoutes]);

  /* cleanup polling on unmount */
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

  /* ================================================================ */
  /*  操作 - 重新解析                                                  */
  /* ================================================================ */

  const handleReparse = async (routeId: number) => {
    try {
      const resp = await authedFetch<ReparseResponse>("/admin/routes/reparse", {
        method: "POST",
        body: JSON.stringify({ route_ids: [routeId] }),
      });
      if (resp.accepted.includes(routeId)) {
        message.success("已提交重新解析");
        setParsingIds((prev) => new Set(prev).add(routeId));
      } else {
        const skip = resp.skipped.find((s) => s.route_id === routeId);
        message.warning(`跳过: ${skip?.reason ?? "未知原因"}`);
      }
    } catch (error) {
      handleAuthError(error);
    }
  };

  /* ================================================================ */
  /*  操作 - 编辑                                                      */
  /* ================================================================ */

  const openEdit = (route: RouteListItem) => {
    setEditingRoute(route);
    editForm.setFieldsValue({
      name: route.name,
      supplier: route.supplier,
      summary: route.summary,
      doc_url: route.doc_url,
      features: route.features ?? undefined,
      is_hot: route.is_hot,
      sort_weight: route.sort_weight,
      highlights: route.highlights,
      base_info: route.base_info,
      notice: route.notice,
      included: route.included,
      cost_excluded: route.cost_excluded ?? undefined,
      age_limit: (route as RouteListItem & { age_limit?: string }).age_limit ?? undefined,
      certificate_limit:
        (route as RouteListItem & { certificate_limit?: string }).certificate_limit ?? undefined,
    });
    setEditOpen(true);
  };

  const handleEditSubmit = async () => {
    if (!editingRoute) return;
    try {
      const values = await editForm.validateFields();
      setEditSubmitting(true);

      const body: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(values)) {
        if (v !== undefined && v !== null && v !== "") {
          body[k] = v;
        }
      }

      await authedFetch<RouteDetail>(`/admin/routes/${editingRoute.id}`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      message.success("更新成功");
      setEditOpen(false);
      setEditingRoute(null);
      void loadRoutes();
    } catch (error) {
      handleAuthError(error);
    } finally {
      setEditSubmitting(false);
    }
  };

  /* ================================================================ */
  /*  操作 - 删除                                                      */
  /* ================================================================ */

  const handleDelete = async (routeId: number) => {
    try {
      await authedFetch(`/admin/routes/${routeId}`, { method: "DELETE" });
      message.success("删除成功");
      void loadRoutes();
    } catch (error) {
      handleAuthError(error);
    }
  };

  /* ================================================================ */
  /*  操作 - 创建                                                      */
  /* ================================================================ */

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      setCreateSubmitting(true);
      const resp = await authedFetch<RouteCreateResponse>("/admin/routes/", {
        method: "POST",
        body: JSON.stringify(values),
      });
      message.success(`线路「${resp.name}」创建成功`);
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

  /* ================================================================ */
  /*  操作 - 批量导入                                                  */
  /* ================================================================ */

  const uploadProps: UploadProps = {
    accept: ".xlsx,.xls",
    showUploadList: false,
    beforeUpload: async (file) => {
      setBatchLoading(true);
      try {
        const formData = new FormData();
        formData.append("file", file);
        const token = useAdminStore.getState().token;
        const resp = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/admin/routes/batch/preview`,
          {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
          },
        );
        if (!resp.ok) {
          const errData = (await resp.json().catch(() => ({}))) as { detail?: string };
          throw new Error(errData.detail ?? `上传失败: ${resp.status}`);
        }
        const data = (await resp.json()) as PreviewResponse;
        setPreviewRows(data.rows);
        setPreviewValidCount(data.valid_count);
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
    const validRows = previewRows.filter((r) => r.error === null);
    if (validRows.length === 0) {
      message.warning("没有可导入的有效行");
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
      const pendingIds = resp.created
        .filter((c) => c.parse_status === "pending")
        .map((c) => c.route_id);
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

  /* ================================================================ */
  /*  表格列定义                                                       */
  /* ================================================================ */

  const columns: ColumnsType<RouteListItem> = useMemo(
    () => [
      {
        title: "ID",
        dataIndex: "id",
        key: "id",
        width: 70,
        sorter: (a, b) => a.id - b.id,
      },
      {
        title: "线路名称",
        dataIndex: "name",
        key: "name",
        ellipsis: true,
        width: 240,
      },
      {
        title: "供应商",
        dataIndex: "supplier",
        key: "supplier",
        width: 120,
        ellipsis: true,
      },
      {
        title: "价格区间",
        key: "price",
        width: 160,
        render: (_, row) =>
          row.pricing
            ? `¥${row.pricing.price_min} - ¥${row.pricing.price_max}`
            : <Text type="secondary">未设置</Text>,
      },
      {
        title: "热门",
        dataIndex: "is_hot",
        key: "is_hot",
        width: 70,
        render: (v: boolean) => (v ? <Tag color="red">热门</Tag> : <Tag>普通</Tag>),
      },
      {
        title: "上次修改时间",
        dataIndex: "updated_at",
        key: "updated_at",
        width: 180,
        sorter: (a, b) =>
          new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime(),
        render: (v: string) => (v ? new Date(v).toLocaleString("zh-CN") : "-"),
      },
      {
        title: "操作",
        key: "actions",
        width: 240,
        render: (_, row) => (
          <Space>
            <Button
              size="small"
              onClick={() => void handleReparse(row.id)}
              loading={parsingIds.has(row.id)}
            >
              {parsingIds.has(row.id) ? "解析中" : "重新解析"}
            </Button>
            <Button size="small" type="primary" ghost onClick={() => openEdit(row)}>
              编辑
            </Button>
            <Popconfirm
              title="确定删除该线路？"
              description="删除后不可恢复"
              onConfirm={() => void handleDelete(row.id)}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button size="small" danger>
                删除
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [parsingIds],
  );

  const previewColumns: ColumnsType<PreviewRow> = [
    { title: "行号", dataIndex: "row_num", width: 60 },
    { title: "名称", dataIndex: "name", ellipsis: true },
    { title: "供应商", dataIndex: "supplier", width: 100 },
    { title: "文档链接", dataIndex: "doc_url", ellipsis: true, width: 200 },
    {
      title: "状态",
      width: 120,
      render: (_, row) =>
        row.error ? <Tag color="error">{row.error}</Tag> : <Tag color="success">有效</Tag>,
    },
  ];

  /* ================================================================ */
  /*  渲染                                                             */
  /* ================================================================ */

  return (
    <>
      <Card
        title="线路管理"
        extra={
          <Space>
            <Input.Search
              placeholder="搜索线路名称/供应商"
              allowClear
              onSearch={(v) => {
                setKeyword(v);
                setPage(1);
              }}
              style={{ width: 260 }}
            />
            <Upload {...uploadProps}>
              <Button icon={<UploadOutlined />} loading={batchLoading}>
                批量导入
              </Button>
            </Upload>
            <Button onClick={() => void loadRoutes()}>刷新</Button>
            <Button type="primary" onClick={() => setCreateOpen(true)}>
              新建线路
            </Button>
          </Space>
        }
      >
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
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
          scroll={{ x: 1100 }}
        />
      </Card>

      {/* ==================== 编辑弹窗 ==================== */}
      <Modal
        title={editingRoute ? `编辑线路 · ${editingRoute.name}` : "编辑线路"}
        open={editOpen}
        width={720}
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
        <Form form={editForm} layout="vertical" style={{ maxHeight: 520, overflowY: "auto" }}>
          <Form.Item label="线路名称" name="name" rules={[{ required: true, message: "请输入线路名称" }]}>
            <Input maxLength={200} />
          </Form.Item>
          <Form.Item label="供应商" name="supplier" rules={[{ required: true, message: "请输入供应商" }]}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item label="简介" name="summary">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item label="文档链接" name="doc_url" rules={[{ required: true, message: "请输入文档链接" }]}>
            <Input maxLength={500} />
          </Form.Item>
          <Form.Item label="线路特色" name="features">
            <Input maxLength={500} />
          </Form.Item>

          <Space style={{ width: "100%" }}>
            <Form.Item label="热门" name="is_hot" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item label="排序权重" name="sort_weight">
              <InputNumber min={0} max={9999} />
            </Form.Item>
          </Space>

          <Descriptions
            title="Coze 解析字段（可手动修正）"
            column={1}
            size="small"
            style={{ marginBottom: 16 }}
          />

          <Form.Item label="亮点" name="highlights">
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item label="基本信息" name="base_info">
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item label="注意事项" name="notice">
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item label="费用包含" name="included">
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item label="费用不含" name="cost_excluded">
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item label="年龄限制" name="age_limit">
            <Input />
          </Form.Item>
          <Form.Item label="证件要求" name="certificate_limit">
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      {/* ==================== 创建弹窗 ==================== */}
      <Modal
        title="新建线路"
        open={createOpen}
        width={600}
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
          <Form.Item label="线路名称" name="name" rules={[{ required: true }]}>
            <Input maxLength={200} />
          </Form.Item>
          <Form.Item label="供应商" name="supplier" rules={[{ required: true }]}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item label="简介" name="summary">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item label="文档链接 (PDF)" name="doc_url" rules={[{ required: true }]}>
            <Input maxLength={500} placeholder="https://oss.example.com/xxx.pdf" />
          </Form.Item>
          <Form.Item label="线路特色" name="features">
            <Input />
          </Form.Item>
          <Space>
            <Form.Item label="最低价" name="price_min">
              <InputNumber min={0} precision={2} />
            </Form.Item>
            <Form.Item label="最高价" name="price_max">
              <InputNumber min={0} precision={2} />
            </Form.Item>
          </Space>
          <Space>
            <Form.Item label="热门" name="is_hot" valuePropName="checked" initialValue={false}>
              <Switch />
            </Form.Item>
            <Form.Item label="排序权重" name="sort_weight" initialValue={0}>
              <InputNumber min={0} max={9999} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      {/* ==================== 批量导入预览弹窗 ==================== */}
      <Modal
        title={`批量导入预览（有效 ${previewValidCount} 条）`}
        open={previewOpen}
        width={800}
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
          scroll={{ y: 400 }}
        />
      </Modal>
    </>
  );
}
