# Local Higgsfield-Compatible Adapter Research

Date: 2026-05-07

## Scope

This note captures the public Higgsfield MCP/API surface observed from official metadata and public wrapper repositories, then maps it to a Forge-local equivalent backed by ComfyUI. This is an interoperability layer, not a private Higgsfield clone.

## What The Public Surface Shows

The official hosted MCP endpoint is:

```text
https://mcp.higgsfield.ai/mcp
```

Unauthenticated calls return `401 Unauthorized`. The protected-resource metadata is public and advertises Bearer auth, `openid email offline_access` scopes, PKCE authorization-code flow for Claude-style clients, and a device-code option for clients that cannot receive redirects.

Public wrapper repositories expose a conventional async job API shape:

| Capability | Publicly observed shape |
| --- | --- |
| Text to image | `POST /v1/text2image/soul` with `params.prompt`, `width_and_height`, `quality`, `batch_size`, optional `style_id`, `style_strength`, `seed`, `custom_reference_id`, `image_reference` |
| Image to video | `POST /v1/image2video/dop` with `params.prompt`, `model`, `input_images[]`, optional `motions[]`, `input_images_end[]`, `seed` |
| Speech video | `POST /v1/speak/higgsfield` with prompt/image/audio options |
| Styles | `GET /v1/text2image/soul-styles` |
| Motions | `GET /v1/motions` |
| Character refs | `POST /v1/custom-references`, `GET/DELETE /v1/custom-references/{id}` |
| Job polling | `GET /v1/job-sets/{id}` |

The important abstraction is not the proprietary model. It is the tool contract: submit a creative job, return a job-set ID, poll until a result URL exists.

Sources:

- Official MCP protected-resource metadata: `https://mcp.higgsfield.ai/.well-known/oauth-protected-resource`
- Official OAuth metadata: `https://mcp.higgsfield.ai/.well-known/oauth-authorization-server`
- Public wrapper implementation: `https://github.com/geopopos/geo_higgsfield_ai_mcp`
- Public wrapper implementation: `https://github.com/geopopos/higgsfield_ai_mcp`

## Local Forge Mapping

Forge now exposes local compatibility endpoints:

| Local endpoint | Purpose |
| --- | --- |
| `GET /api/local-higgsfield/styles` | Local style presets for ad creative |
| `GET /api/local-higgsfield/motions` | Local motion presets mapped to LTX prompt language |
| `POST /api/local-higgsfield/generate-image` | Higgsfield Soul-like image request routed to Flux/ComfyUI |
| `POST /api/local-higgsfield/generate-video` | Higgsfield DoP-like image-to-video request routed to LTX/ComfyUI |
| `GET /api/local-higgsfield/jobs/{job_set_id}` | Poll local ComfyUI-backed job status |
| `POST /api/local-higgsfield/characters` | Store local character reference assets |
| `GET /api/local-higgsfield/characters` | List local character references |
| `GET /api/local-higgsfield/characters/{reference_id}` | Get a character reference |
| `DELETE /api/local-higgsfield/characters/{reference_id}` | Delete a character reference |

Data is stored under:

```text
~/Desktop/FORGE_NPS_MEDIA/local_higgsfield/
```

Results are served by the dashboard through `/media-assets/local_higgsfield/...`.

## Gaps Versus Real Higgsfield

The local adapter deliberately does not try to replicate private Higgsfield models. The achievable replacement is functional:

- Local image generation uses Forge text-to-image workflows.
- Local image-to-video uses Forge LTX image-to-video workflows.
- Style presets become prompt/compiler constraints.
- Motion presets become LTX motion instructions.
- Character references are stored as reusable local identity assets, not remote Soul custom-reference training jobs.
- Job sets mirror the async response shape, but the backend status source is ComfyUI history/queue.

## Affiliate Workflow Implication

For the affiliate automation idea, the Higgsfield dependency can be replaced as follows:

1. YouTube trend collector finds source patterns.
2. Local/Kimi/Gemini analysis writes a viral-pattern brief.
3. Offer scorer selects products.
4. `POST /api/local-higgsfield/generate-image` creates ad stills/thumbnails.
5. `POST /api/local-higgsfield/generate-video` animates winning frames.
6. Existing Forge campaign/memory/audit routes package and review output.
7. Hermes cron runs the workflow three times weekly.

The distribution bottleneck remains YouTube Shopping product tagging, which appears to require YouTube Studio or partner-level access rather than a public Data API endpoint.
