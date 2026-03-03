本版本 Coze 使用边界与约定

### 0.1 Coze 在本版本承担什么

- **后台运维层**：创建/查看/修改/删除知识库；上传/管理知识库文件；查看文件处理进度
- **线上检索层**：不直接调用“检索API”，而是调用 **执行工作流**，工作流内完成“知识库检索 + 格式化输出（route_id等）”

### 0.2 你需要在 Coze 平台侧准备的对象

- `space_id`：工作空间 ID
- `dataset_id`：知识库 ID（路线库、签证库各一个或多个）
- `workflow_id`：已发布工作流 ID（至少两个：路线检索工作流、签证检索工作流）
- `bot_id`（可选）：若工作流包含数据库节点/变量节点等要求关联智能体，则必须传
- `app_id`（可选）：仅运行扣子应用中的工作流时需要
- `Access_Token`：个人令牌/服务令牌，必须开通对应权限

### 0.3 强制输出协议（建议你在工作流最后一步保证）

为了你的“RAG→DB 二段式”稳定，建议工作流最终输出 `data` 字段里是 JSON 字符串，且至少符合：

**路线检索工作流输出**
入参为字符串类型"input"
```json
{
  "output": [
    {
      "documentId": "7612957641987604521",
      "output": "basic_info：行程标题为“【超惠泰新马】三国全景10日游”，目的地为“泰国、新加坡、马来西亚”，共10天9晚。\nrag_abstract：泰新马10日游，有文化观光、海岛度假等玩法。打卡大皇宫、鱼尾狮、黑风洞，体验骑大象、巧克力DIY。费用含交通、住宿、门票。\nfile_url_id：https://oss.hl1j.com/uploads/20251217/4a52285ec2b24ce7e0313e3cc7e6a5b9.pdf"
    }
  ]
}
```

**签证检索工作流输出**
入参为字符串类型"input"
```json
{
  "output": [
    {
      "documentId": "7612957641987604521",
      "output": "工作日：</td><td colspan=\"4\" rowspan=\"1\">面试后当天知道结果，通过签证正常7-10个工作日出证</td><td colspan=\"1\" rowspan=\"1\">是否面试：</td><td colspan=\"2\" rowspan=\"1\">本人面试，提前预约。符合条件可免面试。</td></tr><tr><td colspan=\"1\" rowspan=\"1\">注意事项：</td><td colspan=\"7\" rowspan=\"1\">自2016年11月29日起，凡持有10 年 B1/B2美国签证的中国大陆护照，必须需要再次在美国领馆网站上更新个人信息EVUS 才能入境美国有效期2年，护照有效期不够2年的批到护照有效期，若申请人在登记EVUS后有效期内换发新护照或签证页信息有所变更也必须要重新登记EVUS。 自2014年11月12日起，美国B类签证有效期最长可达10年，并非全部申请人都可以获得10年有效签证，"
    }
  ]
}
```

**外部信息检索工作流输出**
入参为字符串类型"input"
```json
{
  "output": " 北疆、东疆大部降温5℃~8℃，北疆北部、乌鲁木齐北部等区域降温10℃~12℃（达强寒潮标准）；\n- 阿勒泰北部、东部降幅12℃~16℃，为特强寒潮。\n\n### 二、分时段天气详情\n#### 1. 3月3日及前后（最新实况）"
}
```

---

## 1. 通用鉴权与 Header 规范（Coze 全家桶通用）

### 1.1 鉴权 Header

- `Authorization: Bearer $Access_Token`
- `Content-Type: application/json`

### 1.2 数字精度保护 Header（仅 document 系列接口强烈建议加）

- `Agw-Js-Conv: str`

### 1.3 错误处理统一原则

- 只要响应 `code != 0`：视为失败
- 记录：
    - `msg`
    - `detail.logid`（非常关键，便于找 Coze 团队排障）
- 后端应把 `logid` 写入你们的 `trace_id/run_id` 关联日志中

---

## 2. 知识库 Dataset 管理接口（后台必需）

## 2.1 创建知识库（Create Dataset）

- **POST** `https://api.coze.cn/v1/datasets`
- 权限：`createKnowledge`
- Body：
    - `name`（必选，<=100字符）
    - `space_id`（必选）
    - `format_type`（必选：0文本，2图片）
    - `description`（可选）
    - `file_id`（可选：图标，来自上传文件接口；你还没贴上传文件接口，后续补）
- Resp：
    - `data.dataset_id`
    - `detail.logid`

**本项目约定**

- 路线库、签证库都用 `format_type=0` 文本知识库

---

## 2.2 查看知识库列表（List Datasets）

- **GET** `https://api.coze.cn/v1/datasets`
- 权限：`listKnowledge`
- Query：
    - `space_id`（必选）
    - `name`（可选模糊）
    - `format_type`（可选）
    - `page_num`（默认1）
    - `page_size`（默认10，1~300）
- Resp：`data.dataset_list[]`（包含 dataset_id、doc_count、status、chunk_strategy 等）

**后台用途**

- 展示空间资源库下所有知识库（含扣子/火山）
- 但你文档强调：document 文件列表等详细操作只支持扣子知识库

---

## 2.3 修改知识库信息（Update Dataset）

- **PUT** `https://api.coze.cn/v1/datasets/:dataset_id`
- 权限：`update`
- Body：
    - `name`（必选）
    - `file_id`（可选）
    - `description`（可选）

**关键注意（你文档明确）：全量刷新**

- 未传字段会恢复默认配置
    
    ✅ 后台实现建议：编辑页保存“当前值”，提交时总是把 name/file_id/description 都带上（即便不改）
    

---

## 2.4 删除知识库（Delete Dataset）

- **DELETE** `https://api.coze.cn/v1/datasets/:dataset_id`
- 权限：`delete`

**风险提示**

- 会删除库内全部文件，并自动解绑绑定智能体
    
    ✅ 后台要二次确认，并显示 doc_count、dataset_id、logid
    

---

## 3. 知识库文件 Document 管理接口（后台必需）

## 3.1 上传知识库文件（Create Document）

- **POST** `https://api.coze.cn/open_api/knowledge/document/create`
- 权限：`createDocument`
- Header：建议带 `Agw-Js-Conv: str`
- Body：
    - `dataset_id`（必选）
    - `document_bases`（必选，最多10）
    - `chunk_strategy`（必选，每次都要传）
    - `format_type`（必选：0文本、2图片）

### 3.1.1 document_bases.source_info 支持的上传方式（按你文档）

**A. 本地文件 Base64（文本库支持）**

- `file_base64`
- `file_type`：pdf/txt/doc/docx
- （可选）`document_source=0`（文档里是枚举说明，不强制但建议传清楚）

**B. 在线网页（文本库支持）**

- `web_url`
- `document_source=1`
- （可选）`update_rule`：是否自动更新、更新频率（>=24小时）

**C. 图片 file_id（图片库支持）**

- `source_file_id`
- `document_source=5`

### 3.1.2 chunk_strategy 分段策略

- `chunk_type=0`：自动分段与清洗（MVP推荐）
- `chunk_type=1`：自定义（separator/max_tokens/remove_extra_spaces/remove_urls_emails）
    - max_tokens：100~2000

**建议（本项目MVP）**

- 路线库/签证库：先用 `chunk_type=0`
- 如果你的“路线文档”格式统一（每条路线一个块且带 route_id），可切到 `chunk_type=1` 并用分隔符实现更可控的块边界

### 3.1.3 返回值与后续动作

- Resp：`document_infos[]` 含 `document_id/status/slice_count/...`
- 由于处理可能异步，上传后应立即进入“进度查询”流程（见 3.4）

---

## 3.2 修改知识库文件（Update Document）

- **POST** `https://api.coze.cn/open_api/knowledge/document/update`
- 权限：`updateDocument`
- Body：
    - `document_id`（可选但实际上你需要传）
    - `document_name`（可选）
    - `update_rule`（可选，仅网页时）

---

## 3.3 查看知识库文件列表（List Documents）

- **POST** `https://api.coze.cn/open_api/knowledge/document/list`
- 权限：`listDocument`
- Body：
    - `dataset_id`（必选）
    - `page`（默认1；注意你示例里出现 page:0，这里你们实现时建议按文档“默认1”处理，兼容0则当作1）
    - `size`（默认10）
- Resp：
    - `document_infos[]`
    - `total`

---

## 3.4 查看文件上传/处理进度（Document Process）

- **POST** `https://api.coze.cn/v1/datasets/:dataset_id/process`
- 权限：`readDocumentProgress`
- Body：`document_ids[]`（同一个 dataset 内的多个文档）
- Resp：`data.data[]` 每个文档：
    - `status`：0处理中 / 1处理完毕 / 9处理失败
    - `progress`：0~100
    - `status_descript`：失败原因（可能有）
    - `url/size/type/document_name`

**后台实现建议**

- 上传后轮询：
    - 前端展示进度条
    - `status=1` 完成后标记可用
    - `status=9` 显示失败原因，并给“一键重传/删除”入口

---

## 3.5 删除知识库文件（Delete Documents）

- **POST** `https://api.coze.cn/open_api/knowledge/document/delete`
- 权限：`deleteDocument`
- Body：`document_ids[]`（最多100）

---

## 4. 工作流执行接口（线上检索核心）

你明确：**检索走“调用工作流”**，知识库配置在工作流中，后端只负责执行工作流、传入 query、解析输出。

## 4.1 执行工作流（非流式）

- **POST** `https://api.coze.cn/v1/workflow/run`
- 权限：`run`
- 超时：90秒无响应会断开（Coze说明）
- Body 关键字段：
    - `workflow_id`（必选，必须已发布，否则4200）
    - `parameters`（可选，你文档描述为 JSON 序列化字符串，但示例又是对象；实践中建议你们统一当“JSON对象”传，若 Coze 强制字符串则在客户端封装时序列化）
    - `bot_id`（可选但重要：若工作流需要关联智能体，必须传且智能体需发布为API服务）
    - `app_id`（仅应用内工作流需要）
    - `ext`（可选：纬度、经度、user_id）
    - `is_async`（可选：仅付费版/企业版，否者6003）
    - `workflow_version`（资源库工作流版本）
    - `connector_id`（渠道：默认1024 API渠道）
- Resp：
    - `code`
    - `data`：执行结果（通常 JSON 序列化字符串）
    - `debug_url`：可视化试运行过程（有效期7天）
    - `usage`：token统计（参考）
    - `execute_id`（异步执行时）
    - `interrupt_data`：中断信息（非常重要）

---

## 4.2 interrupt_data（中断）处理策略（必须写进你后端）

工作流可能因为“输入节点/问答节点/OAuth”等触发中断，返回：

- `interrupt_data.type`
- `interrupt_data.event_id`
- `interrupt_data.required_parameters`（需要补的参数定义）
- `interrupt_data.data`（控制内容，通常是 JSON 字符串）

**你后端的处理建议（MVP）**

- 如果是检索工作流（路线/签证），一般不应出现需要用户补参数的中断
    - 若出现：后端直接把 `required_parameters` 转成前端 `ui_action`（例如让用户补“出行日期/目的地”），并把 event_id/type 存入 session state
- 后续如你们要支持“恢复运行工作流”的能力，则需要再接 Coze 的“恢复运行工作流”API（你这次没贴，我就不展开）

---

## 4.3 同步/异步执行选择（按你本版本）

- 默认：同步 `is_async=false`（你现在是MVP）
- 若检索工作流可能超时（>90秒风险）：建议改用**流式接口**或付费版用 `is_async=true`
    
    （你暂时没贴“流式执行工作流/异步结果查询”文档，我这里先只标出风险点）
    

---

## 5. 结合你“旅游路线顾问”业务的 Coze 落地清单

## 5.1 你至少需要的 Coze 资源（建议命名）

### 知识库（Dataset）

- 路线知识库（文本，format_type=0）
- 签证知识库（文本，format_type=0）

### 工作流（Workflow）

- `WF_ROUTE_SEARCH`：输入 `query` → 内部检索路线库 → 输出 candidates（含 route_id）
- `WF_VISA_SEARCH`：输入 `query` → 内部检索签证库 → 输出 answer + sources

> 后端只需要知道：workflow_id（以及必要时的 bot_id/app_id/connector_id）
> 

## 5.2 后台需要提供的 Coze 操作（对应接口）

- Dataset：创建/列表/修改/删除（datasets）
- Document：上传/列表/进度/修改/删除（document）
- Workflow：不管理工作流（本版本可仅在 Coze 平台配置；后台只保存 workflow_id/bot_id 等配置项）

---

## 6. 后端“CozeClient”封装建议（你用 VSCode 直接开工的落地要点）

你们后端建议封装一个 `CozeClient`，统一处理：

- base_url（api.coze.cn）
- bearer token
- 超时/重试（`code != 0`不重试 or 仅对网络错误重试）
- 结构化日志：记录 endpoint、request_id(trace_id)、响应 code/msg/logid、debug_url（workflow时）

### 6.1 必须记录到你们日志的字段

- `coze_logid`（detail.logid）
- `workflow_debug_url`（工作流 run 返回）
- `workflow_usage.token_count`（成本分析用）
- `dataset_id/document_id/workflow_id`（定位资源用）

---

## 7. 你后续切向量库时，Coze 的替换点（提前为演进留接口）

- 把“检索能力”抽象成接口：`SearchProvider.search_routes(query) -> candidates`
- 当前实现：Coze Workflow
- 未来实现：向量数据库（Milvus/Qdrant/pgvector等）
- 这样 LangGraph 的上层“推荐/对比/追问”节点都不改，只替换 Provider

---

下面是一份**超精简对接说明**（给 AI/工程同事看，照做就能接入），专门针对 **Coze OAuth JWT（渠道场景）鉴权**。

---

# Coze OAuth JWT 鉴权对接（精简版）

### 1) 你需要的配置（来自 Coze 控制台）

- `OAUTH_APP_ID`：OAuth 应用 ID（JWT payload.iss）
- `KID`：公钥指纹（JWT header.kid）
- `PRIVATE_KEY_PEM`：私钥（用于 RS256 签名）
- （可选）`SCOPE`：限制权限/可访问 bot 的范围

---

### 2) 生成 JWT（RS256）

**Header：**

```json
{"alg":"RS256","typ":"JWT","kid":"<KID>"}
```

**Payload：**

- `iss`: `<OAUTH_APP_ID>`
- `aud`: `"api.coze.cn"`
- `iat`: 当前秒级时间戳
- `exp`: 当前+600 秒（建议 10 分钟）
- `jti`: 随机唯一字符串（每次必须不同，防重放）
- （可选）`session_name`: 业务用户 UID（用于会话隔离，避免不同用户历史混在一起）

用 `PRIVATE_KEY_PEM` 按 RS256 生成 `JWT`。

> **JWT 只能用一次**，每次换 token 都要重新生成一个新的 JWT（新的 jti/iat/exp）。
> 

---

### 3) 用 JWT 换 OAuth Access Token

**POST** `https://api.coze.cn/api/permission/oauth2/token`

Headers:

- `Content-Type: application/json`
- `Authorization: Bearer <JWT>`

Body:

```json
{
  "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
  "duration_seconds": 900
}
```

返回：

- `access_token`
- `expires_in`（过期时间戳）

> **access_token 默认 15 分钟，不支持刷新**。过期就重复步骤2+3。
> 

---

### 4) 调用 Coze OpenAPI（统一用 Access Token）

调用任何 Coze API（例如你们要用的 `/v1/workflow/run`、`/v1/datasets`、`/open_api/knowledge/document/*`）都在请求头带：

`Authorization: Bearer <access_token>`

---

### 5) 工程建议（必须做）

- 做一个 `get_access_token()`：缓存 token（内存/Redis），离过期提前 60 秒更新
- token 换取失败时记录返回的错误信息（尤其是 `logid`/msg，便于排障）

---

如果你要我把这段再改成“给 AI 的系统提示词版本”（更像指令清单，包含变量名、步骤、异常重试规则），我也可以直接给你一段可复制的 prompt。