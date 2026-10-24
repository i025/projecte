# Offline Integration MVP 发布前审查

基准与已获取的 GitHub main：`2671c129ab66260f6658faf0f741137119836089`。
审核分支：`feat/offline-integration-mvp`；本材料只用于该分支，不合并 main、不强推。
这是发布审查及回归记录，不是新图像实验或正式 Benchmark 成绩。

## 结论与源码边界

- Manifest 新入口只适配现有 build_reference / compare / aggregate / structural_report，输出 PNG/JSON/Markdown。
- 对基准逐项 AST 复核：ENERGIES、POLICY、FIXED_T0、RENDER 未变；record、weighted、gradients、coarse、distribution_error、numerical_errors、perceptual_error、match_anchors 的函数定义未变；独立 benchmark_structure.py 未变。
- compare / aggregate 新增有效支持与参与门控，未改变已有误差定义或混合权重。重叠的有效 named Region 只作诊断，q=0 候选不能使已有有效测量被移除。
- 外部 JSON 布尔声明或数值匹配位姿不再能认证静态 RGB 为 valid。历史相机保持 historical_camera、provisional/debug；trusted launcher/camera/export 的 T0 数值校验更严格。
- uniform_fit 只做既有全帧缩放补边，不搜索对齐、不移动 ROI。共享函数的 RGB、alpha valid 和 transform 与历史缓存逐像素/逐字段一致。
- Group / Structural Layout 原样诊断附入，不将 yes/no/unknown 任意转换为 0/1 Energy，不升级 reviewed:false。
- BlenderRuntime、SANDBOX_READINESS.md 及 blocked 状态未改变。没有开放无人值守执行。

## 回归结果与修复

完整项目单元测试使用 `unittest discover -s tests -p 'test_*.py'`，显式禁止实际 socket 连接和 subprocess 启动；限制 CPU 线程，不运行模型、GPU、Blender 或历史 Agent。

| 运行 | 测试数 | 结果 |
| --- | --- | --- |
| 本轮首个全量运行 | 318 | 316 通过，2 个历史冻结源码校验报错；无模型执行 |
| 最终全量运行 | 319 | 全部通过；其中集成专用 19 项 |
| 仅导出待公开 Git 树后的全量运行 | 319 | 全部通过；未复制忽略的原始数据，仍使用现有 sibling 依赖 |
| 上轮有限集成回归 | 89 | 原记录保留，不冒充本轮全量测试 |

首轮两项错误是 Direct Grounding / Region E2E 检查发现 benchmark_evidence.py 与历史冻结文件不一致，原因仅为新增共享 fit_render。发布修复将该函数移动到新的 benchmark_offline.py；原 benchmark_evidence.py 恢复为基准相同字节，历史冻结副本和检查逻辑均未修改。旧 scripts.region_real_render.fit_render 导入绑定仍可使用，行为不变。

另有最小接口修复：合法 JSON 数组或 null 作为可选 Render Evidence 时，原路径会抛 AttributeError；现在记录 unavailable，其他 RGB 结果保留。新增一项含两种输入的回归测试，故集成专用 18→19、总量 318→319。

真实历史回放与原数据不改写；本轮只读确认共享 fit 的坐标行为一致。没有重新运行 Reference Planning、Grounding、VLM 或重建。

原始测试记录：[首轮含失败](cpu_tests.json) · [最终全量](cpu_tests_final.json)。完整服务器单元测试通过不证明独立安装、实际 Blender 导出或视觉验证器可靠。公开树离线验证结果见 [cpu_tests_public_tree.json](cpu_tests_public_tree.json)。这是临时导出的仓库文件集合验证，不是文件系统安全沙箱，也不消除 sibling 依赖。

## 公开材料与缺失资产

只纳入经过内容审查的源码、文档、数值/标注 JSON、原始失败记录及自制合成 PNG。真实 Reference、历史 Render、所有相关衍生 PNG/Mask、Blender 文件和模型缓存全部排除；服务器原件不移动、不修改。

实际允许与排除清单见 [公开边界](../PUBLICATION.md) 和 [逐文件审查](publication.json)。原实验 summary.md 的真实 PNG 链接在公开树中缺失，这是许可边界，不是未执行或删除失败结果。原有绝对路径仅为项目所有者数据的 provenance，不承诺在克隆目录存在。

## 历史接口兼容性

- evaluate 和 compare 的既有位置参数、返回结构及旧 CLI 命令保留；新增关键字有默认值。
- 原 writer 的 HTML 兼容能力保留；新 offline 入口不产生 HTML。旧测试中的 HTML 只在临时合成目录生成并由测试清理。
- 相机声明的 valid→unverified 是有意的可信性修正，不声称这一行为与旧漏洞兼容。
- 新共享 fit 函数移出被冻结的 Reference Evidence 模块，避免破坏历史回放。

## 未验证路径

没有执行 Blender/GPU/模型推理、真实外部 API、Agent Python 或正式排行榜；没有测试未审核 .blend。渲染器实际导出前/后校验仅经源码/语法审查，尚未执行 Blender 回归。Semantic/Perceptual/3D 的不可用状态与图像边缘/纹理代理范围保留。

核心依赖兼容的 sibling scene-benchmark；本 PR 不复制该依赖、不伪造公开下载源。真实 ROI 与图像许可未确认，不能从公开仓库单独重放真实配对。

## 下一步可信 Blender Fixture 的最小工作（本轮不实施）

1. 仅用已有 trusted fixture 与串行受限 CPU launcher，跑一个固定 T0、Agent 内参的低成本导出；继续禁止历史 Agent Python。
2. 在同一受控调用中将实际相机、RGB、Geometry 与 evaluation 结果直接传递并绑定来源。普通外部 JSON 仍不可授予 formal valid；不需开发新的注册表或评分体系。
3. 增加一条真实 trusted fixture 渲染→Manifest/核心评价回归，验证实际导出位姿、尺寸、valid-pixel 和所需几何字段；保留故意偏离 T0 的拒绝测试。
4. 不为缺少 semantic evidence 或 DINO 输入补造分数；保持 N/A。可信 Fixture 通过也不自动解除 Runtime blocked。

## 复现

在已有兼容环境、sibling 依赖存在时：

```bash
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 -B -m e_harness.benchmark offline --manifest results/offline_integration_mvp/inputs/synthetic_manifest.json --output /tmp/projecte-release-synthetic-new
```

输出目录必须不存在。真实回放仍需获准的本地原数据。该报告不调用或授权下一轮 Blender。
