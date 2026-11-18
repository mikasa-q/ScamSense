# ScamSense（拆招）

AI 多角色求职反诈模拟训练系统。用户在同一聊天界面中分别与林悦、陈浩和王宇交流，通过提问、核实与决策练习识别招聘风险，并获得有行为证据的复盘报告。

当前处于 **P0 文档评审阶段**。资料已整理，事件与评分规则尚未冻结，**不具备进入 P1 的条件**；未启动 P1–P5、业务开发或部署。

## 设计文档

- [架构设计 v1.1](docs/architecture.md)：项目定位、固定角色与岗位、S0–S6 状态机、模块与数据模型、REST/SSE 契约、评分、安全、部署、备份恢复、测试及 P0–P5 规划。
- [P0 资料盘点与验收结论](docs/scenario/p0-inventory.md)：资料来源、缺失项、冲突与处理建议、负责人待确认问题和进入 P1 的条件。
- [角色卡与剧情设计 v1.0（原文）](docs/scenario/characters-and-story-v1.0.md)：三角色、固定岗位与主线的原始设计输入。
- [PR1 评审与 P0 任务（原文）](docs/reviews/pr1-p0-request.md)：本次文档整理范围与约束。
- [.env.example](.env.example)：公开前端变量与后端配置的占位清单；只将 `VITE_API_BASE_URL` 用于前端，密钥只能配置在后端受保护环境中。

## P0 业务文档

当前 MVP 采用精简事件方案 B。十个核心事件、可提前核实或退出的分支，以及逐项引用对话证据的四维评分草案见 [MVP 业务规则 v0.1](docs/scenario/mvp-business-rules.md)。

| 文档 | 核心结论 |
|---|---|
| [角色可见信息](docs/scenario/role-visibility.md) | 按角色与阶段整理边界；用户转述只让接收角色获知，不自动全局共享 |
| [原事件登记表](docs/scenario/events.md) | 留存 PR #1 评审时的 E01–E16 占位记录，供追溯方案变更 |
| [风险线索](docs/scenario/clues.md) | 保留五类已有线索，区分披露、展示、用户识别与核实；严重程度和触发细则未冻结 |
| [登记字段](docs/scenario/data-fields.md) | 原文九项资料可作合理招聘讨论；用途/必要性待确认，额外字段未提供，全部只用虚构示例 |
| [评分细则待确认](docs/scenario/scoring-rubric.md) | 四维权重不变，整理证据要求与每维三个边界案例；没有获批分档，不生成自拟分数 |
| [主线与分支走查](docs/scenario/flow-review.md) | 覆盖八条业务路径及匿名会话体验；约束已核对，具体事件/评分仍无法验收 |

## 已确定方案

前端使用 Vue 3、TypeScript、Vite、Element Plus、Vue Router 和 Pinia，构建为静态资源并发布到 Qoder Sites。后端使用 Python、FastAPI、Pydantic、SQLAlchemy 2.x、SQLite 和 Alembic，在腾讯云 CVM 上由 Nginx、Uvicorn 和 systemd 运行。普通请求使用 HTTPS REST，角色回复使用 SSE；模型通过后端统一调用 OpenAI 兼容 API。

剧情状态由规则引擎控制，三个角色使用独立 Prompt 和独立上下文。评估基于实际行为和可追溯证据，四维权重为风险识别 25%、主动核实 30%、决策合理性 25%、证据分析 20%。

## 下一步与待确认事项

负责人下一步评审方案 B 的事件与分支、线索披露条件、九项资料及评分档位。原 P0 盘点中的 Q01 已由方案 B 取代，其余问题可查原评审记录。[MVP 业务规则 v0.1](docs/scenario/mvp-business-rules.md) · [P0 盘点](docs/scenario/p0-inventory.md)

P0 通过后，再另行进入 P1–P4 的数据结构和契约阶段。服务器规格、域名、证书、模型服务和 Qoder Sites 实际发布配置继续保留 TODO。

本文档交付不包含业务代码、依赖安装或部署；功能测试与部署验收尚未执行。比赛公开应用地址：**TODO，完成实际部署验收后填写**。
