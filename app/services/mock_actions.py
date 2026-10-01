from __future__ import annotations

from uuid import uuid4

from app.services.mock_warranty import MockWarrantyTool
from app.services.tool_registry import ToolRegistry


class MockServiceRequestTool:
    name = "create_service_request"
    description = "Creates a mock service request. No real action is performed."

    def run(self, args: dict) -> dict:
        return {
            "status": "mock_created",
            "reference_id": "MOCK-SERVICE-12345",
            "message": "Mock service request created. No real request was submitted.",
        }


class MockReplacementTool:
    name = "create_replacement_request"
    description = "Creates a mock replacement request. No real action is performed."

    def run(self, args: dict) -> dict:
        return {
            "status": "mock_created",
            "reference_id": "MOCK-REPLACE-12345",
            "message": "Mock replacement request created. No real request was submitted.",
        }


class MockServiceStatusTool:
    name = "check_mock_service_status"
    description = "Returns a mock status for a mock reference ID."

    def run(self, args: dict) -> dict:
        return {
            "status": "mock_created",
            "reference_id": args.get("reference_id", "MOCK-SERVICE-12345"),
            "message": "Mock service status returned. No real status system is connected.",
        }


class MockOrderPlacementTool:
    name = "place_mock_order"
    description = "Places a mock product order. No real payment or shipment is performed."

    def run(self, args: dict) -> dict:
        product_name = str(args.get("product_name") or "Unknown Product")
        return {
            "status": "mock_created",
            "reference_id": f"MOCK-ORDER-{uuid4().hex[:8].upper()}",
            "message": f"Mock order placed for {product_name}. No real order was submitted.",
        }


class MockOrderCancellationTool:
    name = "cancel_mock_order"
    description = "Cancels a mock product order. No real payment reversal is performed."

    def run(self, args: dict) -> dict:
        reference_id = str(args.get("reference_id") or "MOCK-ORDER-UNKNOWN")
        return {
            "status": "mock_cancelled",
            "reference_id": reference_id,
            "message": f"Mock order {reference_id} cancelled. No real order was cancelled.",
        }


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(MockWarrantyTool())
    registry.register(MockServiceRequestTool())
    registry.register(MockReplacementTool())
    registry.register(MockServiceStatusTool())
    registry.register(MockOrderPlacementTool())
    registry.register(MockOrderCancellationTool())
    return registry
