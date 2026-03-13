"use client";

import zhCN from "antd/locale/zh_CN";
import { App as AntdApp, ConfigProvider } from "antd";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#0ea5e9",
          colorSuccess: "#14b8a6",
          colorWarning: "#f97316",
          colorInfo: "#38bdf8",
          borderRadius: 18,
          borderRadiusLG: 24,
          colorBgBase: "#f3fbff",
          colorBgContainer: "#ffffff",
          colorText: "#083344",
          colorTextSecondary: "#3f6274",
          colorBorderSecondary: "#d6e8f2",
          boxShadowSecondary: "0 20px 60px rgba(8, 47, 73, 0.12)",
          fontFamily: "var(--font-ui), 'PingFang SC', 'Microsoft YaHei', sans-serif",
          fontFamilyCode: "var(--font-mono), 'SFMono-Regular', Consolas, monospace",
        },
      }}
    >
      <AntdApp>{children}</AntdApp>
    </ConfigProvider>
  );
}
