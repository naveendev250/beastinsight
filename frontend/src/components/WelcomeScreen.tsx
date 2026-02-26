import { Box, Flex, Grid, Icon, Text } from "@chakra-ui/react";
import {
  FiDollarSign,
  FiCheckCircle,
  FiBarChart2,
  FiTrendingUp,
  FiActivity,
  FiLayers,
} from "react-icons/fi";

interface Props {
  onQuickAction: (question: string) => void;
}

const SUGGESTIONS = [
  { question: "What was the total revenue yesterday?", icon: FiDollarSign },
  { question: "What is the approval rate for today?", icon: FiCheckCircle },
  { question: "Give me order summary insights", icon: FiBarChart2 },
  { question: "Revenue trend for the last 30 days - is it going up or down?", icon: FiTrendingUp },
  { question: "Which MIDs are currently in critical health?", icon: FiActivity },
  { question: "Give me LTV insights", icon: FiDollarSign },
];

export default function WelcomeScreen({ onQuickAction }: Props) {
  return (
    <Flex
      direction="column"
      align="center"
      justify="center"
      h="full"
      px={6}
      py={10}
      textAlign="center"
    >
      <Icon as={FiLayers} boxSize={12} color="brand.400" mb={4} opacity={0.8} />

      <Text fontSize="28px" fontWeight={700} letterSpacing="-0.5px" mb={2}>
        BeastInsights AI
      </Text>

      <Text
        maxW="480px"
        fontSize="15px"
        color="gray.400"
        lineHeight={1.6}
        mb={9}
      >
        Your AI-powered analytics copilot. Ask any question about your business
        data or generate structured insight reports.
      </Text>

      <Grid
        templateColumns={{ base: "1fr", md: "repeat(2, 1fr)" }}
        gap={3}
        maxW="560px"
        w="full"
      >
        {SUGGESTIONS.map((s) => (
          <Box
            key={s.question}
            as="button"
            display="flex"
            alignItems="flex-start"
            gap={3}
            p={4}
            borderRadius="xl"
            border="1px solid"
            borderColor="whiteAlpha.100"
            bg="whiteAlpha.50"
            color="gray.400"
            fontSize="13px"
            textAlign="left"
            lineHeight={1.45}
            cursor="pointer"
            transition="all 0.18s ease"
            _hover={{
              borderColor: "brand.500",
              bg: "whiteAlpha.100",
              color: "gray.100",
              transform: "translateY(-1px)",
            }}
            onClick={() => onQuickAction(s.question)}
          >
            <Icon as={s.icon} boxSize="18px" mt="2px" flexShrink={0} color="brand.400" />
            <Text flex={1}>{s.question}</Text>
          </Box>
        ))}
      </Grid>
    </Flex>
  );
}
