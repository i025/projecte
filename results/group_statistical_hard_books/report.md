# 书籍 Group：跨布局与困难样本验证

后端 **Codex Subagent**，模型请求与会话记录均为 **gpt-6-sol**。5 个独立上下文验证子 Agent 严格串行，每图一个、无重试；没有重新运行旧 A/B/C，没有 Ofox 请求、正式 Energy 或综合准确率。全部 reviewed=false、provisional/debug。T1–T4 的“正确/误报/漏检”仅表示相对 construction_expected 的候选诊断，不是人工 GT 结论。

## 先审计旧实验

旧三子会话各只有一次指定图像读取，未观察到标签/其他图读取；模型 gpt-6-sol、fork_turns=none。但旧路径暴露实验主题且用顺序文件名，父任务正文在持久日志中加密，无法独立逐字核实；共享文件系统仍可读，“禁止读取”只是任务约束。旧实验不能追溯认定为强制隔离的严格盲测。审计证据在 verification_results.json.previous_input_audit；原实验保持只读。

## 新数据与冻结

新建三列三层书架，层板、分隔位置、相机与上一轮不同，并非只换颜色。复用本轮可信的基础几何生成器；只扩展可配置隔板和可见唱片圆盘/中心标签/沟槽。T1/T2 同 11 本书、相机、光照、尺寸、材质、seed；3 本横放书转竖必然改变中心高度与横向间距，并改变遮挡/阴影，不能声称像素级单因素。T3 留一册平放书及原竖放书，数量减少是明确记录的负对照。T4 将横放书替为唱片，并增加两个直立展示圆盘；类别依据可见圆盘、沟槽、标签，不依赖 Blender 名称。未测试文件夹或带书籍式封套的唱片。T5 是新 T1 固定 GaussianBlur(radius=14) 的完整图像，没有再生成场景；两项可见预期均为 None，必须人工审核，不能预设 unknown 正确。

预期、问题、Schema 和生成配置均在验证前冻结于 runs/books_controls_31bc7758b31a4e36b309c4dc8ec44201/frozen_plan.json；验证输入在 frozen_agent_inputs.json 中先保存再逐个发送。本轮没有根据回答调整场景、标签、问题或模糊程度。4 次受限 CPU 渲染全部成功，累计启动墙钟 82.682 秒；896×704、24 samples、两核、低优先级、每图120秒墙钟/60秒CPU/1GiB RSS阈值、网络命名空间，无 GPU。

## 原始结果

| 样本 | 冻结预期 H/U | 实际 H/U | 分字段候选诊断 |
|---|---|---|---|
| T1 | yes/yes | yes/yes | correct / correct |
| T2 | no/yes | no/yes | correct / correct |
| T3 | no/yes | no/yes | correct / correct |
| T4 | no/yes | no/yes | correct / correct |
| T5 | None/None | no/yes | expected_unreviewed / expected_unreviewed |

T1→T2：Horizontal yes→no，Upright yes→yes。成对 candidate_violated 表示目标变化被发现，不是额外 Energy 惩罚；完整分字段状态保留在 JSON。

T1–T4 各字段计数：{"correct": 8, "false_positive": 0, "false_negative": 0, "unknown": 0, "unavailable": 0}。Unknown 与 Unavailable 不折算为对或错。T5 两项不计正确、误报、漏检或准确率；实际给出 {'horizontal_stack': 'no', 'upright_books': 'yes'}，只记录其弃权/确定回答行为，待人工判断证据是否足够。没有已确定的误报/漏检时不生成 failure_cases.png，避免将 T5 未决状态伪称已确认错误。

## 能力证据与失败模式

相较旧 A/B/C 只有方向与颜色控制，本轮添加真实新布局、单册平放与可见唱片干扰。T1/T2 能支持该新布局中的方向变化检测；T3 检查“至少两本”的排除能力；T4 仅检查裸唱片圆盘这个相对明显的非书籍类别，不代表复杂文件夹/封套混淆已解决。原图仍有采样噪点、重复书脊与隔板暗线，整体形状和水平线捷径仍不能排除。没有定位/注意力证据，不能仅凭两个回答证明模型理解每本书或真实实例数量。

T5 未知标签尚未经人工确认，不能说模型弃权正确、漏检或过度自信。如果模型回答 no，它可能将“看不清”解释为“没有清楚看到”，也可能未识别；回答 yes 也可能依赖模糊形状。这个 **no 与 unknown 的可观察性边界**既涉及原子命题定义，也涉及视觉识别，现有 JSON 无法辨别原因。讨论仅作后续协议诊断，本轮问题完全未改。

结论：仍值得作为 Group-level Statistical 的候选验证器继续有限研究；本轮不是可靠性认证。需要人工逐项审核，之后在独立真实图、书籍式唱片封套、文件夹、部分遮挡和分辨率变化上检验类别误报、计数阈值与弃权校准。当前只有一个新合成布局和每条件一个观测，不能以总体准确率声称跨场景稳定。

## 输入隔离与资源口径

每张图使用独立随机 /tmp/UUID/UUID.png 路径，目录仅包含该图；验证者未收到 T编号、实验条件、expected、其他答案或历史结论。模型任务名也随机。实际发送的协调端任务字符串、原始回答、模型、用量、只读工具记录和session路径保存在 verification_results.json；所有源图保存在 images/。与源图字节/像素一致，展示文字在收齐回答后添加，没有进入输入。每个子会话工具记录只应出现一次指定 PNG 的 view_image；shared filesystem 仍没有强制单图读取权限，父消息正文在日志中加密，因此 **不能声称严格盲测隔离已被证明**。冻结 System/User 以任务文本传递，平台系统上下文、温度及输出上限不等价固定 API。

5 个验证会话合计 41.865 秒；用量 {"input_tokens": 219652, "cached_input_tokens": 206080, "cache_write_input_tokens": 0, "output_tokens": 652, "reasoning_output_tokens": 198, "total_tokens": 220304}。这是五个完整子会话（平台指令、取得图像的工具阶段和最终回答），不含主 Agent/代码审计/准备。缓存输入已包含在输入、推理输出已包含在输出。Ofox调用与该Key消费为0；Codex实际货币费用未知，不称免费。本轮 27 项CPU测试通过，另做原始JSON重解析、匿名副本一致性、序列和PNG检查。没有新的 HTML。

## 复现

离线重放现有回答不调用模型。报告生成器拒绝覆盖已完成结果，使用临时副本测试或新目录；现有JSON包含全部固定参数和实际输入，原始会话用于只读核查。受控数据可用以下命令写入新目录，仍使用受限串行CPU启动器：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p 'test_group_statistical*controls.py' -v
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_statistical_hard_controls.py --stage prepare --output results/group_statistical_hard_books_repro
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_statistical_hard_controls.py --stage render --output results/group_statistical_hard_books_repro
```

只重画已有结果、不生成新样本或调用模型，使用新的空目标目录：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_statistical_hard_controls.py --stage replay --output results/group_statistical_hard_books --destination results/group_statistical_hard_books_replay
```

collect 阶段只读已存在子会话；report/replay 阶段只读 frozen_plan/raw_observations，不启动验证。主实验的构造、测试与资源日志位于 runs/books_controls_31bc7758b31a4e36b309c4dc8ec44201。源码只改可信图片生成器、添加本轮辅助函数及必要测试，没有修改五类 Energy、Region/Group 正式结构、历史产物或提交 Git。完成五图后停止。
