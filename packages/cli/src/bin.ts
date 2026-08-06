#!/usr/bin/env node
/**
 * The CLI entry point, and the only file that touches `process`.
 *
 * Everything it does is delegated to `runCommand`, which takes its
 * dependencies as arguments — so the behaviour is testable without
 * spawning a process, and this file stays small enough to read in one
 * go.
 */

import { AgentVerse, AgentVerseError, ConfigurationError } from "@agentverse/sdk";

import { type CommandContext, runCommand } from "./commands.js";

const context: CommandContext = {
  // Constructed lazily: `agentverse --help` and `agentverse whoami`
  // must work without credentials, and building the client eagerly
  // would make a missing key fail before the help text prints.
  client: () => new AgentVerse(),
  output: {
    out: (line) => process.stdout.write(`${line}\n`),
    err: (line) => process.stderr.write(`${line}\n`),
  },
  env: process.env,
};

try {
  process.exitCode = await runCommand(process.argv.slice(2), context);
} catch (error) {
  if (error instanceof ConfigurationError) {
    // A missing key is a setup problem, not a stack trace.
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 78; // EX_CONFIG
  } else if (error instanceof AgentVerseError) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  } else {
    throw error;
  }
}
