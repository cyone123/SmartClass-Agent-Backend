from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from pydantic import BaseModel, Field, field_validator
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

import yaml

from app.config import get_skills_root
from app.core.progress import emit_progress

SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9-]{1,64}$")
SKILL_ALLOWED_TOOL_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
RESERVED_SKILL_TERMS = ("anthropic", "claude")
DEFAULT_SCRIPT_TIMEOUT_SECONDS = 30
MAX_SCRIPT_OUTPUT_CHARS = 12000
MAX_SCRIPT_OUTPUT_LINES = 200


class SkillValidationError(ValueError):
    """Raised when a skill definition is invalid."""


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    compatibility: str | None = None
    metadata: dict[str, str] | None = None
    allowed_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillDefinition:
    metadata: SkillMetadata
    root_path: Path
    skill_file_path: Path
    resource_files: tuple[str, ...]
    script_files: tuple[str, ...]
    reference_files: tuple[str, ...]
    template_files: tuple[str, ...]
    asset_files: tuple[str, ...]

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def description(self) -> str:
        return self.metadata.description

    @property
    def compatibility(self) -> str | None:
        return self.metadata.compatibility

    @property
    def metadata_map(self) -> dict[str, str]:
        return dict(self.metadata.metadata or {})

    @property
    def allowed_tools(self) -> tuple[str, ...]:
        return self.metadata.allowed_tools


@dataclass(frozen=True)
class SkillScriptResult:
    skill_name: str
    script_path: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    def format_for_agent(self) -> str:
        lines = [
            f"Skill script: {self.skill_name}/{self.script_path}",
            f"Exit code: {self.exit_code}",
        ]
        if self.timed_out:
            lines.append("Timed out: true")
        if self.stdout:
            lines.append("Stdout:")
            lines.append(self.stdout)
        if self.stderr:
            lines.append("Stderr:")
            lines.append(self.stderr)
        return "\n".join(lines)


def _truncate_output(text: str) -> str:
    if not text:
        return ""

    lines = text.splitlines()
    truncated = False
    if len(lines) > MAX_SCRIPT_OUTPUT_LINES:
        lines = lines[:MAX_SCRIPT_OUTPUT_LINES]
        truncated = True

    result = "\n".join(lines)
    if len(result) > MAX_SCRIPT_OUTPUT_CHARS:
        result = result[:MAX_SCRIPT_OUTPUT_CHARS]
        truncated = True

    if truncated:
        result = f"{result}\n...[truncated]"
    return result


def _split_frontmatter(raw_text: str, *, source: Path) -> tuple[dict[str, object], str]:
    if not raw_text.startswith("---\n") and raw_text != "---":
        raise SkillValidationError(f"{source} is missing YAML frontmatter.")

    delimiter = "\n---\n"
    end_index = raw_text.find(delimiter, 4)
    if end_index == -1:
        raise SkillValidationError(f"{source} has an unclosed YAML frontmatter block.")

    frontmatter_text = raw_text[4:end_index]
    body = raw_text[end_index + len(delimiter):].lstrip("\r\n")

    data = yaml.safe_load(frontmatter_text) or {}
    if not isinstance(data, dict):
        raise SkillValidationError(f"{source} frontmatter must be a YAML mapping.")
    return data, body


def _validate_skill_name(name: object, *, source: Path) -> str:
    if not isinstance(name, str):
        raise SkillValidationError(f"{source} frontmatter field 'name' must be a string.")
    if not SKILL_NAME_PATTERN.fullmatch(name):
        raise SkillValidationError(
            f"{source} has invalid skill name '{name}'. "
            "Only lowercase letters, numbers, and hyphens are allowed, max length 64."
        )
    lowered = name.lower()
    if any(term in lowered for term in RESERVED_SKILL_TERMS):
        raise SkillValidationError(
            f"{source} has invalid skill name '{name}'. Reserved terms are not allowed."
        )
    return name


def _validate_skill_description(description: object, *, source: Path) -> str:
    if not isinstance(description, str):
        raise SkillValidationError(f"{source} frontmatter field 'description' must be a string.")
    description = description.strip()
    if not description:
        raise SkillValidationError(f"{source} frontmatter field 'description' must not be empty.")
    if len(description) > 1024:
        raise SkillValidationError(
            f"{source} frontmatter field 'description' exceeds 1024 characters."
        )
    return description


def _validate_skill_compatibility(compatibility: object, *, source: Path) -> str | None:
    if compatibility is None:
        return None
    if not isinstance(compatibility, str):
        raise SkillValidationError(
            f"{source} frontmatter field 'compatibility' must be a string when provided."
        )
    normalized = compatibility.strip()
    if not normalized:
        return None
    if len(normalized) > 2048:
        raise SkillValidationError(
            f"{source} frontmatter field 'compatibility' exceeds 2048 characters."
        )
    return normalized


def _validate_skill_metadata_map(value: object, *, source: Path) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SkillValidationError(
            f"{source} frontmatter field 'metadata' must be a mapping when provided."
        )

    normalized: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise SkillValidationError(f"{source} metadata keys must be strings.")
        normalized_key = key.strip()
        if not normalized_key:
            raise SkillValidationError(f"{source} metadata keys must not be empty.")
        normalized[normalized_key] = str(item).strip()
    return normalized or None


def _normalize_allowed_tools(value: object, *, source: Path) -> tuple[str, ...]:
    if value is None:
        return ()

    raw_values: list[str]
    if isinstance(value, str):
        raw_values = [item.strip() for item in re.split(r"[\n,]+", value) if item.strip()]
    elif isinstance(value, (list, tuple)):
        raw_values = [str(item).strip() for item in value if str(item).strip()]
    else:
        raise SkillValidationError(
            f"{source} frontmatter field 'allowed-tools' must be a string or list of strings."
        )

    seen: set[str] = set()
    allowed_tools: list[str] = []
    for item in raw_values:
        if not SKILL_ALLOWED_TOOL_PATTERN.fullmatch(item):
            raise SkillValidationError(
                f"{source} has invalid allowed tool '{item}'."
            )
        if item in seen:
            continue
        seen.add(item)
        allowed_tools.append(item)
    return tuple(allowed_tools)


def _iter_relative_files(root_path: Path) -> tuple[str, ...]:
    file_paths: list[str] = []
    for path in sorted(root_path.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root_path).as_posix()
        file_paths.append(relative)
    return tuple(file_paths)


def _filter_files(paths: Iterable[str], *, prefix: str) -> tuple[str, ...]:
    return tuple(path for path in paths if path.startswith(prefix))


def _build_skill_definition(skill_dir: Path) -> SkillDefinition:
    skill_file_path = skill_dir / "SKILL.md"
    if not skill_file_path.is_file():
        raise SkillValidationError(f"Missing SKILL.md in {skill_dir}.")

    raw_text = skill_file_path.read_text(encoding="utf-8")
    frontmatter, _ = _split_frontmatter(raw_text, source=skill_file_path)

    metadata = SkillMetadata(
        name=_validate_skill_name(frontmatter.get("name"), source=skill_file_path),
        description=_validate_skill_description(
            frontmatter.get("description"),
            source=skill_file_path,
        ),
        compatibility=_validate_skill_compatibility(
            frontmatter.get("compatibility"),
            source=skill_file_path,
        ),
        metadata=_validate_skill_metadata_map(
            frontmatter.get("metadata"),
            source=skill_file_path,
        ),
        allowed_tools=_normalize_allowed_tools(
            frontmatter.get("allowed-tools"),
            source=skill_file_path,
        ),
    )

    all_files = tuple(path for path in _iter_relative_files(skill_dir) if path != "SKILL.md")
    return SkillDefinition(
        metadata=metadata,
        root_path=skill_dir.resolve(),
        skill_file_path=skill_file_path.resolve(),
        resource_files=all_files,
        script_files=_filter_files(all_files, prefix="scripts/"),
        reference_files=_filter_files(all_files, prefix="references/"),
        template_files=_filter_files(all_files, prefix="templates/"),
        asset_files=_filter_files(all_files, prefix="assets/"),
    )


def _resolve_child_path(root_path: Path, relative_path: str) -> Path:
    if not relative_path:
        raise SkillValidationError("Path must not be empty.")

    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise SkillValidationError("Absolute paths are not allowed.")

    resolved = (root_path / candidate).resolve()
    try:
        resolved.relative_to(root_path)
    except ValueError as exc:
        raise SkillValidationError("Path traversal outside the skill directory is not allowed.") from exc
    return resolved


def _script_command_for_path(script_path: Path) -> list[str]:
    suffix = script_path.suffix.lower()
    if suffix == ".py":
        return [sys.executable, str(script_path)]
    if suffix == ".ps1":
        return [
            "powershell",
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ]
    if suffix in {".bat", ".cmd"}:
        return ["cmd", "/c", str(script_path)]
    if suffix == ".sh":
        return ["sh", str(script_path)]
    if os.access(script_path, os.X_OK):
        return [str(script_path)]
    raise SkillValidationError(
        f"Unsupported script type '{script_path.suffix or '<none>'}' for {script_path.name}."
    )

def _format_file_listing(title: str, files: tuple[str, ...]) -> str:
    if not files:
        return f"{title}: none"
    lines = [f"{title}:"]
    lines.extend(f"- {file_path}" for file_path in files)
    return "\n".join(lines)


def _format_metadata_listing(metadata: dict[str, str] | None) -> str:
    if not metadata:
        return "Metadata: none"
    lines = ["Metadata:"]
    lines.extend(f"- {key}: {value}" for key, value in sorted(metadata.items()))
    return "\n".join(lines)


def _format_allowed_tools_listing(allowed_tools: tuple[str, ...]) -> str:
    if not allowed_tools:
        return "Allowed tools: none"
    return "Allowed tools: " + ", ".join(allowed_tools)

def _normalize_script_args(value: object) -> list[str] | None:
    if value is None:
        return None

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None

        if stripped.startswith("[") and stripped.endswith("]"):
            for parser in (json.loads, ast.literal_eval):
                try:
                    parsed = parser(stripped)
                except (ValueError, SyntaxError, json.JSONDecodeError):
                    continue
                value = parsed
                break
            else:
                return [stripped]
        else:
            return [stripped]

    if isinstance(value, tuple):
        value = list(value)

    if isinstance(value, list):
        return [str(item) for item in value]

    return [str(value)]

class RunSkillScriptInput(BaseModel):
    skill_name: str
    script_path: str
    script_args: list[str] | None = Field(
        default=None,
        description=(
            "Optional script arguments. Prefer a JSON array of strings. "
            "Single strings and stringified arrays are also accepted."
        ),
    )

    @field_validator("script_args", mode="before")
    @classmethod
    def validate_script_args(cls, value: object) -> list[str] | None:
        return _normalize_script_args(value)

class SkillToolset:
    """Registry-backed tools that implement progressive skill disclosure."""

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

        @tool
        def load_skill(
            skill_name: str,
            runtime: ToolRuntime,
        ) -> Command | str:
            """Load the full instructions for a skill when the task matches it.

            Use this after a request matches a skill description from the system prompt.
            This returns the skill instructions without YAML frontmatter plus the
            resource and script files available for further progressive disclosure.
            """
            print(f"==============尝试加载skills:{skill_name}=================")
            config = runtime.config
            emit_progress(
                config,
                "skill_activation",
                "running",
                detail=f"Loading skill {skill_name}",
            )
            try:
                canonical_name = self.registry.resolve_skill_name(skill_name)
                skill = self.registry.get_skill(canonical_name)
                body = self.registry.load_skill_body(canonical_name)
            except SkillValidationError as exc:
                emit_progress(
                    config,
                    "skill_activation",
                    "failed",
                    detail=str(exc),
                )
                return str(exc)
            
            sections = [
                f"Loaded skill: {canonical_name}",
                f"Description: {skill.description}",
                f"Compatibility: {skill.compatibility or 'none'}",
                _format_allowed_tools_listing(skill.allowed_tools),
                _format_metadata_listing(skill.metadata_map),
                _format_file_listing("Available references", skill.reference_files),
                _format_file_listing("Available templates", skill.template_files),
                _format_file_listing("Available assets", skill.asset_files),
                _format_file_listing("Available scripts", skill.script_files),
                "",
                body,
            ]
            print(f"==============加载skills完成:{skill_name}=================")
            content = "\n".join(section for section in sections if section != "")
            emit_progress(
                config,
                "skill_activation",
                "success",
                detail=f"Loaded skill {canonical_name}",
            )

            if runtime.tool_call_id is None:
                return content

            current_active_skills = list(runtime.state.get("active_skills", []) or [])
            if canonical_name not in current_active_skills:
                current_active_skills.append(canonical_name)

            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=content,
                            name="load_skill",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                    "active_skills": current_active_skills,
                }
            )

        @tool
        def read_skill_resource(skill_name: str, relative_path: str) -> str:
            """Read a text resource bundled inside a skill directory.

            Use this to progressively load supporting markdown, templates, and other
            files after loading a skill.
            """
            print(f"==============尝试加载skills资源:{skill_name}=================")
            try:
                canonical_name = self.registry.resolve_skill_name(skill_name)
                content = self.registry.read_skill_resource(canonical_name, relative_path)
            except SkillValidationError as exc:
                return str(exc)

            return (
                f"Loaded resource: {canonical_name}/{relative_path}\n\n"
                f"{content}"
            )

        @tool(args_schema=RunSkillScriptInput)
        def run_skill_script(
            skill_name: str,
            script_path: str,
            script_args: list[str] | None = None,
        ) -> str:
            """Execute a script from the skill's scripts directory.

            Use this for tasks that need to run scripts of specific skill. 
            script_path as a relative path like: 'scripts/one_script.py'
            Pass optional script arguments with `script_args`, ideally as a JSON array of strings.
            """
            print(f"==============尝试运行脚本skills:{skill_name}=================")
            try:
                canonical_name = self.registry.resolve_skill_name(skill_name)
                result = self.registry.run_skill_script(
                    canonical_name,
                    script_path,
                    args=script_args,
                )
            except SkillValidationError as exc:
                return str(exc)
            return result.format_for_agent()

        self.load_skill = load_skill
        self.read_skill_resource = read_skill_resource
        self.run_skill_script = run_skill_script
        self.tools = [load_skill, read_skill_resource, run_skill_script]


class SkillRegistry:
    def __init__(
        self,
        *,
        root_path: Path,
        skills: dict[str, SkillDefinition],
    ) -> None:
        self.root_path = root_path.resolve()
        self._skills = dict(sorted(skills.items()))
        

    @classmethod
    def from_root(
        cls,
        root_path: Path,
    ) -> SkillRegistry:
        resolved_root = root_path.resolve()
        if not resolved_root.exists():
            resolved_root.mkdir(parents=True, exist_ok=True)
        if not resolved_root.is_dir():
            raise SkillValidationError(f"Skills root is not a directory: {resolved_root}")

        skills: dict[str, SkillDefinition] = {}
        for skill_dir in sorted(resolved_root.iterdir()):
            if not skill_dir.is_dir():
                continue
            definition = _build_skill_definition(skill_dir)
            if definition.name in skills:
                raise SkillValidationError(
                    f"Duplicate skill name '{definition.name}' found in {skill_dir}."
                )
            skills[definition.name] = definition

        return cls(root_path=resolved_root, skills=skills)

    def list_metadata(self) -> list[SkillMetadata]:
        return [definition.metadata for definition in self._skills.values()]

    def list_skill_names(self) -> list[str]:
        return list(self._skills.keys())

    def resolve_skill_name(self, skill_name: str) -> str:
        normalized = skill_name.strip()
        if normalized in self._skills:
            return normalized
        raise SkillValidationError(
            f"Skill '{skill_name}' not found. Available skills: {', '.join(self.list_skill_names())}"
        )

    def get_skill(self, skill_name: str) -> SkillDefinition:
        return self._skills[self.resolve_skill_name(skill_name)]

    def skill_allows_tool(self, skill_name: str, tool_name: str) -> bool:
        skill = self.get_skill(skill_name)
        return tool_name in skill.allowed_tools

    def load_skill_body(self, skill_name: str) -> str:
        skill = self.get_skill(skill_name)
        raw_text = skill.skill_file_path.read_text(encoding="utf-8")
        _, body = _split_frontmatter(raw_text, source=skill.skill_file_path)
        return body.strip()

    def read_skill_resource(self, skill_name: str, relative_path: str) -> str:
        skill = self.get_skill(skill_name)
        resolved_path = _resolve_child_path(skill.root_path, relative_path)
        if not resolved_path.is_file():
            raise SkillValidationError(f"Skill resource '{relative_path}' was not found.")

        try:
            content = resolved_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            size_bytes = resolved_path.stat().st_size
            return (
                f"Resource '{relative_path}' is not UTF-8 text. "
                f"Use scripts or treat it as a binary asset. Size: {size_bytes} bytes."
            )
        return content

    def run_skill_script(
        self,
        skill_name: str,
        script_path: str,
        args: list[str] | None = None,
        *,
        timeout_seconds: int = DEFAULT_SCRIPT_TIMEOUT_SECONDS,
    ) -> SkillScriptResult:
        skill = self.get_skill(skill_name)
        resolved_path = _resolve_child_path(skill.root_path, script_path)
        scripts_root = (skill.root_path / "scripts").resolve()
        try:
            resolved_path.relative_to(scripts_root)
        except ValueError as exc:
            raise SkillValidationError(
                "Only files inside the skill's scripts/ directory may be executed."
            ) from exc
        if not resolved_path.is_file():
            raise SkillValidationError(f"Skill script '{script_path}' was not found.")

        command = _script_command_for_path(resolved_path)
        command.extend(args or [])
        try:
            completed = subprocess.run(
                command,
                cwd=skill.root_path,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            return SkillScriptResult(
                skill_name=skill.name,
                script_path=resolved_path.relative_to(skill.root_path).as_posix(),
                exit_code=completed.returncode,
                stdout=_truncate_output(completed.stdout),
                stderr=_truncate_output(completed.stderr),
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _truncate_output(exc.stdout or "")
            stderr = _truncate_output(exc.stderr or "")
            return SkillScriptResult(
                skill_name=skill.name,
                script_path=resolved_path.relative_to(skill.root_path).as_posix(),
                exit_code=-1,
                stdout=stdout,
                stderr=stderr,
                timed_out=True,
            )


def create_skill_registry(
    root_path: Path | None = None,
) -> SkillRegistry:
    resolved_root = root_path or get_skills_root()
    return SkillRegistry.from_root(
        resolved_root,
    )
