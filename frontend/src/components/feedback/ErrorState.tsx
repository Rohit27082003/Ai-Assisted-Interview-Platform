import Button from '../ui/Button';

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export default function ErrorState({ title = 'Something went wrong', message, onRetry }: ErrorStateProps) {
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50 p-5">
      <h3 className="text-base font-semibold text-rose-800">{title}</h3>
      <p className="mt-1 text-sm text-rose-700">{message}</p>
      {onRetry ? (
        <div className="mt-3">
          <Button variant="danger" size="sm" onClick={onRetry}>
            Retry
          </Button>
        </div>
      ) : null}
    </div>
  );
}
