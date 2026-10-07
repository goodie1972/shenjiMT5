"""阶段1：流式 LLM 调用 + 网关适配表。

- 激活 Provider 读 data/llm_providers.json（复用神机密钥管理与 SSRF 判定），自持 openai SDK 流式调用；
- 返回 AIReply(content, reasoning_content, usage, raw)，思考/正文分通道回调；
- 网关适配表（从 PA 移植的踩坑知识）：thinking 参数按网关（sensenova=enabled/disabled/auto、
  deepseek v4=adaptive+output_config.effort、anthropic=budget_tokens）；max_tokens 上限按网关
  （deepseek 393216 / sensenova 65k / packy-claude 128k / b.ai 8192 / 默认 384k）；
- KV 前缀链开关（阶段3）：deepseek 原生开，agent 型路由关。
"""
