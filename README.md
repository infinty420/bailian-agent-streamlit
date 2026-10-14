# 阿里云百炼智能体 · 本地 Streamlit 调用 实验手册

## 0. 一键启动

```bash
pip install -r requirements.txt
set DASHSCOPE_API_KEY=sk-你的APIKey          # Windows CMD（PowerShell 用 $env:）
set BAILIAN_APP_ID=你的应用ID
streamlit run bailian_agent_app.py
```

浏览器自动打开 http://localhost:8501 。若环境变量未配，也可在页面左侧侧边栏直接填 APP_ID 与 API Key。

---

## 1. 在阿里云百炼创建智能体（必须用 Agent 1.0 版本）

| 步骤 | 操作位置 | 说明 |
|---|---|---|
| 1 | 打开 `bailian.console.aliyun.com` | 首次进入需开通百炼服务（免费额度可用） |
| 2 | 右上角「密钥管理」→ 创建 API Key | 保存为环境变量 `DASHSCOPE_API_KEY` |
| 3 | 左侧「应用管理」→「创建应用」 | **类型务必选择「智能体应用（Agent 1.0）」**，不要选 Agent 2.0 / 工作流 / 高代码 |
| 4 | 模型选择 | `qwen-plus`（性价比）或 `qwen-max`（效果最佳） |
| 5 | 系统提示词 | 见 `智能体_提示词.md`，复制粘贴进去 |
| 6 | 知识库（可选，建议做） | 新建一个知识库，上传 `知识库样例.txt`（或自己的资料），回到应用页挂载 |
| 7 | 右侧「预览/调试」 | 测试 3~5 轮问答，观察是否命中知识库 |

---

## 2. 发布并以 API 方式调用

1. 应用配置页右上角 **发布 → 确认发布**（发布是后续调用的前提）
2. 进入 **发布渠道 → API 调用 → 查看 API**，记录：
   - `APP_ID`：应用卡片上的一串 ID
   - 请求地址：`POST https://dashscope.aliyuncs.com/api/v1/apps/{APP_ID}/completion`
3. 本项目的 `bailian_agent_app.py` 已实现：
   - **多轮对话**：按官方规则，使用 `input.messages` 传递历史（此时不传 `prompt` / `session_id`）
   - **流式输出**：`parameters` 同级传 `"stream": true`，解析 SSE `data:` 行，兼容「增量」与「累积」两种 text 返回习惯
   - **错误可读化**：失败时打印 `HTTP状态码 / request_id / code / message`
   - **知识库检索**：勾选后可填 `pipeline_ids` → `parameters.rag_options`

### 请求体示例

```json
{
  "input": {
    "messages": [
      {"role": "user", "content": "什么是 AI Agent？"},
      {"role": "assistant", "content": "AI Agent 是..."},
      {"role": "user", "content": "它和 LLM 有什么区别？"}
    ]
  },
  "parameters": {},
  "stream": true
}
```

返回结果文本位于 `output.text`。

---

## 2.5 上传图片 / 截图（让智能体"看得见"）

网页内置附件区：**「📎 上传图片 / 截图」**展开后选择本地图片（支持 JPG / PNG / WEBP / BMP / GIF，可多选），
发送时自动 Base64 编码，通过 `input.image_list` 传给百炼。超过限额的大图会**自动等比压缩**（长边压到 1568px）。

> **前置条件（很重要）**：智能体必须绑定**支持视觉理解的模型**，例如 `qwen-vl-max` 或多模态版 `qwen3.x-plus`；
> 纯文本模型（普通 `qwen-plus`）会忽略图片或直接报错。改完模型记得**重新发布**。

> 如果你的应用开启了"文件解析"能力，可在侧栏勾选「把图片也放进 file_list」，图片会同时作为文件被解析检索。

| 限制项 | 数值 |
|---|---|
| 单图（Base64 编码后） | ≤ 9 MB（超出自动压缩） |
| 建议分辨率 | 长边 ≤ 1568 px（压缩不会影响识别） |
| 图片数量 | 建议单轮 ≤ 5 张 |

### 请求体示例（带图）

```json
{
  "input": {
    "messages": [{"role": "user", "content": "这张截图里哪里报错了？"}],
    "image_list": ["data:image/png;base64,iVBORw0KGgoAAA..."]
  },
  "parameters": {"incremental_output": true},
  "stream": true
}
```

---

## 3. 设计思想总结（对照 ai-agent-book）

见 `实验报告_智能体设计思想.md`，核心围绕书中公式 **Agent = LLM + 上下文 + 工具**。

---

## 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| `HTTP 403 / InvalidApiKey` | API Key 填错或未在百炼开通；检查有无空格 |
| `HTTP 404 App not found` | APP_ID 错，或还没点「发布」 |
| 回答与知识库无关 | 提示词里明确「仅依据知识库回答」；做一次命中测试；提高相似度阈值 |
| 多轮没记忆 | 检查是否误传了 `prompt`（传了会忽略 messages） |
| 报错显示 gateway/地域 | 确认选用华北2（北京）地域控制台，国际版 endpoint 不同 |
