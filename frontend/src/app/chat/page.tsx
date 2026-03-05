import MessageList from "@/components/chat/MessageList";
import ChatLayout from "@/components/chat/ChatLayout";

export default function ChatPage() {
  return (
    <ChatLayout>
      <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
        <MessageList />
      </div>
    </ChatLayout>
  );
}
