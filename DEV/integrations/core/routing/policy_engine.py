# filepath: core/routing/policy_engine.py
# project: Unified Bot Protocol (UBP)
# module: Routing Policy Engine
# version: 0.1.0
# last_edited: 2025-09-16
# author: Michael Landbo (UBP BDFL)
# license: Apache-2.0
# description:
#   Declarative allow/deny and selection constraints for routing decisions.
#
# changelog:
# - 0.1.0: Initial creation with safe predicate model.
#
# TODO:
# - Integrate with Management API for live policy updates
# - Add CEL-like expression language and compiled predicates

from __future__ import annotations
from typing import Dict, Any, List

class PolicyDecision:
    def __init__(self, allowed: bool, reasons: List[str] | None = None):
        self.allowed = allowed
        self.reasons = reasons or []

class PolicyEngine:
    """
    Policies example:
    {
      "allow_platforms": ["slack", "email", "mqtt_iot"],
      "deny_users": ["banned_user_1"],
      "max_content_length": 5000,
      "require_capabilities": ["supports_text"]
    }
    """
    def __init__(self, policies: Dict[str, Any] | None = None):
        self.policies = policies or {}

    def evaluate(self, message: Dict[str, Any], context: Dict[str, Any], adapter_capabilities: Dict[str, Any]) -> PolicyDecision:
        reasons: List[str] = []
        p = self.policies

        platform = context.get("target_platform") or context.get("source_platform")

        allow_list = p.get("allow_platforms")
        if allow_list is not None and platform not in allow_list:
            return PolicyDecision(False, [f"platform {platform} not allowed"])

        deny_users = set(p.get("deny_users", []))
        if context.get("user_id") in deny_users:
            return PolicyDecision(False, ["user denied"])

        max_len = p.get("max_content_length")
        if max_len is not None:
            content = message.get("content", "")
            if isinstance(content, dict):
                content = str(content)
            if len(content) > max_len:
                return PolicyDecision(False, ["content length exceeded"])

        req_caps = p.get("require_capabilities", [])
        for cap in req_caps:
            if not adapter_capabilities.get(cap, False):
                reasons.append(f"missing capability: {cap}")
        if reasons:
            return PolicyDecision(False, reasons)

        return PolicyDecision(True)