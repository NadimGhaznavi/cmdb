---
title: Multilingual Documentation
lang: en
locale: en-US
language_name: English
translation_key: bmforge-multilingual-documentation
---

**This page governs static Jekyll documentation, not application runtime localization.** For all new application's interface and CLI messages, see [Application Localization]({{ site.baseurl }}{% link pages/component-localization.md %}), which prepares stable keys and an English source catalogue from the first release.

Translate documentation only after the project is complete, when its interface and content have settled. During development, prepare the English metadata and configuration using [Jekyll Setup]({{ site.baseurl }}{% link pages/jekyll-setup.md %}). This avoids maintaining translations while the project is still evolving.

## Organize the Translations

The theme provides the language selector and browser-language matching. Keep this behavior in the shared theme; no project-specific JavaScript, copied theme layouts, or translation plugin is needed for documentation pages. Enabling the setting does not translate content: maintain each translation as a separate Markdown file.

Follow the blog's directory convention: English at the root and translated content under a language directory. For Simplified Chinese, use `zh-CN/index.md` for the translated homepage and `zh-CN/pages/` for translated guides. Reuse images from `pages/images/` unless an image itself needs translation. Add other languages using their own language directories.

## Pair the Pages

For every page, including the homepage:

- Set `lang` to the content language, such as `en` or `zh-CN`.
- Set `locale` for the theme's UI text, such as `en-US` or `zh-CN`.
- Set `language_name` to the label shown in the selector, such as `English` or `简体中文`.
- Give all translations of that page the same stable `translation_key`. Use a different key for each distinct page and only one file per language for each key.
- Give each translation a distinct URL. Keep the English URL stable and prefix translated URLs with the language code.

For example, an English guide at `pages/guide.md` starts with:

```yaml
---
title: "Project Guide"
lang: en
locale: en-US
language_name: English
translation_key: __PROJECT_SLUG__-guide
permalink: /pages/guide/
---
```

Its Simplified Chinese counterpart at `zh-CN/pages/guide.md` starts with:

```yaml
---
title: "项目指南"
lang: zh-CN
locale: zh-CN
language_name: 简体中文
translation_key: __PROJECT_SLUG__-guide
permalink: /zh-CN/pages/guide/
---
```

## Translate the Homepage and Navigation

For `zh-CN/index.md`, use the English homepage's `translation_key`, Chinese language metadata, `layout: single`, and `permalink: /zh-CN/`. Translate the overview and navigation. Use `layout: single` for documentation homepages; the blog's custom translated post listing is specific to its blog layout.

{% raw %}
Translated guides should link back to their language's homepage, for example `[文档首页]({{ site.baseurl }}{% link zh-CN/index.md %})`. Link to translated guides where available. If a target only exists in English, link to it with an English-language label. Keep commands, code identifiers, configuration keys, and shared asset paths unchanged when translating explanatory text.
{% endraw %}

## Maintain Published Translations

Once translations are published, keep them current with subsequent source changes. Include the English version of every translated page so the default fallback exists. The selector lists only the translations present for the current page; there is no separate language registry to maintain.

## Verify the Translations

- Check each page's language metadata, unique `(translation_key, lang)` pair, and distinct URL.
- Verify that every translated page has an English counterpart and is reachable from its language's index.
- After publishing, check the language selector, direct translated URLs, localized navigation, and browser-language selection. A manual selection uses the `mm_lang` URL parameter; test automatic matching without that parameter. An unmatched browser language should fall back to English.

---

[Back]({{ site.baseurl }}{% link index.md %})
