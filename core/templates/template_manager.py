import json
from pathlib import Path
from typing import Any, Dict, Optional


class TemplateManager:
    """
    Handles the retrieval of project-specific prompt configurations 
    and supports dynamic parameter injection.
    """

    def __init__(self, templates_dir: str = "~/Desktop/forge_nps/templates/"):
        self.templates_dir = Path(templates_dir)
        if not self.templates_dir.exists():
            raise FileNotFoundError(f"Templates directory not found: {self.templates_dir}")

    def get_template(self, template_name: str, overlays: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Retrieves a template by name and applies optional overlays for dynamic injection.
        
        Args:
            template_name: The name of the template (without .json extension).
            overlays: A dictionary of parameters to inject into the template.

        Returns:
            A dictionary containing the processed template content.
        """
        template_path = self.templates_dir / f"{template_name}.json"

        if not template_path.exists():
            raise FileNotFoundError(f"Template '{template_name}' not found at {template_path}")

        with open(template_path, 'r') as f:
            template_data = json.load(f)

        if overlays:
            template_data = self._apply_overlays(template_data, overlays)

        return template_data

    def _apply_overlays(self, data: Any, overlays: Dict[str, Any]) -> Any:
        """
        Recursively traverses the template data and replaces placeholders with overlay values.
        Placeholders are expected in the format '{{key}}'.
        """
        if isinstance(data, dict):
            return {k: self._apply_overlays(v, overlays) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._apply_overlays(item, overlays) for item in data]
        elif isinstance(data, str):
            return self._inject_string(data, overlays)
        else:
            return data

    def _inject_string(self, text: str, overlays: Dict[str, Any]) -> str:
        """
        Performs string replacement for placeholders.
        """
        for key, value in overlays.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in text:
                text = text.replace(placeholder, str(value))
        return text
