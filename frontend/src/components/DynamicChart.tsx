import {
  Card,
  CardBody,
  CardHeader,
  Heading,
  Text,
  VStack,
} from "@chakra-ui/react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  VisualizationConfig,
  VisualizationSeries,
  VisualizationSeriesPoint,
  ChartType,
} from "../types";

interface DynamicChartProps {
  config: VisualizationConfig;
}

type CartesianDatum = {
  x: string | number;
  [seriesName: string]: string | number;
};

function normalizeCartesian(
  series: VisualizationSeries[],
): { data: CartesianDatum[]; seriesKeys: string[] } {
  const byX = new Map<string | number, Record<string, number>>();

  for (const s of series) {
    for (const point of s.data) {
      const key = point.x;
      const existing = byX.get(key) ?? {};
      existing[s.name] = point.y;
      byX.set(key, existing);
    }
  }

  const data: CartesianDatum[] = [];
  for (const [x, valueMap] of byX.entries()) {
    data.push({ x, ...valueMap });
  }

  const seriesKeys = series.map((s) => s.name);
  return { data, seriesKeys };
}

function renderCartesianChart(config: VisualizationConfig, chartType: ChartType) {
  const { data, seriesKeys } = normalizeCartesian(config.series);

  const ChartComponent =
    chartType === "bar"
      ? BarChart
      : chartType === "area"
      ? AreaChart
      : LineChart;

  const renderSeries = () => {
    return seriesKeys.map((name) => {
      if (chartType === "bar") {
        return <Bar key={name} dataKey={name} name={name} />;
      }
      if (chartType === "area") {
        return (
          <Area
            key={name}
            type="monotone"
            dataKey={name}
            name={name}
            fillOpacity={0.3}
          />
        );
      }
      return <Line key={name} type="monotone" dataKey={name} name={name} />;
    });
  };

  return (
    <ResponsiveContainer width="100%" height={260}>
      <ChartComponent data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="x" />
        <YAxis />
        <Tooltip />
        <Legend />
        {renderSeries()}
      </ChartComponent>
    </ResponsiveContainer>
  );
}

function renderPieChart(config: VisualizationConfig) {
  const points: VisualizationSeriesPoint[] =
    config.series.flatMap((s) => s.data) ?? [];

  const pieData = points.map((p, index) => ({
    name: String(p.x ?? index),
    value: p.y,
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Tooltip />
        <Legend />
        <Pie data={pieData} dataKey="value" nameKey="name" />
      </PieChart>
    </ResponsiveContainer>
  );
}

function renderKPI(config: VisualizationConfig) {
  const primary = config.primary_metric || config.y_axis?.[0];
  const firstSeries = config.series[0];
  const latestPoint = firstSeries?.data[firstSeries.data.length - 1];

  return (
    <VStack align="flex-start" spacing={1}>
      <Heading size="2xl">
        {latestPoint ? latestPoint.y : "—"}
      </Heading>
      {primary && (
        <Text fontSize="sm" color="gray.500">
          {primary}
        </Text>
      )}
    </VStack>
  );
}

export function DynamicChart({ config }: DynamicChartProps) {
  const { chart_type, title, insights } = config;

  let body: JSX.Element;
  if (chart_type === "kpi") {
    body = renderKPI(config);
  } else if (chart_type === "pie") {
    body = renderPieChart(config);
  } else if (chart_type === "bar" || chart_type === "area" || chart_type === "line") {
    body = renderCartesianChart(config, chart_type);
  } else {
    // Fallback: show raw JSON if chart_type unsupported
    body = (
      <Text fontSize="sm" fontFamily="mono" whiteSpace="pre-wrap">
        {JSON.stringify(config, null, 2)}
      </Text>
    );
  }

  return (
    <Card variant="outline" mt={3}>
      <CardHeader pb={2}>
        <Heading size="sm">{title}</Heading>
      </CardHeader>
      <CardBody>
        <VStack align="stretch" spacing={3}>
          {body}
          {insights?.length ? (
            <VStack align="flex-start" spacing={1}>
              <Text fontSize="sm" fontWeight="semibold">
                Insights:
              </Text>
              {insights.map((line, idx) => (
                <Text key={idx} fontSize="sm">
                  • {line}
                </Text>
              ))}
            </VStack>
          ) : null}
        </VStack>
      </CardBody>
    </Card>
  );
}

