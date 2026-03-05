"use client";

import ChatInput from "@/components/chat/ChatInput";
import MessageList from "@/components/chat/MessageList";
import ChatLayout from "@/components/chat/ChatLayout";
import LeadModal from "@/components/lead/LeadModal";
import { useChatStore } from "@/stores/sessionStore";

export default function ChatPage() {
  const { showLeadModal, setLeadModalVisible } = useChatStore((state) => ({
    showLeadModal: state.showLeadModal,
    setLeadModalVisible: state.setLeadModalVisible,
  }));

  return (
    <ChatLayout>
      <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 32px)" }}>
        <MessageList />
        <ChatInput />
        <LeadModal
          open={showLeadModal}
          onClose={() => {
            setLeadModalVisible(false);
          }}
        />
      </div>
    </ChatLayout>
  );
}
