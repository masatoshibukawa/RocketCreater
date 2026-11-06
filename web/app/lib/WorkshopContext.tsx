"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { chooseCrewTask, IDLE_TASK, type CrewTask } from "./workshopActivity";

type Report = (source: string, task: CrewTask | null) => void;
const WorkshopContext = createContext({ task: IDLE_TASK, visible: true, paused: false, reduced: false,
  motionEnabled: true, setVisible: (_: boolean) => {}, setPaused: (_: boolean) => {}, report: ((_source, _task) => {}) as Report });
const PREFS = "rocketwright.crew.v1";

export function WorkshopProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<Record<string, { task: CrewTask; order: number }>>({});
  const serial = useRef(0);
  const [visible, setVisible] = useState(true);
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem(PREFS) ?? "null");
      if (saved && typeof saved === "object") {
        if ("visible" in saved && typeof saved.visible === "boolean") setVisible(saved.visible);
        if ("paused" in saved && typeof saved.paused === "boolean") setPaused(saved.paused);
      }
    } catch { /* Storage can be disabled without disabling the workshop. */ }
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    update(); setLoaded(true); media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (loaded) try { localStorage.setItem(PREFS, JSON.stringify({ visible, paused })); } catch { /* Optional preference. */ }
  }, [loaded, visible, paused]);
  const report = useCallback<Report>((source, task) => {
    const order = ++serial.current;
    setTasks(previous => {
      if (task === null) {
        if (!(source in previous)) return previous;
        const next = { ...previous }; delete next[source]; return next;
      }
      const old = previous[source]?.task;
      if (old?.id === task.id && old.status === task.status && old.label === task.label) return previous;
      return { ...previous, [source]: { task, order } };
    });
  }, []);
  const task = useMemo(() => chooseCrewTask(Object.entries(tasks).map(([source, value]) => ({ source, ...value }))), [tasks]);
  const value = useMemo(() => ({ task, visible, paused, reduced, motionEnabled: loaded && !paused && !reduced,
    setVisible, setPaused, report }), [task, visible, paused, reduced, loaded, report]);
  return <WorkshopContext.Provider value={value}>{children}</WorkshopContext.Provider>;
}

export const useWorkshop = () => useContext(WorkshopContext);

export function useCrewTask(source: string, task: CrewTask) {
  const { report } = useWorkshop();
  const { id, status, label } = task;
  useEffect(() => { report(source, { id, status, label }); }, [source, id, status, label, report]);
  useEffect(() => () => report(source, null), [source, report]);
}
