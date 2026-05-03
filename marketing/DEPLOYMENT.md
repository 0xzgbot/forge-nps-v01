# Marketing Site Deployment

The Forge NPS marketing site is a static website in this folder.

## Recommended Free Host

Use Cloudflare Pages.

Cloudflare Pages works well here because the site is plain HTML, CSS, JavaScript, and local image assets. No build step is required.

## Cloudflare Pages Settings

| Setting | Value |
| --- | --- |
| Project type | Pages |
| Repository | `0xzgbot/forge-nps-v01` |
| Production branch | `master` |
| Build command | Leave blank |
| Build output directory | `marketing` |
| Root directory | Repository root |

Cloudflare will serve:

```text
marketing/index.html
```

as the public site root.

## Local Preview

Open the HTML file directly:

```text
/Users/zgbot/Desktop/forge_nps_v01/marketing/index.html
```

Or serve it from the repository root:

```bash
python3 -m http.server 8080
```

Then open:

```text
http://localhost:8080/marketing/
```

## Included Pages

| File | Purpose |
| --- | --- |
| `index.html` | Public marketing landing page. |
| `app-ui.html` | High-fidelity app UI concept / demo surface. |
| `assets/` | Generated website imagery. |

## Notes

- The site has no backend dependency.
- The site does not modify the Forge dashboard or Hermes pipeline.
- GitHub will show HTML files as source code unless the site is published through Pages, Cloudflare Pages, Netlify, or another static host.
