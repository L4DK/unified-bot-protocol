# FilePath: "/DEV/integrations/core/routing/policy_engine.py"
# Project: Unified Bot Protocol (UBP)
# Module: Routing Policy Engine
# Version: 0.1.0
# Last_edited: 2025-09-16
# Author: "Michael Landbo"
# License: Apache-2.0
# Description:
#   Declarative allow/deny and selection constraints for routing decisions.
#
# Changelog:
# - 0.1.0: Initial creation with safe predicate model.

from __future__ import annotations
from typing import Dict, Any, List, Optional

class PolicyDecision:
    """Represents the result of a policy evaluation."""
    def __init__(self, allowed: bool, reasons: List[str] | None = None):
        self.allowed = allowed
        self.reasons = reasons or []

class PolicyEngine:
    """
    Evaluates messages against a set of policies to determine if they should be allowed.

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
        """
        Evaluates the policy against the provided message context and adapter capabilities.
        Returns a PolicyDecision object indicating allowed status and reasons.
        """
        reasons: List[str] = []
        p = self.policies

        # 1. Platform Check
        platform = context.get("target_platform") or context.get("source_platform")
        allow_list = p.get("allow_platforms")
        if allow_list is not None and platform not in allow_list:
            return PolicyDecision(False, [f"platform {platform} not allowed"])

        # 2. User Deny List Check
        deny_users = set(p.get("deny_users", []))
        if context.get("user_id") in deny_users:
            return PolicyDecision(False, ["user denied"])

        # 3. Content Length Check
        max_len = p.get("max_content_length")
        if max_len is not None:
            content = message.get("content", "")
            if isinstance(content, dict):
                content = str(content)
            if len(content) > max_len:
                return PolicyDecision(False, ["content length exceeded"])

        # 4. Required Capabilities Check
        req_caps = p.get("require_capabilities", [])
        for cap in req_caps:
            # Check if the adapter capabilities dict has the required capability set to True
            if not adapter_capabilities.get(cap, False):
                reasons.append(f"missing capability: {cap}")

        if reasons:
            return PolicyDecision(False, reasons)

        return PolicyDecision(True)
