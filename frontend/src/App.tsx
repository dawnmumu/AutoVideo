import { useQuery } from "@tanstack/react-query";
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

import { fetchHealth } from "./api/health";

const navItems = [
  { label: "混剪工作台", shortLabel: "混剪", icon: Clapperboard },
  { label: "素材库", shortLabel: "素材", icon: FolderOpen },
  { label: "字幕模板", shortLabel: "字幕", icon: Captions },
  { label: "BGM 管理", shortLabel: "BGM", icon: Music },
  { label: "音色中心", shortLabel: "音色", icon: Volume2 },
  { label: "功能提取处理", shortLabel: "提取", icon: Sparkles },
  { label: "任务与输出", shortLabel: "任务", icon: SquarePlay },
  { label: "系统设置", shortLabel: "设置", icon: Settings },
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
          {navItems.map((item, index) => {
            const Icon = item.icon;
            return index === 0 ? (
              <a
                aria-current="page"
                className={index === 0 ? "active" : ""}
                href={`#${index}`}
                key={item.label}
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
          {navItems.map((item, index) =>
            index === 0 ? (
              <a aria-current="page" className="active" href="#0" key={item.shortLabel}>
                {item.shortLabel}
              </a>
            ) : (
              <span aria-disabled="true" className="disabled" key={item.shortLabel}>
                {item.shortLabel}
              </span>
            ),
          )}
        </nav>

        <section className="content-grid" id="0">
          <article className="panel primary-panel">
            <div className="panel-heading">
              <h2>新建混剪任务</h2>
              <span>阶段 1 先搭建产品骨架，后续阶段接入素材、字幕模板、BGM、音色和功能提取处理。</span>
            </div>
            <div className="empty-state">
              <strong>工作台已就绪</strong>
              <p>下一阶段将接入资源中心、功能提取处理和混剪任务流。</p>
            </div>
          </article>

          <RuntimeStatus />
        </section>
      </main>
    </div>
  );
}
