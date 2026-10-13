"use client";

/**
 * Client state (zustand).
 *
 * The acting user matters beyond preference: their name is recorded on every
 * approval, override and audit row (PRD §18 - no login screen, a header
 * switcher instead), so it is persisted and restored across reloads.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Tier, User } from "./api";

interface AppState {
  currentUser: User | null;
  setCurrentUser: (u: User | null) => void;

  theme: "light" | "dark";
  setTheme: (t: "light" | "dark") => void;
  toggleTheme: () => void;

  /** Node selected in the twin/heatmap graph, shown in the side panel. */
  selectedNode: string | null;
  selectNode: (id: string | null) => void;

  /** Tier filter shared by the twin and heatmap screens. */
  tierFilter: Tier | null;
  setTierFilter: (t: Tier | null) => void;

  chatOpen: boolean;
  setChatOpen: (open: boolean) => void;
}

export const useApp = create<AppState>()(
  persist(
    (set, get) => ({
      currentUser: { id: "lead-advisor", name: "Modernization Lead", role: "Pharma IT Advisor" },
      setCurrentUser: (currentUser) => set({ currentUser }),

      theme: "light",
      setTheme: (theme) => {
        set({ theme });
        if (typeof document !== "undefined") {
          document.documentElement.dataset.theme = theme;
        }
      },
      toggleTheme: () => get().setTheme(get().theme === "dark" ? "light" : "dark"),

      selectedNode: null,
      selectNode: (selectedNode) => set({ selectedNode }),

      tierFilter: null,
      setTierFilter: (tierFilter) => set({ tierFilter }),

      chatOpen: false,
      setChatOpen: (chatOpen) => set({ chatOpen }),
    }),
    {
      name: "modernrx",
      partialize: (s) => ({ currentUser: s.currentUser, theme: s.theme }),
    },
  ),
);
