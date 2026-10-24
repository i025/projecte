# Group Verification：不存在与证据不足

本轮采用新的独立实验协议，旧 T1–T5 原图、Prompt、标签和原始结果均未修改。后端为 **Codex Subagent / gpt-6-sol**，4 个验证子 Agent，每图一次、严格串行、无自动重试。结果全部 reviewed=false、provisional/debug；没有正式 Statistical Energy。

## 验证前冻结的操作定义

- yes：有充分可见证据确认该排列存在。
- no：相关书架区域足够清晰，能够确认该排列不存在。
- unknown：由于模糊、遮挡或类别歧义，无法可靠判断。

Q1：图中是否存在至少两本水平叠放的书籍？
Q2：图中是否存在竖直站立摆放的书籍？

冻结 System 明确要求不要将“没有清楚看到”当作“不存在”，两个字段各只允许单个 yes/no/unknown。完整原文和Schema在 JSON.protocol，验证前只读副本为 runs/group_observability_2ce4da0e924b418598d369c4af63fca5/frozen_plan.json。没有根据任何回答修改定义。

## 数据、预览和可观察性审核

直接复用上轮清晰 T1/T2，分别生成相同 whole-image GaussianBlur(radius=14) 的新 PNG；分辨率896×704、相机、构图和场景内容完全保持，没有 Blender/GPU/新场景变量。清晰图逐像素与来源一致，两张模糊图均由明确的同一处理生成。新模糊T1与上轮T5视觉像素相同，这是固定视觉输入下对新协议的行为观察；旧结果未替换。

先生成 comparison.png 的 Pending 预览，协调 Agent 做静态观察：清晰图有书脊/页块和排列线索，模糊图仍有整体形状但细节消失。**没有独立人工审核**，静态观察不是人工可见性GT。JSON将source_construction、visible_expected、human_visibility_review和human_book_category_review分开记录。清晰控制仅与未审核的构造预期比较；模糊两图的4个可见标签均为None，不用源场景真值代替，不预设unknown正确。

## 实际原始回答

H/U = horizontal_stack / upright_books。

| 图像 | 源构造 H/U | 当前可见标签来源 | 模型实际 H/U |
|---|---|---|---|
| Clear T1 | yes/yes | construction_expected，未人工审核 | yes/yes |
| Clear T2 | no/yes | construction_expected，未人工审核 | no/yes |
| Blurred T1 | yes/yes | 未审核，不评分 | unknown/yes |
| Blurred T2 | no/yes | 未审核，不评分 | unknown/unknown |

清晰控制分字段候选比较：{"correct": 4, "false_positive": 0, "false_negative": 0, "unknown": 0, "unavailable": 0}。Unknown/Unavailable独立保留，不折算为对错。模糊样本行为：{"unknown": 3, "definite_yes": 1, "definite_no": 0, "unavailable": 0}。这只是回答类型计数，不是弃权准确率。

T1 clear→blur：{'horizontal_stack': 'yes', 'upright_books': 'yes'} → {'horizontal_stack': 'unknown', 'upright_books': 'yes'}。
T2 clear→blur：{'horizontal_stack': 'no', 'upright_books': 'yes'} → {'horizontal_stack': 'unknown', 'upright_books': 'unknown'}。

## 结论及不能证明的部分

本次清晰T1得到yes/yes，清晰T2得到no/yes：模型在清晰对照中保留了横放存在与不存在的区别。模糊T1得到unknown/yes，模糊T2得到unknown/unknown；4个模糊判断中3个弃权、1个肯定、0个否定。这说明本次运行确实出现了按字段弃权，而不是将未看清一律回答no。模糊T1的竖放yes仍需人工判断其可见依据是否充分；不能由源场景中存在竖放书籍反推它一定正确。

清晰正/负控制是否保留判断，应逐字段读上表；与construction_expected一致只能作为初步对照证据。对模糊图，unknown表示模型选择弃权，并不自动证明弃权合理；yes/no表示给出确定回答，也不自动证明无依据或错误，仍需人工判断其所依据的可见形状是否足够、书籍类别是否可辨。因缺少这组人工可观察性标签，本轮不能计算模糊误报/漏检率或宣称校准完成。

新定义明确收紧no的证据要求，减少“未看清＝不存在”的文字歧义。但只看最终二字段JSON，不能区分剩余问题来自视觉识别、书籍类别歧义、模型对no/unknown边界的执行、或对模糊整体形状的推断；本轮没有要求解释或追加自检，不能编造原因。与旧T5回答的变化只作描述，单次独立调用和不同任务上下文不能建立Prompt修正的因果效果。

当前最多支持有限的合成可观察性行为对照，**不足以把确定回答直接作为真实 Render 的重建错误，也不足以认证真实Render的弃权可靠性**。接入真实图之前，需要独立审核这些可见标签，并在有GT的清晰不存在、局部模糊、遮挡和类别混淆案例上检查选择性误报、漏检与弃权；本轮不自动扩展。所有 Energy 值保持None，不把unknown/unavailable伪造为零误差。

## 输入隔离与实际开销

每图采用独立 /tmp/随机目录/随机文件名.png，验证者只收到这一图路径和相同冻结任务文本，未得到源构造、清晰/模糊条件、其他图答案或历史结论。fork_turns=none；会话日志核实gpt-6-sol，实际工具读取记录及原始回复完整保存在JSON.cases.*.raw_response。共享文件系统不提供强制单图访问边界，父任务正文持久日志为加密形式，无法独立逐字核实交付内容；System/User作为任务文本转交，平台系统上下文、温度及输出上限不同于API。所以不宣称已实现严格盲测或固定API等价复现。

四个PNG的预处理按冻结协议执行，但子Agent自主使用view_image时，clear_T2和blur_T1显式指定original，clear_T1和blur_T2使用工具默认值，图片转交模型时的detail提示也不完全相同。原始调用已保留，未补跑或重试；因此不能保证底层视觉编码完全一致。这是本轮子Agent后端的额外控制限制，不能把所有回答差异仅归因于图像模糊或新Prompt。

4 个验证会话合计 221.113 秒，Token口径：{"input_tokens": 176365, "cached_input_tokens": 165376, "cache_write_input_tokens": 0, "output_tokens": 550, "reasoning_output_tokens": 196, "total_tokens": 176915}。包含子会话平台指令、取得图像的工具阶段和最终回答；不含主协调/准备。缓存输入、推理输出分别已包含在输入、输出，不重复加总。Ofox调用0；Codex实际货币费用未知，不称免费。

8 项针对新定义/比较逻辑的CPU测试通过。输入像素、冻结时序、单图工具读取、原始JSON重解析、串行和离线重画检查另保存在 runs/group_observability_2ce4da0e924b418598d369c4af63fca5/final_checks.json；实际测试结果见tests.txt。没有新增HTML，没有调用OfoxTunnel、SAM/SLIC/DINO/Blender，未自动提交Git。

## 离线复现

只根据已保存回复重画，无模型/API请求，目标目录须不存在：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_abstention_calibration.py --stage replay --output results/group_abstention_calibration --destination results/group_abstention_calibration_replay
```

重新准备输入和Pending预览（不启动验证、不重新渲染）：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_abstention_calibration.py --stage prepare --output results/group_abstention_calibration_inputs_repro
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p test_group_abstention_calibration.py -v
```

主实验的只读冻结文件、实际发送模板、可观察性待审记录、原始回复与测试日志位于 runs/group_observability_2ce4da0e924b418598d369c4af63fca5。完成四次验证后停止。
