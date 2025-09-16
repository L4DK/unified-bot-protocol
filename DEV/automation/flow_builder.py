# automation/flow_builder.py
from typing import Dict, List, Any, Optional
from pydantic import BaseModel
from enum import Enum
import json
import uuid

class NodeType(Enum):
    TRIGGER = "trigger"
    CONDITION = "condition"
    ACTION = "action"
    TRANSFORM = "transform"
    AI_TASK = "ai_task"
    FLOW_CONTROL = "flow_control"

class ConnectionType(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DEFAULT = "default"
    CONDITION_TRUE = "condition_true"
    CONDITION_FALSE = "condition_false"

class FlowNode(BaseModel):
    """Node in the visual flow"""
    id: str
    type: NodeType
    name: str
    config: Dict[str, Any]
    position: Dict[str, int]
    metadata: Dict[str, Any]

class FlowConnection(BaseModel):
    """Connection between nodes"""
    id: str
    source_id: str
    target_id: str
    type: ConnectionType
    metadata: Dict[str, Any]

class Flow(BaseModel):
    """Complete flow definition"""
    id: str
    name: str
    description: str
    nodes: List[FlowNode]
    connections: List[FlowConnection]
    metadata: Dict[str, Any]
    version: int

class VisualFlowBuilder:
    def __init__(self):
        self.flows: Dict[str, Flow] = {}
        self.node_templates: Dict[str, Dict] = self._load_node_templates()

    def _load_node_templates(self) -> Dict[str, Dict]:
        """Load predefined node templates"""
        return {
            # Triggers
            "message_received": {
                "type": NodeType.TRIGGER,
                "config": {
                    "platforms": ["all"],
                    "message_types": ["text", "media"]
                }
            },
            "schedule": {
                "type": NodeType.TRIGGER,
                "config": {
                    "cron": "",
                    "timezone": "UTC"
                }
            },

            # Conditions
            "message_contains": {
                "type": NodeType.CONDITION,
                "config": {
                    "keywords": [],
                    "match_type": "any"
                }
            },
            "user_property": {
                "type": NodeType.CONDITION,
                "config": {
                    "property": "",
                    "value": ""
                }
            },

            # Actions
            "send_message": {
                "type": NodeType.ACTION,
                "config": {
                    "platform": "",
                    "message": "",
                    "variables": []
                }
            },
            "api_call": {
                "type": NodeType.ACTION,
                "config": {
                    "url": "",
                    "method": "GET",
                    "headers": {},
                    "body": {}
                }
            },

            # AI Tasks
            "sentiment_analysis": {
                "type": NodeType.AI_TASK,
                "config": {
                    "input": "${message}",
                    "model": "default"
                }
            },
            "content_generation": {
                "type": NodeType.AI_TASK,
                "config": {
                    "prompt": "",
                    "parameters": {}
                }
            },

            # Transforms
            "json_transform": {
                "type": NodeType.TRANSFORM,
                "config": {
                    "input": "",
                    "path": "",
                    "output": ""
                }
            },

            # Flow Control
            "branch": {
                "type": NodeType.FLOW_CONTROL,
                "config": {
                    "conditions": []
                }
            },
            "delay": {
                "type": NodeType.FLOW_CONTROL,
                "config": {
                    "duration": 0
                }
            }
        }

    def create_flow(
        self,
        name: str,
        description: str,
        metadata: Dict[str, Any] = None
    ) -> Flow:
        """Create a new flow"""
        flow_id = str(uuid.uuid4())
        flow = Flow(
            id=flow_id,
            name=name,
            description=description,
            nodes=[],
            connections=[],
            metadata=metadata or {},
            version=1
        )
        self.flows[flow_id] = flow
        return flow

    def add_node(
        self,
        flow_id: str,
        template_id: str,
        name: str,
        position: Dict[str, int],
        config: Dict[str, Any] = None
    ) -> FlowNode:
        """Add a node to the flow"""
        if flow_id not in self.flows:
            raise ValueError(f"Flow {flow_id} not found")

        template = self.node_templates.get(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")

        node = FlowNode(
            id=str(uuid.uuid4()),
            type=template["type"],
            name=name,
            config=config or template["config"].copy(),
            position=position,
            metadata={}
        )

        self.flows[flow_id].nodes.append(node)
        return node

    def connect_nodes(
        self,
        flow_id: str,
        source_id: str,
        target_id: str,
        connection_type: ConnectionType = ConnectionType.DEFAULT,
        metadata: Dict[str, Any] = None
    ) -> FlowConnection:
        """Connect two nodes"""
        if flow_id not in self.flows:
            raise ValueError(f"Flow {flow_id} not found")

        flow = self.flows[flow_id]

        # Verify nodes exist
        if not any(n.id == source_id for n in flow.nodes):
            raise ValueError(f"Source node {source_id} not found")
        if not any(n.id == target_id for n in flow.nodes):
            raise ValueError(f"Target node {target_id} not found")

        connection = FlowConnection(
            id=str(uuid.uuid4()),
            source_id=source_id,
            target_id=target_id,
            type=connection_type,
            metadata=metadata or {}
        )

        flow.connections.append(connection)
        return connection

    def update_node(
        self,
        flow_id: str,
        node_id: str,
        updates: Dict[str, Any]
    ) -> FlowNode:
        """Update a node's configuration"""
        if flow_id not in self.flows:
            raise ValueError(f"Flow {flow_id} not found")

        flow = self.flows[flow_id]
        node = next((n for n in flow.nodes if n.id == node_id), None)

        if not node:
            raise ValueError(f"Node {node_id} not found")

        for key, value in updates.items():
            if hasattr(node, key):
                setattr(node, key, value)
            elif key in node.config:
                node.config[key] = value

        return node

    def delete_node(self, flow_id: str, node_id: str):
        """Delete a node and its connections"""
        if flow_id not in self.flows:
            raise ValueError(f"Flow {flow_id} not found")

        flow = self.flows[flow_id]

        # Remove node
        flow.nodes = [n for n in flow.nodes if n.id != node_id]

        # Remove connected connections
        flow.connections = [
            c for c in flow.connections
            if c.source_id != node_id and c.target_id != node_id
        ]

    def validate_flow(self, flow_id: str) -> List[str]:
        """Validate flow configuration"""
        if flow_id not in self.flows:
            raise ValueError(f"Flow {flow_id} not found")

        flow = self.flows[flow_id]
        errors = []

        # Check for trigger nodes
        if not any(n.type == NodeType.TRIGGER for n in flow.nodes):
            errors.append("Flow must have at least one trigger node")

        # Check for disconnected nodes
        connected_nodes = set()
        for conn in flow.connections:
            connected_nodes.add(conn.source_id)
            connected_nodes.add(conn.target_id)

        for node in flow.nodes:
            if node.type != NodeType.TRIGGER and node.id not in connected_nodes:
                errors.append(f"Node {node.name} is disconnected")

        # Check for cycles
        if self._has_cycle(flow):
            errors.append("Flow contains cycles")

        return errors

    def _has_cycle(self, flow: Flow) -> bool:
        """Check if flow has cycles"""
        visited = set()
        path = set()

        def visit(node_id: str) -> bool:
            if node_id in path:
                return True
            if node_id in visited:
                return False

            visited.add(node_id)
            path.add(node_id)

            for conn in flow.connections:
                if conn.source_id == node_id:
                    if visit(conn.target_id):
                        return True

            path.remove(node_id)
            return False

        return any(
            visit(node.id)
            for node in flow.nodes
            if node.type == NodeType.TRIGGER
        )

    def export_flow(self, flow_id: str) -> Dict[str, Any]:
        """Export flow to automation rule format"""
        if flow_id not in self.flows:
            raise ValueError(f"Flow {flow_id} not found")

        flow = self.flows[flow_id]

        # Convert flow to automation rule
        triggers = []
        conditions = []
        actions = []

        # Process nodes in order
        processed_nodes = self._sort_nodes(flow)

        for node in processed_nodes:
            if node.type == NodeType.TRIGGER:
                triggers.append(node.config)
            elif node.type == NodeType.CONDITION:
                conditions.append(node.config)
            elif node.type in [NodeType.ACTION, NodeType.AI_TASK, NodeType.TRANSFORM]:
                actions.append({
                    "type": node.type.value,
                    **node.config
                })

        return {
            "id": flow.id,
            "name": flow.name,
            "description": flow.description,
            "enabled": True,
            "priority": 1,
            "triggers": triggers,
            "conditions": conditions,
            "actions": actions,
            "error_handling": {
                "action_error": "stop"
            },
            "metadata": flow.metadata,
            "version": flow.version
        }

    def _sort_nodes(self, flow: Flow) -> List[FlowNode]:
        """Sort nodes in execution order"""
        sorted_nodes = []
        visited = set()

        def visit(node_id: str):
            if node_id in visited:
                return
            visited.add(node_id)

            # Process incoming connections first
            for conn in flow.connections:
                if conn.target_id == node_id:
                    visit(conn.source_id)

            node = next(n for n in flow.nodes if n.id == node_id)
            sorted_nodes.append(node)

        # Start with trigger nodes
        trigger_nodes = [n for n in flow.nodes if n.type == NodeType.TRIGGER]
        for node in trigger_nodes:
            visit(node.id)

        return sorted_nodes