# Evaluation Validity Study v0.1

基准：`77d9ec422cb240bb6c092bd2b56b2078efa4698b`。冻结输入13组、10个任务/Reference、80条独立参考命题、107条配对比较：91 satisfied、13 candidate_violated、3 unknown。本轮没有新增模型调用、Blender执行或指标推理，没有改问题、回答、Energy、权重或Runtime。

审核包已准备，尚无人类标签；所有有效性指标pending、reviewed=false、provisional/debug，不能发布正式成绩。

- [两阶段审核说明](audit_packet.md)、[107条空白证据审核模板](human_review_template.csv)、[39个可扩展盲审空槽](blind_difference_template.csv)。优先审核42条：13候选差异+3 Unknown+26条satisfied覆盖抽样，剩余可扩展。
- [协议分层](protocol_strata.csv)：3组RGB+通用协议、10组RGB+场景专属文字；9完整、4不完整检查点；12条已记录Agent运行链（厨房续接与超时检查点同链），10任务；不混合排名、不将检查点当独立样本。没有记录续接也不证明统计独立。
- 私有PNG：`private/stage1_blind/`（全图、原生全图、中性固定Region近图），`private/stage2_evidence/`（逐条冻结问答）。只向盲审者分发第一阶段；冻结后才给第二阶段。公开仓库不含第三方像素或私有路径映射。
- [有效性待审及Geometry库存](evidence_validity.json)、[指标覆盖和限制](metric_coverage.md)。全部历史相机正式资格false；Reference相机未知，PNG/.blend同步未知。相机、遮挡和重建差异不可强行分离。
- 现有reliability、Region/Anchor和Structural triage/rules可读取独立人工审核标注；Group/Atomic VQA仍仅诊断，无通用数值Energy映射，不能按候选数打分。13个.blend存在，只有一个Scene Graph/Group-ID缓存，无可用于实际碰撞/支撑/退化评分的绑定Geometry，Structural继续N/A。

需要人类：先独立盲审13组主要差异并冻结，再逐条确认命题可观察性、双方回答、比较状态、混淆和重复问题；同时披露先验暴露。Codex未填任何人类结论，没有将审核准备冒充独立审核。人类身份与隔离由协调者管理，软件不作认证。

复现命令及字段枚举见审核说明。CPU测试和公开审查完成后另存检查记录；本轮不开展新实验、不扩大数据集。
