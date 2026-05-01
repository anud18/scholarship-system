import type { TestInfo } from "@playwright/test";

export interface RunState {
  startedAt: number;
  traceIds: string[];
  appId?: string;
  configId?: number;
  classificationHint?: "codebase" | "seed" | "frontend" | "test";
  notes?: string[];
}

export const RUN_STATE_ATTACHMENT = "runState";

export function newRunState(): RunState {
  return { startedAt: Date.now(), traceIds: [] };
}

export function pushTrace(state: RunState, traceId: string | null | undefined): void {
  if (typeof traceId === "string" && traceId.length > 0 && !state.traceIds.includes(traceId)) {
    state.traceIds.push(traceId);
  }
}

export async function attachRunState(testInfo: TestInfo, state: RunState): Promise<void> {
  await testInfo.attach(RUN_STATE_ATTACHMENT, {
    body: JSON.stringify(state, null, 2),
    contentType: "application/json",
  });
}
