# automation/engine.py
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
import asyncio
import json
import logging
import aiohttp
from pydantic import BaseModel
from datetime import datetime, timedelta
import pytz
import re
from collections import defaultdict

class TriggerType(Enum):
    MESSAGE = "message"
    SCHEDULE = "schedule"
    EVENT = "event"
    CONDITION = "condition"
    WEBHOOK = "webhook"
    AI_INTENT = "ai_intent"
    METRIC = "metric"

class ActionType(Enum):
    SEND_MESSAGE = "send_message"
    API_CALL = "api_call"
    FUNCTION = "function"
    WAIT = "wait"
    CONDITION = "condition"
    AI_TASK = "ai_task"
    TRANSFORM = "transform"

class AutomationRule(BaseModel):
    """Definition of an automation rule"""
    id: str
    name: str
    description: str
    enabled: bool
    priority: int
    triggers: List[Dict[str, Any]]
    conditions: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    error_handling: Dict[str, Any]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int

class AutomationEngine:
    def __init__(self):
        self.logger = logging.getLogger("automation_engine")
        self.rules: Dict[str, AutomationRule] = {}
        self.triggers: Dict[str, List[str]] = defaultdict(list)
        self.action_handlers: Dict[str, Callable] = {}
        self.condition_handlers: Dict[str, Callable] = {}
        self.running_automations: Dict[str, asyncio.Task] = {}
        self.metrics = defaultdict(int)

        # Initialize handlers
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register default action and condition handlers"""
        # Action Handlers
        self.action_handlers.update({
            ActionType.SEND_MESSAGE.value: self._handle_send_message,
            ActionType.API_CALL.value: self._handle_api_call,
            ActionType.WAIT.value: self._handle_wait,
            ActionType.AI_TASK.value: self._handle_ai_task,
            ActionType.TRANSFORM.value: self._handle_transform
        })

        # Condition Handlers
        self.condition_handlers.update({
            "message_contains": self._check_message_contains,
            "time_between": self._check_time_between,
            "user_property": self._check_user_property,
            "metric_threshold": self._check_metric_threshold,
            "ai_sentiment": self._check_ai_sentiment
        })

    async def add_rule(self, rule: AutomationRule):
        """Add or update an automation rule"""
        self.rules[rule.id] = rule

        # Index triggers for faster lookup
        for trigger in rule.triggers:
            trigger_type = trigger["type"]
            self.triggers[trigger_type].append(rule.id)

        self.logger.info(f"Added automation rule: {rule.name}")

    async def remove_rule(self, rule_id: str):
        """Remove an automation rule"""
        if rule_id in self.rules:
            rule = self.rules.pop(rule_id)

            # Remove from trigger index
            for trigger_type in self.triggers:
                if rule_id in self.triggers[trigger_type]:
                    self.triggers[trigger_type].remove(rule_id)

            self.logger.info(f"Removed automation rule: {rule.name}")

    async def handle_event(self, event_type: str, event_data: Dict):
        """Handle incoming events and trigger automations"""
        try:
            # Find matching rules
            matching_rules = []
            for rule_id in self.triggers[event_type]:
                rule = self.rules[rule_id]
                if rule.enabled and await self._check_conditions(rule, event_data):
                    matching_rules.append(rule)

            # Sort by priority
            matching_rules.sort(key=lambda r: r.priority, reverse=True)

            # Execute matching rules
            for rule in matching_rules:
                task = asyncio.create_task(
                    self._execute_rule(rule, event_data)
                )
                self.running_automations[rule.id] = task

            self.metrics["events_processed"] += 1

        except Exception as e:
            self.logger.error(f"Error handling event: {str(e)}")
            self.metrics["event_errors"] += 1

    async def _execute_rule(self, rule: AutomationRule, event_data: Dict):
        """Execute an automation rule"""
        try:
            context = {
                "rule_id": rule.id,
                "event_data": event_data,
                "variables": {},
                "start_time": datetime.now(pytz.UTC)
            }

            self.logger.info(f"Executing rule: {rule.name}")

            # Execute actions in sequence
            for action in rule.actions:
                try:
                    handler = self.action_handlers.get(action["type"])
                    if handler:
                        result = await handler(action, context)
                        context["variables"].update(result or {})
                    else:
                        raise ValueError(f"Unknown action type: {action['type']}")

                except Exception as e:
                    self.logger.error(
                        f"Action error in rule {rule.name}: {str(e)}"
                    )
                    if rule.error_handling["action_error"] == "stop":
                        break

            self.metrics["rules_executed"] += 1

        except Exception as e:
            self.logger.error(f"Rule execution error: {str(e)}")
            self.metrics["rule_errors"] += 1
        finally:
            if rule.id in self.running_automations:
                del self.running_automations[rule.id]

    async def _check_conditions(
        self,
        rule: AutomationRule,
        event_data: Dict
    ) -> bool:
        """Check if all conditions are met"""
        try:
            for condition in rule.conditions:
                handler = self.condition_handlers.get(condition["type"])
                if handler:
                    if not await handler(condition, event_data):
                        return False
                else:
                    self.logger.warning(
                        f"Unknown condition type: {condition['type']}"
                    )
                    return False
            return True

        except Exception as e:
            self.logger.error(f"Condition check error: {str(e)}")
            return False

    # Action Handlers
    async def _handle_send_message(
        self,
        action: Dict,
        context: Dict
    ) -> Dict:
        """Handle send message action"""
        platform = action["platform"]
        message = self._interpolate_variables(
            action["message"],
            context["variables"]
        )

        # Send message through appropriate platform adapter
        # Implementation depends on platform adapter integration

        return {"message_sent": True, "platform": platform}

    async def _handle_api_call(
        self,
        action: Dict,
        context: Dict
    ) -> Dict:
        """Handle API call action"""
        url = self._interpolate_variables(action["url"], context["variables"])
        method = action["method"]
        headers = action.get("headers", {})
        body = action.get("body", {})

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                url,
                headers=headers,
                json=body
            ) as response:
                return await response.json()

    async def _handle_wait(
        self,
        action: Dict,
        context: Dict
    ) -> Dict:
        """Handle wait action"""
        duration = action["duration"]
        await asyncio.sleep(duration)
        return {"waited": duration}

    async def _handle_ai_task(
        self,
        action: Dict,
        context: Dict
    ) -> Dict:
        """Handle AI task action"""
        task_type = action["task_type"]
        input_data = self._interpolate_variables(
            action["input"],
            context["variables"]
        )

        # Integrate with AI service based on task type
        if task_type == "sentiment_analysis":
            sentiment = await self._analyze_sentiment(input_data)
            return {"sentiment": sentiment}
        elif task_type == "content_generation":
            content = await self._generate_content(input_data)
            return {"generated_content": content}
        elif task_type == "classification":
            category = await self._classify_content(input_data)
            return {"category": category}

        return {}

    async def _handle_transform(
        self,
        action: Dict,
        context: Dict
    ) -> Dict:
        """Handle data transformation action"""
        transform_type = action["transform_type"]
        input_data = self._interpolate_variables(
            action["input"],
            context["variables"]
        )

        if transform_type == "json_path":
            result = self._apply_json_path(
                input_data,
                action["path"]
            )
        elif transform_type == "template":
            result = self._apply_template(
                input_data,
                action["template"]
            )
        else:
            result = input_data

        return {"transformed_data": result}

    # Condition Handlers
    async def _check_message_contains(
        self,
        condition: Dict,
        event_data: Dict
    ) -> bool:
        """Check if message contains specific text"""
        if "message" not in event_data:
            return False

        text = event_data["message"].get("text", "").lower()
        keywords = [k.lower() for k in condition["keywords"]]

        if condition.get("match_type") == "any":
            return any(k in text for k in keywords)
        return all(k in text for k in keywords)

    async def _check_time_between(
        self,
        condition: Dict,
        event_data: Dict
    ) -> bool:
        """Check if current time is between specified times"""
        now = datetime.now(pytz.UTC)
        start_time = datetime.strptime(
            condition["start_time"],
            "%H:%M"
        ).time()
        end_time = datetime.strptime(
            condition["end_time"],
            "%H:%M"
        ).time()

        current_time = now.time()
        return start_time <= current_time <= end_time

    async def _check_user_property(
        self,
        condition: Dict,
        event_data: Dict
    ) -> bool:
        """Check user property condition"""
        if "user" not in event_data:
            return False

        user = event_data["user"]
        property_name = condition["property"]
        expected_value = condition["value"]

        return user.get(property_name) == expected_value

    async def _check_metric_threshold(
        self,
        condition: Dict,
        event_data: Dict
    ) -> bool:
        """Check if metric meets threshold"""
        metric_name = condition["metric"]
        threshold = condition["threshold"]
        operator = condition["operator"]

        current_value = self.metrics[metric_name]

        if operator == "gt":
            return current_value > threshold
        elif operator == "lt":
            return current_value < threshold
        elif operator == "eq":
            return current_value == threshold
        return False

    async def _check_ai_sentiment(
        self,
        condition: Dict,
        event_data: Dict
    ) -> bool:
        """Check sentiment condition"""
        if "message" not in event_data:
            return False

        text = event_data["message"].get("text", "")
        sentiment = await self._analyze_sentiment(text)

        return sentiment == condition["sentiment"]

    # Utility Methods
    def _interpolate_variables(
        self,
        template: str,
        variables: Dict
    ) -> str:
        """Replace variables in template with actual values"""
        for key, value in variables.items():
            template = template.replace(f"${{{key}}}", str(value))
        return template

    def _apply_json_path(self, data: Dict, path: str) -> Any:
        """Apply JSONPath expression to data"""
        # Implementation using jsonpath-ng or similar library
        pass

    def _apply_template(self, data: Dict, template: str) -> str:
        """Apply template to data"""
        # Implementation using Jinja2 or similar library
        pass

    async def _analyze_sentiment(self, text: str) -> str:
        """Analyze text sentiment"""
        # Implementation using AI service
        pass

    async def _generate_content(self, prompt: str) -> str:
        """Generate content using AI"""
        # Implementation using AI service
        pass

    async def _classify_content(self, text: str) -> str:
        """Classify content using AI"""
        # Implementation using AI service
        pass