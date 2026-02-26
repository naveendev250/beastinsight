import { useRef, useState } from "react";
import {
  Box,
  Flex,
  IconButton,
  Kbd,
  Text,
  Textarea,
} from "@chakra-ui/react";
import { FiArrowUp, FiSquare } from "react-icons/fi";

interface Props {
  onSend: (question: string) => void;
  onStop: () => void;
  isLoading: boolean;
}

export default function ChatInput({ onSend, onStop, isLoading }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSend = value.trim().length > 0 && !isLoading;

  function handleSend() {
    if (!canSend) return;
    onSend(value.trim());
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setValue(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  return (
    <Box maxW="868px" mx="auto" w="full" px={6} pt={3} pb={4}>
      <Flex
        align="flex-end"
        gap={2}
        px={4}
        py={2}
        borderRadius="2xl"
        border="1px solid"
        borderColor="whiteAlpha.200"
        bg="surface.elevated"
        transition="all 0.18s ease"
        _focusWithin={{
          borderColor: "brand.600",
          boxShadow: "0 0 0 3px rgba(91, 124, 250, 0.08)",
        }}
      >
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about your business data..."
          rows={1}
          isDisabled={isLoading}
          resize="none"
          border="none"
          bg="transparent"
          color="gray.100"
          fontSize="14px"
          lineHeight={1.5}
          maxH="200px"
          py={2}
          px={0}
          _placeholder={{ color: "gray.600" }}
          _focus={{ boxShadow: "none" }}
          _disabled={{ opacity: 0.5 }}
        />

        {isLoading ? (
          <IconButton
            aria-label="Stop generating"
            icon={<FiSquare />}
            size="sm"
            borderRadius="full"
            colorScheme="red"
            onClick={onStop}
          />
        ) : (
          <IconButton
            aria-label="Send message"
            icon={<FiArrowUp />}
            size="sm"
            borderRadius="full"
            bg={canSend ? "brand.500" : "whiteAlpha.100"}
            color={canSend ? "white" : "gray.600"}
            isDisabled={!canSend}
            onClick={handleSend}
            _hover={canSend ? { bg: "brand.400", transform: "scale(1.05)" } : {}}
            transition="all 0.15s ease"
          />
        )}
      </Flex>

      <Text textAlign="center" fontSize="11px" color="gray.600" mt={1.5}>
        Press <Kbd fontSize="10px" bg="whiteAlpha.50" borderColor="whiteAlpha.100">Enter</Kbd> to send,{" "}
        <Kbd fontSize="10px" bg="whiteAlpha.50" borderColor="whiteAlpha.100">Shift+Enter</Kbd> for new line
      </Text>
    </Box>
  );
}
