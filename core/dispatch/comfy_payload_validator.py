"""
ComfyUI Payload Validator — Pre-flight checks for ComfyUI API submissions.

Catches the specific errors that broke Sienna Nomad EP01 (Apr 16):
  • Node missing class_type (web UI format leaked into API endpoint)
  • Invalid model references (z_image_turbo_bf16, flux2-dev-nvfp4-mixed)
  • Missing required nodes (KSampler, SaveImage, CLIPTextEncode)
  • Broken input connections (references to non-existent nodes)
  • Workflow format mismatch (API vs Web UI 'nodes' array)

Usage:
    validator = ComfyPayloadValidator()
    report = validator.validate(payload_dict, models_available=[...])
    if not report.is_valid:
        print(report.errors)
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger("ComfyPayloadValidator")


@dataclass
class ValidationReport:
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    missing_models: List[str] = field(default_factory=list)
    orphaned_nodes: List[str] = field(default_factory=list)
    missing_required_nodes: List[str] = field(default_factory=list)

    def add_error(self, msg: str):
        self.is_valid = False
        self.errors.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)


class ComfyPayloadValidator:
    """
    Validates a ComfyUI API payload before HTTP submission.
    """

    REQUIRED_NODE_TYPES = {
        "KSampler",
        "SaveImage",
        "CLIPTextEncode",
    }

    # Nodes that must have a valid model/checkpoint loaded upstream
    MODEL_DEPENDENT_TYPES = {
        "UNETLoader",
        "CheckpointLoaderSimple",
        "DualCLIPLoader",
        "CLIPLoader",
    }

    def __init__(self):
        self._known_webui_keys = {"nodes", "links", "groups"}

    def validate(
        self,
        payload: Dict[str, Any],
        models_available: Optional[List[str]] = None,
        strict: bool = True,
    ) -> ValidationReport:
        """
        Run full validation suite on a ComfyUI payload.

        Args:
            payload: The JSON dict to validate.
            models_available: List of model filenames known to exist on the target ComfyUI.
            strict: If True, warnings about unknown models become errors.
        """
        report = ValidationReport()

        # 1. Top-level structure & format checks
        self._check_top_level(payload, report)
        self._check_not_webui_format(payload, report)
        if not report.is_valid and strict:
            return report

        workflow = payload.get("prompt", {})

        # 3. Every node must have class_type
        self._check_all_nodes_have_class_type(workflow, report)

        # 4. Required nodes present
        self._check_required_nodes(workflow, report)

        # 5. Input connections resolve to existing nodes
        self._check_input_connections(workflow, report)

        # 6. Model references exist (if models_available provided)
        if models_available is not None:
            self._check_model_references(workflow, models_available, report, strict=strict)

        # 7. Seed present in KSampler
        self._check_k_sampler_seeds(workflow, report)

        # 8. SaveImage has filename_prefix
        self._check_saveimage_filenames(workflow, report)

        return report

    def validate_file(
        self,
        path: str | Path,
        models_available: Optional[List[str]] = None,
        strict: bool = True,
    ) -> ValidationReport:
        """Load JSON from disk and validate."""
        p = Path(path)
        if not p.exists():
            report = ValidationReport()
            report.add_error(f"File not found: {p}")
            return report
        try:
            with open(p, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except json.JSONDecodeError as e:
            report = ValidationReport()
            report.add_error(f"Invalid JSON in {p}: {e}")
            return report
        return self.validate(payload, models_available=models_available, strict=strict)

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_top_level(self, payload: Dict, report: ValidationReport):
        if not isinstance(payload, dict):
            report.add_error("Payload must be a JSON object (dict)")
            return
        # Allow video descriptor format (content capture, not a workflow yet)
        if payload.get("type") == "VIDEO_PROMPT" or payload.get("status") == "awaiting_ltx_workflow":
            return
        if "prompt" not in payload:
            report.add_error("Missing top-level 'prompt' key — this is the API format.")

    def _check_not_webui_format(self, payload: Dict, report: ValidationReport):
        """
        The Web UI workflow format uses 'nodes', 'links', 'groups' keys.
        The API format uses 'prompt': {node_id: {class_type, inputs}}.
        """
        # Skip video descriptors
        if payload.get("type") == "VIDEO_PROMPT" or payload.get("status") == "awaiting_ltx_workflow":
            return
        overlap = self._known_webui_keys & set(payload.keys())
        if overlap:
            report.add_error(
                f"Payload appears to be Web UI format (found keys: {overlap}). "
                f"Convert to API format with 'prompt': {{node_id: {{...}}}} before submitting."
            )

    def _check_all_nodes_have_class_type(self, workflow: Dict, report: ValidationReport):
        if not workflow:
            return
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                report.add_error(f"Node '{node_id}' is not a dict: {type(node).__name__}")
                continue
            class_type = node.get("class_type")
            if not class_type:
                report.add_error(
                    f"Node 'ID #{node_id}' has no class_type. "
                    f"The workflow may be corrupted or a custom node is missing."
                )
            elif not isinstance(class_type, str):
                report.add_error(
                    f"Node 'ID #{node_id}' class_type must be a string, got {type(class_type).__name__}"
                )

    def _check_required_nodes(self, workflow: Dict, report: ValidationReport):
        if not workflow:
            return
        present_types = {
            node.get("class_type")
            for node in workflow.values()
            if isinstance(node, dict) and isinstance(node.get("class_type"), str)
        }
        missing = self.REQUIRED_NODE_TYPES - present_types
        if missing:
            report.missing_required_nodes = sorted(missing)
            report.add_error(f"Missing required node types: {sorted(missing)}")

    def _check_input_connections(self, workflow: Dict, report: ValidationReport):
        if not workflow:
            return
        node_ids = set(workflow.keys())
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs", {})
            if not isinstance(inputs, dict):
                continue
            for input_name, input_val in inputs.items():
                # ComfyUI connections are [node_id, slot_index]
                if isinstance(input_val, list) and len(input_val) == 2:
                    ref_node_id, slot_idx = input_val
                    if str(ref_node_id) not in node_ids:
                        report.orphaned_nodes.append(str(ref_node_id))
                        report.add_error(
                            f"Node '{node_id}' input '{input_name}' references "
                            f"non-existent node '{ref_node_id}'"
                        )

    def _check_model_references(
        self,
        workflow: Dict,
        models_available: List[str],
        report: ValidationReport,
        strict: bool = True,
    ):
        if not workflow:
            return
        available_set = set(models_available)
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type", "")
            inputs = node.get("inputs", {})
            if class_type in self.MODEL_DEPENDENT_TYPES and isinstance(inputs, dict):
                for key in ("unet_name", "ckpt_name", "clip_name", "vae_name", "model_name"):
                    if key in inputs:
                        model_name = inputs[key]
                        if model_name and model_name not in available_set:
                            report.missing_models.append(model_name)
                            msg = (
                                f"Node '{node_id}' ({class_type}) references model "
                                f"'{model_name}' which is not in available models list."
                            )
                            if strict:
                                report.add_error(msg)
                            else:
                                report.add_warning(msg)

    def _check_k_sampler_seeds(self, workflow: Dict, report: ValidationReport):
        if not workflow:
            return
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") == "KSampler":
                inputs = node.get("inputs", {})
                seed = inputs.get("seed")
                if seed is None:
                    report.add_warning(
                        f"Node '{node_id}' (KSampler) has no seed — will use default/random."
                    )

    def _check_saveimage_filenames(self, workflow: Dict, report: ValidationReport):
        if not workflow:
            return
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") == "SaveImage":
                prefix = node.get("inputs", {}).get("filename_prefix", "")
                if not prefix or prefix == "ComfyUI":
                    report.add_warning(
                        f"Node '{node_id}' (SaveImage) has generic filename_prefix '{prefix}'. "
                        f"Consider using a descriptive prefix to avoid overwrites."
                    )


# ------------------------------------------------------------------
# Batch scanner for project folders
# ------------------------------------------------------------------

def scan_project_payloads(project_root: str | Path) -> Dict[str, ValidationReport]:
    """
    Recursively find all JSON payload files and validate them.
    Returns dict mapping file path -> ValidationReport.
    """
    root = Path(project_root)
    results = {}
    validator = ComfyPayloadValidator()

    for json_file in root.rglob("*.json"):
        # Skip non-payload JSONs (state files, configs)
        if any(x in json_file.name.lower() for x in ("state", "config", "metadata", "settings")):
            continue
        report = validator.validate_file(json_file)
        results[str(json_file)] = report

    return results


def print_scan_summary(results: Dict[str, ValidationReport]):
    total = len(results)
    valid = sum(1 for r in results.values() if r.is_valid)
    invalid = total - valid

    print(f"\n{'='*60}")
    print("  Payload Validation Scan")
    print(f"{'='*60}")
    print(f"  Total files scanned: {total}")
    print(f"  Valid:   {valid}")
    print(f"  Invalid: {invalid}")
    print()

    if invalid:
        print("  INVALID FILES:")
        for path, report in sorted(results.items()):
            if not report.is_valid:
                print(f"    ❌ {path}")
                for err in report.errors[:3]:
                    print(f"       → {err}")
                if len(report.errors) > 3:
                    print(f"       ... and {len(report.errors) - 3} more errors")
        print()

    # Summary of common errors
    error_counter: Dict[str, int] = {}
    for report in results.values():
        for err in report.errors:
            # Normalize error messages for grouping
            if "no class_type" in err:
                key = "missing_class_type"
            elif "Web UI format" in err:
                key = "web_ui_format"
            elif "Missing required node" in err:
                key = "missing_required_nodes"
            elif "non-existent node" in err:
                key = "orphaned_connections"
            elif "not in available models" in err:
                key = "missing_model"
            else:
                key = "other"
            error_counter[key] = error_counter.get(key, 0) + 1

    if error_counter:
        print("  ERROR CATEGORIES:")
        for category, count in sorted(error_counter.items(), key=lambda x: -x[1]):
            print(f"    {category}: {count}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python comfy_payload_validator.py <project_root>")
        sys.exit(1)
    results = scan_project_payloads(sys.argv[1])
    print_scan_summary(results)
