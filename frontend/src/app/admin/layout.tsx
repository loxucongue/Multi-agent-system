"use client";

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
import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useShallow } from "zustand/react/shallow";

import { useAdminStore } from "@/stores/adminStore";

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const MENU_ITEMS: MenuProps["items"] = [
  { key: "/admin/routes", icon: <CompassOutlined />, label: "线路管理" },
  { key: "/admin/prompts", icon: <AppstoreOutlined />, label: "Prompt管理" },
  { key: "/admin/kb", icon: <DatabaseOutlined />, label: "知识库管理" },
  { key: "/admin/logs", icon: <FileSearchOutlined />, label: "日志查看" },
  { key: "/admin/coze-logs", icon: <ApiOutlined />, label: "Coze调用日志" },
  { key: "/admin/config", icon: <SettingOutlined />, label: "系统配置" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [hydrated, setHydrated] = useState(false);

  const { token, logout } = useAdminStore(
    useShallow((state) => ({
      token: state.token,
      logout: state.logout,
    })),
  );

  const isLoginPage = pathname === "/admin/login";

  useEffect(() => {
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) {
      return;
    }

    if (isLoginPage) {
      if (token) {
        router.replace("/admin/prompts");
      }
      return;
    }

    if (!token) {
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
    <Layout style={{ minHeight: "100vh" }}>
      <Sider width={240}>
        <div style={{ padding: 16, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>
          <Text style={{ color: "#fff", fontSize: 16, fontWeight: 600 }}>管理后台</Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={selectedKeys}
          items={MENU_ITEMS}
          onClick={(info) => {
            router.push(info.key);
          }}
        />
      </Sider>

      <Layout>
        <Header
          style={{
            background: "#fff",
            borderBottom: "1px solid #f0f0f0",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            paddingInline: 16,
          }}
        >
          <Text strong>旅游路线智能顾问 · 管理后台</Text>
          <Button
            icon={<LogoutOutlined />}
            onClick={() => {
              logout();
              router.replace("/admin/login");
            }}
          >
            退出
          </Button>
        </Header>

        <Content style={{ padding: 16, background: "#f5f7fa" }}>{children}</Content>
      </Layout>
    </Layout>
  );
}
