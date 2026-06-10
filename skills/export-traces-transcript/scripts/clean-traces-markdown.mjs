#!/usr/bin/env node

import { readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'

const eventHeadingPattern =
  /^### (User|Agent|Tool Call: .+|Tool Result(?:[: ].+)?|Error)$/

function printUsage() {
  console.error(`Usage:
  node skills/export-traces-transcript/scripts/clean-traces-markdown.mjs <input.md> [--output <output.md>]

Reads a Traces Markdown export, replaces injected runtime/context user blocks
with compact markers, and writes cleaned Markdown to stdout or --output.`)
}

function parseArgs(argv) {
  let inputPath = null
  let outputPath = null

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]

    if (arg === '--help' || arg === '-h') {
      return { help: true }
    }

    if (arg === '--output' || arg === '-o') {
      outputPath = argv[index + 1]

      if (!outputPath) {
        throw new Error(`${arg} requires a path`)
      }

      index += 1
      continue
    }

    if (arg.startsWith('-')) {
      throw new Error(`Unknown option: ${arg}`)
    }

    if (inputPath) {
      throw new Error(`Unexpected extra argument: ${arg}`)
    }

    inputPath = arg
  }

  if (!inputPath) {
    throw new Error('Missing input Markdown path')
  }

  return { inputPath, outputPath, help: false }
}

function splitLines(value) {
  return value.match(/[^\n]*\n|[^\n]+/g) ?? []
}

function isEventHeading(line) {
  return eventHeadingPattern.test(line.trimEnd())
}

function findEventSections(lines) {
  const sections = []

  for (let index = 0; index < lines.length; index += 1) {
    if (!isEventHeading(lines[index])) {
      continue
    }

    const start = index
    let end = lines.length

    for (let next = index + 1; next < lines.length; next += 1) {
      if (isEventHeading(lines[next])) {
        end = next
        break
      }
    }

    sections.push({
      start,
      end,
      heading: lines[start].trimEnd(),
      text: lines.slice(start, end).join(''),
    })

    index = end - 1
  }

  return sections
}

function countMatches(value, pattern) {
  return [...value.matchAll(pattern)].length
}

function extractTagValue(value, tagName) {
  const match = value.match(new RegExp(`<${tagName}>([^<]+)</${tagName}>`))
  return match?.[1]?.trim() ?? null
}

function getInstructionsSource(value) {
  const match = value.match(/^# AGENTS\.md instructions for (.+)$/m)
  return match?.[1]?.trim() ?? null
}

function analyzeRuntimeContextUserSection(section) {
  if (section.heading !== '### User') {
    return { remove: false }
  }

  const body = section.text.replace(/^### User\s*/, '').trimStart()
  const startsLikeRuntime =
    body.startsWith('# AGENTS.md instructions for ') ||
    body.startsWith('<INSTRUCTIONS>') ||
    body.startsWith('<environment_context>')

  if (!body.includes('<environment_context>')) {
    return { remove: false }
  }

  if (!body.includes('</environment_context>')) {
    return { remove: false }
  }

  if (!startsLikeRuntime) {
    return { remove: false }
  }

  const closeTag = '</environment_context>'
  const closeIndex = body.lastIndexOf(closeTag)
  const trailingText = body.slice(closeIndex + closeTag.length)

  if (trailingText.trim().length > 0) {
    return {
      remove: false,
      runtimeLikeSkipped: true,
      warning:
        `Runtime-shaped user block at line ${section.start + 1} has content ` +
        `after ${closeTag}; leaving it unchanged.`,
    }
  }

  return { remove: true }
}

function buildReplacement(section, replacementIndex) {
  const source = getInstructionsSource(section.text)
  const cwd = extractTagValue(section.text, 'cwd')
  const currentDate = extractTagValue(section.text, 'current_date')
  const timezone = extractTagValue(section.text, 'timezone')
  const label =
    replacementIndex === 0
      ? 'Initial runtime instructions and environment context omitted.'
      : 'Runtime instructions and environment context reloaded.'
  const details = []

  if (source) {
    details.push(`- AGENTS scope: \`${source}\``)
  }

  if (cwd) {
    details.push(`- cwd: \`${cwd}\``)
  }

  if (currentDate) {
    details.push(`- current_date: \`${currentDate}\``)
  }

  if (timezone) {
    details.push(`- timezone: \`${timezone}\``)
  }

  const detailBlock =
    details.length > 0 ? `\n${details.join('\n')}\n\n` : '\n\n'

  return `### Conversation Event

[${label}]
${detailBlock}`
}

function cleanMarkdown(markdown) {
  const lines = splitLines(markdown)
  const sections = findEventSections(lines)
  const warnings = []
  const envContextStarts = countMatches(markdown, /<environment_context>/g)
  const envContextEnds = countMatches(markdown, /<\/environment_context>/g)
  const instructionStarts = countMatches(markdown, /<INSTRUCTIONS>/g)
  const instructionEnds = countMatches(markdown, /<\/INSTRUCTIONS>/g)

  if (sections.length === 0) {
    warnings.push('No Traces event headings were found; output is unchanged.')
  }

  if (envContextStarts !== envContextEnds) {
    warnings.push(
      `Mismatched environment_context tags: ${envContextStarts} start, ${envContextEnds} end.`,
    )
  }

  if (instructionStarts !== instructionEnds) {
    warnings.push(
      `Mismatched INSTRUCTIONS tags: ${instructionStarts} start, ${instructionEnds} end.`,
    )
  }

  const runtimeSections = new Set()
  const replacements = []
  let runtimeLikeSkipped = 0

  for (const section of sections) {
    const analysis = analyzeRuntimeContextUserSection(section)

    if (analysis.warning) {
      warnings.push(analysis.warning)
    }

    if (analysis.runtimeLikeSkipped) {
      runtimeLikeSkipped += 1
    }

    if (!analysis.remove) {
      continue
    }

    runtimeSections.add(section.start)
    replacements.push(section)
  }

  if (
    replacements.length === 0 &&
    envContextStarts > 0 &&
    runtimeLikeSkipped === 0
  ) {
    warnings.push(
      'Found environment_context tags, but none matched the runtime user-block shape.',
    )
  }

  let output = ''
  let cursor = 0
  let replacementIndex = 0

  for (const section of sections) {
    if (!runtimeSections.has(section.start)) {
      continue
    }

    output += lines.slice(cursor, section.start).join('')
    output += buildReplacement(section, replacementIndex)
    cursor = section.end
    replacementIndex += 1
  }

  output += lines.slice(cursor).join('')

  return {
    markdown: output,
    stats: {
      eventSections: sections.length,
      runtimeBlocksRemoved: replacements.length,
      reloadMarkersInserted: Math.max(0, replacements.length - 1),
      runtimeLikeSkipped,
      envContextStarts,
      envContextEnds,
      instructionStarts,
      instructionEnds,
    },
    warnings,
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2))

  if (args.help) {
    printUsage()
    return
  }

  const inputPath = path.resolve(args.inputPath)
  const input = await readFile(inputPath, 'utf8')
  const result = cleanMarkdown(input)

  if (args.outputPath) {
    const outputPath = path.resolve(args.outputPath)

    if (outputPath === inputPath) {
      throw new Error(
        'Refusing to overwrite the input file; choose a separate output path',
      )
    }

    await writeFile(outputPath, result.markdown)
  } else {
    process.stdout.write(result.markdown)
  }

  for (const warning of result.warnings) {
    console.error(`clean-traces-markdown warning: ${warning}`)
  }

  console.error(
    [
      'clean-traces-markdown:',
      `events=${result.stats.eventSections}`,
      `runtime_blocks_removed=${result.stats.runtimeBlocksRemoved}`,
      `reload_markers=${result.stats.reloadMarkersInserted}`,
      `runtime_like_skipped=${result.stats.runtimeLikeSkipped}`,
      `environment_context=${result.stats.envContextStarts}/${result.stats.envContextEnds}`,
      `instructions=${result.stats.instructionStarts}/${result.stats.instructionEnds}`,
    ].join(' '),
  )
}

main().catch((error) => {
  console.error(`clean-traces-markdown error: ${error.message}`)
  process.exitCode = 1
})
