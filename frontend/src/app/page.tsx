"use client";

import { useEffect, useState } from "react";
import { getDashboardStats } from "@/lib/api";
import type { DashboardStats } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import {
  FileText,
  CheckCircle2,
  Clock,
  AlertCircle,
  Target,
  Package,
  Building2,
} from "lucide-react";

export default function Home() {
  const [stats, setStats] = useState<DashboardStats | null>(null);

  useEffect(() => {
    getDashboardStats().then(setStats).catch(console.error);
  }, []);

  const cards = [
    {
      label: "Total Invoices",
      value: stats?.total_invoices ?? "—",
      icon: FileText,
      color: "text-blue-600",
    },
    {
      label: "Invoices Done",
      value: stats?.invoices_done ?? "—",
      icon: CheckCircle2,
      color: "text-green-600",
    },
    {
      label: "Pending",
      value: stats?.invoices_pending ?? "—",
      icon: Clock,
      color: "text-amber-600",
    },
    {
      label: "Failed",
      value: stats?.invoices_failed ?? "—",
      icon: AlertCircle,
      color: "text-red-600",
    },
    {
      label: "Match Rate",
      value: stats ? `${stats.match_rate}%` : "—",
      icon: Target,
      color: "text-purple-600",
    },
    {
      label: "Products in DB",
      value: stats?.total_products ?? "—",
      icon: Package,
      color: "text-indigo-600",
    },
    {
      label: "Suppliers",
      value: stats?.total_suppliers ?? "—",
      icon: Building2,
      color: "text-teal-600",
    },
  ];

  return (
    <div className="p-4 md:p-8">
      <PageHeader
        title="Dashboard"
        description="AI Invoice Processing System — Overview"
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {stats === null
          ? Array.from({ length: 7 }).map((_, i) => (
              <Card key={i}>
                <CardContent className="p-5">
                  <Skeleton className="h-8 w-16 mb-2" />
                  <Skeleton className="h-4 w-24" />
                </CardContent>
              </Card>
            ))
          : cards.map((card) => (
              <Card key={card.label} className="group transition-shadow hover:shadow-md">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between mb-2">
                    <card.icon className={`h-6 w-6 ${card.color} transition-transform duration-200 group-hover:scale-110`} />
                  </div>
                  <p className={`text-3xl font-bold ${card.color}`}>
                    {card.value}
                  </p>
                  <p className="text-[15px] text-muted-foreground mt-1">
                    {card.label}
                  </p>
                </CardContent>
              </Card>
            ))}
      </div>
    </div>
  );
}
