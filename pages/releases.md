---
title: Release Management
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

Development happens on a feature branch. The maintainer reviews and commits
changes, then runs `scripts/new-release.sh` to cut a release. The project owner
performs Git operations and releases; the assistant prepares files and checks.

## Prepare branches

The script expects local `main`, `dev`, and feature branches. For a fresh
checkout with only `main`, the maintainer creates the initial branches once:

```sh
git switch -c dev
git switch -c feat/maint-0.1.0
```

Before releasing, commit all changes, bring local `main` and `dev` up to date,
and merge `dev` into the feature branch. Follow the source checks in
[Site development]({{ site.baseurl }}{% link pages/development.md %}), including:

```sh
bash -n scripts/new-release.sh
```

For server changes, run the Python tests described in
[CMDB server]({{ site.baseurl }}{% link pages/server.md %}).

Review `CHANGELOG.md`'s `Unreleased` section. The project version is the literal
`DCMDB.VERSION` in `cmdb/constants/DCMDB.py`; the release script reads and
updates this constant. The supplied release message also replaces
`DCMDB.CMDB_CODENAME` as a safely escaped Python string, without the
`Release <version>:` prefix used in commit and tag messages.

## Cut a release

The maintainer can inspect usage:

```sh
./scripts/new-release.sh --help
```

From the clean feature branch, choose the version and release message. For
example, the first release could be:

```sh
./scripts/new-release.sh 0.1.0 "Initial project foundation"
```

Use a semantic version without a leading `v`. An optional third argument sets
the next feature branch name. Git and Python 3 must be available.

The script checks the working tree, version, changelog, and branches,
then fetches remote refs and verifies branch ancestry. It displays the source
branch, tag, message, codename, next branch, and remote URL, and asks
`Create and push this release? [y/N]`. Confirmation requires an interactive
terminal; only `y` or `Y` proceeds. Any other response or end of input cancels
before changing release files, branches, or tags. The fetch happens before
confirmation so the checks use current remote refs.

It merges the feature branch into `dev`, updates `DCMDB.VERSION`,
`DCMDB.CMDB_CODENAME`, and `CHANGELOG.md`, commits the
release, merges into `main`, and creates an annotated tag such as `v0.1.0`.
It advances `dev` to `main`, atomically pushes `main`, `dev`, and the tag to
`origin`, then creates the next local feature branch, such as `feat/maint-0.1.1`.

Completed steps print `[ PASSED ]` in green; errors print `[ FAIL ]` in red;
cancellations and absent remote branches print `[ WARNING ]` in yellow.
Color is enabled for terminals, with plain text for redirected output, a
`dumb` terminal, or when `NO_COLOR` is set. Git's own output remains visible.

The script publishes Git changes. GitHub Pages handles the site build using
the repository's configured publishing source. Check its build result and
the live site after release. Deploy the Python server separately using the
[installation or upgrade command]({{ site.baseurl }}{% link pages/installation.md %});
publishing a release does not restart the server.

## Adapt the script to another project

Copy `scripts/new-release.sh` into the other project's `scripts/` directory
and edit its project settings block:

| Setting | Purpose |
| --- | --- |
| `project_name` | Name displayed in summaries and status messages |
| `version_file` | Python constants file, relative to the repository root |
| `version_constant`, `codename_constant` | Names of the version and codename assignments |
| `changelog_file` | Changelog path, relative to the repository root |
| `remote` | Git remote to fetch and push |
| `dev_branch`, `main_branch` | Development and release branch names |
| `feature_prefix` | Prefix for the next feature branch |
| `python_command` | Python 3 executable used to read and update constants |

Each configured constant must have exactly one assignment to a single-line
literal Python string. Type annotations are optional. The script reads the
file without importing project code and preserves comments, annotations, and
other contents when replacing the values. The changelog must contain exactly
one `## [Unreleased]` heading. Adaptations retain the confirmation and the same
feature-to-development-to-main release flow.

## If a release stops

The script stops at the first failed command and does not roll back completed
Git operations. Inspect the current branch, merge state, commits, and tags
before continuing. A failed push can leave a completed release locally; the
maintainer should resolve the cause and finish publishing those refs rather
than rerunning the full release command blindly.
