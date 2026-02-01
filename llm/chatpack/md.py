from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import List


@dataclass
class MarkdownDoc:
    lines: List[str] = field(default_factory=list)

    def h1(self, s: str) -> None:
        self.lines.append(f"# {s}")

    def bullet(self, s: str) -> None:
        self.lines.append(f"- {s}")

    def sec(self, s: str) -> None:
        self.lines.append("")
        self.lines.append(f"## {s}")

    def sub(self, s: str) -> None:
        self.lines.append("")
        self.lines.append(f"### {s}")

    def codeblock(self, body: str) -> None:
        self.lines.append("```")
        if body.strip():
            self.lines.append(body.rstrip())
        self.lines.append("```")

    def cmd_block(self, title: str, argv: List[str], output: str, rc: int) -> None:
        self.sub(title)
        cmdline = "+ " + " ".join(shlex.quote(x) for x in argv)
        self.codeblock(f"{cmdline}\\n{output.rstrip()}\\n(rc={rc})")

    def text(self, s: str = "") -> None:
        self.lines.append(s)

    def render(self) -> str:
        return "\\n".join(self.lines) + "\\n"
