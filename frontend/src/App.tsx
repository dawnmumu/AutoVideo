import { useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import {
  Captions,
  Clapperboard,
  FolderOpen,
  Music,
  Settings,
  Sparkles,
  SquarePlay,
  Volume2,
} from "lucide-react";
import { useState } from "react";

import { fetchHealth } from "./api/health";
import { OnlineRemixWorkbench } from "./components/OnlineRemixWorkbench";
import { SubtitleTemplateWorkbench } from "./components/SubtitleTemplateWorkbench";

type ActiveSection = "remix" | "subtitles";
type BaseNavItem = {
  label: string;
  shortLabel: string;
  icon: LucideIcon;
};
type NavItem =
  | (BaseNavItem & { id: ActiveSection; enabled: true })
  | (BaseNavItem & { id: string; enabled: false });

const navItems: NavItem[] = [
  { id: "remix", label: "混剪工作台", shortLabel: "混剪", icon: Clapperboard, enabled: true },
  { id: "materials", label: "素材库", shortLabel: "素材", icon: FolderOpen, enabled: false },
  { id: "subtitles", label: "字幕模板", shortLabel: "字幕", icon: Captions, enabled: true },
  { id: "bgm", label: "BGM 管理", shortLabel: "BGM", icon: Music, enabled: false },
  { id: "voices", label: "音色中心", shortLabel: "音色", icon: Volume2, enabled: false },
  { id: "extract", label: "功能提取处理", shortLabel: "提取", icon: Sparkles, enabled: false },
  { id: "tasks", label: "任务与输出", shortLabel: "任务", icon: SquarePlay, enabled: false },
  { id: "settings", label: "系统设置", shortLabel: "设置", icon: Settings, enabled: false },
];

function RuntimeStatus() {
  const query = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  if (query.isLoading) {
    return (
      <div aria-live="polite" className="runtime-status" role="status">
        正在检查运行环境
      </div>
    );
  }

  if (query.isError || !query.data) {
    return (
      <div aria-live="polite" className="runtime-status degraded" role="status">
        无法读取运行状态
      </div>
    );
  }

  const checks = Object.values(query.data.checks);
  const statusText = query.data.status === "ok" ? "运行环境正常" : "运行环境需检查";

  return (
    <aside className="panel status-panel" aria-label="运行检查">
      <div aria-live="polite" className={`runtime-status ${query.data.status}`} role="status">
        {statusText}
      </div>
      <h2>运行检查</h2>
      <dl>
        {checks.map((check) => (
          <div key={check.name}>
            <dt>{check.name}</dt>
            <dd>{check.message}</dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}

export default function App() {
  const [activeSection, setActiveSection] = useState<ActiveSection>("remix");

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand">
          <span className="brand-mark">AV</span>
          <div>
            <strong>AutoVideo</strong>
            <small>视频混剪工作台</small>
          </div>
        </div>
        <nav className="nav-list">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = item.id === activeSection;
            return item.enabled ? (
              <a
                aria-current={isActive ? "page" : undefined}
                className={isActive ? "active" : ""}
                href={`#${item.id}`}
                key={item.label}
                onClick={(event) => {
                  event.preventDefault();
                  setActiveSection(item.id);
                }}
              >
                <Icon aria-hidden="true" size={18} />
                <span>{item.label}</span>
              </a>
            ) : (
              <span aria-disabled="true" className="disabled" key={item.label}>
                <Icon aria-hidden="true" size={18} />
                <span>{item.label}</span>
              </span>
            );
          })}
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">本地自托管</p>
            <h1>混剪工作台</h1>
          </div>
          <div className="topbar-summary">
            <Sparkles aria-hidden="true" size={18} />
            <span>React + Vite 产品骨架</span>
          </div>
        </header>

        <nav className="mobile-tabs" aria-label="移动端导航">
          {navItems.map((item) =>
            item.enabled ? (
              <a
                aria-current={item.id === activeSection ? "page" : undefined}
                className={item.id === activeSection ? "active" : ""}
                href={`#${item.id}`}
                key={item.shortLabel}
                onClick={(event) => {
                  event.preventDefault();
                  setActiveSection(item.id);
                }}
              >
                {item.shortLabel}
              </a>
            ) : (
              <span aria-disabled="true" className="disabled" key={item.shortLabel}>
                {item.shortLabel}
              </span>
            ),
          )}
        </nav>

        {activeSection === "remix" ? (
          <section className="content-grid" id="remix">
            <OnlineRemixWorkbench />
            <RuntimeStatus />
          </section>
        ) : (
          <section className="content-grid single-column" id="subtitles">
            <SubtitleTemplateWorkbench />
          </section>
        )}
      </main>
    </div>
  );
}
