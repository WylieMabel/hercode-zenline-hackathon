import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";

const ROOT = path.resolve(process.cwd(), "..");

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const location = body.location || "Switzerland";
  const market = body.market || "Swiss outdoor";
  const client = body.client || "";

  const env = {
    ...process.env,
    PIPELINE_LOCATION: location,
    PIPELINE_MARKET: market,
    PIPELINE_CLIENT: client,
  };

  return new Response(
    new ReadableStream({
      start(controller) {
        const enc = new TextEncoder();
        const send = (msg: string) => controller.enqueue(enc.encode(msg + "\n"));

        send(`Starting pipeline: ${market} · ${location}${client ? ` · client: ${client}` : ""}`);

        const proc = spawn(
          "python3",
          ["-u", path.join(ROOT, "scraper_pipeline.py")],
          { cwd: ROOT, env }
        );

        proc.stdout.on("data", (d) => send(d.toString().trimEnd()));
        proc.stderr.on("data", (d) => send(d.toString().trimEnd()));
        proc.on("close", (code) => {
          send(code === 0 ? "✓ Pipeline complete." : `✗ Pipeline exited with code ${code}.`);
          controller.close();
        });
        proc.on("error", (err) => {
          send(`Error: ${err.message}`);
          controller.close();
        });
      },
    }),
    { headers: { "Content-Type": "text/plain; charset=utf-8", "X-Content-Type-Options": "nosniff" } }
  );
}
