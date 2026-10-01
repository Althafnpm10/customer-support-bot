from __future__ import annotations


class MockWarrantyTool:
    name = "create_warranty_claim"
    description = "Creates a mock warranty claim. No real action is performed."

    def run(self, args: dict) -> dict:
        return {
            "status": "mock_created",
            "reference_id": "MOCK-WARRANTY-12345",
            "message": "Mock warranty claim created. No real request was submitted.",
        }

