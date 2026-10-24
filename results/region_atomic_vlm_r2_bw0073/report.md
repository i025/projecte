# R2 首次真实VLM Atomic Verification

只验证bw_0073 R2的三个问题；既有Reference、真实Render与同坐标ROI来源见pair_audit.json和inputs.json。沿用1536×837共同网格及历史全图适配，输入均缩放到1024×558。每次请求只含同一侧的完整RGB与R2轮廓图；无黑色Mask、无期望答案、无跨侧比较。

[人工审核页面](comparison.html) · [真实Reference回答](reference_answers.json) · [真实Render回答](render_answers.json) · [比较结果](verification_results.json) · [实际成本](request_summary.json)

| 问题 | Reference真实回答 | Render真实回答 | 程序结果 |
| --- | --- | --- | --- |
| q1 | yes | yes | satisfied |
| q2 | 4 | 4 | satisfied |
| q3 | yes | yes | satisfied |

## 静态图像初审及本轮结论

- q1：Reference 与可见中央岛台存在性相符；Render 与可见中央岛台存在性相符。两幅完整画面中央均可观察到台面与下方岛台主体；仅验证基本存在性，不检验形状、尺寸或材质
- q2：Reference 与前侧4把可辨认高脚椅相符；Render 与前侧4把可辨认高脚椅相符。前侧4个椅背及其座面/支撑可见；本次没有明显遮挡计数歧义，但不是完整隐藏实例清单
- q3：Reference 与吊灯在岛台上方的图像投影关系相符；Render 与吊灯在岛台上方的图像投影关系相符。完整画面中吊灯和岛台均可见；Render吊灯主体部分移出固定Polygon，完整上下文避免将其直接当作缺失

上述如有静态初审，均是助手查看已保存RGB后的可见性意见，reviewed=false，并非第三次模型API验证或真实人工GT。两侧真实解析答案：{"reference": {"q1": "yes", "q2": 4, "q3": "yes"}, "render": {"q1": "yes", "q2": 4, "q3": "yes"}}。程序状态数量：{"satisfied": 3, "candidate_violated": 0, "unknown": 0, "unavailable": 0}。 一次回答不能检验稳定性。

本例最重要的限制是问题覆盖范围：岛台存在、椅子数量和吊灯上方关系这三项即使同时一致，形状、纹理、材质、灯具高度和具体位置仍可能明显不同。因此未发现原子违反不等于重建无错；这里是命题覆盖局限，不是已经证明模型答错。完整上下文保留了固定Polygon外的吊灯，避免直接把移出ROI当成缺失；没有额外跑黑色Mask对照，不能宣称量化改善。

有效格式的Semantic存在性和Statistical可见计数回答可供进一步人工审核；Spatial仅支持图像投影上方这一粗命题，尚不支持精确位移或3D关系。三者都缺少审核后的Reference GT、验证器校准和正式相机条件，当前均不能作为正式Energy。无效或Unknown回答不能补造为评分输入。

## 结果的含义

本目录分别保存实际模型响应、请求/解析失败时的不可用记录和程序比较，未人工审核；实际调用数与有效回答数见下方。known相同记satisfied，明确不同记candidate_violated，任一unknown记unknown，请求/解析失败记unavailable。Q1两侧任一不是yes时，Q2/Q3保留原答但比较记unknown，不重复处罚。没有确认缺失判定，也不把物体移出ROI当成不存在。Q3没有独立吊灯可见性字段，必须人工核对模型是否遵守条件。

Reference答案不是GT，相同回答可能共同错误；不同回答也可能来自视觉识别、遮挡、视角或真实重建差异。每侧只有一次，不能声称稳定性或可靠准确率已验证。Semantic/Spatial/Statistical各只有一个具体命题；计数不等于密度/分布评测，投影上方不等于世界坐标或完整3D结构。全部正式Energy和总分保持N/A。

## 实际请求、费用和边界

模型openai/gpt-6-sol，temperature=0.1，最多800输出Token；使用既有OfoxTunnel、HTTPS原域名与证书校验。关闭网络和HTTP自动重试，每侧独占预算记录，最多2次；首次请求/解析失败即停止后续请求。不额外检查余额、模型目录或验证模型。

```json
{
  "actual_requests": 2,
  "maximum_authorized": 2,
  "usage": [
    {
      "side": "bw_0073:R2:reference_atomic_answers",
      "model": "openai/gpt-6-sol",
      "tokens": {
        "prompt_tokens": 1576,
        "completion_tokens": 35,
        "total_tokens": 1611,
        "completion_tokens_details": {
          "reasoning_tokens": 10
        }
      },
      "latency_seconds": 5.8596190710086375,
      "actual_cost": null
    },
    {
      "side": "bw_0073:R2:render_atomic_answers",
      "model": "openai/gpt-6-sol",
      "tokens": {
        "prompt_tokens": 1576,
        "completion_tokens": 35,
        "total_tokens": 1611,
        "completion_tokens_details": {
          "reasoning_tokens": 10
        }
      },
      "latency_seconds": 5.310503120999783,
      "actual_cost": null
    }
  ],
  "total_tokens": 3222,
  "total_latency_seconds": 11.17012219200842,
  "total_actual_cost": null,
  "actual_cost_unknown_reason": "Provider did not supply a numeric cost; no estimate/balance request",
  "reviewed": false
}
```

费用字段缺失时unknown，不估价、不推断免费。保存脱敏原始provider响应和原始回答；没有保存API Key、认证Header或Base64请求正文。原图/Render和Mask仅复制到新目录，核心公式、权重、Grounding参数及历史产物不改动。历史相机不符合T0，全部provisional/debug、reviewed=false。

173项离线CPU测试通过后才发送付费请求，详情见tests_offline.log与offline_checks.json。正式评分、SAM、SLIC、DINO、Blender和Agent执行均为0。复用现有VLMClient及Energy记录字段，保留level=region、energy、q=0、value/score=null，不将candidate_violated改成正式惩罚。离线重放和最终检查见validation.json。

## 免费离线复现

以下仅重放已保存真实回答、重建页面，不会请求API。目标目录必须不存在：

```bash
cd /home/xymo/projects/e-harness
/home/xymo/environments/relateanything-inference/bin/python scripts/region_atomic_vlm.py replay --source results/region_atomic_vlm_r2_bw0073 --output results/region_atomic_vlm_r2_bw0073_replay
```

本轮请求结束后停止，等待人工审核，不计算正式Benchmark总分。
