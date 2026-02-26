import {
  Box,
  Code,
  Heading,
  Link,
  ListItem,
  OrderedList,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  UnorderedList,
} from "@chakra-ui/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

interface Props {
  content: string;
}

const components: Components = {
  h1: ({ children }) => (
    <Heading as="h1" size="lg" mt={5} mb={3} pb={2} borderBottom="1px solid" borderColor="whiteAlpha.100">
      {children}
    </Heading>
  ),
  h2: ({ children }) => (
    <Heading as="h2" size="md" mt={4} mb={2} color="gray.100">
      {children}
    </Heading>
  ),
  h3: ({ children }) => (
    <Heading as="h3" size="sm" mt={3} mb={1} color="brand.300">
      {children}
    </Heading>
  ),
  p: ({ children }) => (
    <Text my={1.5} lineHeight={1.7}>
      {children}
    </Text>
  ),
  strong: ({ children }) => (
    <Text as="strong" fontWeight={600} color="gray.50">
      {children}
    </Text>
  ),
  em: ({ children }) => (
    <Text as="em" color="gray.400">
      {children}
    </Text>
  ),
  a: ({ href, children }) => (
    <Link href={href} color="brand.300" isExternal>
      {children}
    </Link>
  ),
  ul: ({ children }) => (
    <UnorderedList pl={4} my={1.5} spacing={1}>
      {children}
    </UnorderedList>
  ),
  ol: ({ children }) => (
    <OrderedList pl={4} my={1.5} spacing={1}>
      {children}
    </OrderedList>
  ),
  li: ({ children }) => (
    <ListItem color="gray.200" fontSize="14px">
      {children}
    </ListItem>
  ),
  code: ({ className, children }) => {
    const isBlock = className?.includes("language-");
    if (isBlock) {
      return (
        <Box
          as="pre"
          my={3}
          p={4}
          borderRadius="lg"
          bg="blackAlpha.500"
          border="1px solid"
          borderColor="whiteAlpha.100"
          overflowX="auto"
        >
          <Code
            display="block"
            whiteSpace="pre-wrap"
            bg="transparent"
            color="gray.300"
            fontSize="12px"
            fontFamily="mono"
            lineHeight={1.6}
          >
            {children}
          </Code>
        </Box>
      );
    }
    return (
      <Code
        bg="blackAlpha.400"
        color="brand.300"
        px={1.5}
        py={0.5}
        borderRadius="md"
        fontSize="12.5px"
        border="1px solid"
        borderColor="whiteAlpha.100"
      >
        {children}
      </Code>
    );
  },
  table: ({ children }) => (
    <Box overflowX="auto" my={3}>
      <Table size="sm" variant="simple">
        {children}
      </Table>
    </Box>
  ),
  thead: ({ children }) => <Thead>{children}</Thead>,
  tbody: ({ children }) => <Tbody>{children}</Tbody>,
  tr: ({ children }) => (
    <Tr _hover={{ bg: "whiteAlpha.50" }}>{children}</Tr>
  ),
  th: ({ children }) => (
    <Th
      color="gray.500"
      fontSize="11px"
      textTransform="uppercase"
      letterSpacing="0.5px"
      borderColor="whiteAlpha.200"
      bg="whiteAlpha.50"
    >
      {children}
    </Th>
  ),
  td: ({ children }) => (
    <Td color="gray.300" borderColor="whiteAlpha.100" fontSize="13px">
      {children}
    </Td>
  ),
  blockquote: ({ children }) => (
    <Box
      my={3}
      pl={4}
      py={2}
      borderLeft="3px solid"
      borderColor="brand.500"
      bg="whiteAlpha.50"
      borderRadius="0 8px 8px 0"
      color="gray.300"
    >
      {children}
    </Box>
  ),
  hr: () => <Box as="hr" border="none" borderTop="1px solid" borderColor="whiteAlpha.100" my={4} />,
};

export default function MarkdownRenderer({ content }: Props) {
  return (
    <Box fontSize="14px" lineHeight={1.65} color="gray.100">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </Box>
  );
}
