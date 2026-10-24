# bw_0073 R2/R3：Atomic Evidence 区分能力审计

**先前的三个真实VLM问题回答一致，是命题未区分这些差异，不是Region重建质量良好的证明。** 本轮冻结的更丰富候选覆盖了部分摆件类别、颜色和纹理，但没有执行新验证，不能把“可能区分”写成“已经自动检出”。

[审核页面](comparison.html) · [冻结Reference Evidence](reference_evidence_frozen.json) · [冻结记录](reference_freeze_receipt.json) · [完整差异审计CSV](difference_audit.csv) · [检测能力对照CSV](detection_matrix.csv) · [检查结果](validation.json)

## 1. 阶段隔离与信息泄漏披露

主代理此前已看过该Render及具体差异，因此**整个实验不是严格盲测**。本轮第一阶段使用不继承前文上下文的独立助手过程，仅获准读取Reference RGB、Region Plan、既有R2/R3 Mask和通用证据加载代码。该过程没有读取Render、差异图或历史评价结果。旧Region Plan本身也带有语义先验，不能当作GT。

该过程先写入并宣布冻结 `reference_evidence_frozen.json`；主代理创建只读冻结记录后，才在本轮第二阶段读取Render及既有评价。后续没有回写冻结文件。另一个只读方法审查过程仅阅读冻结证据文字，没有看图或确认图像事实。

这14条是 `assistant_reference_only_visual_draft`，不是经过验证的自动提取器输出，更不是独立人工标注。所有候选 `reviewed:false`、可靠性0；`uncertainty.level=low`只是草拟者自评，不是真实正确概率。

## 2. 冻结的Reference证据

R2、R3各7条，共14条：Semantic 5、Spatial 4、Statistical 2、Appearance 3。其中炉灶命题 `R3_SEM_03` 为Unknown、expected=null，不能转成false或缺失。保留颜色/纹理为Appearance，未增加新Energy。

- **R2**：环带式灯具轮廓、盛水果容器、灯具上下及水平对齐、椅子横向排列、四把高脚椅、台面脉纹、椅面色系。
- **R3**：上部壁柜、长叶盆栽、柜门与中央面板的左右关系、开放陈列列的位置、三个器皿、背景脉纹，以及不可确认的炉灶。

保留原有ROI。原子证据的 `scope.bbox` 只是Reference观察支持范围，不是新评价ROI；矩形中包含Mask外背景不等于对象内容缺失。`scope_audit.json`的交集比例只是几何备注，**不是对象覆盖率或语义准确率**。完整上下文和固定Mask必须分开解释，不能依据裁剪中未见目标就判缺失。

两条Statistical证据都只是计数。冻结材料没有独立的密度、尺度或归一化间距分布判据；不能把“一排”或纹理类别中的“dense”当成已经完成分布评测。

## 3. 可见差异与检测能力核心对照

下表是助手在冻结后对真实图像做的静态审核候选，**不是独立人工Reconstruction Error GT**。完整逐项记录、来源与不确定性见CSV/JSON。各分类可有交叉：例如颜色证据有覆盖，但连续视觉指标仍更适合。

| 实际可见差异候选 | 区域 | 冻结证据能否检测 | 适用Energy | 未检出或不可归因原因 |
| --- | --- | --- | --- | --- |
| 台面高反差脉纹在Render中明显变淡 | R2 | R2_APP_01部分覆盖；未验证 | Appearance / Perceptual | 粗纹理类别不保证对比度、密度或细节匹配；连续比较更合适 |
| 椅背和座面色系更浅 | R2 | R2_APP_02覆盖；未验证 | Appearance / Perceptual | 未明确“主要色系”的判据；光照也影响颜色 |
| 椅背、外框细节和局部比例不同 | R2 | 未覆盖这项形态/比例 | Spatial / Perceptual | 四把、单排和同类家具都可保持成立 |
| 灯具色调与精细呈现不同，但均像交叠环带 | R2 | R2_SEM_01只覆盖粗形态 | Appearance / Perceptual | 类别一致不代表颜色、反光或细部一致 |
| 灯体在同坐标下更低，仍在岛台上方 | R2 | R2_SPA_01不足以检出该位移 | Spatial / Perceptual | 缺纵向间距/位置判据；相机差异使三维归因不确定 |
| 明确果盘与Render小型浅绿容器样物的组成不同 | R2 | R2_SEM_02覆盖，待有效验证器 | Semantic | 只能记类别替代/遗漏候选；对应和可见性未核实，不能Confirmed Missing |
| 后墙及中央背景脉纹显著弱化、图样不同 | R3 | R3_APP_01覆盖，未验证 | Appearance / Perceptual | 现有图像距离有响应，但不能隔离纹理原因；细节适合连续比较 |
| 后方柜组图像位置/范围不同，固定裁剪混入更多背景 | R3 | 类别与粗左右关系不足 | Spatial / Perceptual | 缺投影范围/尺度证据；相机与布局混合 |
| 盆栽在全图仍可见，但更小、更低，局部裁剪不完整 | R3 | R3_SEM_02类别可能仍通过 | Spatial / Perceptual | expected只问盆栽类别，没有操作化位置/尺度；不得判缺失 |
| 陈列列由三个清楚器皿呈现为约四个相似浅色小体块 | R3 | R3_STA_01部分覆盖，不能直接确认计数违例 | Statistical / Semantic / Perceptual | 可数单元类别、移位后的支持范围不一致；不是已验证的3→4错误 |

炉灶本身在Reference中就不可可靠辨认，是否产生重建差异保持Unknown。这里没有确认真实物体缺失、实际物理材质或三维尺寸错误。

**本轮实际自动检出状态：** 既有三个VLM问题没有回答变化；新冻结命题的验证执行数为0。静态候选差异不是穷尽的错误清单，也无独立GT，故不计算原子检出率、召回率或准确率。

## 4. 为什么三个Satisfied仍会遗漏差异

| 既有真实问题 | Reference / Render | 实际检查 | 没有检查 |
| --- | --- | --- | --- |
| 岛台存在 | yes / yes | 基本存在性 | 台面、轮廓、大小、位置、组成摆件 |
| 前侧高脚椅数量 | 4 / 4 | 一个可见实例计数 | 椅子外观、比例、间距、细部与尺度分布 |
| 吊灯位于岛台上方 | yes / yes | 粗图像上下关系 | 纵向间距、精确位置、灯体大小和外观 |

这三个命题即使被完美验证，也可在当前两幅图同时成立。不能把未问到的属性差异归咎模型回答错误。R3此前没有相应的真实付费原子验证；**未执行不等于验证器漏检**。既有真实结果原样保留于 `prior_atomic_verification_results.json`，本轮没有追加请求。

## 5. Reference抽取与Verification都需要什么改进

**先改善命题覆盖与定义，而不是重复询问同样三个问题。** Reference侧需要按显著性选择对象组成、区分性可见属性、可操作的相对位置/尺度及群体分布，而非只问基本存在与计数。不能因看过Render后发现差异，就回填“Reference独立证据”。

冻结候选本身也有不足，详见 `reference_evidence_quality_audit.json`：

- `R2_SPA_01`把上方和居中合在一题，部分满足时无法唯一判定；“近似中部”未定义。
- `R3_SEM_02`描述右侧、长叶和展开形态，但expected只有盆栽类别；通过类别不代表属性都通过。
- `R2_SEM_02`的claim允许浅盘或碗，expected却写fruit_bowl，需防过窄类别判定。
- `R3_STA_01`主要是局部计数探针，不代表整个料理区的布局或统计保真。
- 纹理类别中的密度、方向与对比度没有统一操作规则；颜色/纹理不能冒充语义正确性。

**对已经覆盖的命题，再验证验证器。** 果盘类别、清楚可数实例及投影关系，需要真实、经校准的VQA或人工判断；定位/尺度/分布还需可靠对应与支持范围。目标被遮挡、移出局部ROI、类别含糊和真正缺失要分开。重复回答或未经校准的置信度不能补齐这些条件。本轮没有证据说明当前验证器能可靠区分新增命题的正负样本。

**能加载不等于能自动验证。** 现有加载器可以读取此JSON及Mask，但旧原子问题构造器只接受boolean/count，真实VLM实验又只支持固定q1–q3。新草稿含category/integer等答案类型，没有自动获得验证接口支持。`interface_compatibility.json`记录了这一缺口：后续需外置类型适配、明确类别接受范围和Unknown规则，不能用严格字符串相等假装完成语义校准。本轮未实现新评分适配，也未改写冻结命题。

## 6. 哪些更适合连续视觉指标

脉纹细节、颜色、明暗、反光和精细轮廓优先使用Appearance / Perceptual诊断，不把每个像素属性变成VQA。VQA可以问粗纹理类别，但相同类别不等于纹理保真；图像只能支持可见表面呈现，不能确认真实材质。

这里只复用历史真实测量：R2 Polygon Appearance约0.27087、Perceptual约0.15656；R3约0.31898、0.27629。两张Polygon与本轮冻结Mask像素一致。它们说明区域有图像差异，**不能证明果盘、纹理或其他某一原子命题已被自动判为违反**。DINO还受裁剪、填充和相对尺度影响，本轮没有重跑或更改其公式。

## 7. 事后诊断提案与未来控制协议

`posthoc_diagnostic_protocol.json`单列4项：灯体归一化纵向间距、椅背外框属性、柜组/盆栽投影范围、椅子间距与尺度分布。它们均在看过Render后提出，标为 `post_render_diagnostic_only`，**不具备本轮Reference独立性，不能加入冻结文件**。柜组/盆栽及间距/尺度应分别报告，避免再捆绑成单一问答。

`synthetic_controls_protocol.json`仅设计5组，全部未执行、未生成图像：

1. 类别替换与只改水果色系：检查类别区分和颜色干扰。
2. 清晰3把/4把与只改椅子颜色：检查数量而非颜色代理。
3. 保持数量/尺寸但改变单排排列，与只改纹理对照：检查分布敏感性。
4. 完全去除脉纹作为明确违例，与保持目标纹理但改变外部颜色对照；仅弱化另作连续敏感性分支，不预设原子违例。
5. 目标移出局部ROI但仍在全图可见，及无法辨认的遮挡支路：检查不误判缺失、正确弃权。

控制单元、可见性、支持范围和判据必须在生成前固定；正负预期与模型输出分开记录。这里没有执行这些控制，也没有新增正式指标或权重。

## 8. 相机、执行和检查边界

历史相机高度1.5m，当前固定T0为2m，Reference相机未知；不能将投影变化全部归为Agent三维错误。所有静态差异、质量审查和证据都为 `provisional/debug`、`reviewed:false`。

本轮没有付费API、GPU、SAM、SLIC、DINO、Blender或Agent代码执行；没有新合成实验、没有正式评分/总分、没有改ROI、五类Energy、权重或Runtime状态，没有Git提交。只新增审计材料和一个离线重排脚本。

执行必要的轻量一致性检查：冻结JSON可由现有加载器读取、ID和引用有效、坐标在图内、源Mask与旧测量一致、既有VLM结果未改变、页面图片链接有效，以及免费重放的一致性。实际检查详见 `validation.json`；没有用旧单元测试数量冒充本轮新执行实验。

## 9. 免费离线复现

只浏览审核页面无需执行命令。以下仅复制冻结证据与已记录的静态审核，重建CSV和页面，**不会自动重新做语义抽取、人工审核、VQA或生成控制图像**。输出目录必须不存在。

```bash
cd /home/xymo/projects/e-harness
/home/xymo/environments/relateanything-inference/bin/python scripts/audit_atomic_discriminability.py replay --source results/atomic_evidence_discriminability_bw0073 --output results/atomic_evidence_discriminability_bw0073_replay
```

本轮已停止，保留证据缺口、不可观察项和未验证状态，等待人工审核。
