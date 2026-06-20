# AutoVideo 混剪工作台音色选择设计

## 背景

用户选择方案 A：参考 `junxincode` 的视频音色选择模型，在 AutoVideo 混剪工作台中选择旁白音色。`junxincode` 旧 WebUI 的关键行为是加载可用人声、维护音色映射、提供试听，并在创建视频任务时提交所选 `voice`。AutoVideo 当前已经有独立的音色中心、`GET /api/voices`、`POST /api/voices/preview` 和 Edge TTS 试听能力，但线上混剪工作台还不能选择音色。

当前 AutoVideo 的 FFmpeg 混剪链路只生成视频、字幕、时间线和 manifest，还没有把 TTS 旁白音频混入最终 MP4。因此本次目标是完成任务级音色选择和持久化，为后续配音合成留下明确数据入口，不在本次声明最终视频已经带旁白配音。

## 目标

1. 在混剪工作台新增旁白音色选择区，用户可以选择 Edge TTS 音色。
2. 音色选择体验复用音色中心的数据源和试听能力，避免复制一套不一致逻辑。
3. 创建线上混剪任务时，把所选音色写入 `options`，并在任务 manifest 中保存安全的音色快照。
4. 桌面端和移动端都可读、可点、可滚动，不依赖 hover。
5. README 同步说明混剪工作台已支持选择音色，但最终配音合成仍是后续能力。

## 非目标

1. 不在本次把 TTS 音频合成进最终 MP4。
2. 不接入 Fish Speech 音色复刻到混剪任务。
3. 不引入权限管理、用户级音色库或账号隔离。
4. 不改变现有脚本生成、素材搜索、字幕渲染和任务输出下载语义。

## 方案对比

### 方案 A：抽取 AutoVideo 原生音色选择组件

新增可复用 `VoiceSelector` 组件，内部使用 `fetchVoiceStatus`、`fetchVoices` 和 `createVoicePreview`。音色中心继续保留完整试听工作台，混剪工作台使用较轻的选择器版本。创建任务时传 `voice_id`、`voice_name`、`voice_provider`、`voice_locale` 和 `voice_gender`。

优点是复用现有 API，前后端边界清晰，后续接入配音合成时可以直接使用任务 `options.voice_id`。缺点是需要抽一个组件和补测试。

### 方案 B：把音色中心逻辑直接复制到混剪工作台

直接在 `OnlineRemixWorkbench.tsx` 中加入查询、列表、试听和状态逻辑。优点是首轮文件数少，缺点是 `OnlineRemixWorkbench.tsx` 会继续膨胀，音色中心和混剪工作台的错误文案、默认音色选择、试听参数容易分叉。

### 方案 C：同时实现最终视频配音合成

在任务创建时生成 TTS 音频，并修改 FFmpeg 渲染命令把音频混入输出。优点是用户可直接得到带旁白成片，缺点是范围跨越音频生成、镜头级音频拼接、FFmpeg 混音、失败清理和输出语义，风险明显高于本次需求。

推荐方案 A。

## 用户体验设计

混剪工作台的基础表单保留现有结构，新增一个与“字幕设置”同级的“旁白音色”设置区。

桌面端布局：

- 表单基础字段仍保持多列排列。
- “字幕设置”和“旁白音色”作为跨列设置面板放在表单下方。
- 旁白音色区包含语言选择、搜索框、音色下拉或列表、当前音色摘要、试听按钮和试听播放器。
- 试听文案默认优先取脚本首个镜头旁白；脚本还未生成时使用主题生成一段短试听文案；都为空时使用默认中文试听文案。

移动端布局：

- 表单、字幕设置、旁白音色区全部单列。
- 语言、搜索、音色选择、试听按钮各自占满可用宽度。
- 按钮和表单控件最小触控高度保持 44px。
- 播放器宽度为 100%，避免横向溢出。

错误与空状态：

- 音色列表加载中显示 `正在读取音色`。
- 音色列表失败显示中文错误和 `重试` 按钮。
- 没有匹配音色显示 `没有匹配音色`。
- 试听失败复用音色中心的中文错误映射。
- 如果音色服务暂时不可用，仍允许用户生成脚本，但创建任务时不提交无效音色。
- 所有筛选字段使用可见 label；音色选中态通过 `aria-pressed` 或等价语义表达；加载状态使用 `aria-live`，错误状态使用 `role="alert"`；试听按钮在生成中有 disabled/loading 状态。

## 组件边界

新增 `frontend/src/components/VoiceSelector.tsx`：

- 负责加载音色状态和音色列表。
- 负责默认音色选择。
- 负责语言、搜索、选择、试听和错误呈现。
- 通过 `value` 和 `onChange` 把所选音色对象传给父组件。
- 不直接创建混剪任务，不知道 `OnlineRemixWorkbench` 的素材和字幕状态。

调整 `frontend/src/components/VoiceCenterWorkbench.tsx`：

- 保留完整音色中心页面。
- 复用 `VoiceSelector` 的默认选择、标签和错误处理 helper，避免重复。

调整 `frontend/src/components/OnlineRemixWorkbench.tsx`：

- 维护 `selectedVoice` 状态。
- 渲染 `VoiceSelector` 的 compact/workbench 形态。
- 调用 `createOnlineMixTask` 时在 `options` 中传入音色字段。

调整 `frontend/src/api/onlineRemix.ts`：

- 在 `CreateOnlineMixTaskInput.options` 增加可选字段：
  - `voice_id?: string | null`
  - `voice_name?: string | null`
  - `voice_provider?: "edge_tts" | null`
  - `voice_locale?: string | null`
  - `voice_gender?: string | null`

## 后端数据设计

新增 `normalize_voice_options(options)`，职责类似现有 `normalize_subtitle_options`，但只做安全字段归一，不调用外部 TTS 服务。

输出字段：

```json
{
  "voice_id": "zh-CN-XiaoxiaoNeural",
  "voice_name": "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
  "voice_provider": "edge_tts",
  "voice_locale": "zh-CN",
  "voice_gender": "Female"
}
```

规则：

- `voice_id` 为空时所有音色字段归一为 `null`。
- `voice_id` 非空时保存受清洗的字符串字段。
- `voice_id` 非空且 `voice_provider` 缺失或为空时归一为 `edge_tts`，因为首版只支持 Edge TTS。
- `voice_provider` 显式传入非 `edge_tts` 时返回结构化 400，避免写入伪造 provider。
- 字段先经过现有 `sanitize_manifest_payload`，不暴露本地路径、token 或服务端配置。
- manifest 顶层保存同名字段，`options` 中也保留归一后的音色字段，便于任务列表和后续配音合成读取。

## API 行为

`POST /api/online-mix/tasks` 的请求体结构不变，继续通过 `options` 承载任务设置。新增音色字段是向后兼容的可选字段。

示例：

```json
{
  "title": "线上素材混剪",
  "script": {
    "id": "script-1",
    "title": "线上素材混剪",
    "topic": "咖啡店早高峰",
    "aspect_ratio": "9:16",
    "duration_seconds": 5,
    "shots": [
      {
        "index": 1,
        "duration": 5,
        "narration": "第一杯热咖啡递到通勤者手里。",
        "subtitle": "第一杯热咖啡",
        "visual_description": "coffee shop morning",
        "keywords": ["coffee shop morning"]
      }
    ]
  },
  "asset_strategy": "auto",
  "provider": "auto",
  "options": {
    "aspect_ratio": "9:16",
    "resolution": "1080p",
    "subtitle_enabled": true,
    "voice_id": "zh-CN-XiaoxiaoNeural",
    "voice_name": "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
    "voice_provider": "edge_tts",
    "voice_locale": "zh-CN",
    "voice_gender": "Female"
  }
}
```

响应仍使用 `public_task(task, store)`，本次不扩大任务列表输出字段。

## 测试计划

后端：

- 在 `tests/api/test_online_mix.py` 增加测试：创建手动素材线上混剪任务时传入音色字段，断言 `manifest.json` 和任务 `options` 包含归一后的安全音色字段。
- 增加测试：不传 `voice_id` 时 manifest 和任务 `options` 中的 `voice_id`、`voice_name`、`voice_provider`、`voice_locale`、`voice_gender` 都为 `null`。
- 增加测试：`voice_id` 非空但 `voice_provider` 缺失或为空时归一为 `edge_tts`。
- 增加测试：非法 `voice_provider` 返回结构化 400，避免写入伪造 provider。

前端：

- 在 `frontend/src/App.test.tsx` 增加测试：混剪工作台渲染旁白音色选择器，默认选中后端返回的默认音色。
- 增加测试：用户创建线上混剪任务时，`createOnlineMixTask` 收到 `options.voice_id` 等音色字段。
- 增加测试：试听按钮调用 `createVoicePreview`，试听文案优先使用脚本首个镜头旁白。
- 增加测试或源码断言覆盖移动端单列布局、控件最小 44px 和无 hover 依赖；`fetchVoiceStatus` mock 必须使用 `edge_tts.default_voice`，避免误读为顶层 `default_voice`。

手工验证：

- `npm test -- --run src/App.test.tsx`
- `pytest tests/api/test_online_mix.py`
- `npm run build`
- 必须启动 Vite 或生产构建预览，在 375px 和桌面视口检查混剪页：`document.body.scrollWidth <= window.innerWidth`，语言、搜索、音色选择和试听按钮实际高度不低于 44px，音频播放器不撑破布局，主要交互可点击触发且不依赖 hover。

## 文档更新

更新 README：

- 当前阶段增加“混剪工作台可选择旁白音色并保存到任务 manifest”。
- API 示例在 `POST /api/online-mix/tasks` 中展示 `voice_id`。
- 明确当前最终视频还未混入 TTS 旁白音频，音色字段用于任务配置和后续配音合成。

## 验收标准

1. 混剪工作台可以看到“旁白音色”设置区。
2. 默认音色来自 `/api/voices/status` 的 `edge_tts.default_voice`，否则使用列表第一项。
3. 用户可以切换语言、搜索音色并选择音色。
4. 用户可以试听当前音色，试听文案来自脚本首个镜头旁白或安全默认文案。
5. 创建线上混剪任务时，前端提交所选音色字段。
6. 后端把音色字段写入任务 `options` 和 manifest，且不暴露本地路径、token 或真实凭据。
7. 不选择音色或音色列表不可用时，现有混剪任务创建流程不被破坏。
8. 移动端 375px 下 `document.body.scrollWidth <= window.innerWidth`，没有页面级横向溢出。
9. 移动端语言、搜索、音色选择和试听按钮实际高度不低于 44px，主要交互可点击触发且不依赖 hover。
10. 移动端试听播放器宽度不撑破布局，音频控件在单列布局中保持可见、可点、可滚动。
