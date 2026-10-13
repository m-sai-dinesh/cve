"use client";

/**
 * Ask the Twin (PRD §18, screen 3b).
 *
 * The honest part of this screen is the "how it answered" block: the model never
 * writes Cypher. It picks one of a fixed set of whitelisted query templates, the
 * backend runs them against the graph, and the answer is grounded in those rows.
 * Showing the template id, the real Cypher and the row count is what makes the
 * answer auditable rather than a plausible paragraph.
 */

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  CornerDownLeft, Database, Sparkles, TriangleAlert, Code2, Bot, UserRound,
} from "lucide-react";
import React from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Api, apiError, type AskResponse } from "@/lib/api";
import { cn, nodeLabel, ratio } from "@/lib/format";
import { useApp } from "@/lib/store";
import { Collapse, Drawer, Spinner, TierBadge } from "./ui";

const SUGGESTIONS = [
  "Which components write to the RESULT table?",
  "What breaks if I change ResultService?",
  "Which classes are HIGH GxP criticality and why?",
  "Show me the dead code.",
  "Which libraries are end-of-life?",
  "What configuration findings were detected?",
];

interface Turn {
  question: string;
  answer: AskResponse | null;
  error?: string;
}

export function AskTwin({
  projectId, open, onClose,
}: { projectId: string; open: boolean; onClose: () => void }) {
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [draft, setDraft] = React.useState("");
  const selectNode = useApp((s) => s.selectNode);
  const scroller = React.useRef<HTMLDivElement>(null);

  const templates = useQuery({
    queryKey: ["templates", projectId],
    queryFn: () => Api.templates(projectId),
    enabled: open,
    staleTime: Infinity,
  });

  const ask = useMutation({
    mutationFn: (q: string) => Api.ask(projectId, q),
    onMutate: (q) => setTurns((t) => [...t, { question: q, answer: null }]),
    onSuccess: (res) =>
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, answer: res } : x))),
    onError: (e) =>
      setTurns((t) =>
        t.map((x, i) => (i === t.length - 1 ? { ...x, error: apiError(e) } : x))),
  });

  React.useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const submit = (q: string) => {
    const text = q.trim();
    if (!text || ask.isPending) return;
    setDraft("");
    ask.mutate(text);
  };

  return (
    <Drawer open={open} onClose={onClose} width="max-w-2xl"
      title={<span className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-accent" /> Ask the Twin</span>}
      subtitle="Grounded in the knowledge graph through whitelisted query templates - the model never writes Cypher.">
      <div className="flex h-full flex-col">
        <div ref={scroller} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
          {turns.length === 0 && (
            <div className="space-y-4">
              <p className="text-sm leading-relaxed text-muted">
                Ask a question about this application. The answer is assembled from graph
                rows, and every claim is linked back to the nodes it came from.
              </p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => submit(s)}
                    className="btn-outline py-2 px-3 text-xs font-semibold rounded-lg shadow-2xs hover:border-accent/40 min-h-[38px]">
                    {s}
                  </button>
                ))}
              </div>
              {templates.data && (
                <Collapse title={
                  <span className="flex items-center gap-2">
                    <Database className="h-3.5 w-3.5 text-muted" />
                    {templates.data.templates.length} whitelisted query templates
                  </span>
                }>
                  <p className="mb-3 text-2xs leading-relaxed text-muted">
                    {templates.data.note}
                  </p>
                  <ul className="space-y-2">
                    {templates.data.templates.map((t) => (
                      <li key={t.id} className="rounded-lg border border-line bg-raised/60 p-2.5">
                        <p className="mono font-semibold text-accent">{t.id}</p>
                        <p className="mt-0.5 text-2xs text-muted">{t.description}</p>
                        <pre className="mono mt-1.5 overflow-x-auto whitespace-pre-wrap
                                        text-[0.6875rem] leading-relaxed text-faint">
                          {t.cypher.trim()}
                        </pre>
                      </li>
                    ))}
                  </ul>
                </Collapse>
              )}
            </div>
          )}

          {turns.map((turn, i) => (
            <div key={i} className="space-y-3">
              <div className="flex items-start justify-end gap-2.5">
                <p className="max-w-[80%] rounded-xl rounded-br-sm bg-accent px-4 py-2.5
                              text-sm leading-relaxed text-white shadow-sm font-medium">
                  {turn.question}
                </p>
                <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full
                                 bg-raised text-muted border border-line/50">
                  <UserRound className="h-3.5 w-3.5" />
                </span>
              </div>

              <div className="flex items-start gap-2.5">
                <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full
                                 bg-accent-soft text-accent border border-accent/20">
                  <Bot className="h-3.5 w-3.5" />
                </span>
                <div className="min-w-0 flex-1">
                  {turn.error ? (
                    <p className="rounded-xl border border-high/35 bg-high-soft px-3.5 py-2
                                  text-xs text-high">
                      {turn.error}
                    </p>
                  ) : !turn.answer ? (
                    <p className="flex items-center gap-2 px-1 py-2 text-xs text-muted">
                      <Spinner /> querying the graph...
                    </p>
                  ) : (
                    <Answer res={turn.answer} onPick={selectNode} />
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        <form
          onSubmit={(e) => { e.preventDefault(); submit(draft); }}
          className="shrink-0 border-t border-line bg-surface p-4">
          <div className="flex items-end gap-2">
            <textarea
              value={draft} rows={1}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(draft); }
              }}
              placeholder="Which components write to the BATCH table?"
              className="input max-h-28 min-h-[44px] resize-none py-2.5 px-3 border-line shadow-xs text-xs sm:text-sm" />
            <button type="submit" disabled={ask.isPending || !draft.trim()}
              className="btn-primary h-11 w-11 shrink-0 p-0 flex items-center justify-center rounded-lg shadow-sm" aria-label="Ask">
              {ask.isPending ? <Spinner className="text-white" /> : <CornerDownLeft className="h-4 w-4" />}
            </button>
          </div>
        </form>
      </div>
    </Drawer>
  );
}

function Answer({ res, onPick }: { res: AskResponse; onPick: (id: string) => void }) {
  return (
    <div className="space-y-3">
      <div className="prose-sm-custom rounded-xl rounded-tl-sm border bg-raised/50 px-3.5 py-2.5">
        <Markdown remarkPlugins={[remarkGfm]}>{res.answer}</Markdown>
      </div>

      {res.missing && (
        <p className="flex items-start gap-2 rounded-lg border border-medium/35 bg-medium-soft
                      px-3 py-2 text-2xs leading-relaxed text-medium">
          <TriangleAlert className="mt-px h-3.5 w-3.5 shrink-0" />
          <span><strong>Not in the graph:</strong> {res.missing}</span>
        </p>
      )}

      {res.evidence.length > 0 && (
        <div>
          <p className="label mb-1.5">Evidence ({res.evidence.length})</p>
          <div className="flex flex-wrap gap-1.5">
            {res.evidence.map((e) => (
              <button key={e.node_id} onClick={() => onPick(e.node_id)}
                title={e.node_id}
                className="chip border-line bg-surface px-2 py-1 hover:border-accent hover:text-accent">
                <TierBadge tier={e.gxpTier} size="xs" showLabel={false} />
                <span className="max-w-[12rem] truncate">{e.name || nodeLabel(e.node_id)}</span>
                <span className="text-faint">{e.kind}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-faint">
        <span className={cn("font-semibold",
          res.generator === "gemini" ? "text-accent" : "text-muted")}>
          {res.generator === "gemini" ? res.model_id : "deterministic reasoner"}
        </span>
        <span>confidence {ratio(res.confidence)}</span>
        {res.templates_used.length > 0 && (
          <span className="mono">{res.templates_used.join(", ")}</span>
        )}
      </div>

      {res.queries.length > 0 && (
        <Collapse title={
          <span className="flex items-center gap-2">
            <Code2 className="h-3.5 w-3.5 text-muted" /> How it answered
          </span>
        }>
          <ul className="space-y-2.5">
            {res.queries.map((q, i) => (
              <li key={i}>
                <p className="flex items-center gap-2 text-2xs font-semibold">
                  <span className="mono text-accent">{q.template_id}</span>
                  <span className="text-faint">{q.row_count} rows</span>
                </p>
                <pre className="mono mt-1 overflow-x-auto whitespace-pre-wrap rounded-lg
                                border bg-raised/60 p-2 text-[0.6875rem] leading-relaxed text-muted">
                  {q.cypher.trim()}
                </pre>
                {Object.keys(q.params).length > 0 && (
                  <p className="mono mt-1 text-[0.6875rem] text-faint">
                    {JSON.stringify(q.params)}
                  </p>
                )}
              </li>
            ))}
          </ul>
          {res.reasoning && (
            <p className="mt-3 border-t pt-2.5 text-2xs leading-relaxed text-muted">
              {res.reasoning}
            </p>
          )}
        </Collapse>
      )}
    </div>
  );
}
