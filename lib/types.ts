// Mirrors backend/agent/types.py — keep in sync.

export interface StepPrompt {
  system_prompt: string;
  user_prompt: string;
}

export interface Step {
  module: string;
  prompt: StepPrompt;
  response: unknown;
}

export interface ExecuteOut {
  status: "ok" | "error";
  error: string | null;
  response: string | null;
  steps: Step[];
  ui?: Record<string, unknown> | null;
}
