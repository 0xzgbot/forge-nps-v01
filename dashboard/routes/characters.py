"""Domain router: characters — mounts cinesmith_dashboard handlers + multi-upload (F2) + auto-sheet (F3)."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile


def build_characters_router():
    """Build router after cinesmith_dashboard handlers are defined."""
    from dashboard import cinesmith_dashboard as d
    from core.character.auto_sheet import (
        apply_photo_to_character,
        build_auto_sheet_prompt,
        build_auto_sheet_result,
        clamp_grid,
        draft_character_record,
        master_ref_from_upload,
        name_from_filename,
        pick_sheet_url_from_render,
        spark_recovery_hint,
    )
    from core.character.reference_upload import (
        merge_character_uploads,
        save_character_reference_bytes,
    )

    router = APIRouter(tags=["characters"])
    router.add_api_route("/api/identity/templates", d.api_list_identity_templates, methods=["GET"])
    router.add_api_route(
        "/api/identity/templates/{template_name}", d.api_save_identity_template, methods=["POST"]
    )
    router.add_api_route(
        "/api/identity/templates/{template_name}", d.api_get_identity_template, methods=["GET"]
    )
    router.add_api_route("/api/characters", d.api_get_characters, methods=["GET"])
    router.add_api_route(
        "/api/characters/{char_id}/profile", d.api_get_character_profile, methods=["GET"]
    )
    router.add_api_route(
        "/api/characters/{char_id}/variations", d.api_get_character_variations, methods=["GET"]
    )
    router.add_api_route(
        "/api/characters/{char_id}/export", d.api_export_character, methods=["GET"]
    )
    router.add_api_route("/api/characters/save-dna", d.api_save_character_dna, methods=["POST"])
    router.add_api_route(
        "/api/characters/{char_id}/profile", d.api_patch_character_profile, methods=["PATCH"]
    )
    router.add_api_route(
        "/api/characters/{char_id}/master-reference",
        d.api_add_character_master_reference,
        methods=["POST"],
    )
    router.add_api_route(
        "/api/characters/{char_id}/references",
        d.api_upload_character_reference,
        methods=["POST"],
    )
    router.add_api_route(
        "/api/characters/{char_id}/sheet-panels",
        d.api_extract_character_sheet_panels,
        methods=["POST"],
    )
    router.add_api_route(
        "/api/characters/{char_id}/lora-pack",
        d.api_prepare_character_lora_pack,
        methods=["POST"],
    )
    router.add_api_route(
        "/api/characters/reference/{char_id}/{filename}",
        d.api_character_reference_file,
        methods=["GET"],
    )
    router.add_api_route(
        "/api/characters/{char_id}/audit", d.api_audit_character_generation, methods=["POST"]
    )
    router.add_api_route(
        "/api/characters/{char_id}/benchmarks",
        d.api_get_character_benchmarks,
        methods=["GET"],
    )
    router.add_api_route(
        "/api/characters/{char_id}/export-package",
        d.api_export_character_package,
        methods=["GET"],
    )
    router.add_api_route(
        "/api/characters/role-prompt", d.api_character_role_prompt, methods=["POST"]
    )
    router.add_api_route(
        "/api/characters/spark-render", d.api_character_spark_render, methods=["POST"]
    )
    router.add_api_route("/api/characters/render", d.api_render_character, methods=["POST"])
    router.add_api_route(
        "/api/characters/anchor/{name}", d.api_character_anchor, methods=["GET"]
    )
    router.add_api_route("/api/characters", d.api_create_character, methods=["POST"])

    # --- F2: multi-file reference upload (self-contained handler) ---
    async def api_upload_character_references_batch(
        char_id: str,
        files: List[UploadFile] = File(...),
        reference_type: str = Form("auto"),
        notes: str = Form(""),
    ):
        """
        Upload one or many reference images/clips for a character.

        Form field: files (multi). Stored under data/character_banks/references/{char_id}/.
        """
        if not files:
            raise HTTPException(status_code=400, detail="At least one file is required")

        cid = d._character_slug(char_id)
        char = d._CHARACTERS_STORE.get(cid)
        if not char:
            raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")

        import time as _time

        records = []
        errors = []
        stamp = int(_time.time())
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
                rec = save_character_reference_bytes(
                    char_id=cid,
                    filename=upload.filename or f"ref_{idx}.jpg",
                    content=content,
                    banks_dir=d.CHARACTER_BANKS_DIR,
                    reference_type=reference_type,
                    notes=notes,
                    stamp=stamp + idx,
                )
                records.append(rec)
            except ValueError as exc:
                errors.append(
                    {
                        "filename": getattr(upload, "filename", None) or f"file_{idx}",
                        "error": str(exc),
                    }
                )
            except Exception as exc:  # pragma: no cover - defensive
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

        normalized = d._normalize_character(cid, char)
        merged = merge_character_uploads(normalized, records)
        saved = d._persist_normalized_character(cid, merged)
        return {
            "status": "ok",
            "character": saved,
            "uploaded": records,
            "uploaded_count": len(records),
            "errors": errors,
        }

    router.add_api_route(
        "/api/characters/{char_id}/references/batch",
        api_upload_character_references_batch,
        methods=["POST"],
    )

    # --- F3: auto character sheet from one photo ---

    def _truthy(value: object) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "yes", "on", "y"}

    def _next_accent() -> str:
        accents = ["cyan", "magenta", "amber", "green"]
        used = {c.get("accent") for c in d._CHARACTERS_STORE.values()}
        return next((a for a in accents if a not in used), "cyan")

    async def _probe_spark() -> dict:
        """Return {configured, available, host, error} without raising."""
        host = ""
        try:
            host = d._character_host_from_config() or ""
        except Exception as exc:  # pragma: no cover
            return {
                "configured": False,
                "available": False,
                "host": "",
                "error": str(exc),
            }
        if not host:
            return {
                "configured": False,
                "available": False,
                "host": "",
                "error": "COMFYUI_PRIMARY is not configured",
            }
        try:
            from core.dispatch.comfy_client import ComfyUIClient

            client = ComfyUIClient(host)
            ok, info = await client.check_health()
            err = ""
            if isinstance(info, dict):
                err = str(info.get("error") or "")
            return {
                "configured": True,
                "available": bool(ok),
                "host": host,
                "error": err if not ok else "",
            }
        except Exception as exc:
            return {
                "configured": True,
                "available": False,
                "host": host,
                "error": str(exc),
            }

    async def _save_photo_as_master(
        cid: str,
        char: dict,
        upload: UploadFile,
        *,
        notes: str = "auto-sheet master photo",
    ) -> tuple:
        """Persist photo under character refs and promote to master/anchor."""
        content = await upload.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty photo file")
        rec = save_character_reference_bytes(
            char_id=cid,
            filename=upload.filename or "auto_sheet_photo.jpg",
            content=content,
            banks_dir=d.CHARACTER_BANKS_DIR,
            reference_type="face_closeup",
            notes=notes,
        )
        normalized = d._normalize_character(cid, char)
        merged = apply_photo_to_character(normalized, rec, notes=notes)
        saved = d._persist_normalized_character(cid, merged)
        master = master_ref_from_upload(rec, notes=notes)
        return saved, rec, master

    async def _maybe_extract_panels(
        cid: str,
        sheet_url: str,
        *,
        rows: int,
        cols: int,
        prompt_id: str = "",
        make_master: bool = True,
    ) -> list:
        if not sheet_url:
            return []
        try:
            req = d.CharacterSheetExtractRequest(
                image_url=sheet_url,
                rows=rows,
                columns=cols,
                make_master=make_master,
                source_prompt_id=prompt_id or "",
                notes="auto-extracted from character sheet",
            )
            result = await d.api_extract_character_sheet_panels(cid, req)
            return list(result.get("panels") or []) if isinstance(result, dict) else []
        except Exception:
            # Extraction is best-effort; sheet render still counts as success
            return []

    async def _run_auto_sheet(
        *,
        cid: str,
        char: dict,
        file: Optional[UploadFile],
        prompt: str,
        rows: int,
        cols: int,
        extract_panels: bool,
        created: bool = False,
        workflow_id: str = "",
    ) -> dict:
        master = None
        upload_rec = None
        if file is not None and getattr(file, "filename", None):
            char, upload_rec, master = await _save_photo_as_master(
                cid, char, file, notes="auto-sheet master photo"
            )
        else:
            char = d._persist_normalized_character(cid, d._normalize_character(cid, char))
            masters = [r for r in (char.get("master_references") or []) if isinstance(r, dict)]
            if masters:
                master = masters[0]
            elif char.get("anchor_url"):
                master = {
                    "id": "master_anchor",
                    "url": char.get("anchor_url"),
                    "type": "face_closeup",
                    "source": "anchor_url",
                    "locked": True,
                    "notes": "existing anchor",
                }

        has_ref = bool(
            (master and master.get("url"))
            or char.get("anchor_url")
            or d._character_reference_urls(char)
        )
        if not has_ref:
            return build_auto_sheet_result(
                status="error",
                character_id=cid,
                character=char,
                master_reference=master,
                spark_available=False,
                spark_configured=bool(d._character_host_from_config()),
                rows=rows,
                cols=cols,
                created=created,
                message=spark_recovery_hint(has_reference=False),
                recovery_hint=spark_recovery_hint(has_reference=False),
                error="No face/body photo or master reference available",
            )

        sheet_prompt = build_auto_sheet_prompt(
            name=str(char.get("name") or cid),
            role=str(char.get("role") or char.get("description") or ""),
            user_prompt=prompt or "",
        )

        spark = await _probe_spark()
        if not spark["available"]:
            return build_auto_sheet_result(
                status="partial",
                character_id=cid,
                character=char,
                master_reference=master,
                spark_available=False,
                spark_configured=bool(spark["configured"]),
                prompt=sheet_prompt,
                rows=rows,
                cols=cols,
                created=created,
                message=(
                    "Photo locked as master reference. Sheet render skipped "
                    f"({'Spark not configured' if not spark['configured'] else 'Spark offline'})."
                ),
                recovery_hint=spark_recovery_hint(
                    configured=bool(spark["configured"]),
                    has_reference=True,
                ),
                error=str(spark.get("error") or ""),
            )

        # Spark healthy — submit sheet via existing render path
        ref_url = ""
        if master and master.get("url"):
            ref_url = str(master["url"])
        elif char.get("anchor_url"):
            ref_url = str(char.get("anchor_url"))
        else:
            refs = d._character_reference_urls(char)
            ref_url = refs[0] if refs else ""

        try:
            render_req = d.CharacterSparkRenderRequest(
                name=str(char.get("name") or cid),
                prompt=sheet_prompt,
                role=str(char.get("role") or ""),
                render_type="sheet",
                workflow_id=(workflow_id or "04_flux2_multi_reference_character_sheet").strip()
                or "04_flux2_multi_reference_character_sheet",
                save_character=True,
                character_id=cid,
                reference_image_url=ref_url,
                reference_image_urls=[ref_url] if ref_url else [],
            )
            render = await d.api_character_spark_render(render_req)
        except HTTPException as exc:
            # Photo already saved — return partial with detail
            detail = exc.detail
            err_text = detail if isinstance(detail, str) else str(detail)
            # Refresh character after possible partial writes
            char = d._CHARACTERS_STORE.get(cid) or char
            return build_auto_sheet_result(
                status="partial",
                character_id=cid,
                character=d._normalize_character(cid, char),
                master_reference=master,
                spark_available=True,
                spark_configured=True,
                prompt=sheet_prompt,
                rows=rows,
                cols=cols,
                created=created,
                message="Master reference saved; Spark sheet render failed.",
                recovery_hint=(
                    "Photo is locked. Fix Spark/workflow, then re-run Sheet from photo "
                    "or Generate Character Sheet for this character."
                ),
                error=err_text,
            )
        except Exception as exc:  # pragma: no cover
            char = d._CHARACTERS_STORE.get(cid) or char
            return build_auto_sheet_result(
                status="partial",
                character_id=cid,
                character=d._normalize_character(cid, char),
                master_reference=master,
                spark_available=True,
                spark_configured=True,
                prompt=sheet_prompt,
                rows=rows,
                cols=cols,
                created=created,
                message="Master reference saved; Spark sheet render failed.",
                recovery_hint=spark_recovery_hint(configured=True, has_reference=True),
                error=str(exc),
            )

        image_urls = list(render.get("image_urls") or []) if isinstance(render, dict) else []
        sheet_url = pick_sheet_url_from_render(render if isinstance(render, dict) else {})
        prompt_id = str((render or {}).get("prompt_id") or "")
        char = (render or {}).get("character") or d._CHARACTERS_STORE.get(cid) or char

        panels: list = []
        if extract_panels and sheet_url:
            panels = await _maybe_extract_panels(
                cid,
                sheet_url,
                rows=rows,
                cols=cols,
                prompt_id=prompt_id,
                make_master=True,
            )
            char = d._CHARACTERS_STORE.get(cid) or char

        return build_auto_sheet_result(
            status="complete",
            character_id=cid,
            character=char if isinstance(char, dict) else d._normalize_character(cid, {}),
            master_reference=master,
            spark_available=True,
            spark_configured=True,
            prompt_id=prompt_id,
            job_set_id=prompt_id,
            image_urls=image_urls,
            sheet_url=sheet_url,
            panels=panels,
            prompt=sheet_prompt,
            rows=rows,
            cols=cols,
            created=created,
            message=(
                "Character sheet generated."
                + (f" Extracted {len(panels)} panel(s)." if panels else "")
            ),
        )

    async def api_character_auto_sheet(
        char_id: str,
        file: Optional[UploadFile] = File(None),
        prompt: str = Form(""),
        create_if_missing: str = Form(""),
        name: str = Form(""),
        role: str = Form(""),
        rows: int = Form(2),
        cols: int = Form(3),
        columns: Optional[int] = Form(None),
        extract_panels: str = Form("true"),
        workflow_id: str = Form(""),
    ):
        """
        One-photo continuity pack for an existing character.

        - Optional multipart `file` becomes master reference + anchor when empty.
        - When Spark is healthy: submits render_type=sheet with reference lock.
        - When Spark is down: still saves the photo and returns status=partial.
        - Optional panel extract when a sheet image is produced.
        """
        r, c = clamp_grid(rows, columns if columns is not None else cols)
        cid = d._character_slug(char_id)
        created = False
        char = d._CHARACTERS_STORE.get(cid)
        if not char:
            # Only create when explicitly requested — do not treat path char_id as create_if_missing.
            create_name = (create_if_missing or name or "").strip()
            if not create_name:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Character '{char_id}' not found. "
                        "Pass create_if_missing=<name> or use /api/characters/auto-sheet-from-photo."
                    ),
                )
            cid = d._character_slug(create_name) or cid
            if not cid:
                raise HTTPException(status_code=400, detail="Invalid character name")
            draft = draft_character_record(
                char_id=cid,
                name=create_name,
                role=(role or "Character").strip() or "Character",
                accent=_next_accent(),
            )
            char = d._persist_normalized_character(cid, draft)
            created = True

        return await _run_auto_sheet(
            cid=cid,
            char=char,
            file=file,
            prompt=prompt or "",
            rows=r,
            cols=c,
            extract_panels=_truthy(extract_panels),
            created=created,
            workflow_id=workflow_id or "",
        )

    async def api_auto_sheet_from_photo(
        file: UploadFile = File(...),
        name: str = Form(""),
        role: str = Form("Character"),
        prompt: str = Form(""),
        rows: int = Form(2),
        cols: int = Form(3),
        columns: Optional[int] = Form(None),
        extract_panels: str = Form("true"),
        workflow_id: str = Form(""),
        char_id: str = Form(""),
    ):
        """
        Create a character from one face/body photo and build continuity sheet when Spark is up.

        Always persists the photo as master reference even if Spark is offline (status=partial).
        """
        if not file or not getattr(file, "filename", None):
            raise HTTPException(status_code=400, detail="Photo file is required")

        r, c = clamp_grid(rows, columns if columns is not None else cols)
        display_name = (name or "").strip() or name_from_filename(
            file.filename or "", fallback="New Character"
        )
        cid = d._character_slug(char_id or display_name)
        if not cid:
            raise HTTPException(status_code=400, detail="Invalid character name")

        created = False
        char = d._CHARACTERS_STORE.get(cid)
        if not char:
            draft = draft_character_record(
                char_id=cid,
                name=display_name,
                role=(role or "Character").strip() or "Character",
                accent=_next_accent(),
            )
            char = d._persist_normalized_character(cid, draft)
            created = True

        return await _run_auto_sheet(
            cid=cid,
            char=char,
            file=file,
            prompt=prompt or "",
            rows=r,
            cols=c,
            extract_panels=_truthy(extract_panels),
            created=created,
            workflow_id=workflow_id or "",
        )

    # Register F3 routes BEFORE /api/characters/{char_id}/... catch-alls where needed.
    # auto-sheet-from-photo must not be captured as {char_id}.
    router.add_api_route(
        "/api/characters/auto-sheet-from-photo",
        api_auto_sheet_from_photo,
        methods=["POST"],
    )
    router.add_api_route(
        "/api/characters/{char_id}/auto-sheet",
        api_character_auto_sheet,
        methods=["POST"],
    )
    return router
