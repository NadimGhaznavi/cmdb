---
name: bmforge-github-pages
description: Create or standardize a project's GitHub Pages documentation site using the shared Minimal Mistakes theme, canonical Jekyll configuration, required project logo, Markdown scaffold and publishing workflow. Use for project website setup, branding, documentation layout or Pages publication. Independent of the application HTTP and Git components.
---

# Project GitHub Pages sites

Read `references/specification.md` and `references/engineering-contract.md`.
Use `references/github-pages-publishing.md` for publication and
`references/multilingual-documentation.md` when translations are requested.

- Observe the implementation authorization gate. Installing this skill pins
  instructions and templates; it does not authorize replacing site files,
  publishing, changing DNS or deploying. For an existing site, inspect its
  configuration, content and translations before applying the agreed changes.
- Copy `assets/_config.yml`, `assets/index.md`, `assets/README.md` and
  `assets/jekyll-gh-pages.yml` to the destinations in the specification.
  Use `assets/page.md` only for guides the project needs. Replace every
  placeholder with established project values, quoting YAML scalars correctly.
  Preserve existing content and project-specific settings when adopting the standard.
- Keep the shared `NadimGhaznavi/minimal-mistakes` theme, `dark` skin,
  `single` layout, wide content and author sidebar. Keep styling in the theme;
  add a local override only for an explicit project requirement. Do not add
  a frontend framework, copy the theme or require the application HTTP skill.
- Require the project's own logo under `pages/images/`. Point `logo` at that
  asset and render the homepage image with `site.logo | relative_url` so both
  uses agree. Preserve aspect ratio and transparency; do not substitute another
  project's logo or claim completion while the logo is missing.
- Use `index.md` as the documentation entry point, `pages/` for guides and
  `pages/images/` for images. Keep README short with the published website link.
  Use front-matter titles without a duplicate body H1, baseurl-aware internal
  links/images, English metadata and unique stable translation keys. Prepare
  multilingual support now; generate translations only when requested.
- Retain the shared MyCount endpoint with the project's own site identifier.
  Keep hostname, baseurl, repository and logo consistent; exclude the actual
  application source and tooling directories from the site output.
- Keep Jekyll builds on GitHub using the bundled workflow. Do not add a
  Gemfile, local Jekyll requirement or generated `_site/` files. Follow the
  publishing guide for Pages settings, custom domain, CNAME and HTTPS.
- Record `bmforge.github-pages` specification `0.1.0` in the configuration's
  source comment. Run the specification's file checks and report authorized
  deployment checks separately. Update the application's changelog for the change.
