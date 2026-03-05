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
    setErrorText(PHONE_REGEX.test(next) ? null : "璇疯緭鍏ユ纭殑 11 浣嶆墜鏈哄彿");
  };

  const closeModal = () => {
    setLeadModalVisible(false);
    onClose();
  };

  const handleSubmit = async () => {
    if (leadStatus === "captured") {
      message.info("鎮ㄥ凡鎻愪氦杩囪仈绯绘柟寮?);
      closeModal();
      return;
    }

    if (!sessionId) {
      setErrorText("浼氳瘽涓嶅瓨鍦紝璇峰埛鏂板悗閲嶈瘯");
      return;
    }
    if (!isValidPhone) {
      setErrorText("璇疯緭鍏ユ纭殑 11 浣嶆墜鏈哄彿");
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
        message.success("鎻愪氦鎴愬姛");
        useChatStore.setState({
          leadStatus: "captured",
          showLeadModal: false,
        });
        onClose();
        return;
      }

      if (response.status === 409) {
        message.info("鎮ㄥ凡鎻愪氦杩囪仈绯绘柟寮?);
        useChatStore.setState({
          leadStatus: "captured",
          showLeadModal: false,
        });
        onClose();
        return;
      }

      if (response.status === 422) {
        setErrorText("鎵嬫満鍙锋牸寮忎笉姝ｇ‘");
        return;
      }

      setErrorText("鎻愪氦澶辫触锛岃绋嶅悗閲嶈瘯");
    } catch {
      setErrorText("缃戠粶寮傚父锛岃绋嶅悗閲嶈瘯");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="鐣欎笅鑱旂郴鏂瑰紡锛岄【闂负鎮ㄥ畾鍒惰绋?
      open={open && leadStatus !== "captured"}
      onCancel={closeModal}
      footer={null}
      centered
      width={400}
      destroyOnHidden
      mask={{ closable: !submitting }}
      closable={!submitting}
    >
      <Form layout="vertical" onFinish={() => void handleSubmit()}>
        <Form.Item
          label="鎵嬫満鍙?
          validateStatus={errorText ? "error" : undefined}
          help={errorText ?? " "}
          required
        >
          <Input
            value={phone}
            maxLength={11}
            placeholder="璇疯緭鍏ユ墜鏈哄彿"
            onChange={(event) => handlePhoneChange(event.target.value)}
            disabled={submitting}
          />
        </Form.Item>

        <Button type="primary" htmlType="submit" loading={submitting} disabled={!canSubmit} block>
          鎻愪氦
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
          鏆傛椂涓嶉渶瑕?        </Link>
        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            鎴戜滑浠呯敤浜庤绋嬫矡閫氾紝涓嶄細鐢ㄤ簬鍏朵粬鐢ㄩ€?          </Text>
        </div>
      </div>
    </Modal>
  );
}

