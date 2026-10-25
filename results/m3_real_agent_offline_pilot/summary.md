# M3.0 Real-Agent Offline Evaluation Pilot

**两组历史配对；reviewed:false、provisional/debug；没有正式 Benchmark 成绩。**

本轮只读复用 bw_0073 厨房和 bw_0074 陈列书柜的既有图片、冻结 ROI/Group 与真实回答。0 次新的 VLM/CLI/Subagent/Ofox 调用，0 次 Agent/Blender/GPU 执行。旧 API 与 Codex Subagent 结果分别标明来源，不与新的固定 CLI 实验混同。

| Scene | Semantic | Spatial image proxy | Appearance | Statistical image proxy | Perceptual | Independent Structural |
| --- | --- | --- | --- | --- | --- | --- |
| bw_0073 | N/A | 0.02281487 | 0.21231670 | 0.05807331 | N/A | N/A |
| bw_0074 | N/A | 0.03623520 | 0.23010060 | 0.05878935 | N/A | N/A |

Spatial/Statistical 数字来自已有边缘/纹理代理，不是已验证的真实物体位置、密度或结构拓扑分数。Semantic 无已审核有效证据，Perceptual 本轮未运行 DINO，Structural 缺完整评估几何/审核条件，保持 N/A。未审核 VQA/Group/结构命题只进诊断；没有把 yes/no 或候选差异转为任意 0/1 Energy。

## 两组案例的主要发现

- bw_0073：岛台存在、四把椅子、吊灯在上方的旧回答全部 satisfied。它们没有覆盖岛台/吊灯的投影比例、材质与纹理等可见差异。独立历史柜体验证 K3 给出上下叠置抽屉样前面板 → 并排竖向门板的候选外立面组织差异；K1/K2/K4 为粗一致。没有把“外立面看起来像抽屉”解释为内部机构 GT。未验证的椅子支撑框架命题保持 unavailable。
- bw_0074：书籍存在与 3+ 柜格回答相同，mixed → upright 保留为 candidate_violated。旧操作定义较粗，R2右缘/R3混入、书籍/唱片混淆与相机都待审核；不追溯替换成后来更明确的书堆定义。唱片三条旧回答全部 satisfied，但另一个明确标为post-hoc的类别实验在Render回答ambiguous，因此身份比较为unknown，而不是已确认缺失或语义错误。
- bw_0074书柜：三条局部水平层板粗一致；V1/V3仅在“简单、独立、全深度板件”的几何查询假设下保留候选差异，image_only_status仍unknown。第二层Reference疑似漏检、左外框裁切和完整柜格计数保持Unknown。不能用柜格数简单相减，也不把未找到AABB候选当成视觉确认缺失。
- 颜色、材质、纹理、局部投影比例等差异未被少数原子问题完整覆盖；当前主要由Appearance和已有图像代理响应。本轮静态观察只是Codex后验审核候选，不是独立人工GT，不能声称“只有Appearance”在所有可能指标中有效。

## 坐标、相机与可比较性

bw_0073 原图7952×4333按既有thumbnail规则得到1536×837；Render1672×941全帧等比fit为1487×837，左留24、右留25像素。bw_0074 Reference1258×855；Render1920×1300按既有全帧fit为1258×852，顶部1、底部2像素无效。原始Reference与Agent实际输入字节一致，run/task/export映射及旧缓存像素本轮重查；没有内容对齐、移动ROI或相机优化。
厨房导出相机高度1.5m；书柜已有Scene Graph活动相机高度1.71m且平移/旋转也不同于T0。后者是已有场景快照，不证明历史PNG与该blend精确同步。Reference真实相机未知；两组均historical_camera。因此不能将二维差异直接归因为三维重建错误，Camera Error / Reconstruction Error不可分时保留不确定性。
固定ROI选择为厨房R2岛台+R4高柜、陈列场景R2书籍+R3唱片，严格复用各历史验证的范围；其余画面由Global和Dense负责。未审核ROI不参与正式局部聚合；重叠诊断单独保留，不把命名ROI损失直接相加。连续Spatial没有可靠RGB对象定位/对应，为N/A；没有借用合成Object-ID。

## 人工审核待办

逐条填写 evidence_audit.md：核对厨房K3的局部对应、前面板/装饰缝；书籍横放堆与竖放的可见性及R3混入；唱片身份与独立柜格定义；书柜第二层漏检候选以及V1/V3几何假设。判断裁切、相机、遮挡影响，确认来源与实际Render可见性；任何条目都未自动升级reviewed。
## 下一阶段受控真实 Agent 执行的必要条件

先单独审核可信Agent执行边界与资源限制，再由受控渲染链实际强制T0、记录实际内参及RGB/Geometry同次来源；统一固定参考坐标与有效像素支持，冻结Reference证据后独立验证。需要可审核的对象/集合对应、局部可观察性与弃权校准；Scene Graph名称不是GT，独立Structural还需评估几何、triage及规则。仅生成侧T0合规也不证明未知Reference相机与之对齐，仍需参考视角可比性证据或保留Camera不确定性。Runtime继续blocked；本轮不授权或启动下一阶段，不新增PyBullet、算法或权重。

## 复现与公开边界

需要服务器已有的合法Reference/Render与冻结缓存，公开仓库不分发这些第三方图片、ROI Mask或其衍生PNG。公开JSON/Markdown中的外部输入引用不是可下载资产；干净clone不能单凭公开记录重建受限素材。本轮本地 comparison/valid-pixel PNG 均不公开。

```bash
python3 -B scripts/real_agent_offline_pilot.py --output /tmp/projecte-m3-new
python3 -B -m unittest discover -s tests -p 'test_real_agent_pilot.py'
```

[审核表](evidence_audit.md) · [真实回答与Replay](verification_results.json) · [完整报告](report.json) · [接口检查](integration_checks.json)。这只是两组案例，不计算总体检出准确率；相同答案不表示重建质量好，候选差异也不是确认错误。


## 实际运行与CPU回归

两组已跑通 `build_reference → compare → aggregate` 与独立 `structural_report`。9项新增M3测试及完整395项CPU回归均通过，0失败、0错误、0跳过；回归时禁止真实网络连接及子进程启动。覆盖历史真实回答的Schema/逐字段比较、Unknown/Unavailable、错误图片关联、Mock不可冒充真实、历史结论不静默改变、mask:null的仅格式适配和条件几何的image_only_unknown。完整口径见 integration_checks.json → cpu_tests。

首次派生输入接入因旧可选Anchor的mask:null失败，原材料保留在本机bw_0073/；只将“无Mask”转换成省略该可选字段，不改原框、证据或审核状态。最终回放位于final_replay/。最后回放与前一次成功回放的Energy对象完全相同；未通过修改规则让实验通过。

厨房同ROI的历史DINO缓存经Mask/网格核对后，仅附在 diagnostics.cached_perceptual：R2=0.15655710、R4=0.18730614；不是本轮推理，不进入Perceptual Energy。R2旧输入有约45% bbox裁剪范围为黑填充，旧预处理可能干扰距离，不能视为已标定的独立语义误差。书柜没有对应缓存，仍N/A。

固定ROI Appearance：厨房R2=0.27086611、R4=0.22227121；书柜R2=0.26588370、R3=0.25322070。它们提供局部RGB差异强度，但不隔离相机、外观和几何原因，不直接相加。两组当前命名ROI彼此不重叠，local_aggregate仍为null。

只发布代码、测试及本文等五个根报告；图片、Mask、最终blend、完整会话日志、原始任务文字和中间重复报告不公开。公开元数据副本只做路径脱敏，原始回答、候选失败、Unknown和N/A不改写。此处为小规模历史案例分析，无总体准确率或排行榜结论。完成后停止，不启动M3后续受控Agent执行。
