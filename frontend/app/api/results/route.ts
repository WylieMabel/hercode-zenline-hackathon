import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

const ROOT = path.resolve(process.cwd(), "..");

function parseCSV(text: string): Record<string, string>[] {
  const lines = text.trim().split("\n");
  if (lines.length < 2) return [];
  const headers = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
  return lines.slice(1).map((line) => {
    const values: string[] = [];
    let cur = "";
    let inQuote = false;
    for (const ch of line) {
      if (ch === '"') { inQuote = !inQuote; }
      else if (ch === "," && !inQuote) { values.push(cur); cur = ""; }
      else { cur += ch; }
    }
    values.push(cur);
    return Object.fromEntries(headers.map((h, i) => [h, (values[i] ?? "").trim()]));
  });
}

export async function GET() {
  const recPath = path.join(ROOT, "ranked_recommendations.csv");
  const rawPath = path.join(ROOT, "raw_signals.csv");

  if (!fs.existsSync(recPath)) {
    return NextResponse.json({ opportunities: [], rawCount: 0, error: "ranked_recommendations.csv not found — run the pipeline first." });
  }

  const opportunities = parseCSV(fs.readFileSync(recPath, "utf-8"));
  const rawCount = fs.existsSync(rawPath)
    ? fs.readFileSync(rawPath, "utf-8").trim().split("\n").length - 1
    : 0;

  return NextResponse.json({ opportunities, rawCount });
}
