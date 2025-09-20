# Standardized LLM Tool Calling Runtime (UBP)

**File:** `standardized_llm_tool_calling_runtime.py`
**Project:** Unified Bot Protocol (UBP)
**Version:** 1.0.0
**Last Updated:** 2025-09-17
**Author:** Michael Landbo (Founder of UBP)

---

## 📌 Overview
The **Standardized LLM Tool Calling Runtime** provides **model-agnostic orchestration** of AI agents with **unified tool calling capabilities**. This runtime enables seamless integration between **any LLM provider** (OpenAI, Anthropic, Google, Azure, local models) and the **Unified Bot Protocol (UBP) Orchestrator**.

This runtime standardizes **function calling, tool execution, and response handling** across different LLM providers, ensuring consistent behavior regardless of the underlying model architecture.

---

## ✨ Features
- ✅ **Multi-provider LLM support** (OpenAI, Anthropic, Google, Azure, Ollama)
- ✅ **Standardized tool calling interface** across all providers
- ✅ **Dynamic tool registration** and discovery
- ✅ **Parallel tool execution** with async/await support
- ✅ **Tool result caching** for performance optimization
- ✅ **Error handling & retry logic** for failed tool calls
- ✅ **Token usage tracking** and cost optimization
- ✅ **Security**: Tool sandboxing, permission validation
- ✅ **Observability**: Execution tracing, performance metrics
- ✅ **Model switching** with automatic fallback support

---

## ⚙️ Installation

### 1. Install Python dependencies
```bash
pip install openai anthropic google-generativeai azure-openai ollama asyncio pydantic
```

### 2. Clone UBP Repository
```bash
git clone https://github.com/L4DK/Unified-Bot-Protocol.git
cd Unified-Bot-Protocol/runtime/llm-tool-calling/
```

---

## 🚀 Usage

### 1. Configure the Runtime
Edit `config` in `standardized_llm_tool_calling_runtime.py`:

```python
config = {
    'llm_providers': {
        'openai': {
            'api_key': 'sk-your-openai-api-key',
            'model': 'gpt-4-turbo-preview',
            'max_tokens': 4096,
            'temperature': 0.7,
            'enabled': True
        },
        'anthropic': {
            'api_key': 'sk-ant-your-anthropic-key',
            'model': 'claude-3-opus-20240229',
            'max_tokens': 4096,
            'temperature': 0.7,
            'enabled': True
        },
        'google': {
            'api_key': 'your-google-ai-api-key',
            'model': 'gemini-pro',
            'enabled': False
        },
        'azure': {
            'api_key': 'your-azure-openai-key',
            'endpoint': 'https://your-resource.openai.azure.com/',
            'model': 'gpt-4',
            'enabled': False
        }
    },
    'runtime': {
        'default_provider': 'openai',
        'fallback_providers': ['anthropic', 'google'],
        'max_parallel_tools': 5,
        'tool_timeout': 30,
        'cache_enabled': True,
        'cache_ttl': 300
    },
    'ubp': {
        'orchestrator_url': 'ws://localhost:8080/ws/runtime',
        'runtime_id': 'llm_runtime_001',
        'security_key': 'your_security_key_here'
    }
}
```

### 2. Run the Runtime
```bash
python standardized_llm_tool_calling_runtime.py
```

The runtime will connect to the **UBP Orchestrator** and register available tools.

---

## 📚 Example Tool Calling Workflows

### Weather Tool Example
```python
# Tool definition
@runtime.register_tool
async def get_weather(location: str, units: str = "celsius") -> dict:
    """Get current weather for a location"""
    # Tool implementation
    return {"temperature": 22, "condition": "sunny", "location": location}

# Usage in conversation
user_message = "What's the weather like in Paris?"
# Runtime automatically:
# 1. Detects need for weather tool
# 2. Calls get_weather("Paris", "celsius")
# 3. Integrates result into LLM response
# 4. Returns: "The weather in Paris is currently 22°C and sunny."
```

### Multi-Tool Orchestration
```python
user_message = "Book a flight to Tokyo and check the weather there"
# Runtime executes in parallel:
# 1. book_flight("Tokyo")
# 2. get_weather("Tokyo")
# Then combines results into coherent response
```

### Cross-Provider Fallback
```python
# If OpenAI fails, automatically falls back to Anthropic
# Maintains same tool calling interface across providers
# User experience remains consistent
```

---

## 🛠️ Built-in Tool Categories

| Category | Tools | Description |
|----------|-------|-------------|
| **Web** | `Web Search`, `fetch_url`, `scrape_page` | Internet data retrieval |
| **Files** | `read_file`, `write_file`, `list_directory` | File system operations |
| **APIs** | `http_request`, `graphql_query` | External API integration |
| **Data** | `query_database`, `execute_sql` | Database operations |
| **Math** | `calculate`, `plot_graph`, `analyze_data` | Mathematical computations |
| **Time** | `get_time`, `schedule_task`, `set_reminder` | Time-based operations |

---

## 🧪 Health & Observability

- **Runtime metrics**: Token usage, tool execution times, error rates
- **Provider health**: Model availability, response latency, cost tracking
- `StructuredLogger` → JSON logs for tool executions and LLM interactions
- `MetricsCollector` → Performance metrics for each tool and provider
- `TracingManager` → End-to-end conversation and tool execution tracing

---

## 🔒 Security

- **Tool sandboxing** → Isolated execution environment for each tool
- **Permission validation** → Tools require explicit authorization
- **Input sanitization** → All tool inputs validated and sanitized
- **Rate limiting** → Prevents abuse of expensive LLM calls
- **API key rotation** → Supports dynamic credential updates
- **Audit logging** → Complete trail of all tool executions

---

## 🛠️ Development Guide

### Register custom tools
```python
@runtime.register_tool
async def my_custom_tool(param1: str, param2: int = 10) -> dict:
    """Description of what this tool does"""
    # Your tool implementation
    return {"result": "success"}
```

### Test tool execution
```python
# Test individual tool
result = await runtime.execute_tool("get_weather", {"location": "London"})

# Test full conversation with tools
response = await runtime.process_message(
    "What's the weather in London and what time is it there?",
    provider="openai"
)
```

### Useful links
- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)
- [Anthropic Tool Use Documentation](https://docs.anthropic.com/claude/docs/tool-use)
- [Unified Bot Protocol - Official Docs](https://www.unified-bot-protocol.com)
- [UBP GitHub Repo](https://github.com/L4DK/Unified-Bot-Protocol)

---

## 📜 Changelog

### v1.0.0 (2025-09-17)
- Initial implementation of LLM Tool Calling Runtime
- Added support for **OpenAI, Anthropic, Google, Azure** providers
- Implemented **standardized tool calling interface**
- Added **parallel tool execution** with async support
- Enabled **automatic provider fallback** mechanism
- Integrated **comprehensive observability** and metrics
- Added **tool sandboxing** and security features
- Implemented **result caching** for performance optimization

---

## 👥 Contributing

This project follows the **UBP Open Source Model (Apache 2.0 License)**.
All **protocol code** must remain **free and open**.
Commercial extensions are allowed, but must not compromise interoperability.

Fork → PR → Code Review → Merge (Founder-led BDFL governance).

---

## 📝 License

Apache 2.0 License. See [LICENSE](../../LICENSE) for details.
