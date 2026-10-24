# Blender执行边界

正式无人值守Runtime继续为blocked，BlenderRuntime.isolated=False。
真实模型与正式本地Runtime的组合在API请求前拒绝；人工批准不替代隔离。

此前容器、命名空间、cgroup、seccomp、RLIMIT及调度器检查已合并到[历史实验与问题记录](EXPERIMENT_HISTORY.md)。
这些检查有明确历史日期，不表示清理时重新完成了环境验收。

已保留的GPT-6 Sol实验使用用户明确允许的逐份人工监督CPU执行，记录原始代码一致性、环境清理、网络/PID命名空间、资源采样及清理。
没有完成宿主机文件系统访问隔离或任务级CPU、内存、pids和输出容量硬配额，不能将其称为完整安全沙箱。
runtime_evidence中的可信CPU/World校准摘要只支持原人工监督配置，不改变正式入口的blocked状态。

新的无人值守后端需要实际验证文件访问边界、无密钥、断网、CPU/内存/进程/磁盘限制和完整超时清理；不能仅修改布尔值放行。
