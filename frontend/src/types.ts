import type { IconType } from "react-icons";

export type ChartType = "line" | "bar" | "pie" | "table" | "kpi" | "area";

export interface VisualizationSeriesPoint {
  x: string | number;
  y: number;
}

export interface VisualizationSeries {
  name: string;
  data: VisualizationSeriesPoint[];
}

export interface VisualizationConfig {
  chart_type: ChartType;
  title: string;
  x_axis: string | null;
  y_axis: string[];
  series: VisualizationSeries[];
  insights: string[];
  analysis_type?: "trend" | "comparison" | "distribution" | "kpi";
  is_time_series?: boolean;
  primary_metric?: string;
}

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
    visualizations?: VisualizationConfig[];
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
