import { useQuery } from "@tanstack/react-query";
import {
  CircleAlert,
  CircleCheck,
  Clock3,
  Download,
  FileJson,
  FileVideo,
  RefreshCw,
} from "lucide-react";

import { VideoTask, fetchTasks } from "../api/tasks";

const TASK_LIST_LIMIT = 50;

type StatusView = {
  label: string;
  className: string;
  Icon: typeof CircleCheck;
};

function statusView(status: string): StatusView {
  if (status === "succeeded") {
    return { label: "成功", className: "succeeded", Icon: CircleCheck };
  }
  if (status === "failed") {
    return { label: "失败", className: "failed", Icon: CircleAlert };
  }
  if (status === "running" || status === "rendering" || status === "processing") {
    return { label: "处理中", className: "running", Icon: Clock3 };
  }
  if (status === "pending" || status === "created") {
    return { label: "等待中", className: "pending", Icon: Clock3 };
  }
  return { label: status || "未知", className: "unknown", Icon: CircleAlert };
}

function taskStatusView(task: VideoTask): StatusView {
  if (task.output.kind === "partial_video") {
    return { label: "部分输出", className: "partial", Icon: CircleAlert };
  }
  if (task.status === "succeeded" && task.output.kind === "manifest") {
    return { label: "清单", className: "manifest", Icon: FileJson };
  }
  return statusView(task.status);
}

function optionText(task: VideoTask, key: string): string | null {
  const value = task.options[key];
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function downloadName(task: VideoTask, extension: string): string {
  const safeTitle = task.title.replace(/[\\/:*?"<>|]+/g, "_").trim();
  return `${safeTitle || task.id}${extension}`;
}

function canDownloadVideo(task: VideoTask): boolean {
  return task.output.kind === "video" && Boolean(task.output.download_url);
}

function canDownloadManifest(task: VideoTask): boolean {
  return task.output.kind === "manifest" && Boolean(task.output.download_url);
}

function outputSummary(task: VideoTask): string | null {
  if (task.output.failure_reason) {
    return task.output.failure_reason;
  }
  if (task.output.kind === "video") {
    return task.output.filename ? `输出文件：${task.output.filename}` : "视频已生成";
  }
  if (task.output.kind === "manifest") {
    return "当前任务仅生成输出清单。";
  }
  if (task.output.kind === "partial_video") {
    return "渲染未完成，已保留部分输出用于排查。";
  }
  if (task.status === "failed") {
    return "任务失败，暂无可下载输出。";
  }
  return null;
}

function TaskOutputCard({ task }: { task: VideoTask }) {
  const status = taskStatusView(task);
  const StatusIcon = status.Icon;
  const aspectRatio = optionText(task, "aspect_ratio");
  const resolution = optionText(task, "resolution");
  const subtitleEnabled = optionText(task, "subtitle_enabled");
  const materialCount = task.material_ids.length;
  const summary = outputSummary(task);

  return (
    <article aria-label={task.title} className="task-output-card">
      <div className="task-output-main">
        <div className="task-output-title-row">
          <h3>{task.title}</h3>
          <span className={`status-pill ${status.className}`}>
            <StatusIcon aria-hidden="true" size={16} />
            {status.label}
          </span>
        </div>
        <div className="task-meta" aria-label="任务信息">
          <span>{`创建 ${formatDate(task.created_at)}`}</span>
          <span>{`更新 ${formatDate(task.updated_at)}`}</span>
          <span>{`素材 ${materialCount} 个`}</span>
          {aspectRatio ? <span>{aspectRatio}</span> : null}
          {resolution ? <span>{resolution}</span> : null}
          {subtitleEnabled === "true" ? <span>字幕开启</span> : null}
          {task.output.render_status ? <span>{`渲染 ${task.output.render_status}`}</span> : null}
        </div>
        {summary ? <p className="task-output-summary">{summary}</p> : null}
      </div>
      <div className="task-output-actions">
        {canDownloadVideo(task) ? (
          <a className="primary-action" download={downloadName(task, ".mp4")} href={task.output.download_url}>
            <Download aria-hidden="true" size={18} />
            下载视频
          </a>
        ) : canDownloadManifest(task) ? (
          <a className="secondary-action" download={downloadName(task, ".json")} href={task.output.download_url}>
            <FileJson aria-hidden="true" size={18} />
            下载清单
          </a>
        ) : (
          <span className="disabled-action" aria-disabled="true">
            <FileVideo aria-hidden="true" size={18} />
            {task.status === "failed" || task.output.kind === "partial_video" ? "输出未完成" : "等待输出"}
          </span>
        )}
      </div>
    </article>
  );
}

export function TaskOutputList() {
  const tasks = useQuery({
    queryKey: ["video-tasks", TASK_LIST_LIMIT, 0],
    queryFn: () => fetchTasks({ limit: TASK_LIST_LIMIT, offset: 0 }),
  });

  return (
    <article className="panel task-output-panel" aria-label="任务与输出">
      <div className="panel-heading">
        <div>
          <h2>历史任务</h2>
          <span>查看最近生成的混剪任务，并下载已生成的视频输出。</span>
        </div>
        <button
          aria-label="刷新任务列表"
          disabled={tasks.isFetching}
          type="button"
          onClick={() => {
            void tasks.refetch();
          }}
        >
          <RefreshCw aria-hidden="true" size={18} />
          {tasks.isFetching ? "刷新中" : "刷新"}
        </button>
      </div>

      {tasks.isLoading ? (
        <div aria-live="polite" className="runtime-status" role="status">
          正在加载历史任务
        </div>
      ) : null}

      {tasks.isError ? (
        <div className="inline-error" role="alert">
          <span>任务列表加载失败</span>
          <button
            type="button"
            onClick={() => {
              void tasks.refetch();
            }}
          >
            <RefreshCw aria-hidden="true" size={16} />
            重试
          </button>
        </div>
      ) : null}

      {!tasks.isLoading && !tasks.isError && (tasks.data ?? []).length === 0 ? (
        <div className="empty-state">
          <strong>暂无历史任务</strong>
          <span>创建混剪任务后会出现在这里。</span>
        </div>
      ) : null}

      {(tasks.data ?? []).length > 0 ? (
        <div className="task-output-list">
          {(tasks.data ?? []).map((task) => (
            <TaskOutputCard key={task.id} task={task} />
          ))}
        </div>
      ) : null}
    </article>
  );
}
