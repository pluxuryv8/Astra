type IdleScreenProps = {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  status?: string | null;
};

export default function IdleScreen({ value, disabled, onChange, onSubmit, status }: IdleScreenProps) {
  return (
    <section className="idle">
      <div className="idle-brand">ASTRA</div>
      <div className="idle-tagline">Чем займёмся?</div>
      <div className="idle-input-wrap">
        <input
          className="idle-input"
          type="text"
          placeholder="Например: собери мои «Мне нравится» и сделай плейлист"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onSubmit();
            }
          }}
        />
        <button className="idle-send" title="Отправить" onClick={onSubmit} disabled={disabled || !value.trim()}>
          →
        </button>
      </div>
      {status ? <div className="status-line">{status}</div> : null}
    </section>
  );
}
