# 历史实验、测试结果与问题记录

整理时间：2026-10-14（Asia/Shanghai）。内容依据清理前的本地summary、analysis、执行日志及环境报告整理；没有重新调用API或执行Blender。

当前完整保留的实验是[runs/scene_064_gpt6_sol_20261014](runs/scene_064_gpt6_sol_20261014/final_report.md)。
本文件中列出的旧路径是清理前的来源索引，已从项目runs目录移除，不应作为现存产物链接使用。
旧目录通过系统回收站删除，未永久清空回收站。源码、测试用例、环境、原始输入图片、BVB、VIGA和Evaluation未删除。

## 早期Harness及离线测试

初始19项验收覆盖单Agent原生工具调用、single_shot、预算、失败保留、真实入口blocked、日志脱敏、Blender保存/重开、input/custom渲染和LiteLLM消息适配。
demo/smoke的Mock轨迹为7次Mock请求、2次建模、3次渲染、1次查询；one_shot/single_shot为一次可信建模加最终渲染。
Mock summary中的api_calls可能包含Mock客户端计数，不等于真实付费请求；固定fixture成功不证明图像重建能力。

逐次人工审核、generation_only、replace/update、Scene-State Context、Prompt选择等功能随后分别增加验证。
generation_only阶段记录52项非Blender测试通过；普通真实执行仍在API前blocked。
Mock增量测试轨迹为replace → update → update → render → inspect → finish；验证新增、移动、材质修改、删除、场景继承、失败回退和临时相机不改变已保存场景。

旧完整测试报告中的实际计数如下，均为当时结果，不表示本次清理重新运行了这些测试：

| 原目录 | tests_run | failures / errors / skipped |
|---|---:|---|
| test_report_169kavo6 | 32 | 0 / 0 / 0 |
| test_report_23af99mt | 30 | 0 / 0 / 0 |
| test_report_5q_s1avl | 68 | 0 / 0 / 0 |
| test_report_6hus8okv | 19 | 0 / 0 / 0 |
| test_report_7vt5jr7k | 68 | 0 / 0 / 0 |
| test_report__wfdmnm9 | 48 | 0 / 0 / 0 |
| test_report_b6cd8t90 | 19 | 0 / 0 / 0 |
| test_report_bxdm15gp | 59 | 0 / 0 / 0 |
| test_report_drfow5l5 | 90 | 0 / 0 / 0 |
| test_report_fjawn8mf | 89 | 0 / 0 / 0 |
| test_report_jr3us9vz | 90 | 0 / 0 / 0 |
| test_report_kdy0b2kx | 76 | 0 / 0 / 0 |
| test_report_ndct8b7u | 19 | 0 / 0 / 0 |
| test_report_vhyp3tv0 | 47 | 0 / 0 / 0 |
| test_report_x9bf_7kq | 102 | 0 / 0 / 0 |

另有16个integration、7个incremental、4个scene_context目录，主要是重复可信fixture集成验收，不是27组真实VLM实验。

## Scene-State Context实验

可信Mock中full与scene_state_recent均完成四个成功场景版本，保持实际工具结果、错误和图像版本配对。
最后一次请求：消息数13→6，历史代码1846→0bytes，新增场景记忆2067bytes；非图像文本JSON7986→4826bytes，含图片消息106830→103690bytes。
这是本fixture文本约39.6%、总消息字节约2.9%的减少，不是实测Token节省，更不是重建质量改善。
快照不含网格拓扑、完整shader graph、贴图、modifier或动画；对象很多时记忆仍可能很长。API-only没有真实快照时退回full。

## OFox GPT-5.1真实API实验

均使用原始scene_064.png，没有人工物体清单或隐藏GT；费用没有可靠记录时为Unknown。

| 实验 / 原目录 | 真实请求 | 输入 / 输出 / 总tokens | API秒 | 实际结果 |
|---|---:|---|---:|---|
| Smoke：api_smoke_20261009T033814_a8567084 | 2 | 2214 / 526 / 2740 | 19.362 | RGB、工具Schema、原生调用、匹配call ID及fixture图片反馈通过；不执行代码 |
| 单次generation_only：scene_064_generation | 1 | 1258 / 4096 / 5354 | 77.893 | finish_reason=length，工具JSON和Python截断，无完整程序 |
| Baseline API-only：scene_064_incremental_api | 3 | 12440 / 4195 / 16635 | 112.660 | replace → render(input) → 普通文本，无update/finish，以协议错误停止 |
| incremental_v1 API-only：scene_064_incremental_api_incremental_v1 | 4 | 11768 / 4470 / 16238 | 123.410 | replace → render(input) → replace → update，预算耗尽，无finish |

首次Smoke客户端尝试api_smoke_20261009T033725_366baf70在请求前因缺少socksio失败；计数1是客户端尝试，不是收到模型响应或发生扣费的证明。
仅在项目环境补装socksio==1.0.0后完成真实Smoke。其余两个api_smoke目录为dry-run，0次真实请求。
Smoke中的第二张图为明确标记的可信fixture，不是模型代码的执行结果。

generation_only收到的代码前缀约12271bytes、342行，停在冰箱scale表达式，ast.parse失败；没有生成合法generated_scene.py，也没有补齐后执行。
其代码意图覆盖房间、桌椅、盆栽和部分冰箱，但有primitive size/scale误用、地板范围不足、部件间隙及相机裁切风险。这些是静态分析，不是已生成场景。

Baseline的合法代码为11695bytes、352行，首轮输出3919tokens；尝试一次性构建完整场景，未实际执行。
incremental_v1三份代码分别为3967/3307/6041bytes、120/106/166行，均通过ast.parse；前两份重复重建房间，第三份添加圆桌、两椅、冰箱和盆栽。
单份最大代码变短，但总代码13315bytes、392行反而增加，存在重复房间初始化，不能称总输出更少。
两组API-only的render返回RENDER_UNAVAILABLE_API_ONLY，execute只接受语法并推进虚拟版本；当时没有真实渲染反馈。
两组总tokens仅减少约2.39%，API延迟增加约9.54%；单样本、覆盖细节不同，不能据此认定增量Prompt普遍提升能力或降低费用。

## 隔离环境与用户态运行研究

2026-10-09的宿主机检查未发现可用Docker、Podman、Apptainer、Singularity或所查调度器入口。
bwrap未发现安装；有gcc/make，缺Meson/Ninja/pkg-config/libcap开发文件。没有安装、编译或部署Bubblewrap。
User/Mount/Network/PID Namespace创建小探针通过；新网络命名空间连接诊断地址返回ENETUNREACH，PID命名空间内PID为1。
这不证明完整文件系统访问策略、Blender隔离集成或任务清理已验收。

CPU、memory、pids控制器位于cgroup v1，当前用户不能修改所查限额；v2没有可用控制器委派。
未验证任务级CPU、内存、pids及磁盘容量/inode硬配额。无特权不等于无法使用任何namespace或seccomp，但现有资源边界不足以放行无人值守未知代码。

可信小探针验证RLIMIT_AS阻止超地址空间mmap、RLIMIT_FSIZE阻止单文件超限、一次fork在NPROC限制下失败；CPU限额仅配置回读，没有用高负载耗尽测试。
seccomp可信C探针允许一个pthread，并拒绝部分进程创建路径；没有完成Blender线程兼容、clone3完整策略或任务线程总量限制。
研究结论为“仍有技术障碍”，不是证明所有未来用户态方案绝对不可能；正式Runtime始终blocked。

## GPT-5.1离线重放及实际问题

scene_064_offline_replay仅完成静态审查和方案，未启动Blender。
其后用户明确允许逐份人工监督本机试验，仍保留正式无人值守blocked状态。
实际代码来源为incremental_v1的round_00、round_02、round_03，不拼接程序，update加载上一成功blend。

| 阶段 / 原目录 | 实际结果及问题 |
|---|---|
| scene_064_manual_replay | round_00实际执行失败：scene.world为None，world.use_nodes触发AttributeError；无成功场景/PNG |
| scene_064_environment_normalized_replay | 可信Mock验证可选World Wrapper；默认路径和初始化路径均成功，不修改模型代码 |
| scene_064_environment_normalized_round_00 | World Wrapper下原始round_00成功保存scene.blend；渲染启动约0.208秒后线程增长，监控终止，未生成PNG |
| cpu_thread_diagnosis | 可信fixture发现默认启动149个Blender线程；OPENIMAGEIO_THREADS=2后约10个Blender线程/11任务线程，单次渲染通过；重复时因短命xdg-user-dir辅助进程超2进程阈值停止 |
| manual_cpu_calibration | 独立XDG配置不能阻止查询shell；实测正常进程树峰值4，固定人工监督阈值4后连续三次可信CPU渲染通过，无名称白名单 |
| scene_064_independent_cpu_render | 仅读取已保存round_00.blend、禁用自动脚本，独立CPU渲染成功，不重跑模型Python |
| scene_064_environment_normalized_followup | round_02 replace和round_03 update逐份批准后均执行、重开和渲染成功；最终27对象，但冰箱及桌底座悬空、家具小且拥挤、图像偏白及噪声明显 |

线程诊断时最早渲染停止记录未保存触发瞬间的完整快照，不能从其launcher采样推断Blender真实内存峰值。后续监控已改为先保存超限快照再停止。
OPENIMAGEIO_THREADS=2的同fixture对照是启动线程池的重要因果线索；没有原生调用栈，不能精确给每个线程归属库。
两渲染线程不等于整个进程只有两线程；CPU affinity不等于独占核心或CPU时间配额。

三次可信校准数据（原manual_cpu_calibration）：

| 测试 | 同时进程峰值 | 线程峰值 | RSS MiB | 采样CPU秒 | 进程壁钟秒 | 清理 |
|---|---:|---:|---:|---:|---:|---|
| test_01 | 2 | 11 | 261.48 | 1.41 | 1.590 | 完成 |
| test_02 | 4 | 11 | 260.65 | 1.44 | 1.302 | 完成 |
| test_03 | 2 | 11 | 258.55 | 1.41 | 1.419 | 完成 |

对应固定配置为CPU Cycles、256×256、8samples、2允许逻辑CPU/2渲染线程、OPENIMAGEIO_THREADS=2，120秒上限、监测RSS1GiB/线程128/进程4/输出512MiB等。
仅保留CPU与World可信校准的精简机器可读摘要于runtime_evidence，作为现有脚本的运行依赖；旧fixture.blend、PNG、逐项日志及探针文件从runs清理。摘要保留历史来源，不冒充新验收或沙箱ready。

GPT-5.1最终update保留7个原房间对象、添加20个家具部件；世界坐标诊断冰箱主体底部z≈0.7、下门底部≈0.6、桌底座底部≈0.135，地面z=0。
其update/渲染/查询壁钟为0.812/3.057/0.561秒，渲染RSS峰值264.80MiB，任务采样峰值2进程/11线程，清理完成。
这些事后渲染没有补回原GPT-5.1 API-only对话，不能说当时模型看到了它们。没有自动修复悬空问题。

## 清理范围及保留边界

本次移除71个旧runs目录，清理前普通文件逻辑大小共374170246bytes（约356.84MiB；不等同于实际释放磁盘空间）。
采用系统回收站删除，未永久清空，因此原始文件在回收站保留期间可恢复；恢复到原路径时不能覆盖当前结果。
实际恢复位置为/home/xymo/.local/share/Trash，已核对71个对应原项目路径的trashinfo条目。
当前GPT-6 Sol目录完整保留，包括原始响应、三份代码、每轮场景和渲染、人工拒绝/批准、资源记录及最终汇总；不是只留最终图片。
锁文件.manual_reviewed_replay.lock属于并发控制，不是历史结果，保留。
README中的旧结果链接改为本文件，Smoke默认fixture改用已有BVB可信PNG（只读），校准入口改读runtime_evidence。
旧GPT-5.1专用重放脚本源码仍在，但其默认历史输入已清理；要重新运行旧实验必须先恢复原始数据，不能伪造旧代码或场景。

清理后重新运行test_manual_cpu_render、test_manual_replay、test_environment_normalized_replay共39项离线测试，全部通过；未调用真实API、未启动Blender。
确认runs中只有当前GPT-6 Sol实验目录及并发锁；校准依赖和Smoke可信fixture仍可读取，正式Runtime仍isolated=False。
当前最终blend、PNG、实验摘要及四份原始模型响应与清理前字节一致，PNG读取验证通过。

清理前旧目录清单：

```text
api_smoke_20261009T033148_ed52ccbc
api_smoke_20261009T033403_f3aa9fbc
api_smoke_20261009T033725_366baf70
api_smoke_20261009T033814_a8567084
blocked_real
bubblewrap_environment_check
cpu_thread_diagnosis
demo
generation_only_dry_run
generation_only_mock
incremental_12ud39ac
incremental_8039wwya
incremental_b34xzfum
incremental_pncafdax
incremental_sigqmyqi
incremental_ur3vg8xm
incremental_zx0l68zw
integration_1_o5sjsp
integration_1cqzk4mu
integration_8b1xf2vf
integration_bvoo5ra1
integration_c6993trk
integration_eua8u9h6
integration_fyt7maip
integration_g8galdhy
integration_ismunnjz
integration_kn_u2bi_
integration_lububy8n
integration_rqswkq78
integration_tx482ydb
integration_vvpabcel
integration_wd2r4oe0
integration_wzbdplp5
manual_blocked_check
manual_cpu_calibration
manual_rejected_mock
manual_terminal_mock
one_shot
restricted_runtime_research
scene_064_environment_normalized_followup
scene_064_environment_normalized_replay
scene_064_environment_normalized_round_00
scene_064_generation
scene_064_gpt6_sol_preflight_20261013
scene_064_incremental_api
scene_064_incremental_api_dry_run
scene_064_incremental_api_incremental_v1
scene_064_independent_cpu_render
scene_064_manual_replay
scene_064_offline_replay
scene_context_mdh8g83w
scene_context_n4mbwqz1
scene_context_vzm091y8
scene_context_w9k4yr8y
single_shot
smoke
test_report_169kavo6
test_report_23af99mt
test_report_5q_s1avl
test_report_6hus8okv
test_report_7vt5jr7k
test_report__wfdmnm9
test_report_b6cd8t90
test_report_bxdm15gp
test_report_drfow5l5
test_report_fjawn8mf
test_report_jr3us9vz
test_report_kdy0b2kx
test_report_ndct8b7u
test_report_vhyp3tv0
test_report_x9bf_7kq
```
