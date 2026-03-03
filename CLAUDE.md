
```markdown
# 项目：旅游路线顾问智能体（Travel Route Advisor）

面向旅游公司客户的智能咨询系统。后端 Python FastAPI + LangGraph，前端 Next.js，
知识库 Coze，数据库 MySQL，LLM DeepSeek。

---

## 一、铁律（NEVER / ALWAYS，AI 必须无条件遵守）

1. **NEVER 在一个文件中写多个不相关的功能。** 一个文件只做一件事。
2. **NEVER 自行编造业务数据。** 路线详情/价格/团期必须来自 MySQL 或 Coze 工作流返回值，
   不得凭空生成示例数据（测试代码除外）。
3. **NEVER 修改不属于当前任务的文件。** 除非该文件是当前任务的直接依赖且必须改动。
   如需改动其他文件，先停下来告知我。
4. **NEVER 删除或覆盖已有的测试。** 只能新增或修改与当前任务直接相关的测试。
5. **NEVER 在代码中硬编码密钥、token、密码。** 全部走环境变量（.env）。
6. **NEVER 把多个任务混在一次提交中。** 一个任务一个 commit，commit message 格式见下方。
7. **ALWAYS 先读懂当前目录结构和已有代码再动手。** 动手前先列出你要创建/修改的文件清单，
   等我确认后再写。
8. **ALWAYS 在完成编码后写出该功能的测试方法（手动或自动）。**
   告诉我怎么验证这段代码是正确的。
9. **ALWAYS 保持已有代码的导入风格、命名风格、目录风格一致。**
   新代码必须与项目现有风格统一。
10. **ALWAYS 在函数/类/模块顶部写一行简短的 docstring 说明用途。** 不写行内注释。

---

## 二、项目目录结构（必须遵守，不得随意创建新的顶级目录）
```

travel-advisor/

├── backend/

│   ├── app/

│   │   ├── api/              # FastAPI 路由（每个资源一个文件）

│   │   │   ├── [chat.py](http://chat.py/)

│   │   │   ├── [session.py](http://session.py/)

│   │   │   ├── [lead.py](http://lead.py/)

│   │   │   ├── [compare.py](http://compare.py/)

│   │   │   └── admin/        # 管理后台 API

│   │   │       ├── [auth.py](http://auth.py/)

│   │   │       ├── [prompts.py](http://prompts.py/)

│   │   │       ├── [kb.py](http://kb.py/)

│   │   │       ├── [logs.py](http://logs.py/)

│   │   │       └── [config.py](http://config.py/)

│   │   ├── services/         # 业务服务层（每个服务一个文件）

│   │   │   ├── coze_client.py

│   │   │   ├── workflow_service.py

│   │   │   ├── kb_admin_service.py

│   │   │   ├── route_service.py

│   │   │   ├── session_service.py

│   │   │   ├── lead_service.py

│   │   │   ├── audit_service.py

│   │   │   └── rate_limiter.py

│   │   ├── graph/            # LangGraph 编排

│   │   │   ├── [state.py](http://state.py/)      # State Schema

│   │   │   ├── [graph.py](http://graph.py/)      # Graph 组装

│   │   │   └── nodes/        # 每个节点一个文件

│   │   │       ├── [router.py](http://router.py/)

│   │   │       ├── [collect.py](http://collect.py/)

│   │   │       ├── kb_search.py

│   │   │       ├── [select.py](http://select.py/)

│   │   │       ├── db_detail.py

│   │   │       ├── [followup.py](http://followup.py/)

│   │   │       ├── [price.py](http://price.py/)

│   │   │       ├── [visa.py](http://visa.py/)

│   │   │       ├── [external.py](http://external.py/)

│   │   │       ├── [rematch.py](http://rematch.py/)

│   │   │       ├── [compare.py](http://compare.py/)

│   │   │       ├── [chitchat.py](http://chitchat.py/)

│   │   │       ├── [response.py](http://response.py/)

│   │   │       ├── lead_check.py

│   │   │       └── state_update.py

│   │   ├── models/           # Pydantic 模型 & SQLAlchemy 模型

│   │   │   ├── [schemas.py](http://schemas.py/)    # Pydantic 请求/响应模型

│   │   │   ├── [database.py](http://database.py/)   # SQLAlchemy 模型

│   │   │   └── [state.py](http://state.py/)      # State 相关类型（如与 graph/state.py 合并也可）

│   │   ├── config/           # 配置

│   │   │   ├── [settings.py](http://settings.py/)   # pydantic-settings

│   │   │   └── [database.py](http://database.py/)   # DB 连接

│   │   ├── utils/            # 工具函数

│   │   │   ├── [logger.py](http://logger.py/)

│   │   │   ├── [security.py](http://security.py/)   # 脱敏、JWT 等

│   │   │   └── [helpers.py](http://helpers.py/)

│   │   ├── prompts/          # 提示词模板文件

│   │   │   ├── intent_classification.py

│   │   │   ├── requirement_collection.py

│   │   │   ├── response_generation.py

│   │   │   └── …

│   │   └── [main.py](http://main.py/)           # FastAPI 入口

│   ├── tests/                # 测试（镜像 app/ 结构）

│   ├── alembic/              # 数据库迁移

│   ├── requirements.txt

│   ├── .env.example

│   └── Dockerfile

├── frontend/

│   ├── src/

│   │   ├── app/              # Next.js App Router

│   │   ├── components/       # 组件

│   │   │   ├── chat/         # 聊天相关组件

│   │   │   ├── route-card/   # 路线卡片组件

│   │   │   ├── compare/      # 对比组件

│   │   │   ├── lead/         # 留资组件

│   │   │   └── admin/        # 管理后台组件

│   │   ├── hooks/            # 自定义 hooks

│   │   ├── services/         # API 调用封装

│   │   ├── stores/           # 状态管理

│   │   ├── types/            # TypeScript 类型定义

│   │   └── utils/            # 工具函数

│   ├── public/

│   ├── package.json

│   └── .env.example

├── docker-compose.yml        # MySQL + Redis

├── docs/                     # 项目文档

├── [CLAUDE.md](http://claude.md/)                 # 本文件

└── [README.md](http://readme.md/)

```

---

## 三、技术栈与命令

### 后端
- Python 3.11+, FastAPI, LangGraph, SQLAlchemy, Pydantic
- `cd backend && pip install -r requirements.txt`
- `cd backend && uvicorn app.main:app --reload` 启动开发服务器
- `cd backend && pytest tests/` 运行测试
- `cd backend && alembic upgrade head` 执行数据库迁移

### 前端
- Next.js 14+, TypeScript, Ant Design
- `cd frontend && npm install`
- `cd frontend && npm run dev` 启动开发服务器
- `cd frontend && npm run lint`
- `cd frontend && npm run build`

### 基础设施
- `docker-compose up -d` 启动 MySQL + Redis

---

## 四、编码规范

### Python 后端
- 使用 `async/await`，所有 I/O 操作必须异步
- 导入顺序：标准库 → 第三方 → 本项目，每组之间空一行
- 函数命名：`snake_case`
- 类命名：`PascalCase`
- 常量：`UPPER_SNAKE_CASE`
- 类型注解：所有函数参数和返回值必须有类型注解
- 错误处理：不使用裸 `except:`，必须捕获具体异常
- 字符串：统一使用双引号 `"`
- Pydantic 模型用于所有 API 入参和出参校验

### TypeScript 前端
- 严格模式，不使用 `any`
- 使用 named exports，不使用 default exports
- 组件文件名：`PascalCase.tsx`
- hooks 文件名：`useCamelCase.ts`
- 工具函数文件名：`camelCase.ts`
- CSS：使用 Ant Design 组件 + CSS Modules，不写内联样式

### Git 提交
- 格式：`<type>(<scope>): <description>`
- type：feat / fix / refactor / test / docs / chore
- scope：对应任务编号，如 `1.1`, `2.4`
- 示例：`feat(1.1): implement CozeClient with OAuth JWT authentication`
- 每个任务完成后立即 commit，不要积攒多个任务

---

## 五、AI 工作流程规范（每个任务必须遵循的步骤）

### 第 1 步：理解任务
- 阅读我给你的任务描述
- 阅读相关的已有代码文件
- 列出你理解的任务目标（用一句话）

### 第 2 步：制定计划
- 列出你将要创建或修改的文件清单（精确到文件名）
- 列出每个文件的主要内容（函数/类名 + 一句话说明）
- 列出对其他已有文件的改动（如果有）
- **等我确认后再开始写代码**

### 第 3 步：逐个文件编码
- 一次只写一个文件的完整代码
- 写完一个文件后暂停，等我确认后再写下一个
- 如果一个文件超过 200 行，考虑拆分

### 第 4 步：验证说明
- 代码写完后，告诉我如何验证：
  - 需要运行什么命令
  - 预期看到什么结果
  - 如果有自动测试，给出测试代码

### 第 5 步：收尾
- 确认所有新文件都已加入正确目录
- 确认没有遗留的 TODO 或占位符
- 给出 git commit 命令建议

---

## 六、文件大小与拆分规则

- 单个 Python 文件不超过 300 行（不含空行和注释）
- 单个 TypeScript 组件文件不超过 250 行
- 如果一个 Service 有超过 6 个公共方法，考虑拆分为两个 Service
- 如果一个 API 路由文件有超过 4 个端点，考虑拆分

---

## 七、依赖管理

- 添加新的 Python 依赖时，必须同步更新 `requirements.txt`
- 添加新的 npm 依赖时，说明为什么需要这个包
- 不安装不需要的包。如果标准库能做到，不引入第三方

---

## 八、环境变量（.env）

后端需要的环境变量（写在 .env.example 中）：
- `DATABASE_URL`
- `REDIS_URL`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL`（默认 deepseek-chat）
- `COZE_OAUTH_APP_ID`
- `COZE_KID`
- `COZE_PRIVATE_KEY_PATH`
- `COZE_WF_ROUTE_SEARCH_ID`
- `COZE_WF_VISA_SEARCH_ID`
- `COZE_WF_EXTERNAL_INFO_ID`
- `COZE_SPACE_ID`
- `COZE_ROUTE_DATASET_ID`
- `COZE_VISA_DATASET_ID`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD_HASH`
- `JWT_SECRET_KEY`

---

## 九、关键业务规则（AI 生成代码时必须牢记）

1. 路线推荐流程：Coze 知识库检索（只用于找 route_id）→ MySQL 查权威详情 → 回答
2. 价格和团期是动态数据，必须从 MySQL 实时查询，回答必须带 `updated_at` 时间戳
3. 留资只收手机号，留资成功后不强制转人工，机器人继续服务
4. 所有回答路线细节/价格/签证的内容必须基于数据源，模型只负责组织语言
5. 手机号必须脱敏存储（展示用）+ 原始存储（受控访问）
6. 每次请求必须有 trace_id，贯穿全链路日志
```