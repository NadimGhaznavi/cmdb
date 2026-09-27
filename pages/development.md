---
title: Site Development
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

## Local setup

Install Ruby, Bundler, and the build tools needed by Ruby gems. From the project
root, install the dependencies declared in `Gemfile`:

```sh
bundle config set --local path vendor/bundle
bundle install
```

The maintainer should commit the generated `Gemfile.lock` so local builds use
the same resolved dependencies. Repeat installation after dependency changes.

The initial dependency installation and remote theme download require network
access. The theme is `NadimGhaznavi/minimal-mistakes`; changes to its neighboring
local checkout do not automatically change this site's remote theme.

## Preview

```sh
bundle exec jekyll serve --host 127.0.0.1
```

Open `http://127.0.0.1:4000` and follow the links from the homepage. Jekyll writes
generated files to `_site/`. Restart the preview after changing `_config.yml`.

## Check changes

```sh
bundle exec jekyll build --strict_front_matter
bash -n scripts/new-release.sh
```

The build checks Liquid link targets and reports front-matter errors. Inspect
the rendered pages for correct titles, tables, code blocks, sidebar, and links.
For changes to URL handling, also build with a project-site prefix:

```sh
bundle exec jekyll build --strict_front_matter --baseurl /cmdb
```

Internal links and assets should include `/cmdb` in that build. Run the normal
build again before inspecting output for the custom domain.

## Publication

The maintainer manages GitHub Pages settings and the custom domain. Configure
Pages to publish this Jekyll site from the repository's `main` branch and root
folder. Keep `CNAME` and `_config.yml`'s `url` consistent with
`cmdb.osoyalce.com`.

The [release script]({{ site.baseurl }}{% link pages/releases.md %}) pushes the
release to `main`. With branch-based Pages publishing configured, that push
triggers the site build. Confirm the Pages build succeeds and check the live
homepage and documentation links after publication.
