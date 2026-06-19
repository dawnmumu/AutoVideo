export interface VideoTask {
  id: string;
  title: string;
  status: string;
  material_ids: string[];
  options: Record<string, unknown>;
  output: {
    download_url: string;
    filename?: string;
    media_type?: string;
    kind?: "video" | "manifest" | "partial_video" | "file";
    render_status?: string;
    failure_reason?: string;
  };
  created_at: string;
  updated_at: string;
}

export interface FetchTasksInput {
  limit?: number;
  offset?: number;
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`HTTP_${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchTasks({
  limit = 50,
  offset = 0,
}: FetchTasksInput = {}): Promise<VideoTask[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return readJson(await fetch(`/api/tasks?${params.toString()}`));
}

export async function deleteTask(taskId: string): Promise<void> {
  const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`HTTP_${response.status}`);
  }
}
