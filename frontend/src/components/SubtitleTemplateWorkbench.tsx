import { useQuery } from "@tanstack/react-query";

import { fetchSubtitleTemplateSets } from "../api/subtitles";

export function SubtitleTemplateWorkbench() {
  const templates = useQuery({
    queryKey: ["subtitle-template-sets"],
    queryFn: fetchSubtitleTemplateSets,
  });

  const availableTemplateCount =
    (templates.data?.items.length ?? 0) + (templates.data?.presets.length ?? 0);

  return (
    <article
      aria-label="字幕模板"
      className="panel subtitle-template-workbench"
      data-mobile-layout="stacked-template-preview-editor"
    >
      <div className="panel-heading">
        <h2>字幕模板</h2>
      </div>
      <div aria-live="polite" className="runtime-status" role="status">
        {templates.isLoading
          ? "正在加载模板"
          : templates.isError
            ? "模板加载失败"
            : `可用模板 ${availableTemplateCount} 个`}
      </div>
    </article>
  );
}
