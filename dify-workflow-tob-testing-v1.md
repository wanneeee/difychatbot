# Dify ToB 客户端联调测试手册 V1

> 状态：待客户端 / Dify 调试环境联调时使用
>
> 更新日期：2026-07-23
>
> 关联设计：`dify-workflow-configuration-v1.md`（工作流配置蓝本）、`llm-dify-integration-v1.md`（服务端侧集成设计）
>
> 正式契约：OpenAPI 3.0.3，版本 `0.8.0`

本文面向**在 Dify `POST /chat-messages` 调用侧**（ToB 服务端 / 联调人员）的测试手册，覆盖新
工作流约定的会话输入参数（`inputs`）、必填 / 可选边界、以及每个字段配置错误时应观察到的行为。
配合 `dify-workflow-configuration-v1.md` 第 4 章「开始节点与作用域校验」一起使用：该文档定义
工作流侧应当如何校验这些参数，本文定义联调时应当如何逐项验证。

## 1. 背景与范围

ToB 场景下，Dify 不再接收单一 `user_id`，而是由服务端在每次 `/chat-messages` 调用时，通过
`inputs` 传入一组会话级参数，工作流据此判断作用域、身份票据、上下文版本与目标计划信息。
本手册只覆盖 **Dify 侧 `inputs` 契约的联调验证**，不覆盖：

- ToB 服务端如何签发 `llm_job_ticket`（见服务端集成设计）。
- 知识库内容治理（见配置手册第 9 章）。
- 正式计划生成 Prompt 与 JSON Schema 细节（见配置手册第 7 章）。

## 2. `inputs` 参数总览

| 参数 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `assistant_scope` | 是 | 字符串枚举 | 仅允许 `general`、`patient` |
| `llm_job_ticket` | 是 | 字符串 | 仅用于 HTTP `Authorization`，不进入 Prompt / 知识库查询 / Answer |
| `context_schema_version` | 是 | 字符串 | 当前为 `patient_rehab_context_v1` |
| `prompt_version` | 是 | 字符串 | 用于运行记录与 Prompt 对齐，不参与业务判断 |
| `catalog_version` | 是 | 数字 | 当前为 `1`，用于知识库目录版本核对 |
| `llm_context_url` | 否（`patient` 作用域下必填） | 字符串（URL） | 患者上下文只读接口地址 |
| `llm_rehab_plan_url` | 否（生成正式计划时必填） | 字符串（URL） | 正式计划保存接口地址 |
| `target_plan_date` | 否（生成正式计划时必填） | 字符串（日期） | 目标计划日期 |

与 `dify-workflow-configuration-v1.md` 第 4.2 节「输入完备性」呼应的硬约束：

- `assistant_scope=general` 时，`llm_context_url`、`llm_rehab_plan_url`、`target_plan_date`
  三者均可为空——工作流不应因为它们缺失而报错。
- `assistant_scope=patient` 时，`llm_context_url` 必须存在；若本轮意图落在
  `plan_generate`，`llm_rehab_plan_url` 与 `target_plan_date` 也必须存在。
- 任一必填项缺失或类型不对，工作流应在开始节点直接终止，不尝试猜测或补全。
- `llm_job_ticket` 是唯一允许写入 HTTP Header 的凭据类字段；不允许出现在 Prompt、知识库
  查询、Answer、模板输出或自定义日志中。

## 3. 测试环境准备

1. 使用 Dify 调试环境（非生产 App API Key）发起 `POST /chat-messages`。
2. 每个用例单独起一个新会话（不复用 `conversation_id`），避免历史记忆污染判断。
3. 记录每次请求的原始 `inputs`、`query`，以及返回的 `workflow_finished.data.outputs`
   （尤其是 `client_action`、`plan_saved` 相关字段，如工作流已实现）。
4. 若使用真实 `llm_job_ticket`，确认其来自测试环境专用票据，不与生产票据混用。
5. 全程通过 HTTPS 调用；不关闭 SSL 校验（呼应配置手册第 6 章对 GET/PUT 出站请求的要求）。

## 4. 必填参数缺失/异常用例

| 用例 | inputs 变更 | 预期行为 |
|---|---|---|
| T01 | 缺失 `assistant_scope` | 工作流在开始节点终止，不进入意图分类 |
| T02 | `assistant_scope` 传入非法值（如 `admin`） | 工作流终止，提示作用域不识别，不默认降级为 `general` |
| T03 | 缺失 `llm_job_ticket` | 工作流终止，不发起任何 HTTP 出站请求 |
| T04 | 缺失 `context_schema_version` | 工作流终止，不读取患者上下文 |
| T05 | `context_schema_version` 与服务端实际版本不一致 | 工作流终止并标记版本不一致，不继续生成 |
| T06 | 缺失 `prompt_version` | 工作流终止（该字段仅用于对齐记录，但仍属开始节点必填校验范围） |
| T07 | 缺失 `catalog_version` | 工作流终止，不进入知识库检索 |
| T08 | `catalog_version` 传入非数字（如空字符串） | 工作流终止，不做隐式类型转换 |

以上用例的核心验证点：**任何一致性失败都应停止工作流，不尝试用默认值兜底**，与配置手册
第 4.2 节「任何不一致都终止工作流，不尝试猜测或修正作用域」的要求一致。

## 5. `general` 作用域用例

| 用例 | inputs | 提问内容 | 预期行为 |
|---|---|---|---|
| T10 | `assistant_scope=general`，其余可选字段为空 | 询问游戏玩法（公共知识） | 仅检索公共知识库，正常 Markdown 回答，不触发任何患者接口调用 |
| T11 | 同上 | 询问硬件安装/连接问题 | 命中产品说明文档，无文档时应明确说明资料不足，不编造 |
| T12 | 同上 | 要求分析自己的训练情况 | 工作流不读取患者上下文，输出 `client_action: context_required`（若已实现该字段） |
| T13 | 同上 | 要求制定正式康复计划 | 同 T12，不读取上下文、不保存计划，仅触发患者选择提示 |
| T14 | `assistant_scope=general` 但意外传入了 `llm_context_url` | 询问患者相关问题 | 工作流仍不得读取该 URL——`general` 作用域下患者上下文相关字段必须被忽略 |

T14 是重点回归用例：验证工作流对作用域的判断以 `assistant_scope` 本身为准，而不是"只要
URL 存在就去读"，防止服务端误传导致越权读取患者数据。

## 6. `patient` 作用域用例

| 用例 | inputs | 提问内容 | 预期行为 |
|---|---|---|---|
| T20 | `assistant_scope=patient` + 合法 `llm_context_url` | 询问游戏玩法 | 优先走公共知识分支，不强制读取患者上下文 |
| T21 | 同上 | 询问自己近期训练/评估情况 | 读取一次患者上下文，结合上下文与公共知识回答 |
| T22 | `assistant_scope=patient` 但缺失 `llm_context_url` | 询问自己近期训练情况 | 工作流终止或明确报错，不得静默跳过上下文读取直接瞎答 |
| T23 | `llm_context_url` 指向 401/403 的票据失效地址 | 任意患者相关问题 | 工作流终止，不继续使用模型编造回答（对应配置手册 12 章「患者上下文 401」） |
| T24 | `llm_context_url` 返回的 `context_schema_version` 与开始节点传入版本不一致 | 任意患者相关问题 | 工作流终止并标记版本不一致，不强行继续 |
| T25 | 合法上下文 + 要求制定正式计划，但缺失 `llm_rehab_plan_url` | 要求生成本周康复计划 | 工作流应在进入保存步骤前终止，不得生成计划后静默丢弃 |
| T26 | 合法上下文 + 缺失 `target_plan_date` | 要求生成本周康复计划 | 工作流终止，不使用当前系统日期等方式自行猜测目标日期 |
| T27 | 合法上下文 + 三个可选字段齐全 | 要求生成本周康复计划 | 走完整链路：检索版本化目录 → 生成计划 → 结构化校验 → `PUT llm_rehab_plan_url` → 仅保存成功后才输出"已保存"类回答 |
| T28 | 同 T27，但 `llm_rehab_plan_url` 返回非 `code=OK` | 同上 | 不得回复"已保存/已更新"等误导性话术，保存失败即视为失败 |

T21 与 T27 是核心正向路径，建议逐个字段单独截断验证（即：先跑通全量正确参数，再依次
去掉一个可选字段，确认工作流分别在正确的位置终止），避免多个字段同时缺失时掩盖真实的
校验断点。

## 7. `llm_job_ticket` 专项测试

| 用例 | 场景 | 预期行为 |
|---|---|---|
| T30 | 票据格式合法但已过期 | 患者上下文 GET / 计划 PUT 均返回票据失效错误，工作流终止，不重试 |
| T31 | 票据合法但权限不匹配（如票据对应患者与上下文不符） | 由服务端接口返回错误，工作流应原样终止，不在 Dify 侧做身份判断 |
| T32 | 票据在 Answer 输出中被误引用 | 人工审阅所有分支 Answer 与知识库检索请求，确认不包含票据原文 |
| T33 | 票据在错误提示中被误回显 | 触发 T23/T30 等失败用例后检查错误提示文本，确认不包含票据 |

`llm_job_ticket` 的唯一合法用途是 HTTP `Authorization: Bearer {{llm_job_ticket}}`，T32/T33
是防止其通过日志、Answer 或知识库查询参数外泄的回归检查项，对应配置手册第 4.2 节末尾的约束。

## 8. 版本一致性专项测试

| 用例 | 场景 | 预期行为 |
|---|---|---|
| T40 | `context_schema_version` 与患者上下文接口返回版本一致 | 正常继续 |
| T41 | `context_schema_version` 不一致 | 终止，不继续生成（同 T24） |
| T42 | `catalog_version` 与本次知识库检索到的目录版本一致 | 正常继续生成计划 |
| T43 | `catalog_version` 不一致（知识库已升级但开始参数未更新） | 终止并提示目录版本不一致，不使用旧版本 ID 拼凑计划 |
| T44 | `prompt_version` 与运行记录不一致（人工核对日志） | 不影响工作流继续执行，但需在联调记录中标注版本，用于事后追踪 Prompt 变更 |

T44 说明 `prompt_version` 是记录型字段而非强校验字段——测试目的是确认它被正确记录，而不是
确认工作流会因它中断。

## 9. `target_plan_date` 格式测试

| 用例 | 值 | 预期行为 |
|---|---|---|
| T50 | 合法日期（如 `2026-07-23`） | 生成计划的 `plan_date` 与该值一致 |
| T51 | 非法格式（如 `23/07/2026`） | 工作流终止或明确报错，不做隐式日期解析 |
| T52 | 过去日期 | 是否允许由服务端业务规则决定；Dify 侧只需确保透传值与生成结果一致，不擅自改写为当前日期 |
| T53 | 缺失（且意图为 `plan_generate`） | 同 T26，终止 |

## 10. 端到端联调检查单

按顺序执行，每步失败即停止并记录：

1. 使用 `general` + 全部可选字段为空，跑通 T10-T13。
2. 使用 `general` + 误传 `llm_context_url`，验证 T14 不越权读取。
3. 使用 `patient` + 合法必填字段、可选字段为空，跑通 T20-T22。
4. 使用 `patient` + 故意失效的 `llm_job_ticket` / `llm_context_url`，验证 T23-T24 正确终止。
5. 使用 `patient` + 合法上下文，依次去掉 `llm_rehab_plan_url`、`target_plan_date`，
   验证 T25-T26 分别在保存前终止。
6. 使用 `patient` + 参数齐全，跑通 T27 全量正确路径，确认 `plan_saved` 相关字段与
   PUT 请求真实发生（核对原始 HTTP 节点记录，而非仅看 Answer 文本）。
7. 人工审阅所有分支的原始 Dify SSE / 节点日志，确认 T32-T33 无票据泄漏。
8. 汇总测试记录，标注每条用例的 `prompt_version`、`catalog_version`，与
   `dify-workflow-configuration-v1.md` 第 16 章「配置交付物」要求的证据一并存档。

## 11. 已知不测范围

- 知识库内容准确性（属于配置手册第 9 章治理范畴，非本手册联调对象）。
- `client_action`、`plan_saved` 等字段若尚未在当前工作流版本实现，相关用例标记为
  "待工作流补齐后回归"，不视为本轮联调失败项。
- ToB 服务端如何生成 / 轮换 `llm_job_ticket`，属于服务端集成设计范畴。

## 12. 参考

- 工作流配置蓝本：`dify-workflow-configuration-v1.md`
- 服务端与安全设计：`llm-dify-integration-v1.md`
- 字段级契约：`server/docs/openapi.yaml`
