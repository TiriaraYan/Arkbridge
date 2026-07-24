# ark-ship

给 coding agent 用的结构化 ship（提交前检查）流程。

在你的项目里输入 `/ship`，agent （下文将以Claude Code为案例）会自动走完 **8 个步骤**：盘点改动 → 识别管线 → 同步文档 → 安全扫描 → 语法检查 → 干净提交 → 清理 → 自省。每一步都有明确的"做什么"和"为什么"——不是靠纪律记住该做什么，而是让流程替你记住。

## 它解决什么问题

裸 `git commit` 常见的翻车：
- 密钥/密码混进了提交（发现时已经 push 了）
- 改了后端 API 但忘了同步前端 / 文档
- 语法错误没检查就提交了，部署上去才发现
- `git add .` 把不相关的文件、别人的改动一起卷进去
- "fix → fix the fix → really fix this time" 碎 commit 链
- 改了代码但文档还在描述旧行为

`/ship` 不是万能的，但它把"老手凭经验会检查的事"变成了每次都跑的清单。

## 核心概念：管线意识

大多数项目不是铁板一块——它有前端、后端、数据库、部署配置等"管线"，每条管线有自己的文档、自己的规则、自己容易踩的坑。

`/ship` 的核心设计是：**每次提交前，先识别"这次改动触碰了哪条管线"，然后按那条管线的规则检查**。

这通过一个注册表文件，例如 `.claude/pipelines.json` 实现——它记录：
- **paths**：哪些文件属于这条管线（glob 匹配）
- **docs**：这条管线对应哪些文档（改了代码要检查文档是否过时）
- **rules**：这条管线有什么特殊规则（比如"数据库改动必须有 migration 文件"）
- **keywords**：关键词，用于在日志 / issue / changelog 里检索相关条目

一个文件可以同时命中多条管线——这是正常的（比如一个 auth middleware 既属于 `api` 也属于 `auth`）。

### 文档分层同步

真实项目的文档不止一处。`/ship` 支持检查多层文档：

| 层 | `pipelines.json` 字段 | 典型例子 |
|---|---|---|
| **项目内文档** | `docs` | `docs/api.md`、README、代码注释 |
| **外部文档** | `external_docs` | Wiki、Notion、GitHub 设计文档 |
| **状态追踪** | `keywords` | Changelog、issue tracker、Claude Code memory |

你不需要一开始就用全部三层。从 `docs` 一层开始就够了，随着项目长大再加。

## 安装

### 最简安装（1 分钟）

复制 `commands/ship.md` 到你的项目：

```bash
mkdir -p .claude/commands
cp claude-ship/commands/ship.md .claude/commands/
```

装完就能用 `/ship` 了。没有 `pipelines.json` 时，管线映射步骤会回退到手动判断。

### 完整安装（推荐，5 分钟）

```bash
# 1. 复制 skill 和脚本
mkdir -p .claude/commands .claude/scripts .claude/agents

cp claude-ship/commands/ship.md    .claude/commands/
cp claude-ship/scripts/map_pipelines.py .claude/scripts/
cp claude-ship/agents/security-auditor.md .claude/agents/

# 2. 创建管线注册表
cp claude-ship/pipelines.example.json .claude/pipelines.json
# 然后编辑 .claude/pipelines.json，按你的项目结构填写
```

### 配置你的 pipelines.json

打开 `.claude/pipelines.json`，按你的项目结构修改。核心是把你项目的目录结构映射到逻辑管线上。

一些现实中的例子：

<details>
<summary>Next.js 全栈项目</summary>

```json
{
  "pipelines": {
    "pages": {
      "summary": "Next.js 页面和路由",
      "paths": ["app/**", "pages/**"],
      "docs": ["docs/routing.md"],
      "rules": ["新页面需要添加到导航菜单", "动态路由需要配置 generateStaticParams"]
    },
    "api-routes": {
      "summary": "API 路由",
      "paths": ["app/api/**", "pages/api/**"],
      "docs": ["docs/api.md"],
      "rules": ["POST/PUT/DELETE 路由必须验证请求体", "需要错误处理中间件"]
    },
    "database": {
      "summary": "Prisma schema 和数据库",
      "paths": ["prisma/**", "src/db/**", "src/models/**"],
      "docs": ["docs/database.md"],
      "rules": ["schema 改动必须 prisma migrate dev", "不要手写 SQL，用 Prisma Client"]
    },
    "auth": {
      "summary": "认证（NextAuth）",
      "paths": ["src/auth/**", "app/api/auth/**", "middleware.ts"],
      "docs": [],
      "rules": ["Token 处理变更需要额外安全审查"]
    }
  }
}
```
</details>

<details>
<summary>Python FastAPI 项目</summary>

```json
{
  "pipelines": {
    "api": {
      "summary": "FastAPI 路由和依赖",
      "paths": ["app/routers/**", "app/dependencies/**", "app/schemas/**"],
      "docs": ["docs/api.md"],
      "rules": ["新路由必须加 Depends(get_current_user)", "响应模型必须用 Pydantic schema"]
    },
    "models": {
      "summary": "SQLAlchemy 模型和迁移",
      "paths": ["app/models/**", "alembic/**"],
      "docs": ["docs/models.md"],
      "rules": ["模型改动必须生成 alembic revision", "迁移必须可回滚（写 downgrade）"]
    },
    "services": {
      "summary": "业务逻辑层",
      "paths": ["app/services/**", "app/utils/**"],
      "docs": [],
      "rules": ["services 层不 import routers（单向依赖）"]
    },
    "infra": {
      "summary": "Docker 和部署",
      "paths": ["docker-compose*.yml", "Dockerfile", ".github/**", "nginx/**"],
      "docs": ["docs/deployment.md"],
      "rules": ["端口绑定 127.0.0.1", "新容器必须设 mem_limit"]
    }
  }
}
```
</details>

<details>
<summary>Flutter + Go 前后端分离</summary>

```json
{
  "pipelines": {
    "flutter-ui": {
      "summary": "Flutter 页面和组件",
      "paths": ["mobile/lib/screens/**", "mobile/lib/widgets/**"],
      "docs": ["mobile/docs/ui.md"],
      "rules": ["颜色必须用 AppColors 常量", "文案走 l10n"]
    },
    "flutter-state": {
      "summary": "状态管理（Riverpod/Bloc）",
      "paths": ["mobile/lib/providers/**", "mobile/lib/models/**"],
      "docs": [],
      "rules": ["Provider 必须有对应的单元测试"]
    },
    "go-api": {
      "summary": "Go 后端 API",
      "paths": ["server/handlers/**", "server/middleware/**", "server/routes/**"],
      "docs": ["server/docs/api.md"],
      "rules": ["新 handler 必须注册到 router", "错误统一用 AppError 类型"]
    },
    "go-db": {
      "summary": "数据库操作",
      "paths": ["server/db/**", "server/migrations/**", "server/models/**"],
      "docs": [],
      "rules": ["migration 文件名格式: YYYYMMDDHHMMSS_description.sql", "查询用 sqlx，不拼字符串"]
    }
  }
}
```
</details>

**Tips**：
- 刚开始不用追求完美——先把主要目录注册上去，后续 `/ship` 跑出 "unregistered" 文件时再补。
- `rules` 写你实际踩过的坑。不用硬凑——宁可空着，也不要写自己都不执行的规则。
- `docs` 如果你还没写文档，先留空数组 `[]`。`/ship` 不会因为没有文档就卡住。

## 使用

在 Claude Code 里：

```
/ship
```

就这样。Claude 会按步骤走完整个流程，每步都会给你看中间结果。遇到问题会停下来等你决定。

### 什么时候用

- **完成一个完整功能 / bug fix 后**。不是每写几行就 ship——等一个逻辑单元完成。
- **结束一个工作 session 前**。确保改动不会 silently 堆在 working tree 里被下一个 session 搞混。

### 什么时候不用

- 只改了一行注释 / typo fix → 直接 commit 就行。
- 探索性实验、还没定型的代码 → 先不 ship，定型了再说。

## 完整工作流程

`/ship` 不是孤立的——它是一个更大的工作流程的"收口"环节。完整的生命周期是：

```
接到任务 → 判规模 → (大活: 设计 review) → 实现 (边写边验) → /ship
```

### 1. 判规模

接到一个任务后，先判断：这是小活还是大活？

| 类型 | 特征 | 流程 |
|------|------|------|
| **小活** | Bug fix、单文件改动、已有明确方案 | 直接动手 → `/ship` |
| **大活** | 多文件架构改动、新管线、跨模块影响 | 先做设计讨论 → 确认方案 → 动手 → `/ship` |

判断标准：如果做完后 `/ship` Step 7 会发现"有好几个设计假设没跟用户说"，那说明这个任务应该在动手前先讨论设计。

### 2. 边写边验

这是一个容易忽视但非常重要的原则：**改完一个文件立刻验证，不要等写完所有文件再一起验**。

反面教材：改了 5 个文件后才发现第 2 个文件有语法错误 → 第 3-5 个文件可能建立在错误的基础上 → 返工。

正确做法：
- 每改完一个 `.py` 文件 → `python -m py_compile`
- 每改完一个逻辑单元 → 试一下能不能跑（import、启动、基本调用）
- 发现问题当场修，不要堆到 `/ship` 的 Step 4

如果你用 Claude Code 的 hooks，可以配一个 PostToolUse hook 让它自动帮你做（见下方"进阶用法"）。

### 3. /ship 收口

一个逻辑单元完成后，跑 `/ship`。它会帮你检查你可能忘记的事情。

重点：**完成一个完整的逻辑单元后再 ship**。不是每改几行就 ship（那会产生碎 commit），也不是堆了一大堆改动不 ship（那会让 working tree 越来越乱，下一个 session 打开直接懵）。

## 各组件说明

```
.claude/
├── commands/
│   └── ship.md                # /ship 命令本体（Claude 按这个流程走）
├── scripts/
│   └── map_pipelines.py       # 文件→管线自动映射器
├── agents/
│   └── security-auditor.md    # 独立安全审计 agent（Step 3 用）
└── pipelines.json             # 管线注册表（你的项目结构）
```

### commands/ship.md
`/ship` 的流程定义。Claude 读这个文件来知道该走哪些步骤、按什么顺序、每步检查什么。

### scripts/map_pipelines.py
接收 `git status --short` 的输出，根据 `pipelines.json` 的 glob 规则自动匹配每个文件属于哪条管线。输出：每条被触碰的管线 + 对应的文档 + 规则。不在任何管线里的文件会归到 "unregistered"——提示你考虑是否补注册。

### agents/security-auditor.md
一个只读的安全审计 agent。`/ship` Step 3 会把它当作独立的"第二双眼睛"——它没有写过这些代码，所以能冷静地审。它只输出 findings，不做任何修改。10 项检查清单覆盖：密钥泄露、注入、错误处理、认证、端口绑定、阻塞 IO、内存纪律、import 验证等。

### pipelines.json
你的项目"地图"。告诉 `/ship`：这个项目有哪些管线，每条管线管哪些文件、对应哪些文档、有什么规则。

## 进阶用法

### 添加 pre-commit hooks

`/ship` 流程之外，你还可以加 Claude Code hooks 来实时拦截问题。在 `.claude/settings.json` 里配置：

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "command": "bash .claude/hooks/postwrite_pycheck.sh $FILE_PATH",
        "description": "Python syntax check on save"
      }
    ]
  }
}
```

示例 hook（`hooks/postwrite_pycheck.sh`）——每次写 .py 文件自动检查语法：

```bash
#!/bin/bash
[[ "$1" != *.py ]] && exit 0
python3 -c "import ast; ast.parse(open('$1').read())" 2>&1
```

### 与 /code-review 配合

`/ship` Step 2.5 会在改动 ≥3 文件时建议先跑 `/code-review`。这两个流程是互补的：

| | /code-review | /ship |
|---|---|---|
| **关注点** | 逻辑正确性、代码质量、设计偏离 | 安全、文档同步、提交纪律 |
| **什么时候跑** | 大改动、跨模块改动 | 每次提交前 |
| **谁来跑** | 你主动，或 /ship 提醒 | 每次 /ship 自动包含安全扫描 |

### 团队使用

把 `.claude/` 目录提交到 Git 仓库，团队成员 clone 后自动获得 `/ship` 能力。`pipelines.json` 是共享的项目知识——新人入职就能看到"哪些文件属于哪条管线、有什么规则"。

### 多人 / 多 session 协作

当多个人（或多个 Claude Code session）同时在一个仓库里工作时，working tree 会变得混乱——你的改动和别人的改动混在一起，`git status` 分不清谁是谁的。

`/ship` Step 0 的"分区"设计就是为了解决这个问题。但光靠 `/ship` 不够，还需要一些习惯：

**及时 commit**：做完一个逻辑单元就 `/ship`，不要让改动堆在 working tree 里过夜。堆得越久，跟别人冲突的概率越高。真实案例：一个 session 改了 3 个文件没 commit 就结束了，下一个 session 打开看到这 3 个脏文件不知道是什么，不敢动也不敢删，只能先绕开——结果绕着绕着就绕出了 bug。

**不碰别人的文件**：如果 `git status` 里有不是你改的文件，leave it alone。就算你"顺手修了一下"，也会让原作者回来时困惑"这个文件怎么变了"。

**commit 粒度**：宁可一个大 commit 也不要一串碎 commit（`fix` → `fix the fix` → `really fix this time`）。碎 commit 链不只是 git history 难看——它让 `git bisect`（二分查 bug）失效，因为中间状态都是坏的。

### 危险命令保护

`/ship` 本身不包含 `git push`——push 是独立的决策，需要用户确认。同样，这些命令在 `/ship` 流程中绝对不应该出现：

- `git add .` / `git add -A` → 用 `git add <file>` 逐文件加
- `git reset --hard` → 可能丢掉别人的改动
- `git push --force` → 可能覆盖远端历史
- `rm -rf` 在仓库目录内 → 先 `git status` 确认

这些命令不是不能用，而是用之前必须确认"我知道我在做什么"。

### Rules 从事故中长出来

你的 `pipelines.json` 里的 `rules` 不需要一开始就写得很全。最好的 rules 来自真实的事故——每次翻车后加一条，让同样的坑不再踩第二次。

一些常见的"第一批 rules"（基本上每个全栈项目迟早会踩到）：

| 管线 | 事故 | Rule |
|------|------|------|
| api | 改了接口返回格式，前端直接白屏 | "API 响应格式变更必须同步前端" |
| database | 加了 NOT NULL 列，旧数据全报错 | "新增 NOT NULL 列必须给 DEFAULT 或分两步" |
| infra | Docker 端口绑了 0.0.0.0，数据库裸奔在公网 | "端口绑定 127.0.0.1 除非有明确理由" |
| auth | 新加的 API 忘了加鉴权，上线后被扫到 | "新端点必须有 auth middleware" |
| frontend | 用了 `innerHTML` 渲染用户输入，XSS | "用户输入必须转义后再渲染" |
| infra | `.env` 文件被 commit 到 GitHub，API key 泄露 | "git add 前检查有没有 .env / .key / .pem" |

写法要求：**Rule 必须是可验证的**。"写好代码"不是 rule，"API 响应统一用 `{ data, error }` 格式"才是——因为 `/ship` 可以对着检查。

## 数据合约：用 rules 守住系统间的约定

当你的项目不只是一个人写一个文件的时候，"前端发什么、后端收什么、数据库存什么"这些约定就开始变得重要——这就是数据合约。

数据合约不是一个额外的工具或框架。它是一种意识：**系统的每个边界（前后端之间、服务之间、代码和数据库之间）都有一个隐含的"协议"，你改了一边，另一边可能就炸了。**

新手最常见的翻车场景：
- 后端改了 API 返回的 JSON 字段名，前端还在读旧名字 → 页面空白
- 数据库加了 `NOT NULL` 列但没给默认值，旧数据全部报错
- 两个服务约定用 `status: "active"` 但一个写成了 `"Active"` → 静默过滤
- 错误响应格式不统一，前端写了 3 套不同的错误处理逻辑

### 怎么用 pipelines.json 守合约

`pipelines.json` 里每条管线的 `rules` 字段就是放合约的地方。把你踩过的坑、约定好的格式写进去，`/ship` 每次提交前会自动对着检查。

```json
{
  "api": {
    "rules": [
      "API 响应统一用 { data, error, message } 格式，不裸返对象",
      "枚举值统一小写蛇形 (active, pending_review)，前后端同源",
      "分页接口统一用 { items, total, page, page_size }",
      "时间字段统一 ISO 8601 带时区 (2026-07-24T12:00:00+08:00)"
    ]
  },
  "database": {
    "rules": [
      "新增 NOT NULL 列必须提供 DEFAULT 或分两步（先加 nullable 列，回填后再加约束）",
      "状态字段用 CHECK 约束，不靠代码保证合法值",
      "金额用 DECIMAL/NUMERIC，不用 FLOAT"
    ]
  }
}
```

这些 rules 不需要一次写完。**踩一个坑，加一条**——随着项目跑起来，rules 会自然长成你项目的"合约手册"。

### 合约和测试的关系

测试验证的是"这个函数对不对"，合约守的是"两个系统之间的约定有没有被打破"。两者互补：
- 测试能告诉你"这个 API handler 能正确处理请求"
- 合约能告诉你"但你返回的字段名改了，前端会挂"

如果你的项目有类型系统（TypeScript / Pydantic / protobuf），类型定义本身就是一种合约。`rules` 里可以写"API schema 变更必须同步更新 TypeScript 类型定义"这种守卫规则。

---

## 设计原则

这套流程从一个运行了 4 个月的真实全栈项目中提炼出来。以下是一些设计决策的背景：

**为什么用管线而不是简单的 checklist？**
因为"改数据库"和"改前端样式"需要检查的东西完全不同。一个通用 checklist 要么太宽（每次都检查用不上的项）要么太窄（漏掉特定领域的坑）。管线让检查精准命中。

**为什么要独立的 security auditor agent？**
自己审自己的代码，潜意识会跳过"我知道这里没问题"的地方。独立 agent 是一双冷眼——它没写过这段代码，没有作者偏见。

**为什么 Step 7 的"两个问题"是整个流程最重要的部分？**

测试抓 bug，audit 抓安全漏洞——这些都是已知类别的问题。但有两类问题它们抓不住：

**问题 1："有什么东西是你假定用户知道，所以直接跑过去了的？"**

AI 助手（或者你自己 review 自己的代码）经常会默默做一个决策然后不说。比如"我假设这个 API 只在内网调用所以没加鉴权"——测试在内网跑确实过了，audit 看不出问题，但部署到公网就裸奔了。这个问题逼 Claude 把隐含假设摊开来。

**问题 2："有什么额外的活是流程里没执行、但你现在觉得应该做的？"**

流程是有限的，但改动的影响是发散的。代码改完后站远一步看，经常能发现"哦这个地方其实也该改"或者"那个缓存可能需要清"。这个问题让 Claude 在 checklist 跑完后做一次开放式扫描——不是"清单上每项都绿了就完事"，而是"真的没遗漏吗？"

这两个问题的价值在于：它们抓的不是"已知类别的已知问题"，而是"你不知道自己不知道的东西"。

**为什么提交要 whitelist add？**
`git add .` 是新手最常见的事故来源。一个 `.env` 文件、一个编辑器临时文件、一个不相关的实验——全被卷进 commit。明确列出要提交的文件，虽然多打几个字，但避免了"哎怎么这个也推上去了"的事故。

**为什么 import 路径要 grep 验证？**
"我记得那个函数在那个文件里" → `from utils.helpers import do_thing` → 部署 → ImportError → 500。这种事故的根因是凭记忆写 import 路径。正确做法：写 import 之前先 `grep -rn "def do_thing\|class do_thing"` 确认它到底在哪个文件。听起来多此一举，但它杜绝了"代码在开发机能跑、到生产就 crash"的整类事故。

**为什么不要在生产环境做实验？**
调试一个问题时，你可能想"改一下数据库里这行数据试试"——直接在生产库 UPDATE 了一行。但这行数据被一个 cron job 读取 → 触发了一次消息发送 → 用户收到了一条莫名其妙的消息。**生产环境的任何写操作都可能触发你不知道的后续链路**。排查和实验一律在本地 / staging / 测试数据上进行。

**为什么 Step 0 要严格分区？**
我们实际跑了 4 个月的经验：最难 debug 的问题不是代码 bug，而是"这个文件到底是谁改的"。当多个工作 session 的改动混在一个 commit 里，出问题后 `git bisect` 定位不到根因、`git revert` 回滚不干净、blame 指向错误的作者。Step 0 的分区看似繁琐，但它把"谁的改动"这个问题在最前面就解决了，后面所有步骤都建立在这个干净的基础上。

---

## 一些实战教训

这些是从真实项目中总结的、新手容易踩的坑——不是所有坑都能被 `/ship` 自动拦住，但知道它们的存在能帮你主动避开。

### 碎 commit 综合症

```
a1b2c3d Fix login
d4e5f6g Fix login again
h7i8j9k Actually fix login this time
l0m1n2o Fix the fix of the login fix
```

这种 commit 链的根因是"改一点就急着 commit"。正确做法：在确认改动完整、能跑通之后再 commit 一次。`/ship` 强制你在 commit 前跑完验证，自然就不会出现"fix the fix"。

### 文档幽灵

代码改了但文档没改 → 新人按文档操作 → 实际行为跟文档不符 → 花半天排查"代码 bug" → 最后发现是文档过时。

`/ship` Step 2 的文档同步检查就是治这个病的。关键是 `pipelines.json` 里的 `docs` 字段把代码和文档的对应关系写死了——改了代码，`/ship` 自动提醒你检查对应的文档。

### 沉默的 working tree

Session 结束时忘了 commit → 下一个 session 打开看到一堆脏文件 → 不知道是半成品还是成品 → 不敢改也不敢删 → 被迫绕开或者硬着头皮猜。

`/ship` Step 6 的 post-commit cleanup 就是终结这个循环的：commit 后立刻检查 working tree 是否干净，有遗留就当场处理。

### 权限和安全

新手写的第一个 API，十有八九不加鉴权、不做输入校验、用 `detail=str(e)` 返回内部错误。这不是因为他们不知道安全重要——而是"先把功能跑通，安全以后再加"。问题是"以后"永远不会来。

`/ship` Step 3 的安全扫描把这个检查前置了：不是"以后再加"，而是"提交前必须过"。

## License

[CC BY-NC-SA 4.0](../../LICENSE) — 署名-非商业性使用-相同方式共享。可以自由使用和修改，但不可商用，二次分发需保持相同协议。
