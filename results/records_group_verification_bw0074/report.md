# 真实唱片 Group Verification Pilot

仅 bw_0074/R3 唱片与音响区中的唱片封套集合。后端 Codex Subagent/gpt-6-sol，2次独立、串行、单侧验证，无Ofox调用、无重试。所有证据 reviewed=false、provisional/debug，正式Semantic/Spatial/Statistical均N/A。

## 参考侧冻结与图像来源

先读原Reference及历史Region Plan、既有B2 R3 ROI，再冻结Group语义范围、三个问题、Schema；然后才读取本轮Render。只读冻结文件 `runs/records_group_87adcd00ebf84540acd9efe30551dfe3/frozen_plan.json`。Group是可辨认的黑胶LP封套陈列，排除装订书籍、设备和隔板；没有逐张ID、精确Group Mask、数目或密度GT。候选由协调Agent参考侧静态观察准备，并非自动VLM提取或独立人工标注。问题本轮新增，不追溯声称来自旧冻结书籍证据。

Reference：/srv/lab-disks/disk2/users/xymo/projects/e-harness/results/vlm_direct_grounding_cross_scene/bw_0074/reference.png。原始JPEG关联见 `results/region_first_pilot_bw0074/input.json`。Region Plan：/srv/lab-disks/disk2/users/xymo/projects/e-harness/results/region_first_pilot_bw0074/vlm_plan.json。固定ROI：/srv/lab-disks/disk2/users/xymo/projects/e-harness/results/coarse_evaluation_roi_bw0074/B2_edge_polygons/R3.png。同一ROI成员像素用于两侧；放大框仅由其外接矩形导出，未按Render调整。

Render：/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/runs/official-showcase-10-images-v2/bw_0074/bw_0074__KcPDLD8/artifacts/workspace/exports/modern_living_room.png；实际来源Run为 official-showcase-10-images-v2/bw_0074/bw_0074__KcPDLD8。既有pair_audit记录与重算像素一致。图像统一只作等比例全帧缩放、居中留边：{"original_size": [1920, 1300], "common_size": [1258, 855], "nominal_scale": 0.6552083333333333, "resized_size": [1258, 852], "offset_xy": [0, 1], "padding_is_not_observation": true, "content_alignment": false, "transform": "uniform full-frame fit with integer rounding, centered letterbox; no crop/search/warp"}。这不是相机配准。历史任务包含图片和额外场景文字，不是Strict RGB-only；无证据满足固定T0，Reference真实相机未知，Render独立相机参数未知，不执行Blender求取。历史Render是否与最终blend完全同步也未重新验证。

## 冻结定义与实际结果

yes需要充分可见证据；no需要相关区域足够清晰以确认命题不成立；模糊、遮挡、类别/柜格歧义时unknown。柜格必须有可见隔板/柜框，内部小簇不另算柜格；竖直陈列允许倾斜，不判断逐张角度，主次不清弃权。若唱片存在性未确认，后两个问题不得推定有意义的分布错误。完整相同Prompt和Schema保存在JSON.protocol，两个子Agent只看各自一张匿名PNG，不看另一侧、预期标签或历史答案。

| 问题 | Reference真实回答 | Render真实回答 | 程序比较 |
|---|---|---|---|
| 标记区域内是否存在可辨认的黑胶唱片封套集合？ | yes | yes | satisfied |
| 可辨认的唱片封套是否分布在至少两个清晰可辨的独立柜格中？ | yes | yes | satisfied |
| 可辨认的唱片封套是否主要呈竖直站立陈列（允许倾斜），而非水平平放叠放？ | yes | yes | satisfied |

satisfied仅表示两侧回答一致；candidate_violated仅是待审核差异；unknown/unavailable不伪造为零误差。保留独立字段比较与存在性依赖处理，原始答案不改写，不将语义缺失重复计入位置/排列。没有总分，也没有使用模型置信度。

## 能力、失败模式与迁移边界

实际两侧均为yes/yes/yes，三个比较均satisfied，candidate_violated、unknown和unavailable均为0。没有发现本轮三个命题所覆盖的差异；这不是三项独立人工验证成功，也不是三项Energy为零。模型没有弃权，只能记录这一行为，不能据此证明类别无歧义。

协调Agent在参考冻结后进行的静态复核候选（不是独立人工审核）：Reference封套侧缘的颜色、宽窄和倾斜更不规则，Render更浅色和规整；局部分簇、间隙与倾斜的可见差异并未触发这三个粗命题。当前没有可靠Group Mask、密度数值或逐张身份，不把这些观察写成确认的数量/密度错误。两侧仍均满足多层陈列和主要竖直这个粗描述。固定R3在Render顶部包含更多顶棚/墙面，且柜架投影高度不同，不能排除相机影响。完整未审核观察保存在JSON.static_review_candidates；冻结问题及证据未随之修改。

本轮可观察是否对集合存在性、至少两个柜格的粗分布、主要陈列方向给出一致或不同回答；这些能力可以沿用书籍实验的少量Group组织、独立单侧问答、确定性比较和弃权协议。但一对图片没有独立类别GT或唱片/书籍对照，不能证明VLM可靠区分二者。LP封套背脊、书脊、文件夹可能相似；已知区域和问句也会形成类别先验。

柜格判断受透视、遮挡、柜体结构变化影响。“至少两个”只反映粗分散程度，会漏掉同为多个柜格时的数量、占据位置、疏密和覆盖差异。主要竖直的二值问题不覆盖稀疏、小范围横放或倾斜角变化。没有Group定位，不输出连续空间中心、精确面积、密度或实例数；柜体颜色、材质、封套纹理等仍应由Appearance/Perceptual诊断，本轮不重算。

即使两侧均yes，也不能证明Group重建质量良好；即使回答不同，也可能是相机、可见性或识别差异。若目标在固定ROI外而全图可见，应人工检查Misplaced，不能判Confirmed Missing。需要独立人工逐侧确认类别、柜格与排列可见性，扩展独立真实类别混淆/遮挡对照并核验验证器，再讨论Group-level Statistical适用性。未审核候选不能直接转成Statistical Energy。

## 隔离、成本与复现

参考准备存在历史知识泄漏可能；本轮前置清点也读到了Inventory旧概括性书架差异描述，不能称严格盲测。验证子Agent使用fork_turns=none、随机路径/任务名，相同冻结文本，不接收源侧身份、预期、其他答案。单图读取可通过工具日志审计；共享文件系统没有强制单文件权限边界，持久会话中父任务正文不可独立明文逐字核实，因此不宣称严格隔离或等价固定API。实际工具调用、原始回答、模型标识和用量保存在JSON.answers。

两个完整验证会话累计 24.660 秒；Token统计 {"input_tokens": 92427, "cached_input_tokens": 75264, "cache_write_input_tokens": 0, "output_tokens": 308, "reasoning_output_tokens": 115, "total_tokens": 92735}，包含平台上下文、图像工具阶段及最终答案，排除主Agent；缓存输入、推理输出分别包含在输入/输出，不重复加总。Codex货币费用未知，Ofox调用0，不声称免费。

8项CPU单元测试通过，覆盖独立字段可用性、非法/重复JSON、unknown、语义依赖和避免重复处罚。实际输入离线检查保存在JSON.offline_checks。准备时遇到系统无中文字体，改用已有DejaVu绘制英文显示标签；未下载字体或依赖，冻结的中文问句不变，发生在任何验证子Agent启动之前。原始RGB在完整图中保留原始像素，仅在ROI边界画细线；右侧统一2倍放大，不涂黑区域外内容。核实原图来源、ROI/源文件未改、模型/单图读取、冻结时序和离线重放的最终检查在同一work目录final_checks.json。

只重放已保存回答到全新目录，不调用模型、不读取凭证：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/records_group_verification.py --stage replay --output results/records_group_verification_bw0074 --destination results/records_group_verification_bw0074_replay
```

离线Schema/依赖比较及最终检查在 `runs/records_group_87adcd00ebf84540acd9efe30551dfe3` 中。没有HTML，未运行SAM/SLIC/DINO/GPU/Blender或Agent代码，未修改Grounding、五类能量、权重或历史书籍实验，未提交Git。完成本轮两侧验证后停止。
