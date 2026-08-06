"""Domain router: assets — mounts cinesmith_dashboard handlers + multi-upload (F2) + package→identity (F4)."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel


class AttachCampaignIdentityRequest(BaseModel):
    """Attach Asset Vault package continuity to a Hermes campaign identity pack."""

    campaign_id: str = ""
    copy_reference_assets: bool = True


def build_assets_router():
    """Build router after cinesmith_dashboard handlers are defined."""
    from dashboard import cinesmith_dashboard as d
    from core.character.identity_attach import build_identity_pack_from_vault_package
    from core.character.reference_upload import save_asset_vault_reference_bytes

    router = APIRouter(tags=["assets"])
    router.add_api_route("/api/banks", d.api_banks, methods=["GET"])
    router.add_api_route("/api/banks", d.api_save_banks, methods=["POST"])
    router.add_api_route("/api/build-recipe", d.api_build_recipe, methods=["POST"])
    router.add_api_route("/api/products", d.api_get_products, methods=["GET"])
    router.add_api_route(
        "/api/asset-vault/packages", d.api_asset_vault_packages, methods=["GET"]
    )
    router.add_api_route(
        "/api/asset-vault/packages/{package_id}",
        d.api_asset_vault_get_package,
        methods=["GET"],
    )
    router.add_api_route(
        "/api/asset-vault/verify-frame", d.api_asset_vault_verify_frame, methods=["POST"]
    )
    router.add_api_route(
        "/api/asset-vault/packages", d.api_asset_vault_create_package, methods=["POST"]
    )
    router.add_api_route(
        "/api/asset-vault/packages/{package_id}",
        d.api_asset_vault_update_package,
        methods=["PUT"],
    )
    router.add_api_route(
        "/api/asset-vault/packages/{package_id}",
        d.api_asset_vault_delete_package,
        methods=["DELETE"],
    )
    router.add_api_route(
        "/api/asset-vault/packages/{package_id}/duplicate",
        d.api_asset_vault_duplicate_package,
        methods=["POST"],
    )
    router.add_api_route(
        "/api/asset-vault/packages/{package_id}/references/upload",
        d.api_asset_vault_upload_reference,
        methods=["POST"],
    )
    router.add_api_route(
        "/api/asset-vault/packages/{package_id}/characters/{char_id}",
        d.api_asset_vault_add_character,
        methods=["POST"],
    )
    router.add_api_route(
        "/api/asset-vault/packages/{package_id}/characters/{char_id}",
        d.api_asset_vault_remove_character,
        methods=["DELETE"],
    )

    # --- F2: multi-file Asset Vault reference upload ---
    async def api_asset_vault_upload_references_batch(
        package_id: str,
        files: List[UploadFile] = File(...),
        asset_type: str = Form("reference"),
        name: str = Form(""),
        prompt: str = Form(""),
    ):
        """
        Upload one or many reference assets into a vault package.

        Form field: files (multi). Stored under MEDIA_ROOT/asset_vault/{package_id}/
        and appended to package.references.
        """
        if not files:
            raise HTTPException(status_code=400, detail="At least one file is required")

        packages = d._list_asset_vault_packages()
        pid = d._asset_slug(package_id)
        target = None
        for pkg in packages:
            if pkg.get("id") == pid:
                target = pkg
                break
        if not target:
            raise HTTPException(
                status_code=404, detail=f"Asset Vault package not found: {package_id}"
            )

        records = []
        errors = []
        name_prefix = (name or "").strip()
        for idx, upload in enumerate(files):
            try:
                content = await upload.read()
                if not content:
                    errors.append(
                        {
                            "filename": upload.filename or f"file_{idx}",
                            "error": "empty file",
                        }
                    )
                    continue
                stem = Path(upload.filename or f"asset_{idx}").stem
                if name_prefix and len(files) > 1:
                    display_name = f"{name_prefix} {idx + 1}"
                elif name_prefix:
                    display_name = name_prefix
                else:
                    display_name = stem or f"Asset {idx + 1}"

                ref, out_path = save_asset_vault_reference_bytes(
                    package_id=pid,
                    filename=upload.filename or f"asset_{idx}.bin",
                    content=content,
                    media_root=d.MEDIA_ROOT,
                    asset_type=asset_type,
                    name=display_name,
                    prompt=prompt,
                )
                ref["url"] = d._media_url_for_path(out_path)
                ref.pop("path", None)
                records.append(ref)
            except Exception as exc:
                errors.append(
                    {
                        "filename": getattr(upload, "filename", None) or f"file_{idx}",
                        "error": str(exc),
                    }
                )

        if not records and errors:
            raise HTTPException(
                status_code=400,
                detail={"message": "All uploads failed", "errors": errors},
            )

        refs = d._normalize_vault_references(target.get("references"))
        refs.extend(records)
        target["references"] = refs
        target["updated_at"] = d._now_iso()
        normalized = [d._normalize_asset_vault_package(item) for item in packages]
        d._write_asset_vault_packages(normalized)
        package = next(item for item in normalized if item.get("id") == pid)
        return {
            "status": "ok",
            "package": package,
            "uploaded": records,
            "uploaded_count": len(records),
            "errors": errors,
        }

    # --- F4: one-click package → campaign identity ---
    async def api_asset_vault_attach_campaign_identity(
        package_id: str,
        req: Optional[AttachCampaignIdentityRequest] = None,
    ):
        """
        Attach this Asset Vault package's continuity lock to a campaign identity pack.

        Default campaign is the active Hermes campaign (or first known campaign).
        Optionally copies local image references into the campaign identity asset folder.
        """
        body = req or AttachCampaignIdentityRequest()
        package = d._asset_vault_package_by_id(package_id)
        if not package:
            raise HTTPException(
                status_code=404, detail=f"Asset Vault package not found: {package_id}"
            )

        cid = (body.campaign_id or "").strip()
        if not cid:
            cid = (d._ACTIVE_CAMPAIGN or "").strip()
        if not cid:
            try:
                campaigns = await d.api_get_campaigns()
                items = campaigns.get("campaigns") if isinstance(campaigns, dict) else None
                if isinstance(items, list) and items:
                    cid = str(items[0].get("campaign_id") or "").strip()
            except Exception:
                cid = ""
        if not cid:
            raise HTTPException(
                status_code=400,
                detail=(
                    "campaign_id is required when no active Hermes campaign is selected. "
                    "Pass campaign_id or start/select a campaign first."
                ),
            )

        anchor_ids: List[str] = []
        copied_assets: List[dict] = []
        if body.copy_reference_assets:
            for ref in package.get("references") if isinstance(package.get("references"), list) else []:
                if not isinstance(ref, dict):
                    continue
                url = str(ref.get("url") or "").strip()
                if not url:
                    continue
                try:
                    local = (
                        d._resolve_image_path(url)
                        if hasattr(d, "_resolve_image_path")
                        else None
                    )
                    if local is None or not local.exists():
                        continue
                    asset_id = uuid.uuid4().hex[:12]
                    safe_cid = d._safe_campaign_name(cid)
                    out_dir = d._campaign_asset_dir(safe_cid)
                    out_dir.mkdir(parents=True, exist_ok=True)
                    ext = Path(local.name).suffix.lower() or ".png"
                    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
                        ext = ".png"
                    file_name = f"{asset_id}{ext}"
                    dest = out_dir / file_name
                    dest.write_bytes(local.read_bytes())
                    meta = {
                        "asset_id": asset_id,
                        "campaign_id": safe_cid,
                        "file_name": file_name,
                        "role": "anchor",
                        "active": True,
                        "priority": int(time.time()),
                        "created_at": d._now_iso(),
                        "source_package_id": package.get("id"),
                        "source_reference_id": ref.get("id"),
                    }
                    (out_dir / f"{asset_id}.json").write_text(
                        json.dumps(meta, ensure_ascii=True, indent=2),
                        encoding="utf-8",
                    )
                    anchor_ids.append(asset_id)
                    copied_assets.append(
                        {
                            "asset_id": asset_id,
                            "role": "anchor",
                            "src": f"/identity-assets/{safe_cid}/{file_name}",
                            "source_reference_id": ref.get("id"),
                        }
                    )
                except Exception:
                    continue

        identity_pack = build_identity_pack_from_vault_package(
            package, anchor_image_ids=anchor_ids
        )
        set_req = d.CampaignIdentityRequest(
            campaign_id=cid,
            identity_pack=d.CampaignIdentityPack(**identity_pack),
        )
        result = await d.api_set_campaign_identity(set_req)
        return {
            "status": "ok",
            "campaign_id": cid,
            "package_id": package.get("id"),
            "package_name": package.get("name"),
            "identity_pack": result.get("identity_pack") or identity_pack,
            "copied_assets": copied_assets,
            "copied_count": len(copied_assets),
            "message": (
                f"Attached Asset Vault package '{package.get('name')}' "
                f"to campaign '{cid}' identity."
            ),
        }

    router.add_api_route(
        "/api/asset-vault/packages/{package_id}/references/upload-batch",
        api_asset_vault_upload_references_batch,
        methods=["POST"],
    )
    router.add_api_route(
        "/api/asset-vault/packages/{package_id}/attach-campaign-identity",
        api_asset_vault_attach_campaign_identity,
        methods=["POST"],
    )
    return router
