"use client";

import ChatPanel from "@/components/ChatPanel";
import { strategyChat, type StrategyChatResult } from "@/lib/api";
import type { AgentSettings } from "@/lib/types";

type Extras = Pick<StrategyChatResult, "applied">;

export default function StrategyChat({
  onApplied,
}: {
  onApplied?: (settings: AgentSettings) => void;
}) {
  return (
    <ChatPanel<Extras>
      title="Instruct the agent"
      hint="toggles · risk rules · halt / resume · bankroll"
      emptyText={
        <>
          Give the autonomous agent instructions in plain language — &ldquo;turn off copy
          trading&rdquo;, &ldquo;set stop loss to 30%&rdquo;, &ldquo;be more
          conservative&rdquo;, &ldquo;halt everything&rdquo; — or ask how it is configured
          and doing. Changes apply immediately and the widgets above reflect them.
        </>
      }
      placeholder="Tell the agent what to run and how much risk to take…"
      sendLabel="Send"
      footer="changes are whitelisted & clamped by code · paper trading only"
      send={async (question, history) => {
        const res = await strategyChat(question, history);
        if (res.applied && res.settings && onApplied) onApplied(res.settings);
        return { content: res.answer ?? "(no answer)", extras: { applied: res.applied } };
      }}
      renderExtrasTop={(e) =>
        e.applied ? (
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-emerald-400">
            settings updated · {Object.keys(e.applied).length} change
            {Object.keys(e.applied).length === 1 ? "" : "s"}
          </div>
        ) : null
      }
    />
  );
}
