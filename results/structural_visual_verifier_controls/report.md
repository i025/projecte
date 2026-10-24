# Structural Layout 视觉验证器：首次独立合成对照

本轮实际运行 3 个独立 gpt-6-sol 视觉验证子 Agent，每图一次、严格串行、无重试。判断来自真实单图输入与原始回答，不是 Oracle 标签代替模型输出。全部 reviewed=false、provisional/debug，不生成正式 Spatial Energy 或准确率。

| 样本条件（不进入模型输入） | 构造结构真值 | 冻结可见答案候选 | 真实原始回答 | 比较结果 |
| --- | --- | --- | --- | --- |
| divider_present | present | present | {"internal_divider":"present"} | matches_construction_expected |
| divider_absent | absent | absent | {"internal_divider":"absent"} | matches_construction_expected |
| target_occluded | present | unknown | {"internal_divider":"unknown"} | not_scored_visibility_review_pending |

清晰样本的描述性结果计数：{"matches_construction_expected": 2, "false_positive": 0, "false_negative": 0, "abstained": 0, "unavailable": 0}。遮挡图的真实回答单独保留，不纳入该计数。它说明本次模型实际选择了什么，不能用未审核的遮挡标签宣称三项全对或稳定准确率。

## 构造与控制

新书架使用本轮静态检查过的 Pillow 轻量程序绘制固定仿正交 2.5D 视图；1024×800、2倍超采样。所有样本保留相同书架外框、层板、上下层书籍、颜色、投影和背景。明确区别于此前 bw_0074 和旧正视矩形 Oracle 对照，没有运行历史 Agent 代码或 Blender。

存在/缺失两图仅增加或移除最上方开口内连接上下边界的竖向薄板；没有移动书籍。遮挡样本沿用存在图的结构，并增加位于前景的布帘，覆盖最上方开口。新增遮挡物会改变颜色、遮挡、边缘，这是可见性控制的必要变化，不宣称只改变一个像素因素。仿正交图是程序化示意场景，不能代表复杂真实图片能力。

场景配置、独立 PNG、预先冻结的构造真值和可见性记录均位于 `/srv/lab-disks/disk2/users/xymo/projects/e-harness/runs/structural_visual_e270c5514c5b4bbe99b84e2c0782dd87`。程序主入口设置单核亲和性、30秒 CPU/进程、1GiB 地址空间限制；不启动 GPU 或渲染器。初次 prepare 观测用户 CPU 约 0.644 秒、峰值 RSS 108.8 MiB；另一次轻量单图预检修正为普通单进程 CPU 绘图，未将主入口限制扩称为所有辅助工具调用的硬配额。

首次图像预检发现遮挡图仍露出一小块隔板顶面，因此在任何验证调用与最终标签冻结之前，将布帘向上扩展一次；原草稿保留，记录见 preflight_note.json。该修改仅依据图像可见性检查，未看到模型结果、未改 Prompt。最终 A/B 像素差异范围为 (482, 90, 540, 391)，其他布局未改变。

## 标签、审核与冻结

在首次验证前，冻结了相同 System/User、唯一字段 internal_divider 的 present/absent/unknown Schema，以及 expected_frozen.json（只读）。present 要有内部结构隔板的可见证据；absent 要目标层可观察且确认无隔板；遮挡/类别歧义时 unknown，不能用未看到替代不存在。外框、书脊、阴影和布帘都不计隔板。

遮挡样本另由主 Agent 在请求前静态检查图像，记录可观察性候选，不从其几何存在真值直接继承可见答案。其 unknown 仍只是**未独立人工审核的可见性候选**：human_visibility_review=unreviewed，因此无论实际回答如何均不计算正确/错误。两个清晰样本按 construction_expected 作描述性比较，也不是独立审核 GT。没有在结果后改图、改标签或改 Prompt。

## 输入隔离和真实请求

三个模型接收匿名随机路径的单张原始图及完全相同的简短问题，只针对最上方开口内的内部竖向隔板。没有 A/B/C 标题、条件名、预期值、其他图或历史结论。没有同时展示对照页给模型。fork_turns=none；工具日志、实际输入全文、模型标识和原始回答保存在每项 observation。核对通过：冻结时间早于全部会话、输入提示除匿名路径外完全相同、匿名 PNG 与冻结图片逐字节相同且无附加元数据。

共享文件系统未实施单文件权限沙箱，持久日志不能独立明文验证父任务正文；因此不声称严格盲测或与固定 API 相同。可审计的是模型标识、各次只读取指定单图的工具轨迹和原始回答。Ofox 不可用且本轮没有调用，也未读取密钥。

## 如何解释本轮证据

存在图若 present、缺失图若 absent，可作为实际视觉区分的初步证据；unknown 为弃权，不强行算作正确/错误。明确输出相反类别分别记录漏检/误报。遮挡图若 unknown，仅说明本次表现符合冻结的弃权候选，需独立可见性审核后才能验证弃权正确；若给出确定类别，记录潜在无依据确定性，不能直接归为重建错误。

本轮不能证明提取器稳定区分复杂隔板、书脊或外框：只有一个新布局、每种条件一个观测，未测试倾斜/透明/合并几何、遮挡程度梯度或真实图片。布帘也可能成为易识别的弃权线索；清晰 present/absent 的简单结构不能代表真实书架中细隔板漏检已解决。未发生模型失败时也不得以零失败宣称稳定可靠。

## 实际成本与复现

共 3 个真实验证会话、26.879 秒；Token 为 {"input_tokens": 132791, "cached_input_tokens": 90112, "cache_write_input_tokens": 0, "output_tokens": 323, "reasoning_output_tokens": 65, "total_tokens": 133114}。统计为验证子会话全量平台/图像工具上下文，排除主 Agent；缓存已包含在输入、推理已包含在输出，不重复相加。Codex 货币费用不可核实；Ofox 请求 0。未修改历史结果、Reference Evidence、ROI 或正式权重。

仅从冻结数据及真实会话回答重画到新目录（不调用模型）：

```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/structural_visual_controls.py --stage report --output /srv/lab-disks/disk2/users/xymo/projects/e-harness/results/structural_visual_verifier_controls --destination results/structural_visual_verifier_controls_replay
```

输出 comparison.png、verification_results.json、report.md，无 HTML。完成后停止，没有重复调 Prompt 或扩展样本。
