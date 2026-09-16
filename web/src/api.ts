import type { components } from "./generated";
export type Config = components["schemas"]["WorldConfig"];
export type Run = components["schemas"]["RunView"];
export type Snapshot = components["schemas"]["Snapshot"];
export type Agent = components["schemas"]["AgentState"];
export type Job = components["schemas"]["JobView"];
export type ExperimentSpec = components["schemas"]["ExperimentSpec"];
export type ResearchSpec = components["schemas"]["ResearchSpec"];
export type Policy = "private" | "pool" | "surplus";
export const policyNames: Record<Policy, string> = {
  private: "Private stores",
  pool: "Common pool",
  surplus: "Surplus sharing",
};
export async function api<T>(url: string, data?: unknown): Promise<T> {
  const response = await fetch(
    "/api" + url,
    data === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        },
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : JSON.stringify(error.detail),
    );
  }
  return response.json();
}
export const fmt = (n: number | undefined, d = 0) =>
  Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: d });
