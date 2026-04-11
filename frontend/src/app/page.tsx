"use client";

import { useEffect, useState } from "react";
import { getDashboardStats } from "@/lib/api";
import type { DashboardStats } from "@/lib/types";

export default function Home() {
  const [stats, setStats] = useState<DashboardStats | null>(null);

  useEffect(() => {
    getDashboardStats().then(setStats).catch(console.error);
  }, []);

  const cards = [
    {
      label: "Total Invoices",
      value: stats?.total_invoices ?? "—",
      color: "text-blue-600",
      bg: "bg-blue-50",
    },
    {
      label: "Invoices Done",
      value: stats?.invoices_done ?? "—",
      color: "text-green-600",
      bg: "bg-green-50",
    },
    {
      label: "Pending",
      value: stats?.invoices_pending ?? "—",
      color: "text-amber-600",
      bg: "bg-amber-50",
    },
    {
      label: "Failed",
      value: stats?.invoices_failed ?? "—",
      color: "text-red-600",
      bg: "bg-red-50",
    },
    {
      label: "Match Rate",
      value: stats ? `${stats.match_rate}%` : "—",
      color: "text-purple-600",
      bg: "bg-purple-50",
    },
    {
      label: "Products in DB",
      value: stats?.total_products ?? "—",
      color: "text-indigo-600",
      bg: "bg-indigo-50",
    },
    {
      label: "Suppliers",
      value: stats?.total_suppliers ?? "—",
      color: "text-teal-600",
      bg: "bg-teal-50",
    },
  ];

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">
          AI Invoice Processing System — Overview
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {cards.map((card) => (
          <div
            key={card.label}
            className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm"
          >
            <p className={`text-3xl font-bold ${card.color}`}>{card.value}</p>
            <p className="text-sm text-gray-500 mt-1">{card.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
