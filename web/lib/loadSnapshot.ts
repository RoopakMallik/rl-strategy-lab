// Read the snapshot at build time. The page is pre-rendered, so the deployed site never fetches it.
import { readFileSync } from "node:fs";
import path from "node:path";
import type { AssistantAnswers, Dashboard, EquityCurves } from "./snapshotTypes";

const DATA_DIR = path.join(process.cwd(), "public", "data");

function readJson<T>(fileName: string): T {
  return JSON.parse(readFileSync(path.join(DATA_DIR, fileName), "utf8")) as T;
}

export function loadSnapshot() {
  return {
    dashboard: readJson<Dashboard>("dashboard.json"),
    equityCurves: readJson<EquityCurves>("equity_curves.json"),
    assistantAnswers: readJson<AssistantAnswers>("assistant_answers.json"),
  };
}
