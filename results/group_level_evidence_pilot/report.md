# Group-level Evidence & Evaluation Pilot

本轮只研究bw_0073中央岛台区、bw_0074展示书架区。两份真实Region Plan均确认目标ID为R2。3个Semantic Group、10条新原子命题、1个可选岛台Anchor，未列举或匹配全部物体；所有真实候选reviewed:false、reliability:0。没有新增评分层级、公式、权重或Group总分。

## Reference冻结及范围

Reference-only子任务独立查看原RGB和历史Reference材料，先写reference_groups_frozen.json并设为只读，再检查Render。主代理此前已经知道历史Render，整体不是严格盲测。来源标human_seeded_provisional，实际为助手目视草拟，不伪称新VLM提取或独立人工GT。冻结记录见reference_freeze_receipt.json；后续没有按Render修补命题或ROI。

- bw_0073/R2：一个高脚椅集合，关注可见细杆框架、椅背相对台面位置、横排组织。岛台仅因关系问题作为一个可选Anchor；不逐把创建ID。吊灯不新增本轮Anchor，旧吊灯问题仅保留历史上下文。
- bw_0074/R2：书籍陈列集合、独立装框图像集合。书籍不逐本计数；竖立/平放、封面朝向及书堆与框画关系作为候选证据。框画精确总数Unknown，不把“至少两幅”冒充确切计数。
- 唱片集合属于bw_0074的R3“唱片与音响区”，本轮排除，没有因探索提示而补入R2。地球仪、植物、小摆件等由Region/Global/Dense兜底，不为凑数建实例清单。
- bw_0073复用Direct Polygon R2；bw_0074复用已冻结B2 R2。后者历史Direct Polygon响应曾不合法，本轮不修补或重建ROI、不宣称B2是Group精确Mask。不同ROI表示是既有条件，本轮不比较Grounding优劣。

## 实际数据流与结果

Reference Region → Semantic Groups → Atomic Evidence → typed Questions → offline Verification → Energy Applicability已运行。

新增10问：9条unavailable、1条unknown、0条真实新验证，没有使用Mock填充结果。Reference未知精确框画数量在验证前就保持Unknown，其余没有对应真实回复，不能得到Semantic/Spatial/Statistical数值。所有Group对应状态Unknown；静态看到类似对象不自动升级Matched或Confirmed Missing。

历史真实三问已经重新严格解析并绑定：原始/缓存RGB直接字节比较、ROI解码成员比较（编码可能不同）、历史Prompt和输入上下文核对；不靠文件名或自行填写expected认定匹配。旧答案两侧均yes/4/yes，3条satisfied，只表示回答一致。q2只限定近相机侧可见高脚椅，不能自动代答当前Group的框架、排列、遮挡或密度；q1/q3不是新Group验证。没有新的付费请求或模型自我验证。

Region-only真实视觉诊断：

| Scene / Region | Appearance | Perceptual | 本轮来源 |
| --- | ---: | ---: | --- |
| bw_0073 / R2 | 0.270866 | 0.156557 | Appearance轻量重算并与缓存核对；Perceptual只重用同图同ROI旧值 |
| bw_0074 / R2 | 0.265884 | N/A | 新读可信历史PNG，现有numerical_errors；未找到该配对/ROI可重用Perceptual值，不运行DINO |

Region + Groups保留上述同一份视觉测量，不复制、不相加；增加10个可核验命题的类型、归属、来源和不可用原因。新Group三类Energy均N/A。当前结果只证明数据组织和程序门控可运行，未证明分割/语义准确率或错误检出率提升。

## 分能量适用性

1. Semantic：集合无需精确Mask即可提出具体VQA问题，例如椅架形态、书籍类别、飞机框画内容。接口能够处理；新问题无真实验证器回复，尚未证明自动语义验证可靠。旧岛台存在yes/yes不验证书籍或椅子关键属性。
2. Spatial：离散“椅背在台面下方”“书堆在飞机框画下方”可供VQA。连续中心、范围、比例必须有两侧独立可靠定位，当前全部N/A；没有使用Region ROI中心替代Group中心。Reference椅子粗框只作图示，Render没有据它复制对象位置。
3. Statistical：集合方向、横排规律可用定性问题避免逐成员ID；这些回答还需真实验证且不等于精确分布数字。椅子旧数量4→4是有限历史观察；书籍总数、Group面积、密度、占据图均不可测。不能把图像梯度统计称为书籍密度，也未新增计数差归一化公式。
4. Appearance/Perceptual：继续只做固定Region内的连续视觉响应，不拆算为书籍/椅子Group得分。颜色、纹理、细结构简化仍更适合连续视觉诊断；DINO受裁剪/黑底/面积及长宽比影响，旧值只在同图同ROI内复用，不跨Group面积比较。

## 真实Render的静态审核候选与漏检

详见static_review_candidates.json，均为冻结后助手静态观察，不是真实VLM响应、独立人工GT或已确认重建错误。

- bw_0073：都保留横排椅子，但框架连接/脚踏等形态不同；新框架问题更具体，不过宽泛的“主要细杆”仍可能两侧yes，不能保证捕捉所有差异。
- bw_0074书籍：可见书籍，但水平堆叠、正面大开本的对应不清楚；冻结的方向/封面命题可针对性检查。是否真实违反仍未知。
- bw_0074框画：能看到框体，但飞机题材和纵向小框画的对应受遮挡/简化影响；语义端点未知时关系也未知，不能硬判空间错位或缺失。

## Group、Anchor与重叠如何去重

Group是组织信息，不直接新增Energy行。每个原子事实只有canonical_fact_id及owner_id，显式alias保留审核信息但不再次生成问题/指标记录。已有Region Appearance/Perceptual只计算一份，Group没有复制像素损失。同一对象的Group presence与Anchor presence将来必须明确同一事实owner；已确认缺失只由该Semantic owner计一次，依赖的数量和关系不再完整处罚。检测器未检出不等于Confirmed Missing。

本轮没有把两个重叠Region的损失相加：每个场景只评一个冻结R2、两个不同场景分别报告。bw_0074书籍和框画的语义定义排除彼此，仍不能假定有互斥精确Mask。未来跨Region重叠实体也应沿用同一事实owner，不通过新增候选行改变正式聚合。

原有stage='group'表示多个Region归并，因此不用于这里的Semantic Group。保留现有三层计算架构，用semantic_groups侧字段组织Region内命题，Question仍level=region。reuse atomic_questions、replay_atomic_answers、load_document、record和aggregate，正式核心源码不变。N/A记录的aggregate仅显示本轮计划可用性，不代表完整Benchmark Coverage；Unknown和不可用没有删除。

## 相机与数据限制

bw_0073历史相机高1.5m，正式2m，Reference相机未知。bw_0074没有检查到独立最终相机JSON；PNG元数据可追溯到同Run导出blend，最终参数与逐项同步未重渲染验证，Reference相机也未知。只复用/进行全图等比居中留边，不裁剪、不搜索、不做内容对齐。所有结果provisional/debug，不能作正式三维重建Error GT。

## 测试与复现

新增tests/test_group_evidence.py覆盖Group归属、无Mask/无成员ID、Unknown/Unavailable、alias去重/冲突、不能升级审核、Mock不产分、历史side/source/raw/context绑定及旧问题不能代答新问题。实际测试日志见tests.txt（交付前写入），结构/引用/ROI与冻结检查见validation.json。

在项目根目录只用CPU重放（新目录必须不存在）：

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/xymo/environments/relateanything-inference/bin/python -B scripts/group_evidence_pilot.py --source /srv/lab-disks/disk2/users/xymo/projects/e-harness/results/group_level_evidence_pilot --output results/group_level_evidence_pilot_replay
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p test_group_evidence.py -v
```

重放读冻结草稿及历史回复，不重新提取或验证Group。0次新API，0次SAM/SLIC/DINO/大型模型，0次GPU/Blender/Agent运行。没有修改正式公式、权重、相机协议或历史产物，没有提交Git。未执行项：新真实VQA、精确Group Grounding/密度、独立人工审核、正式评分；原因分别是未授权请求、缺可靠定位与Mask、尚待审核、相机/证据不满足协议。

## 执行偏差

一个只读子任务曾额外计算文件摘要作比对，不符合项目此前避免哈希校验的约束；已停止，未保存摘要、未写入历史文件，也未用作本轮证据或评分依据。主流程仅做元数据、直接字节及ROI成员核对，未重复计算摘要。

主要自动化瓶颈仍是Reference候选的可靠提取、具体问题的真实验证，以及连续测量所需的Group定位；不是必须先完成整个场景的实例清单。当前少量Group已能表达具体待验证差异，但真实检出能力尚待后续审核和授权验证。

实际CPU回归：206项通过，其中新增Group合同测试14项。首次HTML检查曾在validation.json写出之前检查其自身链接，已修正写出顺序；版面刷新时临时目录路径格式也已修正。测量数值、冻结证据和ROI均未改变。最终离线重放检查另见offline_replay_check.json。
