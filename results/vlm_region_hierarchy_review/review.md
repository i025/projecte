# VLM 请求与返回脱敏审查

本次只读检查原结果与相关源码，未发起网络/API 请求、未导入或运行项目调用代码、未修改源码或原结果。当前目录为新生成的审查副本。

## 可核实的结论

1. 本地共有两次 VLM 尝试，分别保存在两个账本中；它们各自的 request_number 都是1，不是重复的一次请求。外部跨对话“5/6”仅为用户提供的计数，不能由本目录证明。
2. 首次 gpt-5.1 请求记录 SSLError，延迟0.6559784600976855秒；没有 HTTP 状态、Token 用量或详细异常堆栈。余额记录也只保留 SSLError。不能从这些记录恢复完整 TLS 错误消息，或推断密钥无效。
3. 最后 openai/gpt-5.1 请求记录 HTTP200、finish_reason=stop、耗时15.244517527054995秒；服务端报告 prompt_tokens=3353、completion_tokens=659、total_tokens=4012，actual_cost=null。它是一次双图、双任务（规划+分组）的合并请求，并非原定每图独立两阶段对照。
4. 保存的 raw_answer 是合法 JSON，重新用标准库 json.loads 读取与保存的 parsed_answer 完全相等。不存在已记录的 JSONDecodeError；失败发生在字段/层级契约校验与缺失键访问。
5. raw_answer 中仅有 scenes.bw_9064，plan 只有 regions。第9项（零基索引8）包含 anchors/relations/uncertain，没有 id；其后3项是字符串，仍是合法 JSON 字符串。它们不是有效 Region 项。
6. 四个最终错误原文分别为：bw_9064/plan 的 `Invalid text field: id`，bw_9064/group 的 `'group'`，bw_0074/plan 与 group 的 `'bw_0074'`。错误值及推断来源完整列于 recorded_errors.json。不能把后两类缺失键错误误称为 JSON 语法错误。
7. vlm_final.json 的顶层 status=`partial`，但四个 scene/stage 全为 unavailable。当前 final_vlm 使用“全成功则 available，否则 partial”，没有“全失败则 unavailable”的分支。这是汇总状态表达不一致；后续 vlm_evidence.json 为 unavailable，report.md 没有把语义结果宣布成功。本次只记录，不修代码或原产物。

## 请求构造核对

- 通过 VLMClient 生成 Chat Completions 请求；图片被打开、转为RGB、重新编码成 PNG data URL，而不是把本地路径作为模型视觉输入。detail=high。
- 最后输入是两张拼图：每张左侧为缩小 Reference RGB，右侧为同图编号区域。尺寸分别2048×618、2048×738；原始两阶段设计的规划本应只看原图，本次合并请求同时提供了编号图。这是可见的实验协议偏离。
- 使用 response_format={type:json_object}，没有发送 JSON Schema。它要求返回 JSON 对象，不保证 regions/anchors/group 的字段、类型、引用或两个 scene 键都符合业务契约。
- Session hook 替换 system prompt 并设置 temperature=0.2。首次 max_completion_tokens=3000、read_timeout=120；最后 max_tokens=6000、read_timeout=300。两次均关闭自动重试和重定向。
- 最后走用户提供的 OfoxTunnel：临时回环 CONNECT 仅允许 api.ofox.ai:443，连接指定供应商IP；保持域名/SNI与TLS证书校验。相关实现保留在 related_code.txt。首次代码没有配置该通道；首次实际使用哪个系统代理未存入本地账本，原报告对此的因果表述无法仅凭本目录独立证明。
- request_construction.json 是依据保存 Prompt、账本与当前代码制作的离线请求结构说明，省略图片 Base64，映射到 inputs/ 中的原有输入 PNG；它不是当时捕获的完整请求报文。没有保留任何认证字段。

## report.md 审核

- HTTP状态、模型、用量、耗时、JSON可解析但结构错误、分组不可用等核心描述与本地记录一致。
- “本结果目录2次”和外部“5/6”在报告中有区分，不能相加为本地请求明细。
- 报告将全部语义候选保持 Unknown，没有以现有 SAM 候选冒充有效 VLM Anchor 规划，这与 vlm_evidence.json 的不可用状态一致。
- related_code.txt 同时保留 report() 当前实现：关于这次具体错误、88项测试等文字有硬编码内容，不是每次自动从账本推导。因此 report.md 应与原始记录交叉核对，不能作为独立来源。
- 余额查询失败，没有后置余额记录或可信余额差值；Token计数不能替代实际费用。
- 最终 finish_reason=stop 且服务端报告输出659 Token，小于6000上限；没有 length 结束标志，不能据此断言是达到输出上限造成截断。该返回为何出现嵌套/字符串损坏，现有记录不能定位到模型、中转站或其他环节。

## 供后续排查的观察（不是已证明的根因）

- 一次请求同时处理两场景及规划/分组，提示包含两套结构示例，最后包络采用 `{规划结构}` / `{分组结构}` 伪JSON占位符；JSON object mode 没有严格 schema。这些是可观察的构造弱点，但不能证明它们导致本次返回错误。
- raw_answer 已经是网关提取出的 message.content，并经现有凭证脱敏逻辑处理，不是完整 HTTP response.text。没有原始 choices/message 包络、响应Header、请求ID或堆栈，不能复原丢失信息。
- 当前源码是只读时的快照；目录没有保存请求当时的完整源码快照，不能据此证明历史代码每一行完全相同。

## 材料索引

- records/：两份完整账本、两份 Prompt、原始保存结果、VLM汇总、预算、余额失败、report.md 与原有检查记录的脱敏副本。
- raw_answer.txt：完整保存的模型文本，无额外换行；与 vlm_final.json.raw_answer 对照。
- recorded_errors.json：所有现存错误字符串与来源，未补造 traceback。
- offline_inspection.json：仅用标准库重新读取保存回复所得的结构事实。
- request_construction.json：不含认证字段或 Base64 的请求结构、输入映射、参数与限制。
- related_code.txt / source_locations.json：带原文件行号的相关当前代码；仅在副本中省略认证构造与对应参数，源码没有改动。
- inputs/：当时保存的3张输入PNG，可离线核对图片实际内容。
- review_checks.json：脱敏和原文件未变的检查结果。

本材料不提供 API 重放命令，也不修补或重新解释无效回复为有效 Evidence。
