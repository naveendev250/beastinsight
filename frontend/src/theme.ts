import { extendTheme, type ThemeConfig } from "@chakra-ui/react";

const config: ThemeConfig = {
  initialColorMode: "dark",
  useSystemColorMode: false,
};

const theme = extendTheme({
  config,
  fonts: {
    heading: `"Inter", system-ui, sans-serif`,
    body: `"Inter", system-ui, sans-serif`,
    mono: `"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace`,
  },
  colors: {
    brand: {
      50: "#e8edff",
      100: "#c5cfff",
      200: "#9eafff",
      300: "#7c9cff",
      400: "#6d8bff",
      500: "#5b7cfa",
      600: "#4a65d4",
      700: "#3a4fae",
      800: "#2b3a88",
      900: "#1c2662",
    },
    surface: {
      bg: "#0a0e1a",
      card: "#0f1420",
      elevated: "#151b2e",
      hover: "#1a2140",
      active: "#1e2748",
    },
  },
  styles: {
    global: {
      "html, body": {
        bg: "surface.bg",
        color: "gray.100",
        overflowX: "hidden",
      },
      "*::-webkit-scrollbar": {
        width: "6px",
      },
      "*::-webkit-scrollbar-track": {
        bg: "transparent",
      },
      "*::-webkit-scrollbar-thumb": {
        bg: "whiteAlpha.200",
        borderRadius: "full",
      },
      "*::-webkit-scrollbar-thumb:hover": {
        bg: "whiteAlpha.300",
      },
    },
  },
  components: {
    Button: {
      baseStyle: {
        fontWeight: 500,
        borderRadius: "lg",
      },
    },
  },
});

export default theme;
