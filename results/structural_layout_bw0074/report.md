# bw_0074/R3 Structural Layout 自动提取最小实验

结论：独立提取确实产生了隔板组织差异信号，但**冻结的纯 VLM 比较保留 Unknown**，因为 Render 四层都返回 partial。场景几何辅助检查额外支持第 1、3 层的 `candidate_structural_layout_mismatch` 假设；这组补充假设属于事后探索，没有覆盖或提升模型原始 certainty。Reference 第二层疑似漏检，不能宣称本轮完整识别所有结构差异。

全部 reviewed=false、provisional/debug；没有正式 Spatial 分数或第六类 Energy。未改变 Region、ROI、历史回答或评分权重。

## 实际输入和隔离

复用原 Reference、历史 Render 和固定 R3 bbox [883, 119, 1258, 541]。Render 只按既有等比例全帧缩放及留边规则映射到 Reference 坐标，没有配准或移动 ROI。每个子 Agent 仅收到一张匿名 PNG：左为一侧完整原图及橙框，右为同坐标 2 倍放大的 R3。原图没有另一侧或预期标签，也没有 U1–U7、历史答案、几何对象信息或本轮预期结论。

使用用户指定的 System/User 原文，另冻结统一输出/坐标定义：自上而下可见开口层带，内部竖隔板不含外框；水平线只标内部层板；粗坐标为目标裁剪图 0–1000。Prompt 没有给示例数量。匿名实际输入图、完整请求文本、协议和原始会话输出位于 `/srv/lab-disks/disk2/users/xymo/projects/e-harness/runs/structural_layout_4c14a310f5124e489572e4afedbca517`；topology_reference/render.json 保存模型标识、原始回答和工具读取审计。

严格串行 2 个新 gpt-6-sol 子 Agent，各一次、不重试，fork_turns=none。日志均显示只读取各自一张匿名图，模型标识核对通过。共享文件系统并无强制单文件隔离，持久日志也不能独立明文重读父任务正文；主 Agent 已知历史结构，因此不能声称严格盲测或固定 API 等价。没有追加验证。

## 模型实际结构与冻结比较

两侧均报告从最上到最下可见开口完整，均为 4 层和 3 条内部水平层板。这个计数来自本轮独立结构识别，**不是 U1–U7 与三个唱片高度组的 7−3**。Reference 行 certainty 均为 clear；Render 均为 partial，原因原文为“左侧边界超出目标裁剪图，无法确认各层开口向左延伸的范围。”

| 自上而下层次 | Reference 隔板 / 柜格 | Render 隔板 / 柜格 | 冻结纯 VLM 比较 |
| --- | --- | --- | --- |
| 1 | 1 / 2 | 0 / 1 | unknown |
| 2 | 0 / 1 | 0 / 1 | unknown |
| 3 | 1 / 2 | 0 / 1 | unknown |
| 4 | 0 / 1 | 0 / 1 | unknown |

程序只在双方确认垂直范围、开口层数相等时按上到下顺序比较，未建立逐柜格 ID 匹配，也未重排空间位置。对 clear 观测中明确不同的隔板/柜格数量，预先测试的规则返回 candidate_structural_layout_mismatch；对 partial/unknown 仍弃权。因此这轮纯 VLM 实测没有通过可靠性条件的逐层差异，不能拿受控单元测试通过冒充真实自动检测成功。每层隔板变化与柜格变化是同一结构事件，不重复施加惩罚。

## Scene Graph 辅助证据与额外候选

只读取既有 scene_graph.json。名称用于检索候选后，实际检查了三块宽 1.65 m、深 0.522 m、厚 0.055 m 的独立 Mesh：均为 8 顶点/6 面的薄水平立方体，无 modifier、未 hide_render，已有包围盒投影与目标位置相符。它们位于约 z=1.42、1.87、2.33 m；上下外边界由既存桌高层板与顶冠几何限定，形成四个粗开口区间。投影只代表包围范围，不是可见 Mask。

对全部已存 Mesh AABB 查询柜体内部的薄竖板：x 位置在长层板内部、厚度不超过两倍层板厚度、深度至少为层板的 80%、前后覆盖到层板深度容差内、并与开口 z 区间相交。**找到 0 个候选**。唱片薄片因尺寸/深度和位置条件不会被当作这些全深隔板；柜体左右框不算内部隔板。没有以对象名称或对象数量直接代替柜格。

在“独立全深薄板表示、粗开口顺序可比”的条件下，第 1、3 层 Reference 明确隔板观测与生成侧连续长层板构成两个 **场景几何辅助差异候选**。这项补充分析在模型回答后完成，保存为 post_hoc_scene_graph_assisted_hypothesis；原纯 VLM Unknown 和 Render partial 原样保留。

该查询不是完备的隔板检测器：浅隔板、斜板、合并 Mesh、未评估 modifier 几何可能遗漏；不把“查询为空”升级为确认三维缺失。历史读取器兼容性、像素可见性也未在本轮重新认证。因此这些是可审核的结构布局不一致候选，不是 Reconstruction Error GT。

## 提取失败与可视化

Reference 第二层模型输出 0 隔板、1 柜格且 clear；事后静态检查与既有 U3/U4 候选提示该层左侧约四分之一处可能有竖向结构隔板。图中单独放大，未把该位置加入模型预测线，也未将答案修正为 1/2。此为待独立人工审核的漏检候选；没有用旧单元作为模型输入或预期标签。

comparison.png 的青线/黄线直接来自实际模型输出，未修补。Render 红色层范围只表示几何辅助的候选差异，不虚构缺失隔板在 Render 中的精确位置。完整定位坐标、未知说明和原始回答均保留。

## 相比唱片 Group 验证增加什么

旧方法回答集合存在、多柜格、主要竖放，三个结果 satisfied，但不描述柜体本身。新结构证据可表达每层是否左右分隔、隔板是否错层，以及“分开的柜格变为连续开口”的候选变化，不需逐张唱片或逐柜格匹配。

本轮实际新增的是两条带条件的几何辅助布局候选及一条 Reference 提取失败候选；没有证明稳定检出率，也没有自动确认所有结构缺失。历史相机不同、固定 R3 左缘裁切导致 Render 弃权；柜内遮挡与隔板/封套边缘混淆影响 Reference。相同行数不能单独证明物理层架身份相同。

值得继续作为 Spatial 的辅助候选证据研究，但目前不能直接纳入正式惩罚。下一步需要独立人工审核结构线与层带可比性，验证同视角已知有/无隔板的正负对照，并校准 partial 与 unknown 的判定；本轮不执行这些扩展。

## 执行、测试与复现

2 个真实子 Agent 会话共 51.425 秒。Token：{"input_tokens": 92466, "cached_input_tokens": 75520, "cache_write_input_tokens": 0, "output_tokens": 1988, "reasoning_output_tokens": 1418, "total_tokens": 94454}。统计包含验证子会话的平台上下文、图像工具阶段，排除主 Agent；缓存包含于输入、推理包含于输出，不重复相加。实际货币成本未知。Ofox/Blender/GPU/SAM/SLIC 调用为 0。

5 项离线单元测试通过：清晰合并产生候选、部分可见弃权且不强制对齐、非法坐标/重复 ID 拒绝、响应失败不伪造零误差，以及几何辅助假设不改变原 VLM partial/Unknown。前 4 项在模型运行前完成，第 5 项用于事后辅助通路的隔离检查。初次模块式测试调用因 tests 不是包而失败，改用 discover 后通过；不是模型或指标测试失败。实际两个响应 Schema/坐标合法；源文件大小与 mtime 检查未变。

只重放已有回答并画到新目录，不调用模型：

```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/structural_layout_pilot.py --stage report --output results/structural_layout_bw0074 --destination results/structural_layout_bw0074_replay
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p 'test_structural_layout_pilot.py'
```

输出为 PNG、三个 topology JSON 和本报告；准备阶段协议保留在 verification_results.json。无 HTML、无历史结果修改、无 Git 提交。完成后停止。
