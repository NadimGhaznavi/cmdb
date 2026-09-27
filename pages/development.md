---
title: Site Development
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

## Editing

GitHub Pages builds the site. Edit Markdown pages and `_config.yml` in the
checkout; local Jekyll builds and Ruby dependencies are not part of this workflow.

The theme is `NadimGhaznavi/minimal-mistakes`. Changes to its neighboring local
checkout take effect after they are published to the remote theme and GitHub
Pages rebuilds this site.

## Check changes

```sh
bash -n scripts/new-release.sh
```

Check YAML front matter, confirm internal link targets exist, and ensure every
documentation page is reachable from `index.md`. Check rendered titles, tables,
code blocks, sidebar, and links on the published site after the Pages build.

## Publication

The maintainer manages GitHub Pages settings and the custom domain. Configure
Pages to publish this Jekyll site from the repository's `main` branch and root
folder. Keep `CNAME` and `_config.yml`'s `url` consistent with
`cmdb.osoyalce.com`.

The [release script]({{ site.baseurl }}{% link pages/releases.md %}) pushes the
release to `main`. With branch-based Pages publishing configured, that push
triggers the site build. Confirm the Pages build succeeds and check the live
homepage and documentation links after publication.
