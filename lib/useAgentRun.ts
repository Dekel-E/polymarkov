"use client";

import { useEffect, useRef, useState } from "react";
import { executeAgent } from "./api";
import type { ExecuteOut } from "./types";

export function useAgentRun() {
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState<ExecuteOut | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  async function run(prompt: string) {
    const text = prompt.trim();
    if (!text || running) return;
    setRunning(true);
    setResult(null);
    setFetchError(null);
    setElapsed(0);
    const started = Date.now();
    timerRef.current = setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    try {
      setResult(await executeAgent(text));
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : String(err));
    } finally {
      if (timerRef.current) clearInterval(timerRef.current);
      setRunning(false);
    }
  }

  return { running, elapsed, result, fetchError, run };
}
