"use client";

import "react-resizable/css/styles.css";
import "./resizable.css";

import {
  ApiOutlined,
  AppstoreOutlined,
  CompassOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  LogoutOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, Spin, Typography } from "antd";
import type { MenuProps } from "antd";
import { useEffect, useMemo, useSyncExternalStore } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useShallow } from "zustand/react/shallow";

import { useAdminStore } from "@/stores/adminStore";

const { Header, Sider, Content } = Layout;
const { Paragraph, Text, Title } = Typography;

const MENU_ITEMS: MenuProps["items"] = [
  { key: "/admin/routes", icon: <CompassOutlined />, label: "线路管理" },
  { key: "/admin/prompts", icon: <AppstoreOutlined />, label: "Prompt 管理" },
  { key: "/admin/kb", icon: <DatabaseOutlined />, label: "知识库管理" },
  { key: "/admin/logs", icon: <FileSearchOutlined />, label: "日志查看" },
  { key: "/admin/coze-logs", icon: <ApiOutlined />, label: "Coze 调用日志" },
  { key: "/admin/config", icon: <SettingOutlined />, label: "系统配置" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const hydrated = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  const { token, logout } = useAdminStore(
    useShallow((state) => ({
      token: state.token,
      logout: state.logout,
    })),
  );

  const isLoginPage = pathname === "/admin/login";

  useEffect(() => {
    if (!hydrated) {
      return;
    }

    if (isLoginPage && token) {
      router.replace("/admin/prompts");
      return;
    }

    if (!isLoginPage && !token) {
      router.replace("/admin/login");
    }
  }, [hydrated, isLoginPage, router, token]);

  const selectedKeys = useMemo(() => {
    if (pathname.startsWith("/admin/routes")) {
      return ["/admin/routes"];
    }
    if (pathname.startsWith("/admin/prompts")) {
      return ["/admin/prompts"];
    }
    if (pathname.startsWith("/admin/kb")) {
      return ["/admin/kb"];
    }
    if (pathname.startsWith("/admin/logs")) {
      return ["/admin/logs"];
    }
    if (pathname.startsWith("/admin/coze-logs")) {
      return ["/admin/coze-logs"];
    }
    if (pathname.startsWith("/admin/config")) {
      return ["/admin/config"];
    }
    return [];
  }, [pathname]);

  if (!hydrated) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spin />
      </div>
    );
  }

  if (isLoginPage) {
    return <>{children}</>;
  }

  if (!token) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spin />
      </div>
    );
  }

  return (
    <Layout style={{ minHeight: "100vh", background: "transparent" }}>
      <Sider
        width={264}
        style={{
          background: "linear-gradient(180deg, #082f49 0%, #0f766e 100%)",
          padding: 14,
        }}
      >
        <div
          style={{
            padding: 18,
            borderRadius: 24,
            background: "rgba(255,255,255,0.08)",
            border: "1px solid rgba(255,255,255,0.1)",
            marginBottom: 14,
          }}
        >
          <Text style={{ color: "rgba(255,255,255,0.72)" }}>管理后台</Text>
          <Title level={4} style={{ color: "#fff", margin: "8px 0 6px" }}>
            旅游路线智能顾问
          </Title>
          <Paragraph style={{ color: "rgba(255,255,255,0.7)", marginBottom: 0 }}>
            管理用户侧所有路线展示、提示词、日志与配置能力。
          </Paragraph>
        </div>

        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={selectedKeys}
          items={MENU_ITEMS}
          onClick={(info) => {
            router.push(info.key);
          }}
          style={{
            background: "transparent",
            borderInlineEnd: 0,
          }}
        />
      </Sider>

      <Layout>
        <Header
          style={{
            height: "auto",
            padding: "18px 20px",
            background: "rgba(255,255,255,0.76)",
            borderBottom: "1px solid rgba(125, 181, 211, 0.2)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div>
            <Text type="secondary">Admin Workspace</Text>
            <Title level={4} style={{ margin: "4px 0 0" }}>
              运营与线路内容中心
            </Title>
          </div>
          <Button
            icon={<LogoutOutlined />}
            onClick={() => {
              logout();
              router.replace("/admin/login");
            }}
            style={{ borderRadius: 999 }}
          >
            退出登录
          </Button>
        </Header>

        <Content style={{ padding: 16, background: "transparent" }}>{children}</Content>
      </Layout>
    </Layout>
  );
}
