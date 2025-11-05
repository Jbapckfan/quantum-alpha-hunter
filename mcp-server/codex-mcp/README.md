# Codex MCP Server

MCP server that integrates with Codex CLI (ChatGPT) to provide intelligent code review and analysis as a second set of eyes.

## Features

- **File Review**: Comprehensive code review of individual files
- **Directory Review**: Architectural analysis of entire directories
- **Code Explanation**: Detailed explanations of code snippets
- **Bug Detection**: Find potential bugs and vulnerabilities
- **Improvement Suggestions**: Get actionable refactoring advice
- **Approach Comparison**: Compare different implementation strategies

## Installation

```bash
cd mcp-server/codex-mcp
npm install
npm run build
```

## Configuration

### Option 1: Using Codex CLI

If you have the `codex` CLI installed (ChatGPT desktop app or standalone):

```bash
# No additional setup needed if codex is in PATH
# Or set custom path:
export CODEX_CLI_PATH=/path/to/codex
```

### Option 2: Direct OpenAI API

Set your OpenAI API key:

```bash
export OPENAI_API_KEY=your_key_here
```

## Adding to Claude Code

Add to your MCP settings (`~/Library/Application Support/Claude/claude_desktop_config.json` on Mac):

```json
{
  "mcpServers": {
    "codex-review": {
      "command": "node",
      "args": [
        "/Users/jamesalford/quantum-alpha-hunter/mcp-server/codex-mcp/dist/index.js"
      ],
      "env": {
        "CODEX_CLI_PATH": "/path/to/codex",
        "OPENAI_API_KEY": "your_key_if_not_using_cli"
      }
    }
  }
}
```

## Usage in Claude Code

Once configured, you'll have access to these tools:

### Review a File

```
Use codex_review_file to review qaht/scoring/ridge_model.py focusing on machine learning best practices
```

### Review Directory

```
Use codex_review_directory to review qaht/equities_options/features focusing on feature engineering patterns
```

### Explain Code

```
Use codex_explain_code to explain this Ridge regression pipeline code
```

### Find Bugs

```
Use codex_find_bugs to check qaht/db.py for potential issues, severity: high
```

### Get Improvements

```
Use codex_suggest_improvements on qaht/utils/retry.py focusing on performance
```

### Compare Approaches

```
Use codex_compare_approaches to compare two different implementations of the social delta calculation
```

## Example Workflow

```python
# In Claude Code conversation:

"Let's get a second opinion on our Ridge regression model.
Use codex_review_file on qaht/scoring/ridge_model.py focusing on:
- Model validation approach
- Feature engineering pipeline
- Calibration method
- Potential overfitting risks"

# Codex will analyze and provide detailed feedback

"Now check the entire scoring module architecture:
Use codex_review_directory on qaht/scoring focusing on overall design"

# Get architectural insights

"Compare our current Ridge approach with a potential LightGBM approach:
Use codex_compare_approaches with criteria: interpretability vs performance"
```

## Benefits

1. **Fresh Perspective**: ChatGPT provides unbiased review without context from previous conversations
2. **Specialized Analysis**: Can focus on specific aspects (security, performance, ML best practices)
3. **Cross-Reference**: Catch issues that one AI might miss
4. **Architectural Insights**: Good for higher-level design review
5. **Educational**: Learn alternative approaches and best practices

## Limitations

- Requires internet connection (calls ChatGPT)
- Rate limited by OpenAI API
- May not have full context of your codebase history
- Best used as complement to Claude, not replacement

## Development

```bash
# Watch mode for development
npm run dev

# Build
npm run build

# Test
node dist/index.js
```

## Troubleshooting

**Codex CLI not found:**
- Install ChatGPT desktop app or standalone codex CLI
- Set `CODEX_CLI_PATH` environment variable
- Or use direct API with `OPENAI_API_KEY`

**Timeout errors:**
- Increase timeout in code (default 30s)
- Split large files into smaller reviews

**Rate limiting:**
- Add delays between requests
- Use batch reviews instead of per-file

## Architecture

```
Claude Code
    ↓
MCP Protocol
    ↓
Codex MCP Server (TypeScript)
    ↓
Codex CLI / OpenAI API
    ↓
ChatGPT (GPT-4)
    ↓
Code Analysis Results
```

This gives you two AI systems working together:
- **Claude**: Writes and refactors code with full context
- **ChatGPT via Codex**: Reviews with fresh eyes, catches different issues

## Use Cases

1. **Pre-commit Review**: "Review all changed files before I commit"
2. **Refactoring Validation**: "Check if this refactor maintains correctness"
3. **Security Audit**: "Scan for security vulnerabilities in data adapters"
4. **Performance Review**: "Analyze feature computation for bottlenecks"
5. **Architecture Validation**: "Review pipeline orchestration design"

Perfect for getting that second set of eyes on critical code! 🔍
