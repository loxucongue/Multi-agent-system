"use client";

import { App, Button, Form, Input, Modal, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { API_BASE_URL } from "@/services/api";
import { useChatStore } from "@/stores/sessionStore";

const { Link, Text } = Typography;

const PHONE_REGEX = /^1[3-9]\d{9}$/;

interface LeadModalProps {
  open: boolean;
  onClose: () => void;
}

export default function LeadModal({ open, onClose }: LeadModalProps) {
  const { message } = App.useApp();
  const [phone, setPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);

  const { sessionId, leadStatus, setLeadModalVisible } = useChatStore(
    useShallow((state) => ({
      sessionId: state.sessionId,
      leadStatus: state.leadStatus,
      setLeadModalVisible: state.setLeadModalVisible,
    })),
  );

  useEffect(() => {
    if (!open) {
      setPhone("");
      setErrorText(null);
      setSubmitting(false);
    }
  }, [open]);

  const normalizedPhone = phone.trim();
  const isValidPhone = PHONE_REGEX.test(normalizedPhone);
  const canSubmit = useMemo(
    () => normalizedPhone.length > 0 && isValidPhone && !submitting,
    [isValidPhone, normalizedPhone.length, submitting],
  );

  const handlePhoneChange = (value: string) => {
    const next = value.replace(/\s+/g, "");
    setPhone(next);
    if (next.length === 0) {
      setErrorText(null);
      return;
    }
    setErrorText(PHONE_REGEX.test(next) ? null : "请输入正确的 11 位手机号");
  };

  const closeModal = () => {
    setLeadModalVisible(false);
    onClose();
  };

  const handleSubmit = async () => {
    if (leadStatus === "captured") {
      message.info("您已提交过联系方式");
      closeModal();
      return;
    }

    if (!sessionId) {
      setErrorText("会话不存在，请刷新后重试");
      return;
    }
    if (!isValidPhone) {
      setErrorText("请输入正确的 11 位手机号");
      return;
    }

    setSubmitting(true);
    setErrorText(null);

    try {
      const response = await fetch(`${API_BASE_URL}/session/${sessionId}/lead`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ phone: normalizedPhone }),
      });

      if (response.ok) {
        message.success("提交成功");
        useChatStore.setState({
          leadStatus: "captured",
          showLeadModal: false,
        });
        onClose();
        return;
      }

      if (response.status === 409) {
        message.info("您已提交过联系方式");
        useChatStore.setState({
          leadStatus: "captured",
          showLeadModal: false,
        });
        onClose();
        return;
      }

      if (response.status === 422) {
        setErrorText("手机号格式不正确");
        return;
      }

      setErrorText("提交失败，请稍后重试");
    } catch {
      setErrorText("网络异常，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="留下联系方式，顾问为您定制行程"
      open={open && leadStatus !== "captured"}
      onCancel={closeModal}
      footer={null}
      centered
      width={400}
      destroyOnClose
      maskClosable={!submitting}
      closable={!submitting}
    >
      <Form layout="vertical" onFinish={() => void handleSubmit()}>
        <Form.Item
          label="手机号"
          validateStatus={errorText ? "error" : undefined}
          help={errorText ?? " "}
          required
        >
          <Input
            value={phone}
            maxLength={11}
            placeholder="请输入手机号"
            onChange={(event) => handlePhoneChange(event.target.value)}
            disabled={submitting}
          />
        </Form.Item>

        <Button type="primary" htmlType="submit" loading={submitting} disabled={!canSubmit} block>
          提交
        </Button>
      </Form>

      <div style={{ marginTop: 12, textAlign: "center" }}>
        <Link
          onClick={() => {
            if (!submitting) {
              closeModal();
            }
          }}
        >
          暂时不需要
        </Link>
        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            我们仅用于行程沟通，不会用于其他用途
          </Text>
        </div>
      </div>
    </Modal>
  );
}
