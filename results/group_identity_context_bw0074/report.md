# Group Semantic Identity 与上下文依赖

**post-hoc exploratory / Codex Subagent gpt-6-sol / reviewed=false / provisional/debug**。最多4个验证子Agent，实际每图一次、串行、无重试、无Ofox。不修改此前R3三个satisfied，也不生成正式Energy。

## 先冻结Reference裁剪与问题

沿用参考图 `/srv/lab-disks/disk2/users/xymo/projects/e-harness/results/vlm_direct_grounding_cross_scene/bw_0074/reference.png`、已有固定R3 ROI `/srv/lab-disks/disk2/users/xymo/projects/e-harness/results/coarse_evaluation_roi_bw0074/B2_edge_polygons/R3.png`。完整R3输入取其外接矩形 [883, 119, 1258, 541]；仅陈列输入为 [883, 119, 1258, 322]，保留Reference上方两层柜格，排除下方收录机和唱机。坐标均为Reference原始1258×855网格的xyxy、右/下界不含；由协调Agent只看Reference作粗裁剪，不是自动Grounding或独立人工GT。裁剪、Prompt及Schema先保存在只读 `runs/group_identity_b2a12569436543f2b0bafdb796ff955e/frozen_plan.json`，本轮再次读取Render前冻结。

Render按此前已保存的等比例全帧缩放/居中留边规则映射到参考网格，之后使用完全相同裁剪坐标；不移动ROI或重对齐。所有输入都用统一2倍LANCZOS放大、无文字/类别提示/覆盖涂黑，匿名PNG目录每个只有一图。图片大小不同是裁剪范围不同的直接结果，显示目标的像素放大倍数一致；并非只删设备且其余像素集合完全相同的因果消融，因为局部输入同时删去较低柜格。模型只接收一张图及同一冻结问题/分类规则，没有Reference/Render身份、条件名称、预期类别或其他答案。

唯一问题：**目标柜格内主要可辨认的陈列内容是什么？** 输出单个category，严格枚举vinyl_sleeves/books/other/ambiguous/absent。需要陈列内容本身的可见证据，不得只从附近设备猜测。ambiguous是证据不足；absent要求柜格清晰且确实没有集合，不能用裁掉/没看清替代。完整原文在JSON.protocol。

## 原始回答与裁剪可比性

| 输入 | 原始回答（未改写） | 协调Agent可见性初审，未人工审核 |
|---|---|---|
| reference_context | {"category":"vinyl_sleeves"} | target_visible |
| reference_display | {"category":"vinyl_sleeves"} | residual_context |
| render_context | {"category":"ambiguous"} | target_visible |
| render_display | {"category":"ambiguous"} | partial_target_visible |

完整→局部确定性比较：reference：vinyl_sleeves → vinyl_sleeves（satisfied）；render：ambiguous → ambiguous（unknown）。
两枚举都明确且相同记satisfied，不同记candidate_violated；任一ambiguous记unknown；解析/调用失败或目标裁掉不可比较记unavailable。raw_label_changed另外保留是否变化，不把ambiguous当作一个已确认错误类别。这里的candidate_violated指输入上下文下分类变化候选，不是Agent重建错误。全部原始回答完整保留，不改写为GT。

## 解读与限制

reference：两种输入保持同一类别；这只是本次观测稳定，不证明正确或不依赖任何上下文。 render：完整和局部都无法可靠确定类别，未观察到去除上下文后的明确类别改变。 本轮不能将此前三个satisfied追溯改为错误；新分类问题的任务、选项与输入均不同于此前是否存在/多个柜格/竖直陈列的二值问题。它揭示本次类别证据的可用性，不直接证明此前回答来自设备推断。

裁剪初审在验证前完成，均未获独立人工确认：Reference局部仍保留右缘一小块扬声器和左缘植物，因此不是彻底去除全部背景的输入；Render局部含更多顶棚/墙面，保留一整排及部分下一排陈列，目标没有完全被裁掉，但可见成员范围与Reference不完全相同。分类行为可作有限诊断，不可用于完整Group数量/密度比较，也不是严格的成对因果对照。若目标完全被裁掉，程序比较会记unavailable，不移动裁剪框。

应分别读取Reference和Render的完整/局部回答：出现明确类别→ambiguous，只能说明这一观测的局部证据不足；明确类别改变是输入敏感性候选；保持相同类别也不能证明模型独立于上下文或分类正确。单侧每条件仅一个观测，模型随机性和裁剪改变可见集合成员都可能影响结果，不能把变化完全归因于音响设备。没有独立类别GT或书籍/唱片混淆负对照，也没有独立人工可比性审核。

历史相机并未配准，Reference真实相机未知，Render不满足正式固定T0证据要求。相同参考坐标可能在Render中含更多背景或截去部分柜格；详细可见性在JSON.crop_comparability。若裁掉目标，不迁移裁剪框去寻找它，更不能将其认定为Confirmed Missing。

协调Agent已知此前Render与三个satisfied，不能称参考准备严格盲测；本轮裁剪选择本身是事后探索。验证Agent通过fork_turns=none和匿名路径减少泄漏，实际模型、输入模板、单图工具读取、原始回复及用量保存在JSON.answers。共享文件系统没有强制单文件访问边界，持久日志无法独立明文重读父任务正文，因此不宣称严格隔离或与固定API等价。未要求模型解释/反思，不能从最终一字段回答还原其实际视觉依据。

4个完整验证会话共 51.364 秒；Token {"input_tokens": 176208, "cached_input_tokens": 145536, "cache_write_input_tokens": 0, "output_tokens": 851, "reasoning_output_tokens": 487, "total_tokens": 177059}，包括子会话平台上下文和图像工具阶段，不含主Agent。缓存包含在输入、推理包含在输出，不重复加总；Codex实际货币成本未知。Ofox调用0，不读取凭证。14项CPU单元测试通过（本轮6项、沿用三字段协议的回归测试8项）；输入检查和最终完整性检查存于 `runs/group_identity_b2a12569436543f2b0bafdb796ff955e`。未运行SAM/SLIC/DINO/Blender或历史Agent代码，未修改正式Energy/权重，未提交Git，没有HTML。

## 离线复现

在项目目录，仅重放既有真实回答并重画到新的目录，不调用模型：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_identity_context.py --stage replay --output results/group_identity_context_bw0074 --destination results/group_identity_context_bw0074_replay
```

完成本轮四图后停止。
