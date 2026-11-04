---
title: GitHub Pages Publishing
lang: en
locale: en-US
language_name: English
translation_key: bmforge-github-pages-publishing
---

Publish a project's Jekyll documentation site from `main` using GitHub Actions. Prepare the site files with the [Project GitHub Pages Standard]({{ site.baseurl }}{% link pages/jekyll-setup.md %}) first. The `bmforge-github-pages` skill bundles this guide and the workflow for offline use.

## Add the Publishing Workflow

Copy the [workflow template]({{ '/templates/jekyll-gh-pages.yml' | relative_url }}) (installed as `assets/jekyll-gh-pages.yml`) to `.github/workflows/jekyll-gh-pages.yml`. It builds the repository root and deploys on pushes to `main`, with a manual trigger available. The build's branch condition also skips manual runs from development and feature branches, so only `main` publishes.

In the repository's **Settings → Pages**, select **GitHub Actions** as the publishing source. The workflow includes the required permissions, artifact upload, and `github-pages` deployment environment. See [GitHub's custom workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

## Configure the Domain

For a custom subdomain:

1. Set the hostname in the repository's Pages settings.
2. Configure a DNS `CNAME` record pointing that hostname to `<github-owner>.github.io`, without a repository path.
3. Enable **Enforce HTTPS** when available.
4. Add a root `CNAME` file containing only the hostname to follow the existing projects' convention.

The repository `CNAME` file records the hostname; GitHub Actions publishing uses the domain configured in Pages settings. See [GitHub's custom domain instructions](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site). For a default GitHub Pages URL, omit `CNAME` and set `url` and `baseurl` accordingly.

## Keep Builds on GitHub

GitHub Pages builds the site. Do not add a Gemfile, require a local Jekyll build, or commit generated `_site/` output. Add `_site/`, `.jekyll-cache/`, and `.jekyll-metadata` to the project's `.gitignore`.

## Verify the Deployment

- After an authorized push to `main`, verify that the build and deployment jobs succeed.
- Open the published homepage and documentation pages; check the dark theme, wide content, sidebar, required project logo, links, mobile view, and HTTPS. Check the MyCount site identifier and language selector when translations exist.

Report file preparation and publication verification separately. If repository settings, DNS access, or a deployment are unavailable, identify the remaining work rather than marking the site setup complete.

---

[Back]({{ site.baseurl }}{% link index.md %})
