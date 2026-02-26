import {
  Box,
  Button,
  Divider,
  Flex,
  Icon,
  Text,
  VStack,
} from "@chakra-ui/react";
import {
  FiPlus,
  FiBarChart2,
  FiBell,
  FiDollarSign,
  FiClock,
  FiUsers,
  FiActivity,
  FiRefreshCw,
  FiTrendingUp,
  FiCheckCircle,
  FiAlertTriangle,
  FiAward,
  FiLayers,
} from "react-icons/fi";
import type { QuickAction } from "../types";

const QUICK_ACTIONS: QuickAction[] = [
  { label: "Order Summary", question: "Give me order summary insights", icon: FiBarChart2, category: "insight" },
  { label: "Alert Report", question: "Give me alert insights", icon: FiBell, category: "insight" },
  { label: "LTV Analysis", question: "Give me LTV insights", icon: FiDollarSign, category: "insight" },
  { label: "Hourly Revenue", question: "Give me hourly revenue insights", icon: FiClock, category: "insight" },
  { label: "Cohort Report", question: "Give me cohort insights", icon: FiUsers, category: "insight" },
  { label: "MID Health", question: "Give me MID health insights", icon: FiActivity, category: "insight" },
  { label: "Decline Recovery", question: "Give me decline recovery insights", icon: FiRefreshCw, category: "insight" },
  { label: "Revenue yesterday?", question: "What was the total revenue yesterday?", icon: FiTrendingUp, category: "qa" },
  { label: "Approval rate today?", question: "What is the approval rate for today?", icon: FiCheckCircle, category: "qa" },
  { label: "Chargeback rate", question: "What is the current chargeback rate?", icon: FiAlertTriangle, category: "qa" },
  { label: "Top campaign", question: "Which campaign had the highest approval rate last week?", icon: FiAward, category: "qa" },
  { label: "Revenue trend 30d", question: "Revenue trend for the last 30 days - is it going up or down?", icon: FiTrendingUp, category: "qa" },
];

interface Props {
  onQuickAction: (question: string) => void;
  onNewChat: () => void;
  disabled: boolean;
}

export default function Sidebar({ onQuickAction, onNewChat, disabled }: Props) {
  const insights = QUICK_ACTIONS.filter((a) => a.category === "insight");
  const questions = QUICK_ACTIONS.filter((a) => a.category === "qa");

  return (
    <Flex
      direction="column"
      w="260px"
      minW="260px"
      h="100vh"
      bg="surface.card"
      borderRight="1px solid"
      borderColor="whiteAlpha.100"
      overflowY="auto"
      overflowX="hidden"
      display={{ base: "none", lg: "flex" }}
    >
      {/* Logo */}
      <Flex align="center" gap={2} px={4} pt={5} pb={3}>
        <Icon as={FiLayers} boxSize={5} color="brand.400" />
        <Text fontWeight={700} fontSize="15px" letterSpacing="0.3px">
          BeastInsights AI
        </Text>
      </Flex>

      <Divider borderColor="whiteAlpha.100" />

      {/* New Chat */}
      <Box px={3} pt={3} pb={1}>
        <Button
          w="full"
          variant="outline"
          size="sm"
          borderStyle="dashed"
          borderColor="whiteAlpha.200"
          color="gray.400"
          fontWeight={500}
          leftIcon={<FiPlus />}
          onClick={onNewChat}
          isDisabled={disabled}
          _hover={{ borderColor: "brand.400", color: "brand.300", bg: "whiteAlpha.50" }}
        >
          New Chat
        </Button>
      </Box>

      {/* Insight Reports */}
      <Box px={2} pt={4}>
        <Text
          px={2}
          pb={1}
          fontSize="11px"
          fontWeight={600}
          textTransform="uppercase"
          letterSpacing="0.8px"
          color="gray.500"
        >
          Insight Reports
        </Text>
        <VStack spacing={0} align="stretch">
          {insights.map((a) => (
            <Button
              key={a.label}
              variant="ghost"
              size="sm"
              justifyContent="flex-start"
              fontWeight={400}
              color="gray.400"
              leftIcon={<Icon as={a.icon} boxSize="14px" />}
              onClick={() => onQuickAction(a.question)}
              isDisabled={disabled}
              borderRadius="md"
              px={2}
              _hover={{ bg: "surface.hover", color: "gray.100" }}
            >
              <Text fontSize="13px" noOfLines={1}>
                {a.label}
              </Text>
            </Button>
          ))}
        </VStack>
      </Box>

      {/* Quick Questions
      <Box px={2} pt={4} pb={4}>
        <Text
          px={2}
          pb={1}
          fontSize="11px"
          fontWeight={600}
          textTransform="uppercase"
          letterSpacing="0.8px"
          color="gray.500"
        >
          Quick Questions
        </Text>
        <VStack spacing={0} align="stretch">
          {questions.map((a) => (
            <Button
              key={a.label}
              variant="ghost"
              size="sm"
              justifyContent="flex-start"
              fontWeight={400}
              color="gray.400"
              leftIcon={<Icon as={a.icon} boxSize="14px" />}
              onClick={() => onQuickAction(a.question)}
              isDisabled={disabled}
              borderRadius="md"
              px={2}
              _hover={{ bg: "surface.hover", color: "gray.100" }}
            >
              <Text fontSize="13px" noOfLines={1}>
                {a.label}
              </Text>
            </Button>
          ))}
        </VStack>
      </Box> */}
    </Flex>
  );
}
