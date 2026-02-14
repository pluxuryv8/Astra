import { useCallback, useMemo, useState } from "react";
import { Loader2, Play, Copy } from "lucide-react";
import Button from "../shared/ui/Button";
import { apiBase, cancelRun, createProject, createRun, getSnapshot, listProjects, startRun } from "../shared/api/client";

type SmokeStatus = "idle" | "running" | "pass" | "fail";

type SmokeState = {
  status: SmokeStatus;
  message: string;
  runId?: string | null;
  approvalSeen?: boolean;
  hashChanged?: boolean | null;
};

const BRIDGE_PORT =
  (import.meta.env as Record<string, string | undefined>).VITE_ASTRA_DESKTOP_BRIDGE_PORT ||
  (import.meta.env as Record<string, string | undefined>).VITE_DESKTOP_BRIDGE_PORT ||
  "43124";

const BRIDGE_BASE = `http://127.0.0.1:${BRIDGE_PORT}`;
const SMOKE_QUERY =
  "S_SMOKE_1: Проверь локальный smoke-тест. Сделай наблюдение, безопасную прокрутку и остановись перед удалением test.txt.";

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export default function SmokePanel() {
  const [state, setState] = useState<SmokeState>({
    status: "idle",
    message: "Готов к запуску."
  });

  const reportText = useMemo(() => {
    const lines = [
      "S_SMOKE_1",
      `Статус: ${state.status === "pass" ? "PASS" : state.status === "fail" ? "FAIL" : "—"}`,
      `Причина: ${state.message}`,
      `Run: ${state.runId || "—"}`,
      `Approval: ${state.approvalSeen ? "запрошено" : "нет"}`,
      `Hash changed: ${state.hashChanged == null ? "—" : state.hashChanged ? "да" : "нет"}`,
      `API: ${apiBase()}`,
      `Bridge: ${BRIDGE_BASE}`
    ];
    return lines.join("\n");
  }, [state]);

  const runSmoke = useCallback(async () => {
    if (state.status === "running") return;
    setState({ status: "running", message: "Проверяю bridge…" });

    try {
      const bridgeRes = await fetch(`${BRIDGE_BASE}/autopilot/permissions`);
      if (!bridgeRes.ok) {
        setState({
          status: "fail",
          message: "Bridge недоступен. Запусти astra dev и проверь порт.",
          runId: null
        });
        return;
      }
    } catch {
      setState({
        status: "fail",
        message: "Bridge недоступен. Запусти astra dev и проверь порт.",
        runId: null
      });
      return;
    }

    setState({ status: "running", message: "Готовлю проект…", runId: null });
    let projectId: string | null = null;
    try {
      const projects = await listProjects();
      if (projects.length) {
        projectId = projects[0].id;
      } else {
        const created = await createProject({ name: "Smoke", tags: ["smoke"], settings: {} });
        projectId = created.id;
      }
    } catch (err) {
      setState({ status: "fail", message: "Не удалось загрузить проекты.", runId: null });
      return;
    }

    if (!projectId) {
      setState({ status: "fail", message: "Проект не найден.", runId: null });
      return;
    }

    setState({ status: "running", message: "Создаю запуск…", runId: null });
    let runId: string | null = null;
    try {
      const response = await createRun(projectId, { query_text: SMOKE_QUERY, mode: "execute_confirm" });
      runId = response.run?.id ?? null;
    } catch {
      setState({ status: "fail", message: "Не удалось создать запуск.", runId: null });
      return;
    }

    if (!runId) {
      setState({ status: "fail", message: "run_id отсутствует.", runId: null });
      return;
    }

    setState({ status: "running", message: "Запускаю сценарий…", runId });
    try {
      await startRun(runId);
    } catch {
      setState({ status: "fail", message: "Не удалось запустить сценарий.", runId });
      return;
    }

    const startedAt = Date.now();
    let approvalSeen = false;
    let hashChanged: boolean | null = null;
    let lastStatus = "running";

    while (Date.now() - startedAt < 180_000) {
      try {
        const snapshot = await getSnapshot(runId);
        lastStatus = snapshot.run?.status || "unknown";
        const events = snapshot.last_events || [];
        const eventTypes = new Set(events.map((evt) => evt.type));
        if (eventTypes.has("approval_requested") || eventTypes.has("step_paused_for_approval")) {
          approvalSeen = true;
        }
        const facts = snapshot.facts || [];
        const hashFact = facts.find((fact) => fact.key === "smoke.hash_changed");
        if (hashFact && typeof hashFact.value === "boolean") {
          hashChanged = hashFact.value;
        }
        if (approvalSeen) break;
        if (["done", "failed", "canceled"].includes(lastStatus)) break;
      } catch {
        // ignore single poll error
      }
      await sleep(1500);
    }

    if (approvalSeen) {
      try {
        await cancelRun(runId);
      } catch {
        // ignore
      }
      setState({
        status: "pass",
        message: "Запрошено подтверждение. Smoke остановлен до опасного шага.",
        runId,
        approvalSeen,
        hashChanged
      });
      return;
    }

    setState({
      status: "fail",
      message: `Smoke не дошёл до approval (status: ${lastStatus}).`,
      runId,
      approvalSeen,
      hashChanged
    });
  }, [state.status]);

  return (
    <div className="settings-card smoke-card">
      <div className="settings-label">Smoke-тест</div>
      <div className="smoke-status">
        <span className={`smoke-pill ${state.status}`}>{state.status === "running" ? "Выполняется" : state.status === "pass" ? "PASS" : state.status === "fail" ? "FAIL" : "Готов"}</span>
        <span className="smoke-message">{state.message}</span>
      </div>
      <div className="smoke-meta">
        <span>Run: {state.runId || "—"}</span>
        <span>Approval: {state.approvalSeen ? "запрошено" : "нет"}</span>
        <span>Hash changed: {state.hashChanged == null ? "—" : state.hashChanged ? "да" : "нет"}</span>
      </div>
      <div className="smoke-actions">
        <Button type="button" variant="primary" onClick={() => void runSmoke()} disabled={state.status === "running"}>
          {state.status === "running" ? (
            <>
              <Loader2 size={16} className="spin" />
              Выполняется…
            </>
          ) : (
            <>
              <Play size={16} />
              Запустить smoke
            </>
          )}
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => void navigator.clipboard?.writeText(reportText)}
          disabled={state.status === "running"}
        >
          <Copy size={16} />
          Скопировать отчёт
        </Button>
      </div>
      <div className="smoke-hint">
        Для полного отчёта используй <code>./scripts/smoke.sh</code> или <code>astra smoke</code>.
      </div>
    </div>
  );
}
