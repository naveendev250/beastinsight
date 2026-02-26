import { Flex, Icon, Text } from "@chakra-ui/react";
import { keyframes } from "@emotion/react";
import {
  FiSearch,
  FiCpu,
  FiDatabase,
  FiMessageCircle,
  FiDownload,
  FiEdit3,
  FiLoader,
} from "react-icons/fi";
import type { PhaseInfo } from "../types";
import type { IconType } from "react-icons";

const pulse = keyframes`
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40%            { opacity: 1;   transform: scale(1);   }
`;

const fadeIn = keyframes`
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0);   }
`;

const PHASE_ICONS: Record<string, IconType> = {
  routing: FiSearch,
  generating_sql: FiCpu,
  executing: FiDatabase,
  explaining: FiMessageCircle,
  fetching_data: FiDownload,
  formatting: FiEdit3,
};

interface Props {
  phase: PhaseInfo | null;
  isLoading: boolean;
}

export default function PhaseIndicator({ phase, isLoading }: Props) {
  if (!isLoading) return null;

  const PhaseIcon = phase ? PHASE_ICONS[phase.phase] || FiLoader : FiLoader;

  return (
    <Flex align="center" gap={3} py={2} animation={`${fadeIn} 0.3s ease`}>
      {/* Animated dots */}
      <Flex gap="4px">
        {[0, 1, 2].map((i) => (
          <Flex
            key={i}
            w="6px"
            h="6px"
            borderRadius="full"
            bg="brand.400"
            animation={`${pulse} 1.4s ease-in-out infinite`}
            style={{ animationDelay: `${i * 0.2}s` }}
          />
        ))}
      </Flex>

      <Icon as={PhaseIcon} boxSize="14px" color="gray.400" />

      <Text fontSize="13px" color="gray.400">
        {phase?.message || "Connecting..."}
      </Text>
    </Flex>
  );
}
