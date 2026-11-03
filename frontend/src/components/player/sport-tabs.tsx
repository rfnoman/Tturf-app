"use client";

import type { ReactNode } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export type SportTab = {
  value: string;
  label: string;
  icon?: string;
  content: ReactNode;
};

/**
 * One tab per sport on the profile.
 *
 * A thin client boundary: the cards themselves are server components passed in as
 * `content`, so the only thing shipped to the browser is the tab switching.
 */
export function SportTabs({ tabs }: { tabs: SportTab[] }) {
  if (tabs.length === 0) return null;
  if (tabs.length === 1) return <>{tabs[0].content}</>;

  return (
    <Tabs defaultValue={tabs[0].value} className="gap-4">
      <TabsList>
        {tabs.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value}>
            <span aria-hidden className="mr-1">
              {tab.icon}
            </span>
            {tab.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {tabs.map((tab) => (
        <TabsContent key={tab.value} value={tab.value}>
          {tab.content}
        </TabsContent>
      ))}
    </Tabs>
  );
}
