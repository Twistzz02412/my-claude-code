#!/usr/bin/env python3
"""
s01_agent_loop.py - The Agent Loop (LangChain Refactored Version)

使用 LangChain 1.3.4 重构版本，展示如何使用 create_agent 构建 Agent。

核心改进：
- 使用 LangChain 的 ChatAnthropic 模型封装
- 使用 @tool 装饰器定义工具
- 使用 create_agent 实现 Agent 循环（LangChain 推荐的主要方式）
- 更好的类型安全和可维护性

Usage:
    pip install langchain langchain-anthropic langgraph python-dotenv
    DASHSCOPE_API_KEY=... python s01_agent_loop.py
"""

import os
import glob as glob_module
import warnings

import subprocess

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*v3 streaming protocol.*")

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_tool_call, HumanInTheLoopMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage, AIMessage
from langchain_core.utils.uuid import uuid7
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command



load_dotenv(override=True)

# ── 1. 初始化模型 (通过 Anthropic 兼容接口连接 DashScope) ────────────────────
# 使用 ChatAnthropic 并指定 base_url 来连接 DashScope
model = ChatAnthropic(
    model=os.getenv("MODEL_ID", "deepseek-v4-flash"),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/apps/anthropic",
    max_tokens=8000,
)

# ── 2. 定义工具 ─────────────────────────────────────────────────────────────
@tool
def read_file(file_path: str) -> str:
    """Read the content of a file.

    Args:
        file_path: The path to the file to read.

    Returns:
        The content of the file.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: File not found: {file_path}"
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="gbk") as f:
                return f.read()
        except Exception as e:
            return f"Error: Cannot decode file: {e}"
    except Exception as e:
        return f"Error: {e}"


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file (creates or overwrites).

    Args:
        file_path: The path to the file to write.
        content: The content to write to the file.

    Returns:
        A success message or error.
    """
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        return f"Error: {e}"


@tool
def find_files(pattern: str) -> str:
    """Find files matching a glob pattern.

    Args:
        pattern: Glob pattern to search for (e.g. "*.py", "**/*.txt").

    Returns:
        List of matching file paths, one per line.
    """
    try:
        matches = glob_module.glob(pattern, recursive=True)
        if not matches:
            return f"No files found matching: {pattern}"
        return "\n".join(matches)
    except Exception as e:
        return f"Error: {e}"


@tool
def delete_file(file_path: str) -> str:
    """Delete a file.

    Args:
        file_path: The path to the file to delete.

    Returns:
        A success message or error.
    """
    try:
        os.remove(file_path)
        return f"Successfully deleted: {file_path}"
    except FileNotFoundError:
        return f"Error: File not found: {file_path}"
    except PermissionError:
        return f"Error: Permission denied: {file_path}"
    except Exception as e:
        return f"Error: {e}"


@tool
def edit_file(file_path: str, old_text: str, new_text: str) -> str:
    """Replace text in a file. Replaces the first occurrence of old_text with new_text.

    Args:
        file_path: The path to the file to edit.
        old_text: The text to find and replace.
        new_text: The replacement text.

    Returns:
        A success message or error.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        if old_text not in content:
            return f"Error: '{old_text}' not found in {file_path}"
        new_content = content.replace(old_text, new_text, 1)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"Successfully replaced text in {file_path}"
    except FileNotFoundError:
        return f"Error: File not found: {file_path}"
    except Exception as e:
        return f"Error: {e}"


def _decode_bytes(data: bytes) -> str:
    """Decode bytes from subprocess output, trying UTF-8 first then GBK."""
    if not data:
        return ""
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


@tool
def shell(command: str) -> str:
    """Execute a shell command in a subprocess.

    Args:
        command: The shell command to execute.

    Returns:
        The stdout/stderr output of the command.
    """
    try:
        args = ["powershell", "-Command", command] if os.name == "nt" else command
        result = subprocess.run(args, shell=os.name != "nt", capture_output=True, timeout=60)
        output = _decode_bytes(result.stdout)
        if result.stderr:
            output += f"\nstderr: {_decode_bytes(result.stderr)}"
        if result.returncode != 0:
            output += f"\nExit code: {result.returncode}"
        return output or "Command executed with no output."
    except Exception as e:
        return f"Error: {e}"


# 全局任务列表
CURRENT_TODOS: list[dict] = []
_TODO_ICONS = {"pending": " ", "in_progress": "\033[36m▸\033[0m", "completed": "\033[32m✓\033[0m"}


def _format_todos(todos: list[dict]) -> str:
    """格式化任务列表为字符串。"""
    lines = ["\n\033[33m## Current Tasks\033[0m"]
    for t in todos:
        icon = _TODO_ICONS.get(t.get("status", "pending"), " ")
        lines.append(f"  [{icon}] {t.get('content', '')}")
    return "\n".join(lines)


@tool
def todo_write(todos: list) -> str:
    """Create and manage a task list for the current coding session.

    Args:
        todos: A list of task objects, each with 'content' and 'status' keys.
               Status must be one of: "pending", "in_progress", "completed".

    Returns:
        A success message showing the number of tasks updated.
    """
    global CURRENT_TODOS
    CURRENT_TODOS = todos
    output = _format_todos(CURRENT_TODOS)
    print(output)
    return f"Updated {len(CURRENT_TODOS)} tasks"


@tool
def todo_read() -> str:
    """Read the current task list.

    Returns:
        The current task list as a formatted string.
    """
    if not CURRENT_TODOS:
        return "No tasks yet."
    return _format_todos(CURRENT_TODOS)


# ─ 3. 中间件 ──────────────────────────────────────────────────────────────

@wrap_tool_call
def logging_middleware(request, handler):
    """日志中间件：在命令行实时显示模型调用的工具及结果摘要。"""
    tc = request.tool_call
    args_str = ", ".join(f"{k}={v!r}" for k, v in tc["args"].items())
    print(f"\033[90m[调用] {tc['name']}({args_str})\033[0m")

    result = handler(request)
    status = "失败" if isinstance(result, str) and result.startswith("Error:") else "成功"
    content = result.content if isinstance(result, ToolMessage) else result
    summary = str(content).replace("\n", " ")[:100]
    print(f"\033[90m[结果] {status}: {summary}\033[0m")

    return result


def _always_interrupt(_request: ToolCallRequest) -> bool:
    """总是中断，用于中高风险工具。"""
    return True


# ─ 4. 创建 Agent ──────────────────────────────────────────────────────────
# 使用 create_agent 创建 Agent（LangChain 推荐的主要方式）
system_prompt = f"""You are a coding agent at {os.getcwd()}. Use tools to solve tasks. Act, don't explain.

Before starting any multi-step task, use todo_write to plan your steps. Update status as you go.

ENVIRONMENT:
- OS: {"Windows" if os.name == "nt" else "Unix/Linux/Mac"}
- Shell: PowerShell on Windows, /bin/bash on Unix
- When using shell tool, use the NATIVE shell commands for the current OS:
  - Windows (PowerShell): Copy-Item, Move-Item, Remove-Item, Get-ChildItem, Get-Content, etc.
  - Unix (Bash): cp, mv, rm, ls, cat, etc.

CRITICAL RULES:
1. You MUST report tool results accurately. If a tool returns an error, refusal, or cancellation, you MUST tell the user the operation was NOT executed. NEVER claim an operation succeeded when it failed or was rejected.
2. If the user rejects a tool execution, politely inform them the operation was cancelled. Do NOT make up fake results.
3. When writing files with non-ASCII content (Chinese, Japanese, etc.), NEVER use shell echo/redirect (e.g. `echo "中文" > file.txt`).
   Instead, use Python to write files with explicit UTF-8 encoding:
   python -c "with open('file.txt', 'w', encoding='utf-8') as f: f.write('content here')"
   This avoids Windows GBK encoding issues."""

checkpointer = InMemorySaver()

agent = create_agent(
    model=model,
    tools=[read_file, write_file, find_files, delete_file, edit_file, shell, todo_write, todo_read],
    system_prompt=system_prompt,
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={
                "write_file": {
                    "allowed_decisions": ["approve", "edit", "reject"],
                    "when": _always_interrupt,
                },
                "edit_file": {
                    "allowed_decisions": ["approve", "edit", "reject"],
                    "when": _always_interrupt,
                },
                "delete_file": {
                    "allowed_decisions": ["approve", "reject"],
                    "when": _always_interrupt,
                },
                "shell": {
                    "allowed_decisions": ["approve", "reject"],
                    "when": _always_interrupt,
                },
            },
        ),
        logging_middleware,
    ],
    checkpointer=checkpointer,
)


def _extract_text(msg) -> str:
    """从消息对象中提取文本内容。"""
    if not hasattr(msg, "content") or not msg.content:
        return ""
    if isinstance(msg.content, list):
        return "".join(
            block.get("text", "")
            for block in msg.content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return msg.content if isinstance(msg.content, str) else ""


def _get_pending_tool_calls(state) -> list:
    """从状态中提取被 HumanInTheLoopMiddleware 拦截、尚未执行的工具调用。"""
    msgs = state.values.get("messages", [])
    last_ai = next((m for m in reversed(msgs) if isinstance(m, AIMessage)), None)
    if not last_ai or not getattr(last_ai, "tool_calls", None):
        return []

    responded_ids = {m.tool_call_id for m in msgs if isinstance(m, ToolMessage)}
    return [tc for tc in last_ai.tool_calls if tc.get("id") not in responded_ids]


# ─ 5. Agent 执行函数 ──────────────────────────────────────────────────────
def run_agent(query: str, chat_history: list = None) -> str:
    """
    执行 Agent 并以流式方式输出响应，返回完整文本。
    支持 HumanInTheLoopMiddleware 中断恢复。

    Args:
        query: 用户输入的问题
        chat_history: 对话历史（可选）

    Returns:
        Agent 的最终文本响应
    """
    messages = list(chat_history) if chat_history else []
    messages.append({"role": "user", "content": query})

    if not hasattr(run_agent, "_thread_id"):
        run_agent._thread_id = str(uuid7())
    config = {"configurable": {"thread_id": run_agent._thread_id}}

    full_content = ""
    inputs = {"messages": messages}

    while True:
        # 流式输出
        for msg, metadata in agent.stream(inputs, config=config, stream_mode="messages"):
            text = _extract_text(msg)
            if text:
                print(text, end="", flush=True)
                full_content += text

        # 检查是否有被 HumanInTheLoopMiddleware 拦截的工具调用
        state = agent.get_state(config)
        pending = _get_pending_tool_calls(state)
        if not pending:
            break

        # 询问用户决策
        decisions = []
        for tc in pending:
            args_str = ", ".join(f"{k}={v!r}" for k, v in tc.get("args", {}).items())
            confirm = input(f"\n\033[33m[权限] 允许执行 {tc['name']}({args_str})？[y/n] \033[0m")
            if confirm.strip().lower() == "y":
                decisions.append({"type": "approve"})
            else:
                decisions.append({"type": "reject"})

        inputs = Command(resume={"decisions": decisions})

    print()
    return full_content


# ─ 6. 主程序入口 ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("s01: Agent Loop (LangChain Version)")
    print("输入问题，回车发送。输入 q 退出。\n")
    
    chat_history = []
    
    while True:
        try:
            query = input("\033[36ms01 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        
        if query.strip().lower() in ("q", "exit", ""):
            break
        
        try:
            # 执行 Agent（流式输出，run_agent 内部已打印）
            response = run_agent(query, chat_history)

            # 更新对话历史（使用字典格式）
            chat_history.append({"role": "user", "content": query})
            chat_history.append({"role": "assistant", "content": response})

            # 额外空行，让界面更清晰
            print()

        except Exception as e:
            print(f"\033[31mError: {e}\033[0m")
            continue
