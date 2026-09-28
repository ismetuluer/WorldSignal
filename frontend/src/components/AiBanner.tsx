import { api, ApiError } from "../api/client";
import type { AiState } from "../api/types";
import { describeError, useI18n, type MessageKey } from "../i18n";
import { navigate } from "../router";
import { useAppState } from "../state";
import { Banner } from "./controls";
import { useToast } from "./Toasts";

const PROBLEM_STATES: AiState[] = ["unreachable", "model_missing", "no_model", "timeout", "gpu_busy"];

/** Explains why new reports are not being grouped into stories. Renders nothing when clustering works. */
export function StoryBanner() {
  const { t } = useI18n();
  const { status } = useAppState();
  const st = status?.stories;
  if (!st || (st.state !== "unreachable" && st.state !== "model_missing")) return null;
  // Ollama down is already explained by the AI banner when AI is on; avoid saying it twice.
  if (st.state === "unreachable" && status?.ai.state === "unreachable") return null;
  return (
    <Banner
      kind="error"
      icon="alert"
      title={t(`stories.banner.${st.state}.title`)}
      body={t(`stories.banner.${st.state}.body`, { model: st.model ?? "" })}
      action={
        st.state === "model_missing" ? (
          <button className="btn btn-sm" onClick={() => navigate("settings")}>{t("ai.openSettings")}</button>
        ) : undefined
      }
    />
  );
}

/** Explains why Turkish summaries are missing and offers the fix. Renders nothing when AI works. */
export function AiBanner() {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { status, refreshStatus } = useAppState();
  const ai = status?.ai;
  if (!ai || !PROBLEM_STATES.includes(ai.state)) return null;
  const state = ai.state as "unreachable" | "model_missing" | "no_model" | "timeout" | "gpu_busy";

  const retry = async () => {
    try {
      await api.retryAi();
      refreshStatus();
    } catch (e) {
      toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");
    }
  };

  const needsSettings = state === "model_missing" || state === "no_model" || state === "gpu_busy";
  const model = state === "gpu_busy" ? (ai.busy_with ?? "") : (ai.model ?? "");
  return (
    <Banner
      kind={state === "unreachable" || state === "model_missing" ? "error" : "warning"}
      icon="alert"
      title={t(`ai.banner.${state}.title` as MessageKey)}
      body={t(`ai.banner.${state}.body` as MessageKey, { model })}
      action={
        needsSettings ? (
          <button className="btn btn-sm" onClick={() => navigate("settings")}>{t("ai.openSettings")}</button>
        ) : (
          <button className="btn btn-sm" onClick={() => void retry()}>{t("ai.retry")}</button>
        )
      }
    />
  );
}
