# 指标适用范围与人工有效性状态

以下数值直接读取冻结报告，不重跑DINO或其他指标。可计算覆盖率不等于正确率。全部历史相机不合规/未验证，正式成绩0。

| Energy | 有条件数值配对 | 有效记录/计划记录 | 实际含义与限制 |
| --- | --- | --- | --- |
| semantic | 0/13 | 0/17 | N/A；Group/Atomic未审核且仅诊断，候选数量不是分数 |
| spatial | 13/13 | 52/116 | Dense图像边缘代理；无可靠RGB对象定位/对应，连续空间N/A |
| appearance | 13/13 | 65/129 | 真实图像颜色/纹理差异，仍受视角、可见性、尺寸适配影响 |
| statistical | 13/13 | 104/198 | 纹理统计/多尺度边缘分布代理，不是书籍/唱片真实密度或数量 |
| perceptual | 13/13 | 65/129 | 已运行DINOv2 CPU特征差异；并非语义正确性概率，局部尺寸/上下文仍有限制 |
| structural | 0/13 | N/A/N/A | N/A；13个.blend存在，但无绑定的已评估穿透、支撑、退化检查 |

## Geometry盘点

13/13原生.blend路径存在，本轮全部未打开。13/13绑定geometry.json均unavailable，无碰撞记录、支撑记录或evaluated components。仅bw_0074有900对象的已有Scene Graph和低分辨率Group-ID缓存；基础网格边界/变换、名称和像素可见支持不能验证接触/碰撞或结构退化，也不证明与历史PNG逐像素同步。详见evidence_validity.json逐配对库存。未发现足以安全启用Structural评分的现成数据；未执行新提取。

## 待人类标注后才可报告的有效性

Reference Evidence正确/可观察比例、两侧VQA正确性、候选差异确认、satisfied误判、unknown/ambiguous适当性、盲审未覆盖差异、重复底层问题和相机影响目前均pending。逐配对判断可审查，但Reference相同的task_id/evidence_id只算一个参考命题；不能把107条当107条独立Reference真值或独立物理错误。按任务和运行链聚类，按输入及完成状态分层；本轮不排名、不估计总体准确率。

审核后的Group/Structural Layout命题仍可作为Spatial/Statistical诊断；正式接入需明确比较定义、可靠定位或经验证的语义测量及协议合规。图像中的隔板布局属于Observation Spatial，不等于独立3D Structural接触/支撑检查。
