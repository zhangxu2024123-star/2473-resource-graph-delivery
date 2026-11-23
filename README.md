# 资源图谱完整版 · 交付说明

【S6-PLAN-009】会员空间平台 · 资源图谱完整版：节点与关系类型定义草案
交付日期：2026-11-23 ｜ 版本：v1.0 ｜ 全部数据为虚构示例

---

## 一、三分钟验收

```bash
pip install -r requirements.txt
python verify.py                    # 期望 RESULT: PASS（30/30 节点、50/50 关系）
python verify.py --self-test        # 期望 4/4 correctly rejected
```

跑完这两条就能确认三件事：样例确实通过 Schema；Schema 确实能挡住坏数据；治理规则不是纸面约定。

## 二、先读哪个文件

| 顺序 | 文件 | 为什么 |
|---|---|---|
| 1 | `docs/graph-model.pdf`（或 `.md`） | 主文档：10 类节点、10 类关系、来源映射、治理规则、边界情况、验收对照表 |
| 2 | `diagram/resource-graph.png` | 一张图看懂节点与关系的整体结构（含 AI 待复核关系的标注） |
| 3 | `schema/node.schema.json`、`schema/edge.schema.json` | 机器可执行的约束，比文档更权威；冲突时以 Schema 为准 |
| 4 | `data/nodes.json`、`data/edges.json` | 30 个节点 + 50 条关系的虚构样例 |
| 5 | `verify.py` | 校验脚本；也可直接作为 CI 门禁（非 0 退出即阻断） |
| 6 | `evidence/*.txt` | 本次实跑的原始输出（未删改），便于与你的复跑结果对照 |

## 三、目录结构

```
delivery_2473/
├─ README.md                     本文件
├─ docs/
│  ├─ graph-model.md             主文档（Markdown）
│  └─ graph-model.pdf            主文档（PDF，16 页）
├─ schema/
│  ├─ node.schema.json           节点 Schema（draft 2020-12）
│  └─ edge.schema.json           关系 Schema（draft 2020-12）
├─ data/
│  ├─ nodes.json                 30 个虚构节点（10 类 × 3）
│  └─ edges.json                 50 条虚构关系（10 类 × 5）
├─ diagram/
│  ├─ resource-graph.svg         关系示意图源文件
│  └─ resource-graph.png         2 倍分辨率（3200×2000）
├─ evidence/
│  ├─ verify-output.txt          校验实跑输出
│  ├─ self-test-output.txt       自测实跑输出
│  └─ env.txt                    运行环境
├─ verify.py                     校验脚本
└─ requirements.txt              依赖锁定（jsonschema==4.26.0）
```

## 四、这份模型做了什么取舍

**1. 治理规则写进 Schema，而不是只写在文档里。**
`origin=ai` 的边必须同时满足 `review_status=pending`、`reviewed_by=null`、`visibility=private`，缺一即校验失败。`--self-test` 的第三个坏样例就是「AI 关系想直接对会员可见」，它会被拒绝。这样「AI 关系未经人工确认不得对外」不依赖开发自觉。

**2. 「需新采集」变成可判定字段。**
每个节点都必须声明 `source_state`：`phase1` 必须给出 `source_ref`（表 + 记录 + 字段），`new_collection` 必须给出 `collection_hint` 且不许伪造 `source_ref`。跑一次脚本就能得到 `phase1 18 / new_collection 12`，不需要逐条读文档核对。

**3. 能力、需求、专家、政策四类明确标注「需新采集」。**
一期没有对应对象，硬拿行业标签或招商线索代替会污染语义（详见文档 §6.3）。这四类需要的是采集表单，不是抽取脚本。

**4. 金额彻底不进图模型。**
两份 Schema 都是 `additionalProperties: false`，任何金额字段会被直接拒绝。商机金额按 `opportunity.id` 回查业务接口；AI 不计算、不排序、不生成金额。

**5. 边界情况给了判定规则，不留判断题。**
时间半开区间与重叠裁决、`weight=0` 的语义、可见性继承对照表、证据软删除降级、类型扩展的 6 处改动清单——每条都配了样例 ID 可直接对照；唯一例外是 `weight=0`，本期没有为凑样例而构造 0 值边，文档 §8 已如实说明。

## 五、已知留白（不擅自扩范围）

- `policy` 节点本期没有对应边类型（政策与企业的「适用」关系不在工单给定的 10 类内），已在示意图标注，v1.1 拟增 `related_to`，改动清单见文档 §9.2。
- `industry_tag` 的母子层级暂用 `tag_level` 近似，未建 `parent_of` 边。
- 图数据库实现、ETL、复核队列界面、Figma 稿均不在本单范围。

## 六、与 S2-CRM 的对接点（依赖工单）

本单是设计交付、不含运行时代码，因此**不调用** S2-CRM 的接口；但节点与边的来源全部指向 S2-CRM 的核心对象。后续实现 ETL 时的对接面如下，接口未就绪时按统一技术约定先用接口桩 / mock：

| 本单定义 | 依赖的 S2-CRM 对象 | 对接方式 |
|---|---|---|
| `company` / `contact` / `opportunity` 节点 | CRM 企业、联系人、商机 | 只读字段映射（文档 §6.1），不复制手机号 / 邮箱明文 |
| `industry_tag` 节点、`tagged_with` 边 | 标签中心 `tax_tag`、`crm_company_tag` | 只读同步，`weight=1.0` |
| `attended` 边 | 活动报名 `event_registration`、签到 `event_checkin` | 只读同步 |
| 商机金额 | `crm_opportunity.estimated_amount_first_year` | **不入图**，按 `opportunity.id` 回查业务接口 |
| `capability` / `demand` / `expert` / `policy` | 无对应对象 | 走新采集表单，不依赖 S2-CRM |

对接只依赖字段名与主键：只要 S2-CRM 的字段与 §6.1 一致，Schema 与 30+50 条样例可直接复用，无需改动图模型。

## 七、验收对照

| 验收标准 | 看哪里 | 怎么验 |
|---|---|---|
| 10 节点 / 10 关系，各有定义、属性、示例 | 文档第 4、5 章；`data/` | 数章节；脚本输出 `node_type 10/10, edge_type 10/10` |
| 每种节点写明一期来源或「需新采集」 | 文档第 4 章各节 + 第 6 章；Schema 的 `source_state` | 脚本输出 `source coverage: phase1 18 / new_collection 12` |
| 30 节点 + 50 关系通过 Schema 校验 | `data/`、`schema/`、`verify.py` | `python verify.py` → `30/30 valid`、`50/50 valid`、`RESULT: PASS` |
| `origin=ai` 须复核、确认前不对外 | 文档 §7.1；Schema 的 `if/then` | 脚本输出 `ai review queue: 10 pending, member-visible ai edges: 0`；`--self-test` 4/4 |

---

如需调整字段命名、示例编号或图示配色，属于验收标准 1–4 范围内的口径澄清，不计入修订轮次。

如需仓库形态：本目录不含外部依赖（除 `requirements.txt` 中的 `jsonschema`），可直接作为 Git 仓库根目录提交，`python verify.py` 即为 CI 门禁命令。
