# Region Grounding + Conflict Resolution：bw_0074

结论：目前不能确认“默认SAM3即可稳定地得到内容完整、背景干扰少的粗Region”。本轮可以保证冲突后的Mask无重叠、编号顺序不影响归属，但缓存候选缺失的工作设施和音响设备无法靠冲突消解恢复。禁止人工修补，全部候选未审核，不进入正式评分。

本轮仅复用上轮成功的4区VLM JSON。新付费API请求0次、新模型推理0次；两次GPU观察均为8张40GiB卡被其他任务占用，每张约31GiB、16个外部计算进程。因此没有启动新SAM3/DINO。官方代码、隔离环境和本地sam3.pt仍存在，Plan通用生成的提示保存在plan_derived_sam3_prompts.json，**没有执行**。

## 对照与三轮固定规则

|方法|候选并集覆盖|区域重叠|Unassigned|
|---|---:|---:|---:|
|A_baseline|86.45%|12.30%|13.55%|
|round1_B_union|64.52%|32.18%|35.48%|
|round1_C_resolved|32.34%|0.00%|67.66%|
|round2_B_union|64.52%|2.13%|35.48%|
|round2_C_resolved|64.17%|0.00%|35.83%|
|round3_B_union|51.83%|0.39%|48.17%|
|round3_C_resolved|51.82%|0.00%|48.18%|

上表均为原图像素并集/交叠统计，不是准确率。Unassigned包含背景与漏掉的前景，不能视作已确认背景。Global/Dense Patch始终负责全图覆盖，不能以Region覆盖率越大越好选择方法。

- A：直接复制历史Region-first SLIC/DINO粗块支持，未重新调其窗口。
- 第1轮 B：VLM名称/内容名词与历史SAM3类别匹配后取并集；C对所有区域冲突对称弃权。结果虽无重叠，但大范围共同书架候选使大量正确内容一并被弃权，是保留的失败案例。
- 第2轮 B：若某概念直接命名另一Region，则抑制当前Region对该概念的顺带提及；例如组成描述中的“书架上”不能自动吞并整个书架。C以语义匹配、面积特异性、SAM边界内侧距离、软位置先验比较支持，差距不足0.08则Unassigned。没有按R编号、预设优先级、手工像素或bbox裁剪。
- 第3轮：对同一概念先在同一历史提示来源内取并集，再对多个来源取交集，之后沿用第2轮归属规则。单来源保留并标记single_source_unverified，不把零检测当物体不存在。交集减少一部分宽泛支持，同时损失书架陈列与沙发织物，是保守诊断，不宣布更优。

归属支持的启发式公式：semantic × (1 − 0.5 × candidate_area_fraction) + 0.04 × mask_interior + 0.04 × position_prior；名称匹配0.9、组成匹配0.85。区域内多个候选取max，重复候选不会累加票数。所有权重均未校准；没有使用SAM分数作为正确概率或Evidence reliability。只生成候选，reliability=0。阈值全局固定，没有按这张图扫参。

## 逐区静态检查与失败

- R1工作区：显示器、透明椅等可保留；书桌、台灯、笔记本整组缺少历史候选。大量工作台背景仍被宽泛书架候选归入R2。不能声称工作区完整定位。
- R2展示书架：陈列物和框架有支持，但宽泛候选带入工作区墙板、桌面、部分下柜/地板；跨来源交集仍未解决语义边界。第1轮完全弃权导致严重漏分，第3轮交集又产生孔洞和碎片。
- R3唱片与音响区：主要只得到部分唱片；收录机和唱盘没有对应历史Mask，保留了明确的完整性失败。新生成提示包括实际Plan中的boombox/turntable，但GPU不可用，未推理，也未把唱片Mask延展成音响Mask。
- R4沙发区：大部分可见主体有历史Mask支持，背景混入比旧粗块更少的视觉迹象需要人工确认；织物、抱枕边界仍有漏分，第3轮交集尤其丢失部分彩色织物。无人工GT，不声称准确率提高。

以上是助手对参考图与Overlay的静态检查，**不是人工审核通过**。最终4区数目沿用VLM，无逐书逐唱片评分；多连通分量可以组成一个Region，但碎片/孔洞仍需审核。各方法每区Overlay、原始候选、冲突图和Unassigned图均保留。

第2轮C可作为较宽松的人工审核候选；第3轮作为更保守的失败对照。两者都不应自动冻结为正式Evidence。所有最终C均0重叠，仅证明几何互斥，不证明语义正确或内容完整。

## 来源与泛化限制

复用25个真实历史SAM3候选（文本和Visual两类）。Visual来源含之前助手提供的松bbox，文本概念也是参考侧固定提示；它们不是本轮由VLM Plan自动新生成的分割。当前同义词表是有限的中英文名词匹配，未验证开放词汇泛化，不能当作完整语义理解器。

bw_9064、bw_0073的已有SAM3候选元数据已清点，但没有成功的Region-first VLM Plan；bw_9064上次多任务回复结构失败，不能拿局部残片或手工Evidence当有效Plan。本轮不调用付费VLM、不凭目标答案补Plan，故真实跨场景Grounding验证阻塞。详见generalization_audit.json。

## 工程、验证与成本

新增/修改：benchmark_evidence.py中添加通用概念提取、Plan提示生成、SAM候选关联、对称冲突消解和跨来源一致支持；新增scripts/region_grounding_experiment.py；扩展tests/test_region_hierarchy.py。复用现有Evidence loader、原始RGB、SLIC/DINO基线、SAM3官方历史产物。未修改五能量数学公式、权重、Runtime blocked或历史产物，未执行Agent/Blender，未提交Git。

evidence.json沿用regions/anchors/relations格式（没有新建Anchor/Relation），所有reviewed=false、mask_reviewed=false、reliability=0。无支持的Region仍保留并标unavailable_no_valid_support，不伪造零误差。独立Region Mask默认来自resolve_region_conflicts，其Unassigned为精确补集。

本地CPU实验约37.47秒（含保存图、真实图像顺序置换复查；不含人工等待）。本轮GPU峰值与SAM3新推理时间为N/A，未拿旧GPU占用充当新测量。API成本0次请求；没有下载模型/依赖。测试详见tests.log，产物和互斥不变量见validation.json。

不计算IoU、Boundary F1、真内容召回率或分割准确率；candidate_retention.json只是与同一批输入Mask的一致性比例，不是独立质量证据。泛化未完成，默认新SAM3是否稳定尚未得到本轮验证。

## 复现（CPU缓存模式，零API）

```bash
cd /home/xymo/projects/e-harness
OUT=results/region_grounding_conflict_resolution_replay
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
/home/xymo/environments/relateanything-inference/bin/python -B scripts/region_grounding_experiment.py --output "$OUT" --phase initial
/home/xymo/environments/relateanything-inference/bin/python -B scripts/region_grounding_experiment.py --output "$OUT" --phase round3
/home/xymo/environments/relateanything-inference/bin/python -B scripts/region_grounding_experiment.py --output "$OUT" --phase finalize
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -v
```

输出目录必须不存在，避免覆盖。新SAM3 Plan提示需要空闲GPU才能执行，本脚本不自动加载模型或连接网络；当前结果明确为缓存候选探索。已到3轮上限，本轮停止。

完整CPU测试实际运行101项全部通过（新增8项Grounding/Conflict测试），无真实API请求。验证7组四区Evidence及63个HTML本地链接；详见tests.log与validation.json。resource_checks.json保存两次GPU只读观察；comparison_round2.png是原图/A/B/C的单张总览。run.json记录初始两轮，experiment_summary.json汇总实际三轮。

碎片诊断：第2轮C的R1/R2/R3/R4连通分量数为[5, 222, 29, 31]；第3轮为[2, 85, 28, 72]。这不是物体数量或准确率，包含遮挡、分散集合与碎片噪声，未自动删除小块或补洞。
