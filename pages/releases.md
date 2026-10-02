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
updates this constant.

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
the next feature branch name.

The script checks the working tree, version, changelog, and branches,
then fetches remote refs and verifies branch ancestry. It merges the
feature branch into `dev`, updates `DCMDB.VERSION` and `CHANGELOG.md`, commits the
release, merges into `main`, and creates an annotated tag such as `v0.1.0`.
It advances `dev` to `main`, atomically pushes `main`, `dev`, and the tag to
`origin`, then creates the next local feature branch, such as `feat/maint-0.1.1`.

The script publishes Git changes. GitHub Pages handles the site build using
the repository's configured publishing source. Check its build result and
the live site after release. Deploy the Python server separately using the
[installation or upgrade command]({{ site.baseurl }}{% link pages/installation.md %});
publishing a release does not restart the server.

## If a release stops

The script stops at the first failed command and does not roll back completed
Git operations. Inspect the current branch, merge state, commits, and tags
before continuing. A failed push can leave a completed release locally; the
maintainer should resolve the cause and finish publishing those refs rather
than rerunning the full release command blindly.
