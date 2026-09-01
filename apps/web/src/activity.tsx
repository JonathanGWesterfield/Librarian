import { useCallback, useEffect, useRef, useState } from "react";
import {
  getIngestionStatus,
  refreshSearchIndex,
  runIngestion,
  type IngestionRunResponse,
  type IngestionStageStatus,
  type IngestionStatusResponse,
  type SearchIndexResponse,
} from "./api";

const STATUS_POLL_INTERVAL_MS = 5_000;

type ActivityPhase = "idle" | "ingesting" | "reprocessing" | "indexing" | "ready" | "ingestion-error" | "index-error";

type ActivitySectionProps = {
  onLibraryUpdated: () => Promise<void>;
};

export function ActivitySection({ onLibraryUpdated }: ActivitySectionProps) {
  const [status, setStatus] = useState<IngestionStatusResponse | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [phase, setPhase] = useState<ActivityPhase>("idle");
  const [operationBusy, setOperationBusy] = useState(false);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [ingestionResult, setIngestionResult] = useState<IngestionRunResponse | null>(null);
  const [indexResult, setIndexResult] = useState<SearchIndexResponse | null>(null);
  const [indexReset, setIndexReset] = useState(false);
  const mounted = useRef(true);
  const statusRequest = useRef<Promise<void> | null>(null);
  const operationGeneration = useRef(0);
  const operationActive = useRef(false);

  const loadStatus = useCallback((): Promise<void> => {
    if (statusRequest.current) return statusRequest.current;

    const request = (async () => {
      if (mounted.current) {
        setStatusLoading(true);
        setStatusError(null);
      }
      try {
        const response = await getIngestionStatus();
        if (mounted.current) setStatus(response);
      } catch (error) {
        if (mounted.current) setStatusError(messageFor(error, "Unable to load ingestion status."));
      } finally {
        if (mounted.current) setStatusLoading(false);
      }
    })();

    statusRequest.current = request;
    void request.finally(() => {
      if (statusRequest.current === request) statusRequest.current = null;
    });
    return request;
  }, []);

  useEffect(() => {
    mounted.current = true;
    void loadStatus();
    return () => {
      mounted.current = false;
      operationGeneration.current += 1;
    };
  }, [loadStatus]);

  const workflowActive = phase === "ingesting" || phase === "reprocessing" || phase === "indexing";
  const serverActive = status ? stages(status).some(([, stage]) => stage.running_books > 0 || stage.active_jobs.length > 0) : false;

  useEffect(() => {
    if (!workflowActive && !serverActive) return;
    const timer = window.setTimeout(() => void loadStatus(), STATUS_POLL_INTERVAL_MS);
    return () => window.clearTimeout(timer);
  }, [loadStatus, serverActive, status, statusError, workflowActive]);

  async function refreshAfterIndex() {
    if (statusRequest.current) await statusRequest.current;
    await Promise.allSettled([onLibraryUpdated(), loadStatus()]);
  }

  async function indexProcessedBooks(generation: number, reset = false) {
    setIndexReset(reset);
    setPhase("indexing");
    try {
      const response = await refreshSearchIndex({ reset });
      if (!isCurrent(generation)) return;
      setIndexResult(response);
      setPhase("ready");
      await refreshAfterIndex();
    } catch (error) {
      if (!isCurrent(generation)) return;
      setOperationError(messageFor(error, "Unable to refresh the search index."));
      setPhase("index-error");
    }
  }

  async function updateLibrary(reprocessUnchanged = false) {
    if (operationActive.current) return;
    operationActive.current = true;
    setOperationBusy(true);
    const generation = ++operationGeneration.current;
    setPhase(reprocessUnchanged ? "reprocessing" : "ingesting");
    setOperationError(null);
    setIngestionResult(null);
    setIndexResult(null);
    setIndexReset(reprocessUnchanged);
    try {
      const response = await runIngestion({ reprocessUnchanged });
      if (!isCurrent(generation)) return;
      setIngestionResult(response);
      await indexProcessedBooks(generation, reprocessUnchanged);
    } catch (error) {
      if (!isCurrent(generation)) return;
      setOperationError(messageFor(error, "Unable to update the library."));
      setPhase("ingestion-error");
    } finally {
      if (generation === operationGeneration.current) {
        operationActive.current = false;
        if (mounted.current) setOperationBusy(false);
      }
    }
  }

  async function retrySearchIndex() {
    if (operationActive.current) return;
    operationActive.current = true;
    setOperationBusy(true);
    const generation = ++operationGeneration.current;
    setOperationError(null);
    setIndexResult(null);
    try {
      await indexProcessedBooks(generation, indexReset);
    } finally {
      if (generation === operationGeneration.current) {
        operationActive.current = false;
        if (mounted.current) setOperationBusy(false);
      }
    }
  }

  function isCurrent(generation: number) {
    return mounted.current && generation === operationGeneration.current;
  }

  return <section id="activity" className="activity-section" aria-labelledby="activity-heading">
    <div className="section-heading">
      <div><p className="eyebrow">Library activity</p><h2 id="activity-heading">Keep every passage current.</h2></div>
      <p>Process newly added or changed EPUBs, then refresh search without resetting existing data.</p>
    </div>

    <div className="activity-panel">
      <div className="activity-actions">
        <div>
          <h3>Processing status</h3>
          <p>Chunking, summaries, and metadata are tracked independently.</p>
        </div>
        <div className="activity-action-buttons">
          <button type="button" onClick={() => void updateLibrary()} disabled={operationBusy}>
            {phase === "ingesting" ? "Processing books…" : phase === "indexing" ? "Refreshing search…" : "Update library"}
          </button>
          <button type="button" className="activity-secondary-action" onClick={() => void updateLibrary(true)} disabled={operationBusy}>
            {phase === "reprocessing" ? "Reprocessing books…" : "Reprocess existing books"}
          </button>
        </div>
      </div>

      {statusLoading && !status && <p className="activity-state" role="status">Loading processing status…</p>}
      {statusError && <div className="activity-state activity-error" role="alert"><p>{statusError}</p><button type="button" onClick={() => void loadStatus()} disabled={statusLoading}>Retry status</button></div>}
      {status && <div className="stage-grid">{stages(status).map(([label, stage]) => <StageCard key={label} label={label} stage={stage} />)}</div>}

      <div className="activity-result" aria-live="polite">
        {phase === "ingesting" && <p role="status">Checking for new or changed books and generating search embeddings…</p>}
        {phase === "reprocessing" && <p role="status">Reprocessing every existing EPUB with current rules and regenerating search embeddings. This can take as long as the original library import.</p>}
        {phase === "indexing" && <p role="status">Processing finished. Refreshing the search index; new books are not search-ready yet.</p>}
        {ingestionResult && <p>{ingestionSummary(ingestionResult)}</p>}
        {ingestionResult && ingestionResult.failed > 0 && <p className="activity-warning" role="alert">{ingestionResult.failed} {plural(ingestionResult.failed, "book")} failed during ingestion. Successfully processed books were still sent to the search index.</p>}
        {phase === "ready" && indexResult && <p className="activity-success" role="status">Search ready. {indexResult.documents_seen} documents seen; {indexResult.documents_indexed} documents indexed.</p>}
        {phase === "ingestion-error" && operationError && <p className="activity-error" role="alert">{operationError} Search indexing was not started.</p>}
        {phase === "index-error" && operationError && <div className="activity-error" role="alert"><p>{operationError} New books may not be searchable.</p><button type="button" onClick={() => void retrySearchIndex()} disabled={operationBusy}>Retry search index</button></div>}
      </div>
    </div>
  </section>;
}

function StageCard({ label, stage }: { label: string; stage: IngestionStageStatus }) {
  const percent = Math.max(0, Math.min(100, stage.percent_complete));
  const activeMessage = stage.active_jobs.find((job) => job.message)?.message;
  return <article className="stage-card">
    <div className="stage-title"><h3>{label}</h3><span>{Math.round(percent)}%</span></div>
    <progress aria-label={`${label} progress`} max="100" value={percent}>{Math.round(percent)}%</progress>
    <p>{stage.completed_books} of {stage.total_books} complete</p>
    <dl><div><dt>Pending</dt><dd>{stage.pending_books}</dd></div><div><dt>Running</dt><dd>{stage.running_books}</dd></div><div><dt>Failed</dt><dd>{stage.failed_books}</dd></div></dl>
    {activeMessage && <p className="active-job" role="status">{activeMessage}</p>}
  </article>;
}

function stages(status: IngestionStatusResponse): [string, IngestionStageStatus][] {
  return [["Chunking", status.chunking], ["Summarizing", status.summarizing], ["Tagging", status.tagging]];
}

function ingestionSummary(result: IngestionRunResponse): string {
  return `Found ${result.found} ${plural(result.found, "book")}: ${result.parsed} processed, ${result.skipped_unchanged} unchanged, ${result.skipped_duplicates} duplicate, ${result.failed} failed.`;
}

function plural(count: number, singular: string): string {
  return count === 1 ? singular : `${singular}s`;
}

function messageFor(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
