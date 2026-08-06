/**
 * The CLI's behaviour, without spawning it.
 *
 * Commands take their client, output sink and environment as arguments,
 * so what is asserted here is exactly what a user would see and what the
 * API would be asked to do. Spawning a process to check the same things
 * would be slower and would test the shell as much as the code.
 */

import type { AgentVerse } from "@agentverse/sdk";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type CommandContext, type Output, parseArgs, runCommand } from "../src/commands.js";

function collector(): Output & { stdout: string[]; stderr: string[] } {
  const stdout: string[] = [];
  const stderr: string[] = [];
  return {
    stdout,
    stderr,
    out: (line) => stdout.push(line),
    err: (line) => stderr.push(line),
  };
}

type Mock = ReturnType<typeof vi.fn>;

interface Fake {
  agents: { list: Mock; create: Mock; delete: Mock };
  runs: { create: Mock };
  marketplace: { templates: Mock; listings: Mock; install: Mock };
  webhooks: { list: Mock; eventTypes: Mock };
}

let fake: Fake;
let output: ReturnType<typeof collector>;

function context(env: Record<string, string | undefined> = {}): CommandContext {
  return {
    client: () => fake as unknown as AgentVerse,
    output,
    env,
  };
}

beforeEach(() => {
  output = collector();
  fake = {
    agents: {
      list: vi.fn(() => Promise.resolve([])),
      create: vi.fn(() => Promise.resolve({ id: "a1" })),
      delete: vi.fn(() => Promise.resolve(undefined)),
    },
    runs: { create: vi.fn(() => Promise.resolve({ id: "r1", status: "queued" })) },
    marketplace: {
      templates: vi.fn(() => Promise.resolve([])),
      listings: vi.fn(() => Promise.resolve({ data: [], total: 0 })),
      install: vi.fn(() => Promise.resolve({ agent_id: "a1", created: true, version_number: 1 })),
    },
    webhooks: {
      list: vi.fn(() => Promise.resolve([])),
      eventTypes: vi.fn(() => Promise.resolve(["run.completed"])),
    },
  };
});

describe("argument parsing", () => {
  it("separates the command from its flags", () => {
    const parsed = parseArgs(["agents", "list", "--json"]);
    expect(parsed.command).toEqual(["agents", "list"]);
    expect(parsed.flags["json"]).toBe(true);
  });

  it("reads --flag=value", () => {
    expect(parseArgs(["install", "--name=Research"]).flags["name"]).toBe("Research");
  });

  it("reads --flag value", () => {
    expect(parseArgs(["install", "--name", "Research"]).flags["name"]).toBe("Research");
  });

  it("does not swallow the next flag as a value", () => {
    // `--json --limit 5` must not make `--limit` the value of `--json`.
    const parsed = parseArgs(["agents", "list", "--json", "--limit", "5"]);
    expect(parsed.flags["json"]).toBe(true);
    expect(parsed.flags["limit"]).toBe("5");
  });

  it("keeps positional arguments that follow a flag", () => {
    expect(parseArgs(["run", "--json", "a1", "hello"]).positional).toEqual(["a1", "hello"]);
  });
});

describe("help", () => {
  it("prints help with no arguments", async () => {
    expect(await runCommand([], context())).toBe(0);
    expect(output.stdout.join("\n")).toContain("USAGE");
  });

  it("prints help for --help without needing credentials", async () => {
    // The client is constructed lazily precisely so this works.
    expect(await runCommand(["agents", "list", "--help"], context())).toBe(0);
    expect(fake.agents.list).not.toHaveBeenCalled();
  });

  it("fails on an unknown command and says so", async () => {
    expect(await runCommand(["frobnicate"], context())).toBe(1);
    expect(output.stderr.join("\n")).toContain("Unknown command");
  });
});

describe("whoami", () => {
  it("never prints the API key itself", async () => {
    // `whoami` is exactly the command someone runs while sharing their
    // screen; printing the key puts it in shell history and recordings.
    await runCommand(["whoami"], context({ AGENTVERSE_API_KEY: "sk-super-secret" }));
    expect(output.stdout.join("\n")).not.toContain("sk-super-secret");
  });

  it("reports what is set without leaking it", async () => {
    await runCommand(
      ["whoami"],
      context({ AGENTVERSE_API_KEY: "abcdef", AGENTVERSE_WORKSPACE_ID: "ws-1" }),
    );
    const text = output.stdout.join("\n");
    expect(text).toContain("ws-1");
    expect(text).toContain("6 chars");
  });

  it("exits non-zero when the configuration is incomplete", async () => {
    expect(await runCommand(["whoami"], context({}))).toBe(1);
  });

  it("redacts in --json output too", async () => {
    await runCommand(["whoami", "--json"], context({ AGENTVERSE_API_KEY: "sk-secret" }));
    expect(output.stdout.join("")).not.toContain("sk-secret");
  });
});

describe("agents", () => {
  it("lists agents", async () => {
    fake.agents.list.mockResolvedValue([{ id: "a1", status: "draft", name: "Researcher" }]);
    await runCommand(["agents", "list"], context());
    expect(output.stdout.join("\n")).toContain("Researcher");
  });

  it("teaches the next step when there are none", async () => {
    // An empty state that says what to do, not just that there is
    // nothing here.
    await runCommand(["agents", "list"], context());
    expect(output.stdout.join("\n")).toContain("agentverse install");
  });

  it("emits parseable JSON with --json", async () => {
    fake.agents.list.mockResolvedValue([{ id: "a1", status: "draft", name: "R" }]);
    await runCommand(["agents", "list", "--json"], context());
    expect(JSON.parse(output.stdout.join("\n"))).toEqual([
      { id: "a1", status: "draft", name: "R" },
    ]);
  });

  it("refuses to create without the required flags", async () => {
    expect(await runCommand(["agents", "create", "--name", "X"], context())).toBe(1);
    expect(fake.agents.create).not.toHaveBeenCalled();
  });

  it("creates an agent", async () => {
    await runCommand(
      ["agents", "create", "--name", "X", "--model", "gpt-4o-mini", "--instructions", "Be brief"],
      context(),
    );
    expect(fake.agents.create).toHaveBeenCalledWith({
      name: "X",
      model: "gpt-4o-mini",
      system_instructions: "Be brief",
    });
  });

  it("refuses to delete without an id", async () => {
    expect(await runCommand(["agents", "delete"], context())).toBe(1);
    expect(fake.agents.delete).not.toHaveBeenCalled();
  });
});

describe("run", () => {
  it("prints the run id on stdout and the status on stderr", async () => {
    // The id is the machine-readable part, so it goes to stdout alone
    // and `$(agentverse run ...)` captures exactly it.
    await runCommand(["run", "a1", "Summarise", "this"], context());
    expect(output.stdout).toEqual(["r1"]);
    expect(output.stderr.join("\n")).toContain("queued");
  });

  it("joins the input words", async () => {
    await runCommand(["run", "a1", "Summarise", "this", "document"], context());
    expect(fake.runs.create).toHaveBeenCalledWith({
      agentId: "a1",
      input: "Summarise this document",
    });
  });

  it("refuses without an input", async () => {
    expect(await runCommand(["run", "a1"], context())).toBe(1);
    expect(fake.runs.create).not.toHaveBeenCalled();
  });
});

describe("install", () => {
  it("prints the new agent id on stdout", async () => {
    await runCommand(["install", "research-assistant"], context());
    expect(output.stdout).toEqual(["a1"]);
  });

  it("says plainly when nothing new was created", async () => {
    // The difference between "it worked" and "it did nothing, twice".
    fake.marketplace.install.mockResolvedValue({
      agent_id: "a1",
      created: false,
      version_number: 1,
    });
    await runCommand(["install", "research-assistant"], context());
    expect(output.stderr.join("\n")).toContain("Already installed");
  });

  it("passes a chosen name through", async () => {
    await runCommand(["install", "research-assistant", "--name", "Our researcher"], context());
    expect(fake.marketplace.install).toHaveBeenCalledWith("research-assistant", {
      name: "Our researcher",
    });
  });

  it("passes a pinned version through", async () => {
    await runCommand(["install", "research-assistant", "--version", "2"], context());
    expect(fake.marketplace.install).toHaveBeenCalledWith("research-assistant", {
      versionNumber: 2,
    });
  });

  it("ignores a non-numeric version rather than sending NaN", async () => {
    await runCommand(["install", "research-assistant", "--version", "latest"], context());
    expect(fake.marketplace.install).toHaveBeenCalledWith("research-assistant", {});
  });

  it("points at templates when the slug is missing", async () => {
    expect(await runCommand(["install"], context())).toBe(1);
    expect(output.stderr.join("\n")).toContain("agentverse templates");
  });
});

describe("marketplace and templates", () => {
  it("lists templates", async () => {
    fake.marketplace.templates.mockResolvedValue([
      { slug: "research-assistant", category_slug: "research", summary: "Answers from sources." },
    ]);
    await runCommand(["templates"], context());
    expect(output.stdout.join("\n")).toContain("research-assistant");
  });

  it("filters templates by category", async () => {
    await runCommand(["templates", "--category", "engineering"], context());
    expect(fake.marketplace.templates).toHaveBeenCalledWith({ category: "engineering" });
  });

  it("marks first-party listings in search results", async () => {
    fake.marketplace.listings.mockResolvedValue({
      data: [
        { slug: "a", is_official: true, publisher_name: "AgentVerse", summary: "s" },
        { slug: "b", is_official: false, publisher_name: "Acme", summary: "s" },
      ],
      total: 2,
    });
    await runCommand(["marketplace", "search", "code"], context());
    const text = output.stdout.join("\n");
    expect(text).toContain("official");
    expect(text).toContain("Acme");
  });

  it("says so when nothing matched", async () => {
    await runCommand(["marketplace", "search", "zzz"], context());
    expect(output.stdout.join("\n")).toContain("Nothing matched");
  });
});

describe("webhooks", () => {
  it("lists event types", async () => {
    await runCommand(["webhooks", "events"], context());
    expect(output.stdout).toContain("run.completed");
  });

  it("shows whether an endpoint is disabled", async () => {
    fake.webhooks.list.mockResolvedValue([
      { id: "e1", is_active: false, url: "https://x.test/h" },
    ]);
    await runCommand(["webhooks", "list"], context());
    expect(output.stdout.join("\n")).toContain("disabled");
  });

  it("rejects an unknown subcommand", async () => {
    expect(await runCommand(["webhooks", "frobnicate"], context())).toBe(1);
  });
});
