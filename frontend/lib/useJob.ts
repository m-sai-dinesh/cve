"use client";

import { useQueryClient } from "@tanstack/react-query";
import React from "react";
import { Api, openJobSocket, type JobEvent } from "./api";

export interface JobState {
  jobId: string | null;
  status: "idle" | "queued" | "running" | "succeeded" | "failed";
  progress: number;
  step: string;
  error: string;
  events: JobEvent[];
  /** Council debate messages, in arrival order. */
  messages: JobEvent[];
  result: Record<string, unknown>;
}

const INITIAL: JobState = {
  jobId: null, status: "idle", progress: 0, step: "",
  error: "", events: [], messages: [], result: {},
};

/**
 * Subscribe to a background job and expose its live state.
 *
 * `invalidate` lists react-query keys to refetch when the job succeeds, so a
 * finished analysis immediately repaints every screen that depends on it.
 */
export function useJob(invalidate: string[][] = []) {
  const qc = useQueryClient();
  const [state, setState] = React.useState<JobState>(INITIAL);
  const cleanup = React.useRef<(() => void) | null>(null);
  const invalidateRef = React.useRef(invalidate);
  invalidateRef.current = invalidate;

  const reset = React.useCallback(() => {
    cleanup.current?.();
    cleanup.current = null;
    setState(INITIAL);
  }, []);

  const attach = React.useCallback(
    (jobId: string) => {
      cleanup.current?.();
      setState({ ...INITIAL, jobId, status: "queued" });

      cleanup.current = openJobSocket(jobId, (e) => {
        setState((prev) => {
          const next = { ...prev };
          switch (e.type) {
            case "snapshot":
              next.status = (e.status as JobState["status"]) ?? prev.status;
              next.progress = (e.progress as number) ?? prev.progress;
              next.step = (e.step as string) ?? prev.step;
              if (Array.isArray(e.events)) {
                const incoming = e.events as JobEvent[];
                next.events = incoming;
                next.messages = incoming.filter((x) => x.type === "council_message");
              }
              break;
            case "progress":
              next.progress = (e.progress as number) ?? prev.progress;
              next.step = (e.step as string) ?? prev.step;
              break;
            case "heartbeat":
              next.status = (e.status as JobState["status"]) ?? prev.status;
              next.progress = (e.progress as number) ?? prev.progress;
              next.step = (e.step as string) ?? prev.step;
              break;
            case "status":
              next.status = (e.status as JobState["status"]) ?? prev.status;
              next.error = (e.error as string) ?? "";
              if (e.result) next.result = e.result as Record<string, unknown>;
              if (next.status === "succeeded") next.progress = 1;
              break;
            case "council_message":
              next.messages = [...prev.messages, e];
              next.events = [...prev.events, e];
              break;
            default:
              next.events = [...prev.events, e];
          }
          return next;
        });

        if (e.type === "status" && (e.status === "succeeded" || e.status === "failed")) {
          // Pull the authoritative record: the socket carries a summary only.
          Api.job(jobId)
            .then((job) =>
              setState((prev) => ({
                ...prev,
                status: job.status as JobState["status"],
                error: job.error,
                result: job.result,
                progress: job.status === "succeeded" ? 1 : prev.progress,
              })),
            )
            .catch(() => undefined);
          if (e.status === "succeeded") {
            for (const key of invalidateRef.current) {
              qc.invalidateQueries({ queryKey: key });
            }
          }
        }
      });
    },
    [qc],
  );

  React.useEffect(() => () => cleanup.current?.(), []);

  const busy = state.status === "queued" || state.status === "running";
  return { ...state, busy, attach, reset };
}
