import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center py-24 text-center">
      <div className="text-5xl font-semibold tracking-tight text-ink-faint">404</div>
      <h1 className="mt-3 text-lg font-medium text-ink">Page not found</h1>
      <p className="mt-1 max-w-sm text-sm text-ink-faint">
        There's nothing at this address. Check the link, or head back to the dashboard.
      </p>
      <Link to="/" className="btn btn-primary mt-6">
        ← Back to dashboard
      </Link>
    </div>
  );
}
