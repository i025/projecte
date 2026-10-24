# BlenderWorld 历史 Runs 清点与筛选

扫描时间：2026-10-20T03:37:13.356800+00:00。本次仅静态数据审计，无新评分。

## 范围与数量

- 扫描 `BlenderWorld/runs` 全部 **16 个顶层目录**；清单 **29 行**：25 个原生生成尝试（包括失败与续跑），3 个有提交副本的独立评测记录，1 个仅 plan 的评测记录。父级 Harbor job 容器不重复计行；评测记录不算新生成。

- 全部 29 行均能通过任务/输入元数据找到现存原始 RGB；涉及 **16 张按任务 ID 去重的参考图**。这是有据可查的源媒体数量，不是已消费输入数，也未进行内容哈希去重。其中浣熊单个文件含多个视图，不视为单视图重建。

- **25 行有实际 .blend 文件**，其中 **22 个生成尝试**有保存文件（含中断快照和继承场景），其余为评测副本。数量不代表独立成品或已验证可加载。

- **eligible 9 / uncertain 6 / ineligible 14**。本次推荐全部 9 个高置信离线候选，覆盖 7 张不同任务参考图；未为凑数使用不完整场景。

- 6 条记录需要人工先确认来源或完成范围；另全部 9 个推荐场景都必须在未来执行 Blender 前接受安全审核。

- 不读取凭据，不导入仓库或 Agent 模块，不执行历史 Python，不启动 Blender/GPU/Agent/VLM/正式 Benchmark，不计算哈希，不下载依赖；原目录只读访问。Project e Runtime/Evidence 审核状态未改动。仅新建本目录四个文件，未复制原图或改写历史结果。

## 可复核的数据对应链

- 生成记录：`runs/<group>/<job>/<trial>/config.json.task.path` 指向准备任务；该目录 `environment/inputs/input.json` 明确 `task_id` 和实际文件列表；与数据集 `task.json.reference_images` 交叉对应；`result.json` 保留任务名称、Agent/模型、结束状态，`agent/trajectory.json` 或原生日志保留生成过程。`artifacts/manifest.json` 记录 `/workspace/exports` 的恢复位置。每行 CSV 的 provenance 给出具体文件。

- 原图列优先使用实际分发给该 Run 的只读 staged reference；original_reference_image 列保留数据集原媒体路径。未通过文件名猜任务，未把纹理、作者渲染或 gallery 当作参考图。image_count 统计元数据声明且实际存在的参考媒体，不表示初始化失败的 Agent 已收到图片。other_inputs 保留 query 和额外协议文件；完整任务文字在 task_goal。

- 官方展示批的准备代码和 selection.json 明确源为 `data/hf-snapshot/<task>/tests/dataset`；RGB-only pair 的 selection.json 明确原始图与 generation_image 对应。所有发现的任务均声明一张参考文件，无视频或规格附件；这不排除同一文件含多视图，也不排除有详细文字要求。

- 雪山三次尝试的 `.blend` 从 controller status 的 `task_id + delivery_directory` 找到，明确标为 partial；并未把缺失的 trial 导出误认为没有任何中间产物。session-path-failure 保留继承文件但不认定新成功结果。setup_failure_01 没有自己的 .blend，未借用同任务后续成功文件。

- `scene_064` 是本地适配任务 **bw_9064**，由 provenance 和 task metadata 明确关联；它与官方雪山 **bw_0064** 无关。旧 e-harness 源运行路径现不可访问，复制品仍在，但不凭路径文字认定模型。

- 独立评测由 plan.task_ids/submissions 与 submission_archive 的文件清单定位提交副本。`scene_064-harbor-evaluation` 和对应生成通过 work/scene_064-harbor/report.json 的 generated_project/submission 关联，去除重复推荐。旧 bw_0006 只有 Codex-authored 脚本说明，评测 Judge 模型不是生成 Agent 模型。

- 只使用作者已有成图/预览；官方 `official-renders` gallery 和 evaluator `multiview/view_*.png` 未作为推荐配对图。成图与最终 .blend 同源，不保证最后一次保存和成图严格同步；需后续人工检查。

## 资格、输入与相机边界

- **Offline Evaluator Candidate**：eligible 指单张源图、还原意图、可追溯实际场景、无原生异常的完成记录及已有作者渲染/轨迹，适合后续审核后研究评价器；不等于任务达成，也不赋予安全执行授权。

- **Strict RGB-only Baseline**：只有厨房 RGB-only Key2 记录获得保存输入与原生轨迹的正面支持：input.json 明确 original_task_query_included=false/rubric_included=false；通用 agent_prompt 不含厨房对象清单；trajectory 的两个 user 消息为环境与一图+通用任务；原生 rollout 在初始任务 user 消息保留恰好一个 input_image，后续查看的是自己生成的 preview/final。未发现额外场景输入请求。此结论限于保存的输入/工具轨迹，不能替代独立隔离审计或模型训练来源证明。其他结果按 CSV 标为 not_proven/unknown；不因名称带 RGB-only 自动认可。

- **Fixed-T0 Compliant**：本次没有可证明符合当前 Project e T0 的推荐样本。BlenderWorld 固定相机导出 T_c2w 平移为 [0,-6,1.5]；当前 e_harness/benchmark_config.py FIXED_T0 平移为 [0,-6,2]。两者相差 0.5m，均使用 Blender 相机坐标约定；不能把固定相机名称当作协议相同。推荐全部标 historical_camera；自由相机组参数缺失时写 unknown。未变换任何场景。

- 相机信息优先来自 camera_parameters.json 或已有 agent_bpy_dump.json。后者是历史评测副本快照，不是新检查；未知原相机或原图相机真值时不从图像猜参数。

## 推荐与兼容性

九个结果的现有 RGB 和作者图均已实际解码、检查尺寸并静态查看。可用保留比例/留边统一尺寸；这不保证视角一致。可以人工标 Global / Region / Anchor，但本轮没有自动生成或更改 Evidence。Statistical 在没有审核占据图/重复实例证据时只能称纹理或边缘分布代理；Semantic 不使用 DINO 距离冒充类别证据。五能量和独立 3D Structural 的研究方向如下，均不是评分结果。

### 1. 第 1 批：bw_9064 — 餐桌、双椅与冰箱

Run：`scene_064-harbor-generation/scene_064/task__LY4dtPw`；Agent：claude-code 2.1.220 / gpt-6-sol (anthropic)。

选择原因：主要 Anchor 清晰、大片墙地面连续；适合先检验物体完整性和空间关系。静态图中冰箱偏白、家具与叶片简化，提供可解释的外观和几何差异。

Region：墙面/天花、木地板、左侧家具簇、右侧电器区。Anchor：圆桌、左椅、右椅、桌上盆栽、冰箱。

适合的能量验证：Semantic 存在与类别；Spatial 左右和支撑；Appearance 木材/金属；Statistical 地板与叶片边缘分布代理；Perceptual 整体外观。 3D Structural 留待人工安全审核后检查几何支撑、穿插、隐藏面和实体构造。

现成图：[Reference](../../../BlenderWorld/work/scene_064-harbor/task/environment/inputs/references/image_01.png)（1672x941; RGB; PNG） / [Agent Render](../../../BlenderWorld/runs/scene_064-harbor-generation/scene_064/task__LY4dtPw/artifacts/workspace/exports/final.png)（1672x941; RGBA; PNG）；[历史 .blend 文件（未打开）](../../../BlenderWorld/runs/scene_064-harbor-generation/scene_064/task__LY4dtPw/artifacts/workspace/exports/final.blend)。

资格：eligible；Offline Candidate=yes；historical_camera；Fixed-T0 不合规/未证明。Strict RGB-only：unknown：准备输入仅一图和通用指令，但本轮不将其升级为经过完整输入隔离证明的 Strict Baseline。

未知与人工审核：原图无相机真值；历史 dump 可追溯但未经本轮确认；隐藏面和材质依赖需审核。旧 bw_9064 复制品可作未来配对候选，但其原运行目录缺失。 均需先审核场景内嵌脚本、驱动、相对纹理和外部依赖；本轮未验证载入安全、贴图完整性或图场景同步。

### 2. 第 1 批：bw_0074 — 深蓝书柜客厅

Run：`official-showcase-10-images-v2/bw_0074/bw_0074__KcPDLD8`；Agent：claude-code 2.1.220 / gpt-6-sol (anthropic)。

选择原因：重复书籍/唱片、丰富小物与前景遮挡并存；现成渲染中书架分隔、书本排列和沙发/抱枕细节与原图有可见差异。

Region：开放书架、唱片集中区、发光书桌区、沙发前景、墙地面。Anchor：显示器、笔记本、透明椅、沙发、地球仪、唱机、生态缸（存在性需逐个复核）。

适合的能量验证：Semantic 重要小物遗漏；Spatial 分格/遮挡；Appearance 蓝色柜面与布料；Statistical 重复书籍的空间分布；Perceptual 整体。 3D Structural 留待人工安全审核后检查几何支撑、穿插、隐藏面和实体构造。

现成图：[Reference](../../../BlenderWorld/work/official-showcase-10-images-v2/tasks/bw_0074/environment/inputs/references/image_01.jpg)（1258x855; RGB; JPEG） / [Agent Render](../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0074/bw_0074__KcPDLD8/artifacts/workspace/exports/modern_living_room.png)（1920x1300; RGB; PNG）；[历史 .blend 文件（未打开）](../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0074/bw_0074__KcPDLD8/artifacts/workspace/exports/final.blend)。

资格：eligible；Offline Candidate=yes；historical_camera；Fixed-T0 不合规/未证明。Strict RGB-only：not_proven：原始 Image+Text 任务提供了场景描述。

未知与人工审核：无独立相机参数 JSON；书本/唱片不应逐条从边缘代理冒充真实实例；细小 Anchor 可见性和文字给予的提示需人工标注。 均需先审核场景内嵌脚本、驱动、相对纹理和外部依赖；本轮未验证载入安全、贴图完整性或图场景同步。

### 3. 第 1 批：bw_0073 — 厨房同图重建对照

Run：`bw_0073-codex-fixed-camera-v1-rgb-only-key2-generation/bw_0073/task__bA358eg`；Agent：codex 0.147.0 / gpt-6-sol (openai)。

选择原因：四把吧椅、岛台、拱窗和橱柜提供明确关系及连续材质区域；三个完整重建在窗形、布局比例、明暗与石材上存在可见差异。

Region：左窗与台面、岛台和吧椅簇、右侧高柜、后墙、木地板。Anchor：岛台、四把吧椅（逐实例）、大拱窗、吊灯、冰箱/高柜。

适合的能量验证：Semantic 经审核的实例数和类别；Spatial 排列/窗形位置；Appearance 石材/木/柜色；Statistical 柜门、椅子和地板分布代理；Perceptual 整体。 3D Structural 留待人工安全审核后检查几何支撑、穿插、隐藏面和实体构造。

现成图：[Reference](../../../BlenderWorld/work/codex-fixed-camera-v1-reference-pair/bw_0073/task/environment/inputs/references/image_01.jpg)（7952x4333; RGB; JPEG） / [Agent Render](../../../BlenderWorld/runs/bw_0073-codex-fixed-camera-v1-rgb-only-key2-generation/bw_0073/task__bA358eg/artifacts/workspace/exports/final.png)（1672x941; RGBA; PNG）；[历史 .blend 文件（未打开）](../../../BlenderWorld/runs/bw_0073-codex-fixed-camera-v1-rgb-only-key2-generation/bw_0073/task__bA358eg/artifacts/workspace/exports/final.blend)。

资格：eligible；Offline Candidate=yes；historical_camera；Fixed-T0 不合规/未证明。Strict RGB-only：supported_by_saved_input_and_native_trace：单张初始 input_image；仅通用重建/工具/相机指令，无原任务 query/rubric；详见 report.md 的证据和边界。

未知与人工审核：RGB-only 与原 query 两组输入不同；Claude 续跑继承旧 session；均非不同模型的公平对决。固定相机两组高度 1.5m，与当前 T0 的 2m 不同；自由相机组参数 unknown。 均需先审核场景内嵌脚本、驱动、相对纹理和外部依赖；本轮未验证载入安全、贴图完整性或图场景同步。

### 4. 第 2 批：bw_0073 — 厨房同图重建对照

Run：`bw_0073-codex-fixed-camera-v1-official-query-generation/bw_0073/task__Dpf9tyA`；Agent：codex 0.147.0 / gpt-6-sol (openai)。

选择原因：四把吧椅、岛台、拱窗和橱柜提供明确关系及连续材质区域；三个完整重建在窗形、布局比例、明暗与石材上存在可见差异。

Region：左窗与台面、岛台和吧椅簇、右侧高柜、后墙、木地板。Anchor：岛台、四把吧椅（逐实例）、大拱窗、吊灯、冰箱/高柜。

适合的能量验证：Semantic 经审核的实例数和类别；Spatial 排列/窗形位置；Appearance 石材/木/柜色；Statistical 柜门、椅子和地板分布代理；Perceptual 整体。 3D Structural 留待人工安全审核后检查几何支撑、穿插、隐藏面和实体构造。

现成图：[Reference](../../../BlenderWorld/work/bw_0073-codex-fixed-camera-v1-official-query/task/environment/inputs/references/image_01.jpg)（7952x4333; RGB; JPEG） / [Agent Render](../../../BlenderWorld/runs/bw_0073-codex-fixed-camera-v1-official-query-generation/bw_0073/task__Dpf9tyA/artifacts/workspace/exports/final.png)（1672x941; RGBA; PNG）；[历史 .blend 文件（未打开）](../../../BlenderWorld/runs/bw_0073-codex-fixed-camera-v1-official-query-generation/bw_0073/task__Dpf9tyA/artifacts/workspace/exports/final.blend)。

资格：eligible；Offline Candidate=yes；historical_camera；Fixed-T0 不合规/未证明。Strict RGB-only：not_proven：原始 Image+Text 任务提供了场景描述。

未知与人工审核：RGB-only 与原 query 两组输入不同；Claude 续跑继承旧 session；均非不同模型的公平对决。固定相机两组高度 1.5m，与当前 T0 的 2m 不同；自由相机组参数 unknown。 均需先审核场景内嵌脚本、驱动、相对纹理和外部依赖；本轮未验证载入安全、贴图完整性或图场景同步。

### 5. 第 2 批：bw_0073 — 厨房同图重建对照

Run：`bw_0073-official-harbor-continued/bw_0073/task__qtzUWks`；Agent：claude-code 2.1.220 / gpt-6-sol (anthropic)。

选择原因：四把吧椅、岛台、拱窗和橱柜提供明确关系及连续材质区域；三个完整重建在窗形、布局比例、明暗与石材上存在可见差异。

Region：左窗与台面、岛台和吧椅簇、右侧高柜、后墙、木地板。Anchor：岛台、四把吧椅（逐实例）、大拱窗、吊灯、冰箱/高柜。

适合的能量验证：Semantic 经审核的实例数和类别；Spatial 排列/窗形位置；Appearance 石材/木/柜色；Statistical 柜门、椅子和地板分布代理；Perceptual 整体。 3D Structural 留待人工安全审核后检查几何支撑、穿插、隐藏面和实体构造。

现成图：[Reference](../../../BlenderWorld/work/bw_0073-official-harbor/task/environment/inputs/references/image_01.jpg)（7952x4333; RGB; JPEG） / [Agent Render](../../../BlenderWorld/runs/bw_0073-official-harbor-continued/bw_0073/task__qtzUWks/artifacts/workspace/exports/render.png)（1800x1012; RGBA; PNG）；[历史 .blend 文件（未打开）](../../../BlenderWorld/runs/bw_0073-official-harbor-continued/bw_0073/task__qtzUWks/artifacts/workspace/exports/final.blend)。

资格：eligible；Offline Candidate=yes；historical_camera；Fixed-T0 不合规/未证明。Strict RGB-only：not_proven：原始 Image+Text 任务提供了场景描述。

未知与人工审核：RGB-only 与原 query 两组输入不同；Claude 续跑继承旧 session；均非不同模型的公平对决。固定相机两组高度 1.5m，与当前 T0 的 2m 不同；自由相机组参数 unknown。 均需先审核场景内嵌脚本、驱动、相对纹理和外部依赖；本轮未验证载入安全、贴图完整性或图场景同步。

### 6. 第 2 批：bw_0063 — 开放客餐厅

Run：`official-showcase-10-images-v2/bw_0063/bw_0063__Lj7uE6T`；Agent：claude-code 2.1.220 / gpt-6-sol (anthropic)。

选择原因：客厅/餐区语义分组明确，含通道、玻璃开口和多组家具；渲染可见主体布局保留，但家具细节、地面和空间比例简化。

Region：左侧落地窗、客厅家具、中央后退走廊、右餐区、墙地面。Anchor：沙发、茶几、吊扇、绿植、餐桌/椅、玻璃双开门。

适合的能量验证：五能量均可研究；Statistical 限定为分组占据或边缘分布，不推断真实物体密度。 3D Structural 留待人工安全审核后检查几何支撑、穿插、隐藏面和实体构造。

现成图：[Reference](../../../BlenderWorld/work/official-showcase-10-images-v2/tasks/bw_0063/environment/inputs/references/image_01.jpg)（1024x572; RGB; JPEG） / [Agent Render](../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0063/bw_0063__Lj7uE6T/artifacts/workspace/exports/coastal_living_dining.png)（1920x1080; RGBA; PNG）；[历史 .blend 文件（未打开）](../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0063/bw_0063__Lj7uE6T/artifacts/workspace/exports/final.blend)。

资格：eligible；Offline Candidate=yes；historical_camera；Fixed-T0 不合规/未证明。Strict RGB-only：not_proven：原始 Image+Text 任务提供了场景描述。

未知与人工审核：相机参数和真实尺度 unknown；反射、曝光与物体材质误差需要分开解释；可见餐椅数需人工审核。 均需先审核场景内嵌脚本、驱动、相对纹理和外部依赖；本轮未验证载入安全、贴图完整性或图场景同步。

### 7. 第 2 批：bw_0043 — 六瓣白花微距

Run：`official-showcase-10-images-v2/bw_0043/bw_0043__p7isE6U`；Agent：claude-code 2.1.220 / gpt-6-sol (anthropic)。

选择原因：单朵重要主体与可数花瓣，背景有叶片和碎屑；渲染花瓣轮廓、花心和背景分布有清晰可见差异。

Region：主花、黄绿喉部、花心、背景叶片、褐色落叶/木屑。Anchor：整朵花、六片花瓣组、雄蕊/花药簇、花柱。

适合的能量验证：Semantic 类别与部件存在需审核；Spatial 花瓣/花心；Appearance 白/黄绿和透光；Statistical 背景碎屑/边缘；Perceptual。 3D Structural 留待人工安全审核后检查几何支撑、穿插、隐藏面和实体构造。

现成图：[Reference](../../../BlenderWorld/work/official-showcase-10-images-v2/tasks/bw_0043/environment/inputs/references/image_01.jpg)（1024x617; RGB; JPEG） / [Agent Render](../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0043/bw_0043__p7isE6U/artifacts/workspace/exports/final.png)（1920x1080; RGBA; PNG）；[历史 .blend 文件（未打开）](../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0043/bw_0043__p7isE6U/artifacts/workspace/exports/final.blend)。

资格：eligible；Offline Candidate=yes；historical_camera；Fixed-T0 不合规/未证明。Strict RGB-only：not_proven：原始 Image+Text 任务提供了场景描述。

未知与人工审核：微小花药计数/植物类别需要专业人工或语义验证；景深变化影响边缘统计；相机参数 unknown。 均需先审核场景内嵌脚本、驱动、相对纹理和外部依赖；本轮未验证载入安全、贴图完整性或图场景同步。

### 8. 第 2 批：bw_0006 — 航天局展台

Run：`official-showcase-10-images-v2/bw_0006/bw_0006__gfHGhky`；Agent：claude-code 2.1.220 / gpt-6-sol (anthropic)。

选择原因：红柱、屏幕和舱门是清晰 Anchor，大片金属墙便于外观研究；原图局部近景与渲染全景差别明显，可检验相机/裁切混杂。

Region：红色标识柱、屏幕、金属墙板、舱门与月面、地面/顶棚。Anchor：红柱、显示屏、舱门/舷窗、月面车。

适合的能量验证：Semantic 主物件；Spatial 布局；Appearance 金属/红漆；Statistical 铆钉/接缝代理；Perceptual。 3D Structural 留待人工安全审核后检查几何支撑、穿插、隐藏面和实体构造。

现成图：[Reference](../../../BlenderWorld/work/official-showcase-10-images-v2/tasks/bw_0006/environment/inputs/references/image_01.png)（1246x1520; RGB; PNG） / [Agent Render](../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0006/bw_0006__gfHGhky/artifacts/workspace/exports/final.png)（2400x1600; RGBA; PNG）；[历史 .blend 文件（未打开）](../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0006/bw_0006__gfHGhky/artifacts/workspace/exports/final.blend)。

资格：eligible；Offline Candidate=yes；historical_camera；Fixed-T0 不合规/未证明。Strict RGB-only：not_proven：原始 Image+Text 任务提供了场景描述。

未知与人工审核：纵向原图与横向全景需要先人工决定共同可见区域，直接拉伸会误导；字标不凭边缘作语义判断；相机参数 unknown。旧同题提交无完整 Agent 轨迹，暂不配对评分。 均需先审核场景内嵌脚本、驱动、相对纹理和外部依赖；本轮未验证载入安全、贴图完整性或图场景同步。

### 9. 第 2 批：bw_0075 — 蓝调层叠山景

Run：`official-showcase-10-images-v2/bw_0075/bw_0075__nVjEut5`；Agent：claude-code 2.1.220 / gpt-6-sol (anthropic)。

选择原因：补充非室内视觉内容；大片天空与层叠山脊适合区域比较。渲染保留分层，但笔触、云形及山线细节有可见差异。

Region：天空/云、远山、中山、深色前景山脊。Anchor：主要山脊组、云团（边界需人工定义；精细重要物体较少）。

适合的能量验证：主要验证 Appearance、Statistical 纹理/多尺度边缘分布和 Perceptual；Spatial 层次边界；Semantic 缺少可靠类别证据时保持 N/A。 3D Structural 留待人工安全审核后检查几何支撑、穿插、隐藏面和实体构造。

现成图：[Reference](../../../BlenderWorld/work/official-showcase-10-images-v2/tasks/bw_0075/environment/inputs/references/image_01.jpg)（2250x1500; RGB; JPEG） / [Agent Render](../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0075/bw_0075__nVjEut5/artifacts/workspace/exports/mountain_blue_oil_painting.png)（2700x1800; RGB; PNG）；[历史 .blend 文件（未打开）](../../../BlenderWorld/runs/official-showcase-10-images-v2/bw_0075/bw_0075__nVjEut5/artifacts/workspace/exports/final.blend)。

资格：eligible；Offline Candidate=yes；historical_camera；Fixed-T0 不合规/未证明。Strict RGB-only：not_proven：原始 Image+Text 任务提供了场景描述。

未知与人工审核：原图为油画风而非实拍；真实物体密度不适用，精细 Anchor 价值低于首批；相机参数、隐藏几何合理性 unknown。 均需先审核场景内嵌脚本、驱动、相对纹理和外部依赖；本轮未验证载入安全、贴图完整性或图场景同步。

## 同参考图对比与独立性

- **bw_0073 reference → Codex RGB-only / Codex 原 query / Claude Code 原 query+续跑**：推荐 #3/#4/#5。底层记录均为 gpt-6-sol；比较的是输入、接口/相机和生成轨迹差异，不能称为多模型优劣实验。#4/#5 都带场景文字，但自由/固定相机不同；#3/#4 相机协议接近且输入文字不同。不要把这些混杂归因于某个能量或 Agent 名称。

- **bw_9064 reference → 旧 e-harness 导入 / 新 Harbor 重建**：新结果为 #1；旧副本 uncertain，需找回原始运行轨迹后再加入配对。bw_0006 也有旧脚本提交与 #8，但旧记录的 Agent 自主性/模型 unknown。

- 雪山原始与两次续跑是同一 session 的不同检查点；session-path-failure 只是厨房继承副本；评测提交副本均不当作独立 Agent。按 task_id 关联的 same_reference_runs 列覆盖这些关系。没有发现具备完整不同底层模型证据的高置信同图多模型组。

## 未入选与需确认

- `bw_0073-codex-fixed-camera-v1-rgb-only-generation/bw_0073/task__oYZ64xB` — **ineligible**：此尝试没有可访问的实际 .blend；不能借用同任务其他尝试的成功产物。

- `bw_0073-official-harbor/bw_0073/task__PiTqWFN` — **uncertain**：原图与部分产物可追溯，但原生运行异常或超时；final.blend 文件名不能证明完成，需人工确认可用范围。

- `bw_0073-official-harbor-continued-session-path-failure/bw_0073/task__23ZnCR7` — **ineligible**：续接 session 失败；保存的是继承的原始场景，不能作为独立成功重建。

- `bw_0094-codex-fixed-camera-v1-rgb-only-generation/bw_0094/task__Uwpj6BC` — **uncertain**：原图与部分产物可追溯，但原生运行异常或超时；final.blend 文件名不能证明完成，需人工确认可用范围。

- `official-showcase-10-images-v2/bw_0008/bw_0008__bMh96wX` — **ineligible**：重建后指定改造输送带、过渡料斗和控制柜材质，目标不等于原图。

- `official-showcase-10-images-v2/bw_0009/bw_0009__X9GcF9r` — **uncertain**：原图与部分产物可追溯，但原生运行异常或超时；final.blend 文件名不能证明完成，需人工确认可用范围。

- `official-showcase-10-images-v2/bw_0037/bw_0037__euoKweR` — **ineligible**：明确禁止复制原图构图；仅借用风格自由设计连续室内空间。

- `official-showcase-10-images-v2/bw_0064/bw_0064__6jJPogR` — **ineligible**：明确要求由正午改成金色日落；且原始尝试和两次续跑均未完成。

- `official-showcase-10-images-v2/bw_0065/bw_0065__ahYmWAi` — **ineligible**：单文件含浣熊多视图；要求重新摆姿并新建夜间后巷，非单图场景还原。

- `official-showcase-10-images-v2/bw_0070/bw_0070__ofnJd6D` — **uncertain**：原图与部分产物可追溯，但原生运行异常或超时；final.blend 文件名不能证明完成，需人工确认可用范围。

- `official-showcase-10-images-v2/bw_0071/bw_0071__QtP3wre` — **ineligible**：要求额外增加一排树冠阵列，目标元素分布已改变。

- `official-showcase-10-images-v2/bw_0099/bw_0099__Wvpy28t` — **ineligible**：同一工程包含毛坯 before 与精装 after；整体任务是改造，未来仅 before 状态可经人工确认后另作候选。

- `official-showcase-10-images-v2-bw_0064-resumed/bw_0064/bw_0064__zdENoaW` — **ineligible**：明确要求由正午改成金色日落；且原始尝试和两次续跑均未完成。

- `official-showcase-10-images-v2-bw_0064-resumed-final050/bw_0064/bw_0064__uT6rkCq` — **ineligible**：明确要求由正午改成金色日落；且原始尝试和两次续跑均未完成。

- `official-showcase-10-v1/bw_0006/bw_0006__F9MkLeM` — **ineligible**：此尝试没有可访问的实际 .blend；不能借用同任务其他尝试的成功产物。

- `scene_064-harbor-generation/setup_failure_01/task__4HCwsib` — **ineligible**：此尝试没有可访问的实际 .blend；不能借用同任务其他尝试的成功产物。

- `bw_0006-evaluation` — **ineligible**：只有评测 plan.json，没有 task result 或提交副本；不是一次生成，也没有该 Run 的可用评测结果。

- `bw_0006-ofox-evaluation` — **uncertain**：评测提交副本存在且与任务可追溯；只有 Codex-authored 脚本说明，无独立自主 Agent 生成轨迹和生成模型证明。

- `scene_064-blenderworld-custom` — **uncertain**：本地 bw_9064 适配的旧场景；provenance.json 明确原图/原工程，复制品存在，但原 e-harness 运行路径不可访问，完整生成轨迹和输入隔离 unknown。

- `scene_064-harbor-evaluation` — **ineligible**：成功 Harbor 生成样本的重复评测副本；关联来源但不重复推荐或计作独立 Agent。

## 扫描覆盖与检查结果

| 顶层目录 | Inventory 行数 |
| --- | ---: |
| bw_0006-evaluation | 1 |
| bw_0006-ofox-evaluation | 1 |
| bw_0073-codex-fixed-camera-v1-official-query-generation | 1 |
| bw_0073-codex-fixed-camera-v1-rgb-only-generation | 1 |
| bw_0073-codex-fixed-camera-v1-rgb-only-key2-generation | 1 |
| bw_0073-official-harbor | 1 |
| bw_0073-official-harbor-continued | 1 |
| bw_0073-official-harbor-continued-session-path-failure | 1 |
| bw_0094-codex-fixed-camera-v1-rgb-only-generation | 1 |
| official-showcase-10-images-v2 | 13 |
| official-showcase-10-images-v2-bw_0064-resumed | 1 |
| official-showcase-10-images-v2-bw_0064-resumed-final050 | 1 |
| official-showcase-10-v1 | 1 |
| scene_064-blenderworld-custom | 1 |
| scene_064-harbor-evaluation | 1 |
| scene_064-harbor-generation | 2 |



- 已完成：16 个顶层目录覆盖；25 个原生 trial config/result 元数据链交叉核对；4 个评测/计划记录；全部参考路径存在性、推荐 blend/图片存在性与非零文件大小、推荐图像可解码检查；CSV 子集、唯一 run_id 和 HTML 图片链接检查。

- 已完成：静态查看全部有可用图像的生成组概览，并复查九个推荐原图与作者图；未用既有评分排序。

- 未执行：任何 Agent、历史 Python、Blender 打开/渲染、几何测量、GPU/VLM/API、Project e Benchmark。未生成任何能量/质量分数。不存在“评测通过”的结论。

## 最简查看方式与后续边界

在此目录打开 `selected_preview.html` 查看现有图像对照；CSV 用 UTF-8 BOM，直接用表格工具打开。HTML 仅使用相对路径引用现存媒体，需在同一文件系统布局下本地浏览；无需服务器、依赖安装或新渲染。

```bash

cd /home/xymo/projects/e-harness/results/blenderworld_runs_inventory

less report.md

# 用本地浏览器打开 selected_preview.html；表格工具打开 inventory.csv / selected.csv

```

本轮到此结束。后续若获授权，先对第一批三份场景做人工安全与语义审核，再决定任何执行；本报告本身不授权运行场景。
