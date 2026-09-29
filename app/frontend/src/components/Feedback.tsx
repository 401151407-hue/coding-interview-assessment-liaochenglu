/**
 * Accessible feedback channels.
 *
 * Two live regions are kept mounted for the whole lifetime of the page: assistive
 * technology only reliably announces changes inside a region that already existed
 * when the message arrived. Success/info go to a polite `status` region, failures
 * to an assertive `alert`.
 */

export type FeedbackTone = "success" | "error" | "info";

export interface FeedbackMessage {
  tone: FeedbackTone;
  text: string;
}

export function Feedback({ message }: { message: FeedbackMessage | null }) {
  const isError = message !== null && message.tone === "error";
  const statusText = message !== null && !isError ? message.text : "";
  const errorText = isError ? message.text : "";

  return (
    <div className="feedback">
      <p
        className={`feedback__line feedback__line--success`}
        role="status"
        aria-atomic="true"
      >
        {statusText}
      </p>
      <p className="feedback__line feedback__line--error" role="alert" aria-atomic="true">
        {errorText}
      </p>
    </div>
  );
}
