/**
 * Statistics card component for quota management
 */

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import {
  TrendingUp,
  TrendingDown,
  AlertCircle,
  CheckCircle,
  XCircle,
  Loader2,
} from "lucide-react";

interface QuotaStatsCardProps {
  title: string;
  value: number | string;
  subtitle?: string;
  percentage?: number;
  trend?: "up" | "down" | "neutral";
  status?: "normal" | "warning" | "critical" | "exceeded";
  loading?: boolean;
  icon?: React.ReactNode;
  className?: string;
}

export function QuotaStatsCard({
  title,
  value,
  subtitle,
  percentage,
  trend,
  status = "normal",
  loading = false,
  icon,
  className,
}: QuotaStatsCardProps) {
  const getStatusColor = () => {
    switch (status) {
      case "exceeded":
        return "text-red-600 bg-red-50 border-red-200";
      case "critical":
        return "text-orange-600 bg-orange-50 border-orange-200";
      case "warning":
        return "text-yellow-600 bg-yellow-50 border-yellow-200";
      case "normal":
        return "text-green-600 bg-green-50 border-green-200";
      default:
        return "";
    }
  };

  const getStatusIcon = () => {
    switch (status) {
      case "exceeded":
        return <XCircle className="h-4 w-4 text-red-600" />;
      case "critical":
        return <AlertCircle className="h-4 w-4 text-orange-600" />;
      case "warning":
        return <AlertCircle className="h-4 w-4 text-yellow-600" />;
      case "normal":
        return <CheckCircle className="h-4 w-4 text-green-600" />;
      default:
        return null;
    }
  };

  const getTrendIcon = () => {
    if (!trend || trend === "neutral") return null;
    return trend === "up" ? (
      <TrendingUp className="h-4 w-4 text-green-600" />
    ) : (
      <TrendingDown className="h-4 w-4 text-red-600" />
    );
  };

  const getProgressColor = () => {
    if (!percentage) return "bg-blue-600";
    if (percentage >= 95) return "bg-red-600";
    if (percentage >= 80) return "bg-orange-600";
    if (percentage >= 50) return "bg-yellow-600";
    return "bg-green-600";
  };

  if (loading) {
    return (
      <Card className={cn("relative overflow-hidden", className)}>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-gray-600">
            {title}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card
      className={cn("relative overflow-hidden", getStatusColor(), className)}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-gray-600">
            {title}
          </CardTitle>
          <div className="flex items-center gap-1">
            {getStatusIcon()}
            {getTrendIcon()}
            {icon}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          <div className="text-2xl font-bold">{value}</div>

          {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}

          {percentage !== undefined && (
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500">使用率</span>
                <span className="font-medium">{percentage}%</span>
              </div>
              <Progress
                value={percentage}
                className="h-2"
                indicatorClassName={getProgressColor()}
              />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// Compound component for a group of stats cards
interface QuotaStatsGroupProps {
  children: React.ReactNode;
  className?: string;
}

export function QuotaStatsGroup({ children, className }: QuotaStatsGroupProps) {
  return (
    <div className={cn("grid gap-4 md:grid-cols-2 lg:grid-cols-4", className)}>
      {children}
    </div>
  );
}
