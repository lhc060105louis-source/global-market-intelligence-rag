# GitHub 同类项目调研与整体改进建议

调研日期：2026-10-07。目标项目：`lhc060105louis-source/global-market-intelligence-rag`。

本文记录调研时的建议与证据。第一批可靠性修复现已在本地实施，范围及测试结果见[实施验证记录](2026-10-07-release-verification.md)；后续设计建议尚未实施。调研通过 GitHub 搜索、仓库 API、源代码和维护文档，对照本地发布版分析。当时远端 `270c229` 与本地 `ebda4bf` 的应用代码一致，差异只有 README。未部署参考项目，也没有借用参考项目的性能数字作为本项目结果。

## 核心判断

下一阶段应围绕“同一个市场问题如何收集证据、形成结论、分派任务并复盘”组织产品。保留现有 VOC、B2B、KOL 三个业务模块及 FastAPI / SQLite / MaxKB / Ollama / React 技术组合，优先补充统一主体、证据关系、可恢复调查和真实业务数据路径。

项目已经有共享契约、数据同步、知识记录版本、风险周期、协同案例、任务、执行结果、监控和复盘模型。建议复用这些基础，避免再建立一套平行的案件和任务系统。

## 1. 参考项目及实际借鉴点

| 项目 | 核对材料与实际机制 | 本项目适用点 | 适用边界 |
|---|---|---|---|
| GPT Researcher | [ResearchConductor](https://github.com/assafelovic/gpt-researcher/blob/0957c301ed06c2a5857b834358c7227c739041d4/gpt_researcher/skills/researcher.py) 将研究规划、查询和上下文收集分开；[README](https://github.com/assafelovic/gpt-researcher/blob/0957c301ed06c2a5857b834358c7227c739041d4/README.md) 描述问题拆解和来源汇总 | 调查先生成领域问题清单，再检索和汇总；明确预算及缺口 | 阶段划分可以由普通函数实现，未必需要多个 Agent |
| BettaFish | [状态模型](https://github.com/666ghj/BettaFish/blob/b67928ff1ce515dd7672408221fb1e9500d0972d/InsightEngine/state/state.py) 保存搜索历史、来源、段落研究进度和反思次数；[InsightEngine](https://github.com/666ghj/BettaFish/blob/b67928ff1ce515dd7672408221fb1e9500d0972d/InsightEngine/agent.py) 提供按平台/时间等条件查询及情感分析处理 | VOC 按问题维护证据和调查进度，保留分平台、分时段结果 | 不将其宣传中的预测能力视为已验证事实，不直接移植整个采集系统 |
| VoC Insight | [模型](https://github.com/jinjian-liu/voc-insight/blob/f25389f607b25bdadcf3fb54b6601b12c37a6c91/backend/app/models.py) 分离反馈、分析、标准问题、反馈关联和活动；[问题接口](https://github.com/jinjian-liu/voc-insight/blob/f25389f607b25bdadcf3fb54b6601b12c37a6c91/backend/app/routers/issues.py) 实现关联反馈和记录处理结果 | 从重复投诉形成可处理的问题，保留人工确认及处理时间线 | 参考其轻量领域设计；当前 README 未指定开源许可证，因此不把公开可读代码当作可直接复制的代码库 |
| OpenCTI | [外部引用服务](https://github.com/OpenCTI-Platform/opencti/blob/c4487faf47c479d6e32d77d3b8b54f157b93efcd/opencti-platform/opencti-graphql/src/domain/externalReference.js) 将引用与实体/关系关联；[关系字段](https://github.com/OpenCTI-Platform/opencti/blob/c4487faf47c479d6e32d77d3b8b54f157b93efcd/opencti-platform/opencti-graphql/src/modules/attributes/stixCoreRelationship-registrationAttributes.ts) 包含起止时间和说明 | 品牌、车型、市场、法规、创作者之间的关系有来源、有时间、有确认状态 | 属于安全情报领域，借鉴实体和证据关系，不迁移整套领域模型或部署架构 |
| Onyx | [引用处理器](https://github.com/onyx-dot-app/onyx/blob/68dd959648704e0000b7bb070a699355bac11733/backend/onyx/chat/citation_processor.py) 使用引用编号到文档的映射，并发送结构化引用信息 | 每条结论对应具体依据，可点击查看原文 | 引用有效不等于语义结论正确 |
| LangGraph | [interrupt / Command](https://github.com/langchain-ai/langgraph/blob/39c523eb0af1d192f739fd2b7ddfea38f3002a2a/libs/langgraph/langgraph/types.py) 和 [SQLite checkpoint](https://github.com/langchain-ai/langgraph/blob/39c523eb0af1d192f739fd2b7ddfea38f3002a2a/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py) 支持持久暂停/恢复 | 人工审批、调查历史和步骤恢复 | 恢复可能重新执行节点，业务副作用必须幂等；不要求改用该框架 |
| RAGFlow | [检索测试文档](https://github.com/infiniflow/ragflow/blob/cc72ecb0af18ade5d58f84d107af7cd59a88c39f/docs/guides/dataset/retrieval_testing.md) 将检索参数、候选片段和来源展示与生成分开 | 增加内部检索诊断入口，先查为什么找错/漏找证据 | 本条核对的是维护文档，未实际运行界面；不能直接套用其检索阈值 |
| Ragas | [Faithfulness](https://github.com/vibrantlabsai/ragas/blob/298b68274234c060deacab3cf5fb52aa3a20e885/src/ragas/metrics/collections/faithfulness/metric.py) 检查陈述是否受到上下文支持；[ContextPrecision](https://github.com/vibrantlabsai/ragas/blob/298b68274234c060deacab3cf5fb52aa3a20e885/src/ragas/metrics/collections/context_precision/metric.py) 评估检索排序质量 | 分开评测检索、结论支持度和业务主体匹配 | 自动评分需要人工校准，不能验证原始来源本身真实 |

更详细的后四项实现笔记见 [RAG 工作流参考调研](2026-10-07-rag-workflow-references.md)。

## 2. 应先修复的发布版问题

### 2.1 VOC 六维引擎依赖缺失——已复现

`customer-voc/sentiment-analysis/voc-sentiment-analysis/six_dimension_service.py:52–81` 在运行时加载 `customer-voc/six-dimensions-v3.0/core.py` 和 `dimensions.py`。本地发布版和远端 GitHub 目录均没有这些文件。

通过标准库 `runpy` 加载该服务并调用 `_load_legacy_engine()`，得到 `FileNotFoundError: Legacy six-dimension engine is incomplete`。这是非空数据进入依赖该引擎的六维聚合路径时的阻塞问题，不是缺少模型密钥导致的错误。

建议：把经过公开发布审查的引擎纳入可安装模块，或明确声明并提供可安装依赖；新增从干净检出开始的“导入一条合成评论→完成聚合→推送 Hub”检查。现有原始工程不是发布版可复现性的替代品。

### 2.2 KOL 再投放混合固定示例和真实记录——代码确认

`creator-intelligence/global-creator-assessment-platform/app/services/reinvestment.py` 中：

- `_all_assets()` 从固定 `ASSETS` 建立名单；数据库中的 KOL 只有 handle 在名单内才参与覆盖。
- `get_reinvestment_evaluation()` 的建议分数和维度分数来自 `EVALUATIONS`。
- `get_portfolio_plan()` 使用固定候选 handle、`SCENARIOS` 和 `PROJECT`。

因此，新增一个真实创作者不会自然进入该再投放候选路径，部分建议也不会随真实复盘数据重算。此结论限定于再投放模块，不代表整个 KOL 平台都使用模拟数据。

建议：演示数据通过显式 seed/demo 模式加载；正式路径从数据库中的创作者、合作历史、报价和效果记录计算。每个输出标记实测、人工输入、估算或缺失；缺失时不显示示例值作为默认业务值。

### 2.3 延续上次审查的两项修复

- Agent 回退路径需要给最终生成预留工具预算，避免两条来源读取加四域检索用完六次额度。
- README 单独启动 Hub 的命令应加载 `.env`，并在启动时检测占位密钥。

## 3. 面向整个项目的修改方向

### A. 产品入口围绕“市场问题/案件”组织

现有 `rag/service/app/models.py` 已有 `CoordinationCase`、`CoordinationTask`、`ExecutionResult`、`MonitoringSnapshot`、`Retrospective`。以这些对象为主线，提供工作台、案件列表、待审批、证据详情、任务和复盘入口；保留 VOC/B2B/KOL 专用页面作为深入分析入口。

例子：某车型在某市场出现同类投诉 → 汇总原始反馈与时段 → 检查相关法规或售后事项 → 查看相关创作者内容/合作 → 人工确认影响和责任人 → 记录处理结果并回看趋势。这里的关联是待验证假设，不把同时出现当成因果关系。

验收：一个案件能从来源反馈一路导航到处理结果；关掉浏览器后仍可找回待审批内容；已批准任务与后续执行状态互相可见。

### B. 统一跨模块主体与来源，不另建庞大知识图谱

共享层已有 `Regulation`、`Project`、`DataSource` 和跨模块事件，KOL 也有 `shared_contracts.py` 适配。但展示名称、国家代码和业务实体仍在不同模块处理，例如共享枚举使用 `UK`，再投放项目使用 `GB`，KOL 局部有别名映射。

建议在现有共享层建立轻量主体标识与别名映射，统一品牌、车型、市场、组织、法规和创作者；关系记录保存来源记录 ID/版本、适用时段、关系类型与人工确认状态。`EU` 这类区域与国家使用明确类型，不把所有地区都强行当作国家。

首批只覆盖一个市场、一个车型和少量关联主体，用普通关系表实现。验收：同一车型不同拼写被正确归一；不同车型即使关键词相同也不会自动视为同一个主体；人工纠正可回溯。

### C. VOC 从指标展示补到问题管理

保留现有六维分析、去重、监控和 bucket 聚合，在其上增加可复核的问题关联：原始反馈、模型分析版本、人工确认、问题 ID、关联案件、状态与处理结果。学习 VoC Insight 的关系设计和 BettaFish 的逐问题搜索状态。

同一投诉的多条反馈应聚合到同一个问题，同时展示原文样本、独立来源数量、平台和时间分布。需要人工确认低置信或歧义分析。增加分平台/时段的趋势基线与最小样本提示，并用标注样本判断是否确实改善误报。

验收：同一批合成投诉聚合结果可解释；能查看误判并修正；一次修正不会丢失原始分析结果；关闭案件后可以比较后续信号。

### D. B2B 从法规列表补到版本变化与影响复核

现有法规记录已经包含官方来源、最后核验日期、状态、版本和材料清单；业务接口也会在发布和归档时推送事件。因此重点是把已有字段形成工作流。

建议记录法规版本差异和适用时段，展示受影响项目、材料清单和宣传事项；来源变化先生成待核验事项，人工确认后再更新正式结论及关联任务。检索历史问题时按当时有效版本取证。

验收：同一法规新增版本后能看到变化、来源与受影响对象；旧案件保留当时依据；尚未人工核验的新内容不会覆盖已批准结论。

### E. KOL 从固定推荐补到有依据的比较和情景计算

现有 `scoring.py` 已支持缺失维度、数据完整度和人工覆盖，这些应保留。先修再投放固定名单，再把每个维度的分数连接到来源、采集时间和计算版本。

候选比较统一市场、平台、统计时段和计算口径；预算情景从真实候选、报价、已知风险和数据完整度计算。没有可靠受众重叠或转化数据时明确缺失，不补一个看似精确的百分比。人工批准后的合作结果进入现有复盘记录，作为之后比较的依据。

验收：新增创作者可进入候选池；改报价后预算结果随之变化；数据不足的候选显示不足而非示例分；历史决策可用当时的数据重现。

### F. Agent 采用阶段化调查和逐结论引用

学习 GPT Researcher 的阶段划分：确认问题范围 → 生成领域查询 → 检索并校验 → 汇总支持与冲突证据 → 形成草稿 → 人工审核。每一步有明确输入、输出、耗时与预算，避免全部逻辑依赖一次自由规划。

学习 Onyx 的结构化引用机制：草稿增加结论列表，每条结论保存证据 ID、对应摘录、适用时段和支持/冲突/不足状态。后端验证引用属于本轮证据集合，并保留现有版本与哈希检查。语义支持度另行评测。

学习 LangGraph 的持久状态：数据库保存执行步骤、检索结果、草稿版本和审批状态，提供按风险/状态查询历史接口。可以先用现有 SQLite 和后台执行器实现；恢复后的写入继续遵守事务与幂等约束。

### G. 检索诊断、效果评测和干净环境验收

借鉴 RAGFlow 做内部诊断：显示问题、候选片段、来源、主体/地区/时间匹配结果、排序和剔除原因。先衡量当前 MaxKB 检索表现，再决定是否增加重排或混合检索。

借鉴 Ragas 分开统计检索命中、结论支持度、错误跨域关联、正确识别信息不足、耗时和人工接受率。首批 30–50 个公开/合成案例覆盖同车型、不同车型、过期证据、冲突证据及缺失领域；模型评分只作辅助，人工核准基线。

GitHub CI 首先运行干净安装和各服务测试，重点加入 VOC 引擎完整性、Agent 多来源预算、审批幂等/回滚/过期、KOL 新增候选及真实数据路径、前端类型检查。真实模型评测可在发布前独立运行，避免普通单元测试依赖外部服务。

## 4. 建议分批交付

| 批次 | 改动 | 完成标准 |
|---|---|---|
| 第一批：可以复现 | 补 VOC 依赖；拆分 KOL 示例与正式路径；修 Agent 预算和启动说明；补对应自动检查 | 新机器用合成数据走通 VOC→Hub→调查→批准；新增真实 KOL 不被固定名单排除 |
| 第二批：可以解释 | 主体与别名；逐结论引用；检索诊断；首批评测 | 每条结论可追到原文和版本；能识别跨车型误关联与信息不足 |
| 第三批：可以持续使用 | 案件工作台；调查历史；步骤恢复；任务与复盘导航；法规变化复核 | 中断后继续处理；批准、执行和复盘形成一条可追溯记录 |
| 第四批：有数据再优化 | 根据基线决定重排、模型、阈值、并发和预算情景算法 | 同一评测集上能说明改善了什么、代价是什么 |

整体架构可以渐进调整。当前没有证据表明必须更换向量库、拆更多微服务、引入图数据库或多个自治 Agent。是否增加这些依赖，应由上述验收和评测发现的具体瓶颈决定。

## 5. 调研边界

- GitHub 搜索包含 market intelligence、customer feedback analysis、deep research、creator analytics、BettaFish 和 OSINT intelligence platform；按相关机制筛选，未以 star 数代替质量判断。
- 参考项目的代码和文档说明实现思路，不构成本项目已获得相同能力的证据。
- VOC 缺失引擎进行了直接函数调用复现；KOL 再投放问题通过代码确认，未运行完整 UI。
- 本次只新增调研文档，未修改应用代码、安装框架、发布内容或更改远端仓库。
