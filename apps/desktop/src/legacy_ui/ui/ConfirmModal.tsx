import type { Approval } from "../types";

type ConfirmModalProps = {
  approval: Approval;
  onApprove: () => void;
  onReject: () => void;
  onDismiss: () => void;
};

function formatActionPreview(action: Record<string, unknown>): string {
  const type = typeof action.type === "string" ? action.type : typeof action.action === "string" ? action.action : "действие";
  const text = typeof action.text === "string" ? action.text : null;
  const key = typeof action.key === "string" ? action.key : null;
  const ms = typeof action.ms === "number" ? action.ms : null;
  const parts = [type];
  if (text) parts.push(`"${text.slice(0, 80)}${text.length > 80 ? "…" : ""}"`);
  if (key) parts.push(key);
  if (ms) parts.push(`${ms}мс`);
  return parts.join(" ");
}

export default function ConfirmModal({ approval, onApprove, onReject, onDismiss }: ConfirmModalProps) {
  const proposed = approval.proposed_actions || [];
  const preview = proposed.slice(0, 5);
  const hiddenCount = Math.max(0, proposed.length - preview.length);

  return (
    <div className="modal-backdrop" onClick={onDismiss} role="presentation">
      <div className="modal-card" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="modal-head">
          <div className="modal-kicker">Требуется подтверждение</div>
          <button className="icon-button" onClick={onDismiss} title="Скрыть (Esc)">
            ✕
          </button>
        </div>

        <div className="modal-title">{approval.title}</div>
        {approval.description ? <div className="modal-text">{approval.description}</div> : null}

        {preview.length ? (
          <div className="modal-actions-preview">
            <div className="section-title">Что будет сделано</div>
            <ul className="action-list">
              {preview.map((action, idx) => (
                <li key={idx} className="action-item">
                  {formatActionPreview(action)}
                </li>
              ))}
              {hiddenCount ? <li className="action-more">…и ещё {hiddenCount}</li> : null}
            </ul>
          </div>
        ) : null}

        <div className="modal-buttons">
          <button className="btn primary" onClick={onApprove}>
            Разрешить
          </button>
          <button className="btn ghost" onClick={onReject}>
            Отказать
          </button>
          <button className="text-button" onClick={onDismiss}>
            Скрыть
          </button>
        </div>
      </div>
    </div>
  );
}

