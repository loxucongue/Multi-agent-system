"use client";

import zhCN from "antd/locale/zh_CN";
import { App as AntdApp, ConfigProvider } from "antd";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: "#1677ff" } }}>
      <AntdApp>{children}</AntdApp>
    </ConfigProvider>
  );
}
