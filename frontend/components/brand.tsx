export function Mark({ small = false }: { small?: boolean }) {
  return (
    <span className={`brand-mark ${small ? "small" : ""}`} aria-hidden="true">
      <span />
      <i />
    </span>
  );
}

export function Brand() {
  return (
    <div className="brand">
      <Mark />
      <div>
        <span className="wordmark">THRYV</span>
        <span className="tagline">Your Personal AI</span>
      </div>
    </div>
  );
}
