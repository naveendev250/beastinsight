import { useEffect, useRef } from "react";
import { Box, Flex } from "@chakra-ui/react";
import { useChat } from "./hooks/useChat";
import Sidebar from "./components/Sidebar";
import WelcomeScreen from "./components/WelcomeScreen";
import MessageBubble from "./components/MessageBubble";
import PhaseIndicator from "./components/PhaseIndicator";
import ChatInput from "./components/ChatInput";

export default function App() {
  const {
    messages,
    isLoading,
    phase,
    sendMessage,
    clearChat,
    stopStreaming,
  } = useChat();

  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const hasMessages = messages.length > 0;

  return (
    <Flex h="100vh" w="100vw" overflow="hidden">
      {/* Sidebar */}
      <Sidebar
        onQuickAction={sendMessage}
        onNewChat={clearChat}
        disabled={isLoading}
      />

      {/* Main chat area */}
      <Flex direction="column" flex={1} minW={0} h="100vh" bg="surface.bg">
        {/* Messages */}
        <Box flex={1} overflowY="auto" overflowX="hidden">
          {!hasMessages ? (
            <WelcomeScreen onQuickAction={sendMessage} />
          ) : (
            <Box maxW="820px" mx="auto" px={6} pt={6} pb={4}>
              {messages.map((m) => (
                <MessageBubble key={m.id} message={m} />
              ))}
              <PhaseIndicator phase={phase} isLoading={isLoading} />
              <Box ref={bottomRef} />
            </Box>
          )}
        </Box>

        {/* Input */}
        <ChatInput onSend={sendMessage} onStop={stopStreaming} isLoading={isLoading} />
      </Flex>
    </Flex>
  );
}
