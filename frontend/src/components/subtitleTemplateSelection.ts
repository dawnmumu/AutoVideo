import type { SubtitleTemplateSet } from "../api/subtitles";

function selectionKey(template: SubtitleTemplateSet): [string, string, string] {
  return [
    String(template.updated_at ?? ""),
    String(template.created_at ?? ""),
    String(template.id ?? ""),
  ];
}

export function sortSubtitleTemplatesForSelection(
  templates: SubtitleTemplateSet[],
): SubtitleTemplateSet[] {
  return [...templates].sort((left, right) => {
    const leftKey = selectionKey(left);
    const rightKey = selectionKey(right);

    for (let index = 0; index < leftKey.length; index += 1) {
      if (leftKey[index] > rightKey[index]) {
        return -1;
      }
      if (leftKey[index] < rightKey[index]) {
        return 1;
      }
    }

    return 0;
  });
}

export function selectAutoSubtitleTemplate(
  customTemplates: SubtitleTemplateSet[],
  presetTemplates: SubtitleTemplateSet[],
): SubtitleTemplateSet | undefined {
  const newestCustom = sortSubtitleTemplatesForSelection(customTemplates)[0];
  if (newestCustom) {
    return newestCustom;
  }

  return presetTemplates[0];
}
