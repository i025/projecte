# Group-level Statistical：子 agent 替代验证

本轮实际运行 **3 个独立、严格串行的 gpt-6-sol 子 agent**，每张图一个会话、只读取一次指定原始 PNG、只返回一个最终 JSON。**Ofox 请求 0 次**，未读取密钥或使用该账户额度。全部保持 `reviewed:false`、`provisional/debug`，没有正式 Statistical Energy。

## 真实回答与确定性比较

以下 Horizontal/Upright 预期来自此前冻结的 construction_expected，不是人工 GT。

| 样本 | 冻结预期 H/U | 子 agent 实际 H/U | 与构造预期比较 | 会话耗时 s | 会话 Tokens |
|---|---|---|---|---:|---:|
| A | yes/yes | yes/yes | MATCH construction_expected | 7.073 | 43,870 |
| B | no/yes | no/yes | MATCH construction_expected | 6.795 | 43,885 |
| C | yes/yes | yes/yes | MATCH construction_expected | 7.762 | 43,940 |

A→B：Horizontal yes→no，Upright yes→yes，检测到预定的排列变化。A→C：两个字段均保持 yes，没有在这组颜色控制中报告排列变化。6 个字段与 construction_expected 一致，本组三图没有观察到误报、漏检、Unknown 或 Unavailable。这里不计算跨场景准确率，也不将两侧一致解释为重建质量良好。

复用现有 parse_prediction、compare_expected、compare_pair 和 group_energy_rows。A/B 的 Horizontal 成对状态为 candidate_violated，表示相对于 A 的命题发生变化，正是本控制希望发现的变化；不是确认真实 Agent 错误，更不产生惩罚。单图与预期比较均为 satisfied。所有正式能量记录仍 value=None、q=0、scorable=false。

## 输入一致性与通道差异

使用冻结 System/User 原文、相同 JSON Schema、相同任务包装，唯一输入变化为原始 sample_01/02/03.png。三个子 agent 都以 fork_turns=none 启动，未继承父对话、预期答案或其他图片。日志各显示一次 tools.view_image，未见其他文件读取、网络、模型或执行工具。图片无裁剪、局部标记或人工修补；view_image 的平台媒体处理策略由平台控制。comparison.png 的原图区域保持原始 768×640 像素，文字在推理完成后加在图像外，未进入验证输入。

**这不是原 Ofox API 的等价复现。** 模型选择与会话日志均为 gpt-6-sol，原接口标识为 openai/gpt-6-sol，但无法证明两通道的后端完全一致。冻结 System 文本作为子 agent 任务中的指令转交，实际系统/开发者上下文还包含平台工具与运行指令；原 API temperature=0.1、max_tokens=400 不能在 spawn_agent 上强制设置。日志记录的推理档为 medium。原始任务包装保存在 agent_input_template.json；子会话将父消息加密存储，本轮未解密/导出这些内容，转交文本以协调端实际发送模板为准。

因此，本轮只能支持“该子 agent 通道能在这组三张合成图上区分目标排列变化与封面颜色变化”，不能改称原 Ofox 接口验证成功、三次单轮 HTTP 请求或稳定的真实图像检出率。

## 实际资源与成本

三会话累计 21.630 秒，输入 131,394、缓存输入 111,488、输出 301、总计 131,695 Tokens。缓存输入已经包含在输入中，推理输出也已经包含在输出中；不要再次加总。每个子会话有两个用量记录，覆盖取得图像的工具调用阶段与最终回答，包含平台上下文；不含主协调 agent。本用量不能与原 API 的短 Prompt 单轮请求直接比较。Ofox 费用为 0，Codex 子 agent 的实际货币费用未知，不能宣称整个过程免费。

## 失败模式与待审核内容

本轮没有字段不符，但图像仍存在明显的 8-sample 噪点、弱页块细节、书脊饰带与横向书架板。模型可能将薄体误作文件夹/唱片套，也可能依赖水平边线；二值 JSON 没有提供它使用的视觉证据，本轮未追加解释或自检。B 没误报横向书堆，仅能说明此图通过；本组没有真正的文件夹、唱片、单本平放、模糊/严重遮挡或必须 Unknown 的样本。C 只测试一组封面色变化，不能证明普遍外观不变性。

预期仍是未经人工审核的构造标签。还需按冻结定义人工审核，并在独立真实图、非书籍干扰、遮挡/低分辨率、不同布局与视角上验证误报、漏检和弃权；之后才讨论可靠性校准与正式 Energy 适用性。本轮未新增样本、修改冻结 Prompt/标签、运行 SAM/SLIC/DINO/Blender、修改五类公式或提交 Git。

## 测试与离线复现

17 项已有纯 CPU 测试通过。模型名、原始 JSON 重解析、每图一 agent、一工具读取、严格串行、唯一输入图片、原图/冻结文件状态及 comparison.png 内原始像素检查通过；原始回复与元数据在 raw_responses/，没有 Mock、凭证、请求 Base64 或隐藏推理文本。没有生成新 HTML。

仅重放已保存回复并重画 PNG（不启动 agent，不调用 API）；使用新的空目录：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/report_group_statistical_subagents.py --run results/group_statistical_controls_books/subagent_verification --output results/group_statistical_controls_books/subagent_verification_replay
```

原始 source/session 路径用于本机审计；重画只读取保存的回复、协议与原图。完成后三图验证即停止，不追加模型判断或正式评分。
