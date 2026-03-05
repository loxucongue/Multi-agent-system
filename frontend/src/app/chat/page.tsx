import ChatInput from "@/components/chat/ChatInput";
import MessageList from "@/components/chat/MessageList";
import ChatLayout from "@/components/chat/ChatLayout";

export default function ChatPage() {
  return (
    <ChatLayout>
      <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 32px)" }}>
        <MessageList />
        <ChatInput />
      </div>
    </ChatLayout>
  );
}
