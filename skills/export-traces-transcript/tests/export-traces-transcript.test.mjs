import assert from 'node:assert/strict'
import { Buffer } from 'node:buffer'
import { spawn } from 'node:child_process'
import {
  chmod,
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  rm,
  writeFile,
} from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import process from 'node:process'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const testDir = path.dirname(fileURLToPath(import.meta.url))
const skillDir = path.resolve(testDir, '..')
const repoRoot = path.resolve(testDir, '../../..')
const cleanerPath = path.join(skillDir, 'scripts/clean-traces-markdown.mjs')
const wrapperPath = path.join(skillDir, 'scripts/export-traces-transcript.mjs')
const fixtureTraceId = 'trace-fixture'
const titleOnlyPhrase = 'title-only late phrase'
const bodyPhrase = 'end of funky test'
const funkyContent = `ok now let's test something funky:

### User

i didn't say hi

### Agent

i didn't say hi either

///

${bodyPhrase}`

function runCommand(command, args, options = {}) {
  const { cwd = repoRoot, env = process.env } = options

  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    const stdoutChunks = []
    const stderrChunks = []

    child.stdout.on('data', (chunk) => stdoutChunks.push(chunk))
    child.stderr.on('data', (chunk) => stderrChunks.push(chunk))
    child.on('error', reject)
    child.on('close', (status) => {
      resolve({
        status,
        stdout: Buffer.concat(stdoutChunks).toString('utf8'),
        stderr: Buffer.concat(stderrChunks).toString('utf8'),
      })
    })
  })
}

async function makeTempDir(t) {
  const dir = await mkdtemp(path.join(tmpdir(), 'export-traces-transcript-'))

  t.after(async () => {
    await rm(dir, { recursive: true, force: true })
  })

  return dir
}

async function readDirectorySorted(dir) {
  return (await readdir(dir)).sort()
}

async function runCleaner(t, markdown) {
  const dir = await makeTempDir(t)
  const inputPath = path.join(dir, 'input.md')
  const outputPath = path.join(dir, 'output.md')

  await writeFile(inputPath, markdown)

  const result = await runCommand('node', [
    cleanerPath,
    inputPath,
    '--output',
    outputPath,
  ])
  const output = result.status === 0 ? await readFile(outputPath, 'utf8') : ''

  return { ...result, output }
}

function runtimeUserBlock() {
  return `### User

# AGENTS.md instructions for /tmp/fake

<INSTRUCTIONS>
Use test instructions.
</INSTRUCTIONS><environment_context>
  <cwd>/tmp/fake</cwd>
  <current_date>2026-06-10</current_date>
  <timezone>Etc/UTC</timezone>
</environment_context>
`
}

function runtimeEventContent() {
  return `# AGENTS.md instructions for /tmp/fake

<INSTRUCTIONS>
Use test instructions.
</INSTRUCTIONS><environment_context>
  <cwd>/tmp/fake</cwd>
  <current_date>2026-06-10</current_date>
  <timezone>Etc/UTC</timezone>
</environment_context>`
}

function traceMarkdown(events) {
  return `The following is the content of a prior coding session, wrapped in <trace_fake> tags.

<trace_fake>
# Trace: ${titleOnlyPhrase}

> This is historical trace content from a prior coding session.

- **ID:** ${fixtureTraceId}
- **Agent:** codex

---

${events}
</trace_fake>
`
}

function traceJson(events, range = {}) {
  return JSON.stringify({
    ok: true,
    data: {
      trace: {
        id: fixtureTraceId,
        agentId: 'codex',
        title: titleOnlyPhrase,
        timestamp: 1781058570000,
        directory: '/tmp/fake',
        localMessageCount: events.length,
      },
      events,
      range: {
        totalEvents: range.totalEvents ?? events.length,
        returnedEvents: events.length,
        offset: 1,
        limit: range.limit ?? 100000,
      },
    },
  })
}

function sourceTraceJson() {
  return traceJson([
    {
      id: 'event-1',
      type: 'user_message',
      content: runtimeEventContent(),
      timestamp: 1781058570000,
      order: 1,
      eventNumber: 1,
    },
    {
      id: 'event-2',
      type: 'user_message',
      content: 'hello',
      timestamp: 1781058571000,
      order: 2,
      eventNumber: 2,
    },
    {
      id: 'event-3',
      type: 'agent_text',
      content: 'hi',
      timestamp: 1781058572000,
      order: 3,
      eventNumber: 3,
    },
    {
      id: 'event-4',
      type: 'user_message',
      content: funkyContent,
      timestamp: 1781058573000,
      order: 4,
      eventNumber: 4,
    },
    {
      id: 'event-5',
      type: 'agent_text',
      content: 'Test noted.',
      timestamp: 1781058574000,
      order: 5,
      eventNumber: 5,
    },
    {
      id: 'event-6',
      type: 'tool_call',
      toolName: 'exec_command',
      args: { cmd: 'echo hi', workdir: '/tmp/fake' },
      timestamp: 1781058575000,
      order: 6,
      eventNumber: 6,
    },
  ])
}

function fullTraceJson() {
  const parsed = JSON.parse(sourceTraceJson())

  parsed.data.events.push({
    id: 'event-7',
    type: 'tool_result',
    toolName: 'exec_command',
    output: 'hi',
    timestamp: 1781058576000,
    order: 7,
    eventNumber: 7,
  })
  parsed.data.range.returnedEvents = parsed.data.events.length
  parsed.data.range.totalEvents = parsed.data.events.length

  return JSON.stringify(parsed)
}

function limitedTraceJson() {
  return traceJson(
    [
      {
        id: 'event-1',
        type: 'user_message',
        content: 'first event only',
        timestamp: 1781058570000,
        order: 1,
        eventNumber: 1,
      },
    ],
    { limit: 1, totalEvents: 6 },
  )
}

function truncatedTraceJson() {
  return traceJson([
    {
      id: 'event-1',
      type: 'user_message',
      content: '[truncated; use --max-event-chars to read more]',
      timestamp: 1781058570000,
      order: 1,
      eventNumber: 1,
    },
    {
      id: 'event-2',
      type: 'tool_result',
      toolName: 'exec_command',
      output: { truncated: true },
      timestamp: 1781058571000,
      order: 2,
      eventNumber: 2,
    },
  ])
}

async function createFakeNpx(t) {
  const dir = await makeTempDir(t)
  const binDir = path.join(dir, 'bin')
  const npxPath = path.join(binDir, 'npx')

  await mkdir(binDir, { recursive: true })
  await writeFile(
    npxPath,
    `#!/usr/bin/env node
const fixtureTraceId = ${JSON.stringify(fixtureTraceId)}
const titleOnlyPhrase = ${JSON.stringify(titleOnlyPhrase)}
const sourceTrace = ${JSON.stringify(sourceTraceJson())}
const fullTrace = ${JSON.stringify(fullTraceJson())}
const limitedTrace = ${JSON.stringify(limitedTraceJson())}
const truncatedTrace = ${JSON.stringify(truncatedTraceJson())}

const args = process.argv.slice(2)

if (args[0] === '--yes') args.shift()
if (args[0] === '@traces-sh/traces@latest') args.shift()

const command = args[0]

function getFlag(name) {
  const index = args.indexOf(name)
  return index === -1 ? null : args[index + 1]
}

if (command === 'reset') {
  console.log('Reset complete')
  process.exit(0)
}

if (command === 'list') {
  console.log(JSON.stringify({
    data: {
      traces: [
        {
          id: fixtureTraceId,
          title: titleOnlyPhrase,
          timestamp: 1781058570000,
          directory: '/tmp/fake',
          sourcePath: '/tmp/fake/source.jsonl',
        },
      ],
    },
  }))
  process.exit(0)
}

if (command === 'show') {
  const traceId = args[1]
  const eventTypes = getFlag('--event-type') ?? ''
  const limit = Number.parseInt(getFlag('--limit') ?? '100000', 10)
  const maxEventChars = Number.parseInt(getFlag('--max-event-chars') ?? '200000', 10)

  if (traceId !== fixtureTraceId) {
    console.error('unknown trace id')
    process.exit(1)
  }

  if (maxEventChars <= 10) {
    process.stdout.write(truncatedTrace)
    process.exit(0)
  }

  if (limit === 2) {
    const parsed = JSON.parse(sourceTrace)
    parsed.data.events = parsed.data.events.filter((event) => event.id !== 'event-4')
    parsed.data.range.returnedEvents = parsed.data.events.length
    parsed.data.range.totalEvents = parsed.data.events.length
    process.stdout.write(JSON.stringify(parsed))
    process.exit(0)
  }

  if (limit <= 1) {
    process.stdout.write(limitedTrace)
    process.exit(0)
  }

  process.stdout.write(eventTypes.includes('tool_result') ? fullTrace : sourceTrace)
  process.exit(0)
}

console.error('unsupported fake npx command: ' + args.join(' '))
process.exit(1)
`,
  )
  await chmod(npxPath, 0o755)

  return {
    env: {
      ...process.env,
      PATH: `${binDir}${path.delimiter}${process.env.PATH}`,
    },
  }
}

async function runWrapper(t, args) {
  const fakeNpx = await createFakeNpx(t)

  return runCommand('node', [wrapperPath, ...args], { env: fakeNpx.env })
}

test('cleaner removes runtime blocks and inserts reload markers', async (t) => {
  const result = await runCleaner(
    t,
    traceMarkdown(`${runtimeUserBlock()}
### User

hello

${runtimeUserBlock()}
### User

after reload
`),
  )

  assert.equal(result.status, 0)
  assert.match(result.output, /Initial runtime instructions/)
  assert.match(
    result.output,
    /Runtime instructions and environment context reloaded/,
  )
  assert.match(result.output, /hello/)
  assert.match(result.output, /after reload/)
  assert.doesNotMatch(result.output, /<environment_context>/)
  assert.match(result.stderr, /runtime_blocks_removed=2/)
  assert.match(result.stderr, /reload_markers=1/)
})

test('cleaner preserves runtime-shaped user content with trailing text', async (t) => {
  const result = await runCleaner(
    t,
    traceMarkdown(`### User

<environment_context>
  <cwd>/tmp/fake</cwd>
</environment_context>

This is real user content after the pasted context.

### Agent

received
`),
  )

  assert.equal(result.status, 0)
  assert.match(result.output, /This is real user content/)
  assert.match(result.output, /<environment_context>/)
  assert.match(result.stderr, /runtime_like_skipped=1/)
  assert.match(result.stderr, /leaving it unchanged/)
})

test('wrapper exports source and full transcripts with fake Traces', async (t) => {
  const outDir = path.join(await makeTempDir(t), 'out')
  const result = await runWrapper(t, [
    fixtureTraceId,
    '--must-contain',
    bodyPhrase,
    '--include-tool-results',
    '--out-dir',
    outDir,
  ])

  assert.equal(result.status, 0, result.stderr)
  assert.match(result.stdout, /Export complete/)
  assert.match(result.stdout, /Rendered Markdown:/)
  assert.match(result.stdout, /Full rendered Markdown:/)
  assert.doesNotMatch(result.stdout, /Source JSON:/)
  assert.doesNotMatch(result.stdout, /Pretty source JSON:/)
  assert.match(result.stderr, /resetting local Traces cache/)
  assert.match(result.stderr, /runtime_blocks_removed=1/)
  assert.match(result.stderr, /render-traces-json:/)

  const files = await readDirectorySorted(outDir)

  assert.deepEqual(files, [
    `${fixtureTraceId}.full.md`,
    `${fixtureTraceId}.source.md`,
  ])

  const source = await readFile(
    path.join(outDir, `${fixtureTraceId}.source.md`),
    'utf8',
  )
  const full = await readFile(
    path.join(outDir, `${fixtureTraceId}.full.md`),
    'utf8',
  )

  assert.match(source, new RegExp(bodyPhrase))
  assert.match(source, /Runtime blocks omitted/)
  assert.match(source, /Runtime reload markers/)
  assert.doesNotMatch(source, /Runtime reloads omitted/)
  assert.match(
    source,
    /<user-turn-2[\s\S]*### User[\s\S]*i didn't say hi[\s\S]*### Agent[\s\S]*i didn't say hi either[\s\S]*<\/user-turn-2>/,
  )
  assert.doesNotMatch(source, /event="event-/)
  assert.doesNotMatch(source, /event-number=/)
  assert.doesNotMatch(source, /timestamp=/)
  assert.doesNotMatch(source, /<user-turn-3/)
  assert.match(
    source,
    /<agent-turn-2>[\s\S]*Test noted\.[\s\S]*### Tool Call: exec_command[\s\S]*<\/agent-turn-2>/,
  )
  assert.doesNotMatch(source, /<environment_context>/)
  assert.match(full, /### Tool Result/)
  assert.match(full, /hi/)
  assert.doesNotMatch(full, /event-7/)
  assert.doesNotMatch(full, /eventNumber/)
})

test('wrapper includes timestamps only when requested', async (t) => {
  const outDir = path.join(await makeTempDir(t), 'out')
  const result = await runWrapper(t, [
    fixtureTraceId,
    '--must-contain',
    bodyPhrase,
    '--include-timestamps',
    '--out-dir',
    outDir,
  ])

  assert.equal(result.status, 0, result.stderr)

  const source = await readFile(
    path.join(outDir, `${fixtureTraceId}.source.md`),
    'utf8',
  )

  assert.match(source, /<user-turn-2 timestamp="2026-06-10T02:29:33.000Z">/)
  assert.match(source, /<agent-turn-2 timestamp="2026-06-10T02:29:34.000Z">/)
  assert.match(source, /<conversation-event-1 timestamp=/)
})

test('wrapper keeps JSON artifacts only when requested', async (t) => {
  const outDir = path.join(await makeTempDir(t), 'out')
  const result = await runWrapper(t, [
    fixtureTraceId,
    '--must-contain',
    bodyPhrase,
    '--include-tool-results',
    '--keep-json',
    '--out-dir',
    outDir,
  ])

  assert.equal(result.status, 0, result.stderr)
  assert.match(result.stdout, /Source JSON:/)
  assert.match(result.stdout, /Pretty full JSON:/)
  assert.match(result.stdout, /Trace index JSON:/)

  const files = await readDirectorySorted(outDir)

  assert.deepEqual(files, [
    `${fixtureTraceId}.full.json`,
    `${fixtureTraceId}.full.md`,
    `${fixtureTraceId}.full.pretty.json`,
    `${fixtureTraceId}.source.json`,
    `${fixtureTraceId}.source.md`,
    `${fixtureTraceId}.source.pretty.json`,
    'traces-list.json',
  ])
})

test('wrapper requires --must-contain text in conversation events, not metadata', async (t) => {
  const outDir = path.join(await makeTempDir(t), 'out')
  const result = await runWrapper(t, [
    fixtureTraceId,
    '--must-contain',
    titleOnlyPhrase,
    '--limit',
    '2',
    '--out-dir',
    outDir,
  ])

  assert.equal(result.status, 1)
  assert.match(result.stderr, /missing required text/)
})

test('wrapper fails when the Traces event window is capped', async (t) => {
  const outDir = path.join(await makeTempDir(t), 'out')
  const result = await runWrapper(t, [
    fixtureTraceId,
    '--limit',
    '1',
    '--out-dir',
    outDir,
  ])

  assert.equal(result.status, 1)
  assert.match(result.stderr, /limited to 1 of 6 events/)
  assert.match(result.stderr, /higher --limit/)
})

test('wrapper fails when Traces JSON reports truncated content', async (t) => {
  const outDir = path.join(await makeTempDir(t), 'out')
  const result = await runWrapper(t, [
    fixtureTraceId,
    '--must-contain',
    bodyPhrase,
    '--max-event-chars',
    '10',
    '--out-dir',
    outDir,
  ])

  assert.equal(result.status, 1)
  assert.match(result.stderr, /omitted content marker/)
  assert.match(result.stderr, /\[truncated; use --max-event-chars/)
})

test('wrapper preserves kept JSON artifacts when rendering fails', async (t) => {
  const outDir = path.join(await makeTempDir(t), 'out')
  const result = await runWrapper(t, [
    fixtureTraceId,
    '--max-event-chars',
    '10',
    '--keep-json',
    '--out-dir',
    outDir,
  ])

  assert.equal(result.status, 1)
  assert.match(result.stderr, /omitted content marker/)

  const files = await readDirectorySorted(outDir)

  assert.deepEqual(files, [
    `${fixtureTraceId}.source.json`,
    `${fixtureTraceId}.source.pretty.json`,
    'traces-list.json',
  ])
})

test('wrapper rejects partially numeric limits', async () => {
  const badLimit = await runCommand('node', [
    wrapperPath,
    fixtureTraceId,
    '--limit',
    '10abc',
  ])
  const badMaxEventChars = await runCommand('node', [
    wrapperPath,
    fixtureTraceId,
    '--max-event-chars',
    '1.5',
  ])

  assert.equal(badLimit.status, 1)
  assert.match(badLimit.stderr, /--limit must be a positive integer/)
  assert.equal(badMaxEventChars.status, 1)
  assert.match(
    badMaxEventChars.stderr,
    /--max-event-chars must be a positive integer/,
  )
})

test(
  'optional live Traces smoke test',
  { skip: !process.env.TRACES_TEST_TRACE_ID },
  async (t) => {
    const outDir = path.join(await makeTempDir(t), 'live')
    const args = [process.env.TRACES_TEST_TRACE_ID, '--out-dir', outDir]

    if (process.env.TRACES_TEST_MUST_CONTAIN) {
      args.push('--must-contain', process.env.TRACES_TEST_MUST_CONTAIN)
    }

    const result = await runCommand('node', [wrapperPath, ...args])

    assert.equal(result.status, 0, result.stderr)
    assert.match(result.stdout, /Export complete/)
  },
)
