import { useState } from "react";
import {
  Badge,
  Box,
  Button,
  Code,
  Collapse,
  Flex,
  Icon,
  Text,
} from "@chakra-ui/react";
import { keyframes } from "@emotion/react";
import { FiUser, FiLayers, FiCode, FiChevronDown, FiChevronUp } from "react-icons/fi";
import type { ChatMessage } from "../types";
import MarkdownRenderer from "./MarkdownRenderer";

const blink = keyframes`
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
`;

const fadeIn = keyframes`
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
`;

interface Props {
  message: ChatMessage;
}

export default function MessageBubble({ message }: Props) {
  const [showSql, setShowSql] = useState(false);
  const isUser = message.role === "user";

  return (
    <Flex
      gap={3}
      py={2}
      direction={isUser ? "row-reverse" : "row"}
      animation={`${fadeIn} 0.3s ease`}
    >
      {/* Avatar */}
      <Flex
        flexShrink={0}
        w="32px"
        h="32px"
        borderRadius="full"
        align="center"
        justify="center"
        mt="2px"
        bg={isUser ? "whiteAlpha.100" : "whiteAlpha.50"}
        border="1px solid"
        borderColor={isUser ? "brand.600" : "whiteAlpha.200"}
        color={isUser ? "brand.300" : "gray.400"}
      >
        <Icon as={isUser ? FiUser : FiLayers} boxSize="14px" />
      </Flex>

      {/* Bubble */}
      <Box
        maxW="720px"
        minW={0}
        borderRadius="xl"
        p={4}
        bg={isUser ? "whiteAlpha.100" : "whiteAlpha.50"}
        border="1px solid"
        borderColor={isUser ? "brand.800" : "whiteAlpha.100"}
        borderTopRightRadius={isUser ? "4px" : "xl"}
        borderTopLeftRadius={isUser ? "xl" : "4px"}
      >
        {/* Role */}
        <Flex align="center" gap={2} mb={1.5}>
          <Text
            fontSize="11px"
            fontWeight={600}
            color="gray.500"
            textTransform="uppercase"
            letterSpacing="0.5px"
          >
            {isUser ? "You" : "BeastInsights AI"}
          </Text>
          {!isUser && message.meta?.viewKey && (
            <Badge
              variant="subtle"
              colorScheme="purple"
              fontSize="10px"
              fontFamily="mono"
              borderRadius="sm"
              px={1.5}
            >
              {message.meta.viewKey}
            </Badge>
          )}
        </Flex>

        {/* Content */}
        <Box>
          {isUser ? (
            <Text lineHeight={1.65}>{message.content}</Text>
          ) : (
            <>
              <MarkdownRenderer content={message.content} />
              {message.isStreaming && (
                <Box
                  as="span"
                  display="inline-block"
                  w="7px"
                  h="18px"
                  bg="brand.400"
                  borderRadius="sm"
                  ml={0.5}
                  verticalAlign="text-bottom"
                  animation={`${blink} 1s step-end infinite`}
                />
              )}
            </>
          )}
        </Box>

        {/* SQL toggle */}
        {!isUser && message.meta?.sql && message.meta.sql !== "" && !message.isStreaming && (
          <Box mt={3} pt={2.5} borderTop="1px solid" borderColor="whiteAlpha.100">
            <Button
              size="xs"
              variant="ghost"
              color="gray.500"
              fontFamily="mono"
              fontSize="11px"
              leftIcon={<Icon as={FiCode} boxSize="12px" />}
              rightIcon={<Icon as={showSql ? FiChevronUp : FiChevronDown} boxSize="12px" />}
              onClick={() => setShowSql((s) => !s)}
              _hover={{ color: "brand.300", bg: "whiteAlpha.100" }}
            >
              {showSql ? "Hide SQL" : "View SQL"}
            </Button>
            <Collapse in={showSql} animateOpacity>
              <Box
                mt={2}
                p={3}
                borderRadius="lg"
                bg="blackAlpha.500"
                border="1px solid"
                borderColor="whiteAlpha.100"
                overflowX="auto"
              >
                <Code
                  display="block"
                  whiteSpace="pre-wrap"
                  wordBreak="break-all"
                  bg="transparent"
                  color="gray.400"
                  fontSize="12px"
                  fontFamily="mono"
                  lineHeight={1.6}
                >
                  {message.meta.sql}
                </Code>
              </Box>
            </Collapse>
          </Box>
        )}
      </Box>
    </Flex>
  );
}
