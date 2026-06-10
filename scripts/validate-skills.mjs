#!/usr/bin/env node

import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'

const repoRoot = process.cwd()
const skillsRoot = path.join(repoRoot, 'skills')
const marketplacePath = path.join(repoRoot, '.claude-plugin/marketplace.json')
const readmePath = path.join(repoRoot, 'README.md')

function normalizeSkillPath(skillPath) {
  return skillPath.replace(/^\.\//, '').replace(/\/$/, '')
}

function parseFrontmatter(content, filePath) {
  const match = content.match(/^---\n([\s\S]*?)\n---\n/)

  if (!match) {
    throw new Error(`${filePath} is missing YAML frontmatter`)
  }

  const frontmatter = match[1]
  const nameMatch = frontmatter.match(/^name:\s*([a-z0-9-]+)\s*$/m)
  const descriptionMatch = frontmatter.match(/^description:\s*(.+)?$/m)

  if (!nameMatch) {
    throw new Error(`${filePath} is missing a lowercase hyphen-case name`)
  }

  if (!descriptionMatch) {
    throw new Error(`${filePath} is missing a description`)
  }

  return {
    name: nameMatch[1],
  }
}

function compareSets({ actual, expected, label }) {
  const errors = []

  for (const value of expected) {
    if (!actual.has(value)) {
      errors.push(`${label} is missing ${value}`)
    }
  }

  for (const value of actual) {
    if (!expected.has(value)) {
      errors.push(`${label} has unexpected ${value}`)
    }
  }

  return errors
}

async function main() {
  const errors = []
  const skillDirents = await readdir(skillsRoot, { withFileTypes: true })
  const skillNames = skillDirents
    .filter((dirent) => dirent.isDirectory())
    .map((dirent) => dirent.name)
    .sort()

  for (const skillName of skillNames) {
    const skillPath = path.join(skillsRoot, skillName, 'SKILL.md')
    const content = await readFile(skillPath, 'utf8')

    try {
      const frontmatter = parseFrontmatter(content, skillPath)

      if (frontmatter.name !== skillName) {
        errors.push(
          `${skillPath} frontmatter name is ${frontmatter.name}, expected ${skillName}`,
        )
      }

      if (frontmatter.name.length > 64) {
        errors.push(`${skillPath} frontmatter name exceeds 64 characters`)
      }
    } catch (error) {
      errors.push(error.message)
    }
  }

  const marketplace = JSON.parse(await readFile(marketplacePath, 'utf8'))
  const pluginSkills = marketplace.plugins?.[0]?.skills ?? []
  const marketplaceSkills = new Set(pluginSkills.map(normalizeSkillPath).sort())
  const expectedMarketplaceSkills = new Set(
    skillNames.map((skillName) => `skills/${skillName}`),
  )

  errors.push(
    ...compareSets({
      actual: marketplaceSkills,
      expected: expectedMarketplaceSkills,
      label: marketplacePath,
    }),
  )

  const readme = await readFile(readmePath, 'utf8')

  for (const skillName of skillNames) {
    const expectedLink = `[${skillName}](skills/${skillName}/)`

    if (!readme.includes(expectedLink)) {
      errors.push(`${readmePath} is missing ${expectedLink}`)
    }
  }

  if (errors.length > 0) {
    console.error('Skill validation failed:')
    for (const error of errors) {
      console.error(`- ${error}`)
    }
    process.exitCode = 1
    return
  }

  console.log(`Validated ${skillNames.length} skills`)
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
