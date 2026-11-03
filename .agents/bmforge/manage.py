#!/usr/bin/env python3
"""Install and manage pinned BMForge Codex skills in Git repositories.

The check operation never writes to the application or its installed skills.
"""

from argparse import ArgumentParser
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


SOURCE_URL = "https://github.com/NadimGhaznavi/bmforge.git"
SOURCE_BRANCH = "main"
SKILLS = {
    "bmforge-project": (None, ()),
    "bmforge-constants": ("pages/component-constants.md", (
        "components/reference/snake-lab/snakelab/constants/DGame.py",
        "components/reference/snake-lab/snakelab/constants/DSQL.py",
        "components/reference/snake-lab/snakelab/constants/DMyLog.py",
        "components/reference/snake-lab/snakelab/constants/DSnakeLab.py",
        "components/reference/bmgeoip/bmgeoip/constants/DBMGeoIP.py",
        "components/reference/bmgeoip/bmgeoip/constants/DGeoIp.py",
        "components/reference/bmgeoip/bmgeoip/constants/DZMQ.py",
    )),
    "bmforge-localization": ("pages/component-localization.md", (
        "components/reference/minimal-mistakes/_includes/language-selector.html",
        "components/reference/minimal-mistakes/assets/js/multilingual.js",
        "components/reference/blog/_data/taxonomy_translations.yml",
        "components/reference/blog/es/index.md",
    )),
    "bmforge-installation": ("pages/component-installation.md", (
        "components/reference/devlog/scripts/deploy.py",
        "components/reference/devlog/scripts/install.sh",
        "components/reference/devlog/scripts/install-server.sh",
        "components/reference/devlog/scripts/upgrade.sh",
        "components/reference/devlog/tests/test_deployment.py",
        "components/reference/devlog/docs/architecture.md",
    )),
    "bmforge-http": ("pages/component-http.md", (
        "components/reference/bmgeoip/bmgeoip/server/BMGeoIPServer.py",
        "components/reference/bmgeoip/bmgeoip/server/BMGeoIPHandler.py",
        "components/reference/bmgeoip/bmgeoip/server/LookupHandler.py",
        "components/reference/bmdynip/bmdynip/server/static/index.html",
        "components/reference/bmdynip/bmdynip/server/static/style.css",
    )),
    "bmforge-zmq": ("pages/component-zmq.md", (
        "components/reference/bmgeoip/bmgeoip/zmq/ZMQServer.py",
        "components/reference/bmgeoip/bmgeoip/zmq/ZMQMsg.py",
    )),
    "bmforge-db-server": ("pages/component-db-server.md", (
        "components/reference/bmgeoip/bmgeoip/interface/GeoIpDb.py",
        "components/reference/mycount/mycount/interface/VisitDb.py",
    )),
    "bmforge-git": ("pages/component-git.md", (
        "components/reference/snake-web-code/snakewebcode/interface/GitPublisher.py",
    )),
    "bmforge-visualization": ("pages/component-visualization.md", (
        "components/reference/mycount/mycount/server/ControlPages.py",
        "components/reference/mycount/mycount/server/templates/base.html",
        "components/reference/mycount/mycount/server/templates/chart_theme.html",
        "components/reference/mycount/mycount/server/templates/all_traffic.html",
        "components/reference/mycount/mycount/server/templates/pie_charts.html",
        "components/reference/mycount/mycount/server/templates/marketing_chart.html",
        "components/reference/mycount/mycount/server/templates/visitor_map.html",
        "components/reference/cmdb/cmdb/server/templates/home.html",
        "components/reference/cmdb/cmdb/server/static/machines.js",
        "components/reference/cmdb/cmdb/server/static/vendor/cytoscape-3.34.3.min.js",
        "components/reference/cmdb/cmdb/server/static/vendor/cytoscape-LICENSE",
    )),
    "bmforge-gif-animation": ("pages/component-gif-animation.md", (
        "components/reference/snake-web-code/snakewebcode/activity/SimulationAnimation.py",
    )),
    "bmforge-timeline": ("pages/component-timeline.md", ()),
    "bmforge-nftables": ("pages/component-nftables.md", ()),
    "bmforge-fail2ban": ("pages/component-fail2ban.md", ()),
    "bmforge-security-events": ("pages/component-security-events.md", ()),
    "bmforge-github-pages": ("pages/jekyll-setup.md", ()),
    "bmforge-rca": (None, ()),
}
BASE_SKILLS = ("bmforge-project", "bmforge-constants", "bmforge-localization", "bmforge-installation")
REQUIRES = {
    "bmforge-timeline": ("bmforge-http",),
    "bmforge-fail2ban": ("bmforge-zmq",),
}
COMMON = (
    "pages/engineering-contract.md",
    "pages/classification.md",
    "pages/specification-lifecycle.md",
    "pages/component-blueprints.md",
)
HEALTH = "pages/health-checks.md"
DB_TEMPLATE = "components/templates/db-server/interface/DbMgr.py"
GIT_TEMPLATE = "components/templates/git/Git.py"
GIF_TEMPLATE = "components/templates/gif-animation/interface/GIFAnimation.py"
SECURITY_EVENTS_TEMPLATE = "components/templates/security-events/interface/SecurityEvents.py"
CONSTANTS_TEMPLATE = "templates/project/constants/DProject.py"
LOCALIZER_TEMPLATE = "components/templates/localization/interface/Localizer.py"
TEXT_TEMPLATE = "components/templates/constants/DText.py"
EN_CATALOG = "components/templates/localization/locales/en.json"
RELEASE_TEMPLATES = {
    "scripts/new-release.sh": "templates/project/scripts/new-release.sh",
    "scripts/check-cmdb.py": "templates/project/scripts/check-cmdb.py",
    "scripts/install.py": "templates/project/scripts/install.py",
    "scripts/install.sh": "templates/project/scripts/install.sh",
    "scripts/upgrade.sh": "templates/project/scripts/upgrade.sh",
    "scripts/uninstall.sh": "templates/project/scripts/uninstall.sh",
    "CHANGELOG.md": "templates/project/CHANGELOG.md",
}
RELEASE_GUIDES = ("pages/release-setup.md", "pages/creating-a-release.md",
                  "pages/changelog-maintenance.md")
INSTALLATION_GUIDES = ("pages/installation-scripts.md", "pages/cmdb-compliance.md")
GITHUB_PAGES_ASSETS = {
    "_config.yml": "templates/_config.yml",
    "jekyll-gh-pages.yml": "templates/jekyll-gh-pages.yml",
    "index.md": "templates/github-pages/index.md",
    "README.md": "templates/github-pages/README.md",
    "page.md": "templates/github-pages/page.md",
}
GITHUB_PAGES_GUIDES = ("pages/github-pages-publishing.md",
                      "pages/multilingual-documentation.md")
LOCK = Path(".agents/bmforge/lock.json")
MANAGER = Path(".agents/bmforge/manage.py")
DEFAULT_SOURCE_CACHE = Path.home() / ".cache/bmforge-upstream"


class SetupError(Exception):
    """A safe, user-facing failure."""


def git(*args, cwd=None):
    result = subprocess.run(["git", *map(str, args)], cwd=cwd,
                            capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise SetupError(f"Git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


@contextmanager
def source_checkout(source):
    """Use an explicit checkout or an ephemeral clone of the published branch."""
    if source and Path(source).is_dir():
        root = Path(source).resolve()
        if not (root / "skills/bmforge-project/SKILL.md").is_file():
            raise SetupError(f"Not a BMForge skill source: {root}")
        yield root, git("rev-parse", "HEAD", cwd=root)
        return
    with tempfile.TemporaryDirectory(prefix="bmforge-source-") as directory:
        remote = source or SOURCE_URL
        git("clone", "--quiet", "--depth", "1", "--branch", SOURCE_BRANCH,
            "--", remote, directory)
        root = Path(directory)
        yield root, git("rev-parse", "HEAD", cwd=root)


def project_root(project):
    root = Path(project).resolve()
    if not root.is_dir():
        raise SetupError(f"Project directory does not exist: {root}")
    actual = Path(git("rev-parse", "--show-toplevel", cwd=root)).resolve()
    if root != actual:
        raise SetupError("Run against the repository root, not a nested directory")
    return root


def selected_names(value):
    names = [p.strip() for p in value.split(",") if p.strip()] if value else []
    if len(names) != len(set(names)):
        raise SetupError("Duplicate component selection")
    unknown = sorted(set(names) - (set(SKILLS) - set(BASE_SKILLS)))
    if unknown:
        raise SetupError("Unknown component(s): " + ", ".join(unknown))
    return names


def require_components(names, installed=()):
    available = set(names) | set(installed)
    for name in names:
        for dependency in REQUIRES.get(name, ()):
            if dependency not in available:
                raise SetupError(f"{name} requires {dependency}; select both components or install the dependency first")


def bundle(source, name):
    spec, snapshots = SKILLS[name]
    files = {"SKILL.md": f"skills/{name}/SKILL.md"}
    for common in COMMON:
        files["references/" + Path(common).name] = common
    if spec:
        files["references/specification.md"] = spec
    if name == "bmforge-project":
        for destination, original in RELEASE_TEMPLATES.items():
            files["assets/release/" + destination] = original
        for guide in RELEASE_GUIDES:
            files["references/" + Path(guide).name] = guide
    if name == "bmforge-installation":
        for guide in INSTALLATION_GUIDES:
            files["references/" + Path(guide).name] = guide
    if name == "bmforge-github-pages":
        for destination, original in GITHUB_PAGES_ASSETS.items():
            files["assets/" + destination] = original
        for guide in GITHUB_PAGES_GUIDES:
            files["references/" + Path(guide).name] = guide
        files["agents/openai.yaml"] = "skills/bmforge-github-pages/agents/openai.yaml"
    if name in ("bmforge-http", "bmforge-zmq", "bmforge-db-server"):
        files["references/health-checks.md"] = HEALTH
    for snapshot in snapshots:
        files["references/source/" + snapshot.removeprefix("components/reference/")] = snapshot
    if name == "bmforge-db-server":
        files["assets/DbMgr.py"] = DB_TEMPLATE
    if name == "bmforge-git":
        files["assets/Git.py"] = GIT_TEMPLATE
    if name == "bmforge-gif-animation":
        files["assets/GIFAnimation.py"] = GIF_TEMPLATE
    if name == "bmforge-security-events":
        files["assets/SecurityEvents.py"] = SECURITY_EVENTS_TEMPLATE
    if name == "bmforge-constants":
        files["assets/DProject.py"] = CONSTANTS_TEMPLATE
    if name == "bmforge-localization":
        files["assets/Localizer.py"] = LOCALIZER_TEMPLATE
        files["assets/DText.py"] = TEXT_TEMPLATE
        files["assets/en.json"] = EN_CATALOG
    result = {}
    for destination, original in files.items():
        path = source / original
        if not path.is_file() or path.is_symlink():
            raise SetupError(f"Missing regular BMForge source file: {original}")
        result[destination] = path.read_bytes()
    return result


def fingerprint(files):
    digest = sha256()
    for name, data in sorted(files.items()):
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(sha256(data).digest())
    return digest.hexdigest()


def installed_bundle(directory):
    if not directory.is_dir() or directory.is_symlink():
        raise SetupError(f"Missing or invalid installed skill: {directory}")
    entries = {}
    for file in directory.rglob("*"):
        if file.is_symlink():
            raise SetupError(f"Symlinks are not permitted in installed skills: {file}")
        if file.is_file():
            entries[file.relative_to(directory).as_posix()] = file.read_bytes()
    return entries


def spec_version(source, name):
    spec, _ = SKILLS[name]
    if spec is None:
        return "0.1.0"
    for line in (source / spec).read_text().splitlines():
        if line.startswith("spec_version: "):
            return line.split('"')[1]
    raise SetupError(f"Specification version missing for {name}")


def copy_bundle(directory, files):
    directory.mkdir(parents=True, exist_ok=False)
    for relative, content in files.items():
        output = directory / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)


def write_json_atomic(path, value):
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".bmforge-", delete=False) as stream:
        candidate = Path(stream.name)
        try:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            candidate.replace(path)
        finally:
            candidate.unlink(missing_ok=True)


def root_agents():
    return """# Project engineering instructions

This project uses **pinned BMForge Codex skills**. These are project-owned copies,
not live imports from BMForge or another application.

Before the first BMForge-related edit in a Codex session, run the **read-only**,
**offline** update check from the repository root:

    python3 .agents/bmforge/manage.py check --project .

If this project's policy prohibits all Git commands, use the alternative:

    python3 .agents/bmforge/manage.py verify --project .

verify checks only local pinned-skill and manager hashes, with no Git, network or
writes; it does not check whether newer upstream skills exist.

The check reads a clean local BMForge main checkout at
~/.cache/bmforge-upstream (override with BMFORGE_SOURCE or --source).
It never fetches or clones. Refresh that checkout separately with
'git pull --ff-only', outside this check. "CURRENT" means current as of the
reported cached source revision, not necessarily the newest GitHub commit.
Report available changes or an unavailable check to the user. **Do not apply
updates**, reinstall skills, or replace approved technologies without explicit
user authorization. Continue using the pinned skills unless instructed otherwise.

Read `.agents/skills/bmforge-project/SKILL.md` for architecture. Every new app
also follows the pinned `bmforge-constants`, `bmforge-localization` and
`bmforge-installation` skills: centralize programmatic identifiers, prepare
English localization keys from its first user-facing feature, and implement
the installation lifecycle for the actual application before the first release.
Add translations only when requested, never by guessing. Invoke other
components as needed.
Follow each selected skill's local
`references/specification.md` and approved module inventory. Never invent another
framework, database driver or plotting library as a shortcut.

Component selection and application-specific behaviour belong to this project's
requirements. A pinned skill is an instruction bundle, not executable app code.

For applications with more than one service, create an executable
`scripts/services` supporting `start` and `stop`. Run the application's
start/stop commands sequentially in an explicit order. Keep it simple;
no dependency awareness is required.

Implementation authorization gate: discussion, brainstorming, design and
proposed specifications do not authorize implementation. Read-only investigation
is permitted, but do not modify project files (including code, tests,
configuration or documentation), install dependencies or perform other
mutating work until the user explicitly authorizes the agreed scope.
A direct request to implement or fix counts; no magic words are required.
Once authorized, complete that scope, its tests and its changelog without
asking about every file. Pause for unapproved dependencies, architecture
or material scope expansion. Permission to implement does not authorize
commits, pushes, releases or deployments.

For EVERY completed logical change, including small code, tests, documentation,
configuration and maintenance work, update `CHANGELOG.md` under the single
`## [Unreleased]` heading before reporting completion or committing. Do not
wait for the release. Add or refresh one `### Summary` for each meaningful
feature, fix or operational improvement, even if only one change has occurred.
Maintain one Summary heading per section. Follow the pinned
`.agents/skills/bmforge-project/references/changelog-maintenance.md` guide.

Bootstrap provided `scripts/new-release.sh` with metadata, changelog and
deployment-disabled install/upgrade/uninstall stubs. Complete and test these
stubs through `bmforge-installation` once the application topology is known.
Every successful installation must create the application-owned BASE_DIR and
last-successful `.deployment-version`, even for a client or custom library.
Do not run release or deployment tools, commit, tag or push without explicit
user authorization. Once the user reviews and commits the scaffold on local
main, use `python3 .agents/bmforge/manage.py setup-branches --project . --dry-run`
to preview, then `setup-branches` with user approval to create local dev and
feat/maint-0.1.0. It never commits or pushes. Never re-create existing refs.
Read the pinned project's release-setup and creating-a-release references
before release work.
"""


def release_scaffold(bundles, name, subtype):
    """Adapt the established BMForge release templates without inventing a new script."""
    if (not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
            or re.search(r"__[A-Z_]+__", name)):
        raise SetupError("--name must be a canonical Python class name, e.g. SnakeLab")
    if (not isinstance(subtype, str) or not subtype.strip() or len(subtype) > 255
            or any(ord(char) < 32 or ord(char) == 127 for char in subtype)
            or re.search(r"__[A-Z_]+__", subtype)):
        raise SetupError("--subtype must be a nonempty literal description without controls")
    slug = name.lower()
    files = {}
    for destination in RELEASE_TEMPLATES:
        template = bundles["bmforge-project"]["assets/release/" + destination]
        text = template.decode("utf-8")
        text = text.replace("__PROJECT_NAME__", name).replace("__PROJECT_SLUG__", slug)
        if "__PROJECT_" in text:
            raise SetupError(f"Unresolved project placeholder in {destination}")
        files[destination] = text.encode("utf-8")
    template = bundles["bmforge-constants"]["assets/DProject.py"].decode("utf-8")
    if template.count("class DProject:") != 1 or template.count('"__PROJECT_SUBTYPE__"') != 1:
        raise SetupError("Canonical project constants template has changed unexpectedly")
    text = template.replace("class DProject:", f"class D{name}:")
    text = text.replace("__PROJECT_SLUG__", slug)
    text = text.replace('"__PROJECT_SUBTYPE__"', json.dumps(subtype, ensure_ascii=False))
    if "__PROJECT_" in text:
        raise SetupError("Unresolved project placeholder in constants")
    files[f"{slug}/constants/D{name}.py"] = text.encode("utf-8")
    return files


def check_scaffold_destinations(root, files):
    """Refuse to overwrite any pre-existing project file or traverse symlinks."""
    for relative in files:
        path = root / relative
        if path.exists() or path.is_symlink():
            raise SetupError(f"Release scaffold already exists; refusing overwrite: {relative}")
        directory = path.parent
        while directory != root:
            if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
                raise SetupError(f"Unsafe existing parent for release file: {relative}")
            directory = directory.parent


def write_scaffold(root, files, created_files, created_directories):
    for relative, content in files.items():
        target = root / relative
        missing = []
        directory = target.parent
        while directory != root and not directory.exists():
            missing.append(directory)
            directory = directory.parent
        for directory in reversed(missing):
            directory.mkdir()
            created_directories.append(directory)
        created_files.append(target)
        target.write_bytes(content)
        if relative.endswith(".sh"):
            target.chmod(0o755)


def start_init(args):
    root = project_root(args.project)
    if (root / ".agents").exists() or (root / "AGENTS.md").exists():
        raise SetupError("Refusing to overwrite existing .agents/ or AGENTS.md")
    names = [*BASE_SKILLS, *selected_names(args.components)]
    require_components(names)
    with source_checkout(args.source) as (source, revision):
        bundles = {name: bundle(source, name) for name in names}
        versions = {name: spec_version(source, name) for name in names}
        manager_source = (source / "skills/bmforge/scripts/manage.py").read_bytes()
        scaffolding = release_scaffold(bundles, args.name, args.subtype)
    check_scaffold_destinations(root, scaffolding)
    base = root / ".agents"
    created_files = []
    created_directories = []
    try:
        (root / LOCK.parent).mkdir(parents=True)
        (root / MANAGER).write_bytes(manager_source)
        for name, files in bundles.items():
            copy_bundle(root / ".agents/skills" / name, files)
        write_json_atomic(root / LOCK, {
            "schema": 1,
            "repository": args.source or SOURCE_URL,
            "branch": SOURCE_BRANCH,
            "source_commit": revision,
            "manager_sha256": sha256(manager_source).hexdigest(),
            "skills": {name: {"spec_version": versions[name],
                               "sha256": fingerprint(files),
                               "source_commit": revision}
                       for name, files in bundles.items()},
        })
        write_scaffold(root, scaffolding, created_files, created_directories)
        (root / "AGENTS.md").write_text(root_agents(), encoding="utf-8")
    except BaseException:
        for path in reversed(created_files):
            path.unlink(missing_ok=True)
        for directory in reversed(created_directories):
            directory.rmdir()
        if base.exists():
            shutil.rmtree(base)
        raise
    print(f"Installed {len(names)} pinned BMForge skill(s) from {revision[:12]}:")
    for name in names:
        print(f"  {name} ({versions[name]})")
    print(f"Prepared {len(scaffolding)} existing BMForge release templates for {args.name}, including scripts/new-release.sh")
    print("Release tooling is not executed; review and commit the scaffold on local main.")
    print("After explicit approval, create local dev/feature branches with:")
    print("  python3 .agents/bmforge/manage.py setup-branches --project . --dry-run")
    print("  python3 .agents/bmforge/manage.py setup-branches --project .")
    print("No remote branches are pushed automatically.")
    print("Check updates with:")
    print("  python3 .agents/bmforge/manage.py check --project .")


def start_attach(args):
    """Pin selected skills in an existing repository without adopting its architecture."""
    root = project_root(args.project)
    names = selected_names(args.components)
    if not names:
        raise SetupError("Select at least one component to attach")
    require_components(names)
    agents = root / ".agents"
    skills_dir = agents / "skills"
    manager_dir = root / LOCK.parent

    # Existing agent instructions and third-party skills are entirely project-owned.
    for directory in (agents, skills_dir):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise SetupError(f"Unsafe existing agent directory: {directory}")
    if manager_dir.exists() or manager_dir.is_symlink():
        raise SetupError("BMForge management directory already exists; use 'add' for managed projects")
    for name in names:
        path = skills_dir / name
        if path.exists() or path.is_symlink():
            raise SetupError(f"Skill already exists; refusing overwrite: {path}")

    # Read and validate every selected bundle before touching the destination.
    with source_checkout(args.source) as (source, revision):
        bundles = {name: bundle(source, name) for name in names}
        versions = {name: spec_version(source, name) for name in names}
        manager_source = (source / "skills/bmforge/scripts/manage.py").read_bytes()

    created_directories = []
    created_bundles = []
    try:
        for directory in (agents, skills_dir, manager_dir):
            if not directory.exists():
                directory.mkdir()
                created_directories.append(directory)
        for name, files in bundles.items():
            target = skills_dir / name
            created_bundles.append(target)
            copy_bundle(target, files)
        (root / MANAGER).write_bytes(manager_source)
        write_json_atomic(root / LOCK, {
            "schema": 1,
            "mode": "attached",
            "repository": args.source or SOURCE_URL,
            "branch": SOURCE_BRANCH,
            "source_commit": revision,
            "manager_sha256": sha256(manager_source).hexdigest(),
            "skills": {name: {"spec_version": versions[name],
                               "sha256": fingerprint(files),
                               "source_commit": revision}
                       for name, files in bundles.items()},
        })
    except BaseException:
        (root / LOCK).unlink(missing_ok=True)
        (root / MANAGER).unlink(missing_ok=True)
        for directory in reversed(created_bundles):
            if directory.exists():
                shutil.rmtree(directory)
        for directory in reversed(created_directories):
            directory.rmdir()
        raise

    print(f"Attached {len(names)} pinned BMForge skill(s) from {revision[:12]}:")
    for name in names:
        print(f"  {name} ({versions[name]})")
    print("Existing AGENTS.md, application files, release tooling and Git branches were not changed.")
    print("Check pinned skills with: python3 .agents/bmforge/manage.py check --project .")
    print("Add further skills with: python3 .agents/bmforge/manage.py add --project . --components NAME")


def load_lock(root):
    try:
        value = json.loads((root / LOCK).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SetupError(f"Missing or invalid BMForge lock: {error}") from error
    if value.get("schema") != 1 or not isinstance(value.get("skills"), dict):
        raise SetupError("Unsupported BMForge lock format")
    if not (root / MANAGER).is_file():
        raise SetupError("Project-local BMForge manager is missing")
    return value


def start_add(args):
    root = project_root(args.project)
    lock = load_lock(root)
    names = selected_names(args.components)
    if not names:
        raise SetupError("Select at least one additional component")
    require_components(names, lock["skills"])
    present = sorted(set(names) & set(lock["skills"]))
    if present:
        raise SetupError("Already installed, will not overwrite: " + ", ".join(present))
    for name in names:
        if (root / ".agents/skills" / name).exists():
            raise SetupError(f"Untracked local skill path exists: {name}")
    with source_checkout(args.source or lock["repository"]) as (source, revision):
        bundles = {name: bundle(source, name) for name in names}
        versions = {name: spec_version(source, name) for name in names}
    created = []
    try:
        for name, files in bundles.items():
            target = root / ".agents/skills" / name
            copy_bundle(target, files)
            created.append(target)
        for name, files in bundles.items():
            lock["skills"][name] = {"sha256": fingerprint(files),
                                    "spec_version": versions[name],
                                    "source_commit": revision}
        # Each component's local fingerprint is authoritative even when added later.
        write_json_atomic(root / LOCK, lock)
    except BaseException:
        for path in created:
            shutil.rmtree(path)
        raise
    for name in names:
        print(f"ADDED {name} ({versions[name]}) at source revision {revision[:12]}")
    print("Existing installed skills were not modified.")


def local_update_source(explicit, recorded):
    """Find a clean, committed BMForge checkout without network access."""
    candidate = explicit or os.environ.get("BMFORGE_SOURCE")
    if not candidate and isinstance(recorded, str) and Path(recorded).is_dir():
        candidate = recorded
    source = (Path(candidate).expanduser() if candidate else DEFAULT_SOURCE_CACHE).resolve()
    if not source.is_dir():
        raise SetupError(
            f"Local BMForge source unavailable: {source}. "
            "Create or refresh a checkout separately, or set BMFORGE_SOURCE/--source"
        )
    if Path(git("rev-parse", "--show-toplevel", cwd=source)).resolve() != source:
        raise SetupError(f"BMForge source must be a Git repository root: {source}")
    if git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=source) != SOURCE_BRANCH:
        raise SetupError(f"BMForge source must be on {SOURCE_BRANCH}: {source}")
    if git("status", "--porcelain", "--untracked-files=all", cwd=source):
        raise SetupError(f"BMForge source has local changes: {source}; use a clean dedicated checkout")
    return source


def local_pin_integrity(root, lock):
    """Check installed skill/manager hashes without Git, network or mutations."""
    modified = []
    for name, installed in sorted(lock["skills"].items()):
        directory = root / ".agents/skills" / name
        try:
            if fingerprint(installed_bundle(directory)) != installed["sha256"]:
                modified.append(name)
        except (OSError, SetupError):
            modified.append(name)
    manager = root / MANAGER
    manager_changed = (not manager.is_file() or manager.is_symlink()
                       or sha256(manager.read_bytes()).hexdigest() != lock["manager_sha256"])
    return modified, manager_changed


def start_verify(args):
    """Verify only local pins, even in an app that prohibits every Git command."""
    root = Path(args.project).expanduser().resolve()
    if not root.is_dir():
        raise SetupError(f"Project directory does not exist: {root}")
    lock = load_lock(root)
    modified, manager_changed = local_pin_integrity(root, lock)
    for name in modified:
        print(f"LOCALLY MODIFIED {name}: installed snapshot differs from the lock; nothing changed")
    if manager_changed:
        print("LOCALLY MODIFIED manager: pinned script differs from the lock")
    if not modified and not manager_changed:
        print("All local BMForge pins have valid hashes.")
    print("Integrity only: no Git commands, network requests, update checks or writes.")
    return 1 if modified or manager_changed else 0


def start_check(args):
    root = project_root(args.project)
    lock = load_lock(root)
    modified, manager_changed = local_pin_integrity(root, lock)
    for name in modified:
        print(f"LOCALLY MODIFIED {name}: installed snapshot differs from the lock; nothing changed")
    if manager_changed:
        print("LOCALLY MODIFIED manager: pinned update-check script differs from the lock")
    try:
        local_source = local_update_source(args.source, lock.get("repository"))
        with source_checkout(local_source) as (source, revision):
            print(f"LOCAL SOURCE {revision[:12]} ({source}); no network request. Refresh separately to check newer upstream changes.")
            available = []
            for name, installed in sorted(lock["skills"].items()):
                new = bundle(source, name)
                if fingerprint(new) != installed["sha256"]:
                    new_version = spec_version(source, name)
                    available.append(name)
                    print(f"UPDATE AVAILABLE {name}: installed {installed['spec_version']}, "
                          f"available {new_version} ({revision[:12]})")
                elif name not in modified:
                    print(f"CURRENT {name}: {installed['spec_version']}")
            script = (source / "skills/bmforge/scripts/manage.py").read_bytes()
            if sha256(script).hexdigest() != lock["manager_sha256"]:
                available.append("manager")
                print(f"UPDATE AVAILABLE manager: available in {revision[:12]}")
    except (SetupError, OSError, subprocess.TimeoutExpired) as error:
        print(f"UPDATE CHECK UNAVAILABLE: {error}; installed skills were not changed", file=sys.stderr)
        return 2
    if available:
        print("User approval required for any upgrade. No updates were applied.")
    elif not modified and not manager_changed:
        print("All pinned BMForge skills are current against the local source snapshot. No files were changed.")
    return 1 if modified or manager_changed else 0


def ref_exists(root, reference):
    """Check an exact Git ref without interpreting its name as a pattern."""
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", reference],
        cwd=root, capture_output=True, text=True, timeout=90,
    )
    if result.returncode not in (0, 1):
        raise SetupError(f"Cannot inspect Git ref {reference}: {result.stderr.strip()}")
    return result.returncode == 0


def start_setup_branches(args):
    """Create local release branches after the user's reviewed initial commit."""
    root = project_root(args.project)
    lock = load_lock(root)
    if lock.get("mode") == "attached":
        raise SetupError("Branch setup is for new BMForge projects, not attached repositories")
    main = "main"
    feature = args.feature
    if feature in (main, "dev") or not feature.startswith("feat/"):
        raise SetupError("Use a distinct feat/ branch name for the first feature")
    git("check-ref-format", "--branch", feature, cwd=root)
    if not ref_exists(root, "refs/heads/main"):
        raise SetupError("Commit the bootstrap scaffold on a local main branch before setting up release branches")
    if git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=root) != main:
        raise SetupError("Switch to local main before setting up release branches")
    if git("status", "--porcelain", "--untracked-files=all", cwd=root):
        raise SetupError("Commit or stash all project changes before setting up release branches")
    for name in ("dev", feature):
        if ref_exists(root, f"refs/heads/{name}"):
            raise SetupError(f"Local {name} already exists; inspect existing branches instead of overwriting")
        if ref_exists(root, f"refs/remotes/origin/{name}"):
            raise SetupError(f"origin/{name} already exists; inspect and track it instead of creating a divergent branch")
    if args.dry_run:
        print(f"READY to create local dev and {feature} from main. Nothing changed.")
        return
    git("branch", "dev", "main", cwd=root)
    try:
        git("switch", "-c", feature, "dev", cwd=root)
    except (SetupError, OSError, subprocess.TimeoutExpired):
        # Both names were absent at preflight. Roll back only new local refs.
        if ref_exists(root, f"refs/heads/{feature}"):
            git("branch", "-D", feature, cwd=root)
        git("branch", "-D", "dev", cwd=root)
        raise
    print(f"Created local dev and {feature} at the initial main commit.")
    print("No commit, remote branch, tag or push was created by this command.")


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("init", "attach", "add", "check", "verify", "setup-branches"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--project", default=".", help="Existing Git repository root")
        if action in ("init", "attach", "add", "check"):
            cmd.add_argument("--source", help="BMForge checkout or Git remote (default: published main)")
        if action in ("init", "attach", "add"):
            cmd.add_argument("--components", default="", help="Comma-separated component skill names")
        if action == "init":
            cmd.add_argument("--name", required=True, help="Canonical application class name, e.g. SnakeLab")
            cmd.add_argument("--subtype", default="Application", help="CMDB application subtype")
        if action == "setup-branches":
            cmd.add_argument("--feature", default="feat/maint-0.1.0",
                             help="Initial feature branch (default: feat/maint-0.1.0)")
            cmd.add_argument("--dry-run", action="store_true",
                             help="Validate branch setup without writing refs")
    args = parser.parse_args(argv)
    try:
        return {"init": start_init, "attach": start_attach,
                "add": start_add, "check": start_check, "verify": start_verify,
                "setup-branches": start_setup_branches}[args.action](args) or 0
    except (SetupError, OSError, subprocess.TimeoutExpired) as error:
        print(f"BMForge: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
