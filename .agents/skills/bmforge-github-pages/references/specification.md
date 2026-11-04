---
title: Project GitHub Pages Standard
lang: en
locale: en-US
language_name: English
translation_key: bmforge-project-setup
component_id: "bmforge.github-pages"
spec_version: "0.1.0"
spec_status: "draft"
---

**Component ID:** `{{ page.component_id }}` · **Specification:** `{{ page.spec_version }}` ({{ page.spec_status }})

Create project documentation sites from one canonical scaffold. The project owns
its configuration, content and logo; the shared theme owns presentation. This
standard consolidates the existing BMGeoIP/BMDynIP conventions and is packaged
as the optional `bmforge-github-pages` skill. It has no HTTP or Git component
prerequisite and adds no application service.

## Contents

- [Scaffold and skill resources](#scaffold-and-skill-resources)
- [Configure the site](#configure-the-site)
- [Shared styling and logo](#shared-styling-and-logo)
- [Documentation structure and titles](#documentation-structure-and-titles)
- [Approved runtime modules](#approved-runtime-modules)
- [Traceability](#traceability)
- [Acceptance checks](#acceptance-checks)

## Scaffold and skill resources

Select the skill through [BMForge]({{ site.baseurl }}{% link pages/codex-skills.md %})
for a new or existing project. Installation pins the resources without changing
the project's site. After implementation is authorized, use the installed
`assets/` files and `references/` guides; no live BMForge checkout is required.

| Canonical source | Installed skill asset | Project destination |
| --- | --- | --- |
| `templates/_config.yml` | `assets/_config.yml` | `_config.yml` |
| `templates/jekyll-gh-pages.yml` | `assets/jekyll-gh-pages.yml` | `.github/workflows/jekyll-gh-pages.yml` |
| `templates/github-pages/index.md` | `assets/index.md` | `index.md` |
| `templates/github-pages/README.md` | `assets/README.md` | `README.md` |
| `templates/github-pages/page.md` | `assets/page.md` | Each required guide under `pages/` |

The [configuration template]({{ '/templates/_config.yml' | relative_url }})
contains the settings used by these project sites, without the unused upstream
comment, search, social-provider and pagination configuration blocks. Add a
setting only for a project requirement. Keep the project's actual content,
translations and required overrides when adopting this standard on an existing
site; do not replace them with template text.

## Configure the site

Replace every placeholder using established project values. Quote YAML scalars
correctly, including values containing quotes, backslashes or newlines.

| Placeholder | Value |
| --- | --- |
| `__PROJECT_SLUG__` | Repository name; also the MyCount site identifier |
| `__PROJECT_TITLE__` | Human-readable project name |
| `__PROJECT_DESCRIPTION__` | One sentence describing the project |
| `__GITHUB_OWNER__` | Owner or organization from the Git remote |
| `__SITE_HOST__` | Published hostname, without protocol or path |
| `__SITE_BASEURL__` | Empty for a custom domain or user site; `/repository-name` for a project site |
| `__PROJECT_LOGO__` | Required existing logo path under `/pages/images/` |
| `__AUTHOR_NAME__` | Owner's display name |
| `__AUTHOR_LOCATION__`, `__AUTHOR_EMAIL__` | Public author details; empty if omitted |
| `__AUTHOR_WEBSITE__` | Author's website; remove its link entry if unused |
| `__START_YEAR__` | Year the project began |
| `__PAGE_TITLE__`, `__PAGE_KEY__` | Guide title and stable key suffix; used only in the page template |

Derive identity from the project brief and Git remote, following
[CMDB Compliance]({{ site.baseurl }}{% link pages/cmdb-compliance.md %}) when
applicable. Use the project's established domain and public author details;
obtain missing values from the owner instead of guessing them.

| Publication | `url` | `baseurl` | `CNAME` |
| --- | --- | --- | --- |
| Custom subdomain | `https://project.osoyalce.com` | `""` | Established hostname |
| GitHub project site | `https://owner.github.io` | `/repository-name` | Omit |
| GitHub user/organization site | `https://owner.github.io` | `""` | Omit |

Keep the canonical exclude list and add the application's actual source/package
and tooling directories. Site output should contain documentation and its
assets. Do not exclude the guides, logo or linked changelog.

## Shared styling and logo

Use `NadimGhaznavi/minimal-mistakes`, skin `dark`, documentation layout `single`,
`classes: wide` and `author_profile: true`. Keep the shared MyCount endpoint
`https://count.osoyalce.com/count` with the project's own identifier. Retain
Kramdown/GFM, Rouge, compressed Sass and the template's plugin list.

Keep shared typography, colors, spacing, sidebar and responsive behavior in the
remote theme. Do not copy theme layouts or styles into every project. Add local
CSS, layouts or JavaScript only for an explicit project requirement. The pinned
skill contains the instructions and scaffold; the existing shared remote theme
continues to supply presentation at GitHub build time.

Every project site **must include its own logo** under `pages/images/`. Reuse the
supplied or established logo, preserve its aspect ratio and transparency, and
check that it is legible against the dark theme. Set `_config.yml`'s `logo` to
that file and use the same setting for the homepage image:

{% raw %}
```liquid
![{{ site.title }} logo]({{ site.logo | relative_url }})
```
{% endraw %}

Do not substitute another project's branding or an empty logo setting. If the
asset is missing, obtain it before declaring the site ready to publish.

## Documentation structure and titles

Use `index.md` as the sole documentation entry point, English guides under
`pages/`, and shared images under `pages/images/`. Keep `README.md` to a short
overview and the published website link. The scaffold creates no speculative
guides: add only the pages the project needs and link every guide from the index.

Give each page a front-matter `title`, `lang: en`, `locale: en-US`,
`language_name: English` and stable, unique `translation_key`. The homepage
uses `permalink: /`. A guide inherits the shared layout, width and sidebar.
**Do not repeat the front-matter title as a body `#` heading:** the theme
already renders it. README has no front matter and may use a normal H1.

{% raw %}
Use `{{ site.baseurl }}{% link pages/installation.md %}` for an existing guide
and `{{ '/pages/images/example.png' | relative_url }}` for an image. Do not
hard-code root-relative asset or page URLs that break under a project baseurl.
Every guide includes `[Documentation index]({{ site.baseurl }}{% link index.md %})`.
{% endraw %}

Enable multilingual support with English (`en`) as default during setup. Add
English metadata and stable translation keys now; create translations only when
requested after content settles. Follow
[Multilingual Documentation]({{ site.baseurl }}{% link pages/multilingual-documentation.md %}).

## Approved runtime modules

This is a static documentation/build contract. It adds no Python runtime module,
HTTP listener, database or health endpoint. Use the existing GitHub Jekyll build,
the shared remote theme and plugins listed in the canonical configuration. Do
not add a Gemfile, local Jekyll requirement, frontend framework or replacement
theme without an explicit requirement and owner approval. Application runtime
localization remains separate.

## Traceability

Retain `# BMFORGE_COMPONENT: bmforge.github-pages; spec_version: 0.1.0` in
`_config.yml`. This comment identifies the adopted contract without creating a
Python module. The skill lock pins its specification and scaffold fingerprints;
static scanning of YAML component comments is not implemented.

## Acceptance checks

1. Install with `init`, `attach` or `add`; verify the specification, publishing
   and multilingual guides, configuration, workflow and Markdown assets are
   bundled offline. Attachment preserves the site's bytes and existing pins;
   no HTTP/Git runtime component is implicitly selected.
2. Replace all scaffold placeholders. Parse YAML/front matter; check identity,
   MyCount slug, repository, hostname and baseurl. Verify only actual project
   source/tool directories are excluded, with required site assets included.
3. Confirm the required logo exists and both masthead and homepage reference
   that asset. Check aspect ratio, transparency and dark-background legibility.
4. Check index-to-guide and guide-to-index links, image targets, English metadata
   and unique translation keys. Check no front-matter title is repeated as a
   body H1. Verify URLs for the chosen custom-domain or project-subpath setup.
5. Verify the workflow publishes only `main`, including manual runs; it builds
   the root, uploads the artifact, and deploys after the build. Keep generated
   site output and local Jekyll caches ignored.
6. After an authorized publication, verify both Actions jobs, HTTPS, the domain,
   homepage, guides, logo, dark styling, wide layout, sidebar and mobile view.
   Verify MyCount uses the correct site identifier. If translations exist,
   verify the theme's language selector and translated navigation.

Follow [GitHub Pages Publishing]({{ site.baseurl }}{% link pages/github-pages-publishing.md %})
for settings, domain and deployment checks. Report file preparation separately
from publication; identify any checks that could not run.

---

[Back]({{ site.baseurl }}{% link index.md %})
