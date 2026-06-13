# my-claude-code

基于 LangChain 构建的本地编码 Agent，支持文件操作、Shell 命令执行和任务管理。

## 项目结构

```
my-claude-code/
├── s01_agent_loop.py   # 核心 Agent 循环（主程序）
├── hello.py            # 示例脚本
├── requirements.txt    # Python 依赖
├── 古诗.txt            # 示例文本文件
├── 静夜思.txt          # 示例文本文件
└── .env                # 环境变量（未上传，需手动创建）
```

## 功能特性

- **文件操作**：读取、写入、编辑、查找、删除文件
- **Shell 执行**：在本地 PowerShell/Bash 中执行命令
- **任务管理**：使用 `todo_write` / `todo_read` 规划多步骤任务
- **Human-in-the-Loop**：对写入、编辑、删除、Shell 等敏感操作进行人工确认
- **流式输出**：Agent 响应实时输出到终端
- **对话历史**：支持多轮对话上下文

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/Twistzz02412/my-claude-code.git
cd my-claude-code
```

### 2. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

### 3. 配置环境变量

在项目根目录创建 `.env` 文件：

```env
DASHSCOPE_API_KEY=your-dashscope-api-key
MODEL_ID=qwen3.6-plus
```

> 本项目通过 Anthropic 兼容接口连接阿里云 DashScope，因此需要使用 DashScope API Key。

### 4. 运行 Agent

```bash
python s01_agent_loop.py
```

输入问题后回车发送，Agent 会调用工具并流式输出结果。输入 `q` 或 `exit` 退出。

## 内置工具

| 工具名 | 说明 | 风险级别 |
|--------|------|----------|
| `read_file` | 读取文件内容 | 低 |
| `write_file` | 写入/覆盖文件 | 高（需确认） |
| `edit_file` | 替换文件中的文本 | 高（需确认） |
| `delete_file` | 删除文件 | 高（需确认） |
| `find_files` | 按 glob 模式查找文件 | 低 |
| `shell` | 执行系统命令 | 高（需确认） |
| `todo_write` | 创建/更新任务列表 | 低 |
| `todo_read` | 读取当前任务列表 | 低 |

## 依赖版本

- Python >= 3.10
- langchain >= 1.3.4
- langchain-anthropic >= 0.3.0
- langgraph >= 0.3.0
- python-dotenv >= 1.0.0

## 注意事项

- Windows 环境下 Shell 命令使用 PowerShell 语法
- 写入非 ASCII 内容（如中文）时，Agent 会自动使用 Python 写入以避免编码问题
- `.env`、`.venv/`、`.idea/` 等文件已加入 `.gitignore`，不会提交到仓库
