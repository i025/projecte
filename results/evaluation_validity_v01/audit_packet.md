# Evaluation Validity v0.1：人工审核包

状态：pending human review；reviewed=false；provisional/debug。只读取冻结批次，0次新模型、Blender、Agent或指标推理；原问题、回答、Energy及权重不改。

## 分发与冻结顺序

1. 协调者只向独立人类审核者分发服务器私有 `private/stage1_blind/` 和 [空白差异表](blind_difference_template.csv)。此文档、协议分层、问题表及其他历史实验**不要**同时分发。中性编号P001等只用于回填。软件不能保证人类没有先验知识，审核者须填写prior_exposure。
2. 先看每组全图：`*_full.png`是历史模型共同坐标输入；`*_native.png`是两侧原始全图的独立等比展示，非配准。先冻结全图自由记录，再看固定Region近图并追加观察。Region范围来自VLM，可能形成注意偏差，不属于完全无提示盲审；近图不含问题、答案或状态。三个空槽不是差异数，可追加行或填“未发现明确差异”。
3. 第一阶段副本冻结（填写UTC时间，并保留原副本）后，才分发私有 `private/stage2_evidence/`、[107条证据审核表](human_review_template.csv)。每项保留冻结claim、问题、类别空间、双方真实回答和程序状态；对应Region近图在第一阶段目录，映射位于仅协调者可读的 `private/coordinator_key.json`。
4. 优先完成全部13条candidate_violated、3条unknown，以及26条分层satisfied，共42条。priority_reason为空的其余项可随后扩展至全部107条。样本覆盖任务×证据类别及每组配对，是确定性覆盖抽样，不能外推91条satisfied总体误判率。
5. 保存填写后的**独立文件**，不要编辑冻结输入、原始JSON或空白模板。`review_status=completed`、`reviewed=true`只由真实人类填写；使用匿名审核者ID和UTC时间，实际姓名不公开。机器无法认证审核者身份/独立性。

## 逐条审核

先判断Reference命题本身是否可观察、成立，再独立判断两侧VQA答案是否正确。`satisfied`只表示答案相同，不能代替图像质量判断；`candidate_violated`不是已确认错误。unknown/ambiguous的弃权适当性要结合可见性。原生高分辨率能辨认而模型输入不能辨认时，在image_support中区分，不能忽略分辨率限制。

- `reference_observability`: observable / not_observable / uncertain
- `reference_evidence_validity`: valid / invalid / uncertain
- `reference_answer_correctness`: correct / incorrect / uncertain
- `render_observability`: observable / not_observable / uncertain
- `render_answer_correctness`: correct / incorrect / uncertain
- `comparison_judgment`: reasonable / unreasonable / uncertain
- `candidate_difference_confirmation`: confirmed / not_confirmed / uncertain / not_applicable
- `satisfied_false_negative`: yes / no / uncertain / not_applicable
- `abstention_appropriateness`: reasonable / unreasonable / uncertain / not_applicable
- `camera_confound`: yes / no / uncertain
- `occlusion_confound`: yes / no / uncertain
- `category_confusion`: yes / no / uncertain

所有人工标签默认为空；review_status初始unreviewed。`candidate_difference_confirmation`只用于候选差异，`satisfied_false_negative`只用于satisfied，其他项可填not_applicable。`satisfied_false_negative=yes`指本条冻结问题对应的事实确有可比较差异，却被相同回答漏报；未被问题覆盖的其他外观或细节差异应进入盲审覆盖表，不能算成本题VQA错误。`image_support`记录图像位置和依据；`notes`记录不确定性。Render物体移出固定ROI但在全图可见时，不能直接确认缺失。所有相机差异仍待确认。

同一配对多条问题若描述同一底层问题，在`duplicate_issue_id`填写相同人类指定ID（作用域为pair_id），不合并或改写原判断；在`blind_difference_ids`关联第一阶段差异。evidence_validity.json列出同一Group/Anchor下多条candidate_violated的共享范围提示，**不等于确认同一物理错误**，不得据此去重打分。第一阶段发现但所有冻结命题均未覆盖的差异，另存人工覆盖关联表；没有此表，不计算漏检率/召回率。

## 已审核标注如何接入现有计算

当前CSV是有效性审查，**不是Energy输入**。`verification_adapter.validate_diagnostics()`即使收到reviewed=true也重建为未审核诊断，不能用改一个布尔字段开启评分。Group/Atomic VQA尚无通用数值映射；人工核准答案不等于核准一个0/1惩罚。

现有Manifest支持独立reference_evidence、render_evidence、geometry、triage、rules。人工审核后应另建显式标注文件，保留原始ID、输入图像与坐标来源、审核依据和限定为[0,1]的reliability；不能将VLM自信度当可靠性。`benchmark_evidence.reliability()`要求reviewed=true且非unknown、无冲突。Region Semantic可比较双方审核过的同ID category，存在性另需同类别审核occupancy。Anchor匹配支持human来源、input_view范围、可靠且已审核的anchor_verdicts；确认缺失须充分证据，不能由检测失败推出。importance仍独立于reliability。

Structural需要真实已评估几何加独立语义/物理规则：穿透状态+reviewed triage；支撑接收者、完整性、Z-up及排除其他附着；退化需完整 evaluated component affine_rank 与体积期望，多个平面部件还需联合空间秩。名称、AABB或Group-ID不得构造这些字段的“真值”。本批均N/A。

## 复现（只准备材料，不调用模型）

```bash
python3 -B -m scripts.evaluation_validity --source results/existing_scene_batch_20261025 --output results/evaluation_validity_v01_new
python3 -B -m unittest discover -s tests -p 'test_evaluation_validity.py'
```

须具备服务器私有原始图像及run_config；公开仓库不含第三方图片，无法单凭clone生成审核PNG。输出必须是新目录。收集真实人类副本后可用脚本的`--reviews`模式写入新的汇总文件；该汇总不修改Energy。图片仅私有，未获再分发许可，不生成HTML。
