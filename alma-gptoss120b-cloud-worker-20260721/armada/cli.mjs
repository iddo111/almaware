#!/usr/bin/env node
import { fileURLToPath } from "node:url";
import path from "node:path";
import {
  addTask,
  armadaStatus,
  enlistWorker,
  exactMarkerAcceptance,
  initialize,
  listWorkers,
  loadConfig,
  runQueue
} from "./lib.mjs";

const root = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const command = args.shift() || "status";

function option(name, fallback) {
  const index = args.indexOf(`--${name}`);
  return index >= 0 ? args[index + 1] : fallback;
}

function print(value) {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

try {
  const config = await loadConfig(root);
  if (command === "init") {
    await initialize(root);
    print({ ok: true, state: path.join(root, "state") });
  } else if (command === "add") {
    print(await addTask(root, config, {
      role: option("role"),
      prompt: option("prompt"),
      priority: option("priority", 50)
    }));
  } else if (command === "run") {
    print({ results: await runQueue(root, config, {
      maxTasks: option("max-tasks"),
      allowEnlistment: args.includes("--allow-enlistment")
    }) });
  } else if (command === "enlist") {
    print(await enlistWorker(root, config, {
      parent: option("parent"),
      name: option("name"),
      baseRole: option("base-role"),
      purpose: option("purpose"),
      taskBudget: option("task-budget"),
      lifetimeHours: option("lifetime-hours")
    }));
  } else if (command === "workers") {
    print({ workers: await listWorkers(root, config) });
  } else if (command === "status") {
    print(await armadaStatus(root, config, { remote: !args.includes("--local") }));
  } else if (command === "accept") {
    print(await exactMarkerAcceptance(config));
  } else {
    throw new Error("Usage: init | add --role WORKER --prompt TEXT [--priority N] | enlist --parent WORKER --name SLUG --base-role ROLE --purpose TEXT [--task-budget N] [--lifetime-hours N] | workers | run [--max-tasks N] [--allow-enlistment] | status [--local] | accept");
  }
} catch (error) {
  process.stderr.write(`${error.message || error}\n`);
  process.exitCode = 1;
}
