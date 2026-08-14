from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

SYMBOL = r"[A-Za-z_][A-Za-z0-9_.:/-]*"


class PolicyAstError(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    kind: str
    value: str


TOKEN_RE = re.compile(
    r"\s*(?:"
    r"(?P<STRING>\"(?:\\[\"\\/bfnrt]|\\u[0-9a-fA-F]{4}|[^\"\\\x00-\x1f])*\")|"
    r"(?P<NUMBER>[0-9]+(?:\.[0-9]+)?)|"
    r"(?P<PLACEHOLDER>\{" + SYMBOL + r"\})|"
    r"(?P<OP>!=|<=|>=|=|<|>|\+|-|\*|/|%)|"
    r"(?P<LBRACK>\[)|(?P<RBRACK>\])|"
    r"(?P<LPAREN>\()|(?P<RPAREN>\))|(?P<COMMA>,)|"
    r"(?P<SYMBOL>" + SYMBOL + r")"
    r")"
)


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    position = 0
    while position < len(source):
        match = TOKEN_RE.match(source, position)
        if not match:
            raise PolicyAstError(f"unexpected token near {source[position:position + 16]!r}")
        kind = match.lastgroup or ""
        value = match.group(kind)
        if kind == "SYMBOL" and value in {"AND", "OR", "NOT", "IN"}:
            kind = "OP"
        tokens.append(Token(kind, value))
        position = match.end()
    tokens.append(Token("EOF", ""))
    return tokens


class ExpressionParser:
    precedence = {
        "OR": 10,
        "AND": 20,
        "IN": 30,
        "=": 40,
        "!=": 40,
        "<": 50,
        "<=": 50,
        ">": 50,
        ">=": 50,
        "+": 60,
        "-": 60,
        "*": 70,
        "/": 70,
        "%": 70,
    }

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def take(self, kind: str | None = None) -> Token:
        current = self.current
        if kind is not None and current.kind != kind:
            raise PolicyAstError(f"expected {kind}, found {current.value!r}")
        self.index += 1
        return current

    def expression(self, minimum: int = 0) -> dict[str, Any]:
        current = self.current
        if current.kind == "OP" and current.value in {"NOT", "-"}:
            self.take()
            left = {"node": "unary", "operator": current.value, "operand": self.expression(80)}
        else:
            left = self.primary()
        while self.current.kind == "OP" and self.current.value in self.precedence:
            operator = self.current.value
            precedence = self.precedence[operator]
            if precedence < minimum:
                break
            self.take()
            right = self.expression(precedence + 1)
            left = {"node": "binary", "operator": operator, "left": left, "right": right}
        return left

    def primary(self) -> dict[str, Any]:
        current = self.current
        if current.kind == "STRING":
            self.take()
            return {"node": "literal", "value": json.loads(current.value)}
        if current.kind == "NUMBER":
            self.take()
            value: int | float = float(current.value) if "." in current.value else int(current.value)
            return {"node": "literal", "value": value}
        if current.kind == "SYMBOL":
            self.take()
            if current.value in {"TRUE", "FALSE", "true", "false"}:
                return {"node": "literal", "value": current.value in {"TRUE", "true"}}
            return {"node": "symbol", "name": current.value}
        if current.kind == "PLACEHOLDER":
            self.take()
            return {"node": "symbol", "name": current.value}
        if current.kind == "LBRACK":
            return self.collection("RBRACK", list_node=True)
        if current.kind == "LPAREN":
            return self.collection("RPAREN", list_node=False)
        raise PolicyAstError(f"expected expression, found {current.value!r}")

    def collection(self, closing: str, *, list_node: bool) -> dict[str, Any]:
        self.take()
        items: list[dict[str, Any]] = []
        while self.current.kind != closing:
            if self.current.kind == "EOF":
                raise PolicyAstError("unterminated collection")
            items.append(self.expression())
            if self.current.kind == "COMMA":
                self.take()
            elif self.current.kind != closing and list_node:
                raise PolicyAstError("list items require commas")
        self.take(closing)
        if not list_node and len(items) == 1:
            return items[0]
        if not list_node and len(items) < 2:
            raise PolicyAstError("empty grouping is forbidden")
        return {"node": "list" if list_node else "sequence", "items": items}

    def sequence(self) -> dict[str, Any] | None:
        items: list[dict[str, Any]] = []
        while self.current.kind != "EOF":
            if self.current.kind == "COMMA":
                self.take()
                continue
            if self.current.kind == "OP" and self.current.value not in {"NOT", "-"}:
                items.append({"node": "symbol", "name": self.take().value})
                continue
            items.append(self.expression())
        if not items:
            return None
        return items[0] if len(items) == 1 else {"node": "sequence", "items": items}


def parse_condition(source: str) -> dict[str, Any]:
    value = ExpressionParser(tokenize(source)).sequence()
    if value is None:
        raise PolicyAstError("condition must not be empty")
    return value


def parse_action(source: str) -> dict[str, Any]:
    tokens = tokenize(source)
    if tokens[0].kind != "SYMBOL" or not re.fullmatch(r"[A-Z][A-Z0-9_]*", tokens[0].value):
        raise PolicyAstError("action requires an uppercase opcode")
    opcode = tokens[0].value
    body = tokens[1:-1]
    depth = 0
    guard_at: int | None = None
    for index, current in enumerate(body):
        if current.kind in {"LPAREN", "LBRACK"}:
            depth += 1
        elif current.kind in {"RPAREN", "RBRACK"}:
            depth -= 1
        elif depth == 0 and current.kind == "SYMBOL" and current.value == "WHEN":
            guard_at = index
            break
    payload_tokens = body if guard_at is None else body[:guard_at]
    guard_tokens = [] if guard_at is None else body[guard_at + 1 :]
    payload = ExpressionParser(payload_tokens + [Token("EOF", "")]).sequence()
    guard = None
    if guard_at is not None:
        guard = ExpressionParser(guard_tokens + [Token("EOF", "")]).sequence()
        if guard is None:
            raise PolicyAstError("action WHEN requires a condition")
    words = source.split()
    return {
        "kind": "action",
        "opcode": opcode,
        "payload": payload,
        "guard": guard,
        # Compatibility projection for existing wellm emitters and consumers.
        "verb": opcode,
        "arguments": words[1:],
        "text": source,
    }


def parse_next(source: str) -> list[dict[str, Any]]:
    first = re.fullmatch(r"(" + SYMBOL + r")(.*)", source)
    if not first:
        raise PolicyAstError("NEXT requires a target")
    target, tail = first.group(1), first.group(2).strip()
    if not tail:
        return [{"target": target, "condition": None}]
    if tail.startswith("OR "):
        targets = [target] + tail[3:].split(" OR ")
        if any(not re.fullmatch(SYMBOL, value) for value in targets):
            raise PolicyAstError("invalid NEXT targets")
        return [{"target": value, "condition": None} for value in targets]
    if not tail.startswith("WHEN "):
        raise PolicyAstError("NEXT accepts OR or WHEN after its target")
    condition_source = tail[5:]
    fallback: str | None = None
    fallback_match = re.fullmatch(r"(.+) OR (" + SYMBOL + r")", condition_source)
    if fallback_match:
        condition_source, fallback = fallback_match.group(1), fallback_match.group(2)
    targets = [{"target": target, "condition": parse_condition(condition_source)}]
    if fallback is not None:
        targets.append({"target": fallback, "condition": None})
    return targets
