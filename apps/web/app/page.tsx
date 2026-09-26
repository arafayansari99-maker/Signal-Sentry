const monolithUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8001';

export default function Page() {
  return (
    <iframe
      className="monolith-frame"
      src={`${monolithUrl}/site/landing`}
      title="SignalSentry landing page"
    />
  );
}
