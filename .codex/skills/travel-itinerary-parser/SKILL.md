---
name: travel-itinerary-parser
description: 从PDF/Word旅游文档提取结构化字段，输出纯JSON格式；当用户需要解析旅游行程文档并获取完整结构化数据时使用
dependency:
  python:
    - PyPDF2>=3.0.0
    - python-docx>=0.8.11
---

# Travel Itinerary Parser

## 任务目标
- 本 Skill 用于：从PDF或Word格式的旅游行程文档中提取结构化信息
- 能力包含：文档解析、基础信息提取、每日行程拆分、费用条款解析、索引摘要生成
- 触发条件：用户提供旅游行程文档（PDF/Word）并要求提取特定字段信息

## 前置准备
- 依赖说明：scripts脚本所需的依赖包及版本
  ```
  PyPDF2>=3.0.0
  python-docx>=0.8.11
  ```

## 操作步骤

### 标准流程

#### 步骤1：文档解析
- 调用 `scripts/document_parser.py` 处理输入文档
- 脚本参数：`--file-path <文档路径>`
- 支持格式：PDF（.pdf）、Word（.docx）
- 输出：完整的文档文本内容（原始文本，包含可能的格式错乱）

```bash
python /workspace/projects/travel-itinerary-parser/scripts/document_parser.py --file-path ./旅游行程.pdf
```

#### 步骤2：提取基础信息和亮点
- 参考字段提取指导提取 `basic_info` 和 `highlights`
- 字段类型：字符串
- 提取规则：严格按照原文内容，禁止改写或推测

#### 步骤3：提取每日行程信息
- 参考字段提取指导解析每日行程
- 字段类型：JSON对象，包含 `itinerary_days` 数组
- 每日字段：day（天数）、day_title（标题）、meals（餐饮）、hotel（住宿）、pois（POI信息）
- 提取规则：按天拆分，不合并、不遗漏

#### 步骤4：提取费用条款和注意事项
- 参考字段提取指导解析费用信息
- 字段类型：JSON对象，包含 `cost_included`、`cost_excluded`、`notices` 数组
- 提取规则：保留原文表述，不添加主观解读

#### 步骤5：生成索引摘要
- 参考字段提取指导生成检索索引
- 字段类型：
  - index_text（字符串，60~120字结构化文本）
  - index_tags（JSON数组，10~25个标签）
  - certificate_limit（字符串）
  - age_limit（字符串）
- 提取规则：具备字符容错能力，通过语义理解恢复结构

#### 步骤6：生成最终输出
- 将以上五个步骤提取的所有字段整合到一个JSON对象中
- 最终输出格式：纯JSON，不包含任何Markdown标记或解释性文字
- 输出结构示例：

```json
{
  "basic_info": "行程标题为\"日本大阪-东京5天4晚\"，目的地为\"日本-大阪、东京\"，共5天4晚。",
  "highlights": "亮点包含\"全程入住五星级酒店\"、\"专业中文导游陪同\"、\"包含所有景点门票\"",
  "itinerary_days": [
    {
      "day": 1,
      "day_title": "前往大阪",
      "meals": {
        "breakfast": "未提及",
        "lunch": "飞机餐",
        "dinner": "未提及"
      },
      "hotel": {
        "hotel_name": "大阪希尔顿酒店",
        "hotel_level": "五星级"
      },
      "pois": [
        {
          "poi_name": "大阪城公园",
          "poi_type": "景点",
          "activity": "游览大阪城公园"
        }
      ]
    }
  ],
  "cost_included": [
    "往返机票",
    "全程酒店住宿",
    "景点门票"
  ],
  "cost_excluded": [
    "个人消费",
    "自费项目"
  ],
  "notices": [
    "请携带有效护照",
    "建议提前办理签证"
  ],
  "index_text": "日本大阪-东京5天4晚，适合家庭出游，含大阪城、浅草寺、东京塔打卡，行程含机票+住宿+门票，主题玩法：城市+文化体验",
  "index_tags": ["日本", "5天4晚", "家庭", "大阪", "东京", "大阪城", "浅草寺", "东京塔", "城市", "文化", "机票", "住宿", "门票", "出境游"],
  "certificate_limit": "需持有效护照办理入住，出境游需提前办理签证",
  "age_limit": "未提及年龄限制"
}
```

**强制规则**：
- 最终输出必须为纯JSON格式，不可使用Markdown代码块标记（```json ... ```）
- 所有字段必须按照步骤2-5的规范提取
- 缺失信息严格填写"未提及"或"未知"
- JSON必须可直接解析，无语法错误

## 资源索引
- 必要脚本：见 [scripts/document_parser.py](scripts/document_parser.py)（用途：解析PDF/Word文档提取文本内容）
- 领域参考：见 [references/field-extraction-guide.md](references/field-extraction-guide.md)（何时读取：提取各模块字段时）

## 注意事项
- 文档解析脚本可能返回包含乱码、格式错位的文本，智能体需具备容错能力
- 所有字段提取必须基于文档原文，禁止编造未提及的信息
- 当信息缺失时，严格按照指定格式填写"未提及"或"未知"
- 最终输出必须为纯JSON格式，不包含任何Markdown标记、解释性文字或额外说明
- JSON必须可直接解析，确保所有引号、逗号、括号等符号正确配对

## 使用示例

### 示例1：PDF文档完整解析
- 功能说明：从PDF文档中提取所有结构化字段并输出纯JSON
- 执行方式：脚本解析 + 智能体提取
- 关键步骤：
  1. 调用document_parser.py解析PDF
  2. 依次提取基础信息、每日行程、费用条款、索引摘要
  3. 将所有字段整合为纯JSON格式输出
- 输出示例：

```json
{
  "basic_info": "行程标题为\"日本大阪-东京5天4晚\"，目的地为\"日本-大阪、东京\"，共5天4晚。",
  "highlights": "亮点包含\"全程入住五星级酒店\"、\"专业中文导游陪同\"、\"包含所有景点门票\"",
  "itinerary_days": [
    {
      "day": 1,
      "day_title": "前往大阪",
      "meals": {
        "breakfast": "未提及",
        "lunch": "飞机餐",
        "dinner": "未提及"
      },
      "hotel": {
        "hotel_name": "大阪希尔顿酒店",
        "hotel_level": "五星级"
      },
      "pois": [
        {
          "poi_name": "大阪城公园",
          "poi_type": "景点",
          "activity": "游览大阪城公园"
        }
      ]
    }
  ],
  "cost_included": ["往返机票", "全程酒店住宿", "景点门票"],
  "cost_excluded": ["个人消费", "自费项目"],
  "notices": ["请携带有效护照", "建议提前办理签证"],
  "index_text": "日本大阪-东京5天4晚，适合家庭出游，含大阪城、浅草寺、东京塔打卡，行程含机票+住宿+门票，主题玩法：城市+文化体验",
  "index_tags": ["日本", "5天4晚", "家庭", "大阪", "东京", "大阪城", "浅草寺", "东京塔", "城市", "文化", "机票", "住宿", "门票", "出境游"],
  "certificate_limit": "需持有效护照办理入住，出境游需提前办理签证",
  "age_limit": "未提及年龄限制"
}
```

### 示例2：Word文档基础信息提取
- 功能说明：仅提取文档的基础信息和亮点并输出纯JSON
- 执行方式：脚本解析 + 智能体提取
- 关键步骤：
  1. 调用document_parser.py解析Word
  2. 仅执行步骤2（基础信息和亮点提取）
  3. 输出包含basic_info和highlights的纯JSON
- 输出示例：

```json
{
  "basic_info": "行程标题为\"日本大阪-东京5天4晚\"，目的地为\"日本-大阪、东京\"，共5天4晚。",
  "highlights": "亮点包含\"全程入住五星级酒店\"、\"专业中文导游陪同\"、\"包含所有景点门票\"",
  "itinerary_days": [],
  "cost_included": [],
  "cost_excluded": [],
  "notices": [],
  "index_text": "",
  "index_tags": [],
  "certificate_limit": "未提及证件限制",
  "age_limit": "未提及年龄限制"
}
```
