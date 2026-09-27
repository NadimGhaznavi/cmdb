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
and merge `dev` into the feature branch. Install the dependencies described in
[Site development]({{ site.baseurl }}{% link pages/development.md %}), then check:

```sh
bundle exec jekyll build --strict_front_matter
bash -n scripts/new-release.sh
```

Review `CHANGELOG.md`'s `Unreleased` section. `VERSION` starts at `0.0.0` as an
unreleased baseline; it does not represent a published release.

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

The script checks the working tree, version, changelog, branches, and Jekyll
build, then fetches remote refs and verifies branch ancestry. It merges the
feature branch into `dev`, updates `VERSION` and `CHANGELOG.md`, commits the
release, merges into `main`, and creates an annotated tag such as `v0.1.0`.
It advances `dev` to `main`, atomically pushes `main`, `dev`, and the tag to
`origin`, then creates the next local feature branch, such as `feat/maint-0.1.1`.

The script publishes Git changes. GitHub Pages handles the site build using
the repository's configured publishing source. Check its build result and
the live site after release. No application deployment metadata or service
restarts are needed for this static site.

## If a release stops

The script stops at the first failed command and does not roll back completed
Git operations. Inspect the current branch, merge state, commits, and tags
before continuing. A failed push can leave a completed release locally; the
maintainer should resolve the cause and finish publishing those refs rather
than rerunning the full release command blindly.
