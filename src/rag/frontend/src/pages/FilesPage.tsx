import { useEffect } from "react";
import { Link } from "react-router-dom";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/States";
import { formatBytes, formatDateTime, formatPageCount } from "../shared/format";
import { useFilesStore } from "../stores/filesStore";
import type { FileCard } from "../types";

export function FilesPage() {
  const items = useFilesStore((state) => state.items);
  const phase = useFilesStore((state) => state.phase);
  const errorMessage = useFilesStore((state) => state.errorMessage);
  const total = useFilesStore((state) => state.total);
  const offset = useFilesStore((state) => state.offset);
  const limit = useFilesStore((state) => state.limit);
  const load = useFilesStore((state) => state.load);
  const setOffset = useFilesStore((state) => state.setOffset);

  useEffect(() => {
    document.title = "Files · Documents · Filenkov";
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(offset + items.length, total);

  return (
    <section className="view-in screen">
      <div>
        <div className="page-head">
          <div>
            <p className="kicker">Documents</p>
            <h1>Files</h1>
          </div>
        </div>
        <p className="muted page-lead">Indexed files that are ready for questions.</p>
      </div>

      {phase === "loading" ? <LoadingBlock label="Loading list…" /> : null}
      {phase === "error" && errorMessage ? (
        <ErrorBlock text={errorMessage} onRetry={() => void load()} />
      ) : null}
      {phase === "ready" && items.length === 0 ? (
        <EmptyBlock title="No indexed files yet" text="A file appears here after it has been vectorized." />
      ) : null}

      {items.length > 0 ? (
        <div className="table-wrap table-dense">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Size</th>
                <th>Pages</th>
                <th>Indexed</th>
              </tr>
            </thead>
            <tbody>
              {items.map((file) => (
                <FileRow key={file.file_id} file={file} />
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {total > limit ? (
        <div className="pager meta">
          <p className="muted">
            Showing {rangeStart}–{rangeEnd} of {total}
          </p>
          <div className="actions">
            <button
              type="button"
              className="btn btn-ghost"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              Back
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={offset + limit >= total}
              onClick={() => setOffset(offset + limit)}
            >
              Next
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function FileRow({ file }: { file: FileCard }) {
  return (
    <tr>
      <td className="cell-wrap" data-label="Name">
        <Link className="link" to={`/files/${file.file_id}?page=1`}>
          {file.file_name}
        </Link>
      </td>
      <td className="nums muted" data-label="Size">
        {formatBytes(file.file_size)}
      </td>
      <td className="nums" data-label="Pages">
        {formatPageCount(file.page_count)}
      </td>
      <td className="muted" data-label="Indexed">
        {formatDateTime(file.created_at)}
      </td>
    </tr>
  );
}
