/**
 * What each command does, separated from how it is invoked.
 *
 * Every command takes its dependencies — a client factory, an output
 * sink, the environment — as arguments rather than reaching for
 * `process` or `console` directly. That is what makes the CLI testable
 * without spawning it: the tests assert on what a command *printed* and
 * *called*, which is the whole of its behaviour.
 *
 * **Machine-readable output is not an afterthought.** Every command
 * accepts `--json`, because a CLI whose output can only be read by a
 * human is a CLI nobody can script, and scripting is most of why a
 * developer reaches for one instead of the dashboard.
 */

import type { AgentVerse } from "@agentverse/sdk";

export interface Output {
  out(line: string): void;
  err(line: string): void;
}

export interface CommandContext {
  client: () => AgentVerse;
  output: Output;
  /** Injected rather than read from `process.env`, so tests can set it. */
  env: Record<string, string | undefined>;
}

export interface ParsedArgs {
  command: string[];
  flags: Record<string, string | boolean>;
  positional: string[];
}

/**
 * Flags that never take a value.
 *
 * Declared rather than inferred, because the grammar is genuinely
 * ambiguous without it: in `run --json a1 hello`, a parser that assumes
 * any non-flag token after `--json` is its value swallows the agent id.
 * Guessing from the *next* token cannot resolve that — only knowing
 * which flags are boolean can.
 */
const BOOLEAN_FLAGS: ReadonlySet<string> = new Set(["json", "help", "free", "official"]);

/**
 * A deliberately small parser rather than a dependency.
 *
 * The CLI has one job — call the SDK — and adding an argument-parsing
 * library to do `--json` and `--limit 10` would mean a transitive tree a
 * customer installs to run one command. `--flag=value`, `--flag value`
 * and bare `--flag` are the whole grammar.
 */
export function parseArgs(argv: string[]): ParsedArgs {
  const command: string[] = [];
  const flags: Record<string, string | boolean> = {};
  const positional: string[] = [];
  let seenFlag = false;

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === undefined) continue;

    if (token.startsWith("--")) {
      seenFlag = true;
      const body = token.slice(2);
      const eq = body.indexOf("=");
      if (eq !== -1) {
        flags[body.slice(0, eq)] = body.slice(eq + 1);
        continue;
      }
      if (BOOLEAN_FLAGS.has(body)) {
        flags[body] = true;
        continue;
      }
      const next = argv[index + 1];
      // A following token that is itself a flag means this one was used
      // without a value — `--name --json` is a mistake, not a name of
      // "--json".
      if (next !== undefined && !next.startsWith("--")) {
        flags[body] = next;
        index += 1;
      } else {
        flags[body] = true;
      }
      continue;
    }

    if (seenFlag) positional.push(token);
    else command.push(token);
  }

  return { command, flags, positional };
}

function asJson(output: Output, value: unknown): void {
  output.out(JSON.stringify(value, null, 2));
}

function wantsJson(flags: Record<string, string | boolean>): boolean {
  return flags["json"] === true || flags["json"] === "true";
}

/** Right-pad, for the human-readable tables. */
function pad(value: string, width: number): string {
  return value.length >= width ? value : value + " ".repeat(width - value.length);
}

export const HELP = `agentverse — build, run and install AI agents

USAGE
  agentverse <command> [options]

COMMANDS
  agents list                       List this workspace's agents
  agents create                     Create an agent
                                      --name --model --instructions
  agents delete <agent-id>          Delete an agent
  run <agent-id> <input...>         Start a run and print its id
  templates                         The first-party template library
  marketplace search [query]        Search the public catalog
  install <slug>                    Install a listing into this workspace
                                      --name --version
  webhooks list                     List webhook endpoints
  webhooks events                   Event types you can subscribe to
  whoami                            Show the resolved configuration

OPTIONS
  --json                            Machine-readable output
  --help                            This message

ENVIRONMENT
  AGENTVERSE_API_KEY                Required
  AGENTVERSE_WORKSPACE_ID           Required
  AGENTVERSE_BASE_URL               Override the API host
`;

export async function runCommand(argv: string[], context: CommandContext): Promise<number> {
  const { command, flags, positional } = parseArgs(argv);

  if (command.length === 0 || flags["help"] === true || command[0] === "help") {
    context.output.out(HELP);
    return 0;
  }

  const [group, action] = command;

  switch (group) {
    case "whoami":
      return whoami(context, flags);
    case "agents":
      return agents(action, [...command.slice(2), ...positional], context, flags);
    case "run":
      return run([...command.slice(1), ...positional], context, flags);
    case "templates":
      return templates(context, flags);
    case "marketplace":
      return marketplace(action, [...command.slice(2), ...positional], context, flags);
    case "install":
      return install([...command.slice(1), ...positional], context, flags);
    case "webhooks":
      return webhooks(action, context, flags);
    default:
      context.output.err(`Unknown command: ${group ?? ""}\n`);
      context.output.err(HELP);
      return 1;
  }
}

function whoami(context: CommandContext, flags: Record<string, string | boolean>): number {
  const key = context.env["AGENTVERSE_API_KEY"];
  const resolved = {
    workspace_id: context.env["AGENTVERSE_WORKSPACE_ID"] ?? null,
    base_url: context.env["AGENTVERSE_BASE_URL"] ?? "https://api.agentverse.dev",
    // Never the key itself. A CLI that prints credentials puts them in
    // shell history, CI logs and screen recordings — and `whoami` is
    // exactly the command someone runs while sharing their screen.
    api_key: key === undefined ? null : `set (${String(key.length)} chars)`,
  };
  if (wantsJson(flags)) {
    asJson(context.output, resolved);
    return 0;
  }
  context.output.out(`workspace  ${resolved.workspace_id ?? "(not set)"}`);
  context.output.out(`base url   ${resolved.base_url}`);
  context.output.out(`api key    ${resolved.api_key ?? "(not set)"}`);
  return key === undefined || resolved.workspace_id === null ? 1 : 0;
}

async function agents(
  action: string | undefined,
  args: string[],
  context: CommandContext,
  flags: Record<string, string | boolean>,
): Promise<number> {
  const client = context.client();

  if (action === "list" || action === undefined) {
    const rows = await client.agents.list();
    if (wantsJson(flags)) {
      asJson(context.output, rows);
      return 0;
    }
    if (rows.length === 0) {
      // An empty state that says what to do next, not just that there is
      // nothing here.
      context.output.out("No agents yet. Try: agentverse install research-assistant");
      return 0;
    }
    for (const row of rows) {
      context.output.out(`${pad(row.id, 38)}${pad(row.status, 12)}${row.name}`);
    }
    return 0;
  }

  if (action === "create") {
    const name = flags["name"];
    const model = flags["model"];
    const instructions = flags["instructions"];
    if (typeof name !== "string" || typeof model !== "string" || typeof instructions !== "string") {
      context.output.err("agents create needs --name, --model and --instructions");
      return 1;
    }
    const agent = await client.agents.create({
      name,
      model,
      system_instructions: instructions,
    });
    if (wantsJson(flags)) asJson(context.output, agent);
    else context.output.out(agent.id);
    return 0;
  }

  if (action === "delete") {
    const agentId = args[0];
    if (agentId === undefined) {
      context.output.err("agents delete needs an agent id");
      return 1;
    }
    await client.agents.delete(agentId);
    context.output.out(`Deleted ${agentId}`);
    return 0;
  }

  context.output.err(`Unknown agents subcommand: ${action}`);
  return 1;
}

async function run(
  args: string[],
  context: CommandContext,
  flags: Record<string, string | boolean>,
): Promise<number> {
  const [agentId, ...rest] = args;
  const input = rest.join(" ");
  if (agentId === undefined || input === "") {
    context.output.err("run needs an agent id and an input");
    return 1;
  }
  const created = await context.client().runs.create({ agentId, input });
  if (wantsJson(flags)) {
    asJson(context.output, created);
  } else {
    context.output.out(created.id);
    // Runs are asynchronous by design (Rule 14), so the CLI says so
    // rather than appearing to hang or appearing to have finished.
    context.output.err(`Queued. Status: ${created.status}`);
  }
  return 0;
}

async function templates(
  context: CommandContext,
  flags: Record<string, string | boolean>,
): Promise<number> {
  const category = typeof flags["category"] === "string" ? flags["category"] : undefined;
  const rows = await context
    .client()
    .marketplace.templates(category === undefined ? {} : { category });
  if (wantsJson(flags)) {
    asJson(context.output, rows);
    return 0;
  }
  for (const row of rows) {
    context.output.out(`${pad(row.slug, 24)}${pad(row.category_slug, 16)}${row.summary}`);
  }
  return 0;
}

async function marketplace(
  action: string | undefined,
  args: string[],
  context: CommandContext,
  flags: Record<string, string | boolean>,
): Promise<number> {
  if (action !== "search" && action !== undefined) {
    context.output.err(`Unknown marketplace subcommand: ${action}`);
    return 1;
  }
  const query = args.join(" ");
  const page = await context.client().marketplace.listings(query === "" ? {} : { q: query });
  if (wantsJson(flags)) {
    asJson(context.output, page);
    return 0;
  }
  if (page.data.length === 0) {
    context.output.out("Nothing matched.");
    return 0;
  }
  for (const row of page.data) {
    const badge = row.is_official ? "official" : row.publisher_name;
    context.output.out(`${pad(row.slug, 24)}${pad(badge, 20)}${row.summary}`);
  }
  return 0;
}

async function install(
  args: string[],
  context: CommandContext,
  flags: Record<string, string | boolean>,
): Promise<number> {
  const slug = args[0];
  if (slug === undefined) {
    context.output.err("install needs a listing slug. Try: agentverse templates");
    return 1;
  }
  const name = typeof flags["name"] === "string" ? flags["name"] : undefined;
  const version = typeof flags["version"] === "string" ? Number(flags["version"]) : undefined;
  const result = await context.client().marketplace.install(slug, {
    ...(name === undefined ? {} : { name }),
    ...(version === undefined || Number.isNaN(version) ? {} : { versionNumber: version }),
  });
  if (wantsJson(flags)) {
    asJson(context.output, result);
    return 0;
  }
  context.output.out(result.agent_id);
  // `created: false` means an identical install already existed and the
  // same agent came back. Saying so is the difference between "it
  // worked" and "it did nothing, twice".
  context.output.err(
    result.created
      ? `Installed ${slug} v${String(result.version_number)}`
      : `Already installed — returning the existing agent`,
  );
  return 0;
}

async function webhooks(
  action: string | undefined,
  context: CommandContext,
  flags: Record<string, string | boolean>,
): Promise<number> {
  const client = context.client();
  if (action === "events") {
    const events = await client.webhooks.eventTypes();
    if (wantsJson(flags)) asJson(context.output, events);
    else for (const event of events) context.output.out(event);
    return 0;
  }
  if (action === "list" || action === undefined) {
    const rows = await client.webhooks.list();
    if (wantsJson(flags)) {
      asJson(context.output, rows);
      return 0;
    }
    for (const row of rows) {
      const state = row.is_active ? "active" : "disabled";
      context.output.out(`${pad(row.id, 38)}${pad(state, 10)}${row.url}`);
    }
    return 0;
  }
  context.output.err(`Unknown webhooks subcommand: ${action}`);
  return 1;
}
