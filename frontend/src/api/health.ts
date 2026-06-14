export interface RuntimeCheck {
  name: string;
  ok: boolean;
  required: boolean;
  message: string;
}

export interface HealthPayload {
  app: string;
  status: "ok" | "degraded";
  environment: string;
  data_dir: string;
  checks: Record<string, RuntimeCheck>;
}

export async function fetchHealth(): Promise<HealthPayload> {
  const response = await fetch("/api/health");
  if (!response.ok) {
    throw new Error(`health request failed: ${response.status}`);
  }
  return response.json() as Promise<HealthPayload>;
}
