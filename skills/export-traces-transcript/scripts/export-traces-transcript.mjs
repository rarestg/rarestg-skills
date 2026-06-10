#!/usr/bin/env node

import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { Buffer } from 'node:buffer'
import { tmpdir } from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rendererPath = path.join(scriptDir, 'render-traces-json.mjs')
const defaultLimit = 100000
const defaultMaxEventChars = 200000
const defaultOutDir = '.tmp/traces'
const sourceEventTypes = 'user_message,agent_text,tool_call'
const fullEventTypes = 'user_message,agent_text,tool_call,tool_result'

function printUsage() {
  console.error(`Usage:
  node skills/export-traces-transcript/scripts/export-traces-transcript.mjs <trace-id> [options]

Options:
  --must-contain <text>      Require text to appear in the rendered transcript. Repeatable.
  --out-dir <path>           Output directory. Default: ${defaultOutDir}
  --include-tool-results     Also create .full.md with raw tool outputs.
  --include-timestamps       Include timestamp attributes on turn fences.
  --keep-json                Also keep .source.json/.pretty.json audit files.
  --no-reset                 Skip Traces cache reset. Use only for debugging.
  --limit <number>           Traces event limit. Default: ${defaultLimit}
  --max-event-chars <number> Per-event character cap. Default: ${defaultMaxEventChars}
  -h, --help                 Show this help.`)
}

function parsePositiveInteger(value, flagName) {
  if (!/^[1-9]\d*$/.test(value ?? '')) {
    throw new Error(`${flagName} must be a positive integer`)
  }

  const parsed = Number.parseInt(value, 10)

  if (!Number.isSafeInteger(parsed)) {
    throw new Error(`${flagName} is too large`)
  }

  return parsed
}

function parseArgs(argv) {
  const options = {
    traceId: null,
    outDir: defaultOutDir,
    mustContain: [],
    includeToolResults: false,
    includeTimestamps: false,
    keepJson: false,
    reset: true,
    limit: defaultLimit,
    maxEventChars: defaultMaxEventChars,
    help: false,
  }

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]

    if (arg === '--help' || arg === '-h') {
      options.help = true
      return options
    }

    if (arg === '--out-dir') {
      options.outDir = argv[index + 1]

      if (!options.outDir) {
        throw new Error('--out-dir requires a path')
      }

      index += 1
      continue
    }

    if (arg === '--must-contain') {
      const value = argv[index + 1]

      if (!value) {
        throw new Error('--must-contain requires text')
      }

      options.mustContain.push(value)
      index += 1
      continue
    }

    if (arg === '--include-tool-results') {
      options.includeToolResults = true
      continue
    }

    if (arg === '--include-timestamps') {
      options.includeTimestamps = true
      continue
    }

    if (arg === '--keep-json') {
      options.keepJson = true
      continue
    }

    if (arg === '--no-reset') {
      options.reset = false
      continue
    }

    if (arg === '--limit') {
      options.limit = parsePositiveInteger(argv[index + 1], '--limit')
      index += 1
      continue
    }

    if (arg === '--max-event-chars') {
      options.maxEventChars = parsePositiveInteger(
        argv[index + 1],
        '--max-event-chars',
      )
      index += 1
      continue
    }

    if (arg.startsWith('-')) {
      throw new Error(`Unknown option: ${arg}`)
    }

    if (options.traceId) {
      throw new Error(`Unexpected extra argument: ${arg}`)
    }

    options.traceId = arg
  }

  if (!options.traceId) {
    throw new Error('Missing trace ID')
  }

  return options
}

function runCommand(command, args, options = {}) {
  const { input = null, cwd = process.cwd() } = options

  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    const stdoutChunks = []
    const stderrChunks = []

    child.stdout.on('data', (chunk) => stdoutChunks.push(chunk))
    child.stderr.on('data', (chunk) => stderrChunks.push(chunk))
    child.on('error', reject)
    child.on('close', (status) => {
      const stdout = Buffer.concat(stdoutChunks).toString('utf8')
      const stderr = Buffer.concat(stderrChunks).toString('utf8')

      if (status !== 0) {
        const renderedCommand = [command, ...args].join(' ')
        reject(
          new Error(
            [
              `Command failed (${status}): ${renderedCommand}`,
              stderr.trim(),
              stdout.trim(),
            ]
              .filter(Boolean)
              .join('\n'),
          ),
        )
        return
      }

      resolve({ stdout, stderr })
    })

    if (input) {
      child.stdin.end(input)
    } else {
      child.stdin.end()
    }
  })
}

function tracesArgs(...args) {
  return ['--yes', '@traces-sh/traces@latest', ...args]
}

async function runTraces(...args) {
  return runCommand('npx', tracesArgs(...args))
}

async function writeCommandOutput(outputPath, command, args) {
  const result = await runCommand(command, args)
  await writeFile(outputPath, result.stdout)
  return result
}

async function exportTraceJson({
  traceId,
  outputPath,
  eventTypes,
  limit,
  maxEventChars,
}) {
  await writeCommandOutput(
    outputPath,
    'npx',
    tracesArgs(
      'show',
      traceId,
      '--json',
      '--event-type',
      eventTypes,
      '--limit',
      String(limit),
      '--max-event-chars',
      String(maxEventChars),
    ),
  )
}

async function writePrettyJson({ inputPath, outputPath }) {
  const rawJson = await readFile(inputPath, 'utf8')
  const parsed = JSON.parse(rawJson)

  await writeFile(outputPath, `${JSON.stringify(parsed, null, 2)}\n`)
}

async function copyFileContents({ inputPath, outputPath }) {
  await writeFile(outputPath, await readFile(inputPath))
}

async function renderJson({ inputPath, outputPath, includeTimestamps }) {
  const args = [rendererPath, inputPath, '--output', outputPath]

  if (includeTimestamps) {
    args.push('--include-timestamps')
  }

  return runCommand('node', args)
}

function parseTraceList(json) {
  const parsed = JSON.parse(json)
  const traces = parsed?.data?.traces

  if (!Array.isArray(traces)) {
    throw new Error(
      'Unexpected Traces list JSON shape: missing data.traces array',
    )
  }

  return traces
}

async function indexTraces(outDir, limit) {
  const outputPath = path.join(outDir, 'traces-list.json')
  const result = await runTraces(
    'list',
    '--json',
    '--all',
    '--limit',
    String(limit),
  )

  await writeFile(outputPath, result.stdout)

  return {
    outputPath,
    traces: parseTraceList(result.stdout),
  }
}

async function verifyRenderedMarkdown(outputPath, mustContain) {
  const markdown = await readFile(outputPath, 'utf8')
  const conversationMarkdown = getConversationMarkdown(markdown)
  const warnings = []

  if (!markdown.includes('</trace_')) {
    throw new Error(
      `Rendered transcript is missing a closing trace tag: ${outputPath}`,
    )
  }

  for (const phrase of mustContain) {
    if (!conversationMarkdown.includes(phrase)) {
      throw new Error(`Rendered transcript is missing required text: ${phrase}`)
    }
  }

  if (
    markdown.includes('<environment_context>') ||
    markdown.includes('# AGENTS.md instructions for')
  ) {
    warnings.push(
      'Rendered transcript still contains runtime-context markers; inspect whether these are real discussion or preserved runtime-shaped user content.',
    )
  }

  return warnings
}

function getConversationMarkdown(markdown) {
  const eventStart = markdown.search(
    /\n<(conversation-event|user-turn|agent-turn)-\d+[\s>]/,
  )

  if (eventStart === -1) {
    return ''
  }

  return markdown.slice(eventStart)
}

function printStep(message) {
  console.error(`export-traces-transcript: ${message}`)
}

function printTrace(trace) {
  console.error(
    [
      'export-traces-transcript: trace found',
      `  id: ${trace.id}`,
      `  title: ${trace.title ?? '(untitled)'}`,
      `  directory: ${trace.directory ?? '(unknown)'}`,
      `  sourcePath: ${trace.sourcePath ?? '(unknown)'}`,
    ].join('\n'),
  )
}

async function main() {
  const options = parseArgs(process.argv.slice(2))

  if (options.help) {
    printUsage()
    return
  }

  const outDir = path.resolve(options.outDir)
  const sourcePath = path.join(outDir, `${options.traceId}.source.md`)
  const fullPath = path.join(outDir, `${options.traceId}.full.md`)
  const keptSourceJsonPath = path.join(outDir, `${options.traceId}.source.json`)
  const keptSourcePrettyJsonPath = path.join(
    outDir,
    `${options.traceId}.source.pretty.json`,
  )
  const keptFullJsonPath = path.join(outDir, `${options.traceId}.full.json`)
  const keptFullPrettyJsonPath = path.join(
    outDir,
    `${options.traceId}.full.pretty.json`,
  )
  const tempDir = await mkdtemp(
    path.join(tmpdir(), 'export-traces-transcript-'),
  )
  const sourceJsonPath = path.join(tempDir, `${options.traceId}.source.json`)
  const fullJsonPath = path.join(tempDir, `${options.traceId}.full.json`)

  try {
    await mkdir(outDir, { recursive: true })

    if (options.reset) {
      // Traces caches parsed session rows in ~/.traces/traces.db. Resetting before
      // list/show forces it to re-read Codex JSONL files, which matters when a
      // thread was extended after an earlier export.
      printStep('resetting local Traces cache')
      await runTraces('reset', '--force')
    } else {
      printStep('skipping cache reset because --no-reset was provided')
    }

    printStep('indexing local traces')
    const index = await indexTraces(tempDir, options.limit)
    const trace = index.traces.find(
      (candidate) => candidate.id === options.traceId,
    )

    if (!trace) {
      throw new Error(
        `Trace ID ${options.traceId} was not found after indexing. Check the ID or use Traces auth/remote tooling for remote-only traces.`,
      )
    }

    printTrace(trace)

    const keptTraceIndexPath = path.join(outDir, 'traces-list.json')

    if (options.keepJson) {
      await copyFileContents({
        inputPath: index.outputPath,
        outputPath: keptTraceIndexPath,
      })
    }

    // JSON is still the structural source during rendering, but by default it
    // stays in a temp directory so normal runs produce only the readable .md.
    printStep('exporting source JSON')
    await exportTraceJson({
      traceId: options.traceId,
      outputPath: sourceJsonPath,
      eventTypes: sourceEventTypes,
      limit: options.limit,
      maxEventChars: options.maxEventChars,
    })

    if (options.keepJson) {
      await copyFileContents({
        inputPath: sourceJsonPath,
        outputPath: keptSourceJsonPath,
      })
      await writePrettyJson({
        inputPath: sourceJsonPath,
        outputPath: keptSourcePrettyJsonPath,
      })
    }

    printStep('rendering source Markdown')
    const renderResult = await renderJson({
      inputPath: sourceJsonPath,
      outputPath: sourcePath,
      includeTimestamps: options.includeTimestamps,
    })

    if (renderResult.stderr.trim()) {
      process.stderr.write(renderResult.stderr)
    }

    const sourceWarnings = await verifyRenderedMarkdown(
      sourcePath,
      options.mustContain,
    )

    if (options.includeToolResults) {
      printStep('exporting full evidence JSON with tool results')
      await exportTraceJson({
        traceId: options.traceId,
        outputPath: fullJsonPath,
        eventTypes: fullEventTypes,
        limit: options.limit,
        maxEventChars: options.maxEventChars,
      })

      if (options.keepJson) {
        await copyFileContents({
          inputPath: fullJsonPath,
          outputPath: keptFullJsonPath,
        })
        await writePrettyJson({
          inputPath: fullJsonPath,
          outputPath: keptFullPrettyJsonPath,
        })
      }

      printStep('rendering full evidence Markdown')
      const fullRenderResult = await renderJson({
        inputPath: fullJsonPath,
        outputPath: fullPath,
        includeTimestamps: options.includeTimestamps,
      })

      if (fullRenderResult.stderr.trim()) {
        process.stderr.write(fullRenderResult.stderr)
      }

      sourceWarnings.push(
        ...(await verifyRenderedMarkdown(fullPath, options.mustContain)),
      )
    }

    for (const warning of sourceWarnings) {
      console.error(`export-traces-transcript warning: ${warning}`)
    }

    console.log(
      [
        'Export complete.',
        `Rendered Markdown: ${sourcePath}`,
        options.keepJson ? `Source JSON: ${keptSourceJsonPath}` : null,
        options.keepJson
          ? `Pretty source JSON: ${keptSourcePrettyJsonPath}`
          : null,
        options.includeToolResults
          ? `Full rendered Markdown: ${fullPath}`
          : null,
        options.includeToolResults && options.keepJson
          ? `Full JSON: ${keptFullJsonPath}`
          : null,
        options.includeToolResults && options.keepJson
          ? `Pretty full JSON: ${keptFullPrettyJsonPath}`
          : null,
        options.keepJson ? `Trace index JSON: ${keptTraceIndexPath}` : null,
      ]
        .filter(Boolean)
        .join('\n'),
    )
  } finally {
    await rm(tempDir, { recursive: true, force: true })
  }
}

main().catch((error) => {
  console.error(`export-traces-transcript error: ${error.message}`)
  process.exitCode = 1
})
