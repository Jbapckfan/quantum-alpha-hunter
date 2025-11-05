#!/usr/bin/env node

/**
 * Codex MCP Server
 * Provides access to Codex CLI for code review and analysis
 * Uses ChatGPT as the backend for intelligent code review
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  Tool,
} from '@modelcontextprotocol/sdk/types.js';
import { execa } from 'execa';
import * as fs from 'fs/promises';
import * as path from 'path';

// Tool definitions
const TOOLS: Tool[] = [
  {
    name: 'codex_review_file',
    description: 'Review a single file using Codex CLI. Returns detailed analysis of code quality, potential bugs, and improvement suggestions.',
    inputSchema: {
      type: 'object',
      properties: {
        file_path: {
          type: 'string',
          description: 'Absolute path to the file to review',
        },
        focus: {
          type: 'string',
          description: 'What to focus on (e.g., "security", "performance", "bugs", "architecture")',
          default: 'general code quality',
        },
      },
      required: ['file_path'],
    },
  },
  {
    name: 'codex_review_directory',
    description: 'Review all Python files in a directory using Codex CLI. Provides architectural overview and cross-file analysis.',
    inputSchema: {
      type: 'object',
      properties: {
        directory_path: {
          type: 'string',
          description: 'Absolute path to the directory to review',
        },
        pattern: {
          type: 'string',
          description: 'File pattern to match (default: "*.py")',
          default: '*.py',
        },
        focus: {
          type: 'string',
          description: 'What to focus on in the review',
          default: 'architecture and design patterns',
        },
      },
      required: ['directory_path'],
    },
  },
  {
    name: 'codex_explain_code',
    description: 'Get detailed explanation of a code snippet using Codex CLI.',
    inputSchema: {
      type: 'object',
      properties: {
        code: {
          type: 'string',
          description: 'Code snippet to explain',
        },
        language: {
          type: 'string',
          description: 'Programming language (default: python)',
          default: 'python',
        },
      },
      required: ['code'],
    },
  },
  {
    name: 'codex_find_bugs',
    description: 'Analyze code for potential bugs and vulnerabilities using Codex CLI.',
    inputSchema: {
      type: 'object',
      properties: {
        file_path: {
          type: 'string',
          description: 'Absolute path to file to analyze',
        },
        severity: {
          type: 'string',
          description: 'Minimum severity level (low, medium, high, critical)',
          default: 'medium',
        },
      },
      required: ['file_path'],
    },
  },
  {
    name: 'codex_suggest_improvements',
    description: 'Get improvement suggestions for code using Codex CLI.',
    inputSchema: {
      type: 'object',
      properties: {
        file_path: {
          type: 'string',
          description: 'Absolute path to file',
        },
        aspect: {
          type: 'string',
          description: 'What aspect to improve (performance, readability, maintainability, security)',
          default: 'all',
        },
      },
      required: ['file_path'],
    },
  },
  {
    name: 'codex_compare_approaches',
    description: 'Compare different implementation approaches using Codex CLI.',
    inputSchema: {
      type: 'object',
      properties: {
        approach_a: {
          type: 'string',
          description: 'First code approach',
        },
        approach_b: {
          type: 'string',
          description: 'Second code approach',
        },
        criteria: {
          type: 'string',
          description: 'Comparison criteria (performance, readability, maintainability)',
          default: 'performance and maintainability',
        },
      },
      required: ['approach_a', 'approach_b'],
    },
  },
];

class CodexMCPServer {
  private server: Server;
  private codexPath: string;

  constructor() {
    this.server = new Server(
      {
        name: 'codex-mcp-server',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    // Try to find codex CLI
    this.codexPath = process.env.CODEX_CLI_PATH || 'codex';

    this.setupHandlers();
  }

  private setupHandlers() {
    // List available tools
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: TOOLS,
    }));

    // Handle tool calls
    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      if (!args) {
        return {
          content: [{ type: 'text', text: 'No arguments provided' }],
          isError: true,
        };
      }

      try {
        switch (name) {
          case 'codex_review_file':
            return await this.reviewFile(args.file_path as string, args.focus as string);

          case 'codex_review_directory':
            return await this.reviewDirectory(
              args.directory_path as string,
              args.pattern as string,
              args.focus as string
            );

          case 'codex_explain_code':
            return await this.explainCode(args.code as string, args.language as string);

          case 'codex_find_bugs':
            return await this.findBugs(args.file_path as string, args.severity as string);

          case 'codex_suggest_improvements':
            return await this.suggestImprovements(args.file_path as string, args.aspect as string);

          case 'codex_compare_approaches':
            return await this.compareApproaches(
              args.approach_a as string,
              args.approach_b as string,
              args.criteria as string
            );

          default:
            return {
              content: [
                {
                  type: 'text',
                  text: `Unknown tool: ${name}`,
                },
              ],
            };
        }
      } catch (error: any) {
        return {
          content: [
            {
              type: 'text',
              text: `Error: ${error.message}`,
            },
          ],
          isError: true,
        };
      }
    });
  }

  private async callCodex(prompt: string, context?: string): Promise<string> {
    /**
     * Call Codex CLI with a prompt
     * Uses ChatGPT as backend via codex CLI
     */
    try {
      // Build command
      const fullPrompt = context ? `${context}\n\n${prompt}` : prompt;

      // Call codex CLI (assumes it's installed and configured)
      // Alternative: Use OpenAI API directly if codex CLI isn't available
      const { stdout } = await execa(this.codexPath, ['chat', fullPrompt], {
        timeout: 30000, // 30 second timeout
      });

      return stdout;
    } catch (error: any) {
      // Fallback: use direct OpenAI API if codex CLI fails
      if (error.message.includes('command not found') || error.message.includes('ENOENT')) {
        throw new Error(
          'Codex CLI not found. Please install it or set CODEX_CLI_PATH environment variable. ' +
          'Alternatively, configure OPENAI_API_KEY for direct API access.'
        );
      }
      throw error;
    }
  }

  private async reviewFile(filePath: string, focus: string = 'general code quality'): Promise<any> {
    // Read file content
    const content = await fs.readFile(filePath, 'utf-8');
    const fileName = path.basename(filePath);

    const prompt = `Please review this ${fileName} file focusing on ${focus}.
Provide:
1. Overall quality assessment
2. Potential bugs or issues
3. Security concerns
4. Performance considerations
5. Specific improvement suggestions with line numbers

Be detailed and actionable.

File content:
\`\`\`
${content}
\`\`\``;

    const review = await this.callCodex(prompt);

    return {
      content: [
        {
          type: 'text',
          text: `# Code Review: ${fileName}\n\n${review}`,
        },
      ],
    };
  }

  private async reviewDirectory(
    dirPath: string,
    pattern: string = '*.py',
    focus: string = 'architecture'
  ): Promise<any> {
    // Find all matching files
    const files = await this.findFiles(dirPath, pattern);

    if (files.length === 0) {
      return {
        content: [
          {
            type: 'text',
            text: `No files matching ${pattern} found in ${dirPath}`,
          },
        ],
      };
    }

    // Read all files
    const fileContents = await Promise.all(
      files.map(async (file) => {
        const content = await fs.readFile(file, 'utf-8');
        const relativePath = path.relative(dirPath, file);
        return `### ${relativePath}\n\`\`\`python\n${content}\n\`\`\`\n`;
      })
    );

    const prompt = `Please review this codebase focusing on ${focus}.
Analyze the following ${files.length} files:

${fileContents.join('\n')}

Provide:
1. Architectural overview
2. Design pattern analysis
3. Cross-file dependencies and coupling
4. Potential refactoring opportunities
5. Consistency issues
6. Priority improvements

Be comprehensive but concise.`;

    const review = await this.callCodex(prompt);

    return {
      content: [
        {
          type: 'text',
          text: `# Directory Review: ${path.basename(dirPath)}\n\n${review}`,
        },
      ],
    };
  }

  private async explainCode(code: string, language: string = 'python'): Promise<any> {
    const prompt = `Explain this ${language} code in detail. Cover:
1. What it does (high-level purpose)
2. How it works (step-by-step logic)
3. Key algorithms or patterns used
4. Edge cases handled
5. Potential issues or improvements

Code:
\`\`\`${language}
${code}
\`\`\``;

    const explanation = await this.callCodex(prompt);

    return {
      content: [
        {
          type: 'text',
          text: `# Code Explanation\n\n${explanation}`,
        },
      ],
    };
  }

  private async findBugs(filePath: string, severity: string = 'medium'): Promise<any> {
    const content = await fs.readFile(filePath, 'utf-8');
    const fileName = path.basename(filePath);

    const prompt = `Analyze this code for bugs and vulnerabilities. Focus on ${severity} severity and above.
Report:
1. Security vulnerabilities (SQL injection, XSS, etc.)
2. Logic bugs (off-by-one, race conditions, etc.)
3. Error handling issues
4. Memory leaks or resource management issues
5. Type errors or null pointer issues

For each issue, provide:
- Severity level
- Line number(s)
- Description
- How to fix

File: ${fileName}
\`\`\`
${content}
\`\`\``;

    const analysis = await this.callCodex(prompt);

    return {
      content: [
        {
          type: 'text',
          text: `# Bug Analysis: ${fileName}\n\n${analysis}`,
        },
      ],
    };
  }

  private async suggestImprovements(filePath: string, aspect: string = 'all'): Promise<any> {
    const content = await fs.readFile(filePath, 'utf-8');
    const fileName = path.basename(filePath);

    const prompt = `Suggest improvements for this code, focusing on ${aspect}.
Provide:
1. Specific refactoring suggestions with before/after examples
2. Performance optimizations
3. Readability improvements
4. Best practices to adopt
5. Modern Python/language features to use

Be specific with code examples.

File: ${fileName}
\`\`\`
${content}
\`\`\``;

    const suggestions = await this.callCodex(prompt);

    return {
      content: [
        {
          type: 'text',
          text: `# Improvement Suggestions: ${fileName}\n\n${suggestions}`,
        },
      ],
    };
  }

  private async compareApproaches(
    approachA: string,
    approachB: string,
    criteria: string
  ): Promise<any> {
    const prompt = `Compare these two implementation approaches based on ${criteria}.

Approach A:
\`\`\`
${approachA}
\`\`\`

Approach B:
\`\`\`
${approachB}
\`\`\`

Provide:
1. Side-by-side comparison table
2. Pros and cons of each
3. Performance analysis
4. Maintainability assessment
5. Recommendation with justification`;

    const comparison = await this.callCodex(prompt);

    return {
      content: [
        {
          type: 'text',
          text: `# Approach Comparison\n\n${comparison}`,
        },
      ],
    };
  }

  private async findFiles(dir: string, pattern: string): Promise<string[]> {
    const files: string[] = [];
    const entries = await fs.readdir(dir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);

      if (entry.isDirectory() && !entry.name.startsWith('.')) {
        files.push(...(await this.findFiles(fullPath, pattern)));
      } else if (entry.isFile() && this.matchPattern(entry.name, pattern)) {
        files.push(fullPath);
      }
    }

    return files;
  }

  private matchPattern(filename: string, pattern: string): boolean {
    const regex = new RegExp('^' + pattern.replace(/\*/g, '.*') + '$');
    return regex.test(filename);
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('Codex MCP Server running on stdio');
  }
}

// Start server
const server = new CodexMCPServer();
server.run().catch(console.error);
