import type { IconType } from "react-icons";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  meta?: {
    viewKey?: string;
    sql?: string;
    rowCount?: number;
    isInsight?: boolean;
    reportKey?: string;
  };
}

export type StreamPhase =
  | "routing"
  | "generating_sql"
  | "executing"
  | "explaining"
  | "fetching_data"
  | "formatting";

export interface PhaseInfo {
  phase: StreamPhase;
  message: string;
}

export interface QuickAction {
  label: string;
  question: string;
  icon: IconType;
  category: "insight" | "qa";
}
