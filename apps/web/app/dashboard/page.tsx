const monolithUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8001';

export default function DashboardPage() {
  return (
    <iframe
      className="monolith-frame"
      src={`${monolithUrl}/dashboard`}
      title="SignalSentry dashboard"
    />
  );
}


