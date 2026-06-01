/**
 * Qualix Phase Status — VS Code extension MVP.
 *
 * Reads .qualix/output/<pid>/state.json and Q06/_gate_verdict.json directly
 * from disk. No dependency on the qualix Python package.
 */

const vscode = require("vscode");
const fs = require("fs");
const path = require("path");

const PHASE_IDS = ["Q01", "Q02", "Q03", "Q04", "Q05a", "Q05b", "Q06", "Q07"];

const STATUS_ICON = {
  approved: { icon: "$(pass)", emoji: "✅" },
  pending_review: { icon: "$(warning)", emoji: "⚠️" },
  hard_blocked: { icon: "$(error)", emoji: "❌" },
  soft_blocked: { icon: "$(warning)", emoji: "⚠️" },
  in_progress: { icon: "$(sync~spin)", emoji: "🔄" },
  not_started: { icon: "$(circle-large-outline)", emoji: "—" },
  unknown: { icon: "$(question)", emoji: "?" },
};

function safeReadJson(filePath) {
  try {
    if (!fs.existsSync(filePath)) {
      return null;
    }
    const raw = fs.readFileSync(filePath, "utf8");
    return JSON.parse(raw);
  } catch (err) {
    return null;
  }
}

function listProjects(workspaceRoot) {
  const outputDir = path.join(workspaceRoot, ".qualix", "output");
  if (!fs.existsSync(outputDir)) {
    return [];
  }
  let entries;
  try {
    entries = fs.readdirSync(outputDir, { withFileTypes: true });
  } catch (err) {
    return [];
  }
  return entries
    .filter((e) => e.isDirectory() && !e.name.startsWith("."))
    .map((e) => e.name)
    .sort();
}

/**
 * Read SE semantic coverage rate.
 * Tries _gate_verdict.json (semantic_coverage.semantic_coverage_rate) first,
 * then falls back to _semantic_coverage_report.json (top-level field).
 * Returns a number in [0, 1] or null.
 */
function readSemanticCoverage(workspaceRoot, projectId) {
  const q06Dir = path.join(workspaceRoot, ".qualix", "output", projectId, "Q06");

  const verdict = safeReadJson(path.join(q06Dir, "_gate_verdict.json"));
  if (verdict && verdict.semantic_coverage && typeof verdict.semantic_coverage.semantic_coverage_rate === "number") {
    return verdict.semantic_coverage.semantic_coverage_rate;
  }

  const report = safeReadJson(path.join(q06Dir, "_semantic_coverage_report.json"));
  if (report && typeof report.semantic_coverage_rate === "number") {
    return report.semantic_coverage_rate;
  }

  return null;
}

function formatCoverage(rate) {
  if (rate === null || rate === undefined) {
    return null;
  }
  return `${Math.round(rate * 100)}% semantic`;
}

function readProjectState(workspaceRoot, projectId) {
  const stateFile = path.join(workspaceRoot, ".qualix", "output", projectId, "state.json");
  const state = safeReadJson(stateFile);
  const phasesData = state && state.phases ? state.phases : {};
  const phases = PHASE_IDS.map((pid) => {
    const entry = phasesData[pid] || {};
    const status = entry.status || "not_started";
    return { phaseId: pid, status };
  });
  const coverage = readSemanticCoverage(workspaceRoot, projectId);
  return {
    projectId,
    phases,
    coverage,
    initialized: state !== null,
  };
}

class QualixTreeNode extends vscode.TreeItem {
  constructor(label, collapsibleState) {
    super(label, collapsibleState);
  }
}

class QualixTreeProvider {
  constructor() {
    this._onDidChangeTreeData = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    this.projects = [];
  }

  refresh() {
    this.projects = this._loadProjects();
    this._onDidChangeTreeData.fire();
  }

  _loadProjects() {
    const workspaceFolders = vscode.workspace.workspaceFolders || [];
    if (workspaceFolders.length === 0) {
      return [];
    }
    const root = workspaceFolders[0].uri.fsPath;
    const projectIds = listProjects(root);
    return projectIds.map((pid) => readProjectState(root, pid));
  }

  getTreeItem(element) {
    return element;
  }

  getChildren(element) {
    if (!element) {
      // Root: list projects, or a single hint node when none.
      if (this.projects.length === 0) {
        const hint = new QualixTreeNode(
          "No Qualix projects found. Run: qualix-run <pid> init",
          vscode.TreeItemCollapsibleState.None,
        );
        hint.iconPath = new vscode.ThemeIcon("info");
        hint.contextValue = "qualixHint";
        return Promise.resolve([hint]);
      }
      return Promise.resolve(
        this.projects.map((proj) => {
          const node = new QualixTreeNode(proj.projectId, vscode.TreeItemCollapsibleState.Expanded);
          node.contextValue = "qualixProject";
          node.iconPath = new vscode.ThemeIcon("folder");
          if (proj.coverage !== null) {
            node.description = formatCoverage(proj.coverage);
          } else if (!proj.initialized) {
            node.description = "no state.json";
          }
          node.qualixProject = proj;
          return node;
        }),
      );
    }

    if (element.contextValue === "qualixProject") {
      const proj = element.qualixProject;
      return Promise.resolve(
        proj.phases.map((p) => {
          const meta = STATUS_ICON[p.status] || STATUS_ICON.unknown;
          const node = new QualixTreeNode(`${meta.emoji} ${p.phaseId}`, vscode.TreeItemCollapsibleState.None);
          node.description = p.status;
          if (p.phaseId === "Q06" && proj.coverage !== null) {
            node.description = `${p.status} · ${formatCoverage(proj.coverage)}`;
          }
          node.tooltip = `${p.phaseId}: ${p.status}`;
          node.contextValue = "qualixPhase";
          node.qualixPhase = { projectId: proj.projectId, phaseId: p.phaseId, status: p.status };
          return node;
        }),
      );
    }

    return Promise.resolve([]);
  }
}

function pickTerminal(name) {
  const existing = vscode.window.terminals.find((t) => t.name === name);
  if (existing) {
    return existing;
  }
  return vscode.window.createTerminal({ name });
}

async function commandRunPhase(node) {
  let target = null;
  if (node && node.qualixPhase) {
    target = node.qualixPhase;
  } else {
    // Invoked from command palette: ask the user.
    const projects = listProjectsFromWorkspace();
    if (projects.length === 0) {
      vscode.window.showWarningMessage("No Qualix projects found in this workspace.");
      return;
    }
    const projectId = await vscode.window.showQuickPick(projects, { placeHolder: "Select Qualix project" });
    if (!projectId) {
      return;
    }
    const phaseId = await vscode.window.showQuickPick(PHASE_IDS, { placeHolder: "Select phase to run" });
    if (!phaseId) {
      return;
    }
    target = { projectId, phaseId };
  }

  const term = pickTerminal(`Qualix · ${target.projectId}`);
  term.show(true);
  term.sendText(`qualix-run ${target.projectId} execute ${target.phaseId} --json`);
}

function listProjectsFromWorkspace() {
  const folders = vscode.workspace.workspaceFolders || [];
  if (folders.length === 0) {
    return [];
  }
  return listProjects(folders[0].uri.fsPath);
}

function commandOpenDashboard() {
  const term = pickTerminal("Qualix Dashboard");
  term.show(true);
  term.sendText("qualix dashboard start");
}

function updateStatusBar(statusBar, treeProvider) {
  const projects = treeProvider.projects;
  if (projects.length === 0) {
    statusBar.hide();
    return;
  }
  // Prefer a project that has a coverage number; else show first project name.
  const withCoverage = projects.find((p) => p.coverage !== null);
  if (withCoverage) {
    statusBar.text = `$(checklist) Qualix: ${Math.round(withCoverage.coverage * 100)}% SE`;
    statusBar.tooltip = `${withCoverage.projectId} — Q06 semantic coverage`;
  } else {
    const first = projects[0];
    statusBar.text = `$(checklist) Qualix: ${first.projectId}`;
    statusBar.tooltip = `${first.projectId} — Q06 has no coverage report yet`;
  }
  statusBar.command = "qualix.focusView";
  statusBar.show();
}

function activate(context) {
  const provider = new QualixTreeProvider();
  provider.refresh();

  const treeView = vscode.window.createTreeView("qualix-phases", {
    treeDataProvider: provider,
    showCollapseAll: true,
  });
  context.subscriptions.push(treeView);

  const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  context.subscriptions.push(statusBar);

  const refresh = () => {
    provider.refresh();
    updateStatusBar(statusBar, provider);
  };

  context.subscriptions.push(
    vscode.commands.registerCommand("qualix.refresh", refresh),
    vscode.commands.registerCommand("qualix.runPhase", commandRunPhase),
    vscode.commands.registerCommand("qualix.openDashboard", commandOpenDashboard),
    vscode.commands.registerCommand("qualix.focusView", () => {
      vscode.commands.executeCommand("qualix-phases.focus");
    }),
  );

  // Watch .qualix/output/**/state.json and Q06/_gate_verdict.json for changes.
  const folders = vscode.workspace.workspaceFolders || [];
  if (folders.length > 0) {
    const root = folders[0];
    const watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(root, ".qualix/output/**/{state.json,_gate_verdict.json,_semantic_coverage_report.json}"),
    );
    watcher.onDidChange(refresh);
    watcher.onDidCreate(refresh);
    watcher.onDidDelete(refresh);
    context.subscriptions.push(watcher);
  }

  refresh();
}

function deactivate() {
  // No persistent state.
}

module.exports = { activate, deactivate };
