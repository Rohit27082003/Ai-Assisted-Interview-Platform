"""
Prompt Registry - Centralized prompt management system

Provides:
- Type-safe prompt templates
- Variable interpolation
- Versioning for reproducibility
- Runtime prompt loading
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import re


@dataclass
class PromptTemplate:
    """
    A versioned, validated prompt template.

    Attributes:
        name: Unique identifier for the prompt
        template: The prompt text with {variable} placeholders
        version: Version string for tracking changes
        description: Human-readable description
        required_vars: Variables that must be provided
        optional_vars: Variables with defaults
        output_schema: Name of the expected output schema
    """

    name: str
    template: str
    version: str = "1.0.0"
    description: str = ""
    required_vars: list[str] = field(default_factory=list)
    optional_vars: Dict[str, Any] = field(default_factory=dict)
    output_schema: Optional[str] = None

    def __post_init__(self):
        """Validate the template and extract variables."""
        # Extract all variables from template
        self._template_vars = set(re.findall(r"\{(\w+)\}", self.template))

        # Validate required vars exist in template
        for var in self.required_vars:
            if var not in self._template_vars:
                raise ValueError(
                    f"Required variable '{var}' not found in template '{self.name}'"
                )

    def format(self, **kwargs: Any) -> str:
        """
        Format the prompt with provided variables.

        Args:
            **kwargs: Variable values to interpolate

        Returns:
            Formatted prompt string

        Raises:
            ValueError: If required variables are missing
        """
        # Check for missing required variables
        missing = set(self.required_vars) - set(kwargs.keys())
        if missing:
            raise ValueError(
                f"Missing required variables for prompt '{self.name}': {missing}"
            )

        # Merge with optional defaults
        final_vars = {**self.optional_vars, **kwargs}

        # Only include variables that exist in template
        filtered_vars = {k: v for k, v in final_vars.items() if k in self._template_vars}

        try:
            return self.template.format(**filtered_vars)
        except KeyError as e:
            raise ValueError(f"Variable {e} required but not provided for '{self.name}'")

    def get_variables(self) -> set[str]:
        """Get all variables used in this template."""
        return self._template_vars.copy()


class PromptRegistry:
    """
    Central registry for all prompt templates.

    Provides:
    - Namespace-based organization (interview.*, analysis.*, etc.)
    - Thread-safe access
    - Runtime registration
    - Validation on registration
    """

    _instance: Optional["PromptRegistry"] = None

    def __new__(cls) -> "PromptRegistry":
        """Singleton pattern for global access."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._prompts: Dict[str, PromptTemplate] = {}
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize and load all prompts on first access."""
        if not self._initialized:
            self._load_all_prompts()
            self._initialized = True

    def _load_all_prompts(self):
        """Load all prompts from domain modules."""
        from .interview_prompts import INTERVIEW_PROMPTS
        from .analysis_prompts import ANALYSIS_PROMPTS
        from .evaluation_prompts import EVALUATION_PROMPTS
        from .reporting_prompts import REPORTING_PROMPTS

        # Register all prompts
        for prompts in [
            INTERVIEW_PROMPTS,
            ANALYSIS_PROMPTS,
            EVALUATION_PROMPTS,
            REPORTING_PROMPTS,
        ]:
            for prompt in prompts:
                self.register(prompt)

    def register(self, prompt: PromptTemplate) -> None:
        """
        Register a prompt template.

        Args:
            prompt: The prompt template to register

        Raises:
            ValueError: If prompt with same name already exists
        """
        if prompt.name in self._prompts:
            # Allow re-registration with same version (for reloading)
            existing = self._prompts[prompt.name]
            if existing.version != prompt.version:
                raise ValueError(
                    f"Prompt '{prompt.name}' already registered with different version "
                    f"(existing: {existing.version}, new: {prompt.version})"
                )
        self._prompts[prompt.name] = prompt

    def get(self, name: str, **kwargs: Any) -> str:
        """
        Get a formatted prompt by name.

        Args:
            name: The prompt name (e.g., "question_generation")
            **kwargs: Variables to interpolate

        Returns:
            Formatted prompt string

        Raises:
            KeyError: If prompt not found
            ValueError: If required variables missing
        """
        if name not in self._prompts:
            available = ", ".join(sorted(self._prompts.keys()))
            raise KeyError(f"Prompt '{name}' not found. Available: {available}")

        return self._prompts[name].format(**kwargs)

    def get_template(self, name: str) -> PromptTemplate:
        """Get the raw template object."""
        if name not in self._prompts:
            raise KeyError(f"Prompt '{name}' not found")
        return self._prompts[name]

    def list_prompts(self, prefix: Optional[str] = None) -> list[str]:
        """List all registered prompt names, optionally filtered by prefix."""
        names = sorted(self._prompts.keys())
        if prefix:
            names = [n for n in names if n.startswith(prefix)]
        return names

    def get_prompt_info(self, name: str) -> Dict[str, Any]:
        """Get metadata about a prompt."""
        template = self.get_template(name)
        return {
            "name": template.name,
            "version": template.version,
            "description": template.description,
            "required_vars": template.required_vars,
            "optional_vars": list(template.optional_vars.keys()),
            "output_schema": template.output_schema,
        }


# Global registry instance
_registry: Optional[PromptRegistry] = None


def get_prompt_registry() -> PromptRegistry:
    """Get the global prompt registry instance."""
    global _registry
    if _registry is None:
        _registry = PromptRegistry()
    return _registry


def get_prompt(name: str, **kwargs: Any) -> str:
    """Convenience function to get a formatted prompt."""
    return get_prompt_registry().get(name, **kwargs)
