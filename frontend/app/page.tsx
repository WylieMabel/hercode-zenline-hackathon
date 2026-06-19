"use client";

import { useEffect, useRef, useState } from "react";

/* ── types ── */
type Opp = Record<string, string>;
type Insights = { trends?: string[]; features?: string[]; materials?: string[]; aesthetics?: string[]; color_palettes?: string[] };
type Gaps = { gap_brands?: string[]; gap_categories?: string[]; summary?: string };

const CONF_COLOR: Record<string, string> = { high: "bg-green-100 text-green-800", medium: "bg-yellow-100 text-yellow-800", low: "bg-red-100 text-red-800" };
const WF_COLOR: Record<string, string> = { launch: "bg-purple-100 text-purple-800", buy: "bg-blue-100 text-blue-800", test: "bg-orange-100 text-orange-800", monitor: "bg-gray-100 text-gray-700" };
const WF_ICON: Record<string, string> = { launch: "🚀", buy: "🛒", test: "🧪", monitor: "👀" };
const TYPE_LABEL: Record<string, string> = {
  product_type: "Product", material: "Material", feature: "Feature",
  aesthetic: "Aesthetic", color_palette: "Colour", brand: "Brand",
  price_gap: "Price gap", merchandising: "Merchandising",
  usage_occasion: "Occasion", content_community: "Content",
};

function Badge({ label, color }: { label: string; color: string }) {
  return <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>{label}</span>;
}

function Chip({ label, color = "bg-alpine-100 text-alpine-700" }: { label: string; color?: string }) {
  return <span className={`inline-block px-2 py-0.5 rounded-full text-xs mr-1 mb-1 ${color}`}>{label}</span>;
}

function OpportunityCard({ opp, defaultOpen }: { opp: Opp; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen ?? false);
  const conf = opp.confidence ?? "low";
  const wf = opp.recommended_workflow ?? "monitor";
  const urls = (opp.evidence_urls ?? "").split(";").map((u) => u.trim()).filter((u) => u && u !== "N/A");
  const evidence = (opp.evidence ?? "").split(";").map((e) => e.trim()).filter(Boolean);

  return (
    <div className="border border-gray-200 rounded-xl p-4 bg-white shadow-sm">
      <div className="flex items-start justify-between gap-2 cursor-pointer" onClick={() => setOpen(!open)}>
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-alpine-700 font-bold text-sm">#{opp.rank}</span>
            {opp.signal_score && Number(opp.signal_score) > 0 && (
              <span className="text-xs font-mono bg-alpine-100 text-alpine-700 px-1.5 py-0.5 rounded">
                {Number(opp.signal_score).toFixed(2)}
              </span>
            )}
            <span className="font-semibold text-gray-900">{opp.opportunity}</span>
          </div>
          <div className="flex gap-1 flex-wrap">
            <Badge label={TYPE_LABEL[opp.opportunity_type] ?? opp.opportunity_type ?? ""} color="bg-indigo-50 text-indigo-700" />
            <Badge label={CONF_COLOR[conf] ? `${conf} confidence` : conf} color={CONF_COLOR[conf] ?? "bg-gray-100 text-gray-700"} />
            <Badge label={`${WF_ICON[wf] ?? ""} ${wf}`} color={WF_COLOR[wf] ?? "bg-gray-100 text-gray-700"} />
            {opp.first_observed_market && opp.first_observed_market !== "N/A" && (
              <Badge label={`First: ${opp.first_observed_market}`} color="bg-slate-100 text-slate-600" />
            )}
          </div>
        </div>
        <span className="text-gray-400 text-sm mt-1">{open ? "▲" : "▼"}</span>
      </div>

      {opp.description && <p className="text-sm text-gray-700 mt-2">{opp.description}</p>}

      {open && (
        <div className="mt-3 space-y-3 border-t pt-3">
          {evidence.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Evidence</p>
              <ul className="text-sm space-y-0.5 text-gray-700">
                {evidence.map((e, i) => <li key={i} className="before:content-['·'] before:mr-1">{e}</li>)}
              </ul>
            </div>
          )}
          {urls.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Sources</p>
              <ul className="text-sm space-y-0.5">
                {urls.map((u, i) => <li key={i}><a href={u} target="_blank" rel="noreferrer" className="text-alpine-500 underline break-all">{u}</a></li>)}
              </ul>
            </div>
          )}
          {opp.action && (
            <div className="bg-alpine-50 border border-alpine-100 rounded-lg p-3">
              <p className="text-xs font-semibold text-alpine-700 uppercase mb-0.5">Recommended action</p>
              <p className="text-sm text-gray-800">{opp.action ?? opp.recommended_action}</p>
            </div>
          )}
          <div className="grid grid-cols-2 gap-2 text-xs text-gray-600">
            {opp.transferability && <div><span className="font-medium">DACH:</span> {opp.transferability}</div>}
            {opp.coverage_status && <div><span className="font-medium">Coverage:</span> {opp.coverage_status}</div>}
            {opp.risks && <div className="col-span-2"><span className="font-medium text-red-600">Risks:</span> {opp.risks}</div>}
          </div>
          {(opp.features || opp.materials || opp.aesthetics || opp.color_palettes) && (
            <div className="flex flex-wrap gap-1">
              {(opp.features ?? "").split(";").filter(Boolean).map((f, i) => <Chip key={i} label={f.trim()} color="bg-blue-50 text-blue-700" />)}
              {(opp.materials ?? "").split(";").filter(Boolean).map((m, i) => <Chip key={i} label={m.trim()} color="bg-purple-50 text-purple-700" />)}
              {(opp.aesthetics ?? "").split(";").filter(Boolean).map((a, i) => <Chip key={i} label={a.trim()} color="bg-orange-50 text-orange-700" />)}
              {(opp.color_palettes ?? "").split(";").filter(Boolean).map((c, i) => <Chip key={i} label={c.trim()} color="bg-pink-50 text-pink-700" />)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── main page ── */
export default function Home() {
  const [tab, setTab] = useState<"opps" | "report" | "pipeline">("opps");
  const [opps, setOpps] = useState<Opp[]>([]);
  const [rawCount, setRawCount] = useState(0);
  const [insights, setInsights] = useState<Insights>({});
  const [gaps, setGaps] = useState<Gaps>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  // Pipeline form
  const [location, setLocation] = useState("Switzerland");
  const [market, setMarket] = useState("Swiss outdoor");
  const [client, setClient] = useState("Decathlon");
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const logRef = useRef<HTMLDivElement>(null);

  const load = async () => {
    setLoading(true);
    const [res, ins] = await Promise.all([fetch("/api/results"), fetch("/api/insights")]);
    const rd = await res.json();
    const id = await ins.json();
    if (rd.error) setError(rd.error);
    else setError("");
    setOpps(rd.opportunities ?? []);
    setRawCount(rd.rawCount ?? 0);
    setInsights(id.insights ?? {});
    setGaps(id.gaps ?? {});
    setLoading(false);
  };

  useEffect(() => { load(); }, []);
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [log]);

  const runPipeline = async () => {
    setRunning(true);
    setLog([]);
    setTab("pipeline");
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ location, market, client }),
    });
    if (!res.body) { setRunning(false); return; }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      setLog((prev) => [...prev, ...dec.decode(value).split("\n").filter(Boolean)]);
    }
    setRunning(false);
    load();
  };

  const sorted = [...opps].sort((a, b) => {
    const sa = Number(a.signal_score ?? 0);
    const sb = Number(b.signal_score ?? 0);
    if (sa !== sb) return sb - sa;
    return Number(a.rank ?? 99) - Number(b.rank ?? 99);
  });
  const highConf = sorted.filter((o) => o.confidence === "high").length;
  const actionable = sorted.filter((o) => ["buy", "launch"].includes(o.recommended_workflow ?? "")).length;

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-alpine-700">⛰️ Zenline Opportunity Scout</h1>
          <p className="text-sm text-gray-500 mt-0.5">Swiss outdoor retail · six-step signal pipeline</p>
        </div>
        <button
          onClick={runPipeline}
          disabled={running}
          className="px-4 py-2 rounded-lg bg-alpine-500 text-white text-sm font-medium hover:bg-alpine-700 disabled:opacity-50 transition-colors"
        >
          {running ? "Running…" : "▶ Run Pipeline"}
        </button>
      </div>

      {/* Metrics */}
      {!loading && opps.length > 0 && (
        <div className="grid grid-cols-4 gap-3 mb-6">
          {[
            ["Signals", rawCount],
            ["Opportunities", sorted.length],
            ["High confidence", highConf],
            ["Ready to act", actionable],
          ].map(([label, val]) => (
            <div key={label} className="bg-white border border-gray-200 rounded-xl p-3 text-center shadow-sm">
              <div className="text-2xl font-bold text-alpine-700">{val}</div>
              <div className="text-xs text-gray-500 mt-0.5">{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200 mb-6">
        {([["opps", "📊 Opportunities"], ["report", "📋 Report"], ["pipeline", "▶ Pipeline"]] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === key ? "border-alpine-500 text-alpine-700" : "border-transparent text-gray-500 hover:text-gray-700"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab: Opportunities */}
      {tab === "opps" && (
        <div>
          {loading && <p className="text-gray-400 text-sm">Loading…</p>}
          {error && <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-sm text-yellow-800">{error}</div>}
          {!loading && sorted.length === 0 && !error && <p className="text-gray-400 text-sm">No opportunities yet — run the pipeline first.</p>}
          <div className="space-y-3">
            {sorted.map((opp, i) => <OpportunityCard key={i} opp={opp} defaultOpen={i === 0} />)}
          </div>
        </div>
      )}

      {/* Tab: Report */}
      {tab === "report" && (
        <div className="space-y-6">
          {/* Pipeline story */}
          <section>
            <h2 className="text-base font-semibold text-gray-800 mb-3">How we got here</h2>
            <div className="space-y-2">
              {[
                ["1", "Competitor products", `Scraped competitor catalogues · found ${gaps.gap_brands?.length ?? 0} assortment gap brands`],
                ["2", "Social & trend signals", "Reddit, TikTok, GearJunkie, YouTube · keyword signal extraction"],
                ["3", "Regional context", "Swiss weather anomaly · upcoming holidays · daylight hours · CHF/FX rates"],
                ["4", "Google Trends", "12-month series · global + CH market · velocity & lead-market detection"],
                ["5", "Scoring", "Momentum · early-market · innovation · competitor gap · commercial fit"],
                ["6", "LLM recommendations", `${sorted.length} ranked opportunities · ${highConf} high-confidence`],
              ].map(([num, title, detail]) => (
                <div key={num} className="flex gap-3 bg-white border border-gray-200 rounded-lg p-3 shadow-sm">
                  <div className="w-7 h-7 rounded-full bg-alpine-500 text-white text-xs font-bold flex items-center justify-center flex-shrink-0">{num}</div>
                  <div>
                    <p className="text-sm font-medium text-gray-900">{title}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{detail}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Trend intelligence */}
          {Object.keys(insights).length > 0 && (
            <section>
              <h2 className="text-base font-semibold text-gray-800 mb-3">Trend intelligence</h2>
              <div className="grid grid-cols-2 gap-4">
                {[
                  ["Features", insights.features, "bg-blue-50 text-blue-700"],
                  ["Materials", insights.materials, "bg-purple-50 text-purple-700"],
                  ["Aesthetics / vibes", insights.aesthetics, "bg-orange-50 text-orange-700"],
                  ["Colour palettes", insights.color_palettes, "bg-pink-50 text-pink-700"],
                ].map(([label, items, color]) => items && (items as string[]).length > 0 && (
                  <div key={label as string} className="bg-white border border-gray-200 rounded-lg p-3 shadow-sm">
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-2">{label as string}</p>
                    <div className="flex flex-wrap">{(items as string[]).map((item, i) => <Chip key={i} label={item} color={color as string} />)}</div>
                  </div>
                ))}
              </div>
              {insights.trends && insights.trends.length > 0 && (
                <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-sm mt-3">
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Emerging trends</p>
                  <ul className="text-sm text-gray-700 space-y-0.5">
                    {insights.trends.slice(0, 6).map((t, i) => <li key={i} className="before:content-['·'] before:mr-1">{t}</li>)}
                  </ul>
                </div>
              )}
            </section>
          )}

          {/* Competitor gaps */}
          {((gaps.gap_brands?.length ?? 0) > 0 || (gaps.gap_categories?.length ?? 0) > 0) && (
            <section>
              <h2 className="text-base font-semibold text-gray-800 mb-1">Competitor assortment gaps</h2>
              <p className="text-xs text-gray-500 mb-3">Brands and categories seen at competitors but not in client assortment.</p>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-sm">
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Gap brands</p>
                  <div className="flex flex-wrap">{gaps.gap_brands?.map((b, i) => <Chip key={i} label={b} color="bg-red-50 text-red-700" />)}</div>
                </div>
                <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-sm">
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Gap categories</p>
                  <div className="flex flex-wrap">{gaps.gap_categories?.map((c, i) => <Chip key={i} label={c} color="bg-amber-50 text-amber-700" />)}</div>
                </div>
              </div>
            </section>
          )}

          {/* Summary table */}
          {sorted.length > 0 && (
            <section>
              <h2 className="text-base font-semibold text-gray-800 mb-3">All recommendations</h2>
              <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
                <table className="w-full text-sm bg-white">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50 text-xs text-gray-500 uppercase">
                      {["#", "Opportunity", "Type", "First market", "Coverage", "Workflow", "Confidence"].map((h) => (
                        <th key={h} className="px-3 py-2 text-left font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((o, i) => (
                      <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="px-3 py-2 font-bold text-alpine-700">{o.rank}</td>
                        <td className="px-3 py-2 font-medium max-w-[200px]">{o.opportunity}</td>
                        <td className="px-3 py-2 text-gray-500">{TYPE_LABEL[o.opportunity_type] ?? o.opportunity_type}</td>
                        <td className="px-3 py-2 text-gray-500">{o.first_observed_market ?? "—"}</td>
                        <td className="px-3 py-2 text-gray-500">{o.coverage_status ?? "—"}</td>
                        <td className="px-3 py-2"><Badge label={`${WF_ICON[o.recommended_workflow ?? ""] ?? ""} ${o.recommended_workflow ?? ""}`} color={WF_COLOR[o.recommended_workflow ?? ""] ?? "bg-gray-100 text-gray-600"} /></td>
                        <td className="px-3 py-2"><Badge label={o.confidence ?? ""} color={CONF_COLOR[o.confidence ?? ""] ?? "bg-gray-100 text-gray-600"} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
      )}

      {/* Tab: Pipeline */}
      {tab === "pipeline" && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Location</label>
              <input value={location} onChange={(e) => setLocation(e.target.value)} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-alpine-500" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Market / category</label>
              <input value={market} onChange={(e) => setMarket(e.target.value)} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-alpine-500" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Client company</label>
              <input value={client} onChange={(e) => setClient(e.target.value)} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-alpine-500" />
            </div>
          </div>
          <button
            onClick={runPipeline}
            disabled={running}
            className="px-5 py-2 rounded-lg bg-alpine-500 text-white text-sm font-medium hover:bg-alpine-700 disabled:opacity-50 transition-colors"
          >
            {running ? "Pipeline running…" : "▶ Run Pipeline"}
          </button>
          <div
            ref={logRef}
            className="bg-gray-900 text-green-300 rounded-xl p-4 font-mono text-xs h-96 overflow-y-auto whitespace-pre-wrap"
          >
            {log.length === 0 ? <span className="text-gray-500">Output will appear here…</span> : log.join("\n")}
          </div>
        </div>
      )}
    </div>
  );
}
