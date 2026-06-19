import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

const ROOT = path.resolve(process.cwd(), "..");

export async function GET() {
  const insightsPath = path.join(ROOT, "trend_insights.json");
  const gapPath = path.join(ROOT, "competitor_gap_hints.json");

  const insights = fs.existsSync(insightsPath)
    ? JSON.parse(fs.readFileSync(insightsPath, "utf-8"))
    : {};

  const gaps = fs.existsSync(gapPath)
    ? JSON.parse(fs.readFileSync(gapPath, "utf-8"))
    : {};

  return NextResponse.json({ insights, gaps });
}
