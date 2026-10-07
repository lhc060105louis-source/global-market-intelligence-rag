# RAG 证据、审批恢复与评测：GitHub 实现对照

调研日期：2026-10-07。通过 GitHub CLI 读取公开仓库，以下链接固定到本次实际读取的提交。只讨论可借用的设计，没有修改应用代码，也没有运行这些参考项目。本项目现状由主调研任务核对；下述适用建议是分析判断，并非参考项目对本项目的背书。

## 1. Onyx：把引用作为结构化数据交付

仓库：[onyx-dot-app/onyx](https://github.com/onyx-dot-app/onyx)，读取提交 `68dd959648704e0000b7bb070a699355bac11733`。

**实际实现**：`DynamicCitationProcessor` 接收引用编号到 `SearchDoc` 的映射；遇到未注册编号会跳过，文档标识用于去重。在超链接模式中，先发送 `CitationInfo` 元数据，再发送包含引用链接的文本，便于前端立即解析。引用列表按首次引用顺序记录。见 [citation_processor.py](https://github.com/onyx-dot-app/onyx/blob/68dd959648704e0000b7bb070a699355bac11733/backend/onyx/chat/citation_processor.py)。

**本项目可改**：在现有 evidence/source/version 校验上增加 `claims[]`，每条结论带 `evidence_ids[]`、原文摘录、文档定位和“支持/冲突/不足”状态；审批界面点击结论即可查看其依据。后端输出结构化引用映射，模型只选择已检索到的证据编号。可先用于风险调查草稿，不必一次重构全部聊天界面。

**验收建议**：引用编号必须来自本轮证据集合；无依据结论明确标记；不同版本证据不混合；点击引用能定位原文。引用合法性与结论是否真的受到支持应分开评测。

**不照搬**：无需引入 Onyx 整套企业搜索、连接器和部署架构。该引用处理器本身不证明语义正确，不能把“引用编号存在”当成“风险结论可信”。

## 2. LangGraph：人工审批是可恢复的持久状态

仓库：[langchain-ai/langgraph](https://github.com/langchain-ai/langgraph)，读取提交 `39c523eb0af1d192f739fd2b7ddfea38f3002a2a`。

**实际实现**：`interrupt()` 暂停并把待处理内容返回客户端，恢复时接受 `Command(resume=...)`；要求配置 checkpointer。其文档明确指出恢复会从节点开头重新执行，因此暂停点之前的副作用必须可重复执行而不产生重复业务结果。见 [types.py 中的 interrupt 和 Command](https://github.com/langchain-ai/langgraph/blob/39c523eb0af1d192f739fd2b7ddfea38f3002a2a/libs/langgraph/langgraph/types.py)。SQLite 实现持久化 checkpoint 和 writes，以 thread/checkpoint/task 等标识建立主键，并能读取某线程最新状态；实现也明确将同步 SQLite saver 定位于轻量使用。见 [SQLite saver](https://github.com/langchain-ai/langgraph/blob/39c523eb0af1d192f739fd2b7ddfea38f3002a2a/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py)。审批输入格式及非法恢复数据另有 [测试](https://github.com/langchain-ai/langgraph/blob/39c523eb0af1d192f739fd2b7ddfea38f3002a2a/libs/langgraph/tests/test_interruption.py)。

**本项目可改**：保留 FastAPI/SQLite，将现有 run 状态细化为有限步骤，保存当前步骤、输入版本、检索证据、草稿版本、重试次数和审批结果；增加按风险/状态查询历史的接口。后台执行器从数据库领取工作，完成一步再保存下一步，服务重启可以恢复已保存的进度。审批写入继续保持事务和幂等约束。

**验收建议**：关闭浏览器后能找回待审批调查；重启服务不会丢失已保存草稿；批准请求重试仍只产生一个案例；证据变化后要求重新调查或复核。

**不照搬**：无需立即迁移 LangGraph。借鉴持久状态与恢复边界即可；也不能把演示里的内存 saver 当作重启恢复方案。是否引入独立任务队列，应由真实并发和运维需求决定。

## 3. RAGFlow：先做“检索试验台”，再调生成提示词

仓库：[infiniflow/ragflow](https://github.com/infiniflow/ragflow)，读取提交 `cc72ecb0af18ade5d58f84d107af7cd59a88c39f`。

**实际文档**：检索测试页可配置相似度门槛、向量/关键词权重、重排、跨语言、元数据过滤和 Top 数量，展示召回内容、相关性和来源。文档把“没找对材料”和“找到了但回答不好”分开诊断，并建议按解析→切块→元数据→检索参数排查；测试页配置不会自动同步到实际 Agent。见 [retrieval_testing.md](https://github.com/infiniflow/ragflow/blob/cc72ecb0af18ade5d58f84d107af7cd59a88c39f/docs/guides/dataset/retrieval_testing.md)。本条核对的是仓库维护文档，未运行其 UI。

**本项目可改**：给四个知识域增加内部“证据检索诊断”入口：同一个问题展示候选片段、来源、主体/车型/市场/时间过滤、排序和被剔除原因。保存参数方案与评测结果，然后明确发布到调查配置，避免测试和生产行为不一致。优先检查已有 MaxKB 检索接口能提供哪些诊断字段。

**验收建议**：为每个领域准备应命中与应排除的证据；能回答“为什么检索到别的车型”“为什么漏掉正确来源”。先以结果证明需要混合检索或 reranker，再决定是否增加依赖。

**不照搬**：不直接迁移其检索栈；不照抄它的默认相似度门槛，不同 embedding/分数定义不可直接比较；也不把跨语言、重排等全部开关一次暴露给业务用户。

## 4. Ragas：把“找到依据”和“依据支持结论”分别测量

仓库：[vibrantlabsai/ragas](https://github.com/vibrantlabsai/ragas)，读取提交 `298b68274234c060deacab3cf5fb52aa3a20e885`。

**实际实现**：Faithfulness 将回答拆成原子陈述，对每条陈述判断检索上下文能否支持，再计算受到支持的陈述比例；无可评判陈述时返回 NaN。见 [faithfulness/metric.py](https://github.com/vibrantlabsai/ragas/blob/298b68274234c060deacab3cf5fb52aa3a20e885/src/ragas/metrics/collections/faithfulness/metric.py)。带参考答案的 ContextPrecision 对检索片段是否有用作判断，并按排序计算 average precision，见 [context_precision/metric.py](https://github.com/vibrantlabsai/ragas/blob/298b68274234c060deacab3cf5fb52aa3a20e885/src/ragas/metrics/collections/context_precision/metric.py)。

**本项目可改**：建立 30–50 条公开/合成风险案例作为首批基线，每条保存问题、正确主体与时段、应召回证据、禁止跨主体关联、应得结论或“信息不足”。分别记录检索命中/精度、结论支持度、错误跨域关联、拒答质量、耗时和人工接受率。改提示词、模型、检索参数时用同一批样本比较。

**验收建议**：先人工核准一小批标准答案；自动化模型评分作为辅助，并固定评审模型和配置。缺失评分、NaN 和失败要独立统计，不能算作通过。确定性规则先进入 CI，较昂贵的真实模型评测可在发布前运行。

**不照搬**：无需一开始把全部指标集成进产品；不要只展示一个平均总分。Faithfulness 衡量答案是否与给定上下文一致，并不验证原始来源本身是否正确，也不能代替跨品牌、车型、时间的业务规则检查。

## 推荐落地次序

1. 先做评测样本与检索诊断，获得目前问题的基线。
2. 在现有证据结构上补“结论—证据”对应关系及原文查看。
3. 把调查历史、待审批列表、持久步骤和重启恢复连成完整工作流。
4. 用同一评测集决定是否需要混合检索、reranker 或更换模型，而不是为了堆技术而迁移框架。

这些改动可以保留现有 FastAPI、SQLite、MaxKB、Ollama 和 React 组合。更有价值的方向是让风险调查可解释、可恢复、可比较。
